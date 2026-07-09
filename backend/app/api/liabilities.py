"""Liability register router: standard CRUD (contract section 8).

Same conventions as every register router: estate-scoped lists excluding
archived rows unless include_archived, newest first, soft delete only,
audit_event on every write, viewer read-only. Registers store and return
data; no figure is calculated here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, WriteUser
from app.db import get_session
from app.models import AuditEvent, Estate, Liability
from app.models.base import utcnow
from app.schemas.registers import (
    LiabilityCreate,
    LiabilityRead,
    LiabilityUpdate,
    snapshot,
)

router = APIRouter(prefix="/liabilities", tags=["liabilities"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _audit(
    session: AsyncSession,
    user: AuthenticatedUser,
    action: str,
    entity: str,
    estate_id: uuid.UUID,
    before: dict | None,
    after: dict | None,
) -> None:
    session.add(
        AuditEvent(
            estate_id=estate_id,
            actor=user.email,
            action=action,
            entity=entity,
            before=before,
            after=after,
            created_by=user.email,
        )
    )


async def _require_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    if await session.get(Estate, estate_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estate not found.")


async def _get_liability(session: AsyncSession, liability_id: uuid.UUID) -> Liability:
    row = await session.get(Liability, liability_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Liability not found.")
    return row


@router.get("", response_model=list[LiabilityRead])
async def list_liabilities(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    status: str | None = None,
) -> list[Liability]:
    stmt = select(Liability)
    if estate_id is not None:
        stmt = stmt.where(Liability.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(Liability.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(Liability.status == status)
    stmt = stmt.order_by(Liability.created_at.desc(), Liability.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{liability_id}", response_model=LiabilityRead)
async def get_liability(
    liability_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> Liability:
    return await _get_liability(session, liability_id)


@router.post("", response_model=LiabilityRead, status_code=status.HTTP_201_CREATED)
async def create_liability(
    payload: LiabilityCreate, session: SessionDep, user: WriteUser
) -> Liability:
    await _require_estate(session, payload.estate_id)
    row = Liability(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    _audit(session, user, "create", f"liability:{row.id}", row.estate_id, None, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/{liability_id}", response_model=LiabilityRead)
async def update_liability(
    liability_id: uuid.UUID, payload: LiabilityUpdate, session: SessionDep, user: WriteUser
) -> Liability:
    row = await _get_liability(session, liability_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    _audit(session, user, "update", f"liability:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{liability_id}", response_model=LiabilityRead)
async def archive_liability(
    liability_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Liability:
    row = await _get_liability(session, liability_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Liability is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    _audit(session, user, "archive", f"liability:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row
