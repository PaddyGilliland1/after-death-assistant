"""Tests for the section 20 re-evaluation service.

Exercises the service directly against a live Postgres: baseline
recompute, a material change (crossing the tax-free allowance) that must
notify the other executor/admin users, and an immaterial 5000 change that
must not. All figures asserted come from the deterministic engine.
Fixtures live in this file by design.
"""

import asyncio
import datetime as dt
import uuid
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.models as models
from app.models import Asset, Estate, IhtAssessment, Notification
from app.models.enums import OwnershipType
from app.services.reevaluation import (
    MATERIAL_SINGLE_CHANGE_GBP,
    REEVALUATION_EVENT_TYPE,
    reevaluate,
)

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_money"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"


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


async def seed(
    session_factory, asset_value: Decimal
) -> tuple[uuid.UUID, uuid.UUID]:
    """An estate whose allowance is 1000000 (tnrb 1.0, trnrb 1.0,
    residence 400000) holding a single sole asset of the given value."""
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
        asset = Asset(
            estate_id=estate.id,
            category="property",
            description="Family home",
            dod_value=asset_value,
            ownership=OwnershipType.sole,
        )
        session.add(asset)
        await session.commit()
        return estate.id, asset.id


async def baseline(session_factory, estate_id: uuid.UUID) -> None:
    """First recompute: snapshots, but has nothing to compare against."""
    async with session_factory() as session:
        outcome = await reevaluate(session, estate_id, EXECUTOR)
        await session.commit()
    assert outcome.reasons == []
    assert outcome.notified == []


async def set_asset_value(session_factory, asset_id: uuid.UUID, value: Decimal) -> None:
    async with session_factory() as session:
        asset = await session.get(Asset, asset_id)
        asset.dod_value = value
        await session.commit()


async def notifications(session_factory, estate_id: uuid.UUID) -> list[Notification]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Notification).where(Notification.estate_id == estate_id)
            )
        ).scalars().all()
        return list(rows)


class TestMaterialChange:
    async def test_alert_fires_when_change_crosses_the_allowance(
        self, session_factory
    ):
        # Net 990000 against an allowance of 1000000: tax nil.
        estate_id, asset_id = await seed(session_factory, Decimal("990000"))
        await baseline(session_factory, estate_id)

        # The asset value is confirmed at 1020000: tax becomes 8000
        # (contract section 7 row), crossing the allowance.
        await set_asset_value(session_factory, asset_id, Decimal("1020000"))
        async with session_factory() as session:
            outcome = await reevaluate(
                session,
                estate_id,
                EXECUTOR,
                change_context={
                    "entity": f"asset:{asset_id}",
                    "summary": "asset value confirmed at 1,020,000",
                },
            )
            await session.commit()

        assert any("allowance" in reason for reason in outcome.reasons)
        assert outcome.notified == [ADMIN]

        rows = await notifications(session_factory, estate_id)
        assert len(rows) == 1
        note = rows[0]
        assert note.user_id == ADMIN
        assert note.event_type == REEVALUATION_EVENT_TYPE
        assert note.entity_ref == f"iht_assessment:{outcome.assessment_row.id}"
        # Figures in the message come FROM THE ENGINE: the new tax and
        # allowance appear exactly as the engine computed them.
        assert "£8,000.00" in note.message
        assert "£1,000,000.00" in note.message
        assert "asset value confirmed" in note.message

    async def test_alert_never_goes_to_the_actor(self, session_factory):
        estate_id, asset_id = await seed(session_factory, Decimal("990000"))
        await baseline(session_factory, estate_id)
        await set_asset_value(session_factory, asset_id, Decimal("1020000"))
        async with session_factory() as session:
            outcome = await reevaluate(session, estate_id, ADMIN)
            await session.commit()

        assert ADMIN not in outcome.notified
        assert outcome.notified == [EXECUTOR]
        rows = await notifications(session_factory, estate_id)
        assert {row.user_id for row in rows} == {EXECUTOR}

    async def test_taper_threshold_crossing_fires(self, session_factory):
        estate_id, asset_id = await seed(session_factory, Decimal("1990000"))
        await baseline(session_factory, estate_id)
        await set_asset_value(session_factory, asset_id, Decimal("2010000"))
        async with session_factory() as session:
            outcome = await reevaluate(session, estate_id, EXECUTOR)
            await session.commit()
        assert any("taper threshold" in reason for reason in outcome.reasons)


class TestImmaterialChange:
    async def test_no_alert_for_a_5000_change(self, session_factory):
        assert MATERIAL_SINGLE_CHANGE_GBP == Decimal("10000")

        # Net 500000: far inside the allowance, no threshold near.
        estate_id, asset_id = await seed(session_factory, Decimal("500000"))
        await baseline(session_factory, estate_id)

        await set_asset_value(session_factory, asset_id, Decimal("505000"))
        async with session_factory() as session:
            outcome = await reevaluate(session, estate_id, EXECUTOR)
            await session.commit()

        assert outcome.reasons == []
        assert outcome.notified == []
        assert await notifications(session_factory, estate_id) == []

        # The recompute is still snapshotted (spec section 20 point 4).
        async with session_factory() as session:
            count = (
                await session.execute(
                    select(IhtAssessment).where(
                        IhtAssessment.estate_id == estate_id
                    )
                )
            ).scalars().all()
            assert len(count) == 2

    async def test_first_recompute_never_alerts(self, session_factory):
        estate_id, _ = await seed(session_factory, Decimal("1020000"))
        async with session_factory() as session:
            outcome = await reevaluate(session, estate_id, EXECUTOR)
            await session.commit()
        assert outcome.reasons == []
        assert await notifications(session_factory, estate_id) == []
