"""Digital assets, subscriptions and memberships router (Module 17).

CRUD on digital_item at /digital-items (contract section 8) plus
GET /digital/recurring-total, the sum of stored recurring amounts for
active items. The total is an aggregation of stored figures only;
payment frequency is not normalised and nothing is computed beyond the
sum. Conventions match the P1 register routers.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import DigitalItem, Estate
from app.models.base import utcnow
from app.schemas.registers import snapshot
from app.schemas.trackers import (
    DigitalItemCreate,
    DigitalItemRead,
    DigitalItemUpdate,
    RecurringTotalRead,
)
from app.services.seeding import record_audit

router = APIRouter(tags=["digital"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Statuses that mean the item no longer incurs its recurring cost.
INACTIVE_STATUSES = frozenset({"cancelled", "closed", "transferred", "done"})

RECURRING_TOTAL_NOTE = (
    "Sum of the stored recurring amounts for active items. Amounts are "
    "summed as stored; payment frequency is not normalised."
)


async def _require_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    if await session.get(Estate, estate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estate not found.")


async def _get_item(session: AsyncSession, item_id: uuid.UUID) -> DigitalItem:
    row = await session.get(DigitalItem, item_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Digital item not found.")
    return row


def _is_active(row: DigitalItem) -> bool:
    return row.archived_at is None and (
        row.status is None or row.status.strip().lower() not in INACTIVE_STATUSES
    )


@router.get("/digital/recurring-total", response_model=RecurringTotalRead)
async def recurring_total(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
) -> RecurringTotalRead:
    """Total recurring spend still running: the sum of recurring_amount
    across active (not archived, not cancelled or closed) items."""
    stmt = (
        select(DigitalItem)
        .where(DigitalItem.archived_at.is_(None))
        .where(DigitalItem.recurring_amount.is_not(None))
    )
    if estate_id is not None:
        stmt = stmt.where(DigitalItem.estate_id == estate_id)
    rows = [row for row in (await session.execute(stmt)).scalars().all() if _is_active(row)]
    total = sum((row.recurring_amount for row in rows), Decimal("0"))
    return RecurringTotalRead(
        recurring_total=total, item_count=len(rows), note=RECURRING_TOTAL_NOTE
    )


@router.get("/digital-items", response_model=list[DigitalItemRead])
async def list_digital_items(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    status: str | None = None,
) -> list[DigitalItem]:
    stmt = select(DigitalItem)
    if estate_id is not None:
        stmt = stmt.where(DigitalItem.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(DigitalItem.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(DigitalItem.status == status)
    stmt = stmt.order_by(DigitalItem.created_at.desc(), DigitalItem.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/digital-items/{item_id}", response_model=DigitalItemRead)
async def get_digital_item(
    item_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> DigitalItem:
    return await _get_item(session, item_id)


@router.post(
    "/digital-items", response_model=DigitalItemRead, status_code=status.HTTP_201_CREATED
)
async def create_digital_item(
    payload: DigitalItemCreate, session: SessionDep, user: WriteUser
) -> DigitalItem:
    await _require_estate(session, payload.estate_id)
    row = DigitalItem(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    await record_audit(
        session, row.estate_id, user.email, "create", f"digital_item:{row.id}", None, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/digital-items/{item_id}", response_model=DigitalItemRead)
async def update_digital_item(
    item_id: uuid.UUID, payload: DigitalItemUpdate, session: SessionDep, user: WriteUser
) -> DigitalItem:
    row = await _get_item(session, item_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "update", f"digital_item:{row.id}",
        before, snapshot(row),
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/digital-items/{item_id}", response_model=DigitalItemRead)
async def archive_digital_item(
    item_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> DigitalItem:
    row = await _get_item(session, item_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Digital item is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "archive", f"digital_item:{row.id}",
        before, snapshot(row),
    )
    await session.commit()
    await session.refresh(row)
    return row
