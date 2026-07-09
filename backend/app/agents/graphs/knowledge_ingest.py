"""knowledge_ingest graph: keep the cached guidance corpus current.

Wraps the shared app.ingest.pipeline over the source registry. Per-source
reports travel in the typed state. Change handling (AGENT_DESIGN.md 2.1):

- brand-new documents are mechanical and auto-commit, with a report;
- CHANGED documents (hash-diff differs from the stored version) are the
  interrupt point: the graph stops BEFORE committing a new version, so a
  person reviews the "source changed" flag first. Resuming the same
  thread commits the approved new versions.
"""

import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents import tools
from app.agents.tools import AgentContext
from app.schemas.knowledge import IngestReport

COMMIT_CHANGED_NODE = "commit_changed"


class KnowledgeIngestState(BaseModel):
    """Typed state for one ingest run."""

    source_keys: list[str] | None = None
    reports: list[IngestReport] = Field(default_factory=list)
    pending_changed: list[str] = Field(
        default_factory=list,
        description="Source keys whose content changed; committed only after approval",
    )


def _select_sources(state: KnowledgeIngestState) -> tuple[list, list[IngestReport]]:
    """Resolve the requested keys against the registry."""
    registry = tools.load_source_registry()
    if not state.source_keys:
        return registry, []
    by_key = {source.key: source for source in registry}
    selected, missing = [], []
    for key in state.source_keys:
        source = by_key.get(key)
        if source is None:
            missing.append(
                IngestReport(
                    source_key=key,
                    url="",
                    status="not_found",
                    detail="Not in the source registry (or its URL is unresolved).",
                )
            )
        else:
            selected.append(source)
    return selected, missing


async def _plan_node(ctx: AgentContext, state: KnowledgeIngestState) -> dict:
    """Fetch and hash-diff every source; auto-commit new docs, defer changed."""
    selected, reports = _select_sources(state)
    pending: list[str] = []
    for source in selected:
        status, _ = await tools.diff_registry_source(ctx, source)
        if status.startswith("error"):
            reports.append(
                IngestReport(
                    source_key=source.key,
                    url=source.url,
                    status="error",
                    detail=status.removeprefix("error: "),
                )
            )
        elif status == "new":
            # Brand-new document: mechanical, auto-commits with a report.
            reports.append(await tools.ingest_registry_source(ctx, source))
        elif status == "unchanged":
            reports.append(
                IngestReport(
                    source_key=source.key,
                    url=source.url,
                    status="unchanged",
                    detail="Content hash unchanged; no new version stored.",
                )
            )
        else:  # changed: a new version needs human approval first
            pending.append(source.key)
    return {"reports": reports, "pending_changed": pending}


def _route_after_plan(state: KnowledgeIngestState) -> str:
    return COMMIT_CHANGED_NODE if state.pending_changed else END


async def _commit_changed_node(ctx: AgentContext, state: KnowledgeIngestState) -> dict:
    """Commit the approved new versions (runs only after the interrupt)."""
    registry = {source.key: source for source in tools.load_source_registry()}
    reports = list(state.reports)
    for key in state.pending_changed:
        source = registry.get(key)
        if source is None:
            reports.append(
                IngestReport(
                    source_key=key,
                    url="",
                    status="not_found",
                    detail="Source disappeared from the registry before approval.",
                )
            )
            continue
        reports.append(await tools.ingest_registry_source(ctx, source))
    return {"reports": reports, "pending_changed": []}


def build_graph(ctx: AgentContext):
    """Compile the graph with the human-approval interrupt before any
    changed document is committed."""
    graph = StateGraph(KnowledgeIngestState)
    graph.add_node("plan", partial(_plan_node, ctx))
    graph.add_node(COMMIT_CHANGED_NODE, partial(_commit_changed_node, ctx))
    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", _route_after_plan)
    graph.add_edge(COMMIT_CHANGED_NODE, END)
    return graph.compile(checkpointer=MemorySaver(), interrupt_before=[COMMIT_CHANGED_NODE])


async def run_knowledge_ingest(
    ctx: AgentContext,
    source_keys: list[str] | None = None,
    *,
    approve_changed: bool = False,
    thread_id: str | None = None,
):
    """Run the graph to the interrupt; optionally resume after approval.

    Returns the final KnowledgeIngestState. When changed sources are found
    and approve_changed is False, the returned state still lists them in
    pending_changed and nothing new was committed for them.
    """
    app = build_graph(ctx)
    config = {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}
    result = await app.ainvoke(
        KnowledgeIngestState(source_keys=source_keys).model_dump(), config
    )
    state = KnowledgeIngestState.model_validate(result)
    if state.pending_changed and approve_changed:
        # The human approved the "source changed" flag: resume the thread.
        result = await app.ainvoke(None, config)
        state = KnowledgeIngestState.model_validate(result)
    return state
