"""IHT schedule task seeding (contract section 8, Module 9 support).

POST /iht/schedules/seed-tasks reads the required_schedules list from
the latest stored IHT assessment (the deterministic engine's output;
nothing is recomputed here) and creates one tracking task per schedule
not already tracked. Idempotent by title plus source ("iht_schedule"):
running it twice creates nothing new. Write roles only; every created
task is audited.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.estate import get_estate_or_404
from app.core.auth import WriteUser
from app.db import get_session
from app.models import Task
from app.schemas.registers import snapshot
from app.schemas.trackers import ScheduleSeedResult
from app.services.reevaluation import latest_assessment
from app.services.seeding import record_audit

router = APIRouter(prefix="/iht/schedules", tags=["iht"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SCHEDULE_TASK_SOURCE = "iht_schedule"


def schedule_task_title(code: str) -> str:
    return f"Complete schedule {code}"


@router.post("/seed-tasks", response_model=ScheduleSeedResult)
async def seed_schedule_tasks(session: SessionDep, user: WriteUser) -> ScheduleSeedResult:
    """Create one task per required schedule from the latest assessment."""
    estate = await get_estate_or_404(session)
    latest = await latest_assessment(session, estate.id)
    if latest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No IHT assessment has been computed yet. POST /iht/recompute first.",
        )
    codes = list((latest.snapshot or {}).get("result", {}).get("required_schedules", []))

    existing_stmt = (
        select(Task.title)
        .where(Task.estate_id == estate.id)
        .where(Task.source == SCHEDULE_TASK_SOURCE)
    )
    existing_titles = set((await session.execute(existing_stmt)).scalars().all())

    created: list[str] = []
    skipped: list[str] = []
    for code in codes:
        title = schedule_task_title(code)
        if title in existing_titles:
            skipped.append(title)
            continue
        task = Task(
            estate_id=estate.id,
            title=title,
            description=(
                f"Complete supplementary schedule {code} required by the "
                "latest IHT assessment."
            ),
            status="todo",
            source=SCHEDULE_TASK_SOURCE,
            created_by=user.email,
        )
        session.add(task)
        await session.flush()
        await record_audit(
            session, estate.id, user.email, "create", f"task:{task.id}", None, snapshot(task)
        )
        created.append(title)
        existing_titles.add(title)

    await session.commit()
    return ScheduleSeedResult(created=created, skipped=skipped)
