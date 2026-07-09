"""API tests for the estate router (settings, summary, accounts).

Runs against a live Postgres (created as ad_test_money if missing) with
the schema from SQLModel.metadata.create_all. Fixtures live in this file
by design: conftest.py is shared and never imports models. The app under
test is built here because main.py wires routers as they land.
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
from app.api import estate as estate_api
from app.api import iht as iht_api
from app.db import get_session
from app.models import (
    Asset,
    BeneficiaryLegacy,
    Contact,
    Cost,
    Distribution,
    Estate,
    Liability,
    Task,
)
from app.models.enums import IhtTreatment, LegacyType, OwnershipType

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_money"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"
VIEWER = "viewer@test.local"


def _prepare_database() -> None:
    """Create the test database if missing and ensure the schema exists.

    Runs in its own event loop (asyncio.run) so it is safe from sync
    fixtures; every connection is closed before the loop ends.
    """

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
    """A fresh engine per test (loop-bound), with all tables emptied."""
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
    """Factory for AsyncClients authenticated via the dev header."""

    def _make(user: str | None = EXECUTOR) -> AsyncClient:
        headers = {"X-Dev-User": user} if user else {}
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=headers
        )

    return _make


async def seed_estate(session_factory, **overrides) -> uuid.UUID:
    values: dict = {
        "name": "Test estate",
        "date_of_death": dt.date(2026, 1, 1),
        "tnrb_pct": Decimal("1.0"),
        "trnrb_pct": Decimal("1.0"),
        "residence_to_descendants_value": Decimal("400000"),
    }
    values.update(overrides)
    async with session_factory() as session:
        estate = Estate(**values)
        session.add(estate)
        await session.commit()
        return estate.id


class TestRbac:
    async def test_viewer_cannot_put_estate(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for(VIEWER) as client:
            response = await client.put("/estate", json={"name": "Renamed"})
        assert response.status_code == 403

    async def test_viewer_can_read_estate(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for(VIEWER) as client:
            assert (await client.get("/estate")).status_code == 200
            assert (await client.get("/estate/summary")).status_code == 200
            assert (await client.get("/estate/accounts")).status_code == 200

    async def test_anonymous_rejected(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for(None) as client:
            assert (await client.get("/estate")).status_code == 401


class TestEstateSettings:
    async def test_get_estate_returns_settings(self, client_for, session_factory):
        await seed_estate(
            session_factory,
            claims_rnrb=True,
            gifts_with_reservation=False,
            foreign_assets_value=Decimal("0"),
        )
        async with client_for() as client:
            response = await client.get("/estate")
        assert response.status_code == 200
        body = response.json()
        assert body["claims_rnrb"] is True
        assert body["gifts_with_reservation"] is False
        assert Decimal(body["foreign_assets_value"]) == Decimal("0")
        assert Decimal(body["tnrb_pct"]) == Decimal("1")
        # Unknown excepted-estate facts surface as null, never guessed.
        assert body["trust_property_value"] is None

    async def test_put_estate_updates_audits_and_reevaluates(
        self, client_for, session_factory
    ):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.put(
                "/estate",
                json={
                    "residence_to_descendants_value": "340000",
                    "claims_rnrb": True,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["residence_to_descendants_value"]) == Decimal("340000")
        assert body["claims_rnrb"] is True

        async with session_factory() as session:
            audits = (
                (
                    await session.execute(
                        text(
                            "SELECT actor, action, entity FROM audit_event "
                            "WHERE action = 'update'"
                        )
                    )
                ).all()
            )
            assert (EXECUTOR, "update", f"estate:{estate_id}") in [
                tuple(row) for row in audits
            ]
            # Re-evaluation ran: a snapshot was persisted for the estate.
            snapshots = (
                await session.execute(
                    text("SELECT COUNT(*) FROM iht_assessment")
                )
            ).scalar_one()
            assert snapshots == 1

    async def test_put_estate_rejects_unknown_fields(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.put("/estate", json={"nrb": "999999"})
        assert response.status_code == 422

    async def test_get_estate_404_when_absent(self, client_for):
        async with client_for() as client:
            assert (await client.get("/estate")).status_code == 404


class TestEstateSummary:
    async def test_summary_on_empty_database_is_all_zeros(self, client_for):
        async with client_for() as client:
            response = await client.get("/estate/summary")
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["gross_assets_at_dod"]) == 0
        assert Decimal(body["net_estate"]) == 0
        assert Decimal(body["iht_due"]) == 0
        assert body["open_task_count"] == 0
        assert body["unnotified_contact_count"] == 0
        assert Decimal(body["costs_total"]) == 0

    async def test_summary_aggregates(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with session_factory() as session:
            session.add_all(
                [
                    Asset(
                        estate_id=estate_id,
                        category="cash",
                        description="Current account",
                        dod_value=Decimal("100000"),
                        ownership=OwnershipType.sole,
                    ),
                    Asset(
                        estate_id=estate_id,
                        category="property",
                        description="Half share of a house",
                        dod_value=Decimal("50000"),
                        ownership=OwnershipType.tenants_in_common,
                        tic_share_pct=Decimal("0.5"),
                    ),
                    Asset(
                        estate_id=estate_id,
                        category="cash",
                        description="Joint account",
                        dod_value=Decimal("40000"),
                        ownership=OwnershipType.joint_tenants,
                    ),
                    Liability(
                        estate_id=estate_id, type="credit_card", amount=Decimal("10000")
                    ),
                    Liability(
                        estate_id=estate_id,
                        type="informal",
                        amount=Decimal("5000"),
                        iht_deductible=False,
                    ),
                    Cost(
                        estate_id=estate_id,
                        category="funeral",
                        amount=Decimal("4000"),
                        date=dt.date(2026, 1, 10),
                        iht_treatment=IhtTreatment.funeral_deductible,
                    ),
                    Cost(
                        estate_id=estate_id,
                        category="probate",
                        amount=Decimal("2000"),
                        date=dt.date(2026, 1, 12),
                        iht_treatment=IhtTreatment.admin_not_deductible,
                    ),
                    Task(estate_id=estate_id, title="Open task", status="open"),
                    Task(estate_id=estate_id, title="Done task", status="done"),
                    Contact(
                        estate_id=estate_id,
                        name="Generic Bank",
                        notify_required=True,
                    ),
                    Contact(
                        estate_id=estate_id,
                        name="Notified Insurer",
                        notify_required=True,
                        notified_date=dt.date(2026, 1, 15),
                    ),
                ]
            )
            await session.commit()

        async with client_for() as client:
            response = await client.get("/estate/summary")
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["gross_assets_at_dod"]) == Decimal("190000")
        # 100000 sole + 25000 TIC share - 10000 deductible - 4000 funeral
        assert Decimal(body["net_estate"]) == Decimal("111000")
        assert body["open_task_count"] == 1
        assert body["unnotified_contact_count"] == 1
        assert Decimal(body["costs_total"]) == Decimal("6000")
        assert Decimal(body["iht_due"]) == 0


class TestEstateAccounts:
    async def test_accounts_balance_on_seeded_scenario(
        self, client_for, session_factory
    ):
        estate_id = await seed_estate(session_factory)
        async with session_factory() as session:
            beneficiary_one = Contact(estate_id=estate_id, name="Beneficiary One")
            beneficiary_two = Contact(estate_id=estate_id, name="Beneficiary Two")
            beneficiary_three = Contact(estate_id=estate_id, name="Beneficiary Three")
            session.add_all([beneficiary_one, beneficiary_two, beneficiary_three])
            await session.flush()

            session.add_all(
                [
                    Asset(
                        estate_id=estate_id,
                        category="property",
                        description="Family home",
                        dod_value=Decimal("300000"),
                        ownership=OwnershipType.sole,
                    ),
                    Asset(
                        estate_id=estate_id,
                        category="cash",
                        description="Savings account",
                        dod_value=Decimal("200000"),
                        ownership=OwnershipType.sole,
                        income_since_death=Decimal("1000"),
                    ),
                    Asset(
                        estate_id=estate_id,
                        category="cash",
                        description="Joint account",
                        dod_value=Decimal("50000"),
                        ownership=OwnershipType.joint_tenants,
                    ),
                    Asset(
                        estate_id=estate_id,
                        category="property",
                        description="Half share of a flat",
                        dod_value=Decimal("100000"),
                        ownership=OwnershipType.tenants_in_common,
                        tic_share_pct=Decimal("0.5"),
                    ),
                    Liability(
                        estate_id=estate_id, type="credit_card", amount=Decimal("10000")
                    ),
                    Liability(
                        estate_id=estate_id,
                        type="informal",
                        amount=Decimal("5000"),
                        iht_deductible=False,
                    ),
                    Cost(
                        estate_id=estate_id,
                        category="funeral",
                        amount=Decimal("4000"),
                        date=dt.date(2026, 1, 10),
                        iht_treatment=IhtTreatment.funeral_deductible,
                    ),
                    Cost(
                        estate_id=estate_id,
                        category="probate",
                        amount=Decimal("2000"),
                        date=dt.date(2026, 1, 12),
                        iht_treatment=IhtTreatment.admin_not_deductible,
                    ),
                ]
            )
            pecuniary = BeneficiaryLegacy(
                estate_id=estate_id,
                beneficiary_contact_id=beneficiary_one.id,
                legacy_type=LegacyType.pecuniary,
                amount_or_share=Decimal("200000"),
                exempt_or_chargeable="chargeable",
            )
            residuary_two = BeneficiaryLegacy(
                estate_id=estate_id,
                beneficiary_contact_id=beneficiary_two.id,
                legacy_type=LegacyType.residuary,
                amount_or_share=Decimal("0.5"),
            )
            residuary_three = BeneficiaryLegacy(
                estate_id=estate_id,
                beneficiary_contact_id=beneficiary_three.id,
                legacy_type=LegacyType.residuary,
                amount_or_share=Decimal("0.5"),
            )
            session.add_all([pecuniary, residuary_two, residuary_three])
            await session.flush()
            session.add(
                Distribution(
                    estate_id=estate_id,
                    beneficiary_legacy_id=residuary_two.id,
                    amount=Decimal("10000"),
                    date=dt.date(2026, 3, 1),
                )
            )
            await session.commit()
            beneficiary_two_id = str(beneficiary_two.id)

        async with client_for() as client:
            response = await client.get("/estate/accounts")
        assert response.status_code == 200
        body = response.json()

        # Estate share 550000 (300000 + 200000 + 50000 TIC share, joint
        # account passes by survivorship) - 10000 deductible - 4000 funeral.
        assert Decimal(body["net_estate"]) == Decimal("536000")
        assert Decimal(body["income_account"]) == Decimal("1000")
        assert Decimal(body["administration_account"]) == Decimal("2000")
        assert Decimal(body["legacies_total"]) == Decimal("200000")
        # 536000 + 1000 - 2000 - 200000
        assert Decimal(body["residue"]) == Decimal("335000")
        assert body["is_balanced"] is True

        shares = {d["beneficiary_id"]: d for d in body["distributions"]}
        assert len(shares) == 2
        for entry in shares.values():
            assert Decimal(entry["entitlement"]) == Decimal("167500")
        assert Decimal(shares[beneficiary_two_id]["interim_received"]) == Decimal(
            "10000"
        )
        assert Decimal(shares[beneficiary_two_id]["remaining_due"]) == Decimal(
            "157500"
        )
