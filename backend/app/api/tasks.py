"""Tasks router: CRUD, dependencies, checklists and comments.

blocked_by and blocks hold task UUIDs as strings. On every create or
update the referenced tasks are checked to exist in the same estate,
self-references are rejected, and the dependency graph is walked to
reject cycles. A task with any open blocking task cannot move to done
(409, with the blocking list). Tasks flagged executor_private are never
returned to the viewer role. Writes emit audit events; soft delete only.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, Role, WriteUser
from app.db import get_session
from app.models import AuditEvent, Estate, Task, TaskComment
from app.models.base import utcnow
from app.schemas.tasks_costs import (
    TaskCommentCreate,
    TaskCommentRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

DONE_STATUS = "done"


def _snapshot(row: Task) -> dict:
    return TaskRead.model_validate(row).model_dump(mode="json")


def _audit(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            estate_id=estate_id,
            actor=actor,
            action=action,
            entity=entity,
            before=before,
            after=after,
            created_by=actor,
        )
    )


async def _ensure_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    estate = await session.get(Estate, estate_id)
    if estate is None or estate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Estate not found.")


async def _get_task_or_404(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _parse_dependency_ids(values: list[str], field: str) -> list[str]:
    parsed: list[str] = []
    for value in values:
        try:
            parsed.append(str(uuid.UUID(value)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{field} entry {value!r} is not a valid task UUID.",
            ) from exc
    return parsed


async def _validate_dependencies(
    session: AsyncSession,
    estate_id: uuid.UUID,
    task_id: uuid.UUID,
    blocked_by: list[str],
    blocks: list[str],
) -> None:
    """Check referenced tasks exist, and reject self-reference and cycles."""
    blocked_by = _parse_dependency_ids(blocked_by, "blocked_by")
    blocks = _parse_dependency_ids(blocks, "blocks")
    referenced = set(blocked_by) | set(blocks)
    if not referenced:
        return
    if str(task_id) in referenced:
        raise HTTPException(status_code=422, detail="A task cannot reference itself.")

    result = await session.execute(
        select(Task.id).where(
            Task.estate_id == estate_id,
            Task.archived_at.is_(None),
            Task.id.in_([uuid.UUID(r) for r in referenced]),
        )
    )
    found = {str(row) for row in result.scalars().all()}
    missing = sorted(referenced - found)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Referenced tasks do not exist in this estate: {', '.join(missing)}.",
        )

    # Build the dependency graph (edge task -> each task it is blocked by)
    # for the whole estate, overlay the candidate lists, and walk it.
    rows = await session.execute(
        select(Task.id, Task.blocked_by, Task.blocks).where(
            Task.estate_id == estate_id, Task.archived_at.is_(None)
        )
    )
    deps: dict[str, set[str]] = {}
    for other_id, other_blocked_by, other_blocks in rows.all():
        other_key = str(other_id)
        if other_key == str(task_id):
            continue  # replaced by the candidate lists below
        deps.setdefault(other_key, set()).update(other_blocked_by or [])
        for blocked in other_blocks or []:
            if blocked != str(task_id):
                deps.setdefault(blocked, set()).add(other_key)
    deps.setdefault(str(task_id), set()).update(blocked_by)
    for blocked in blocks:
        deps.setdefault(blocked, set()).add(str(task_id))

    start = str(task_id)
    stack = list(deps.get(start, ()))
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == start:
            raise HTTPException(
                status_code=422,
                detail="Dependency cycle detected: these links would make the task "
                "depend on itself.",
            )
        if current in seen:
            continue
        seen.add(current)
        stack.extend(deps.get(current, ()))


async def _open_blockers(session: AsyncSession, blocked_by: list[str]) -> list[str]:
    """Return the ids of blocking tasks that are still open (not done)."""
    if not blocked_by:
        return []
    result = await session.execute(
        select(Task.id).where(
            Task.id.in_([uuid.UUID(b) for b in blocked_by]),
            Task.archived_at.is_(None),
            (Task.status.is_(None)) | (Task.status != DONE_STATUS),
        )
    )
    return sorted(str(row) for row in result.scalars().all())


def _reject_done_if_blocked(open_blockers: list[str]) -> None:
    if open_blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This task cannot move to done while it is blocked by "
                "open tasks.",
                "blocking": open_blockers,
            },
        )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    user: WriteUser,
    session: SessionDep,
) -> Task:
    """Create a task, validating any dependency links."""
    await _ensure_estate(session, payload.estate_id)
    task_id = uuid.uuid4()
    await _validate_dependencies(
        session, payload.estate_id, task_id, payload.blocked_by, payload.blocks
    )
    if payload.status == DONE_STATUS:
        _reject_done_if_blocked(await _open_blockers(session, payload.blocked_by))
    data = payload.model_dump()
    data["checklist"] = [item.model_dump() for item in payload.checklist]
    task = Task(**data, id=task_id, created_by=user.email)
    session.add(task)
    await session.flush()
    _audit(
        session, task.estate_id, user.email, "create", f"task:{task.id}", after=_snapshot(task)
    )
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
    due_before: dt.date | None = None,
    assignee: str | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    include_archived: bool = False,
) -> list[Task]:
    """List tasks with due_before, assignee and status filters.
    executor_private tasks are excluded when the caller is a viewer."""
    stmt = select(Task).order_by(Task.created_at)
    if not include_archived:
        stmt = stmt.where(Task.archived_at.is_(None))
    if estate_id is not None:
        stmt = stmt.where(Task.estate_id == estate_id)
    if due_before is not None:
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date < due_before)
    if status_value is not None:
        stmt = stmt.where(Task.status == status_value)
    if user.role == Role.VIEWER:
        stmt = stmt.where(Task.executor_private.is_(False))
    result = await session.execute(stmt)
    tasks = list(result.scalars().all())
    if assignee is not None:
        # assignees is a JSON list; membership is filtered in Python to stay
        # portable across JSON column implementations.
        tasks = [t for t in tasks if assignee in (t.assignees or [])]
    return tasks


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> Task:
    """Fetch a single task. executor_private tasks are hidden from viewers."""
    task = await _get_task_or_404(session, task_id)
    if user.role == Role.VIEWER and task.executor_private:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    user: WriteUser,
    session: SessionDep,
) -> Task:
    """Partially update a task, revalidating dependencies and the done rule."""
    task = await _get_task_or_404(session, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return task
    new_blocked_by = changes.get("blocked_by", task.blocked_by) or []
    new_blocks = changes.get("blocks", task.blocks) or []
    if "blocked_by" in changes or "blocks" in changes:
        await _validate_dependencies(
            session, task.estate_id, task.id, new_blocked_by, new_blocks
        )
    if changes.get("status") == DONE_STATUS:
        _reject_done_if_blocked(await _open_blockers(session, new_blocked_by))
    before = _snapshot(task)
    if "checklist" in changes and payload.checklist is not None:
        changes["checklist"] = [item.model_dump() for item in payload.checklist]
    for field, value in changes.items():
        setattr(task, field, value)
    task.updated_at = utcnow()
    session.add(task)
    await session.flush()
    _audit(
        session,
        task.estate_id,
        user.email,
        "update",
        f"task:{task.id}",
        before=before,
        after=_snapshot(task),
    )
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", response_model=TaskRead)
async def archive_task(
    task_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Task:
    """Soft delete: archive the task. Nothing is physically deleted."""
    task = await _get_task_or_404(session, task_id)
    if task.archived_at is not None:
        raise HTTPException(status_code=409, detail="Task is already archived.")
    before = _snapshot(task)
    task.archived_at = utcnow()
    task.archive_reason = reason
    task.updated_at = utcnow()
    session.add(task)
    await session.flush()
    _audit(
        session,
        task.estate_id,
        user.email,
        "archive",
        f"task:{task.id}",
        before=before,
        after=_snapshot(task),
    )
    await session.commit()
    await session.refresh(task)
    return task


@router.post(
    "/{task_id}/comments",
    response_model=TaskCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    task_id: uuid.UUID,
    payload: TaskCommentCreate,
    user: WriteUser,
    session: SessionDep,
) -> TaskComment:
    """Add a comment to a task."""
    task = await _get_task_or_404(session, task_id)
    comment = TaskComment(
        estate_id=task.estate_id,
        task_id=task.id,
        body=payload.body,
        created_by=user.email,
    )
    session.add(comment)
    await session.flush()
    _audit(
        session,
        task.estate_id,
        user.email,
        "create",
        f"task_comment:{comment.id}",
        after=TaskCommentRead.model_validate(comment).model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(comment)
    return comment


@router.get("/{task_id}/comments", response_model=list[TaskCommentRead])
async def list_comments(
    task_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> list[TaskComment]:
    """List comments on a task. Comments on executor_private tasks are hidden
    from viewers along with the task itself."""
    task = await _get_task_or_404(session, task_id)
    if user.role == Role.VIEWER and task.executor_private:
        raise HTTPException(status_code=404, detail="Task not found.")
    result = await session.execute(
        select(TaskComment)
        .where(TaskComment.task_id == task_id, TaskComment.archived_at.is_(None))
        .order_by(TaskComment.created_at)
    )
    return list(result.scalars().all())
