"""API tests for the Section 27 creditor notice router: CRUD, derived
claim_deadline, notice claims, and the safe-to-distribute guard.

Runs against the dedicated Postgres database (ad_test_registers) on the
live dev server at localhost:5474, created on demand and truncated between
tests. Fixtures are self-contained here by design; conftest.py only
provides the dev-auth environment.
"""

import asyncio
import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

DB_NAME = "ad_test_registers"
ADMIN_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{DB_NAME}"

EXECUTOR = "executor@test.local"
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

_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def _tables():
    from sqlmodel import SQLModel

    import app.models  # noqa: F401 - registers every table on the metadata

    return [SQLModel.metadata.tables[name] for name in REGISTER_TABLES]


@pytest.fixture(scope="module")
def _database():
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
    async def clean():
        async with _engine.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE TABLE {', '.join(REGISTER_TABLES)} CASCADE")
            )

    asyncio.run(clean())


@pytest.fixture
def estate_id(_clean_db) -> str:
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


TODAY = dt.date.today()
PAST_NOTICE_DATE = (TODAY - dt.timedelta(days=90)).isoformat()  # deadline well past


def create_notice(client, estate_id: str, **overrides) -> dict:
    payload = {"estate_id": estate_id, "gazette_ref": "GAZ-1", **overrides}
    response = client.post("/creditor-notices", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# CRUD and the derived claim deadline
# ---------------------------------------------------------------------------


def test_notice_crud_round_trip_and_soft_delete(estate_id, make_client):
    client = make_client()
    notice = create_notice(
        client, estate_id, gazette_date="2026-01-10", local_paper="Local Herald"
    )
    notice_id = notice["id"]
    assert notice["created_by"] == EXECUTOR
    # Two months and one day from the Gazette date (Trustee Act 1925 s.27).
    assert notice["claim_deadline"] == "2026-03-11"

    listed = client.get("/creditor-notices").json()
    assert [item["id"] for item in listed] == [notice_id]

    patched = client.patch(
        f"/creditor-notices/{notice_id}", json={"local_date": "2026-01-20"}
    )
    assert patched.status_code == 200
    # Deadline re-derived from the LATER of the two notice dates.
    assert patched.json()["claim_deadline"] == "2026-03-21"

    deleted = client.request(
        "DELETE", f"/creditor-notices/{notice_id}", json={"reason": "Placed in error"}
    )
    assert deleted.status_code == 200
    assert deleted.json()["archived_at"] is not None
    assert deleted.json()["archive_reason"] == "Placed in error"
    assert client.get("/creditor-notices").json() == []
    archived = client.get(
        "/creditor-notices", params={"include_archived": "true"}
    ).json()
    assert [item["id"] for item in archived] == [notice_id]
    rows = fetch_rows("SELECT id FROM creditor_notice")
    assert len(rows) == 1  # soft delete only


def test_notice_without_dates_has_no_deadline_and_is_not_safe(estate_id, make_client):
    client = make_client()
    notice = create_notice(client, estate_id)
    assert notice["claim_deadline"] is None
    assert notice["safe_to_distribute"] is False


# ---------------------------------------------------------------------------
# safe_to_distribute logic
# ---------------------------------------------------------------------------


def safe_state(client, estate_id: str) -> dict:
    response = client.get(
        "/creditor-notices/safe-to-distribute", params={"estate_id": estate_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_no_notice_means_not_safe(estate_id, make_client):
    client = make_client()
    state = safe_state(client, estate_id)
    assert state["safe_to_distribute"] is False
    assert any("No Section 27" in reason for reason in state["reasons"])


def test_future_deadline_means_not_safe(estate_id, make_client):
    client = make_client()
    notice = create_notice(client, estate_id, gazette_date=TODAY.isoformat())
    assert notice["safe_to_distribute"] is False
    state = safe_state(client, estate_id)
    assert state["safe_to_distribute"] is False
    assert any("not yet passed" in reason for reason in state["reasons"])


def test_past_deadline_and_no_open_claims_is_safe(estate_id, make_client):
    client = make_client()
    notice = create_notice(client, estate_id, gazette_date=PAST_NOTICE_DATE)
    assert notice["safe_to_distribute"] is True
    state = safe_state(client, estate_id)
    assert state["safe_to_distribute"] is True
    assert any("no claims remain open" in reason for reason in state["reasons"])


def test_open_claim_blocks_distribution_until_resolved(estate_id, make_client):
    client = make_client()
    notice = create_notice(client, estate_id, gazette_date=PAST_NOTICE_DATE)
    notice_id = notice["id"]

    claim = client.post(
        f"/creditor-notices/{notice_id}/claims",
        json={"claimant": "Claimant One", "amount": "150.00", "status": "received"},
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["id"]

    # The stored flag and the live guard both flip to false.
    assert client.get(f"/creditor-notices/{notice_id}").json()["safe_to_distribute"] is False
    state = safe_state(client, estate_id)
    assert state["safe_to_distribute"] is False
    assert any("open claim" in reason for reason in state["reasons"])

    # Resolving the claim restores distribution safety.
    resolved = client.patch(
        f"/creditor-notices/{notice_id}/claims/{claim_id}", json={"status": "resolved"}
    )
    assert resolved.status_code == 200, resolved.text
    assert client.get(f"/creditor-notices/{notice_id}").json()["safe_to_distribute"] is True
    assert safe_state(client, estate_id)["safe_to_distribute"] is True


def test_archived_notice_no_longer_counts(estate_id, make_client):
    client = make_client()
    notice = create_notice(client, estate_id, gazette_date=PAST_NOTICE_DATE)
    assert safe_state(client, estate_id)["safe_to_distribute"] is True
    client.request("DELETE", f"/creditor-notices/{notice['id']}")
    state = safe_state(client, estate_id)
    assert state["safe_to_distribute"] is False
    assert any("No Section 27" in reason for reason in state["reasons"])


def test_claims_list_and_missing_claim_404(estate_id, make_client):
    client = make_client()
    notice_id = create_notice(client, estate_id, gazette_date=PAST_NOTICE_DATE)["id"]
    client.post(
        f"/creditor-notices/{notice_id}/claims",
        json={"claimant": "Claimant One", "amount": "10.00"},
    )
    client.post(
        f"/creditor-notices/{notice_id}/claims",
        json={"claimant": "Claimant Two", "status": "received"},
    )
    claims = client.get(f"/creditor-notices/{notice_id}/claims").json()
    assert len(claims) == 2
    assert {claim["claimant"] for claim in claims} == {"Claimant One", "Claimant Two"}

    missing = client.patch(
        f"/creditor-notices/{notice_id}/claims/{uuid.uuid4()}", json={"status": "resolved"}
    )
    assert missing.status_code == 404
    assert client.get(f"/creditor-notices/{uuid.uuid4()}/claims").status_code == 404


# ---------------------------------------------------------------------------
# Roles and audit
# ---------------------------------------------------------------------------


def test_viewer_read_only_matrix(estate_id, make_client):
    executor = make_client()
    viewer = make_client(VIEWER)
    notice_id = create_notice(executor, estate_id, gazette_date=PAST_NOTICE_DATE)["id"]

    assert viewer.get("/creditor-notices").status_code == 200
    assert viewer.get(f"/creditor-notices/{notice_id}").status_code == 200
    assert viewer.get(f"/creditor-notices/{notice_id}/claims").status_code == 200
    assert viewer.get("/creditor-notices/safe-to-distribute").status_code == 200

    assert viewer.post(
        "/creditor-notices", json={"estate_id": estate_id}
    ).status_code == 403
    assert viewer.patch(
        f"/creditor-notices/{notice_id}", json={"gazette_ref": "GAZ-2"}
    ).status_code == 403
    assert viewer.request("DELETE", f"/creditor-notices/{notice_id}").status_code == 403
    assert viewer.post(
        f"/creditor-notices/{notice_id}/claims", json={"claimant": "Claimant One"}
    ).status_code == 403
    assert viewer.patch(
        f"/creditor-notices/{notice_id}/claims/{uuid.uuid4()}",
        json={"status": "resolved"},
    ).status_code == 403


def test_audit_rows_for_notice_and_claim_writes(estate_id, make_client):
    client = make_client()
    notice_id = create_notice(client, estate_id, gazette_date=PAST_NOTICE_DATE)["id"]
    client.patch(f"/creditor-notices/{notice_id}", json={"local_paper": "Local Herald"})
    claim_id = client.post(
        f"/creditor-notices/{notice_id}/claims",
        json={"claimant": "Claimant One", "status": "received"},
    ).json()["id"]
    client.patch(
        f"/creditor-notices/{notice_id}/claims/{claim_id}", json={"status": "resolved"}
    )

    notice_rows = fetch_rows(
        "SELECT action FROM audit_event WHERE entity = :entity ORDER BY timestamp",
        {"entity": f"creditor_notice:{notice_id}"},
    )
    # create, explicit update, plus derived-state updates from claim writes.
    assert [row.action for row in notice_rows] == ["create", "update", "update", "update"]

    claim_rows = fetch_rows(
        "SELECT actor, action FROM audit_event WHERE entity = :entity ORDER BY timestamp",
        {"entity": f"notice_claim:{claim_id}"},
    )
    assert [row.action for row in claim_rows] == ["create", "update"]
    assert all(row.actor == EXECUTOR for row in claim_rows)


def test_unknown_estate_is_404(make_client, _clean_db):
    client = make_client()
    response = client.post(
        "/creditor-notices", json={"estate_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
