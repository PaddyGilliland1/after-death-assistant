"""Veteran and service benefits checklist (Module 18, contract section 8).

The checklist ships as generic, synthetic RAF and armed-forces content in
seed_templates/veteran_checklist.json (no personal data). This module
loads it, seeds one tracking task per item (source "veteran", idempotent
by title plus source) and exposes a small router the app integrator
includes alongside the API routers:

- GET  /veteran/checklist   items with their tracking-task status
- POST /veteran/seed-tasks  create the missing tasks (write roles)
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.estate import get_estate_or_404
from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import Task
from app.schemas.registers import snapshot
from app.schemas.trackers import (
    VeteranChecklistEntry,
    VeteranChecklistItem,
    VeteranSeedResult,
)
from app.services.seeding import record_audit

logger = logging.getLogger(__name__)

VETERAN_TASK_SOURCE = "veteran"

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_VETERAN_CHECKLIST_PATH = _BACKEND_DIR / "seed_templates" / "veteran_checklist.json"


def load_veteran_checklist(
    checklist_path: Path | None = None,
) -> list[VeteranChecklistItem]:
    """Read and validate the checklist template, sorted by order."""
    path = checklist_path or DEFAULT_VETERAN_CHECKLIST_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = [VeteranChecklistItem.model_validate(entry) for entry in raw]
    return sorted(items, key=lambda item: item.order)


async def _existing_veteran_tasks(
    session: AsyncSession, estate_id: uuid.UUID
) -> dict[str, Task]:
    """Veteran-sourced tasks for the estate, keyed by title."""
    stmt = (
        select(Task)
        .where(Task.estate_id == estate_id)
        .where(Task.source == VETERAN_TASK_SOURCE)
        .order_by(Task.created_at)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.title: row for row in rows}


async def seed_veteran_tasks(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    checklist_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Create one task per checklist item not already tracked.

    Idempotent by title plus source ("veteran"). Every created task is
    audited. The caller commits. Returns (created, skipped) titles.
    """
    items = load_veteran_checklist(checklist_path)
    existing = await _existing_veteran_tasks(session, estate_id)

    created: list[str] = []
    skipped: list[str] = []
    for item in items:
        if item.title in existing:
            skipped.append(item.title)
            continue
        description = item.description if item.url is None else f"{item.description} ({item.url})"
        task = Task(
            estate_id=estate_id,
            title=item.title,
            description=description,
            status="todo",
            source=VETERAN_TASK_SOURCE,
            created_by=actor,
        )
        session.add(task)
        await session.flush()
        await record_audit(
            session, estate_id, actor, "create", f"task:{task.id}", None, snapshot(task)
        )
        created.append(item.title)
    logger.info(
        "Veteran checklist seed for estate %s: %d created, %d skipped",
        estate_id,
        len(created),
        len(skipped),
    )
    return created, skipped


# ---------------------------------------------------------------------------
# Router (included by the app integrator alongside the API routers)
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/veteran", tags=["veteran"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/checklist", response_model=list[VeteranChecklistEntry])
async def veteran_checklist(
    session: SessionDep, user: ReadUser
) -> list[VeteranChecklistEntry]:
    """The checklist items with the status of their tracking tasks."""
    estate = await get_estate_or_404(session)
    items = load_veteran_checklist()
    existing = await _existing_veteran_tasks(session, estate.id)
    entries: list[VeteranChecklistEntry] = []
    for item in items:
        task = existing.get(item.title)
        entries.append(
            VeteranChecklistEntry(
                **item.model_dump(),
                task_id=task.id if task else None,
                task_status=task.status if task else None,
            )
        )
    return entries


@router.post("/seed-tasks", response_model=VeteranSeedResult)
async def seed_veteran_checklist_tasks(
    session: SessionDep, user: WriteUser
) -> VeteranSeedResult:
    """Create the missing veteran checklist tasks (idempotent)."""
    estate = await get_estate_or_404(session)
    created, skipped = await seed_veteran_tasks(session, estate.id, user.email)
    await session.commit()
    return VeteranSeedResult(created=created, skipped=skipped)
