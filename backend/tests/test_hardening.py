"""P3 hardening tests: view auditing (RQ-3), UK GDPR export and erasure
(RQ-1), pg_dump backups (RQ-9) and the production ASGI wrapper.

Own fixtures: Postgres ad_test_hardening on localhost:5474 (created on
first run), routers mounted via the real app factory, get_session
overridden to the test engine, local storage in a per-test tmp directory.

The backup round trip needs the PostgreSQL client tools: if pg_dump is not
on PATH the backup test SKIPS with a clear reason (documented in
docs/DEPLOY.md) rather than failing on machines without postgresql-client.
"""

import asyncio
import datetime as dt
import os
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_NAME = "ad_test_hardening"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"
MAINTENANCE_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/postgres"

EXECUTOR = "executor@test.local"
ADMIN = "admin@test.local"
VIEWER = "viewer@test.local"

ESTATE_NAME = "Scratch Estate (hardening)"


async def _ensure_database() -> None:
    """Create ad_test_hardening if missing; skip the module if Postgres
    on 5474 is not reachable at all."""
    engine = create_async_engine(
        MAINTENANCE_DB_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except OSError as exc:  # connection refused: dev DB not running
        pytest.skip(f"Postgres on localhost:5474 is not reachable: {exc}")
    finally:
        await engine.dispose()


async def _prepare_database() -> None:
    from sqlmodel import SQLModel

    import app.models  # noqa: F401 - registers every table on the metadata

    await _ensure_database()
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


def _seed_estate() -> str:
    """A scratch estate with a contact, an asset and a task, so the export
    and erasure tests exercise several tables."""

    async def _do(session):
        from decimal import Decimal

        from app.models import Asset, Contact, Estate, Task

        estate = Estate(
            name=ESTATE_NAME,
            date_of_death=dt.date(2026, 1, 15),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.flush()
        session.add(
            Contact(
                estate_id=estate.id,
                kind="organisation",
                name="Demo Bank (test)",
                created_by="test-fixture",
            )
        )
        session.add(
            Asset(
                estate_id=estate.id,
                category="cash",
                description="Demo account (test)",
                dod_value=Decimal("1000.00"),
                created_by="test-fixture",
            )
        )
        session.add(
            Task(
                estate_id=estate.id,
                title="Demo task (test)",
                created_by="test-fixture",
            )
        )
        return str(estate.id)

    return asyncio.run(_with_session(_do))


def _audit_rows(action: str) -> list[tuple[str, str]]:
    """(actor, entity) tuples for audit events with the given action."""

    async def _do(session):
        from sqlalchemy import select

        from app.models import AuditEvent

        result = await session.execute(
            select(AuditEvent.actor, AuditEvent.entity).where(AuditEvent.action == action)
        )
        return [tuple(row) for row in result.all()]

    return asyncio.run(_with_session(_do))


def _count_rows_for_estate(estate_id: str) -> dict[str, int]:
    """Row counts per estate-scoped table plus the estate row itself."""

    async def _do(session):
        from sqlalchemy import func, select
        from sqlmodel import SQLModel

        from app.models import Estate

        counts: dict[str, int] = {}
        for table in SQLModel.metadata.sorted_tables:
            if table.name == "estate" or "estate_id" not in table.c:
                continue
            count = (
                await session.execute(
                    select(func.count()).select_from(table).where(table.c.estate_id == estate_id)
                )
            ).scalar_one()
            if count:
                counts[table.name] = count
        estate_count = (
            await session.execute(
                select(func.count()).select_from(Estate).where(Estate.id == estate_id)
            )
        ).scalar_one()
        if estate_count:
            counts["estate"] = estate_count
        return counts

    return asyncio.run(_with_session(_do))


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
def estate_id(clean_db) -> str:
    return _seed_estate()


@pytest.fixture()
def storage_path(tmp_path):
    path = tmp_path / "storage"
    os.environ["STORAGE_LOCAL_PATH"] = str(path)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield path
    os.environ.pop("STORAGE_LOCAL_PATH", None)
    get_settings.cache_clear()


@pytest.fixture()
def make_client(clean_db, storage_path):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    yield _make
    asyncio.run(engine.dispose())


def _upload_document(client, title="Demo valuation", executor_private=False):
    return client.post(
        "/documents",
        data={
            "title": title,
            "type": "valuation",
            "access_roles": "",
            "executor_private": str(executor_private).lower(),
        },
        files={"file": (f"{title}.pdf", b"demo-bytes", "application/pdf")},
    )


# ---------------------------------------------------------------------------
# View auditing (VALIDATION.md RQ-3)
# ---------------------------------------------------------------------------


class TestViewAuditing:
    def test_download_emits_download_audit_event(self, estate_id, make_client):
        client = make_client(EXECUTOR)
        document_id = _upload_document(client).json()["id"]

        response = client.get(f"/documents/{document_id}/download")
        assert response.status_code == 200
        assert response.content == b"demo-bytes"

        rows = _audit_rows("download")
        assert rows == [(EXECUTOR, f"document:{document_id}")]

    def test_private_metadata_read_emits_view_private(self, estate_id, make_client):
        client = make_client(EXECUTOR)
        document_id = _upload_document(client, executor_private=True).json()["id"]

        response = client.get(f"/documents/{document_id}")
        assert response.status_code == 200

        rows = _audit_rows("view_private")
        assert rows == [(EXECUTOR, f"document:{document_id}")]

    def test_public_metadata_read_is_not_audited(self, estate_id, make_client):
        client = make_client(EXECUTOR)
        document_id = _upload_document(client, executor_private=False).json()["id"]

        assert client.get(f"/documents/{document_id}").status_code == 200
        assert _audit_rows("view_private") == []


# ---------------------------------------------------------------------------
# UK GDPR export (VALIDATION.md RQ-1)
# ---------------------------------------------------------------------------


class TestEstateExport:
    def test_export_covers_every_estate_scoped_table(self, estate_id, make_client):
        from sqlmodel import SQLModel

        client = make_client(EXECUTOR)
        _upload_document(client)  # add a document + its audit rows

        response = client.get("/estate/export")
        assert response.status_code == 200
        payload = response.json()

        assert payload["format"] == "ad-assistant-estate-export"
        assert payload["exported_by"] == EXECUTOR
        assert payload["estate"]["id"] == estate_id
        assert payload["estate"]["name"] == ESTATE_NAME

        expected_tables = {
            table.name
            for table in SQLModel.metadata.sorted_tables
            if table.name != "estate" and "estate_id" in table.c
        }
        assert set(payload["tables"].keys()) == expected_tables

        assert len(payload["tables"]["contact"]) == 1
        assert payload["tables"]["contact"][0]["name"] == "Demo Bank (test)"
        assert len(payload["tables"]["asset"]) == 1
        assert payload["tables"]["asset"][0]["dod_value"] == "1000.00"
        assert len(payload["tables"]["task"]) == 1
        assert len(payload["tables"]["document"]) == 1
        assert len(payload["tables"]["audit_event"]) >= 1

    def test_export_is_audited(self, estate_id, make_client):
        client = make_client(ADMIN)
        assert client.get("/estate/export").status_code == 200
        rows = _audit_rows("export")
        assert rows == [(ADMIN, f"estate:{estate_id}")]

    def test_export_refused_for_viewer(self, estate_id, make_client):
        assert make_client(VIEWER).get("/estate/export").status_code == 403


# ---------------------------------------------------------------------------
# UK GDPR erasure (VALIDATION.md RQ-1): the ONE hard-delete endpoint
# ---------------------------------------------------------------------------


class TestEstateErasure:
    def test_wrong_confirm_string_refused_and_nothing_deleted(self, estate_id, make_client):
        client = make_client(ADMIN)
        response = client.post("/estate/erase", json={"confirm": "Wrong Name"})
        assert response.status_code == 400
        assert "Nothing has been deleted" in response.json()["detail"]
        assert _count_rows_for_estate(estate_id).get("estate") == 1
        assert _count_rows_for_estate(estate_id).get("contact") == 1

    def test_non_admin_roles_refused(self, estate_id, make_client):
        for user in (EXECUTOR, VIEWER):
            response = make_client(user).post("/estate/erase", json={"confirm": ESTATE_NAME})
            assert response.status_code == 403, user
        assert _count_rows_for_estate(estate_id).get("estate") == 1

    def test_erase_hard_deletes_every_estate_row(self, estate_id, make_client, storage_path):
        client = make_client(ADMIN)
        _upload_document(client)  # a stored file that must also disappear
        assert any(storage_path.iterdir())

        response = client.post("/estate/erase", json={"confirm": ESTATE_NAME})
        assert response.status_code == 200
        payload = response.json()
        assert payload["erased_estate_id"] == estate_id
        assert payload["rows_deleted"]["estate"] == 1
        assert payload["rows_deleted"]["contact"] == 1
        assert payload["rows_deleted"]["document"] == 1

        # Hard delete: no row for the estate survives in any table.
        assert _count_rows_for_estate(estate_id) == {}
        # The stored document file is gone too (backups excluded).
        leftovers = [
            path
            for path in storage_path.rglob("*")
            if path.is_file() and "backups" not in path.parts
        ]
        assert leftovers == []


# ---------------------------------------------------------------------------
# Backups (VALIDATION.md RQ-9)
# ---------------------------------------------------------------------------


class TestBackups:
    @pytest.mark.skipif(
        shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
        reason=(
            "pg_dump/pg_restore not on PATH; install postgresql-client-16 to run "
            "the backup round trip (documented in docs/DEPLOY.md)"
        ),
    )
    def test_create_list_verify_round_trip(self, clean_db, tmp_path):
        from app.core.config import Settings
        from app.services.backup import create_backup, list_backups, verify_backup

        settings = Settings(DATABASE_URL=TEST_DB_URL, STORAGE_LOCAL_PATH=str(tmp_path))

        info = create_backup(settings)
        assert info.file.is_file()
        assert info.file.parent == tmp_path / "backups"
        assert info.manifest is not None and info.manifest.is_file()
        assert info.sha256 and len(info.sha256) == 64

        listed = list_backups(settings)
        assert [item.file for item in listed] == [info.file]
        assert listed[0].sha256 == info.sha256

        result = verify_backup(info.file.name, settings)
        assert result.sha256_ok, result.detail
        assert result.restore_list_ok, result.detail
        assert result.ok

        # Corruption is caught: flip bytes at the end of the dump.
        data = bytearray(info.file.read_bytes())
        data[-8:] = b"XXXXXXXX"
        info.file.write_bytes(bytes(data))
        tampered = verify_backup(info.file.name, settings)
        assert not tampered.sha256_ok
        assert not tampered.ok

    def test_backup_refuses_non_postgres_url(self, tmp_path):
        from app.core.config import Settings
        from app.services.backup import BackupError, create_backup

        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            STORAGE_LOCAL_PATH=str(tmp_path),
        )
        with pytest.raises(BackupError):
            create_backup(settings)


# ---------------------------------------------------------------------------
# Production ASGI wrapper (app.prod)
# ---------------------------------------------------------------------------


@pytest.fixture()
def frontend_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>AD Assistant</title><div id='root'></div>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.css").write_text("body{margin:0}", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    return dist


class TestProdApp:
    def test_serves_spa_with_index_fallback(self, frontend_dist):
        from fastapi.testclient import TestClient

        from app.prod import create_app

        client = TestClient(create_app())

        root = client.get("/")
        assert root.status_code == 200
        assert "AD Assistant" in root.text

        asset = client.get("/assets/app.css")
        assert asset.status_code == 200
        assert asset.text == "body{margin:0}"

        # Client-side routes fall back to index.html on a full page load.
        fallback = client.get("/assets-register")
        assert fallback.status_code == 200
        assert "AD Assistant" in fallback.text

        # API routes still win over the SPA mount.
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

    def test_api_only_when_dist_not_set(self, monkeypatch):
        from fastapi.testclient import TestClient

        from app.prod import create_app

        monkeypatch.delenv("FRONTEND_DIST", raising=False)
        client = TestClient(create_app())
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 404

    def test_warns_on_dev_auth_in_prod_like_env(self, monkeypatch, caplog):
        from app.prod import create_app

        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        monkeypatch.delenv("FRONTEND_DIST", raising=False)
        with caplog.at_level("WARNING", logger="app.prod"):
            create_app()  # conftest sets DEV_AUTH=true
        assert "DEV_AUTH is true" in caplog.text
        assert "Set DEV_AUTH=false in production" in caplog.text

    def test_no_warning_outside_prod_like_env(self, monkeypatch, caplog):
        from app.prod import create_app

        for marker in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_ENVIRONMENT_NAME",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        ):
            monkeypatch.delenv(marker, raising=False)
        monkeypatch.delenv("FRONTEND_DIST", raising=False)
        with caplog.at_level("WARNING", logger="app.prod"):
            create_app()
        assert "DEV_AUTH is true" not in caplog.text
