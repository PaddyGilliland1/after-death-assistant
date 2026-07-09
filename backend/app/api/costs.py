"""Costs router: CRUD, co-executor alerts and the by-type view.

Every cost creation emits an audit event and an in-app notification
(event_type "cost_recorded") to the other executor and admin users; the
message quotes the description and amount exactly as stored, with no
computation. GET /costs/by-type sums stored figures grouped by category
and by IHT treatment (aggregation only). The reimbursable/reimbursed
workflow runs through PATCH. Costs flagged executor_private are never
returned to the viewer role. Soft delete via DELETE.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, Role, WriteUser, parse_user_roles
from app.core.config import Settings, get_settings
from app.db import get_session
from app.models import AuditEvent, Cost, Estate, Notification
from app.models.base import utcnow
from app.schemas.tasks_costs import (
    CategoryTotal,
    CostCreate,
    CostRead,
    CostsByType,
    CostUpdate,
    TreatmentTotal,
)

router = APIRouter(prefix="/costs", tags=["costs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _snapshot(row: Cost) -> dict:
    return CostRead.model_validate(row).model_dump(mode="json")


def _audit(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            estate_id=estate_id,
            actor=actor,
            action=action,
            entity=entity,
            before=before,
            after=after,
            created_by=actor,
        )
    )


async def _ensure_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    estate = await session.get(Estate, estate_id)
    if estate is None or estate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Estate not found.")


async def _get_cost_or_404(session: AsyncSession, cost_id: uuid.UUID) -> Cost:
    cost = await session.get(Cost, cost_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Cost not found.")
    return cost


def _notify_other_executors(
    session: AsyncSession, cost: Cost, actor_email: str, settings: Settings
) -> None:
    """Queue a cost_recorded notification for every other executor/admin.

    The message quotes the stored description and amount; nothing is
    computed here.
    """
    recipients = [
        email
        for email, role in parse_user_roles(settings.USER_ROLES).items()
        if role in (Role.EXECUTOR, Role.ADMIN) and email != actor_email
    ]
    for recipient in recipients:
        session.add(
            Notification(
                estate_id=cost.estate_id,
                user_id=recipient,
                event_type="cost_recorded",
                entity_ref=f"cost:{cost.id}",
                message=f"Cost recorded: {cost.description}, amount {cost.amount}",
                created_by=actor_email,
            )
        )


@router.post("", response_model=CostRead, status_code=status.HTTP_201_CREATED)
async def create_cost(
    payload: CostCreate,
    user: WriteUser,
    session: SessionDep,
    settings: SettingsDep,
) -> Cost:
    """Record a cost and alert the other executors."""
    await _ensure_estate(session, payload.estate_id)
    cost = Cost(**payload.model_dump(), created_by=user.email)
    session.add(cost)
    await session.flush()
    _audit(
        session, cost.estate_id, user.email, "create", f"cost:{cost.id}", after=_snapshot(cost)
    )
    _notify_other_executors(session, cost, user.email, settings)
    await session.commit()
    await session.refresh(cost)
    return cost


@router.get("/by-type", response_model=CostsByType)
async def costs_by_type(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
) -> CostsByType:
    """Totals of stored cost amounts grouped by category and by IHT
    treatment. This is aggregation of stored figures only."""

    def _filtered(stmt):
        stmt = stmt.where(Cost.archived_at.is_(None))
        if estate_id is not None:
            stmt = stmt.where(Cost.estate_id == estate_id)
        if user.role == Role.VIEWER:
            stmt = stmt.where(Cost.executor_private.is_(False))
        return stmt

    by_category_rows = await session.execute(
        _filtered(
            select(Cost.category, func.sum(Cost.amount)).group_by(Cost.category)
        ).order_by(Cost.category)
    )
    by_treatment_rows = await session.execute(
        _filtered(
            select(Cost.iht_treatment, func.sum(Cost.amount)).group_by(Cost.iht_treatment)
        ).order_by(Cost.iht_treatment)
    )
    return CostsByType(
        by_category=[
            CategoryTotal(category=category, total=total)
            for category, total in by_category_rows.all()
        ],
        by_iht_treatment=[
            TreatmentTotal(iht_treatment=treatment, total=total)
            for treatment, total in by_treatment_rows.all()
        ],
    )


@router.get("", response_model=list[CostRead])
async def list_costs(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
    category: str | None = None,
    reimbursable: bool | None = None,
    reimbursed: bool | None = None,
    include_archived: bool = False,
) -> list[Cost]:
    """List costs. executor_private costs are excluded for viewers."""
    stmt = select(Cost).order_by(Cost.date, Cost.created_at)
    if not include_archived:
        stmt = stmt.where(Cost.archived_at.is_(None))
    if estate_id is not None:
        stmt = stmt.where(Cost.estate_id == estate_id)
    if category is not None:
        stmt = stmt.where(Cost.category == category)
    if reimbursable is not None:
        stmt = stmt.where(Cost.reimbursable == reimbursable)
    if reimbursed is not None:
        stmt = stmt.where(Cost.reimbursed == reimbursed)
    if user.role == Role.VIEWER:
        stmt = stmt.where(Cost.executor_private.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{cost_id}", response_model=CostRead)
async def get_cost(
    cost_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> Cost:
    """Fetch a single cost. executor_private costs are hidden from viewers."""
    cost = await _get_cost_or_404(session, cost_id)
    if user.role == Role.VIEWER and cost.executor_private:
        raise HTTPException(status_code=404, detail="Cost not found.")
    return cost


@router.patch("/{cost_id}", response_model=CostRead)
async def update_cost(
    cost_id: uuid.UUID,
    payload: CostUpdate,
    user: WriteUser,
    session: SessionDep,
) -> Cost:
    """Partially update a cost, including the reimbursable/reimbursed
    workflow (reimbursed, reimbursed_date)."""
    cost = await _get_cost_or_404(session, cost_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return cost
    before = _snapshot(cost)
    for field, value in changes.items():
        setattr(cost, field, value)
    cost.updated_at = utcnow()
    session.add(cost)
    await session.flush()
    _audit(
        session,
        cost.estate_id,
        user.email,
        "update",
        f"cost:{cost.id}",
        before=before,
        after=_snapshot(cost),
    )
    await session.commit()
    await session.refresh(cost)
    return cost


@router.delete("/{cost_id}", response_model=CostRead)
async def archive_cost(
    cost_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Cost:
    """Soft delete: archive the cost. Nothing is physically deleted."""
    cost = await _get_cost_or_404(session, cost_id)
    if cost.archived_at is not None:
        raise HTTPException(status_code=409, detail="Cost is already archived.")
    before = _snapshot(cost)
    cost.archived_at = utcnow()
    cost.archive_reason = reason
    cost.updated_at = utcnow()
    session.add(cost)
    await session.flush()
    _audit(
        session,
        cost.estate_id,
        user.email,
        "archive",
        f"cost:{cost.id}",
        before=before,
        after=_snapshot(cost),
    )
    await session.commit()
    await session.refresh(cost)
    return cost
