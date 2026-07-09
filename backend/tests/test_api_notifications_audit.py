"""Notifications, audit, activity, search and approvals API tests.

Own fixtures: Postgres ad_test_collab on localhost:5474.
"""

import asyncio
import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/ad_test_collab"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"
VIEWER = "viewer@test.local"


async def _prepare_database() -> None:
    from sqlmodel import SQLModel

    import app.models  # noqa: F401

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


async def _with_session(fn):
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await fn(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
def estate_id(clean_db) -> str:
    async def _do(session):
        from app.models import Estate

        estate = Estate(
            name="Demo Estate (test)",
            date_of_death=dt.date(2026, 1, 15),
            created_by="test",
        )
        session.add(estate)
        await session.flush()
        return str(estate.id)

    return asyncio.run(_with_session(_do))


@pytest.fixture()
def make_client(clean_db, tmp_path):
    os.environ["STORAGE_LOCAL_PATH"] = str(tmp_path / "storage")
    from app.core.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.api import approvals, audit_activity, documents, notifications, process
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with factory() as session:
            yield session

    app = create_app()
    for module in (documents, notifications, audit_activity, process, approvals):
        app.include_router(module.router)
    app.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    yield _make
    asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _create_notifications(estate_id: str) -> dict[str, str]:
    async def _do(session):
        from app.models import Notification
        from app.models.base import utcnow

        eid = uuid.UUID(estate_id)
        already_read = Notification(
            estate_id=eid,
            user_id=EXECUTOR,
            event_type="cost_recorded",
            message="Demo cost recorded",
            read_at=utcnow(),
        )
        unread_one = Notification(
            estate_id=eid,
            user_id=EXECUTOR,
            event_type="asset_added",
            message="Demo asset added",
        )
        unread_two = Notification(
            estate_id=eid,
            user_id=EXECUTOR,
            event_type="deadline_due",
            message="Demo deadline approaching",
        )
        other_user = Notification(
            estate_id=eid,
            user_id=ADMIN,
            event_type="approval_needed",
            message="Demo approval needed",
        )
        session.add_all([already_read, unread_one, unread_two, other_user])
        await session.flush()
        return {
            "read": str(already_read.id),
            "unread_one": str(unread_one.id),
            "unread_two": str(unread_two.id),
            "other_user": str(other_user.id),
        }

    return asyncio.run(_with_session(_do))


def test_notifications_own_rows_only_unread_first(estate_id, make_client):
    ids = _create_notifications(estate_id)
    client = make_client(EXECUTOR)

    rows = client.get("/notifications").json()
    assert len(rows) == 3  # never another user's rows
    assert ids["other_user"] not in {row["id"] for row in rows}
    assert [row["read_at"] is None for row in rows] == [True, True, False]


def test_notification_read_flow(estate_id, make_client):
    ids = _create_notifications(estate_id)
    client = make_client(EXECUTOR)

    response = client.post(f"/notifications/{ids['unread_one']}/read")
    assert response.status_code == 200
    assert response.json()["read_at"] is not None

    # Another user's notification is 404, not 403: no existence leak.
    assert client.post(f"/notifications/{ids['other_user']}/read").status_code == 404

    result = client.post("/notifications/read-all").json()
    assert result["marked_read"] == 1  # only unread_two was left
    assert all(row["read_at"] is not None for row in client.get("/notifications").json())


def test_viewer_notifications_read_only(estate_id, make_client):
    ids = _create_notifications(estate_id)
    viewer = make_client(VIEWER)
    assert viewer.get("/notifications").json() == []
    assert viewer.post(f"/notifications/{ids['unread_one']}/read").status_code == 403
    assert viewer.post("/notifications/read-all").status_code == 403


# ---------------------------------------------------------------------------
# Audit and activity
# ---------------------------------------------------------------------------


def _create_audit_events(estate_id: str) -> None:
    async def _do(session):
        from app.models import AuditEvent

        eid = uuid.UUID(estate_id)
        session.add_all(
            [
                AuditEvent(
                    estate_id=eid,
                    actor=EXECUTOR,
                    action="create",
                    entity="asset:11111111-1111-1111-1111-111111111111",
                    after={"description": "Demo asset"},
                    timestamp=dt.datetime(2026, 1, 20, 9, 0, tzinfo=dt.UTC),
                ),
                AuditEvent(
                    estate_id=eid,
                    actor=ADMIN,
                    action="update",
                    entity="cost:22222222-2222-2222-2222-222222222222",
                    before={"amount": "10.00"},
                    after={"amount": "12.00"},
                    timestamp=dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.UTC),
                ),
            ]
        )

    asyncio.run(_with_session(_do))


def test_audit_forbidden_to_viewer(estate_id, make_client):
    _create_audit_events(estate_id)
    assert make_client(VIEWER).get("/audit").status_code == 403
    assert make_client(ADMIN).get("/audit").status_code == 200
    assert make_client(EXECUTOR).get("/audit").status_code == 200


def test_audit_filters(estate_id, make_client):
    _create_audit_events(estate_id)
    client = make_client(ADMIN)

    by_entity = client.get("/audit", params={"entity": "asset:"}).json()
    assert len(by_entity) == 1
    assert by_entity[0]["action"] == "create"
    assert by_entity[0]["after"] == {"description": "Demo asset"}

    by_actor = client.get("/audit", params={"actor": ADMIN}).json()
    assert {event["actor"] for event in by_actor} == {ADMIN}

    since = client.get("/audit", params={"since": "2026-03-01T00:00:00Z"}).json()
    assert len(since) == 1
    assert since[0]["entity"].startswith("cost:")


def test_activity_feed_newest_first_paginated(estate_id, make_client):
    _create_audit_events(estate_id)
    client = make_client(VIEWER)  # summarised feed is open to read roles

    feed = client.get("/activity").json()
    assert [item["action"] for item in feed] == ["update", "create"]
    assert "before" not in feed[0] and "after" not in feed[0]

    page_one = client.get("/activity", params={"limit": 1}).json()
    page_two = client.get("/activity", params={"limit": 1, "offset": 1}).json()
    assert len(page_one) == len(page_two) == 1
    assert page_one[0]["id"] != page_two[0]["id"]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _create_searchable_rows(estate_id: str) -> None:
    async def _do(session):
        from app.models import Asset, Contact, ContactCategory, Cost, Document, Task

        eid = uuid.UUID(estate_id)
        session.add_all(
            [
                Contact(
                    estate_id=eid,
                    name="Demo Contact",
                    org="Blue Example Bank",
                    category=ContactCategory.bank,
                ),
                Asset(estate_id=eid, category="vehicle", description="Blue demo car"),
                Task(estate_id=eid, title="Value the blue car"),
                Task(
                    estate_id=eid,
                    title="Private blue note",
                    executor_private=True,
                ),
                Document(estate_id=eid, title="Blue car valuation"),
                Cost(
                    estate_id=eid,
                    description="Blue car recovery fee",
                    category="admin",
                    amount=100,
                    date=dt.date(2026, 2, 1),
                ),
            ]
        )

    asyncio.run(_with_session(_do))


def test_search_hits_across_entity_types(estate_id, make_client):
    _create_searchable_rows(estate_id)
    client = make_client(EXECUTOR)

    hits = client.get("/search", params={"q": "blue"}).json()
    by_type = {}
    for hit in hits:
        by_type.setdefault(hit["type"], []).append(hit["label"])

    assert set(by_type) == {"contact", "asset", "task", "document", "cost"}
    assert by_type["asset"] == ["Blue demo car"]
    assert sorted(by_type["task"]) == ["Private blue note", "Value the blue car"]
    assert by_type["document"] == ["Blue car valuation"]
    assert by_type["cost"] == ["Blue car recovery fee"]
    assert by_type["contact"] == ["Demo Contact (Blue Example Bank)"]

    assert client.get("/search", params={"q": "b"}).status_code == 422


def test_search_respects_viewer_privacy(estate_id, make_client):
    _create_searchable_rows(estate_id)
    viewer = make_client(VIEWER)

    hits = viewer.get("/search", params={"q": "blue"}).json()
    labels = {hit["label"] for hit in hits}
    assert "Private blue note" not in labels
    assert "Value the blue car" in labels


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def test_approval_records_approver_and_audits(estate_id, make_client):
    client = make_client(EXECUTOR)
    entity_ref = f"document:{uuid.uuid4()}"

    response = client.post(
        "/approvals", json={"entity_ref": entity_ref, "draft_kind": "iht400_draft"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["approved_by"] == EXECUTOR
    assert body["approved_at"] is not None
    assert body["draft_kind"] == "iht400_draft"

    listed = client.get("/approvals", params={"entity_ref": entity_ref}).json()
    assert [item["id"] for item in listed] == [body["id"]]
    assert client.get("/approvals", params={"entity_ref": "document:none"}).json() == []

    events = client.get("/audit", params={"entity": entity_ref}).json()
    assert any(event["action"] == "approve" for event in events)


def test_approval_denied_to_viewer(estate_id, make_client):
    viewer = make_client(VIEWER)
    response = viewer.post(
        "/approvals", json={"entity_ref": "document:demo", "draft_kind": "letter"}
    )
    assert response.status_code == 403
