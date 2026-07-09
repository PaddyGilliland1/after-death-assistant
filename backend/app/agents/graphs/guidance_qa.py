"""guidance_qa graph: cited Q&A over the cached official corpus only.

Shares its behaviour with POST /knowledge/qa through that router's seams
rather than duplicating them: retrieval is app.api.knowledge.hybrid_search
(via the search_guidance tool), the extracts-only/cite/refuse rules are
the same _QA_SYSTEM_PROMPT, and the model call goes through the same
_call_llm seam, so one monkeypatch (and one set of rules) governs both.

No approval interrupt (AGENT_DESIGN.md 2.4): answers are informational
and cited, never outbound artefacts; the corpus restriction and the
mandatory citations are the guardrails.
"""

import uuid
from functools import partial

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents import tools
from app.agents.tools import AgentContext
from app.api import knowledge as knowledge_api
from app.schemas.knowledge import QASource

QA_TOP_CHUNKS = knowledge_api.QA_TOP_CHUNKS
REFUSAL_TEXT = knowledge_api.REFUSAL_TEXT


class GuidanceQAState(BaseModel):
    """Typed state for one guidance question."""

    question: str
    hits: list[dict] = Field(default_factory=list)
    answer: str = ""
    sources: list[QASource] = Field(default_factory=list)
    refused: bool = False


async def _retrieve_node(ctx: AgentContext, state: GuidanceQAState) -> dict:
    hits = await tools.search_guidance(ctx, state.question, QA_TOP_CHUNKS)
    return {"hits": [hit.model_dump(mode="json") for hit in hits]}


def _route_after_retrieve(state: GuidanceQAState) -> str:
    return "answer" if state.hits else "refuse"


def _refuse_node(state: GuidanceQAState) -> dict:
    return {"answer": REFUSAL_TEXT, "refused": True, "sources": []}


async def _answer_node(ctx: AgentContext, state: GuidanceQAState) -> dict:
    sources = [
        QASource(
            n=number,
            doc_title=hit["doc_title"],
            source_url=hit["source_url"],
            form_code=hit.get("form_code"),
        )
        for number, hit in enumerate(state.hits, start=1)
    ]
    extracts = "\n\n".join(
        f"[{number}] From \"{hit['doc_title']}\" ({hit['source_url']}):\n{hit['chunk_text']}"
        for number, hit in enumerate(state.hits, start=1)
    )
    user_prompt = f"Extracts:\n\n{extracts}\n\nQuestion: {state.question}"
    answer = knowledge_api._call_llm(
        knowledge_api._QA_SYSTEM_PROMPT, user_prompt, ctx.settings
    )
    refused = REFUSAL_TEXT in answer
    return {"answer": answer, "refused": refused, "sources": [] if refused else sources}


def build_graph(ctx: AgentContext):
    """Compile the read-only Q&A graph (no interrupt by design)."""
    graph = StateGraph(GuidanceQAState)
    graph.add_node("retrieve", partial(_retrieve_node, ctx))
    graph.add_node("answer", partial(_answer_node, ctx))
    graph.add_node("refuse", _refuse_node)
    graph.set_entry_point("retrieve")
    graph.add_conditional_edges("retrieve", _route_after_retrieve)
    graph.add_edge("answer", END)
    graph.add_edge("refuse", END)
    return graph.compile()


async def run_guidance_qa(ctx: AgentContext, question: str) -> GuidanceQAState:
    """Answer one question over the cached corpus, or refuse with the
    shared refusal text."""
    app = build_graph(ctx)
    result = await app.ainvoke(
        GuidanceQAState(question=question).model_dump(),
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    return GuidanceQAState.model_validate(result)
