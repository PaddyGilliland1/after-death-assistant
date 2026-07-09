"""API tests for the tasks router (P1 people routers).

Fixtures are self-contained by design (conftest.py is owned elsewhere):
a dedicated Postgres test database ad_test_people on localhost:5474 with
the schema created via SQLModel.metadata.create_all, and a client factory
that mounts the router under test with an overridden session dependency.
No personal data appears in these fixtures.
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
    """App with the tasks router mounted, running on the test database."""
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.api import tasks as tasks_api
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.include_router(tasks_api.router)
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
        estate = Estate(name="Tasks API test estate")
        session.add(estate)
        await session.commit()
        return str(estate.id)

    return run_db(api, _create)


def task_payload(estate_id: str, **overrides) -> dict:
    payload = {"estate_id": estate_id, "title": "Value the estate", "status": "open"}
    payload.update(overrides)
    return payload


def test_task_crud_round_trip_with_checklist_and_audit(api, estate_id):
    client = api.client()

    created = client.post(
        "/tasks",
        json=task_payload(
            estate_id,
            description="Collect date-of-death valuations",
            assignees=[EXECUTOR],
            priority="high",
            due_date="2026-08-01",
            checklist=[
                {"text": "Request bank valuation"},
                {"text": "Request property appraisal", "done": True},
            ],
        ),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["checklist"] == [
        {"text": "Request bank valuation", "done": False},
        {"text": "Request property appraisal", "done": True},
    ]
    assert body["assignees"] == [EXECUTOR]
    assert body["created_by"] == EXECUTOR
    task_id = body["id"]

    detail = client.get(f"/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == task_id

    patched = client.patch(
        f"/tasks/{task_id}",
        json={
            "status": "in_progress",
            "checklist": [{"text": "Request bank valuation", "done": True}],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"
    assert patched.json()["checklist"] == [{"text": "Request bank valuation", "done": True}]

    archived = client.request("DELETE", f"/tasks/{task_id}", json={"reason": "raised in error"})
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert archived.json()["archive_reason"] == "raised in error"
    assert client.get("/tasks", params={"estate_id": estate_id}).json() == []

    from sqlalchemy import select

    from app.models import AuditEvent

    async def _actions(session):
        rows = await session.execute(
            select(AuditEvent.action).where(AuditEvent.entity == f"task:{task_id}")
        )
        return sorted(rows.scalars().all())

    assert run_db(api, _actions) == ["archive", "create", "update"]


def test_task_list_filters(api, estate_id):
    client = api.client()
    early = client.post(
        "/tasks",
        json=task_payload(
            estate_id, title="Notify the bank", due_date="2026-07-10", assignees=[EXECUTOR]
        ),
    ).json()
    late = client.post(
        "/tasks",
        json=task_payload(
            estate_id, title="Prepare estate accounts", due_date="2026-09-01", assignees=[ADMIN]
        ),
    ).json()
    done = client.post(
        "/tasks",
        json=task_payload(
            estate_id, title="Order copy certificates", due_date="2026-07-05", status="done"
        ),
    ).json()

    due = client.get("/tasks", params={"estate_id": estate_id, "due_before": "2026-08-01"})
    assert {t["id"] for t in due.json()} == {early["id"], done["id"]}

    assigned = client.get("/tasks", params={"estate_id": estate_id, "assignee": EXECUTOR})
    assert [t["id"] for t in assigned.json()] == [early["id"]]

    by_status = client.get("/tasks", params={"estate_id": estate_id, "status": "done"})
    assert [t["id"] for t in by_status.json()] == [done["id"]]

    combined = client.get(
        "/tasks",
        params={"estate_id": estate_id, "due_before": "2026-08-01", "status": "open"},
    )
    assert [t["id"] for t in combined.json()] == [early["id"]]

    everything = client.get("/tasks", params={"estate_id": estate_id})
    assert {t["id"] for t in everything.json()} == {early["id"], late["id"], done["id"]}


def test_dependency_references_are_validated(api, estate_id):
    client = api.client()

    unknown = client.post("/tasks", json=task_payload(estate_id, blocked_by=[str(uuid.uuid4())]))
    assert unknown.status_code == 422

    not_a_uuid = client.post("/tasks", json=task_payload(estate_id, blocked_by=["not-a-uuid"]))
    assert not_a_uuid.status_code == 422

    task = client.post("/tasks", json=task_payload(estate_id)).json()
    self_reference = client.patch(f"/tasks/{task['id']}", json={"blocked_by": [task["id"]]})
    assert self_reference.status_code == 422
    self_blocks = client.patch(f"/tasks/{task['id']}", json={"blocks": [task["id"]]})
    assert self_blocks.status_code == 422


def test_dependency_cycles_are_rejected(api, estate_id):
    client = api.client()
    task_a = client.post("/tasks", json=task_payload(estate_id, title="Task A")).json()
    task_b = client.post(
        "/tasks", json=task_payload(estate_id, title="Task B", blocked_by=[task_a["id"]])
    ).json()

    # Direct two-node cycle: A is blocked by B while B is blocked by A.
    direct = client.patch(f"/tasks/{task_a['id']}", json={"blocked_by": [task_b["id"]]})
    assert direct.status_code == 422
    assert "cycle" in direct.json()["detail"].lower()

    # Create-time cycle through blocked_by and blocks of the same payload.
    create_time = client.post(
        "/tasks",
        json=task_payload(
            estate_id, title="Task C", blocked_by=[task_a["id"]], blocks=[task_a["id"]]
        ),
    )
    assert create_time.status_code == 422

    # Longer chain: C depends on B depends on A; A may not depend on C.
    task_c = client.post(
        "/tasks", json=task_payload(estate_id, title="Task C2", blocked_by=[task_b["id"]])
    ).json()
    chained = client.patch(f"/tasks/{task_a['id']}", json={"blocked_by": [task_c["id"]]})
    assert chained.status_code == 422

    # A valid extra link still works after the rejections.
    fine = client.patch(f"/tasks/{task_c['id']}", json={"blocks": []})
    assert fine.status_code == 200


def test_blocked_task_cannot_move_to_done(api, estate_id):
    client = api.client()
    blocker = client.post(
        "/tasks", json=task_payload(estate_id, title="Obtain the grant")
    ).json()
    blocked = client.post(
        "/tasks",
        json=task_payload(estate_id, title="Distribute residue", blocked_by=[blocker["id"]]),
    ).json()

    refused = client.patch(f"/tasks/{blocked['id']}", json={"status": "done"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["blocking"] == [blocker["id"]]

    refused_on_create = client.post(
        "/tasks",
        json=task_payload(
            estate_id, title="Created done while blocked", status="done",
            blocked_by=[blocker["id"]],
        ),
    )
    assert refused_on_create.status_code == 409

    assert client.patch(f"/tasks/{blocker['id']}", json={"status": "done"}).status_code == 200
    allowed = client.patch(f"/tasks/{blocked['id']}", json={"status": "done"})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "done"


def test_comments_round_trip(api, estate_id):
    client = api.client()
    task = client.post("/tasks", json=task_payload(estate_id)).json()

    created = client.post(
        f"/tasks/{task['id']}/comments", json={"body": "Waiting on the registrar"}
    )
    assert created.status_code == 201
    assert created.json()["created_by"] == EXECUTOR

    rows = client.get(f"/tasks/{task['id']}/comments")
    assert rows.status_code == 200
    assert [row["body"] for row in rows.json()] == ["Waiting on the registrar"]

    unknown = client.get(f"/tasks/{uuid.uuid4()}/comments")
    assert unknown.status_code == 404


def test_viewer_read_only_and_executor_private_tasks(api, estate_id):
    executor = api.client()
    viewer = api.client(VIEWER)

    public = executor.post("/tasks", json=task_payload(estate_id, title="Public task")).json()
    private = executor.post(
        "/tasks",
        json=task_payload(estate_id, title="Executor-only task", executor_private=True),
    ).json()
    executor.post(f"/tasks/{private['id']}/comments", json={"body": "Private discussion"})

    # Viewer writes are refused across the board.
    assert viewer.post("/tasks", json=task_payload(estate_id)).status_code == 403
    assert viewer.patch(f"/tasks/{public['id']}", json={"status": "done"}).status_code == 403
    assert viewer.delete(f"/tasks/{public['id']}").status_code == 403
    assert (
        viewer.post(f"/tasks/{public['id']}/comments", json={"body": "note"}).status_code == 403
    )

    # Viewer list excludes the private task; the executor sees both.
    viewer_list = viewer.get("/tasks", params={"estate_id": estate_id})
    assert [t["id"] for t in viewer_list.json()] == [public["id"]]
    executor_list = executor.get("/tasks", params={"estate_id": estate_id})
    assert {t["id"] for t in executor_list.json()} == {public["id"], private["id"]}

    # Viewer detail and comments for the private task read as not found.
    assert viewer.get(f"/tasks/{private['id']}").status_code == 404
    assert viewer.get(f"/tasks/{private['id']}/comments").status_code == 404
    assert executor.get(f"/tasks/{private['id']}").status_code == 200
    assert executor.get(f"/tasks/{private['id']}/comments").status_code == 200
