"""Approvals API: the human-approval record for agent drafts.

Agents produce drafts; a person approves. POST /approvals records that a
named person approved a draft at a point in time (guardrail 1: nothing is
filed or sent by code). P3 wires the agent graphs to this record.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import Approval
from app.models.base import utcnow
from app.schemas.collab import ApprovalCreate, ApprovalOut
from app.services.seeding import get_active_estate, record_audit

router = APIRouter(prefix="/approvals", tags=["approvals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
async def create_approval(
    payload: ApprovalCreate, user: WriteUser, session: SessionDep
) -> Approval:
    """Record the caller's approval of a draft, stamped now."""
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate is configured yet. Seed one first.",
        )
    approval = Approval(
        estate_id=estate.id,
        entity_ref=payload.entity_ref,
        draft_kind=payload.draft_kind,
        approved_by=user.email,
        approved_at=utcnow(),
        created_by=user.email,
    )
    session.add(approval)
    await session.flush()
    await record_audit(
        session,
        estate.id,
        user.email,
        "approve",
        payload.entity_ref,
        after={"draft_kind": payload.draft_kind, "approval_id": str(approval.id)},
    )
    await session.commit()
    return approval


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    user: ReadUser,
    session: SessionDep,
    entity_ref: Annotated[str | None, Query()] = None,
) -> list[Approval]:
    """Approvals, optionally filtered to one entity reference."""
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate is configured yet. Seed one first.",
        )
    query = select(Approval).where(
        Approval.estate_id == estate.id, Approval.archived_at.is_(None)
    )
    if entity_ref:
        query = query.where(Approval.entity_ref == entity_ref)
    result = await session.execute(query.order_by(Approval.created_at.desc()))
    return list(result.scalars().all())
