"""Reliefs and reclaims tracker router (Module 14, contract section 8).

CRUD on the relief register plus GET /reliefs/watchlist for windows
closing within 90 days. Conventions match the P1 register routers:
estate-scoped lists, soft delete with the reason in the request body,
audit on every write, viewer read-only.

Figures: window_deadline derives from the estate's date of death (the
statutory sale windows for IHT35 and IHT38; app.domain.deadlines has no
function for these yet, so the derivation lives in
app.schemas.trackers.derive_relief_window with its basis string).
potential_reclaim is either stored as given or derived as probate_value
minus sale_value floored at zero, a subtraction of stored figures only;
the actual reclaim depends on the estate rate and is never computed.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import Estate, Relief
from app.models.base import utcnow
from app.models.enums import ReliefType
from app.schemas.registers import snapshot
from app.schemas.trackers import (
    RECLAIM_NOTE,
    ReliefCreate,
    ReliefRead,
    ReliefUpdate,
    ReliefWatchlistItem,
    derive_potential_reclaim,
    derive_relief_window,
)
from app.services.seeding import record_audit

router = APIRouter(prefix="/reliefs", tags=["reliefs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

WATCHLIST_WINDOW_DAYS = 90


async def _require_estate(session: AsyncSession, estate_id: uuid.UUID) -> Estate:
    estate = await session.get(Estate, estate_id)
    if estate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estate not found.")
    return estate


async def _get_relief(session: AsyncSession, relief_id: uuid.UUID) -> Relief:
    row = await session.get(Relief, relief_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relief not found.")
    return row


def _apply_derivations(row: Relief, date_of_death: dt.date | None) -> None:
    """Fill window_deadline and potential_reclaim where not stored.

    Stored input always wins: derivation only fills fields the caller
    left empty.
    """
    if row.window_deadline is None:
        derived = derive_relief_window(row.relief_type, date_of_death)
        if derived is not None:
            row.window_deadline = derived[0]
    if row.potential_reclaim is None:
        row.potential_reclaim = derive_potential_reclaim(row.probate_value, row.sale_value)


def _to_read(row: Relief, date_of_death: dt.date | None) -> ReliefRead:
    """Attach the derived context (window basis, reclaim note) on read."""
    read = ReliefRead.model_validate(row, from_attributes=True)
    derived = derive_relief_window(row.relief_type, date_of_death)
    if derived is not None and row.window_deadline == derived[0]:
        read.window_basis = derived[1]
    if row.potential_reclaim is not None and row.probate_value is not None:
        read.reclaim_note = RECLAIM_NOTE
    return read


async def _dod_by_estate(
    session: AsyncSession, rows: list[Relief]
) -> dict[uuid.UUID, dt.date | None]:
    dods: dict[uuid.UUID, dt.date | None] = {}
    for estate_id in {row.estate_id for row in rows}:
        estate = await session.get(Estate, estate_id)
        dods[estate_id] = estate.date_of_death if estate else None
    return dods


@router.get("", response_model=list[ReliefRead])
async def list_reliefs(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    relief_type: ReliefType | None = None,
    status: str | None = None,
) -> list[ReliefRead]:
    stmt = select(Relief)
    if estate_id is not None:
        stmt = stmt.where(Relief.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(Relief.archived_at.is_(None))
    if relief_type is not None:
        stmt = stmt.where(Relief.relief_type == relief_type)
    if status is not None:
        stmt = stmt.where(Relief.status == status)
    stmt = stmt.order_by(Relief.created_at.desc(), Relief.id)
    rows = list((await session.execute(stmt)).scalars().all())
    dods = await _dod_by_estate(session, rows)
    return [_to_read(row, dods[row.estate_id]) for row in rows]


@router.get("/watchlist", response_model=list[ReliefWatchlistItem])
async def relief_watchlist(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
) -> list[ReliefWatchlistItem]:
    """Reliefs whose window_deadline falls within the next 90 days
    (overdue windows included), ordered soonest first."""
    today = dt.date.today()
    horizon = today + dt.timedelta(days=WATCHLIST_WINDOW_DAYS)
    stmt = (
        select(Relief)
        .where(Relief.archived_at.is_(None))
        .where(Relief.window_deadline.is_not(None))
        .where(Relief.window_deadline <= horizon)
        .order_by(Relief.window_deadline, Relief.created_at)
    )
    if estate_id is not None:
        stmt = stmt.where(Relief.estate_id == estate_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ReliefWatchlistItem(
            id=row.id,
            estate_id=row.estate_id,
            relief_type=row.relief_type,
            asset_id=row.asset_id,
            window_deadline=row.window_deadline,
            days_remaining=(row.window_deadline - today).days,
            potential_reclaim=row.potential_reclaim,
            status=row.status,
        )
        for row in rows
    ]


@router.get("/{relief_id}", response_model=ReliefRead)
async def get_relief(
    relief_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> ReliefRead:
    row = await _get_relief(session, relief_id)
    estate = await session.get(Estate, row.estate_id)
    return _to_read(row, estate.date_of_death if estate else None)


@router.post("", response_model=ReliefRead, status_code=status.HTTP_201_CREATED)
async def create_relief(
    payload: ReliefCreate, session: SessionDep, user: WriteUser
) -> ReliefRead:
    estate = await _require_estate(session, payload.estate_id)
    row = Relief(**payload.model_dump(), created_by=user.email)
    _apply_derivations(row, estate.date_of_death)
    session.add(row)
    await session.flush()
    await record_audit(
        session, row.estate_id, user.email, "create", f"relief:{row.id}", None, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return _to_read(row, estate.date_of_death)


@router.patch("/{relief_id}", response_model=ReliefRead)
async def update_relief(
    relief_id: uuid.UUID, payload: ReliefUpdate, session: SessionDep, user: WriteUser
) -> ReliefRead:
    row = await _get_relief(session, relief_id)
    estate = await session.get(Estate, row.estate_id)
    date_of_death = estate.date_of_death if estate else None
    before = snapshot(row)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)

    # Re-derive when the driving facts changed and the caller did not
    # pin the derived field explicitly in this request.
    if ("relief_type" in changes or "sale_date" in changes) and "window_deadline" not in changes:
        derived = derive_relief_window(row.relief_type, date_of_death)
        if derived is not None:
            row.window_deadline = derived[0]
    if (
        ("probate_value" in changes or "sale_value" in changes)
        and "potential_reclaim" not in changes
    ):
        recomputed = derive_potential_reclaim(row.probate_value, row.sale_value)
        if recomputed is not None:
            row.potential_reclaim = recomputed

    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "update", f"relief:{row.id}", before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return _to_read(row, date_of_death)


@router.delete("/{relief_id}", response_model=ReliefRead)
async def archive_relief(
    relief_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> ReliefRead:
    row = await _get_relief(session, relief_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Relief is already archived.")
    estate = await session.get(Estate, row.estate_id)
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "archive", f"relief:{row.id}", before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return _to_read(row, estate.date_of_death if estate else None)
