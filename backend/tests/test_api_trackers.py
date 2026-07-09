"""API tests for the P2 tracker routers: reliefs (Module 14), admin tax
(Module 15), digital items (Module 17) and IHT schedule task seeding.

Runs against a live Postgres (database ad_test_trackers on localhost:5474,
created if missing, vector extension + create_all). Fixtures live in this
file by design (conftest.py stays minimal).
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
from app.api import admin_tax as admin_tax_api
from app.api import digital as digital_api
from app.api import iht_schedule_tasks as schedule_tasks_api
from app.api import reliefs as reliefs_api
from app.db import get_session
from app.models import AdminTax, DigitalItem, Estate, IhtAssessment, Task

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_trackers"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"

DATE_OF_DEATH = dt.date(2026, 1, 15)


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
    application.include_router(reliefs_api.router)
    application.include_router(admin_tax_api.router)
    application.include_router(digital_api.router)
    application.include_router(schedule_tasks_api.router)

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


async def seed_estate(session_factory, date_of_death: dt.date | None = DATE_OF_DEATH) -> uuid.UUID:
    async with session_factory() as session:
        estate = Estate(name="Test estate", date_of_death=date_of_death)
        session.add(estate)
        await session.commit()
        return estate.id


async def seed_assessment(
    session_factory,
    estate_id: uuid.UUID,
    net_value: str = "1000000",
    required_schedules: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        row = IhtAssessment(
            estate_id=estate_id,
            snapshot={
                "inputs": {"net_value": net_value},
                "result": {
                    "required_schedules": required_schedules or [],
                    "must_file_iht400": True,
                },
            },
            constants_version="test",
        )
        session.add(row)
        await session.commit()
        return row.id


# ---------------------------------------------------------------------------
# Module 14: reliefs
# ---------------------------------------------------------------------------


class TestReliefs:
    async def test_crud_and_window_derivation_iht35(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.post(
                "/reliefs",
                json={
                    "estate_id": str(estate_id),
                    "relief_type": "iht35",
                    "probate_value": "10000",
                    "sale_value": "6000",
                    "sale_date": "2026-06-01",
                },
            )
            assert response.status_code == 201
            body = response.json()
            # 12 months from the date of death (IHT35 sale window).
            assert body["window_deadline"] == "2027-01-15"
            assert "IHTA 1984" in body["window_basis"]
            # Difference of stored figures only, with the estate-rate note.
            assert Decimal(str(body["potential_reclaim"])) == Decimal("4000")
            assert "estate rate" in body["reclaim_note"]

            fetched = await client.get(f"/reliefs/{body['id']}")
            assert fetched.status_code == 200
            assert fetched.json()["window_deadline"] == "2027-01-15"

            listed = await client.get("/reliefs", params={"estate_id": str(estate_id)})
            assert [item["id"] for item in listed.json()] == [body["id"]]

    async def test_window_derivation_iht38_four_years(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.post(
                "/reliefs",
                json={
                    "estate_id": str(estate_id),
                    "relief_type": "iht38",
                    "sale_date": "2027-03-01",
                },
            )
        body = response.json()
        assert body["window_deadline"] == "2030-01-15"
        assert "IHT38" in body["window_basis"]

    async def test_update_rederives_window_on_type_change(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            created = (
                await client.post(
                    "/reliefs",
                    json={"estate_id": str(estate_id), "relief_type": "iht35"},
                )
            ).json()
            assert created["window_deadline"] == "2027-01-15"
            patched = await client.patch(
                f"/reliefs/{created['id']}", json={"relief_type": "iht38"}
            )
        assert patched.status_code == 200
        assert patched.json()["window_deadline"] == "2030-01-15"

    async def test_explicit_window_deadline_is_stored_input(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.post(
                "/reliefs",
                json={
                    "estate_id": str(estate_id),
                    "relief_type": "iht35",
                    "window_deadline": "2026-12-25",
                },
            )
        body = response.json()
        assert body["window_deadline"] == "2026-12-25"
        assert body["window_basis"] is None  # manually set, not the derived window

    async def test_potential_reclaim_floors_at_zero(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.post(
                "/reliefs",
                json={
                    "estate_id": str(estate_id),
                    "relief_type": "iht38",
                    "probate_value": "5000",
                    "sale_value": "8000",
                },
            )
        assert Decimal(str(response.json()["potential_reclaim"])) == Decimal("0")

    async def test_potential_reclaim_stored_input_wins(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.post(
                "/reliefs",
                json={
                    "estate_id": str(estate_id),
                    "relief_type": "iht35",
                    "probate_value": "10000",
                    "sale_value": "6000",
                    "potential_reclaim": "1234",
                },
            )
        assert Decimal(str(response.json()["potential_reclaim"])) == Decimal("1234")

    async def test_soft_delete_with_body_reason_and_audit(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            created = (
                await client.post(
                    "/reliefs",
                    json={"estate_id": str(estate_id), "relief_type": "rnrb_downsizing"},
                )
            ).json()
            deleted = await client.request(
                "DELETE",
                f"/reliefs/{created['id']}",
                json={"reason": "duplicate entry"},
            )
            assert deleted.status_code == 200
            assert deleted.json()["archived_at"] is not None
            assert deleted.json()["archive_reason"] == "duplicate entry"

            again = await client.request(
                "DELETE", f"/reliefs/{created['id']}", json={"reason": "again"}
            )
            assert again.status_code == 409

            # Archived rows leave the default list.
            listed = (await client.get("/reliefs")).json()
            assert listed == []

        async with session_factory() as session:
            actions = (
                await session.execute(
                    text(
                        "SELECT action FROM audit_event WHERE entity = :entity ORDER BY created_at"
                    ),
                    {"entity": f"relief:{created['id']}"},
                )
            ).scalars().all()
            assert actions == ["create", "archive"]

    async def test_watchlist_orders_and_filters_to_90_days(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        today = dt.date.today()
        soon = (today + dt.timedelta(days=5)).isoformat()
        later = (today + dt.timedelta(days=30)).isoformat()
        far = (today + dt.timedelta(days=200)).isoformat()
        async with client_for() as client:
            for deadline in (later, soon, far):
                response = await client.post(
                    "/reliefs",
                    json={
                        "estate_id": str(estate_id),
                        "relief_type": "bpr_apr",
                        "window_deadline": deadline,
                    },
                )
                assert response.status_code == 201
            watchlist = (await client.get("/reliefs/watchlist")).json()
        assert [item["window_deadline"] for item in watchlist] == [soon, later]
        assert [item["days_remaining"] for item in watchlist] == [5, 30]


# ---------------------------------------------------------------------------
# Module 15: admin tax
# ---------------------------------------------------------------------------


class TestAdminTax:
    async def test_cgt_60day_and_isa_derivations(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(session_factory, estate_id)
        async with client_for() as client:
            response = await client.post(
                "/admin-tax",
                json={
                    "estate_id": str(estate_id),
                    "tax_year": "2026-27",
                    "income_total": "400",
                    "cgt_disposals": [
                        {
                            "description": "Flat sale",
                            "disposal_date": "2026-08-01",
                            "proceeds": "250000",
                            "gain": "1000",
                        },
                        {"description": "No date yet", "gain": "500"},
                    ],
                },
            )
        assert response.status_code == 201
        body = response.json()
        # 60 days from completion (FA 2019 Sch.2): 2026-08-01 -> 2026-09-30.
        assert len(body["cgt_60day_deadlines"]) == 1
        entry = body["cgt_60day_deadlines"][0]
        assert entry["disposal_date"] == "2026-08-01"
        assert entry["deadline"] == "2026-09-30"
        assert "60 days" in entry["basis"]
        # Third anniversary of death (ISA regulations).
        assert body["isa_exemption_end"] == "2029-01-15"

    async def test_estate_complex_false_under_all_thresholds(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(session_factory, estate_id, net_value="1000000")
        async with client_for() as client:
            response = await client.post(
                "/admin-tax",
                json={
                    "estate_id": str(estate_id),
                    "tax_year": "2026-27",
                    "income_total": "400",
                    "cgt_disposals": [
                        {"description": "Shares", "disposal_date": "2026-09-01", "gain": "1000"},
                        {"description": "Car", "disposal_date": "2026-10-01", "gain": "1500"},
                    ],
                },
            )
        body = response.json()
        assert body["estate_complex"] is False
        assert body["complex_reasons"] == []

    async def test_estate_complex_true_on_income_over_500(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(session_factory, estate_id, net_value="1000000")
        async with client_for() as client:
            response = await client.post(
                "/admin-tax",
                json={
                    "estate_id": str(estate_id),
                    "tax_year": "2026-27",
                    "income_total": "600",
                },
            )
        body = response.json()
        assert body["estate_complex"] is True
        assert any("500" in reason for reason in body["complex_reasons"])

    async def test_estate_complex_true_on_gains_over_3000(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(session_factory, estate_id, net_value="1000000")
        async with client_for() as client:
            response = await client.post(
                "/admin-tax",
                json={
                    "estate_id": str(estate_id),
                    "tax_year": "2026-27",
                    "income_total": "100",
                    "cgt_disposals": [
                        {"description": "A", "disposal_date": "2026-09-01", "gain": "2000"},
                        {"description": "B", "disposal_date": "2026-10-01", "gain": "1500"},
                    ],
                },
            )
        body = response.json()
        assert body["estate_complex"] is True
        assert any("3000" in reason for reason in body["complex_reasons"])

    async def test_estate_complex_when_value_condition_unknown(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)  # no assessment stored
        async with client_for() as client:
            response = await client.post(
                "/admin-tax",
                json={
                    "estate_id": str(estate_id),
                    "tax_year": "2026-27",
                    "income_total": "100",
                },
            )
        body = response.json()
        assert body["estate_complex"] is True
        assert any("cannot be verified" in reason for reason in body["complex_reasons"])

    async def test_duplicate_tax_year_conflicts(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        payload = {"estate_id": str(estate_id), "tax_year": "2026-27"}
        async with client_for() as client:
            assert (await client.post("/admin-tax", json=payload)).status_code == 201
            assert (await client.post("/admin-tax", json=payload)).status_code == 409

    async def test_update_rederives_deadlines(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            created = (
                await client.post(
                    "/admin-tax", json={"estate_id": str(estate_id), "tax_year": "2027-28"}
                )
            ).json()
            assert created["cgt_60day_deadlines"] == []
            patched = await client.patch(
                f"/admin-tax/{created['id']}",
                json={
                    "cgt_disposals": [
                        {"description": "Land", "disposal_date": "2027-01-31", "gain": "100"}
                    ]
                },
            )
        body = patched.json()
        assert body["cgt_60day_deadlines"][0]["deadline"] == "2027-04-01"

    async def test_thresholds_documented_with_sources(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for() as client:
            response = await client.get("/admin-tax/thresholds")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "income_de_minimis",
            "gains_annual_exempt_amount",
            "complex_estate_conditions",
        }
        for entry in body.values():
            assert entry["source"]  # every threshold cites its source

    async def test_admin_tax_persists_row(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            created = (
                await client.post(
                    "/admin-tax", json={"estate_id": str(estate_id), "tax_year": "2026-27"}
                )
            ).json()
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(AdminTax).where(AdminTax.id == uuid.UUID(created["id"]))
                )
            ).scalars().one()
            assert row.tax_year == "2026-27"
            assert row.isa_exemption_end == dt.date(2029, 1, 15)


# ---------------------------------------------------------------------------
# Module 17: digital items
# ---------------------------------------------------------------------------


class TestDigital:
    async def test_crud_roundtrip(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            created = await client.post(
                "/digital-items",
                json={
                    "estate_id": str(estate_id),
                    "service": "Streaming service",
                    "type": "subscription",
                    "action": "cancel",
                    "recurring_amount": "9.99",
                },
            )
            assert created.status_code == 201
            item = created.json()
            patched = await client.patch(
                f"/digital-items/{item['id']}", json={"status": "cancelled"}
            )
            assert patched.json()["status"] == "cancelled"
            deleted = await client.request(
                "DELETE", f"/digital-items/{item['id']}", json={"reason": "done"}
            )
            assert deleted.status_code == 200
        async with session_factory() as session:
            row = await session.get(DigitalItem, uuid.UUID(item["id"]))
            assert row.archived_at is not None
            assert row.archive_reason == "done"

    async def test_recurring_total_sums_active_items_only(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        async with client_for() as client:
            for payload in (
                {"service": "Streaming", "recurring_amount": "9.99"},
                {"service": "Cloud storage", "recurring_amount": "5.00"},
                {"service": "Old paper", "recurring_amount": "20.00", "status": "cancelled"},
                {"service": "No cost", "recurring_amount": None},
            ):
                response = await client.post(
                    "/digital-items", json={"estate_id": str(estate_id), **payload}
                )
                assert response.status_code == 201
            # An archived item must not count either.
            archived = (
                await client.post(
                    "/digital-items",
                    json={
                        "estate_id": str(estate_id),
                        "service": "Gym",
                        "recurring_amount": "7.00",
                    },
                )
            ).json()
            await client.request(
                "DELETE", f"/digital-items/{archived['id']}", json={"reason": "closed"}
            )
            total = (await client.get("/digital/recurring-total")).json()
        assert Decimal(str(total["recurring_total"])) == Decimal("14.99")
        assert total["item_count"] == 2
        assert "not normalised" in total["note"]


# ---------------------------------------------------------------------------
# IHT schedule task seeding
# ---------------------------------------------------------------------------


class TestScheduleSeedTasks:
    async def test_seed_creates_one_task_per_schedule_idempotently(
        self, client_for, session_factory
    ):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(
            session_factory, estate_id, required_schedules=["IHT405", "IHT435"]
        )
        async with client_for() as client:
            first = (await client.post("/iht/schedules/seed-tasks")).json()
            second = (await client.post("/iht/schedules/seed-tasks")).json()
        assert sorted(first["created"]) == [
            "Complete schedule IHT405",
            "Complete schedule IHT435",
        ]
        assert first["skipped"] == []
        assert second["created"] == []
        assert sorted(second["skipped"]) == sorted(first["created"])

        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(Task).where(Task.source == "iht_schedule")
                )
            ).scalars().all()
            assert len(rows) == 2
            assert all(row.estate_id == estate_id for row in rows)

    async def test_seed_only_adds_missing_schedules(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        await seed_assessment(session_factory, estate_id, required_schedules=["IHT405"])
        async with client_for() as client:
            assert (await client.post("/iht/schedules/seed-tasks")).json()["created"] == [
                "Complete schedule IHT405"
            ]
        # A later assessment requires one more schedule.
        await seed_assessment(
            session_factory, estate_id, required_schedules=["IHT405", "IHT411"]
        )
        async with client_for() as client:
            body = (await client.post("/iht/schedules/seed-tasks")).json()
        assert body["created"] == ["Complete schedule IHT411"]
        assert body["skipped"] == ["Complete schedule IHT405"]

    async def test_seed_404_without_assessment(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for() as client:
            assert (await client.post("/iht/schedules/seed-tasks")).status_code == 404


# ---------------------------------------------------------------------------
# Viewer is strictly read-only (403 matrix)
# ---------------------------------------------------------------------------


class TestViewerReadOnly:
    async def test_viewer_403_on_every_write(self, client_for, session_factory):
        estate_id = await seed_estate(session_factory)
        target = uuid.uuid4()
        writes = [
            ("POST", "/reliefs", {"estate_id": str(estate_id), "relief_type": "iht35"}),
            ("PATCH", f"/reliefs/{target}", {"status": "open"}),
            ("DELETE", f"/reliefs/{target}", {"reason": "x"}),
            ("POST", "/admin-tax", {"estate_id": str(estate_id), "tax_year": "2026-27"}),
            ("PATCH", f"/admin-tax/{target}", {"income_total": "1"}),
            ("DELETE", f"/admin-tax/{target}", {"reason": "x"}),
            ("POST", "/digital-items", {"estate_id": str(estate_id), "service": "x"}),
            ("PATCH", f"/digital-items/{target}", {"status": "closed"}),
            ("DELETE", f"/digital-items/{target}", {"reason": "x"}),
            ("POST", "/iht/schedules/seed-tasks", None),
        ]
        async with client_for(VIEWER) as client:
            for method, url, body in writes:
                response = await client.request(method, url, json=body)
                assert response.status_code == 403, f"{method} {url} -> {response.status_code}"

    async def test_viewer_can_read(self, client_for, session_factory):
        await seed_estate(session_factory)
        async with client_for(VIEWER) as client:
            assert (await client.get("/reliefs")).status_code == 200
            assert (await client.get("/reliefs/watchlist")).status_code == 200
            assert (await client.get("/admin-tax")).status_code == 200
            assert (await client.get("/digital-items")).status_code == 200
            assert (await client.get("/digital/recurring-total")).status_code == 200
