"""next_actions graph: propose tasks and dependencies from process state.

Deterministic by design: suggestions come from rules over the process
timeline, deadlines and the contact notification tracker (no LLM, so the
graph works in full without an API key and no model can invent work).

Suggestions are a DRAFT: they are stored with an approval-pending row and
the graph interrupts before finalisation. They become real tasks (source
"agent_suggested") ONLY when an executor accepts them through the
approval endpoint (AGENT_DESIGN.md 2.5).
"""

import datetime as dt
import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents import tools
from app.agents.tools import AgentContext
from app.schemas.agents import TaskSuggestion

FINALISE_NODE = "finalise"
DRAFT_KIND = "task_suggestions"
TASK_SOURCE = "agent_suggested"

# A deadline within this window prompts a preparation task.
DEADLINE_HORIZON_DAYS = 60
# Suggested lead time before the deadline itself.
PREPARATION_LEAD_DAYS = 14

_OPEN_STEP_STATUSES = ("", "not_started", "in_progress", "blocked")
_OPEN_TASK_STATUSES = ("", "not_started", "in_progress", "blocked", "open", "todo")


class NextActionsState(BaseModel):
    """Typed state for one suggestion run."""

    suggestions: list[TaskSuggestion] = Field(default_factory=list)
    document_id: str | None = None
    approval_id: str | None = None


async def _propose_node(ctx: AgentContext, state: NextActionsState) -> dict:
    """Deterministic proposal rules over the current process state."""
    today = tools.utc_today()
    existing_tasks = await tools.read_tasks(ctx)
    open_titles = {
        (task.title or "").strip().lower()
        for task in existing_tasks
        if ((task.status or "").strip().lower()) in _OPEN_TASK_STATUSES
    }
    steps_with_tasks = {
        task.process_step_id for task in existing_tasks if task.process_step_id is not None
    }

    suggestions: list[TaskSuggestion] = []

    def add(suggestion: TaskSuggestion) -> int | None:
        """Add unless an open task or an earlier suggestion already covers it."""
        key = suggestion.title.strip().lower()
        if key in open_titles:
            return None
        if any(existing.title.strip().lower() == key for existing in suggestions):
            return None
        suggestions.append(suggestion)
        return len(suggestions) - 1

    # 1. Unnotified contacts that require notification.
    for contact in await tools.read_contacts(ctx):
        notified = contact.notified_date is not None or (
            (contact.notification_status or "").strip().lower() == "notified"
        )
        if contact.notify_required and not notified:
            references = ", ".join(contact.references) if contact.references else "none held"
            add(
                TaskSuggestion(
                    title=f"Notify {contact.name} of the death",
                    description=(
                        f"Send the notification with the account references on file "
                        f"({references}) and request date of death balances. "
                        "Draft the letter with the letter drafting assistant; "
                        "a person reviews and sends it."
                    ),
                    priority="high",
                    source_ref=f"contact:{contact.id}",
                )
            )

    # 2. Approaching deadlines get a preparation task.
    for deadline in await tools.read_deadlines(ctx):
        if deadline.derived_date is None:
            continue
        days_away = (deadline.derived_date - today).days
        if 0 <= days_away <= DEADLINE_HORIZON_DAYS:
            label = deadline.type.replace("_", " ")
            add(
                TaskSuggestion(
                    title=f"Prepare for the {label} deadline",
                    description=(
                        f"The {label} deadline falls on {deadline.derived_date.isoformat()}. "
                        "Gather what is needed ahead of it."
                    ),
                    due_date=max(
                        deadline.derived_date - dt.timedelta(days=PREPARATION_LEAD_DAYS), today
                    ),
                    priority="high",
                    source_ref=f"deadline:{deadline.id}",
                )
            )

    # 3. Open process steps with no linked task, chained in timeline order.
    previous_step_index: int | None = None
    for step in await tools.read_process_steps(ctx):
        status = (step.status or "").strip().lower()
        if status not in _OPEN_STEP_STATUSES:
            continue
        if step.id in steps_with_tasks:
            continue
        index = add(
            TaskSuggestion(
                title=f"Progress step: {step.name}",
                description=f"Process step {step.order} ({step.name}) has no task yet.",
                depends_on=[previous_step_index] if previous_step_index is not None else [],
                source_ref=f"process_step:{step.id}",
            )
        )
        if index is not None:
            previous_step_index = index

    return {"suggestions": suggestions}


async def _store_draft_node(ctx: AgentContext, state: NextActionsState) -> dict:
    payload = {
        "suggestions": [item.model_dump(mode="json") for item in state.suggestions]
    }
    document = await tools.store_draft_document(
        ctx, title="Suggested tasks (draft)", payload=payload, draft_kind=DRAFT_KIND
    )
    approval = await tools.create_pending_approval(
        ctx, entity_ref=f"document:{document.id}", draft_kind=DRAFT_KIND
    )
    return {"document_id": str(document.id), "approval_id": str(approval.id)}


def _finalise_node(state: NextActionsState) -> dict:
    """Post-interrupt no-op: suggestions become tasks only through the
    approval endpoint."""
    return {}


def build_graph(ctx: AgentContext):
    """Compile with the interrupt before suggestions could become tasks."""
    graph = StateGraph(NextActionsState)
    graph.add_node("propose", partial(_propose_node, ctx))
    graph.add_node("store_draft", partial(_store_draft_node, ctx))
    graph.add_node(FINALISE_NODE, _finalise_node)
    graph.set_entry_point("propose")
    graph.add_edge("propose", "store_draft")
    graph.add_edge("store_draft", FINALISE_NODE)
    graph.add_edge(FINALISE_NODE, END)
    return graph.compile(checkpointer=MemorySaver(), interrupt_before=[FINALISE_NODE])


async def run_next_actions(ctx: AgentContext) -> NextActionsState:
    """Run to the human-review interrupt and return the suggestions."""
    app = build_graph(ctx)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = await app.ainvoke(NextActionsState().model_dump(), config)
    return NextActionsState.model_validate(result)
