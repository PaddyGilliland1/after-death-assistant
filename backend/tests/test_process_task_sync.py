"""Task <-> process step synchronisation (both directions)."""

import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.api import process as process_router
from app.api import tasks as tasks_router
from app.db import get_session
from app.models import Estate, ProcessStep, Task

ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB = "ad_test_sync"
TEST_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB}"


@pytest.fixture(scope="module", autouse=True)
def _database():
    import asyncio

    async def prepare():
        conn = await asyncpg.connect(ADMIN_DSN)
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", TEST_DB)
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
def client_and_ids(monkeypatch):
    import asyncio

    monkeypatch.setenv("DEV_AUTH", "true")
    monkeypatch.setenv("USER_ROLES", "exec@test.local:executor")
    from app.core.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    estate_id = uuid.uuid4()
    step_id = uuid.uuid4()
    task_id = uuid.uuid4()

    async def seed():
        async with factory() as session:
            session.add(Estate(id=estate_id, name="Sync Test Estate", created_by="seed"))
            session.add(
                ProcessStep(
                    id=step_id, estate_id=estate_id, order=1,
                    name="Step one", status="not_started", created_by="seed",
                )
            )
            session.add(
                Task(
                    id=task_id, estate_id=estate_id, title="Task for step one",
                    status="todo", process_step_id=step_id, created_by="seed",
                )
            )
            await session.commit()

    asyncio.run(seed())

    app = FastAPI()
    app.include_router(tasks_router.router)
    app.include_router(process_router.router)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    client.headers["X-Dev-User"] = "exec@test.local"
    yield client, estate_id, step_id, task_id
    get_settings.cache_clear()

    async def cleanup():
        async with factory() as session:
            for table in ("audit_event", "task", "process_step", "estate"):
                await session.execute(text(f'DELETE FROM "{table}"'))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def _timeline_status(client, step_id):
    rows = client.get("/process/timeline").json()
    return next(r["stored_status"] for r in rows if r["step_id"] == str(step_id))


def test_completing_the_task_completes_the_step(client_and_ids):
    client, _, step_id, task_id = client_and_ids
    response = client.patch(f"/tasks/{task_id}", json={"status": "done"})
    assert response.status_code == 200
    assert _timeline_status(client, step_id) == "done"


def test_reopening_the_task_reopens_the_step(client_and_ids):
    client, _, step_id, task_id = client_and_ids
    client.patch(f"/tasks/{task_id}", json={"status": "done"})
    client.patch(f"/tasks/{task_id}", json={"status": "in_progress"})
    assert _timeline_status(client, step_id) == "in_progress"


def test_step_change_updates_the_task(client_and_ids):
    client, _, step_id, task_id = client_and_ids
    response = client.patch(f"/process/steps/{step_id}", json={"status": "done"})
    assert response.status_code == 200
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "done"


def test_step_reopen_maps_not_started_to_todo(client_and_ids):
    client, _, step_id, task_id = client_and_ids
    client.patch(f"/process/steps/{step_id}", json={"status": "done"})
    client.patch(f"/process/steps/{step_id}", json={"status": "not_started"})
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "todo"


def test_unlinked_task_touches_no_step(client_and_ids):
    client, estate_id, step_id, _ = client_and_ids
    created = client.post(
        "/tasks",
        json={"estate_id": str(estate_id), "title": "Free task", "status": "todo"},
    ).json()
    client.patch(f"/tasks/{created['id']}", json={"status": "done"})
    assert _timeline_status(client, step_id) == "not_started"
