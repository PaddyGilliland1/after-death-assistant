"""Executor decision log router (Module 19). Immutable once recorded.

Only POST and GET are offered. PATCH and DELETE exist solely to return
405 with a body explaining that decisions are immutable once recorded:
the log protects the executors precisely because it cannot be rewritten.
To correct a decision, record a new one referring to the old. Decisions
flagged executor_private are never returned to the viewer role.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, Role, WriteUser
from app.db import get_session
from app.models import AuditEvent, Decision, Estate
from app.schemas.people import DecisionCreate, DecisionRead

router = APIRouter(prefix="/decisions", tags=["decisions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

IMMUTABLE_DETAIL = (
    "Decisions are immutable once recorded. The decision log exists to protect "
    "the executors, so entries can be neither changed nor deleted. To correct "
    "a decision, record a new decision that refers to this one."
)


async def _ensure_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    estate = await session.get(Estate, estate_id)
    if estate is None or estate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Estate not found.")


@router.post("", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
async def record_decision(
    payload: DecisionCreate,
    user: WriteUser,
    session: SessionDep,
) -> Decision:
    """Record an executor decision. It cannot be changed afterwards."""
    await _ensure_estate(session, payload.estate_id)
    decision = Decision(
        **payload.model_dump(),
        made_by=user.email,
        created_by=user.email,
    )
    session.add(decision)
    await session.flush()
    session.add(
        AuditEvent(
            estate_id=decision.estate_id,
            actor=user.email,
            action="create",
            entity=f"decision:{decision.id}",
            after=DecisionRead.model_validate(decision).model_dump(mode="json"),
            created_by=user.email,
        )
    )
    await session.commit()
    await session.refresh(decision)
    return decision


@router.get("", response_model=list[DecisionRead])
async def list_decisions(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
) -> list[Decision]:
    """List recorded decisions. executor_private decisions are excluded
    when the caller has the viewer role."""
    stmt = select(Decision).order_by(Decision.date, Decision.created_at)
    if estate_id is not None:
        stmt = stmt.where(Decision.estate_id == estate_id)
    if user.role == Role.VIEWER:
        stmt = stmt.where(Decision.executor_private.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{decision_id}", response_model=DecisionRead)
async def get_decision(
    decision_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> Decision:
    """Fetch one decision. executor_private decisions are hidden from
    viewers."""
    decision = await session.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found.")
    if user.role == Role.VIEWER and decision.executor_private:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return decision


@router.patch("/{decision_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def update_decision_not_allowed(decision_id: uuid.UUID, user: ReadUser) -> None:
    """Always 405: decisions are immutable once recorded."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=IMMUTABLE_DETAIL
    )


@router.delete("/{decision_id}", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def delete_decision_not_allowed(decision_id: uuid.UUID, user: ReadUser) -> None:
    """Always 405: decisions are immutable once recorded."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=IMMUTABLE_DETAIL
    )
