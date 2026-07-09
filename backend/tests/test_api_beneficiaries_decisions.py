"""API tests for the beneficiaries and decisions routers (P1 people routers).

Fixtures are self-contained by design (conftest.py is owned elsewhere):
a dedicated Postgres test database ad_test_people on localhost:5474 with
the schema created via SQLModel.metadata.create_all, and a client factory
that mounts the routers under test with an overridden session dependency.
The contacts router is mounted too because legacies reference contacts.
No personal data appears in these fixtures.
"""

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

PG_PORT = 5474
PG_DB = "ad_test_people"
DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:{PG_PORT}/{PG_DB}"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"
VIEWER = "viewer@test.local"


@pytest.fixture(scope="module")
def database():
    """Create the test database if needed, the pgvector extension and the schema."""

    async def _prepare() -> None:
        import asyncpg
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlmodel import SQLModel

        import app.models  # noqa: F401  (import registers every table)

        conn = await asyncpg.connect(
            host="localhost",
            port=PG_PORT,
            user="postgres",
            password="postgres",
            database="postgres",
        )
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", PG_DB)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{PG_DB}"')
        await conn.close()

        engine = create_async_engine(DB_URL)
        async with engine.begin() as tx:
            await tx.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await tx.run_sync(SQLModel.metadata.create_all)
        await engine.dispose()

    asyncio.run(_prepare())


@pytest.fixture
def api(database):
    """App with the beneficiaries, decisions and contacts routers mounted."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api import beneficiaries as beneficiaries_api
    from app.api import contacts as contacts_api
    from app.api import decisions as decisions_api
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.include_router(beneficiaries_api.router)
    app.include_router(decisions_api.router)
    app.include_router(contacts_api.router)
    app.dependency_overrides[get_session] = _override_session

    def make_client(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    yield SimpleNamespace(client=make_client, session_factory=session_factory)
    asyncio.run(engine.dispose())


def run_db(api, fn):
    """Run an async callable that takes a session, on the test database."""

    async def _go():
        async with api.session_factory() as session:
            return await fn(session)

    return asyncio.run(_go())


@pytest.fixture
def estate_id(api):
    """A fresh estate per test keeps every assertion isolated."""
    from app.models import Estate

    async def _create(session):
        estate = Estate(name="Beneficiaries API test estate")
        session.add(estate)
        await session.commit()
        return str(estate.id)

    return run_db(api, _create)


@pytest.fixture
def beneficiary_contact_id(api, estate_id):
    client = api.client()
    response = client.post(
        "/contacts",
        json={
            "estate_id": estate_id,
            "name": "Residuary beneficiary one",
            "category": "beneficiary",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def legacy_payload(estate_id: str, contact_id: str, **overrides) -> dict:
    payload = {
        "estate_id": estate_id,
        "beneficiary_contact_id": contact_id,
        "legacy_type": "pecuniary",
        "amount_or_share": "5000.00",
        "exempt_or_chargeable": "chargeable",
        "status": "unpaid",
    }
    payload.update(overrides)
    return payload


def decision_payload(estate_id: str, **overrides) -> dict:
    payload = {
        "estate_id": estate_id,
        "date": "2026-03-15",
        "title": "Sell the vehicle at trade value",
        "rationale": "A quick sale avoids ongoing insurance and storage costs.",
        "options_considered": [
            {"option": "Sell at trade value", "notes": "Fast, certain figure"},
            {"option": "Private sale", "notes": "Higher price, slower, more effort"},
        ],
        "agreed_by": [EXECUTOR, ADMIN],
    }
    payload.update(overrides)
    return payload


def dec(value) -> Decimal:
    return Decimal(str(value))


def test_legacy_crud_with_distribution_totals(api, estate_id, beneficiary_contact_id):
    client = api.client()

    created = client.post(
        "/beneficiaries", json=legacy_payload(estate_id, beneficiary_contact_id)
    )
    assert created.status_code == 201
    body = created.json()
    assert body["legacy_type"] == "pecuniary"
    assert dec(body["amount_or_share"]) == Decimal("5000.00")
    assert dec(body["distributed_total"]) == Decimal("0")
    legacy_id = body["id"]

    first = client.post(
        f"/beneficiaries/{legacy_id}/distributions",
        json={"amount": "1000.00", "date": "2026-07-01", "method": "bank transfer"},
    )
    assert first.status_code == 201
    assert first.json()["created_by"] == EXECUTOR
    second = client.post(
        f"/beneficiaries/{legacy_id}/distributions",
        json={"amount": "500.00", "date": "2026-07-02", "method": "bank transfer"},
    )
    assert second.status_code == 201

    rows = client.get(f"/beneficiaries/{legacy_id}/distributions")
    assert rows.status_code == 200
    assert [dec(row["amount"]) for row in rows.json()] == [
        Decimal("1000.00"),
        Decimal("500.00"),
    ]

    # Both list and detail carry the per-legacy total of recorded
    # distributions (a sum of stored rows only).
    listed = client.get("/beneficiaries", params={"estate_id": estate_id})
    assert [dec(row["distributed_total"]) for row in listed.json()] == [Decimal("1500.00")]
    detail = client.get(f"/beneficiaries/{legacy_id}")
    assert dec(detail.json()["distributed_total"]) == Decimal("1500.00")

    patched = client.patch(f"/beneficiaries/{legacy_id}", json={"status": "part_paid"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "part_paid"

    archived = client.request(
        "DELETE", f"/beneficiaries/{legacy_id}", json={"reason": "settled in full"}
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/beneficiaries", params={"estate_id": estate_id}).json() == []

    # No distribution can be recorded against an archived legacy.
    refused = client.post(
        f"/beneficiaries/{legacy_id}/distributions",
        json={"amount": "1.00", "date": "2026-07-06"},
    )
    assert refused.status_code == 409

    from sqlalchemy import select

    from app.models import AuditEvent

    async def _actions(session):
        rows = await session.execute(
            select(AuditEvent.action).where(
                AuditEvent.entity == f"beneficiary_legacy:{legacy_id}"
            )
        )
        return sorted(rows.scalars().all())

    assert run_db(api, _actions) == ["archive", "create", "update"]


def test_legacy_unknown_contact_or_estate_is_404(api, estate_id, beneficiary_contact_id):
    client = api.client()
    unknown_contact = client.post(
        "/beneficiaries", json=legacy_payload(estate_id, str(uuid.uuid4()))
    )
    assert unknown_contact.status_code == 404
    unknown_estate = client.post(
        "/beneficiaries", json=legacy_payload(str(uuid.uuid4()), beneficiary_contact_id)
    )
    assert unknown_estate.status_code == 404


def test_distribution_endpoint_is_record_keeping_only():
    """The contract requires the docstring to state that no payment is made."""
    from app.api.beneficiaries import record_distribution

    assert "NO payment is made by code" in record_distribution.__doc__


def test_decisions_are_immutable_once_recorded(api, estate_id):
    client = api.client()

    created = client.post("/decisions", json=decision_payload(estate_id))
    assert created.status_code == 201
    body = created.json()
    assert body["made_by"] == EXECUTOR
    assert body["agreed_by"] == [EXECUTOR, ADMIN]
    decision_id = body["id"]

    listed = client.get("/decisions", params={"estate_id": estate_id})
    assert [d["id"] for d in listed.json()] == [decision_id]
    detail = client.get(f"/decisions/{decision_id}")
    assert detail.status_code == 200

    patched = client.patch(f"/decisions/{decision_id}", json={"title": "Changed"})
    assert patched.status_code == 405
    assert "immutable" in patched.json()["detail"].lower()

    deleted = client.delete(f"/decisions/{decision_id}")
    assert deleted.status_code == 405
    assert "immutable" in deleted.json()["detail"].lower()

    # The decision is untouched after both attempts.
    unchanged = client.get(f"/decisions/{decision_id}").json()
    assert unchanged["title"] == "Sell the vehicle at trade value"


def test_viewer_read_only_and_executor_private_decisions(
    api, estate_id, beneficiary_contact_id
):
    executor = api.client()
    viewer = api.client(VIEWER)

    legacy = executor.post(
        "/beneficiaries", json=legacy_payload(estate_id, beneficiary_contact_id)
    ).json()
    public = executor.post(
        "/decisions", json=decision_payload(estate_id, title="Public decision")
    ).json()
    private = executor.post(
        "/decisions",
        json=decision_payload(estate_id, title="Executor-only decision", executor_private=True),
    ).json()

    # Viewer writes are refused across the board.
    assert (
        viewer.post(
            "/beneficiaries", json=legacy_payload(estate_id, beneficiary_contact_id)
        ).status_code
        == 403
    )
    assert (
        viewer.post(
            f"/beneficiaries/{legacy['id']}/distributions",
            json={"amount": "1.00", "date": "2026-07-06"},
        ).status_code
        == 403
    )
    assert (
        viewer.patch(f"/beneficiaries/{legacy['id']}", json={"status": "paid"}).status_code
        == 403
    )
    assert viewer.delete(f"/beneficiaries/{legacy['id']}").status_code == 403
    assert viewer.post("/decisions", json=decision_payload(estate_id)).status_code == 403

    # Viewer reads work, with executor_private decisions excluded.
    assert viewer.get("/beneficiaries", params={"estate_id": estate_id}).status_code == 200
    viewer_decisions = viewer.get("/decisions", params={"estate_id": estate_id})
    assert [d["id"] for d in viewer_decisions.json()] == [public["id"]]
    assert viewer.get(f"/decisions/{private['id']}").status_code == 404

    executor_decisions = executor.get("/decisions", params={"estate_id": estate_id})
    assert {d["id"] for d in executor_decisions.json()} == {public["id"], private["id"]}
    assert executor.get(f"/decisions/{private['id']}").status_code == 200
