"""iht_narration graph: plain-English, cited breakdown of the engine's
Assessment snapshot.

Hard rule (AGENT_DESIGN.md 2.2): the graph NEVER computes. The prompt
provides every figure verbatim from the stored iht_assessment snapshot
and instructs explanation only. A post-generation validator asserts that
every number in the output appears in the snapshot's figure set
(normalised for formatting); a failing draft is regenerated with
feedback, and flagged unvalidated if it still fails.

The narration is stored as a draft document with an approval-pending row
and the graph interrupts before the finalise node (human review gate).
"""

import re
import uuid
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents import llm, tools
from app.agents.tools import AgentContext
from app.schemas.agents import NarrationCitation

FINALISE_NODE = "finalise"
MAX_DRAFT_ATTEMPTS = 2

# Guidance the narration cites, by form code or topic, when cached.
_CITATION_FORM_CODES = ("IHT400", "IHT402", "IHT435", "IHT436", "IHT403")
_CITATION_TOPICS = ("rates", "residence_nil_rate_band", "excepted", "paying")

NARRATION_SYSTEM_PROMPT = """You are the explanation assistant of an estate \
administration tool for England and Wales. You turn a deterministic inheritance \
tax assessment into a plain-English, line-by-line breakdown. Follow these rules \
exactly:
1. EXPLAIN ONLY. Never calculate, estimate, derive, round or adjust any figure.
2. Use only the figures supplied in the FIGURES block, exactly as written. If a \
number is not in that block, you must not state it.
3. Cite the supplied sources with [n] markers where they support a rule you \
explain.
4. Make clear this is a draft explanation for review, drawn from the stored \
assessment, not advice.
5. Write in UK English. Do not use em dashes."""


class NarrationState(BaseModel):
    """Typed state for one narration run."""

    snapshot: dict = Field(default_factory=dict)
    assessment_ref: str | None = None
    constants_version: str = ""
    figures: dict[str, str] = Field(
        default_factory=dict, description="Labelled verbatim figures from the snapshot"
    )
    allowed_numbers: list[str] = Field(
        default_factory=list, description="Normalised figure set the output may use"
    )
    citations: list[NarrationCitation] = Field(default_factory=list)
    narration: str = ""
    validated: bool = False
    attempts: int = 0
    feedback: str | None = None
    document_id: str | None = None
    approval_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Figure set and validation (pure functions, unit-tested by the guardrails)
# ---------------------------------------------------------------------------


def normalise_number(token: str) -> str | None:
    """Normalise a numeric token for comparison: strip currency, commas and
    percentage signs, drop trailing zeros. Returns None for non-numbers."""
    cleaned = token.strip().replace("£", "").replace(",", "").rstrip("%").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    normalised = value.normalize()
    return format(normalised, "f")


def _collect_numbers(value: Any, into: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float | Decimal | str):
        normalised = normalise_number(str(value))
        if normalised is not None:
            into.add(normalised)
            # Fractions are also allowed in percentage form (0.4 -> 40).
            try:
                pct = (Decimal(normalised) * 100).normalize()
                into.add(format(pct, "f"))
            except InvalidOperation:
                pass
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, into)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _collect_numbers(item, into)


def allowed_figures(snapshot: dict) -> set[str]:
    """Every normalised number the snapshot contains: the only numbers the
    narration is permitted to state."""
    numbers: set[str] = set()
    _collect_numbers(snapshot, numbers)
    return numbers


_CITATION_MARKER_RE = re.compile(r"\[\d+\]")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_FORM_CODE_RE = re.compile(r"\b[A-Z]{2,8}\d{1,4}[A-Z]{0,2}\b")
_NUMBER_RE = re.compile(r"£?\d[\d,]*(?:\.\d+)?%?")


def extract_numbers(text: str) -> list[str]:
    """Numeric tokens in a narration, ignoring citation markers, ISO dates
    and form codes (IHT405 is a form, not a figure)."""
    stripped = _CITATION_MARKER_RE.sub(" ", text)
    stripped = _ISO_DATE_RE.sub(" ", stripped)
    stripped = _FORM_CODE_RE.sub(" ", stripped)
    found: list[str] = []
    for token in _NUMBER_RE.findall(stripped):
        normalised = normalise_number(token)
        if normalised is not None:
            found.append(normalised)
    return found


def validate_narration(narration: str, allowed: set[str]) -> list[str]:
    """The numbers in the narration that do NOT come from the snapshot.
    An empty list means the narration passed."""
    return [number for number in extract_numbers(narration) if number not in allowed]


def build_narration_input(snapshot: dict) -> dict[str, str]:
    """The labelled, verbatim figure block the prompt supplies.

    Always includes must_file_iht400 (the critical rule agents must never
    talk around: claims_rnrb=True forces a full IHT400 account) and the
    excepted-estate route alongside every engine figure.
    """
    inputs = snapshot.get("inputs", {}) or {}
    result = snapshot.get("result", {}) or {}
    figures: dict[str, str] = {}
    for label in (
        "net_value",
        "gross_value",
        "tnrb_pct",
        "trnrb_pct",
        "residence_to_descendants_value",
        "downsizing_addition",
        "exempt_transfers",
        "charity_share",
    ):
        if inputs.get(label) is not None:
            figures[label] = str(inputs[label])
    for label in ("nrb", "rnrb_max", "rnrb", "allowance", "taxable", "rate", "tax"):
        if result.get(label) is not None:
            figures[label] = str(result[label])
    figures["is_excepted"] = str(bool(result.get("is_excepted")))
    figures["must_file_iht400"] = str(bool(result.get("must_file_iht400")))
    figures["required_schedules"] = ", ".join(result.get("required_schedules") or []) or "none"
    return figures


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def _load_node(ctx: AgentContext, state: NarrationState) -> dict:
    row = await tools.read_latest_assessment(ctx)
    if row is None:
        return {"error": "No IHT assessment snapshot exists yet; run a recompute first."}
    snapshot = row.snapshot or {}
    return {
        "snapshot": snapshot,
        "assessment_ref": f"iht_assessment:{row.id}",
        "constants_version": row.constants_version or "",
        "figures": build_narration_input(snapshot),
        "allowed_numbers": sorted(allowed_figures(snapshot)),
    }


async def _citations_node(ctx: AgentContext, state: NarrationState) -> dict:
    citations = [
        NarrationCitation(
            title=f"Tax constants version {state.constants_version}",
            source_url=None,
            form_code=None,
        )
    ]
    for doc in await tools.read_knowledge_docs(ctx):
        relevant_form = doc.form_code in _CITATION_FORM_CODES
        relevant_topic = any(topic in (doc.topic or "") for topic in _CITATION_TOPICS)
        if relevant_form or relevant_topic:
            citations.append(
                NarrationCitation(
                    title=doc.title,
                    source_url=doc.source_url,
                    fetch_date=doc.fetch_date,
                    form_code=doc.form_code,
                )
            )
    return {"citations": citations}


async def _draft_node(ctx: AgentContext, state: NarrationState) -> dict:
    figure_block = "\n".join(f"{label}: {value}" for label, value in state.figures.items())
    source_block = "\n".join(
        f"[{number}] {citation.title}"
        + (
            f" ({citation.source_url}, fetched {citation.fetch_date})"
            if citation.source_url
            else ""
        )
        for number, citation in enumerate(state.citations, start=1)
    )
    feedback_block = (
        f"\n\nYour previous draft was rejected: {state.feedback}\n"
        "Rewrite it using ONLY the figures above." if state.feedback else ""
    )
    user_prompt = (
        f"FIGURES (constants version {state.constants_version}):\n{figure_block}\n\n"
        f"SOURCES:\n{source_block}\n\n"
        "Explain this inheritance tax assessment line by line for the executors."
        f"{feedback_block}"
    )
    narration = llm.call_llm(NARRATION_SYSTEM_PROMPT, user_prompt, ctx.settings)
    return {"narration": narration, "attempts": state.attempts + 1}


def _validate_node(state: NarrationState) -> dict:
    rogue = validate_narration(state.narration, set(state.allowed_numbers))
    if not rogue:
        return {"validated": True, "feedback": None}
    return {
        "validated": False,
        "feedback": (
            "it contained figures that are not in the assessment snapshot: "
            + ", ".join(sorted(set(rogue)))
        ),
    }


def _route_after_validate(state: NarrationState) -> str:
    if state.validated or state.attempts >= MAX_DRAFT_ATTEMPTS:
        return "store_draft"
    return "draft"


async def _store_draft_node(ctx: AgentContext, state: NarrationState) -> dict:
    document = await tools.store_draft_document(
        ctx,
        title="IHT assessment narration (draft)",
        payload={
            "narration": state.narration,
            "validated": state.validated,
            "constants_version": state.constants_version,
            "assessment_ref": state.assessment_ref,
            "citations": [citation.model_dump(mode="json") for citation in state.citations],
        },
        draft_kind="iht_narration",
    )
    approval = await tools.create_pending_approval(
        ctx, entity_ref=f"document:{document.id}", draft_kind="iht_narration"
    )
    return {"document_id": str(document.id), "approval_id": str(approval.id)}


def _finalise_node(state: NarrationState) -> dict:
    """Post-interrupt no-op: the draft stays a draft until the approval row
    is completed by a person."""
    return {}


def _route_after_load(state: NarrationState) -> str:
    return END if state.error else "citations"


def build_graph(ctx: AgentContext):
    """Compile with the human-approval interrupt before finalisation."""
    graph = StateGraph(NarrationState)
    graph.add_node("load", partial(_load_node, ctx))
    graph.add_node("citations", partial(_citations_node, ctx))
    graph.add_node("draft", partial(_draft_node, ctx))
    graph.add_node("validate", _validate_node)
    graph.add_node("store_draft", partial(_store_draft_node, ctx))
    graph.add_node(FINALISE_NODE, _finalise_node)
    graph.set_entry_point("load")
    graph.add_conditional_edges("load", _route_after_load)
    graph.add_edge("citations", "draft")
    graph.add_edge("draft", "validate")
    graph.add_conditional_edges("validate", _route_after_validate)
    graph.add_edge("store_draft", FINALISE_NODE)
    graph.add_edge(FINALISE_NODE, END)
    return graph.compile(checkpointer=MemorySaver(), interrupt_before=[FINALISE_NODE])


async def run_iht_narration(ctx: AgentContext) -> NarrationState:
    """Run to the human-review interrupt and return the drafted state."""
    app = build_graph(ctx)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = await app.ainvoke(NarrationState().model_dump(), config)
    return NarrationState.model_validate(result)
