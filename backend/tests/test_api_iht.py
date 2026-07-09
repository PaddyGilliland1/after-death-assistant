"""API tests for the IHT workbench router (recompute, assessment, schedules).

Runs against a live Postgres (created as ad_test_money if missing). The
hand-checked expectation is the build contract section 7 table row:
net 1020000, tnrb 1.0, trnrb 1.0, residence 400000 gives allowance
1000000 and tax 8000. Fixtures live in this file by design.
"""

import asyncio
import datetime as dt
import uuid
from decimal import Decimal

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.models as models
from app.api import estate as estate_api
from app.api import iht as iht_api
from app.db import get_session
from app.models import Asset, Estate, IhtAssessment
from app.models.enums import OwnershipType

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_money"
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
    application.include_router(estate_api.router)
    application.include_router(iht_api.router)

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


async def seed_contract_row_estate(session_factory) -> uuid.UUID:
    """The contract section 7 hand-checked case: a single sole asset of
    1020000 with tnrb 1.0, trnrb 1.0 and residence to descendants 400000."""
    async with session_factory() as session:
        estate = Estate(
            name="Test estate",
            date_of_death=dt.date(2026, 1, 1),
            tnrb_pct=Decimal("1.0"),
            trnrb_pct=Decimal("1.0"),
            residence_to_descendants_value=Decimal("400000"),
        )
        session.add(estate)
        await session.flush()
        session.add(
            Asset(
                estate_id=estate.id,
                category="property",
                description="Family home",
                dod_value=Decimal("1020000"),
                ownership=OwnershipType.sole,
            )
        )
        await session.commit()
        return estate.id


class TestRbac:
    async def test_viewer_cannot_recompute(self, client_for, session_factory):
        await seed_contract_row_estate(session_factory)
        async with client_for(VIEWER) as client:
            response = await client.post("/iht/recompute")
        assert response.status_code == 403

    async def test_viewer_can_read_assessment_and_schedules(
        self, client_for, session_factory
    ):
        await seed_contract_row_estate(session_factory)
        async with client_for(EXECUTOR) as client:
            assert (await client.post("/iht/recompute")).status_code == 200
        async with client_for(VIEWER) as client:
            assert (await client.get("/iht/assessment")).status_code == 200
            assert (await client.get("/iht/schedules")).status_code == 200


class TestRecompute:
    async def test_recompute_matches_hand_checked_contract_row(
        self, client_for, session_factory
    ):
        await seed_contract_row_estate(session_factory)
        async with client_for() as client:
            response = await client.post("/iht/recompute")
        assert response.status_code == 200
        body = response.json()

        # Contract section 7 table: net 1020000, tnrb 1.0, trnrb 1.0,
        # residence 400000 -> allowance 1000000, tax 8000.
        assert Decimal(body["nrb"]) == Decimal("650000")
        assert Decimal(body["rnrb"]) == Decimal("350000")
        assert Decimal(body["allowance"]) == Decimal("1000000")
        assert Decimal(body["taxable"]) == Decimal("20000")
        assert Decimal(body["tax"]) == Decimal("8000")
        assert Decimal(body["rate"]) == Decimal("0.40")
        # RNRB claimed (derived from the residence value), so a full
        # account is required regardless of excepted status.
        assert body["must_file_iht400"] is True
        assert Decimal(body["inputs"]["net_value"]) == Decimal("1020000")

    async def test_recompute_persists_snapshot_and_audit(
        self, client_for, session_factory
    ):
        estate_id = await seed_contract_row_estate(session_factory)
        async with client_for() as client:
            response = await client.post("/iht/recompute")
        assert response.status_code == 200
        assessment_id = response.json()["id"]

        async with session_factory() as session:
            row = (
                await session.execute(
                    select(IhtAssessment).where(
                        IhtAssessment.estate_id == estate_id
                    )
                )
            ).scalars().one()
            assert str(row.id) == assessment_id
            assert row.constants_version.startswith("england_wales:")
            assert Decimal(row.snapshot["result"]["tax"]) == Decimal("8000.00")
            assert Decimal(row.snapshot["inputs"]["net_value"]) == Decimal("1020000")

            audit = (
                await session.execute(
                    text(
                        "SELECT actor, action, entity FROM audit_event "
                        "WHERE action = 'recompute'"
                    )
                )
            ).all()
            assert (EXECUTOR, "recompute", f"iht_assessment:{assessment_id}") in [
                tuple(entry) for entry in audit
            ]

    async def test_recompute_404_without_estate(self, client_for):
        async with client_for() as client:
            assert (await client.post("/iht/recompute")).status_code == 404


class TestAssessmentAndSchedules:
    async def test_assessment_returns_latest_snapshot(
        self, client_for, session_factory
    ):
        await seed_contract_row_estate(session_factory)
        async with client_for() as client:
            first = (await client.post("/iht/recompute")).json()
            second = (await client.post("/iht/recompute")).json()
            latest = (await client.get("/iht/assessment")).json()
        assert latest["id"] == second["id"]
        assert latest["id"] != first["id"]

    async def test_assessment_404_when_none(self, client_for, session_factory):
        await seed_contract_row_estate(session_factory)
        async with client_for() as client:
            assert (await client.get("/iht/assessment")).status_code == 404

    async def test_schedules_with_reasons(self, client_for, session_factory):
        await seed_contract_row_estate(session_factory)
        async with client_for() as client:
            assert (await client.post("/iht/recompute")).status_code == 200
            response = await client.get("/iht/schedules")
        assert response.status_code == 200
        body = response.json()
        assert body["must_file_iht400"] is True

        by_code = {item["code"]: item["reason"] for item in body["schedules"]}
        # Property -> IHT405; tnrb -> IHT402; RNRB claim -> IHT435; and a
        # transferred RNRB -> IHT436 (all derived by the engine).
        assert set(by_code) == {"IHT402", "IHT405", "IHT435", "IHT436"}
        for reason in by_code.values():
            assert reason  # every schedule carries a plain-English reason
        assert "land or buildings" in by_code["IHT405"]
