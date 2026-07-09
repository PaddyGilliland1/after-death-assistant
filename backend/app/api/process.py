"""Process steps, the timeline view and the statutory deadlines engine.

- GET /process/steps: ordered list.
- PATCH /process/steps/{id}: status change only (audited).
- GET /process/timeline: steps joined with their deadline dates, with a
  derived status of done / current / upcoming.
- GET /deadlines: upcoming deadlines in date order.
- POST /deadlines/recompute: derive the statutory set from
  app.domain.deadlines using the estate's date of death, upserting
  deadline rows with citations kept in the reminders JSON.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.domain.deadlines import (
    StatutoryDeadline,
    cgt_60_day_deadline,
    gazette_claim_deadline,
    iht400_filing_due,
    iht_payment_due,
    isa_exemption_end,
)
from app.models import AdminTax, Asset, CreditorNotice, Deadline, Estate, ProcessStep
from app.models.base import utcnow
from app.schemas.collab import (
    DeadlineOut,
    DeadlineRecomputeOut,
    ProcessStepOut,
    ProcessStepPatch,
    TimelineEntryOut,
)
from app.services.seeding import get_active_estate, record_audit

router = APIRouter(tags=["process"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_DONE_STATUSES = frozenset({"done", "complete", "completed"})


async def _require_estate(session: AsyncSession) -> Estate:
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate is configured yet. Seed one first.",
        )
    return estate


async def _ordered_steps(session: AsyncSession, estate_id: uuid.UUID) -> list[ProcessStep]:
    result = await session.execute(
        select(ProcessStep)
        .where(ProcessStep.estate_id == estate_id, ProcessStep.archived_at.is_(None))
        .order_by(ProcessStep.order)
    )
    return list(result.scalars().all())


@router.get("/process/steps", response_model=list[ProcessStepOut])
async def list_process_steps(user: ReadUser, session: SessionDep) -> list[ProcessStep]:
    """All process steps in order."""
    estate = await _require_estate(session)
    return await _ordered_steps(session, estate.id)


@router.patch("/process/steps/{step_id}", response_model=ProcessStepOut)
async def patch_process_step(
    step_id: uuid.UUID,
    payload: ProcessStepPatch,
    user: WriteUser,
    session: SessionDep,
) -> ProcessStep:
    """Update a step's status. No other field is writable here."""
    step = await session.get(ProcessStep, step_id)
    if step is None or step.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Process step not found."
        )
    before = {"status": step.status}
    step.status = payload.status
    step.updated_at = utcnow()
    session.add(step)
    await session.flush()
    await record_audit(
        session,
        step.estate_id,
        user.email,
        "update",
        f"process_step:{step.id}",
        before=before,
        after={"status": payload.status},
    )
    from app.services.process_sync import sync_tasks_from_step

    await sync_tasks_from_step(session, step, user.email)
    await session.commit()
    return step


@router.get("/process/timeline", response_model=list[TimelineEntryOut])
async def timeline(user: ReadUser, session: SessionDep) -> list[TimelineEntryOut]:
    """Steps joined with their deadlines, with derived progress status.

    A step is done when its stored status says so; the first step that is
    not done is current; everything after it is upcoming.
    """
    estate = await _require_estate(session)
    steps = await _ordered_steps(session, estate.id)

    deadline_ids = [step.deadline_id for step in steps if step.deadline_id is not None]
    deadlines: dict[uuid.UUID, Deadline] = {}
    if deadline_ids:
        result = await session.execute(select(Deadline).where(Deadline.id.in_(deadline_ids)))
        deadlines = {row.id: row for row in result.scalars().all()}

    entries: list[TimelineEntryOut] = []
    current_seen = False
    for step in steps:
        if (step.status or "").lower() in _DONE_STATUSES:
            derived = "done"
        elif not current_seen:
            derived = "current"
            current_seen = True
        else:
            derived = "upcoming"
        deadline = deadlines.get(step.deadline_id) if step.deadline_id else None
        entries.append(
            TimelineEntryOut(
                step_id=step.id,
                order=step.order,
                name=step.name,
                stored_status=step.status,
                derived_status=derived,
                deadline_type=deadline.type if deadline else None,
                deadline_date=deadline.derived_date if deadline else None,
            )
        )
    return entries


@router.get("/deadlines", response_model=list[DeadlineOut])
async def list_deadlines(
    user: ReadUser,
    session: SessionDep,
    include_past: Annotated[bool, Query()] = False,
) -> list[Deadline]:
    """Deadlines in date order; past dates are excluded unless asked for."""
    estate = await _require_estate(session)
    query = select(Deadline).where(
        Deadline.estate_id == estate.id,
        Deadline.archived_at.is_(None),
        Deadline.derived_date.is_not(None),
    )
    if not include_past:
        query = query.where(Deadline.derived_date >= dt.date.today())
    result = await session.execute(query.order_by(Deadline.derived_date))
    return list(result.scalars().all())


def _citation(entry: StatutoryDeadline) -> list[dict]:
    return [
        {
            "kind": "citation",
            "basis": entry.basis,
            "derived_by": "app.domain.deadlines",
            "domain_name": entry.name,
        }
    ]


async def _derive_statutory_set(
    session: AsyncSession, estate: Estate
) -> list[tuple[str, StatutoryDeadline]]:
    """The statutory deadlines that currently apply to this estate."""
    dod = estate.date_of_death
    assert dod is not None  # checked by the caller
    items: list[tuple[str, StatutoryDeadline]] = [
        ("iht_payment", iht_payment_due(dod)),
        ("iht400_filing", iht400_filing_due(dod)),
    ]

    # Section 27 creditor notice, where one exists: use the later of the
    # Gazette and local paper dates (the window runs from the later notice).
    notices = await session.execute(
        select(CreditorNotice).where(
            CreditorNotice.estate_id == estate.id,
            CreditorNotice.archived_at.is_(None),
        )
    )
    notice_dates = [
        max(date for date in (notice.gazette_date, notice.local_date) if date is not None)
        for notice in notices.scalars()
        if notice.gazette_date is not None or notice.local_date is not None
    ]
    if notice_dates:
        items.append(("s27_claim", gazette_claim_deadline(max(notice_dates))))

    # ISA exemption end, where the estate holds an ISA.
    isa_assets = await session.execute(
        select(Asset).where(
            Asset.estate_id == estate.id,
            Asset.archived_at.is_(None),
            Asset.sub_type.ilike("%isa%") | Asset.category.ilike("%isa%"),
        )
    )
    if isa_assets.scalars().first() is not None:
        items.append(("isa_exemption_end", isa_exemption_end(dod)))

    # CGT 60-day deadlines for recorded residential disposals.
    admin_rows = await session.execute(
        select(AdminTax).where(
            AdminTax.estate_id == estate.id, AdminTax.archived_at.is_(None)
        )
    )
    index = 0
    for admin_row in admin_rows.scalars():
        for disposal in admin_row.cgt_disposals or []:
            raw_date = disposal.get("date") if isinstance(disposal, dict) else None
            if not raw_date:
                continue
            try:
                completion = dt.date.fromisoformat(str(raw_date))
            except ValueError:
                continue
            index += 1
            items.append((f"cgt_60_day_{index}", cgt_60_day_deadline(completion)))

    return items


@router.post("/deadlines/recompute", response_model=DeadlineRecomputeOut)
async def recompute_deadlines(user: WriteUser, session: SessionDep) -> DeadlineRecomputeOut:
    """Derive the statutory deadline set and upsert deadline rows."""
    estate = await _require_estate(session)
    if estate.date_of_death is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The estate has no date of death; deadlines cannot be derived.",
        )

    items = await _derive_statutory_set(session, estate)

    existing_result = await session.execute(
        select(Deadline).where(
            Deadline.estate_id == estate.id, Deadline.archived_at.is_(None)
        )
    )
    existing = {row.type: row for row in existing_result.scalars().all()}

    created = 0
    updated = 0
    rows: list[Deadline] = []
    for type_key, derived in items:
        row = existing.get(type_key)
        if row is None:
            row = Deadline(
                estate_id=estate.id,
                type=type_key,
                derived_date=derived.due_date,
                reminders=_citation(derived),
                created_by=user.email,
            )
            created += 1
        else:
            row.derived_date = derived.due_date
            row.reminders = _citation(derived)
            row.updated_at = utcnow()
            updated += 1
        session.add(row)
        rows.append(row)

    await session.flush()
    await record_audit(
        session,
        estate.id,
        user.email,
        "recompute",
        f"estate:{estate.id}",
        after={
            "deadlines": {key: derived.due_date.isoformat() for key, derived in items}
        },
    )
    await session.commit()

    rows.sort(key=lambda row: row.derived_date or dt.date.max)
    return DeadlineRecomputeOut(
        created=created,
        updated=updated,
        deadlines=[DeadlineOut.model_validate(row) for row in rows],
    )
