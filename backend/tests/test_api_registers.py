"""API tests for the P1 register routers: assets (with valuations),
liabilities, debtors and creditors.

Runs against a dedicated Postgres database (ad_test_registers) on the live
dev server at localhost:5474, created on demand and truncated between
tests. Fixtures are self-contained here by design; conftest.py only
provides the dev-auth environment.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DB_NAME = "ad_test_registers"
ADMIN_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{DB_NAME}"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"
VIEWER = "viewer@test.local"

REGISTER_TABLES = (
    "audit_event",
    "notice_claim",
    "creditor_notice",
    "creditor",
    "debtor",
    "valuation_event",
    "liability",
    "asset",
    "contact",
    "estate",
)

# NullPool so no pooled connection outlives its event loop; TestClient and
# asyncio.run each use their own loop.
_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def _tables():
    from sqlmodel import SQLModel

    import app.models  # noqa: F401 - registers every table on the metadata

    return [SQLModel.metadata.tables[name] for name in REGISTER_TABLES]


@pytest.fixture(scope="module")
def _database():
    """Create the test database (if missing) and the register tables."""

    async def bootstrap():
        admin = create_async_engine(
            ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool
        )
        try:
            async with admin.connect() as conn:
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": DB_NAME},
                )
                if not exists:
                    await conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
        finally:
            await admin.dispose()

        tables = _tables()
        async with _engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: tables[0].metadata.create_all(
                    sync_conn, tables=tables, checkfirst=True
                )
            )

    asyncio.run(bootstrap())


@pytest.fixture(autouse=True)
def _clean_db(_database):
    """Empty every register table before each test."""

    async def clean():
        async with _engine.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE TABLE {', '.join(REGISTER_TABLES)} CASCADE")
            )

    asyncio.run(clean())


@pytest.fixture
def estate_id(_clean_db) -> str:
    """A fresh estate row every business record must belong to."""

    async def make() -> uuid.UUID:
        from app.models import Estate

        async with _session_factory() as session:
            estate = Estate(name="Test estate", created_by=EXECUTOR)
            session.add(estate)
            await session.commit()
            return estate.id

    return str(asyncio.run(make()))


@pytest.fixture
def make_client(_database):
    """TestClient factory: register routers wired, DB session overridden."""
    from fastapi.testclient import TestClient

    from app.api import assets, creditor_notices, creditors, debtors, liabilities
    from app.db import get_session
    from app.main import create_app

    async def override_session():
        async with _session_factory() as session:
            yield session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        app = create_app()
        existing = {getattr(route, "path", None) for route in app.routes}
        for module in (assets, liabilities, debtors, creditors, creditor_notices):
            if not any(route.path in existing for route in module.router.routes):
                app.include_router(module.router)
        app.dependency_overrides[get_session] = override_session
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    return _make


def fetch_rows(query: str, params: dict | None = None) -> list:
    async def run():
        async with _engine.connect() as conn:
            result = await conn.execute(text(query), params or {})
            return result.fetchall()

    return asyncio.run(run())


def as_decimal(value) -> Decimal:
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# CRUD round trips per register
# ---------------------------------------------------------------------------

REGISTER_CASES = [
    pytest.param(
        "assets",
        {"category": "cash", "description": "Current account", "dod_value": "1500.00"},
        {"status": "confirmed", "dod_value": "1750.50"},
        id="assets",
    ),
    pytest.param(
        "liabilities",
        {"type": "utility", "amount": "120.00", "iht_deductible": True},
        {"status": "settled", "amount": "95.25"},
        id="liabilities",
    ),
    pytest.param(
        "debtors",
        {"type": "refund", "amount_expected": "300.00", "status": "expected"},
        {"amount_received": "300.00", "status": "received"},
        id="debtors",
    ),
    pytest.param(
        "creditors",
        {"type": "trade", "amount_claimed": "450.00", "priority_class": "unsecured"},
        {"amount_agreed": "400.00", "status": "agreed"},
        id="creditors",
    ),
]

DECIMAL_FIELDS = {
    "dod_value",
    "amount",
    "amount_expected",
    "amount_received",
    "amount_claimed",
    "amount_agreed",
    "amount_paid",
}


def assert_fields(body: dict, expected: dict) -> None:
    for field, value in expected.items():
        if field in DECIMAL_FIELDS:
            assert as_decimal(body[field]) == as_decimal(value), field
        else:
            assert body[field] == value, field


@pytest.mark.parametrize(("path", "create_payload", "patch_payload"), REGISTER_CASES)
def test_crud_round_trip(path, create_payload, patch_payload, estate_id, make_client):
    client = make_client()

    created = client.post(f"/{path}", json={"estate_id": estate_id, **create_payload})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["id"]
    assert body["estate_id"] == estate_id
    assert body["created_by"] == EXECUTOR
    assert body["archived_at"] is None
    assert_fields(body, create_payload)
    row_id = body["id"]

    listed = client.get(f"/{path}")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [row_id]

    fetched = client.get(f"/{path}/{row_id}")
    assert fetched.status_code == 200
    assert_fields(fetched.json(), create_payload)

    patched = client.patch(f"/{path}/{row_id}", json=patch_payload)
    assert patched.status_code == 200, patched.text
    assert_fields(patched.json(), patch_payload)

    refetched = client.get(f"/{path}/{row_id}").json()
    assert_fields(refetched, patch_payload)


@pytest.mark.parametrize(("path", "create_payload", "patch_payload"), REGISTER_CASES)
def test_soft_delete_and_include_archived(
    path, create_payload, patch_payload, estate_id, make_client
):
    client = make_client()
    row_id = client.post(
        f"/{path}", json={"estate_id": estate_id, **create_payload}
    ).json()["id"]

    deleted = client.request("DELETE", f"/{path}/{row_id}", json={"reason": "Entered twice"})
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["archived_at"] is not None
    assert body["archive_reason"] == "Entered twice"

    # Excluded from the default list, included with include_archived.
    assert client.get(f"/{path}").json() == []
    archived_list = client.get(f"/{path}", params={"include_archived": "true"}).json()
    assert [item["id"] for item in archived_list] == [row_id]

    # Still retrievable by id and never physically deleted.
    assert client.get(f"/{path}/{row_id}").status_code == 200
    table = {"assets": "asset", "liabilities": "liability"}.get(path, path.rstrip("s"))
    rows = fetch_rows(f"SELECT id FROM {table}")  # noqa: S608 - fixed table names
    assert len(rows) == 1

    # Archiving twice is a conflict, not a hard delete.
    assert client.request("DELETE", f"/{path}/{row_id}").status_code == 409


@pytest.mark.parametrize(("path", "create_payload", "patch_payload"), REGISTER_CASES)
def test_viewer_read_only_matrix(path, create_payload, patch_payload, estate_id, make_client):
    executor = make_client()
    viewer = make_client(VIEWER)
    row_id = executor.post(
        f"/{path}", json={"estate_id": estate_id, **create_payload}
    ).json()["id"]

    assert viewer.get(f"/{path}").status_code == 200
    assert viewer.get(f"/{path}/{row_id}").status_code == 200
    create_attempt = viewer.post(f"/{path}", json={"estate_id": estate_id, **create_payload})
    assert create_attempt.status_code == 403
    assert viewer.patch(f"/{path}/{row_id}", json=patch_payload).status_code == 403
    assert viewer.request("DELETE", f"/{path}/{row_id}").status_code == 403

    # Nothing changed and nothing new was written by the viewer's attempts.
    assert len(executor.get(f"/{path}").json()) == 1


def test_unauthenticated_requests_are_401(make_client, estate_id):
    anonymous = make_client(None)
    assert anonymous.get("/assets").status_code == 401
    create_attempt = anonymous.post("/assets", json={"estate_id": estate_id, "category": "cash"})
    assert create_attempt.status_code == 401


def test_create_against_unknown_estate_is_404(make_client, _clean_db):
    client = make_client()
    response = client.post(
        "/assets", json={"estate_id": str(uuid.uuid4()), "category": "cash"}
    )
    assert response.status_code == 404


def test_list_is_estate_scoped_and_newest_first(estate_id, make_client):
    client = make_client()

    async def make_second_estate() -> uuid.UUID:
        from app.models import Estate

        async with _session_factory() as session:
            other = Estate(name="Other estate", created_by=EXECUTOR)
            session.add(other)
            await session.commit()
            return other.id

    other_estate_id = str(asyncio.run(make_second_estate()))

    first = client.post(
        "/liabilities", json={"estate_id": estate_id, "type": "mortgage", "amount": "100.00"}
    ).json()["id"]
    second = client.post(
        "/liabilities", json={"estate_id": estate_id, "type": "loan", "amount": "50.00"}
    ).json()["id"]
    client.post(
        "/liabilities",
        json={"estate_id": other_estate_id, "type": "card", "amount": "10.00"},
    )

    scoped = client.get("/liabilities", params={"estate_id": estate_id}).json()
    assert [item["id"] for item in scoped] == [second, first]  # newest first
    assert len(client.get("/liabilities").json()) == 3


def test_status_filter(estate_id, make_client):
    client = make_client()
    client.post(
        "/debtors",
        json={"estate_id": estate_id, "type": "refund", "status": "expected"},
    )
    received = client.post(
        "/debtors",
        json={"estate_id": estate_id, "type": "arrears", "status": "received"},
    ).json()["id"]

    filtered = client.get("/debtors", params={"status": "received"}).json()
    assert [item["id"] for item in filtered] == [received]


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_audit_rows_written_for_every_write(estate_id, make_client):
    client = make_client()
    row_id = client.post(
        "/assets", json={"estate_id": estate_id, "category": "shares", "dod_value": "9000.00"}
    ).json()["id"]
    client.patch(f"/assets/{row_id}", json={"status": "sold"})
    client.request("DELETE", f"/assets/{row_id}", json={"reason": "Duplicate"})

    rows = fetch_rows(
        "SELECT actor, action, before, after FROM audit_event "
        "WHERE entity = :entity ORDER BY timestamp",
        {"entity": f"asset:{row_id}"},
    )
    actions = [row.action for row in rows]
    assert actions == ["create", "update", "archive"]
    assert all(row.actor == EXECUTOR for row in rows)

    import json as jsonlib

    def as_dict(value):
        return jsonlib.loads(value) if isinstance(value, str) else value

    create_row, update_row, archive_row = rows
    assert create_row.before is None
    assert as_dict(create_row.after)["category"] == "shares"
    assert as_dict(create_row.after)["dod_value"] == "9000.00"  # Decimal stored JSON-safe
    assert as_dict(update_row.before)["status"] is None
    assert as_dict(update_row.after)["status"] == "sold"
    assert as_dict(archive_row.after)["archive_reason"] == "Duplicate"


# ---------------------------------------------------------------------------
# Valuation events
# ---------------------------------------------------------------------------


def test_valuation_event_updates_asset_current_value(estate_id, make_client):
    client = make_client()
    asset = client.post(
        "/assets",
        json={
            "estate_id": estate_id,
            "category": "property",
            "description": "Main residence",
            "dod_value": "250000.00",
            "value_basis": "estimate",
        },
    ).json()
    asset_id = asset["id"]

    first = client.post(
        f"/assets/{asset_id}/valuations",
        json={
            "value": "260000.00",
            "basis": "confirmed",
            "source": "Chartered surveyor report",
            "date": "2026-07-01",
        },
    )
    assert first.status_code == 201, first.text
    event = first.json()
    assert event["asset_id"] == asset_id
    assert as_decimal(event["value"]) == Decimal("260000.00")

    refreshed = client.get(f"/assets/{asset_id}").json()
    assert as_decimal(refreshed["current_or_realised_value"]) == Decimal("260000.00")
    assert refreshed["value_basis"] == "confirmed"
    assert refreshed["valuation_source"] == "Chartered surveyor report"
    assert refreshed["valuation_date"] == "2026-07-01"
    assert as_decimal(refreshed["dod_value"]) == Decimal("250000.00")  # untouched

    client.post(
        f"/assets/{asset_id}/valuations",
        json={"value": "255000.00", "basis": "estimate", "date": "2026-07-04"},
    )
    history = client.get(f"/assets/{asset_id}/valuations").json()
    assert len(history) == 2
    assert [as_decimal(item["value"]) for item in history] == [
        Decimal("255000.00"),
        Decimal("260000.00"),
    ]  # newest first

    latest = client.get(f"/assets/{asset_id}").json()
    assert as_decimal(latest["current_or_realised_value"]) == Decimal("255000.00")

    # Both the valuation event and the asset update were audited.
    event_rows = fetch_rows(
        "SELECT action FROM audit_event WHERE entity = :entity",
        {"entity": f"valuation_event:{event['id']}"},
    )
    assert [row.action for row in event_rows] == ["create"]
    asset_updates = fetch_rows(
        "SELECT action FROM audit_event WHERE entity = :entity AND action = 'update'",
        {"entity": f"asset:{asset_id}"},
    )
    assert len(asset_updates) == 2


def test_valuation_for_viewer_and_missing_asset(estate_id, make_client):
    viewer = make_client(VIEWER)
    assert (
        viewer.post(
            f"/assets/{uuid.uuid4()}/valuations",
            json={"value": "1.00", "date": "2026-07-01"},
        ).status_code
        == 403
    )
    executor = make_client()
    assert (
        executor.post(
            f"/assets/{uuid.uuid4()}/valuations",
            json={"value": "1.00", "date": "2026-07-01"},
        ).status_code
        == 404
    )
