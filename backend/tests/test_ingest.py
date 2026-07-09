"""Knowledge ingestion pipeline tests (Module 10).

Own fixtures: Postgres ad_test_knowledge on localhost:5474 (created if
missing) with the pgvector extension and SQLModel create_all. NO test
touches the network: fetch results are injected via build_fetch_result.
"""

import asyncio
import hashlib
import io

import asyncpg
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

import app.models as models
from app.core.config import Settings
from app.ingest.chunker import chunk_text
from app.ingest.embedder import NoneProvider, VoyageProvider, get_embedding_provider
from app.ingest.extractor import extract_text
from app.ingest.fetcher import build_fetch_result
from app.ingest.pipeline import ingest
from app.ingest.registry import UNRESOLVED_URL, RegistrySource, load_registry
from app.models import AuditEvent, Estate, KnowledgeChunk, KnowledgeDoc
from app.services.storage import LocalStorage

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_knowledge"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

FAKE_URL = "https://example.test/guidance/iht400"

FAKE_HTML = b"""<html>
<head><title>IHT400 guidance</title><style>body { colour: black }</style></head>
<body>
<nav>Skip navigation links that must never be extracted</nav>
<script>console.log('never extracted either')</script>
<h1>Inheritance Tax account IHT400</h1>
<p>Use form IHT400 if the estate does not qualify as an excepted estate.</p>
<h2>Residence nil rate band</h2>
<p>The residence nil rate band is claimed with schedule IHT435.</p>
<ul><li>Send the account within twelve months of the end of the month of death.</li></ul>
<footer>Crown copyright footer chrome</footer>
</body>
</html>"""

FAKE_HTML_CHANGED = FAKE_HTML.replace(
    b"claimed with schedule IHT435",
    b"claimed with schedule IHT435 and transferred with schedule IHT436",
)


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
async def estate_id(session_factory):
    import datetime as dt

    async with session_factory() as session:
        estate = Estate(
            name="Knowledge test estate",
            date_of_death=dt.date(2026, 7, 3),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.commit()
        return estate.id


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "knowledge-storage")


@pytest.fixture
def source() -> RegistrySource:
    return RegistrySource(
        form_code_or_topic="IHT400",
        title="Inheritance Tax account (IHT400) and IHT400 notes",
        url=FAKE_URL,
        licence="Open Government Licence v3.0",
        jurisdiction="England and Wales",
    )


def make_fetcher(content: bytes, content_type: str = "text/html; charset=utf-8"):
    async def _fake_fetch(url: str):
        return build_fetch_result(url, content, content_type)

    return _fake_fetch


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_loads_and_skips_unresolved_urls():
    sources = load_registry()
    keys = {source.key for source in sources}
    assert "IHT400" in keys
    assert "rnrb_guidance" in keys
    # The three TO-RESOLVE entries are skipped with a logged note.
    assert "IHT435" not in keys
    assert "rnrb_transfer_guidance" not in keys
    assert "checklist_moneyhelper" not in keys
    assert all(source.url != UNRESOLVED_URL for source in sources)
    # Every entry carries the full provenance set.
    assert all(source.title and source.licence and source.jurisdiction for source in sources)


def test_registry_form_code_and_topic_split():
    form = RegistrySource(
        form_code_or_topic="IHT435", title="t", url="u", licence="l", jurisdiction="j"
    )
    topic = RegistrySource(
        form_code_or_topic="rnrb_guidance", title="t", url="u", licence="l", jurisdiction="j"
    )
    assert form.form_code == "IHT435" and form.topic is None
    assert topic.form_code is None and topic.topic == "rnrb_guidance"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


def test_extract_html_drops_chrome_and_keeps_structure():
    extracted = extract_text(FAKE_HTML, "text/html; charset=utf-8")
    assert "Skip navigation" not in extracted
    assert "console.log" not in extracted
    assert "colour: black" not in extracted
    assert "Crown copyright footer" not in extracted
    assert "# Inheritance Tax account IHT400" in extracted
    assert "## Residence nil rate band" in extracted
    assert "excepted estate" in extracted
    assert "twelve months" in extracted


def test_extract_plain_text_passthrough():
    assert extract_text(b"Plain guidance text.\n", "text/plain") == "Plain guidance text."


def test_extract_pdf_does_not_crash_on_valid_pdf():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    extracted = extract_text(buffer.getvalue(), "application/pdf")
    assert isinstance(extracted, str)


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


def test_chunker_indices_headings_and_overlap():
    body_a = " ".join(f"alpha{n}" for n in range(600))
    body_b = " ".join(f"beta{n}" for n in range(200))
    doc = f"# Section one\n\n{body_a}\n\n## Section two\n\n{body_b}"

    chunks = chunk_text(doc, size=1500, overlap=200)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= 1500 for chunk in chunks)
    assert {chunk.heading for chunk in chunks} == {"Section one", "Section two"}
    first = [chunk for chunk in chunks if chunk.heading == "Section one"]
    assert len(first) >= 2
    # Overlap: the head of the second chunk sits inside the first chunk.
    assert first[1].text[:150] in first[0].text


def test_chunker_short_text_is_one_chunk():
    chunks = chunk_text("# Heading\n\nOne short paragraph.")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].heading == "Heading"
    assert chunks[0].text == "One short paragraph."


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


def test_none_provider_returns_none_and_is_default_when_model_empty():
    assert NoneProvider().embed_texts(["a", "b"]) is None
    provider = get_embedding_provider(Settings(EMBEDDING_MODEL=""))
    assert isinstance(provider, NoneProvider)


def test_voyage_provider_is_a_clear_stub():
    provider = get_embedding_provider(Settings(EMBEDDING_MODEL="voyage-3-large"))
    assert isinstance(provider, VoyageProvider)
    with pytest.raises(NotImplementedError, match="not implemented"):
        provider.embed_texts(["a"])


# ---------------------------------------------------------------------------
# Pipeline against Postgres
# ---------------------------------------------------------------------------


async def test_ingest_stores_doc_chunks_hash_and_audit(session_factory, estate_id, storage, source):
    async with session_factory() as session:
        report = await ingest(
            session,
            source,
            estate_id=estate_id,
            actor="admin@test.local",
            fetcher=make_fetcher(FAKE_HTML),
            storage=storage,
        )

    assert report.status == "ingested"
    assert report.changed is False
    assert report.version == 1
    assert report.chunk_count >= 1

    async with session_factory() as session:
        doc = await session.get(KnowledgeDoc, report.doc_id)
        assert doc is not None
        assert doc.source_url == FAKE_URL
        assert doc.title == source.title
        assert doc.form_code == "IHT400"
        assert doc.jurisdiction == "England and Wales"
        assert doc.licence == "Open Government Licence v3.0"
        assert doc.content_hash == hashlib.sha256(FAKE_HTML).hexdigest()
        assert doc.version == 1
        assert doc.fetch_date is not None
        assert "excepted estate" in (doc.extracted_text or "")
        # The raw fetched file is stored with a retrievable key.
        assert doc.raw_file_key and storage.exists(doc.raw_file_key)
        assert storage.read(doc.raw_file_key) == FAKE_HTML

        chunks = (
            (
                await session.execute(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.knowledge_doc_id == doc.id)
                    .order_by(KnowledgeChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )
        assert len(chunks) == report.chunk_count
        assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
        # EMBEDDING_MODEL is empty in tests, so embeddings are NULL.
        assert all(chunk.embedding is None for chunk in chunks)

        audits = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.entity == f"knowledge_doc:{doc.id}")
                )
            )
            .scalars()
            .all()
        )
        assert any(event.action == "create" for event in audits)
        assert all(event.estate_id == estate_id for event in audits)


async def test_reingest_unchanged_content_skips(session_factory, estate_id, storage, source):
    fetcher = make_fetcher(FAKE_HTML)
    async with session_factory() as session:
        first = await ingest(
            session, source, estate_id=estate_id, fetcher=fetcher, storage=storage
        )
    async with session_factory() as session:
        second = await ingest(
            session, source, estate_id=estate_id, fetcher=fetcher, storage=storage
        )

    assert second.status == "unchanged"
    assert second.changed is False
    assert second.doc_id == first.doc_id
    assert second.version == 1

    async with session_factory() as session:
        doc = await session.get(KnowledgeDoc, first.doc_id)
        assert doc.version == 1
        count = len(
            
                (
                    await session.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.knowledge_doc_id == first.doc_id
                        )
                    )
                )
                .scalars()
                .all()
            
        )
        assert count == first.chunk_count


async def test_changed_content_bumps_version_and_replaces_chunks(
    session_factory, estate_id, storage, source
):
    async with session_factory() as session:
        first = await ingest(
            session,
            source,
            estate_id=estate_id,
            fetcher=make_fetcher(FAKE_HTML),
            storage=storage,
        )
    async with session_factory() as session:
        second = await ingest(
            session,
            source,
            estate_id=estate_id,
            fetcher=make_fetcher(FAKE_HTML_CHANGED),
            storage=storage,
        )

    assert second.status == "changed"
    assert second.changed is True
    assert second.doc_id == first.doc_id
    assert second.version == 2

    async with session_factory() as session:
        doc = await session.get(KnowledgeDoc, first.doc_id)
        assert doc.version == 2
        assert doc.content_hash == hashlib.sha256(FAKE_HTML_CHANGED).hexdigest()

        chunk_texts = [
            chunk.text
            for chunk in (
                (
                    await session.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.knowledge_doc_id == first.doc_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        ]
        assert any("IHT436" in chunk for chunk in chunk_texts)

        audits = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity == f"knowledge_doc:{first.doc_id}"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(event.action == "update" for event in audits)


async def test_fetch_failure_is_reported_not_raised(session_factory, estate_id, storage, source):
    async def _broken_fetch(url: str):
        raise RuntimeError("connection refused (synthetic)")

    async with session_factory() as session:
        report = await ingest(
            session,
            source,
            estate_id=estate_id,
            fetcher=_broken_fetch,
            storage=storage,
        )
    assert report.status == "error"
    assert "connection refused" in (report.detail or "")
    async with session_factory() as session:
        docs = (await session.execute(select(KnowledgeDoc))).scalars().all()
        assert docs == []
