"""Exports API tests: PDF rendering, document rows, audit, approvals, RBAC.

Own fixtures: Postgres ad_test_exports on localhost:5474 (vector extension
plus create_all), the exports and supporting routers mounted onto the app
under test, get_session overridden to the test engine, and local storage
pointed at a per-test tmp directory. No network; nothing is sent anywhere:
exports only create local document rows (guardrail 1).

Fixture data is synthetic (no personal data): a demo estate with one sole
asset, a pecuniary legacy and a single residuary beneficiary.
"""

import asyncio
import datetime as dt
import io
import json
import os
import uuid
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_NAME = "ad_test_exports"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"
ADMIN_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/postgres"

EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"


async def _ensure_database() -> None:
    engine = create_async_engine(
        ADMIN_DB_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await engine.dispose()


async def _prepare_database() -> None:
    from sqlmodel import SQLModel

    import app.models  # noqa: F401

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


def _seed_estate() -> dict[str, str]:
    """A synthetic estate: one sole asset, a pecuniary and a residuary legacy."""

    async def _do(session):
        from app.models import Asset, BeneficiaryLegacy, Contact, Estate
        from app.models.enums import ContactCategory, LegacyType, OwnershipType

        estate = Estate(
            name="Demo Estate (test)",
            date_of_death=dt.date(2026, 1, 15),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.flush()

        beneficiary = Contact(
            estate_id=estate.id,
            name="Residuary Beneficiary One",
            category=ContactCategory.beneficiary,
            created_by="test-fixture",
        )
        pecuniary = Contact(
            estate_id=estate.id,
            name="Pecuniary Beneficiary Two",
            category=ContactCategory.beneficiary,
            created_by="test-fixture",
        )
        session.add(beneficiary)
        session.add(pecuniary)
        await session.flush()

        session.add(
            Asset(
                estate_id=estate.id,
                category="cash",
                description="Demo current account",
                ownership=OwnershipType.sole,
                dod_value=Decimal("100000.00"),
                created_by="test-fixture",
            )
        )
        session.add(
            BeneficiaryLegacy(
                estate_id=estate.id,
                beneficiary_contact_id=pecuniary.id,
                legacy_type=LegacyType.pecuniary,
                amount_or_share=Decimal("5000.00"),
                exempt_or_chargeable="chargeable",
                created_by="test-fixture",
            )
        )
        session.add(
            BeneficiaryLegacy(
                estate_id=estate.id,
                beneficiary_contact_id=beneficiary.id,
                legacy_type=LegacyType.residuary,
                amount_or_share=Decimal("1.0000"),
                exempt_or_chargeable="chargeable",
                created_by="test-fixture",
            )
        )
        await session.flush()
        return {"estate_id": str(estate.id)}

    return asyncio.run(_with_session(_do))


def _seed_assessment(estate_id: str) -> str:
    """A stored engine snapshot (no figure is computed in this test)."""

    async def _do(session):
        from app.models import IhtAssessment

        row = IhtAssessment(
            estate_id=uuid.UUID(estate_id),
            snapshot={
                "inputs": {"net_value": "100000.00"},
                "result": {
                    "jurisdiction_code": "EW",
                    "nrb": "325000.00",
                    "rnrb_max": "175000.00",
                    "rnrb": "0.00",
                    "allowance": "325000.00",
                    "taxable": "0.00",
                    "rate": "0.40",
                    "tax": "0.00",
                    "is_excepted": False,
                    "must_file_iht400": True,
                    "required_schedules": ["IHT406"],
                },
            },
            constants_version="test-constants",
            created_by="test-fixture",
        )
        session.add(row)
        await session.flush()
        return str(row.id)

    return asyncio.run(_with_session(_do))


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
def seeded(clean_db) -> dict[str, str]:
    return _seed_estate()


@pytest.fixture()
def make_client(clean_db, tmp_path):
    os.environ["STORAGE_LOCAL_PATH"] = str(tmp_path / "storage")
    from app.core.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.api import approvals, audit_activity, documents, exports
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with factory() as session:
            yield session

    app = create_app()
    for module in (exports, documents, approvals, audit_activity):
        app.include_router(module.router)
    app.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    yield _make
    asyncio.run(engine.dispose())


def _pdf_text(client, document_id: str) -> tuple[int, str]:
    """Download an export and return (page count, extracted text)."""
    download = client.get(f"/documents/{document_id}/download")
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("application/pdf")
    reader = PdfReader(io.BytesIO(download.content))
    assert len(reader.pages) > 0
    return len(reader.pages), "\n".join(page.extract_text() for page in reader.pages)


def _forms_payload() -> dict:
    """A forms_draft payload in the agent layer's stored shape
    (app.schemas.agents.FormsDraftPayload)."""
    return {
        "forms": [
            {
                "form": "IHT400",
                "title": "Inheritance Tax account",
                "sections": [
                    {
                        "field_ref": "IHT400 box 52",
                        "label": "Bank and building society accounts",
                        "value": "£100,000.00",
                        "source_entity": "asset:demo",
                    },
                    {
                        "field_ref": "IHT400 box 91",
                        "label": "Total estate for IHT",
                        "value": "",
                        "source_entity": "estate:demo",
                    },
                ],
                "gaps": [
                    {
                        "item": "Account balance unconfirmed",
                        "action": "Confirm the account balance with the bank before filing.",
                        "source_entity": "asset:demo",
                    }
                ],
            }
        ],
        "narrative": None,
        "constants_version": "test-constants",
    }


def test_estate_accounts_export_creates_valid_pdf_document_and_audit(seeded, make_client):
    client = make_client(EXECUTOR)

    response = client.post("/exports/estate-accounts")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "export"
    assert body["mime"] == "application/pdf"
    assert body["created_by"] == EXECUTOR
    assert dt.date.today().isoformat() in body["title"]
    assert body["title"].startswith("Estate accounts export")

    pages, pdf_text = _pdf_text(client, body["id"])
    assert pages > 0
    assert "Estate accounts" in pdf_text
    assert "Net estate" in pdf_text
    assert "100,000.00" in pdf_text  # the sole asset, with pence
    assert "5,000.00" in pdf_text  # the pecuniary legacy, with pence
    assert "Residuary Beneficiary One" in pdf_text
    assert "the accounts balance" in pdf_text
    assert "DRAFT for approval, not filed" in pdf_text

    events = client.get("/audit", params={"entity": f"document:{body['id']}"}).json()
    assert any(event["action"] == "create" for event in events)

    listed = client.get("/exports").json()
    assert [doc["id"] for doc in listed] == [body["id"]]


def test_iht_draft_export_renders_sections_and_gaps(seeded, make_client):
    client = make_client(EXECUTOR)

    response = client.post("/exports/iht-draft", json=_forms_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "export"
    assert body["title"].startswith("IHT400 draft export")

    _, pdf_text = _pdf_text(client, body["id"])
    assert "Completed-form draft: IHT400" in pdf_text
    assert "not the official HMRC form" in pdf_text
    assert "Inheritance Tax account" in pdf_text
    assert "IHT400 box 52" in pdf_text
    assert "Bank and building society accounts" in pdf_text
    assert "100,000.00" in pdf_text
    assert "GAP" in pdf_text  # the valueless field
    assert "Gaps: information still needed" in pdf_text
    assert "Confirm the account balance with the bank before filing." in pdf_text
    assert "DRAFT for approval, not filed" in pdf_text


def test_iht_draft_export_uses_latest_approved_agent_draft(seeded, make_client):
    """With no request body, the export reads the agent draft store:
    a document of type "draft" wrapping {"draft_kind", "payload"} plus an
    approved Approval row of kind "iht400_draft"."""
    client = make_client(EXECUTOR)

    # No approved draft and no body: 404 with guidance.
    missing = client.post("/exports/iht-draft")
    assert missing.status_code == 404
    assert "approved forms draft" in missing.json()["detail"]

    # Store a draft the way the forms_draft agent does.
    envelope = {"draft_kind": "iht400_draft", "payload": _forms_payload()}
    upload = client.post(
        "/documents",
        data={"title": "IHT400 draft", "type": "draft"},
        files={
            "file": ("draft.json", json.dumps(envelope).encode(), "application/json")
        },
    )
    assert upload.status_code == 201, upload.text
    draft_id = upload.json()["id"]

    # Pending (unapproved) drafts are not exported.
    still_missing = client.post("/exports/iht-draft")
    assert still_missing.status_code == 404

    approved = client.post(
        "/approvals",
        json={"entity_ref": f"document:{draft_id}", "draft_kind": "iht400_draft"},
    )
    assert approved.status_code == 201, approved.text

    response = client.post("/exports/iht-draft")
    assert response.status_code == 201, response.text
    _, pdf_text = _pdf_text(client, response.json()["id"])
    assert "IHT400 box 52" in pdf_text
    assert "100,000.00" in pdf_text


def test_clearance_draft_requires_an_assessment_then_exports(seeded, make_client):
    client = make_client(EXECUTOR)

    missing = client.post("/exports/clearance-draft")
    assert missing.status_code == 404
    assert "recompute" in missing.json()["detail"]

    _seed_assessment(seeded["estate_id"])
    response = client.post("/exports/clearance-draft")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"].startswith("IHT30 clearance draft export")

    _, pdf_text = _pdf_text(client, body["id"])
    assert "IHT30" in pdf_text
    assert "Estate facts" in pdf_text
    assert "15 January 2026" in pdf_text  # date of death from the fixture
    assert "325,000.00" in pdf_text  # allowance from the stored snapshot
    assert "Declaration" in pdf_text
    assert "Date of grant is not recorded." in pdf_text  # gap list
    assert "DRAFT for approval, not filed" in pdf_text


def _upload_letter_draft(client) -> str:
    letter = {
        "recipient_name": "Demo Bank plc",
        "recipient_address": ["1 Test Street", "Testtown", "TE5 7ED"],
        "subject": "Notification of death: account 00000000",
        "body": (
            "We write as the executors of the estate to notify you of the "
            "account holder's death.\n\nPlease confirm the balance at the "
            "date of death of £100,000.00 and freeze the account."
        ),
        "sender_name": "Executor One",
        "sender_role": "Executor of the estate",
    }
    response = client.post(
        "/documents",
        data={"title": "Draft letter to Demo Bank", "type": "letter_draft"},
        files={
            "file": (
                "letter.json",
                json.dumps(letter).encode(),
                "application/json",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_letter_export_409_when_unapproved_then_exports_once_approved(seeded, make_client):
    client = make_client(EXECUTOR)
    draft_id = _upload_letter_draft(client)

    blocked = client.post(f"/exports/letter/{draft_id}")
    assert blocked.status_code == 409
    assert "has not been approved" in blocked.json()["detail"]

    approved = client.post(
        "/approvals",
        json={"entity_ref": f"document:{draft_id}", "draft_kind": "notification_letter"},
    )
    assert approved.status_code == 201, approved.text

    response = client.post(f"/exports/letter/{draft_id}")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["type"] == "export"
    assert body["title"].startswith("Notification letter export")
    assert any(link.get("entity_id") == draft_id for link in body["links"])

    _, pdf_text = _pdf_text(client, body["id"])
    assert "Demo Bank plc" in pdf_text
    assert "Notification of death: account 00000000" in pdf_text
    assert "100,000.00" in pdf_text
    assert "Executor One" in pdf_text
    # An approved letter carries no draft watermark.
    assert "DRAFT for approval, not filed" not in pdf_text


def test_letter_export_missing_draft_404(seeded, make_client):
    client = make_client(EXECUTOR)
    assert client.post(f"/exports/letter/{uuid.uuid4()}").status_code == 404


def test_viewer_403_on_all_export_posts(seeded, make_client):
    executor = make_client(EXECUTOR)
    draft_id = _upload_letter_draft(executor)

    viewer = make_client(VIEWER)
    assert viewer.post("/exports/estate-accounts").status_code == 403
    assert viewer.post("/exports/iht-draft", json=_forms_payload()).status_code == 403
    assert viewer.post("/exports/clearance-draft").status_code == 403
    assert viewer.post(f"/exports/letter/{draft_id}").status_code == 403

    # Viewer-safe reads: the export list and the documents module.
    assert viewer.get("/exports").status_code == 200
    assert viewer.get("/documents").status_code == 200
