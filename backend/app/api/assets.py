"""Asset register router: CRUD plus valuation events (contract section 8).

Conventions shared by all register routers:
- Lists are estate-scoped, exclude archived rows unless include_archived,
  and are ordered newest first.
- DELETE is a soft delete: archived_at and archive_reason are set; rows are
  never physically removed.
- Every write emits an audit_event with JSON-safe before/after snapshots.
- Writes require an executor or admin role; viewers are read-only.
- Registers store and return data; no figure is calculated here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, WriteUser
from app.db import get_session
from app.models import Asset, AuditEvent, Estate, ValuationEvent
from app.models.base import utcnow
from app.schemas.registers import (
    AssetCreate,
    AssetRead,
    AssetUpdate,
    ValuationEventCreate,
    ValuationEventRead,
    snapshot,
)

router = APIRouter(prefix="/assets", tags=["assets"])

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


async def _get_asset(session: AsyncSession, asset_id: uuid.UUID) -> Asset:
    row = await session.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found.")
    return row


@router.get("", response_model=list[AssetRead])
async def list_assets(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
    status: str | None = None,
) -> list[Asset]:
    stmt = select(Asset)
    if estate_id is not None:
        stmt = stmt.where(Asset.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(Asset.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(Asset.status == status)
    stmt = stmt.order_by(Asset.created_at.desc(), Asset.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(asset_id: uuid.UUID, session: SessionDep, user: ReadUser) -> Asset:
    return await _get_asset(session, asset_id)


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, session: SessionDep, user: WriteUser) -> Asset:
    await _require_estate(session, payload.estate_id)
    row = Asset(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    _audit(session, user, "create", f"asset:{row.id}", row.estate_id, None, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: uuid.UUID, payload: AssetUpdate, session: SessionDep, user: WriteUser
) -> Asset:
    row = await _get_asset(session, asset_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    _audit(session, user, "update", f"asset:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{asset_id}", response_model=AssetRead)
async def archive_asset(
    asset_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Asset:
    row = await _get_asset(session, asset_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Asset is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    _audit(session, user, "archive", f"asset:{row.id}", row.estate_id, before, snapshot(row))
    await session.commit()
    await session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Valuation events (nested under the asset)
# ---------------------------------------------------------------------------


@router.get("/{asset_id}/valuations", response_model=list[ValuationEventRead])
async def list_valuations(
    asset_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> list[ValuationEvent]:
    await _get_asset(session, asset_id)
    stmt = (
        select(ValuationEvent)
        .where(ValuationEvent.asset_id == asset_id)
        .order_by(ValuationEvent.date.desc(), ValuationEvent.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/{asset_id}/valuations",
    response_model=ValuationEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_valuation(
    asset_id: uuid.UUID,
    payload: ValuationEventCreate,
    session: SessionDep,
    user: WriteUser,
) -> ValuationEvent:
    """Record a dated valuation and refresh the asset's current value fields."""
    asset = await _get_asset(session, asset_id)
    asset_before = snapshot(asset)

    event = ValuationEvent(
        estate_id=asset.estate_id,
        asset_id=asset.id,
        value=payload.value,
        basis=payload.basis,
        source=payload.source,
        date=payload.date,
        created_by=user.email,
    )
    session.add(event)
    await session.flush()

    asset.current_or_realised_value = payload.value
    asset.value_basis = payload.basis
    asset.valuation_source = payload.source
    asset.valuation_date = payload.date
    asset.updated_at = utcnow()

    _audit(
        session,
        user,
        "create",
        f"valuation_event:{event.id}",
        event.estate_id,
        None,
        snapshot(event),
    )
    _audit(
        session,
        user,
        "update",
        f"asset:{asset.id}",
        asset.estate_id,
        asset_before,
        snapshot(asset),
    )
    await session.commit()
    await session.refresh(event)
    return event
