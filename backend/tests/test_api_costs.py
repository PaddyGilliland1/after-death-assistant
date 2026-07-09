"""API tests for the costs router (P1 people routers).

Fixtures are self-contained by design (conftest.py is owned elsewhere):
a dedicated Postgres test database ad_test_people on localhost:5474 with
the schema created via SQLModel.metadata.create_all, and a client factory
that mounts the router under test with an overridden session dependency.
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
    """App with the costs router mounted, running on the test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api import costs as costs_api
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.include_router(costs_api.router)
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
        estate = Estate(name="Costs API test estate")
        session.add(estate)
        await session.commit()
        return str(estate.id)

    return run_db(api, _create)


def cost_payload(estate_id: str, **overrides) -> dict:
    payload = {
        "estate_id": estate_id,
        "description": "Probate application fee",
        "category": "probate",
        "amount": "300.00",
        "date": "2026-07-04",
        "paid_by": EXECUTOR,
        "payment_method": "card",
    }
    payload.update(overrides)
    return payload


def dec(value) -> Decimal:
    return Decimal(str(value))


def test_cost_crud_and_reimbursement_workflow(api, estate_id):
    client = api.client()

    created = client.post("/costs", json=cost_payload(estate_id, reimbursable=True))
    assert created.status_code == 201
    body = created.json()
    assert body["description"] == "Probate application fee"
    assert dec(body["amount"]) == Decimal("300.00")
    assert body["reimbursable"] is True
    assert body["reimbursed"] is False
    assert body["iht_treatment"] == "admin_not_deductible"
    cost_id = body["id"]

    detail = client.get(f"/costs/{cost_id}")
    assert detail.status_code == 200

    reimbursed = client.patch(
        f"/costs/{cost_id}", json={"reimbursed": True, "reimbursed_date": "2026-07-05"}
    )
    assert reimbursed.status_code == 200
    assert reimbursed.json()["reimbursed"] is True
    assert reimbursed.json()["reimbursed_date"] == "2026-07-05"

    listed = client.get("/costs", params={"estate_id": estate_id, "reimbursed": True})
    assert [c["id"] for c in listed.json()] == [cost_id]

    archived = client.request("DELETE", f"/costs/{cost_id}", json={"reason": "entered twice"})
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/costs", params={"estate_id": estate_id}).json() == []

    from sqlalchemy import select

    from app.models import AuditEvent

    async def _actions(session):
        rows = await session.execute(
            select(AuditEvent.action).where(AuditEvent.entity == f"cost:{cost_id}")
        )
        return sorted(rows.scalars().all())

    assert run_db(api, _actions) == ["archive", "create", "update"]


def test_cost_creation_notifies_other_executors_only(api, estate_id):
    client = api.client()
    created = client.post("/costs", json=cost_payload(estate_id))
    assert created.status_code == 201
    cost_id = created.json()["id"]

    from sqlalchemy import select

    from app.models import Notification

    async def _notifications(session):
        rows = await session.execute(
            select(Notification).where(Notification.estate_id == uuid.UUID(estate_id))
        )
        return list(rows.scalars().all())

    notifications = run_db(api, _notifications)

    # The actor was executor@test.local, so only the admin (the other
    # write-capable user) is notified; never the actor, never the viewer.
    assert [n.user_id for n in notifications] == [ADMIN]
    note = notifications[0]
    assert note.event_type == "cost_recorded"
    assert note.entity_ref == f"cost:{cost_id}"
    assert "Probate application fee" in note.message
    assert "300.00" in note.message
    assert note.read_at is None


def test_costs_by_type_aggregates_stored_figures(api, estate_id):
    client = api.client()
    client.post(
        "/costs",
        json=cost_payload(
            estate_id,
            description="Funeral director invoice",
            category="funeral",
            amount="1500.00",
            iht_treatment="funeral_deductible",
        ),
    )
    client.post("/costs", json=cost_payload(estate_id))  # probate 300.00
    client.post(
        "/costs",
        json=cost_payload(
            estate_id, description="Property valuation", category="valuation", amount="250.00"
        ),
    )
    duplicate = client.post(
        "/costs",
        json=cost_payload(estate_id, description="Duplicate entry", amount="999.00"),
    ).json()
    client.request("DELETE", f"/costs/{duplicate['id']}", json={"reason": "duplicate"})

    response = client.get("/costs/by-type", params={"estate_id": estate_id})
    assert response.status_code == 200
    body = response.json()

    by_category = {row["category"]: dec(row["total"]) for row in body["by_category"]}
    assert by_category == {
        "funeral": Decimal("1500.00"),
        "probate": Decimal("300.00"),
        "valuation": Decimal("250.00"),
    }
    by_treatment = {row["iht_treatment"]: dec(row["total"]) for row in body["by_iht_treatment"]}
    assert by_treatment == {
        "funeral_deductible": Decimal("1500.00"),
        "admin_not_deductible": Decimal("550.00"),
    }


def test_viewer_read_only_and_executor_private_costs(api, estate_id):
    executor = api.client()
    viewer = api.client(VIEWER)

    public = executor.post(
        "/costs", json=cost_payload(estate_id, description="Public cost", amount="100.00")
    ).json()
    private = executor.post(
        "/costs",
        json=cost_payload(
            estate_id, description="Executor-only cost", amount="40.00", executor_private=True
        ),
    ).json()

    # Viewer writes are refused across the board.
    assert viewer.post("/costs", json=cost_payload(estate_id)).status_code == 403
    assert viewer.patch(f"/costs/{public['id']}", json={"reimbursed": True}).status_code == 403
    assert viewer.delete(f"/costs/{public['id']}").status_code == 403

    # Viewer list and detail exclude executor_private rows.
    viewer_list = viewer.get("/costs", params={"estate_id": estate_id})
    assert [c["id"] for c in viewer_list.json()] == [public["id"]]
    assert viewer.get(f"/costs/{private['id']}").status_code == 404

    executor_list = executor.get("/costs", params={"estate_id": estate_id})
    assert {c["id"] for c in executor_list.json()} == {public["id"], private["id"]}
    assert executor.get(f"/costs/{private['id']}").status_code == 200

    # The by-type view also excludes private rows for the viewer.
    viewer_totals = viewer.get("/costs/by-type", params={"estate_id": estate_id}).json()
    assert {row["category"]: dec(row["total"]) for row in viewer_totals["by_category"]} == {
        "probate": Decimal("100.00")
    }
    executor_totals = executor.get("/costs/by-type", params={"estate_id": estate_id}).json()
    assert {row["category"]: dec(row["total"]) for row in executor_totals["by_category"]} == {
        "probate": Decimal("140.00")
    }


def test_create_cost_unknown_estate_is_404(api):
    client = api.client()
    response = client.post("/costs", json=cost_payload(str(uuid.uuid4())))
    assert response.status_code == 404
