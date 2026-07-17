"""API tests for the asset tracing and completeness router (Module 16).

Read-only module: GET /tracing/completeness is computed entirely from
existing stored data. Runs against a live Postgres (ad_test_trackers on
localhost:5474). Fixtures live in this file by design.
"""

import asyncio
import datetime as dt
import uuid
from decimal import Decimal

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.models as models
from app.api import tracing as tracing_api
from app.db import get_session
from app.models import Asset, Contact, Debtor, Estate
from app.models.enums import ValueBasis

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
    application.include_router(tracing_api.router)

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


async def seed_completeness_data(session_factory) -> dict[str, uuid.UUID]:
    """An estate with one gap of every kind plus complete counterparts."""
    async with session_factory() as session:
        estate = Estate(name="Test estate", date_of_death=dt.date(2026, 1, 15))
        session.add(estate)
        await session.flush()

        estimated = Asset(
            estate_id=estate.id,
            category="cash",
            description="Current account, balance still estimated",
            dod_value=Decimal("1200"),
            value_basis=ValueBasis.estimate,
        )
        confirmed = Asset(
            estate_id=estate.id,
            category="property",
            description="Family home, valuation confirmed",
            dod_value=Decimal("340000"),
            value_basis=ValueBasis.confirmed,
        )
        club_share = Asset(
            estate_id=estate.id,
            category="shares",
            sub_type="gliding club share",
            description="Gliding club syndicate share, no confirmed valuation",
            value_basis=ValueBasis.estimate,
            iht_schedule="IHT412",
        )
        session.add_all([estimated, confirmed, club_share])

        unnotified = Contact(
            estate_id=estate.id,
            name="High street bank",
            notify_required=True,
        )
        notified = Contact(
            estate_id=estate.id,
            name="Utility company",
            notify_required=True,
            notified_date=dt.date(2026, 2, 1),
        )
        no_notice_needed = Contact(estate_id=estate.id, name="Neighbour")
        session.add_all([unnotified, notified, no_notice_needed])

        outstanding = Debtor(
            estate_id=estate.id,
            type="tax_repayment",
            amount_expected=Decimal("100"),
            amount_received=Decimal("40"),
        )
        settled = Debtor(
            estate_id=estate.id,
            type="refund",
            amount_expected=Decimal("50"),
            amount_received=Decimal("50"),
        )
        session.add_all([outstanding, settled])
        await session.commit()
        return {
            "estate": estate.id,
            "estimated": estimated.id,
            "club_share": club_share.id,
            "outstanding": outstanding.id,
        }


class TestCompleteness:
    async def test_picks_up_estimate_assets_and_unnotified_contact(
        self, client_for, session_factory
    ):
        ids = await seed_completeness_data(session_factory)
        async with client_for() as client:
            response = await client.get("/tracing/completeness")
        assert response.status_code == 200
        body = response.json()

        estimated_ids = {item["id"] for item in body["estimated_value_assets"]}
        assert estimated_ids == {str(ids["estimated"]), str(ids["club_share"])}
        assert body["unnotified_contacts_count"] == 1

    async def test_outstanding_debtors_listed_with_outstanding_amount(
        self, client_for, session_factory
    ):
        ids = await seed_completeness_data(session_factory)
        async with client_for() as client:
            body = (await client.get("/tracing/completeness")).json()
        debtors = body["outstanding_debtors"]
        assert [item["id"] for item in debtors] == [str(ids["outstanding"])]
        assert Decimal(str(debtors[0]["outstanding"])) == Decimal("60")

    async def test_unlisted_holdings_without_confirmed_valuation(
        self, client_for, session_factory
    ):
        ids = await seed_completeness_data(session_factory)
        async with client_for() as client:
            body = (await client.get("/tracing/completeness")).json()
        unlisted = body["unconfirmed_unlisted_holdings"]
        assert [item["id"] for item in unlisted] == [str(ids["club_share"])]
        assert "gliding" in unlisted[0]["description"].lower()

    async def test_static_search_suggestions_and_warning(self, client_for, session_factory):
        await seed_completeness_data(session_factory)
        async with client_for() as client:
            body = (await client.get("/tracing/completeness")).json()
        suggestions = body["search_suggestions"]
        assert len(suggestions) == 4
        names = {item["name"] for item in suggestions}
        assert names == {
            "My Lost Account",
            "NS&I tracing service",
            "Pension Tracing Service (DWP)",
            "Gretel unclaimed assets search",
        }
        for item in suggestions:
            assert item["url"].startswith("https://")
            assert item["covers"]
        assert "free" in body["warning"]
        assert "reclaim firm" in body["warning"]

    async def test_viewer_can_read_completeness(self, client_for, session_factory):
        await seed_completeness_data(session_factory)
        async with client_for(VIEWER) as client:
            assert (await client.get("/tracing/completeness")).status_code == 200

    async def test_404_without_estate(self, client_for, db_engine):
        async with client_for() as client:
            assert (await client.get("/tracing/completeness")).status_code == 404
