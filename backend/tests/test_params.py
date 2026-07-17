"""Params page: embeddings off by default, admin toggle, gated pipeline."""

import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.api import params as params_api
from app.db import get_session
from app.models import Estate

ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB = "ad_test_params"
TEST_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB}"

ADMIN = "admin@test.local"
EXECUTOR = "exec@test.local"


@pytest.fixture(scope="module", autouse=True)
def _database():
    import asyncio

    async def prepare():
        conn = await asyncpg.connect(ADMIN_DSN)
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", TEST_DB):
            await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        await conn.close()
        engine = create_async_engine(TEST_URL, poolclass=NullPool)
        async with engine.begin() as c:
            await c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await c.run_sync(SQLModel.metadata.create_all)
        await engine.dispose()

    asyncio.run(prepare())


@pytest.fixture()
def client_for(monkeypatch):
    import asyncio

    monkeypatch.setenv("DEV_AUTH", "true")
    monkeypatch.setenv("USER_ROLES", f"{ADMIN}:admin,{EXECUTOR}:executor")
    from app.core.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed():
        async with factory() as session:
            session.add(Estate(id=uuid.uuid4(), name="Params Estate", created_by="seed"))
            await session.commit()

    asyncio.run(seed())

    app = FastAPI()
    app.include_router(params_api.router)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override

    def make(email: str) -> TestClient:
        client = TestClient(app)
        client.headers["X-Dev-User"] = email
        return client

    yield make
    get_settings.cache_clear()

    async def cleanup():
        async with factory() as session:
            for table in ("audit_event", "app_setting", "estate"):
                await session.execute(text(f'DELETE FROM "{table}"'))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def test_embeddings_default_off(client_for):
    body = client_for(EXECUTOR).get("/settings/params").json()
    assert body["embeddings_enabled"] is False
    assert body["embeddings_status"] == "idle"


def test_only_admin_can_toggle(client_for):
    assert (
        client_for(EXECUTOR)
        .post("/settings/params", json={"embeddings_enabled": True})
        .status_code
        == 403
    )


def test_admin_toggle_starts_backfill(client_for, monkeypatch):
    ran = {"n": 0}

    async def fake_job():
        ran["n"] += 1

    monkeypatch.setattr(params_api, "_backfill_job", fake_job)
    body = (
        client_for(ADMIN)
        .post("/settings/params", json={"embeddings_enabled": True})
        .json()
    )
    assert body["embeddings_enabled"] is True
    assert body["embeddings_status"] == "running"
    assert ran["n"] == 1
    # switching off returns status to idle and does not rerun the job
    body = (
        client_for(ADMIN)
        .post("/settings/params", json={"embeddings_enabled": False})
        .json()
    )
    assert body["embeddings_enabled"] is False
    assert body["embeddings_status"] == "idle"
    assert ran["n"] == 1
