"""End-to-end tests for the P3 agent layer (five graphs + /agents router).

Own fixtures: Postgres ad_test_agents on localhost:5474 (created if
missing) with the pgvector extension and SQLModel create_all; the agents
router is mounted on a fresh app with get_session overridden. NO network
and NO model calls: the LLM seam (app.agents.llm.call_llm) and the
knowledge router's _call_llm seam are monkeypatched, and the ingest graph
receives a fake fetcher.
"""

import asyncio
import datetime as dt
import uuid
from decimal import Decimal

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
from app.agents.graphs.guidance_qa import run_guidance_qa
from app.agents.graphs.knowledge_ingest import run_knowledge_ingest
from app.agents.tools import AgentContext
from app.api import agent_drafts as agent_drafts_api
from app.api import knowledge as knowledge_api
from app.db import get_session
from app.ingest.fetcher import build_fetch_result
from app.models import (
    Approval,
    Asset,
    AuditEvent,
    Contact,
    Deadline,
    Document,
    Estate,
    KnowledgeChunk,
    KnowledgeDoc,
    ProcessStep,
    Task,
)
from app.services.reevaluation import constants_version, run_recompute

assert models is not None  # imported for its metadata side effect

TEST_DB_NAME = "ad_test_agents"
ADMIN_DSN = "postgresql://postgres:postgres@localhost:5474/postgres"
TEST_DB_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5474/{TEST_DB_NAME}"

ADMIN = "admin@test.local"
EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"

EXPECTED_CONSTANTS_VERSION = constants_version()

FAKE_HTML_V1 = b"""<html><body>
<h1>Inheritance Tax account IHT400</h1>
<p>Use form IHT400 if the estate does not qualify as an excepted estate.</p>
</body></html>"""

FAKE_HTML_V2 = b"""<html><body>
<h1>Inheritance Tax account IHT400</h1>
<p>Use form IHT400 if the estate does not qualify as an excepted estate.</p>
<p>The guidance was updated with a new paragraph.</p>
</body></html>"""


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
def client_for(session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    from app.core.config import get_settings

    get_settings.cache_clear()

    application = FastAPI()
    application.include_router(agent_drafts_api.router)

    async def _override_session():
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(application)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    return _make


def _without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()


def _with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
async def demo_estate(session_factory) -> dict:
    """A demo-style estate: house to descendants, cash, car, private shares,
    full transferred bands, an unnotified bank contact, open process steps
    and an approaching deadline, plus one engine snapshot."""
    async with session_factory() as session:
        estate = Estate(
            name="Demo estate",
            date_of_death=dt.date(2026, 7, 3),
            tnrb_pct=Decimal("1"),
            trnrb_pct=Decimal("1"),
            residence_to_descendants_value=Decimal("340000"),
            charity_share_pct=Decimal("0"),
            claims_rnrb=True,
            gifts_with_reservation=False,
            foreign_assets_value=Decimal("0"),
            trust_property_value=Decimal("0"),
            specified_transfers_value=Decimal("9000"),
            created_by="test-fixture",
        )
        session.add(estate)
        await session.flush()

        bank = Contact(
            estate_id=estate.id,
            name="Example Bank",
            kind="organisation",
            references=["ACC-12345678"],
            holds_or_handles="Current account and cash ISA",
            notify_required=True,
            created_by="test-fixture",
        )
        session.add(bank)
        await session.flush()

        assets = [
            Asset(
                estate_id=estate.id,
                category="property",
                description="Family house",
                dod_value=Decimal("340000"),
                value_basis="confirmed",
                rnrb_qualifying=True,
                created_by="test-fixture",
            ),
            Asset(
                estate_id=estate.id,
                category="cash",
                description="Bank and ISA balances",
                dod_value=Decimal("600000"),
                value_basis="confirmed",
                holder_contact_id=bank.id,
                account_reference="ACC-99887766",
                created_by="test-fixture",
            ),
            Asset(
                estate_id=estate.id,
                category="car",
                description="Car",
                dod_value=Decimal("20000"),
                value_basis="confirmed",
                created_by="test-fixture",
            ),
            Asset(
                estate_id=estate.id,
                category="unlisted_shares",
                description="Gliding club shares",
                dod_value=Decimal("0"),
                value_basis="confirmed",
                created_by="test-fixture",
            ),
            Asset(
                estate_id=estate.id,
                category="household",
                description="Household contents",
                dod_value=None,
                value_basis="estimate",
                created_by="test-fixture",
            ),
        ]
        session.add_all(assets)

        step_one = ProcessStep(
            estate_id=estate.id, order=1, name="Register the death", created_by="test-fixture"
        )
        step_two = ProcessStep(
            estate_id=estate.id, order=2, name="Apply for the grant", created_by="test-fixture"
        )
        session.add_all([step_one, step_two])

        deadline = Deadline(
            estate_id=estate.id,
            type="iht_payment",
            derived_date=dt.datetime.now(dt.UTC).date() + dt.timedelta(days=30),
            created_by="test-fixture",
        )
        session.add(deadline)
        await session.flush()

        await run_recompute(session, estate, "test-fixture")
        await session.commit()
        return {"estate_id": estate.id, "contact_id": bank.id, "deadline_id": deadline.id}


def _ctx(session, estate_id: uuid.UUID, **kwargs) -> AgentContext:
    from app.core.config import get_settings

    return AgentContext(
        session=session,
        estate_id=estate_id,
        actor=EXECUTOR,
        settings=get_settings(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# forms_draft
# ---------------------------------------------------------------------------


async def test_draft_form_produces_entries_gaps_and_pending_approval(
    session_factory, demo_estate, client_for, monkeypatch
):
    _without_key(monkeypatch)  # deterministic mapping must work with no key

    response = client_for(EXECUTOR).post("/agents/draft-form", json={})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "pending_approval"
    assert body["narrative"] is None  # no key, narrative omitted
    assert body["constants_version"] == EXPECTED_CONSTANTS_VERSION

    by_code = {form["form"]: form for form in body["forms"]}
    # Main form plus every required schedule from the engine snapshot.
    assert set(by_code) == {
        "IHT400",
        "IHT402",
        "IHT403",
        "IHT405",
        "IHT406",
        "IHT407",
        "IHT412",
        "IHT435",
        "IHT436",
    }

    main = by_code["IHT400"]
    entries = {section["field_ref"]: section for section in main["sections"]}
    assert Decimal(entries["IHT400.net_value"]["value"]) == Decimal("960000")
    assert Decimal(entries["IHT400.tax"]["value"]) == Decimal("0")
    assert entries["IHT400.must_file_iht400"]["value"] == "True"
    assert entries["IHT400.net_value"]["source_entity"].startswith("iht_assessment:")

    # The house maps onto IHT405 with its stored value and provenance.
    house_rows = by_code["IHT405"]["sections"]
    assert any(
        Decimal(row["value"]) == Decimal("340000")
        and row["source_entity"].startswith("asset:")
        for row in house_rows
        if row["value"] not in ("value missing",)
    )
    # The RNRB claim schedule carries the residence value.
    iht435 = {row["field_ref"]: row for row in by_code["IHT435"]["sections"]}
    assert Decimal(iht435["IHT435.residence_value"]["value"]) == Decimal("340000")

    # Gap list: the household contents have no confirmed value.
    gap_text = " ".join(gap["item"] for gap in main["gaps"])
    assert "Household contents" in gap_text

    async with session_factory() as session:
        approval = await session.get(Approval, uuid.UUID(body["approval_id"]))
        assert approval is not None
        assert approval.approved_by is None  # pending until a person approves
        document = await session.get(Document, uuid.UUID(body["draft_id"]))
        assert document is not None
        assert document.type == "draft"
        assert set(document.access_roles) == {"executor", "admin"}
        audits = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.action == "agent_draft")
                )
            )
            .scalars()
            .all()
        )
        assert any(event.entity == f"document:{document.id}" for event in audits)
        assert all(event.estate_id == demo_estate["estate_id"] for event in audits)


async def test_draft_form_single_form_code(demo_estate, client_for, monkeypatch):
    _without_key(monkeypatch)
    response = client_for(EXECUTOR).post("/agents/draft-form", json={"form_code": "IHT435"})
    assert response.status_code == 200, response.text
    forms = response.json()["forms"]
    assert [form["form"] for form in forms] == ["IHT435"]


async def test_draft_form_without_assessment_snapshot_conflicts(
    session_factory, client_for, monkeypatch
):
    _without_key(monkeypatch)
    async with session_factory() as session:
        session.add(Estate(name="Empty estate", created_by="test-fixture"))
        await session.commit()
    response = client_for(EXECUTOR).post("/agents/draft-form", json={})
    assert response.status_code == 409
    assert "assessment" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# RBAC: the viewer role can invoke NO agent endpoint
# ---------------------------------------------------------------------------


async def test_viewer_gets_403_and_anonymous_401_on_all_agent_endpoints(
    demo_estate, client_for
):
    posts = [
        ("/agents/draft-form", {}),
        ("/agents/draft-narration", None),
        ("/agents/draft-letter", {"contact_id": str(uuid.uuid4()), "purpose": "notify"}),
        ("/agents/suggest-tasks", None),
        (f"/agents/drafts/{uuid.uuid4()}/approve", {}),
    ]
    viewer = client_for(VIEWER)
    anonymous = client_for(None)
    for path, body in posts:
        assert viewer.post(path, json=body).status_code == 403, path
        assert anonymous.post(path, json=body).status_code == 401, path
    assert viewer.get("/agents/drafts").status_code == 403
    assert anonymous.get("/agents/drafts").status_code == 401


# ---------------------------------------------------------------------------
# next_actions: suggest -> approve -> tasks exist
# ---------------------------------------------------------------------------


async def test_suggest_tasks_then_approve_materialises_tasks(
    session_factory, demo_estate, client_for, monkeypatch
):
    _without_key(monkeypatch)  # deterministic graph needs no model
    client = client_for(EXECUTOR)

    response = client.post("/agents/suggest-tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_approval"
    suggestions = body["suggestions"]
    titles = [item["title"] for item in suggestions]

    assert "Notify Example Bank of the death" in titles
    assert "Prepare for the iht payment deadline" in titles
    assert "Progress step: Register the death" in titles
    assert "Progress step: Apply for the grant" in titles
    # The second step depends on the first within the batch.
    first = titles.index("Progress step: Register the death")
    second = titles.index("Progress step: Apply for the grant")
    assert suggestions[second]["depends_on"] == [first]
    # No tasks exist yet: suggestions are a draft.
    async with session_factory() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        assert tasks == []

    listing = client.get("/agents/drafts")
    assert listing.status_code == 200
    assert any(item["approval_id"] == body["approval_id"] for item in listing.json())

    approve = client.post(f"/agents/drafts/{body['approval_id']}/approve", json={})
    assert approve.status_code == 200, approve.text
    approved = approve.json()
    assert approved["approved_by"] == EXECUTOR
    assert len(approved["created_task_ids"]) == len(suggestions)

    async with session_factory() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        assert len(tasks) == len(suggestions)
        assert all(task.source == "agent_suggested" for task in tasks)
        by_title = {task.title: task for task in tasks}
        blocker = by_title["Progress step: Register the death"]
        blocked = by_title["Progress step: Apply for the grant"]
        assert blocked.blocked_by == [str(blocker.id)]
        assert str(blocked.id) in blocker.blocks
        approval = await session.get(Approval, uuid.UUID(body["approval_id"]))
        assert approval.approved_by == EXECUTOR
        assert approval.approved_at is not None

    # Approving twice is refused; the pending list no longer shows it.
    again = client.post(f"/agents/drafts/{body['approval_id']}/approve", json={})
    assert again.status_code == 409
    assert all(
        item["approval_id"] != body["approval_id"] for item in client.get("/agents/drafts").json()
    )


async def test_approve_accepts_a_subset_of_suggestions(
    session_factory, demo_estate, client_for, monkeypatch
):
    _without_key(monkeypatch)
    client = client_for(EXECUTOR)
    body = client.post("/agents/suggest-tasks").json()

    approve = client.post(
        f"/agents/drafts/{body['approval_id']}/approve", json={"accepted": [0]}
    )
    assert approve.status_code == 200, approve.text
    assert len(approve.json()["created_task_ids"]) == 1

    async with session_factory() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].title == body["suggestions"][0]["title"]


# ---------------------------------------------------------------------------
# iht_narration
# ---------------------------------------------------------------------------


async def test_narration_cites_constants_version_and_validates(
    session_factory, demo_estate, client_for, monkeypatch
):
    _with_key(monkeypatch)
    seen: dict[str, str] = {}

    def _fake_llm(system_prompt: str, user_prompt: str, settings=None) -> str:
        seen["system"] = system_prompt
        seen["user"] = user_prompt
        return (
            "The nil rate band with the full transfer is £650,000.00 and the "
            "residence nil rate band applied is £340,000.00, so the total "
            "allowance of £990,000.00 exceeds the net estate of £960,000.00 "
            "and no inheritance tax is due [1]. A full account is still "
            "required because the residence nil rate band is claimed."
        )

    monkeypatch.setattr(llm_module, "call_llm", _fake_llm)

    response = client_for(EXECUTOR).post("/agents/draft-narration")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["validated"] is True
    assert body["constants_version"] == EXPECTED_CONSTANTS_VERSION
    assert any(
        EXPECTED_CONSTANTS_VERSION in citation["title"] for citation in body["citations"]
    )
    # The prompt supplied every figure verbatim and never asked for maths;
    # the critical must_file_iht400 flag is always in the narration input.
    assert "must_file_iht400: True" in seen["user"]
    assert "net_value: 960000" in seen["user"]
    assert "EXPLAIN ONLY" in seen["system"]

    async with session_factory() as session:
        approval = await session.get(Approval, uuid.UUID(body["approval_id"]))
        assert approval is not None and approval.approved_by is None
        document = await session.get(Document, uuid.UUID(body["draft_id"]))
        assert document is not None and document.type == "draft"


async def test_narration_regenerates_when_a_rogue_figure_appears(
    demo_estate, client_for, monkeypatch
):
    _with_key(monkeypatch)
    calls: list[str] = []

    def _fake_llm(system_prompt: str, user_prompt: str, settings=None) -> str:
        calls.append(user_prompt)
        if len(calls) == 1:
            return "The tax due is £123.45."  # not an engine figure
        return "No inheritance tax is due: the allowance is £990,000.00."

    monkeypatch.setattr(llm_module, "call_llm", _fake_llm)

    response = client_for(EXECUTOR).post("/agents/draft-narration")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validated"] is True
    assert len(calls) == 2
    # The regeneration prompt fed back the rogue figure.
    assert "123.45" in calls[1]


async def test_llm_endpoints_return_503_without_a_key(
    demo_estate, client_for, monkeypatch
):
    _without_key(monkeypatch)
    client = client_for(EXECUTOR)
    for path, body in (
        ("/agents/draft-narration", None),
        ("/agents/draft-letter", {"contact_id": str(uuid.uuid4()), "purpose": "notify"}),
    ):
        response = client.post(path, json=body)
        assert response.status_code == 503, path
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]


# ---------------------------------------------------------------------------
# draft-letter
# ---------------------------------------------------------------------------


async def test_draft_letter_uses_stored_references_and_is_pending(
    session_factory, demo_estate, client_for, monkeypatch
):
    _with_key(monkeypatch)
    seen: dict[str, str] = {}

    def _fake_llm(system_prompt: str, user_prompt: str, settings=None) -> str:
        seen["system"] = system_prompt
        seen["user"] = user_prompt
        return (
            "DRAFT for executor review\n\nDear Example Bank,\n"
            "We write to notify you of the death of the account holder. "
            "Please confirm the balances at the date of death for references "
            "ACC-12345678 and ACC-99887766, and freeze the accounts.\n"
            "[Signature block]"
        )

    monkeypatch.setattr(llm_module, "call_llm", _fake_llm)

    response = client_for(EXECUTOR).post(
        "/agents/draft-letter",
        json={
            "contact_id": str(demo_estate["contact_id"]),
            "purpose": "Notify the bank of the death and request balances",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["contact_name"] == "Example Bank"
    # The stored contact reference AND the asset account reference travel.
    assert set(body["references"]) == {"ACC-12345678", "ACC-99887766"}
    assert "ACC-12345678" in body["letter_text"]
    assert "date of death" in body["letter_text"].lower()
    # The model only ever saw stored details, and was told: no figures.
    assert "ACC-99887766" in seen["user"]
    assert "NO monetary figures" in seen["system"]

    async with session_factory() as session:
        approval = await session.get(Approval, uuid.UUID(body["approval_id"]))
        assert approval is not None
        assert approval.approved_by is None
        assert approval.draft_kind == "notification_letter"


async def test_draft_letter_unknown_contact_404(demo_estate, client_for, monkeypatch):
    _with_key(monkeypatch)
    monkeypatch.setattr(llm_module, "call_llm", lambda s, u, settings=None: "unused")
    response = client_for(EXECUTOR).post(
        "/agents/draft-letter",
        json={"contact_id": str(uuid.uuid4()), "purpose": "notify"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# guidance_qa graph (shares the knowledge router's seams)
# ---------------------------------------------------------------------------


async def _add_knowledge_doc(session_factory, estate_id: uuid.UUID) -> None:
    async with session_factory() as session:
        doc = KnowledgeDoc(
            estate_id=estate_id,
            source_url="https://example.test/iht400",
            title="Inheritance Tax account (IHT400)",
            form_code="IHT400",
            jurisdiction="England and Wales",
            fetch_date=dt.date(2026, 7, 1),
            content_hash="deadbeef",
            version=1,
            licence="Open Government Licence v3.0",
            created_by="test-fixture",
        )
        session.add(doc)
        await session.flush()
        session.add(
            KnowledgeChunk(
                estate_id=estate_id,
                knowledge_doc_id=doc.id,
                chunk_index=0,
                text="Use form IHT400 if the estate does not qualify as an excepted estate.",
                created_by="test-fixture",
            )
        )
        await session.commit()


async def test_guidance_qa_graph_answers_with_citations(
    session_factory, demo_estate, monkeypatch, tmp_path
):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    _with_key(monkeypatch)
    await _add_knowledge_doc(session_factory, demo_estate["estate_id"])

    def _fake_llm(system_prompt: str, user_prompt: str, settings) -> str:
        assert "ONLY the numbered extracts" in system_prompt
        assert "excepted estate" in user_prompt
        return f"Use form IHT400 when the estate is not excepted [1]. {knowledge_api.GUIDANCE_NOTE}"

    monkeypatch.setattr(knowledge_api, "_call_llm", _fake_llm)

    async with session_factory() as session:
        state = await run_guidance_qa(
            _ctx(session, demo_estate["estate_id"]),
            "Which form is used when the estate is not excepted?",
        )
    assert state.refused is False
    assert "[1]" in state.answer
    assert state.sources[0].doc_title == "Inheritance Tax account (IHT400)"
    assert state.sources[0].form_code == "IHT400"


async def test_guidance_qa_graph_refuses_outside_the_corpus(
    session_factory, demo_estate, monkeypatch, tmp_path
):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    _with_key(monkeypatch)

    def _must_not_call(system_prompt: str, user_prompt: str, settings) -> str:
        raise AssertionError("The LLM must not be called when retrieval is empty")

    monkeypatch.setattr(knowledge_api, "_call_llm", _must_not_call)

    async with session_factory() as session:
        state = await run_guidance_qa(
            _ctx(session, demo_estate["estate_id"]),
            "What colour is the probate registry door?",
        )
    assert state.refused is True
    assert state.answer == knowledge_api.REFUSAL_TEXT
    assert state.sources == []


# ---------------------------------------------------------------------------
# knowledge_ingest graph
# ---------------------------------------------------------------------------


def _fake_fetcher(content: bytes):
    async def _fetch(url: str):
        return build_fetch_result(url, content, "text/html; charset=utf-8")

    return _fetch


async def test_knowledge_ingest_auto_commits_new_and_gates_changed(
    session_factory, demo_estate, monkeypatch, tmp_path
):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    estate_id = demo_estate["estate_id"]

    # 1. Brand-new document: mechanical, auto-commits with a report.
    async with session_factory() as session:
        state = await run_knowledge_ingest(
            _ctx(session, estate_id, fetcher=_fake_fetcher(FAKE_HTML_V1)), ["IHT400"]
        )
    assert [report.status for report in state.reports] == ["ingested"]
    assert state.pending_changed == []

    # 2. Unchanged content: no new version, no interrupt.
    async with session_factory() as session:
        state = await run_knowledge_ingest(
            _ctx(session, estate_id, fetcher=_fake_fetcher(FAKE_HTML_V1)), ["IHT400"]
        )
    assert [report.status for report in state.reports] == ["unchanged"]

    # 3. Changed content stops at the interrupt: nothing committed yet.
    async with session_factory() as session:
        state = await run_knowledge_ingest(
            _ctx(session, estate_id, fetcher=_fake_fetcher(FAKE_HTML_V2)), ["IHT400"]
        )
    assert state.pending_changed == ["IHT400"]
    assert all(report.source_key != "IHT400" or report.status != "changed"
               for report in state.reports)
    async with session_factory() as session:
        doc = (
            (await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.form_code == "IHT400")))
            .scalars()
            .one()
        )
        assert doc.version == 1  # the changed version awaited approval

    # 4. Human approval resumes past the interrupt and commits version 2.
    async with session_factory() as session:
        state = await run_knowledge_ingest(
            _ctx(session, estate_id, fetcher=_fake_fetcher(FAKE_HTML_V2)),
            ["IHT400"],
            approve_changed=True,
        )
    changed = [report for report in state.reports if report.status == "changed"]
    assert len(changed) == 1
    assert changed[0].version == 2
    assert state.pending_changed == []
    async with session_factory() as session:
        doc = (
            (await session.execute(select(KnowledgeDoc).where(KnowledgeDoc.form_code == "IHT400")))
            .scalars()
            .one()
        )
        assert doc.version == 2


async def test_knowledge_ingest_reports_unknown_sources(
    session_factory, demo_estate, monkeypatch, tmp_path
):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    async with session_factory() as session:
        state = await run_knowledge_ingest(
            _ctx(session, demo_estate["estate_id"], fetcher=_fake_fetcher(FAKE_HTML_V1)),
            ["no_such_source"],
        )
    assert [report.status for report in state.reports] == ["not_found"]
