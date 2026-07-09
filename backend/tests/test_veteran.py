"""Tests for the veteran checklist service and router (Module 18).

The checklist template is generic, synthetic armed-forces content with
no personal data. Seeding is idempotent by title plus source "veteran".
Runs against a live Postgres (ad_test_trackers on localhost:5474).
Fixtures live in this file by design.
"""

import asyncio
import datetime as dt
import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.models as models
from app.db import get_session
from app.models import Estate, Task
from app.services import veteran as veteran_service
from app.services.veteran import load_veteran_checklist

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_trackers"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"


def _prepare_database() -> None:
    """Create the test database if missing and ensure the schema exists."""

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
        engine = create_async_engine(TEST_DB_URL)
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
    engine = create_async_engine(TEST_DB_URL)
    tables = ", ".join(f'"{table.name}"' for table in SQLModel.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def app(session_factory) -> FastAPI:
    application = FastAPI()
    application.include_router(veteran_service.router)

    async def _override_session():
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_session
    return application


@pytest.fixture
def client_for(app):
    def _make(user: str | None = EXECUTOR) -> AsyncClient:
        headers = {"X-Dev-User": user} if user else {}
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=headers
        )

    return _make


async def seed_estate(session_factory) -> uuid.UUID:
    async with session_factory() as session:
        estate = Estate(name="Test estate", date_of_death=dt.date(2026, 1, 15))
        session.add(estate)
        await session.commit()
        return estate.id


class TestChecklistTemplate:
    def test_template_loads_with_expected_shape(self):
        items = load_veteran_checklist()
        assert 12 <= len(items) <= 20
        orders = [item.order for item in items]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)  # orders unique
        titles = [item.title for item in items]
        assert len(set(titles)) == len(titles)  # titles unique (idempotency key)
        for item in items:
            assert item.title.strip()
            assert item.description.strip()
            if item.url is not None:
                assert item.url.startswith("https://")

    def test_template_covers_the_core_module_18_routes(self):
        text_blob = " ".join(
            f"{item.title} {item.description}" for item in load_veteran_checklist()
        ).lower()
        for expected in (
            "veterans uk",
            "pension",
            "raf benevolent fund",
            "ssafa",
            "royal british legion",
            "medal",
            "service records",
        ):
            assert expected in text_blob, f"checklist is missing {expected!r}"


class TestSeedTasks:
    async def test_seed_creates_all_tasks_then_is_idempotent(
        self, client_for, session_factory
    ):
        estate_id = await seed_estate(session_factory)
        item_count = len(load_veteran_checklist())
        async with client_for() as client:
            first = (await client.post("/veteran/seed-tasks")).json()
            second = (await client.post("/veteran/seed-tasks")).json()
        assert len(first["created"]) == item_count
        assert first["skipped"] == []
        assert second["created"] == []
        assert len(second["skipped"]) == item_count

        async with session_factory() as session:
            rows = (
                await session.execute(select(Task).where(Task.source == "veteran"))
            ).scalars().all()
            assert len(rows) == item_count
            assert all(row.estate_id == estate_id for row in rows)
            assert all(row.status == "todo" for row in rows)

    async def test_seed_emits_audit_events(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for() as client:
            created = (await client.post("/veteran/seed-tasks")).json()["created"]
        async with session_factory() as session:
            count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM audit_event "
                        "WHERE action = 'create' AND entity LIKE 'task:%'"
                    )
                )
            ).scalar_one()
        assert int(count) == len(created)

    async def test_seed_404_without_estate(self, client_for, db_engine):
        async with client_for() as client:
            assert (await client.post("/veteran/seed-tasks")).status_code == 404


class TestChecklistEndpoint:
    async def test_checklist_reports_task_status_after_seed(
        self, client_for, session_factory
    ):
        await seed_estate(session_factory)
        async with client_for() as client:
            before = (await client.get("/veteran/checklist")).json()
            assert all(entry["task_id"] is None for entry in before)
            assert all(entry["task_status"] is None for entry in before)

            await client.post("/veteran/seed-tasks")
            after = (await client.get("/veteran/checklist")).json()
        assert len(after) == len(load_veteran_checklist())
        assert all(entry["task_id"] is not None for entry in after)
        assert all(entry["task_status"] == "todo" for entry in after)
        assert [entry["order"] for entry in after] == sorted(
            entry["order"] for entry in after
        )

    async def test_viewer_can_read_but_not_seed(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for(VIEWER) as client:
            assert (await client.get("/veteran/checklist")).status_code == 200
            assert (await client.post("/veteran/seed-tasks")).status_code == 403
