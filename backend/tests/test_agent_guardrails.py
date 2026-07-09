"""Guardrail contract for the agent layer (AGENT_DESIGN.md section 4).

These assertions are part of the definition of done for every phase:

1. No send/file/pay reachability: every tool registered across all five
   graphs is on the read/draft allowlist, and no agent module or tool
   function imports or references an email, filing or payment capability
   (smtplib, sendmail, resend, stripe, or any HTTP POST client call).
2. Every draft path creates an approval-pending record: draft-form,
   draft-letter, suggest-tasks and the narration each leave a row in
   approval with approved_by empty, pointing at a stored draft document.
3. Domain contract: claims_rnrb=True forces must_file_iht400=True and the
   narration input always carries that flag; the narration validator
   rejects any output containing a figure absent from the snapshot.
"""

import asyncio
import datetime as dt
import inspect
import re
import uuid
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

import app.models as models
from app.agents import llm as llm_module
from app.agents import tools
from app.agents.graphs import GRAPH_MODULES
from app.agents.graphs.iht_narration import (
    allowed_figures,
    build_narration_input,
    extract_numbers,
    validate_narration,
)
from app.api import agent_drafts as agent_drafts_api
from app.db import get_session
from app.domain.iht_engine import Estate as EngineEstate
from app.domain.iht_engine import assess
from app.domain.jurisdiction.england_wales import ENGLAND_WALES
from app.models import Approval, Contact, Document, Estate
from app.services.reevaluation import run_recompute

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_agents"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

EXECUTOR = "executor@test.local"

AGENTS_DIR = Path(agent_drafts_api.__file__).resolve().parent.parent / "agents"

# ---------------------------------------------------------------------------
# 1. No send/file/pay reachability
# ---------------------------------------------------------------------------

# The complete allowlist. A new tool must be added HERE (and reviewed
# against design rule 2) before any graph can use it.
ALLOWED_TOOL_NAMES = {
    "read_estate",
    "read_latest_assessment",
    "read_assets",
    "read_liabilities",
    "read_contacts",
    "read_contact",
    "read_tasks",
    "read_process_steps",
    "read_deadlines",
    "read_knowledge_docs",
    "search_guidance",
    "diff_registry_source",
    "load_source_registry",
    "store_draft_document",
    "read_draft_payload",
    "create_pending_approval",
    "ingest_registry_source",
}

# Tokens that would indicate a send, file or payment capability.
FORBIDDEN_TOKENS = (
    "smtplib",
    "sendmail",
    "send_email",
    "send_mail",
    "resend",
    "stripe",
    "paypal",
    "gocardless",
    "twilio",
    "httpx.post",
    "requests.post",
    "client.submit",
)

# Outbound HTTP mutations (.post/.put/.delete on any client object). The
# only permitted ".post(" in the layer is FastAPI's @router.post route
# registration, which is inbound, not outbound.
_OUTBOUND_HTTP_RE = re.compile(r"(?<!router)\.(post|put|patch|delete)\(")


def _forbidden_hits(source: str) -> list[str]:
    hits = [token for token in FORBIDDEN_TOKENS if token in source]
    hits.extend(match.group(0) for match in _OUTBOUND_HTTP_RE.finditer(source))
    return hits


def test_every_registered_tool_is_on_the_allowlist():
    assert set(tools.ALL_TOOLS) == ALLOWED_TOOL_NAMES


def test_every_tool_capability_is_read_or_draft_only():
    for spec in tools.ALL_TOOLS.values():
        assert spec.capability in tools.ALLOWED_CAPABILITIES, spec.name


def test_all_five_graphs_use_only_registered_tools():
    assert set(tools.GRAPH_TOOLSETS) == set(GRAPH_MODULES) == {
        "knowledge_ingest",
        "iht_narration",
        "forms_draft",
        "guidance_qa",
        "next_actions",
    }
    for graph, toolset in tools.GRAPH_TOOLSETS.items():
        unknown = set(toolset) - set(tools.ALL_TOOLS)
        assert not unknown, f"{graph} lists unregistered tools: {unknown}"
        for name in toolset:
            assert name in ALLOWED_TOOL_NAMES, f"{graph} -> {name}"


def _agent_source_files() -> list[Path]:
    files = sorted(AGENTS_DIR.rglob("*.py"))
    files.append(Path(agent_drafts_api.__file__).resolve())
    assert files, "agent sources not found"
    return files


def test_no_agent_module_references_send_file_or_pay():
    for path in _agent_source_files():
        hits = _forbidden_hits(path.read_text(encoding="utf-8"))
        assert not hits, f"{path.name} references {hits!r}"


def test_no_tool_function_imports_or_references_send_file_or_pay():
    for spec in tools.ALL_TOOLS.values():
        hits = _forbidden_hits(inspect.getsource(spec.fn))
        assert not hits, f"tool {spec.name} references {hits!r}"
        module = inspect.getmodule(spec.fn)
        for name in ("smtplib", "resend", "stripe"):
            assert name not in vars(module), f"tool module {module.__name__} imports {name}"


# ---------------------------------------------------------------------------
# 3a. Narration validator: rejects figures outside the snapshot set
# ---------------------------------------------------------------------------

_SAMPLE_SNAPSHOT = {
    "inputs": {
        "net_value": "960000.00",
        "gross_value": "960000.00",
        "tnrb_pct": "1.0",
        "trnrb_pct": "1.0",
        "residence_to_descendants_value": "340000.00",
        "exempt_transfers": "0.00",
    },
    "result": {
        "nrb": "650000.00",
        "rnrb_max": "350000.00",
        "rnrb": "340000.00",
        "allowance": "990000.00",
        "taxable": "0.00",
        "rate": "0.4",
        "tax": "0.00",
        "is_excepted": False,
        "must_file_iht400": True,
        "required_schedules": ["IHT402", "IHT435"],
    },
}


def test_validator_accepts_only_snapshot_figures():
    allowed = allowed_figures(_SAMPLE_SNAPSHOT)
    good = (
        "The allowance is £990,000.00 against a net estate of £960,000.00, "
        "taxed at 40% above the threshold, so the tax is £0.00 [1][2]."
    )
    assert validate_narration(good, allowed) == []


def test_validator_rejects_a_figure_not_in_the_snapshot():
    allowed = allowed_figures(_SAMPLE_SNAPSHOT)
    rogue = "The inheritance tax due is £123,456.78."
    assert validate_narration(rogue, allowed) == ["123456.78"]


def test_validator_normalises_formatting_not_meaning():
    allowed = allowed_figures(_SAMPLE_SNAPSHOT)
    # Same figure, different formatting: commas, currency, trailing zeros.
    assert validate_narration("nil rate band of 650000", allowed) == []
    assert validate_narration("nil rate band of £650,000.00", allowed) == []
    # A near miss is still rogue.
    assert validate_narration("nil rate band of £650,001", allowed) == ["650001"]


def test_number_extraction_ignores_citations_dates_and_form_codes():
    assert extract_numbers("See IHT435 and IHT402 [3], fetched 2026-07-06.") == []
    assert extract_numbers("Tax of £1,234.50 applies [1].") == ["1234.5"]


# ---------------------------------------------------------------------------
# 3b. claims_rnrb=True estates always show must_file_iht400
# ---------------------------------------------------------------------------


def _engine_estate_with_rnrb_claim(net_value: str) -> EngineEstate:
    """An estate whose facts would otherwise allow an excepted route."""
    return EngineEstate(
        net_value=Decimal(net_value),
        gross_value=Decimal(net_value),
        residence_to_descendants_value=Decimal("100000"),
        claims_rnrb=True,
        gifts_in_seven_years=Decimal("0"),
        trust_assets_value=Decimal("0"),
        trust_count=0,
        foreign_assets_value=Decimal("0"),
        gifts_with_reservation=False,
    )


@pytest.mark.parametrize("net_value", ["100000", "300000", "960000"])
def test_claims_rnrb_forces_iht400_in_engine_and_narration_input(net_value):
    assessment = assess(_engine_estate_with_rnrb_claim(net_value), ENGLAND_WALES)
    assert assessment.must_file_iht400 is True

    snapshot = {"inputs": {}, "result": assessment.model_dump(mode="json")}
    narration_input = build_narration_input(snapshot)
    assert narration_input["must_file_iht400"] == "True"


def test_narration_input_always_carries_the_filing_flag():
    # Even for an excepted estate the flag is present (and honest).
    estate = EngineEstate(
        net_value=Decimal("100000"),
        gross_value=Decimal("100000"),
        claims_rnrb=False,
        gifts_in_seven_years=Decimal("0"),
        trust_assets_value=Decimal("0"),
        trust_count=0,
        foreign_assets_value=Decimal("0"),
        gifts_with_reservation=False,
    )
    assessment = assess(estate, ENGLAND_WALES)
    snapshot = {"inputs": {}, "result": assessment.model_dump(mode="json")}
    assert "must_file_iht400" in build_narration_input(snapshot)
    assert build_narration_input(snapshot)["must_file_iht400"] == "False"


# ---------------------------------------------------------------------------
# 2. Every draft path creates an approval-pending record (DB-backed)
# ---------------------------------------------------------------------------


def _prepare_database() -> None:
    async def _run() -> None:
        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()
        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await connection.run_sync(SQLModel.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.fixture(scope="module", autouse=True)
def _database() -> None:
    _prepare_database()


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    tables = ", ".join(f'"{table.name}"' for table in SQLModel.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def client(session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    from app.core.config import get_settings

    get_settings.cache_clear()

    application = FastAPI()
    application.include_router(agent_drafts_api.router)

    async def _override_session():
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_session

    test_client = TestClient(application)
    test_client.headers["X-Dev-User"] = EXECUTOR
    return test_client


@pytest.fixture
async def seeded_estate(session_factory) -> dict:
    async with session_factory() as session:
        estate = Estate(
            name="Guardrail estate",
            date_of_death=dt.date(2026, 7, 3),
            tnrb_pct=Decimal("1"),
            trnrb_pct=Decimal("1"),
            residence_to_descendants_value=Decimal("340000"),
            claims_rnrb=True,
            gifts_with_reservation=False,
            foreign_assets_value=Decimal("0"),
            trust_property_value=Decimal("0"),
            specified_transfers_value=Decimal("0"),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.flush()
        contact = Contact(
            estate_id=estate.id,
            name="Example Institution",
            references=["REF-0001"],
            notify_required=True,
            created_by="test-fixture",
        )
        session.add(contact)
        await session.flush()
        await run_recompute(session, estate, "test-fixture")
        await session.commit()
        return {"estate_id": estate.id, "contact_id": contact.id}


async def _assert_single_pending_approval(
    session_factory, approval_id: str, draft_id: str, draft_kind: str
) -> None:
    async with session_factory() as session:
        approval = await session.get(Approval, uuid.UUID(approval_id))
        assert approval is not None, "the draft did not create an approval row"
        assert approval.approved_by is None, "the approval must be pending, not approved"
        assert approval.approved_at is None
        assert approval.draft_kind == draft_kind
        assert approval.entity_ref == f"document:{draft_id}"
        document = await session.get(Document, uuid.UUID(draft_id))
        assert document is not None, "the draft artefact was not stored"
        assert document.type == "draft"
        pending = (
            (
                await session.execute(
                    select(Approval).where(Approval.approved_by.is_(None))
                )
            )
            .scalars()
            .all()
        )
        assert len(pending) == 1


async def test_draft_form_path_creates_pending_approval(
    session_factory, seeded_estate, client, monkeypatch
):
    monkeypatch.setattr(llm_module, "call_llm", lambda s, u, settings=None: "Cover note.")
    body = client.post("/agents/draft-form", json={}).json()
    await _assert_single_pending_approval(
        session_factory, body["approval_id"], body["draft_id"], "iht400_draft"
    )


async def test_suggest_tasks_path_creates_pending_approval(
    session_factory, seeded_estate, client
):
    body = client.post("/agents/suggest-tasks").json()
    await _assert_single_pending_approval(
        session_factory, body["approval_id"], body["draft_id"], "task_suggestions"
    )


async def test_draft_letter_path_creates_pending_approval(
    session_factory, seeded_estate, client, monkeypatch
):
    monkeypatch.setattr(
        llm_module,
        "call_llm",
        lambda s, u, settings=None: "DRAFT letter asking for date of death balances.",
    )
    body = client.post(
        "/agents/draft-letter",
        json={"contact_id": str(seeded_estate["contact_id"]), "purpose": "notify"},
    ).json()
    await _assert_single_pending_approval(
        session_factory, body["approval_id"], body["draft_id"], "notification_letter"
    )


async def test_narration_path_creates_pending_approval(
    session_factory, seeded_estate, client, monkeypatch
):
    monkeypatch.setattr(
        llm_module,
        "call_llm",
        lambda s, u, settings=None: "No inheritance tax is due on this estate.",
    )
    body = client.post("/agents/draft-narration").json()
    await _assert_single_pending_approval(
        session_factory, body["approval_id"], body["draft_id"], "iht_narration"
    )
    assert body["validated"] is True


async def test_artefacts_stay_drafts_until_a_person_approves(
    session_factory, seeded_estate, client
):
    body = client.post("/agents/suggest-tasks").json()
    approve = client.post(f"/agents/drafts/{body['approval_id']}/approve", json={})
    assert approve.status_code == 200
    async with session_factory() as session:
        approval = await session.get(Approval, uuid.UUID(body["approval_id"]))
        assert approval.approved_by == EXECUTOR
        assert approval.approved_at is not None
