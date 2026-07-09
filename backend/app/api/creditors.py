"""Creditor register router: money owed BY the estate, standard CRUD
(contract section 8).

Same conventions as every register router: estate-scoped lists excluding
archived rows unless include_archived, newest first, soft delete only,
audit_event on every write, viewer read-only. Claimed, agreed and paid
amounts and the statutory priority class are stored as entered; nothing is
calculated here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, WriteUser
from app.db import get_session
from app.models import AuditEvent, Creditor, Estate
from app.models.base import utcnow
from app.schemas.registers import (
    CreditorCreate,
    CreditorRead,
    CreditorUpdate,
    snapshot,
)

router = APIRouter(prefix="/creditors", tags=["creditors"])

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


async def _get_creditor(session: AsyncSession, creditor_id: uuid.UUID) -> Creditor:
    row = await session.get(Creditor, creditor_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Creditor not found.")
    return row


@router.get("", response_model=list[CreditorRead])
async def list_creditors(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    status: str | None = None,
) -> list[Creditor]:
    stmt = select(Creditor)
    if estate_id is not None:
        stmt = stmt.where(Creditor.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(Creditor.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(Creditor.status == status)
    stmt = stmt.order_by(Creditor.created_at.desc(), Creditor.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{creditor_id}", response_model=CreditorRead)
async def get_creditor(
    creditor_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> Creditor:
    return await _get_creditor(session, creditor_id)


@router.post("", response_model=CreditorRead, status_code=status.HTTP_201_CREATED)
async def create_creditor(
    payload: CreditorCreate, session: SessionDep, user: WriteUser
) -> Creditor:
    await _require_estate(session, payload.estate_id)
    row = Creditor(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    _audit(session, user, "create", f"creditor:{row.id}", row.estate_id, None, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/{creditor_id}", response_model=CreditorRead)
async def update_creditor(
    creditor_id: uuid.UUID, payload: CreditorUpdate, session: SessionDep, user: WriteUser
) -> Creditor:
    row = await _get_creditor(session, creditor_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    _audit(session, user, "update", f"creditor:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{creditor_id}", response_model=CreditorRead)
async def archive_creditor(
    creditor_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Creditor:
    row = await _get_creditor(session, creditor_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Creditor is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    _audit(session, user, "archive", f"creditor:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row
