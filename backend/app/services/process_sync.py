"""Keep process steps and their linked tasks in step.

The Section 25 seeding creates one task per timeline step (linked by
task.process_step_id), and users act on whichever surface is natural:
ticking the task off the task list, or moving the step on the timeline.
The two must never disagree, so:

- task -> step: a step's stored status is recomputed from ALL its live
  linked tasks (all done -> done; any progress -> in_progress; else
  not_started). Steps with no linked tasks are untouched.
- step -> tasks: a step status change is applied to every live linked
  task (done -> done, in_progress -> in_progress, blocked -> blocked,
  not_started -> todo).

Both directions emit their own audit events so the trail shows the
mirrored change as well as the user's original one.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProcessStep, Task
from app.models.base import utcnow
from app.services.seeding import record_audit

TASK_DONE = "done"
_STEP_TO_TASK_STATUS = {
    "done": "done",
    "in_progress": "in_progress",
    "blocked": "blocked",
    "not_started": "todo",
}


async def _live_linked_tasks(session: AsyncSession, step_id: uuid.UUID) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.process_step_id == step_id)
        .where(Task.archived_at.is_(None))
    )
    return list(result.scalars().all())


async def sync_step_from_tasks(
    session: AsyncSession, step_id: uuid.UUID, actor: str
) -> ProcessStep | None:
    """Recompute a step's status from its linked tasks (task -> step)."""
    step = await session.get(ProcessStep, step_id)
    if step is None or step.archived_at is not None:
        return None
    tasks = await _live_linked_tasks(session, step_id)
    if not tasks:
        return None
    statuses = [(task.status or "").lower() for task in tasks]
    if all(s == TASK_DONE for s in statuses):
        new_status = "done"
    elif any(s in (TASK_DONE, "in_progress", "blocked") for s in statuses):
        new_status = "in_progress"
    else:
        new_status = "not_started"
    if step.status == new_status:
        return step
    before = {"status": step.status}
    step.status = new_status
    step.updated_at = utcnow()
    session.add(step)
    await session.flush()
    await record_audit(
        session,
        step.estate_id,
        actor,
        "update",
        f"process_step:{step.id}",
        before=before,
        after={"status": new_status, "synced_from": "linked tasks"},
    )
    return step


async def sync_tasks_from_step(
    session: AsyncSession, step: ProcessStep, actor: str
) -> list[Task]:
    """Apply a step's status to its linked tasks (step -> tasks)."""
    target = _STEP_TO_TASK_STATUS.get((step.status or "").lower())
    if target is None:
        return []
    changed: list[Task] = []
    for task in await _live_linked_tasks(session, step.id):
        if (task.status or "").lower() == target:
            continue
        before = {"status": task.status}
        task.status = target
        task.updated_at = utcnow()
        session.add(task)
        await session.flush()
        await record_audit(
            session,
            task.estate_id,
            actor,
            "update",
            f"task:{task.id}",
            before=before,
            after={"status": target, "synced_from": f"process_step:{step.id}"},
        )
        changed.append(task)
    return changed
