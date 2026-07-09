"""Agent tools: every capability any graph can reach, all read or draft only.

Design rule 2 (AGENT_DESIGN.md): no tool in any graph's toolset can send
email or letters, file with HMRC or the probate service, or move money.
This module is the single tool registry the guardrail tests enumerate:
a tool is only reachable by a graph if it is registered in ALL_TOOLS and
listed in GRAPH_TOOLSETS, and every registered tool declares a capability
of "read" or "draft". Nothing else exists to call.

Draft storage choice (resolved against the Approval model): Approval rows
have a NULLABLE approved_by, so a draft creates its approval-pending row
up front with approved_by=None (and approved_at=None). The approve
endpoint completes that same row. Draft artefacts themselves are stored
as Document rows with type "draft", access executor/admin, and their JSON
payload in object storage under file_key.
"""

import datetime as dt
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.knowledge import hybrid_search
from app.core.config import Settings, get_settings
from app.ingest.fetcher import FetchResult, fetch_url
from app.ingest.pipeline import ingest as pipeline_ingest
from app.ingest.registry import RegistrySource, load_registry
from app.models import (
    Approval,
    Asset,
    Contact,
    Deadline,
    Document,
    Estate,
    IhtAssessment,
    KnowledgeDoc,
    Liability,
    ProcessStep,
    Task,
)
from app.schemas.knowledge import IngestReport, SearchHit
from app.services.reevaluation import latest_assessment
from app.services.storage import StorageBackend, get_storage

FetchFn = Callable[[str], Awaitable[FetchResult]]

DRAFT_DOCUMENT_TYPE = "draft"
DRAFT_ACCESS_ROLES = ["executor", "admin"]


@dataclass(slots=True)
class AgentContext:
    """Everything a graph run needs, bound once per request.

    The context carries the caller's identity and the estate scope so
    every tool call is attributable; graphs close over it rather than
    hauling live sessions through checkpointed state.
    """

    session: AsyncSession
    estate_id: uuid.UUID
    actor: str
    settings: Settings = field(default_factory=get_settings)
    fetcher: FetchFn = fetch_url
    storage: StorageBackend | None = None
    # Per-run fetch cache so plan and commit phases fetch a source once.
    fetch_cache: dict[str, FetchResult] = field(default_factory=dict)

    def get_storage(self) -> StorageBackend:
        if self.storage is None:
            self.storage = get_storage(self.settings)
        return self.storage


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


async def read_estate(ctx: AgentContext) -> Estate | None:
    """The estate row the run is scoped to."""
    return await ctx.session.get(Estate, ctx.estate_id)


async def read_latest_assessment(ctx: AgentContext) -> IhtAssessment | None:
    """The most recent deterministic engine snapshot (never recomputed here)."""
    return await latest_assessment(ctx.session, ctx.estate_id)


async def read_assets(ctx: AgentContext) -> list[Asset]:
    """All non-archived assets of the estate."""
    result = await ctx.session.execute(
        select(Asset)
        .where(Asset.estate_id == ctx.estate_id, Asset.archived_at.is_(None))
        .order_by(Asset.created_at)
    )
    return list(result.scalars().all())


async def read_liabilities(ctx: AgentContext) -> list[Liability]:
    """All non-archived liabilities of the estate."""
    result = await ctx.session.execute(
        select(Liability)
        .where(Liability.estate_id == ctx.estate_id, Liability.archived_at.is_(None))
        .order_by(Liability.created_at)
    )
    return list(result.scalars().all())


async def read_contacts(ctx: AgentContext) -> list[Contact]:
    """All non-archived contacts of the estate."""
    result = await ctx.session.execute(
        select(Contact)
        .where(Contact.estate_id == ctx.estate_id, Contact.archived_at.is_(None))
        .order_by(Contact.name)
    )
    return list(result.scalars().all())


async def read_contact(ctx: AgentContext, contact_id: uuid.UUID) -> Contact | None:
    """One contact, estate-scoped; archived rows are invisible."""
    contact = await ctx.session.get(Contact, contact_id)
    if contact is None or contact.estate_id != ctx.estate_id or contact.archived_at is not None:
        return None
    return contact


async def read_tasks(ctx: AgentContext) -> list[Task]:
    """All non-archived tasks of the estate."""
    result = await ctx.session.execute(
        select(Task)
        .where(Task.estate_id == ctx.estate_id, Task.archived_at.is_(None))
        .order_by(Task.created_at)
    )
    return list(result.scalars().all())


async def read_process_steps(ctx: AgentContext) -> list[ProcessStep]:
    """The process timeline steps, in order."""
    result = await ctx.session.execute(
        select(ProcessStep)
        .where(ProcessStep.estate_id == ctx.estate_id, ProcessStep.archived_at.is_(None))
        .order_by(ProcessStep.order)
    )
    return list(result.scalars().all())


async def read_deadlines(ctx: AgentContext) -> list[Deadline]:
    """The derived statutory deadlines."""
    result = await ctx.session.execute(
        select(Deadline)
        .where(Deadline.estate_id == ctx.estate_id, Deadline.archived_at.is_(None))
        .order_by(Deadline.derived_date)
    )
    return list(result.scalars().all())


async def read_knowledge_docs(ctx: AgentContext) -> list[KnowledgeDoc]:
    """Cached guidance document metadata, for citations."""
    result = await ctx.session.execute(
        select(KnowledgeDoc)
        .where(KnowledgeDoc.estate_id == ctx.estate_id, KnowledgeDoc.archived_at.is_(None))
        .order_by(KnowledgeDoc.title)
    )
    return list(result.scalars().all())


async def search_guidance(ctx: AgentContext, question: str, limit: int) -> list[SearchHit]:
    """Hybrid retrieval over the cached corpus, shared verbatim with
    /knowledge/search via app.api.knowledge.hybrid_search (no duplication)."""
    return await hybrid_search(ctx.session, ctx.estate_id, question, limit)


async def diff_registry_source(
    ctx: AgentContext, source: RegistrySource
) -> tuple[str, FetchResult | None]:
    """Fetch one registered source and hash-diff it against the stored doc.

    Returns (status, fetch_result) where status is one of "new",
    "changed", "unchanged" or "error". Reads the internet and the
    database; writes nothing.
    """
    try:
        result = ctx.fetch_cache.get(source.url) or await ctx.fetcher(source.url)
    except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
        return f"error: {exc}", None
    ctx.fetch_cache[source.url] = result

    existing = await ctx.session.execute(
        select(KnowledgeDoc)
        .where(
            KnowledgeDoc.estate_id == ctx.estate_id,
            KnowledgeDoc.source_url == source.url,
            KnowledgeDoc.archived_at.is_(None),
        )
        .limit(1)
    )
    doc = existing.scalars().first()
    if doc is None:
        return "new", result
    if doc.content_hash == result.content_hash:
        return "unchanged", result
    return "changed", result


def load_source_registry() -> list[RegistrySource]:
    """The seed source registry (read-only; skips unresolved URLs)."""
    return load_registry()


# ---------------------------------------------------------------------------
# Draft tools (create draft artefacts and approval-pending rows; nothing
# leaves the system)
# ---------------------------------------------------------------------------


async def store_draft_document(
    ctx: AgentContext,
    *,
    title: str,
    payload: dict[str, Any],
    draft_kind: str,
) -> Document:
    """Store a draft artefact as a Document row (type "draft").

    The JSON payload goes to object storage under file_key; access is
    executor/admin only. The row is flushed, not committed: the caller
    owns the transaction.
    """
    body = json.dumps(
        {"draft_kind": draft_kind, "payload": payload}, default=str, ensure_ascii=False
    ).encode("utf-8")
    file_key = ctx.get_storage().save(body, suffix=".json")
    document = Document(
        estate_id=ctx.estate_id,
        title=title,
        type=DRAFT_DOCUMENT_TYPE,
        file_key=file_key,
        mime="application/json",
        access_roles=list(DRAFT_ACCESS_ROLES),
        created_by=ctx.actor,
    )
    ctx.session.add(document)
    await ctx.session.flush()
    return document


def read_draft_payload(ctx: AgentContext, document: Document) -> dict[str, Any]:
    """Load a stored draft payload back from object storage."""
    if not document.file_key:
        return {}
    raw = json.loads(ctx.get_storage().read(document.file_key).decode("utf-8"))
    payload = raw.get("payload", {})
    return payload if isinstance(payload, dict) else {}


async def create_pending_approval(
    ctx: AgentContext, *, entity_ref: str, draft_kind: str
) -> Approval:
    """Create the approval-pending row for a draft: approved_by stays None
    until a person approves via the approvals flow (guardrail 2)."""
    approval = Approval(
        estate_id=ctx.estate_id,
        entity_ref=entity_ref,
        draft_kind=draft_kind,
        approved_by=None,
        approved_at=None,
        created_by=ctx.actor,
    )
    ctx.session.add(approval)
    await ctx.session.flush()
    return approval


async def ingest_registry_source(ctx: AgentContext, source: RegistrySource) -> IngestReport:
    """Run the shared ingest pipeline for one source (fetch, extract, chunk,
    embed, upsert knowledge rows). Stores guidance, drafts nothing outward.

    Uses the run's fetch cache so a source diffed in the plan phase is not
    fetched twice. The pipeline commits per source by design.
    """
    cached = ctx.fetch_cache.get(source.url)

    async def _fetch(url: str) -> FetchResult:
        if cached is not None and url == source.url:
            return cached
        result = await ctx.fetcher(url)
        ctx.fetch_cache[url] = result
        return result

    return await pipeline_ingest(
        ctx.session,
        source,
        estate_id=ctx.estate_id,
        actor=ctx.actor,
        fetcher=_fetch,
        storage=ctx.get_storage(),
    )


# ---------------------------------------------------------------------------
# The registry the guardrail tests enumerate
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A registered tool: its capability is read or draft, never more."""

    name: str
    capability: str  # "read" or "draft"
    description: str
    fn: Callable[..., Any]


ALLOWED_CAPABILITIES = frozenset({"read", "draft"})

_READ_TOOLS = (
    ToolSpec("read_estate", "read", "Read the estate row", read_estate),
    ToolSpec(
        "read_latest_assessment",
        "read",
        "Read the latest deterministic IHT assessment snapshot",
        read_latest_assessment,
    ),
    ToolSpec("read_assets", "read", "List the asset register", read_assets),
    ToolSpec("read_liabilities", "read", "List the liability register", read_liabilities),
    ToolSpec("read_contacts", "read", "List the contacts register", read_contacts),
    ToolSpec("read_contact", "read", "Read one contact", read_contact),
    ToolSpec("read_tasks", "read", "List tasks", read_tasks),
    ToolSpec("read_process_steps", "read", "List process timeline steps", read_process_steps),
    ToolSpec("read_deadlines", "read", "List derived deadlines", read_deadlines),
    ToolSpec(
        "read_knowledge_docs", "read", "List cached guidance metadata", read_knowledge_docs
    ),
    ToolSpec(
        "search_guidance",
        "read",
        "Hybrid retrieval over the cached corpus (shared with /knowledge)",
        search_guidance,
    ),
    ToolSpec(
        "diff_registry_source",
        "read",
        "Fetch a registered source and hash-diff against the stored version",
        diff_registry_source,
    ),
    ToolSpec(
        "load_source_registry", "read", "Load the seed source registry", load_source_registry
    ),
)

_DRAFT_TOOLS = (
    ToolSpec(
        "store_draft_document",
        "draft",
        "Store a draft artefact as a document row (type draft, executor/admin)",
        store_draft_document,
    ),
    ToolSpec(
        "read_draft_payload",
        "draft",
        "Load a stored draft payload back for approval processing",
        read_draft_payload,
    ),
    ToolSpec(
        "create_pending_approval",
        "draft",
        "Create the approval-pending row (approved_by empty until approved)",
        create_pending_approval,
    ),
    ToolSpec(
        "ingest_registry_source",
        "draft",
        "Run the knowledge ingest pipeline for one registered source",
        ingest_registry_source,
    ),
)

ALL_TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in (*_READ_TOOLS, *_DRAFT_TOOLS)}

# Which tools each graph may reach. The guardrail test asserts every entry
# resolves to a registered read/draft tool; no send, file or pay capability
# exists to be listed.
GRAPH_TOOLSETS: dict[str, tuple[str, ...]] = {
    "knowledge_ingest": (
        "load_source_registry",
        "diff_registry_source",
        "ingest_registry_source",
    ),
    "iht_narration": (
        "read_latest_assessment",
        "read_knowledge_docs",
        "store_draft_document",
        "create_pending_approval",
    ),
    "forms_draft": (
        "read_estate",
        "read_latest_assessment",
        "read_assets",
        "read_liabilities",
        "store_draft_document",
        "create_pending_approval",
    ),
    "guidance_qa": ("search_guidance",),
    "next_actions": (
        "read_process_steps",
        "read_deadlines",
        "read_contacts",
        "read_tasks",
        "store_draft_document",
        "create_pending_approval",
    ),
}


def utc_today() -> dt.date:
    """Today in UTC, the only clock read the agent layer makes."""
    return dt.datetime.now(dt.UTC).date()
