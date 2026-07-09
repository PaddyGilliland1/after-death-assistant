"""Documents API tests: upload/download round trip, access_roles
enforcement, viewer executor_private exclusion, versions, soft delete.

Own fixtures: Postgres ad_test_collab on localhost:5474, routers mounted
onto the app under test, get_session overridden to the test engine, and
local storage pointed at a per-test tmp directory.
"""

import asyncio
import datetime as dt
import os

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


def _create_estate() -> str:
    async def _do(session):
        from app.models import Estate

        estate = Estate(
            name="Demo Estate (test)",
            date_of_death=dt.date(2026, 1, 15),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.flush()
        return str(estate.id)

    return asyncio.run(_with_session(_do))


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
def estate_id(clean_db) -> str:
    return _create_estate()


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


def _upload(client, title="Demo valuation", content=b"demo-bytes-1", **fields):
    data = {"title": title, "type": "valuation", "access_roles": ""}
    data.update({key: str(value) for key, value in fields.items()})
    return client.post(
        "/documents",
        data=data,
        files={"file": (f"{title}.pdf", content, "application/pdf")},
    )


def test_upload_download_round_trip_and_audit(estate_id, make_client):
    client = make_client(EXECUTOR)
    content = b"%PDF-1.4 synthetic demo content"

    response = _upload(client, content=content)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Demo valuation"
    assert body["version"] == 1
    assert body["mime"] == "application/pdf"
    assert body["created_by"] == EXECUTOR

    download = client.get(f"/documents/{body['id']}/download")
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"].startswith("application/pdf")
    assert "attachment" in download.headers["content-disposition"]

    audit = client.get("/audit", params={"entity": "document:"})
    assert audit.status_code == 200
    events = audit.json()
    assert any(
        event["action"] == "create" and event["entity"] == f"document:{body['id']}"
        for event in events
    )


def test_viewer_cannot_upload(estate_id, make_client):
    response = _upload(make_client(VIEWER))
    assert response.status_code == 403


def test_unknown_access_role_rejected(estate_id, make_client):
    response = _upload(make_client(EXECUTOR), access_roles="banana")
    assert response.status_code == 422


def test_access_roles_enforced_against_caller_role(estate_id, make_client):
    executor = make_client(EXECUTOR)
    viewer = make_client(VIEWER)

    restricted = _upload(
        executor, title="Executor only paper", access_roles="executor,admin"
    ).json()
    open_doc = _upload(executor, title="Open letter").json()

    executor_titles = {doc["title"] for doc in executor.get("/documents").json()}
    assert executor_titles == {"Executor only paper", "Open letter"}

    viewer_titles = {doc["title"] for doc in viewer.get("/documents").json()}
    assert viewer_titles == {"Open letter"}

    # Hidden documents 404 rather than 403 (no existence leak).
    assert viewer.get(f"/documents/{restricted['id']}").status_code == 404
    assert viewer.get(f"/documents/{restricted['id']}/download").status_code == 404
    assert executor.get(f"/documents/{restricted['id']}").status_code == 200
    assert viewer.get(f"/documents/{open_doc['id']}").status_code == 200


def test_viewer_never_sees_executor_private(estate_id, make_client):
    executor = make_client(EXECUTOR)
    viewer = make_client(VIEWER)

    private = _upload(executor, title="Private note", executor_private="true").json()

    assert private["executor_private"] is True
    assert {doc["title"] for doc in executor.get("/documents").json()} == {"Private note"}
    assert viewer.get("/documents").json() == []
    assert viewer.get(f"/documents/{private['id']}").status_code == 404


def test_new_version_replaces_file_and_keeps_history(estate_id, make_client):
    client = make_client(EXECUTOR)
    first = _upload(client, content=b"version one").json()

    response = client.post(
        f"/documents/{first['id']}/versions",
        files={"file": ("updated.pdf", b"version two", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["version"] == 2
    assert any(link.get("kind") == "previous_version" for link in second["links"])

    download = client.get(f"/documents/{first['id']}/download")
    assert download.content == b"version two"

    viewer = make_client(VIEWER)
    assert viewer.post(
        f"/documents/{first['id']}/versions",
        files={"file": ("x.pdf", b"nope", "application/pdf")},
    ).status_code == 403


def test_soft_delete_archives_and_hides(estate_id, make_client):
    client = make_client(EXECUTOR)
    doc = _upload(client, title="To be archived").json()

    response = client.request("DELETE", f"/documents/{doc['id']}", json={"reason": "superseded"})
    assert response.status_code == 204

    assert client.get("/documents").json() == []
    assert client.get(f"/documents/{doc['id']}").status_code == 404

    events = client.get("/audit", params={"entity": f"document:{doc['id']}"}).json()
    assert any(event["action"] == "archive" for event in events)

    viewer = make_client(VIEWER)
    assert viewer.delete(f"/documents/{doc['id']}").status_code == 403


def test_documents_require_an_estate(clean_db, make_client):
    client = make_client(EXECUTOR)
    assert _upload(client).status_code == 404
    assert client.get("/documents").status_code == 404
