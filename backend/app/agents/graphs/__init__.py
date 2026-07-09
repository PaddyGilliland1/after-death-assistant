"""The five agent graphs (AGENT_DESIGN.md section 2).

Each module exposes build_graph(ctx) returning the compiled LangGraph
StateGraph (with its human-approval interrupt where the design places
one) and a run_* helper that executes to the interrupt.
"""

from app.agents.graphs import (
    forms_draft,
    guidance_qa,
    iht_narration,
    knowledge_ingest,
    next_actions,
)

GRAPH_MODULES = {
    "knowledge_ingest": knowledge_ingest,
    "iht_narration": iht_narration,
    "forms_draft": forms_draft,
    "guidance_qa": guidance_qa,
    "next_actions": next_actions,
}

__all__ = [
    "GRAPH_MODULES",
    "forms_draft",
    "guidance_qa",
    "iht_narration",
    "knowledge_ingest",
    "next_actions",
]
