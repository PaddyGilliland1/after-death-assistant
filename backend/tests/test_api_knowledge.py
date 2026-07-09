"""Knowledge library API tests: hybrid search, docs, admin-gated ingest
and cited Q&A.

Own fixtures: Postgres ad_test_knowledge on localhost:5474 (created if
missing) with the pgvector extension and SQLModel create_all; the router
is mounted on a fresh app with get_session overridden. NO network calls:
ingest tests monkeypatch the router's _fetch seam and QA tests
monkeypatch the _call_llm seam.
"""

import asyncio
import datetime as dt
import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

import app.models as models
from app.api import knowledge as knowledge_api
from app.db import get_session
from app.ingest.fetcher import build_fetch_result
from app.models import AuditEvent, Estate, KnowledgeChunk, KnowledgeDoc

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_knowledge"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

ADMIN = "admin@test.local"
EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"

DIM = 1024

FAKE_HTML = b"""<html><body>
<h1>Inheritance Tax account IHT400</h1>
<p>Use form IHT400 if the estate does not qualify as an excepted estate.</p>
</body></html>"""


def _prepare_database() -> None:
    async def _run() -> None:
        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await connection.run_sync(SQLModel.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.fixture(scope="module", autouse=True)
def _database() -> None:
    _prepare_database()


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    tables = ", ".join(f'"{table.name}"' for table in SQLModel.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def client_for(session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    from app.core.config import get_settings

    get_settings.cache_clear()

    application = FastAPI()
    application.include_router(knowledge_api.router)

    async def _override_session():
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(application)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    return _make


@pytest.fixture
async def estate_id(session_factory) -> uuid.UUID:
    async with session_factory() as session:
        estate = Estate(
            name="Knowledge API test estate",
            date_of_death=dt.date(2026, 7, 3),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.commit()
        return estate.id


async def _add_doc(
    session_factory,
    estate_id: uuid.UUID,
    *,
    title: str,
    chunks: list[tuple[str, list[float] | None]],
    form_code: str | None = None,
    source_url: str = "https://example.test/guidance",
) -> uuid.UUID:
    async with session_factory() as session:
        doc = KnowledgeDoc(
            estate_id=estate_id,
            source_url=source_url,
            title=title,
            form_code=form_code,
            topic=None if form_code else "guidance",
            jurisdiction="England and Wales",
            fetch_date=dt.date(2026, 7, 1),
            content_hash="deadbeef",
            version=1,
            licence="Open Government Licence v3.0",
            extracted_text="\n\n".join(chunk_text for chunk_text, _ in chunks),
            created_by="test-fixture",
        )
        session.add(doc)
        await session.flush()
        for index, (chunk_text, embedding) in enumerate(chunks):
            session.add(
                KnowledgeChunk(
                    estate_id=estate_id,
                    knowledge_doc_id=doc.id,
                    chunk_index=index,
                    text=chunk_text,
                    embedding=embedding,
                    created_by="test-fixture",
                )
            )
        await session.commit()
        return doc.id


def _unit_vector(axis: int) -> list[float]:
    vector = [0.0] * DIM
    vector[axis] = 1.0
    return vector


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def test_search_fts_returns_relevant_chunk(session_factory, estate_id, client_for):
    await _add_doc(
        session_factory,
        estate_id,
        title="Claim for residence nil rate band (IHT435)",
        form_code="IHT435",
        source_url="https://example.test/iht435",
        chunks=[
            ("The residence nil rate band is claimed with schedule IHT435.", None),
            ("Funeral expenses are deductible from the estate.", None),
        ],
    )

    response = client_for(EXECUTOR).get(
        "/knowledge/search", params={"q": "residence nil rate band"}
    )
    assert response.status_code == 200, response.text
    hits = response.json()
    assert hits, "expected at least one full-text hit"
    top = hits[0]
    assert "residence nil rate band" in top["chunk_text"]
    assert top["doc_title"] == "Claim for residence nil rate band (IHT435)"
    assert top["form_code"] == "IHT435"
    assert top["source_url"] == "https://example.test/iht435"
    assert top["licence"] == "Open Government Licence v3.0"
    assert top["fetch_date"] == "2026-07-01"
    assert top["chunk_index"] == 0
    assert top["score"] > 0
    # The irrelevant funeral chunk is not ranked above the match.
    assert all("Funeral" not in hit["chunk_text"] or hit is not top for hit in hits)


async def test_search_merges_vector_hits_with_fts(
    session_factory, estate_id, client_for, monkeypatch
):
    query_vector = _unit_vector(0)
    await _add_doc(
        session_factory,
        estate_id,
        title="Residence nil rate band guidance",
        source_url="https://example.test/rnrb",
        chunks=[("The residence nil rate band is an extra threshold.", None)],
    )
    await _add_doc(
        session_factory,
        estate_id,
        title="Semantically related guidance",
        source_url="https://example.test/semantic",
        chunks=[("Zebra quagga xylophone marmalade paragraph.", query_vector)],
    )

    monkeypatch.setattr(knowledge_api, "_embed_query", lambda question: query_vector)

    response = client_for(EXECUTOR).get(
        "/knowledge/search", params={"q": "residence nil rate band"}
    )
    assert response.status_code == 200, response.text
    texts = [hit["chunk_text"] for hit in response.json()]
    # FTS found the lexical match AND cosine found the embedded chunk.
    assert any("residence nil rate band" in chunk for chunk in texts)
    assert any("Zebra quagga" in chunk for chunk in texts)


async def test_search_readable_by_viewer_and_requires_auth(
    session_factory, estate_id, client_for
):
    assert client_for(VIEWER).get("/knowledge/search", params={"q": "estate"}).status_code == 200
    assert client_for(None).get("/knowledge/search", params={"q": "estate"}).status_code == 401


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------


async def test_docs_list_metadata_and_detail_text(session_factory, estate_id, client_for):
    doc_id = await _add_doc(
        session_factory,
        estate_id,
        title="Paying Inheritance Tax",
        chunks=[("Pay by the end of the sixth month after the death.", None)],
    )
    client = client_for(VIEWER)

    listing = client.get("/knowledge/docs")
    assert listing.status_code == 200
    docs = listing.json()
    assert len(docs) == 1
    assert docs[0]["title"] == "Paying Inheritance Tax"
    assert docs[0]["licence"] == "Open Government Licence v3.0"
    assert docs[0]["version"] == 1
    assert "extracted_text" not in docs[0]

    detail = client.get(f"/knowledge/docs/{doc_id}")
    assert detail.status_code == 200
    assert "sixth month" in detail.json()["extracted_text"]

    assert client.get(f"/knowledge/docs/{uuid.uuid4()}").status_code == 404


# ---------------------------------------------------------------------------
# Ingest (admin only; internet-fetching endpoint)
# ---------------------------------------------------------------------------


async def test_ingest_is_admin_only(estate_id, client_for):
    assert client_for(EXECUTOR).post("/knowledge/ingest", json={}).status_code == 403
    assert client_for(VIEWER).post("/knowledge/ingest", json={}).status_code == 403
    assert client_for(None).post("/knowledge/ingest", json={}).status_code == 401


async def test_admin_ingest_runs_pipeline_and_audits(
    session_factory, estate_id, client_for, monkeypatch
):
    async def _fake_fetch(url: str):
        return build_fetch_result(url, FAKE_HTML, "text/html; charset=utf-8")

    monkeypatch.setattr(knowledge_api, "_fetch", _fake_fetch)

    response = client_for(ADMIN).post(
        "/knowledge/ingest", json={"source_keys": ["IHT400", "no_such_source"]}
    )
    assert response.status_code == 200, response.text
    reports = {report["source_key"]: report for report in response.json()}
    assert reports["IHT400"]["status"] == "ingested"
    assert reports["IHT400"]["version"] == 1
    assert reports["IHT400"]["chunk_count"] >= 1
    assert reports["no_such_source"]["status"] == "not_found"

    docs = client_for(VIEWER).get("/knowledge/docs").json()
    assert [doc["form_code"] for doc in docs] == ["IHT400"]

    async with session_factory() as session:
        run_events = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.entity == "knowledge_registry")
                )
            )
            .scalars()
            .all()
        )
        assert len(run_events) == 1
        assert run_events[0].action == "ingest_run"
        assert run_events[0].actor == ADMIN
        doc_events = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.action == "create")
                )
            )
            .scalars()
            .all()
        )
        assert any(event.entity.startswith("knowledge_doc:") for event in doc_events)


async def test_ingest_requires_an_active_estate(session_factory, client_for):
    response = client_for(ADMIN).post("/knowledge/ingest", json={"source_keys": ["IHT400"]})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------


def _enable_qa_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    from app.core.config import get_settings

    get_settings.cache_clear()


async def test_qa_returns_503_without_api_key(
    session_factory, estate_id, client_for, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()

    response = client_for(EXECUTOR).post(
        "/knowledge/qa", json={"question": "When is IHT due?"}
    )
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_qa_returns_cited_answer(session_factory, estate_id, client_for, monkeypatch):
    await _add_doc(
        session_factory,
        estate_id,
        title="Inheritance Tax account (IHT400)",
        form_code="IHT400",
        source_url="https://example.test/iht400",
        chunks=[("Use form IHT400 if the estate does not qualify as an excepted estate.", None)],
    )
    _enable_qa_key(monkeypatch)

    seen: dict[str, str] = {}

    def _fake_llm(system_prompt: str, user_prompt: str, settings) -> str:
        seen["system"] = system_prompt
        seen["user"] = user_prompt
        return (
            "You must complete form IHT400 when the estate is not an excepted "
            f"estate [1]. {knowledge_api.GUIDANCE_NOTE}"
        )

    monkeypatch.setattr(knowledge_api, "_call_llm", _fake_llm)

    response = client_for(EXECUTOR).post(
        "/knowledge/qa", json={"question": "Which form is used for an excepted estate?"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "[1]" in body["answer"]
    assert body["sources"] == [
        {
            "n": 1,
            "doc_title": "Inheritance Tax account (IHT400)",
            "source_url": "https://example.test/iht400",
            "form_code": "IHT400",
        }
    ]
    # The LLM only ever sees the cached extracts, with citation numbering.
    assert "[1]" in seen["user"]
    assert "excepted estate" in seen["user"]
    assert "ONLY the numbered extracts" in seen["system"]


async def test_qa_refuses_when_retrieval_is_empty(
    session_factory, estate_id, client_for, monkeypatch
):
    _enable_qa_key(monkeypatch)

    def _must_not_be_called(system_prompt: str, user_prompt: str, settings) -> str:
        raise AssertionError("The LLM must not be called when retrieval is empty")

    monkeypatch.setattr(knowledge_api, "_call_llm", _must_not_be_called)

    response = client_for(EXECUTOR).post(
        "/knowledge/qa", json={"question": "What colour is the probate registry door?"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True
    assert body["sources"] == []
    assert body["answer"] == knowledge_api.REFUSAL_TEXT


async def test_qa_marks_model_refusal(session_factory, estate_id, client_for, monkeypatch):
    await _add_doc(
        session_factory,
        estate_id,
        title="Paying Inheritance Tax",
        chunks=[("Pay by the end of the sixth month after the death.", None)],
    )
    _enable_qa_key(monkeypatch)
    monkeypatch.setattr(
        knowledge_api, "_call_llm", lambda s, u, settings: knowledge_api.REFUSAL_TEXT
    )

    response = client_for(EXECUTOR).post(
        "/knowledge/qa", json={"question": "sixth month payment deadline"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["sources"] == []
