"""Knowledge chat: native-citation postprocessing, memory harness, RBAC."""

import uuid
from dataclasses import dataclass, field

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.api import knowledge_chat as chat_api
from app.db import get_session
from app.models import Estate, KnowledgeChunk, KnowledgeDoc
from app.services import qa_chat

ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB = "ad_test_chat"
TEST_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB}"

EXECUTOR = "exec@test.local"
VIEWER = "view@test.local"


@dataclass
class FakeCitation:
    cited_text: str
    search_result_index: int
    type: str = "search_result_location"


@dataclass
class FakeBlock:
    text: str
    citations: list | None = None
    type: str = "text"


@dataclass
class FakeResponse:
    content: list = field(default_factory=list)


@pytest.fixture(scope="module", autouse=True)
def _database():
    import asyncio

    async def prepare():
        conn = await asyncpg.connect(ADMIN_DSN)
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", TEST_DB
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        await conn.close()
        engine = create_async_engine(TEST_URL, poolclass=NullPool)
        async with engine.begin() as c:
            await c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await c.run_sync(SQLModel.metadata.create_all)
        await engine.dispose()

    asyncio.run(prepare())


@pytest.fixture()
def harness(monkeypatch):
    import asyncio

    monkeypatch.setenv("DEV_AUTH", "true")
    monkeypatch.setenv(
        "USER_ROLES", f"{EXECUTOR}:executor,{VIEWER}:viewer"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    estate_id = uuid.uuid4()

    async def seed():
        async with factory() as session:
            session.add(Estate(id=estate_id, name="Chat Test Estate", created_by="seed"))
            doc = KnowledgeDoc(
                id=uuid.uuid4(),
                estate_id=estate_id,
                source_url="https://example.test/probate",
                title="Applying for probate",
                form_code=None,
                topic="probate",
                jurisdiction="England and Wales",
                licence="Open Government Licence v3.0",
                content_hash="x",
                version=1,
                extracted_text="",
                created_by="seed",
            )
            session.add(doc)
            await session.flush()
            session.add(
                KnowledgeChunk(
                    estate_id=estate_id,
                    knowledge_doc_id=doc.id,
                    chunk_index=0,
                    text="You must apply for probate before dealing with the estate.",
                    created_by="seed",
                )
            )
            await session.commit()

    asyncio.run(seed())

    app = FastAPI()
    app.include_router(chat_api.router)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override

    def client_for(email: str) -> TestClient:
        client = TestClient(app)
        client.headers["X-Dev-User"] = email
        return client

    yield client_for
    get_settings.cache_clear()

    async def cleanup():
        async with factory() as session:
            for table in (
                "audit_event",
                "qa_pinned_snippet",
                "qa_message",
                "qa_conversation",
                "task_comment",
                "task",
                "process_step",
                "asset",
                "knowledge_chunk",
                "knowledge_doc",
                "estate",
            ):
                await session.execute(text(f'DELETE FROM "{table}"'))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def _answer_with_citation(index: int = 0) -> FakeResponse:
    return FakeResponse(
        content=[
            FakeBlock(
                text="You must apply for probate first.",
                citations=[
                    FakeCitation(
                        cited_text=(
                            "You must apply for probate before dealing with "
                            "the estate."
                        ),
                        search_result_index=index,
                    )
                ],
            ),
            FakeBlock(
                text=(
                    "\n\nWhat the retrieved guidance does not cover\n"
                    "Timing details."
                )
            ),
        ]
    )


def test_markers_inserted_and_sources_split(harness, monkeypatch):
    captured: dict = {}

    def fake_api(system, messages, settings):
        captured["messages"] = messages
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    response = harness(EXECUTOR).post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    message = body["message"]
    assert "[1]" in message["content"]
    assert "What the retrieved guidance does not cover" in message["content"]
    assert len(message["sources_cited"]) == 1
    cited = message["sources_cited"][0]
    assert cited["n"] == 1
    assert cited["doc_title"] == "Applying for probate"
    assert cited["quotes"] == [
        "You must apply for probate before dealing with the estate."
    ]
    # question is the final text block, after the search results
    final_content = captured["messages"][-1]["content"]
    assert final_content[-1]["type"] == "text"
    assert final_content[0]["type"] == "search_result"


def test_second_turn_supplies_pinned_snippet(harness, monkeypatch):
    calls: list = []

    def fake_api(system, messages, settings):
        calls.append(messages)
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    client = harness(EXECUTOR)
    first = client.post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    ).json()
    second = client.post(
        "/knowledge/chat",
        json={
            "conversation_id": first["conversation_id"],
            "question": "And who applies for it?",
        },
    )
    assert second.status_code == 200, second.text
    final_content = calls[-1][-1]["content"]
    titles = [
        block["title"] for block in final_content if block["type"] == "search_result"
    ]
    assert any("pinned from earlier" in title for title in titles)
    # history replayed as plain turns
    assert calls[-1][0]["role"] == "user"
    assert calls[-1][1]["role"] == "assistant"


def test_refusal_when_nothing_retrieved(harness, monkeypatch):
    def fake_api(system, messages, settings):  # pragma: no cover
        raise AssertionError("API must not be called with nothing to ground in")

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    response = harness(EXECUTOR).post(
        "/knowledge/chat", json={"question": "zzqx unrelated nonsense zzqx"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "could not find anything" in body["message"]["content"]
    assert body["message"]["sources_cited"] == []


def test_viewer_cannot_post_but_can_read(harness, monkeypatch):
    def fake_api(system, messages, settings):
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    executor = harness(EXECUTOR)
    made = executor.post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    ).json()
    viewer = harness(VIEWER)
    assert (
        viewer.post("/knowledge/chat", json={"question": "hello there"}).status_code
        == 403
    )
    assert viewer.get("/knowledge/chats").status_code == 200
    thread = viewer.get(f"/knowledge/chats/{made['conversation_id']}/messages")
    assert thread.status_code == 200
    assert len(thread.json()) == 2


def test_contract_retry_on_missing_heading(harness, monkeypatch):
    calls = {"n": 0}

    def fake_api(system, messages, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(
                content=[FakeBlock(text="Just an answer, no heading.")]
            )
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    response = harness(EXECUTOR).post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    )
    assert response.status_code == 200
    assert calls["n"] == 2
    assert "What the retrieved guidance does not cover" in response.json()["message"]["content"]


def test_conversation_from_another_estate_is_not_found(harness, monkeypatch):
    import asyncio

    def fake_api(system, messages, settings):
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    executor = harness(EXECUTOR)
    made = executor.post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    ).json()

    # Move the conversation to a different estate to simulate cross-tenancy.
    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def move():
        async with factory() as session:
            other = Estate(id=uuid.uuid4(), name="Other Estate", created_by="seed")
            session.add(other)
            await session.flush()
            await session.execute(
                text("UPDATE qa_conversation SET estate_id = :e WHERE id = :c"),
                {"e": str(other.id), "c": made["conversation_id"]},
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(move())

    cid = made["conversation_id"]
    assert executor.get(f"/knowledge/chats/{cid}/messages").status_code == 404
    follow = executor.post(
        "/knowledge/chat",
        json={"conversation_id": cid, "question": "follow up attempt"},
    )
    assert follow.status_code == 404
    archived = executor.request(
        "DELETE", f"/knowledge/chats/{cid}", json={"reason": "test"}
    )
    assert archived.status_code == 404


def test_estate_progress_context_supplied_and_tailoring_only(harness, monkeypatch):
    import asyncio

    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed_progress():
        from decimal import Decimal

        from app.models import Asset, ProcessStep, Task, TaskComment

        async with factory() as session:
            estate = (
                await session.execute(text('SELECT id FROM estate LIMIT 1'))
            ).scalar_one()
            step = ProcessStep(
                estate_id=estate, order=1, name="Value the estate",
                status="not_started", created_by="seed",
            )
            session.add(step)
            await session.flush()
            task = Task(
                estate_id=estate, title="Ask the bank for balances",
                status="in_progress", created_by="seed",
            )
            session.add(task)
            await session.flush()
            session.add(
                TaskComment(
                    estate_id=estate, task_id=task.id,
                    body="Bank says allow ten working days", created_by="seed",
                )
            )
            session.add(
                Asset(
                    estate_id=estate, category="property",
                    description="Example house", ownership="sole",
                    dod_value=Decimal("250000"), value_basis="estimate",
                    created_by="seed",
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed_progress())

    captured: dict = {}

    def fake_api(system, messages, settings):
        captured["messages"] = messages
        return _answer_with_citation(0)

    monkeypatch.setattr(qa_chat, "_call_chat_api", fake_api)
    response = harness(EXECUTOR).post(
        "/knowledge/chat", json={"question": "Do I need probate before selling?"}
    )
    assert response.status_code == 200
    final_content = captured["messages"][-1]["content"]
    progress_blocks = [
        b for b in final_content
        if b["type"] == "text" and "Current details of this estate" in b["text"]
    ]
    assert len(progress_blocks) == 1
    text_block = progress_blocks[0]["text"]
    assert "Ask the bank for balances" in text_block
    assert "allow ten working days" in text_block
    assert "Example house" in text_block
    assert "250000" in text_block
    assert "estimate" in text_block
    # question remains the FINAL block, after the progress context
    assert final_content[-1]["text"] == "Do I need probate before selling?"
