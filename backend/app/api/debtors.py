"""Debtor register router: money owed TO the estate, standard CRUD
(contract section 8).

Same conventions as every register router: estate-scoped lists excluding
archived rows unless include_archived, newest first, soft delete only,
audit_event on every write, viewer read-only. Amounts expected and received
are stored as entered; nothing is calculated here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, WriteUser
from app.db import get_session
from app.models import AuditEvent, Debtor, Estate
from app.models.base import utcnow
from app.schemas.registers import (
    DebtorCreate,
    DebtorRead,
    DebtorUpdate,
    snapshot,
)

router = APIRouter(prefix="/debtors", tags=["debtors"])

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


async def _get_debtor(session: AsyncSession, debtor_id: uuid.UUID) -> Debtor:
    row = await session.get(Debtor, debtor_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Debtor not found.")
    return row


@router.get("", response_model=list[DebtorRead])
async def list_debtors(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    status: str | None = None,
) -> list[Debtor]:
    stmt = select(Debtor)
    if estate_id is not None:
        stmt = stmt.where(Debtor.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(Debtor.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(Debtor.status == status)
    stmt = stmt.order_by(Debtor.created_at.desc(), Debtor.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{debtor_id}", response_model=DebtorRead)
async def get_debtor(debtor_id: uuid.UUID, session: SessionDep, user: ReadUser) -> Debtor:
    return await _get_debtor(session, debtor_id)


@router.post("", response_model=DebtorRead, status_code=status.HTTP_201_CREATED)
async def create_debtor(payload: DebtorCreate, session: SessionDep, user: WriteUser) -> Debtor:
    await _require_estate(session, payload.estate_id)
    row = Debtor(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    _audit(session, user, "create", f"debtor:{row.id}", row.estate_id, None, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/{debtor_id}", response_model=DebtorRead)
async def update_debtor(
    debtor_id: uuid.UUID, payload: DebtorUpdate, session: SessionDep, user: WriteUser
) -> Debtor:
    row = await _get_debtor(session, debtor_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    _audit(session, user, "update", f"debtor:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{debtor_id}", response_model=DebtorRead)
async def archive_debtor(
    debtor_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Debtor:
    row = await _get_debtor(session, debtor_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Debtor is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    _audit(session, user, "archive", f"debtor:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row
