"""API tests for the contacts router (P1 people routers).

Fixtures are self-contained by design (conftest.py is owned elsewhere):
a dedicated Postgres test database ad_test_people on localhost:5474 with
the schema created via SQLModel.metadata.create_all, and a client factory
that mounts the router under test with an overridden session dependency.
No personal data appears in these fixtures; phone numbers use the Ofcom
fictional range.
"""

import asyncio
import uuid
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
    """App with the contacts router mounted, running on the test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api import contacts as contacts_api
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
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
        estate = Estate(name="Contacts API test estate")
        session.add(estate)
        await session.commit()
        return str(estate.id)

    return run_db(api, _create)


def contact_payload(estate_id: str, **overrides) -> dict:
    payload = {
        "estate_id": estate_id,
        "name": "Alpha Bank",
        "category": "bank",
        "org": "Alpha Bank plc",
        "references": ["ACC-0001"],
        "holds_or_handles": "Current account",
        "notify_required": True,
        "notification_status": "pending",
    }
    payload.update(overrides)
    return payload


def test_contact_crud_round_trip_with_audit(api, estate_id):
    client = api.client()

    created = client.post("/contacts", json=contact_payload(estate_id))
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Alpha Bank"
    assert body["category"] == "bank"
    assert body["references"] == ["ACC-0001"]
    assert body["created_by"] == EXECUTOR
    assert body["archived_at"] is None
    contact_id = body["id"]

    detail = client.get(f"/contacts/{contact_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == contact_id

    updated = client.patch(f"/contacts/{contact_id}", json={"phone": "01632 960000"})
    assert updated.status_code == 200
    assert updated.json()["phone"] == "01632 960000"

    listed = client.get("/contacts", params={"estate_id": estate_id})
    assert [c["id"] for c in listed.json()] == [contact_id]

    archived = client.request(
        "DELETE", f"/contacts/{contact_id}", json={"reason": "duplicate entry"}
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert archived.json()["archive_reason"] == "duplicate entry"

    assert client.get("/contacts", params={"estate_id": estate_id}).json() == []
    with_archived = client.get(
        "/contacts", params={"estate_id": estate_id, "include_archived": True}
    )
    assert [c["id"] for c in with_archived.json()] == [contact_id]

    # Archiving twice is rejected; the row is never physically deleted.
    assert client.delete(f"/contacts/{contact_id}").status_code == 409

    from sqlalchemy import select

    from app.models import AuditEvent

    async def _actions(session):
        rows = await session.execute(
            select(AuditEvent.action).where(AuditEvent.entity == f"contact:{contact_id}")
        )
        return sorted(rows.scalars().all())

    assert run_db(api, _actions) == ["archive", "create", "update"]


def test_full_category_enum_accepted(api, estate_id):
    from app.models.enums import ContactCategory

    client = api.client()
    for category in ContactCategory:
        response = client.post(
            "/contacts",
            json=contact_payload(
                estate_id,
                name=f"Example {category.value}",
                category=category.value,
                notify_required=False,
                notification_status=None,
            ),
        )
        assert response.status_code == 201, category
        assert response.json()["category"] == category.value

    rejected = client.post("/contacts", json=contact_payload(estate_id, category="not_a_category"))
    assert rejected.status_code == 422


def test_create_contact_unknown_estate_is_404(api):
    client = api.client()
    response = client.post("/contacts", json=contact_payload(str(uuid.uuid4())))
    assert response.status_code == 404


def test_anonymous_request_is_401(api):
    anonymous = api.client(None)
    assert anonymous.get("/contacts").status_code == 401


def test_viewer_read_only_matrix(api, estate_id):
    executor = api.client()
    viewer = api.client(VIEWER)
    contact_id = executor.post("/contacts", json=contact_payload(estate_id)).json()["id"]

    assert viewer.post("/contacts", json=contact_payload(estate_id)).status_code == 403
    assert (
        viewer.patch(f"/contacts/{contact_id}", json={"phone": "01632 960001"}).status_code == 403
    )
    assert viewer.delete(f"/contacts/{contact_id}").status_code == 403
    assert (
        viewer.post(
            f"/contacts/{contact_id}/interactions", json={"date": "2026-07-01"}
        ).status_code
        == 403
    )

    # Reads remain open to the viewer role.
    assert viewer.get("/contacts", params={"estate_id": estate_id}).status_code == 200
    assert viewer.get(f"/contacts/{contact_id}").status_code == 200


def test_notification_tracker_chase_list(api, estate_id):
    client = api.client()
    pending = client.post(
        "/contacts",
        json=contact_payload(estate_id, name="Beta Insurance", category="insurer"),
    ).json()
    client.post(
        "/contacts",
        json=contact_payload(
            estate_id, name="Gamma Pensions", category="pension", notification_status="done"
        ),
    )
    client.post(
        "/contacts",
        json=contact_payload(
            estate_id,
            name="Delta Utilities",
            category="utility",
            notify_required=False,
            notification_status=None,
        ),
    )

    chase = client.get(
        "/contacts",
        params={
            "estate_id": estate_id,
            "notify_required": True,
            "notification_status": "pending",
        },
    )
    assert chase.status_code == 200
    assert [c["id"] for c in chase.json()] == [pending["id"]]

    updated = client.patch(
        f"/contacts/{pending['id']}",
        json={
            "notification_status": "done",
            "notified_date": "2026-07-02",
            "notified_method": "letter",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["notification_status"] == "done"
    assert updated.json()["notified_date"] == "2026-07-02"
    assert updated.json()["notified_method"] == "letter"

    emptied = client.get(
        "/contacts",
        params={
            "estate_id": estate_id,
            "notify_required": True,
            "notification_status": "pending",
        },
    )
    assert emptied.json() == []


def test_interactions_nested_and_executor_private_filtering(api, estate_id):
    executor = api.client()
    viewer = api.client(VIEWER)
    contact_id = executor.post("/contacts", json=contact_payload(estate_id)).json()["id"]

    public = executor.post(
        f"/contacts/{contact_id}/interactions",
        json={
            "date": "2026-07-01",
            "channel": "phone",
            "direction": "outbound",
            "summary": "Requested the account closure form",
            "follow_up_date": "2026-07-10",
        },
    )
    assert public.status_code == 201
    assert public.json()["by_user"] == EXECUTOR
    assert public.json()["executor_private"] is False

    private = executor.post(
        f"/contacts/{contact_id}/interactions",
        json={
            "date": "2026-07-02",
            "channel": "email",
            "direction": "outbound",
            "summary": "Executor-only note",
            "executor_private": True,
        },
    )
    assert private.status_code == 201

    executor_rows = executor.get(f"/contacts/{contact_id}/interactions")
    assert executor_rows.status_code == 200
    assert {row["id"] for row in executor_rows.json()} == {
        public.json()["id"],
        private.json()["id"],
    }

    viewer_rows = viewer.get(f"/contacts/{contact_id}/interactions")
    assert viewer_rows.status_code == 200
    assert [row["id"] for row in viewer_rows.json()] == [public.json()["id"]]

    unknown = executor.get(f"/contacts/{uuid.uuid4()}/interactions")
    assert unknown.status_code == 404
