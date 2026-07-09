"""Beneficiary legacies router: CRUD plus recorded distributions.

Distributions are record-keeping only: posting one records that a payment
was made outside the system; no payment is ever made by code (contract
guardrail 1). List and detail responses include distributed_total, the
sum of the stored distribution rows for each legacy (aggregation of
stored figures only). Soft delete via DELETE; every write emits an audit
event; the viewer role is read-only.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import AuditEvent, BeneficiaryLegacy, Contact, Distribution, Estate
from app.models.base import utcnow
from app.schemas.people import (
    BeneficiaryLegacyCreate,
    BeneficiaryLegacyRead,
    BeneficiaryLegacyUpdate,
    DistributionCreate,
    DistributionRead,
)

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


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


async def _ensure_contact(
    session: AsyncSession, contact_id: uuid.UUID, estate_id: uuid.UUID
) -> None:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.estate_id != estate_id:
        raise HTTPException(
            status_code=404, detail="Beneficiary contact not found in this estate."
        )


async def _get_legacy_or_404(
    session: AsyncSession, legacy_id: uuid.UUID
) -> BeneficiaryLegacy:
    legacy = await session.get(BeneficiaryLegacy, legacy_id)
    if legacy is None:
        raise HTTPException(status_code=404, detail="Beneficiary legacy not found.")
    return legacy


async def _distributed_total(session: AsyncSession, legacy_id: uuid.UUID) -> Decimal:
    """Sum of the stored distribution rows for one legacy."""
    result = await session.execute(
        select(func.coalesce(func.sum(Distribution.amount), 0)).where(
            Distribution.beneficiary_legacy_id == legacy_id,
            Distribution.archived_at.is_(None),
        )
    )
    return Decimal(result.scalar_one())


async def _read_with_total(
    session: AsyncSession, legacy: BeneficiaryLegacy
) -> BeneficiaryLegacyRead:
    read = BeneficiaryLegacyRead.model_validate(legacy)
    read.distributed_total = await _distributed_total(session, legacy.id)
    return read


def _snapshot(read: BeneficiaryLegacyRead) -> dict:
    return read.model_dump(mode="json")


@router.post("", response_model=BeneficiaryLegacyRead, status_code=status.HTTP_201_CREATED)
async def create_legacy(
    payload: BeneficiaryLegacyCreate,
    user: WriteUser,
    session: SessionDep,
) -> BeneficiaryLegacyRead:
    """Create a beneficiary legacy."""
    await _ensure_estate(session, payload.estate_id)
    await _ensure_contact(session, payload.beneficiary_contact_id, payload.estate_id)
    legacy = BeneficiaryLegacy(**payload.model_dump(), created_by=user.email)
    session.add(legacy)
    await session.flush()
    read = await _read_with_total(session, legacy)
    _audit(
        session,
        legacy.estate_id,
        user.email,
        "create",
        f"beneficiary_legacy:{legacy.id}",
        after=_snapshot(read),
    )
    await session.commit()
    return read


@router.get("", response_model=list[BeneficiaryLegacyRead])
async def list_legacies(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[BeneficiaryLegacyRead]:
    """List legacies, each with its total of recorded distributions
    (sum of stored rows only)."""
    stmt = select(BeneficiaryLegacy).order_by(BeneficiaryLegacy.created_at)
    if not include_archived:
        stmt = stmt.where(BeneficiaryLegacy.archived_at.is_(None))
    if estate_id is not None:
        stmt = stmt.where(BeneficiaryLegacy.estate_id == estate_id)
    legacies = list((await session.execute(stmt)).scalars().all())

    totals_rows = await session.execute(
        select(
            Distribution.beneficiary_legacy_id,
            func.coalesce(func.sum(Distribution.amount), 0),
        )
        .where(Distribution.archived_at.is_(None))
        .group_by(Distribution.beneficiary_legacy_id)
    )
    totals = {legacy_id: Decimal(total) for legacy_id, total in totals_rows.all()}

    reads: list[BeneficiaryLegacyRead] = []
    for legacy in legacies:
        read = BeneficiaryLegacyRead.model_validate(legacy)
        read.distributed_total = totals.get(legacy.id, Decimal("0"))
        reads.append(read)
    return reads


@router.get("/{legacy_id}", response_model=BeneficiaryLegacyRead)
async def get_legacy(
    legacy_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> BeneficiaryLegacyRead:
    """Fetch one legacy with its total of recorded distributions."""
    legacy = await _get_legacy_or_404(session, legacy_id)
    return await _read_with_total(session, legacy)


@router.patch("/{legacy_id}", response_model=BeneficiaryLegacyRead)
async def update_legacy(
    legacy_id: uuid.UUID,
    payload: BeneficiaryLegacyUpdate,
    user: WriteUser,
    session: SessionDep,
) -> BeneficiaryLegacyRead:
    """Partially update a legacy."""
    legacy = await _get_legacy_or_404(session, legacy_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return await _read_with_total(session, legacy)
    if "beneficiary_contact_id" in changes:
        await _ensure_contact(session, changes["beneficiary_contact_id"], legacy.estate_id)
    before = _snapshot(await _read_with_total(session, legacy))
    for field, value in changes.items():
        setattr(legacy, field, value)
    legacy.updated_at = utcnow()
    session.add(legacy)
    await session.flush()
    read = await _read_with_total(session, legacy)
    _audit(
        session,
        legacy.estate_id,
        user.email,
        "update",
        f"beneficiary_legacy:{legacy.id}",
        before=before,
        after=_snapshot(read),
    )
    await session.commit()
    return read


@router.delete("/{legacy_id}", response_model=BeneficiaryLegacyRead)
async def archive_legacy(
    legacy_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> BeneficiaryLegacyRead:
    """Soft delete: archive the legacy. Nothing is physically deleted."""
    legacy = await _get_legacy_or_404(session, legacy_id)
    if legacy.archived_at is not None:
        raise HTTPException(status_code=409, detail="Legacy is already archived.")
    before = _snapshot(await _read_with_total(session, legacy))
    legacy.archived_at = utcnow()
    legacy.archive_reason = reason
    legacy.updated_at = utcnow()
    session.add(legacy)
    await session.flush()
    read = await _read_with_total(session, legacy)
    _audit(
        session,
        legacy.estate_id,
        user.email,
        "archive",
        f"beneficiary_legacy:{legacy.id}",
        before=before,
        after=_snapshot(read),
    )
    await session.commit()
    return read


@router.post(
    "/{legacy_id}/distributions",
    response_model=DistributionRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_distribution(
    legacy_id: uuid.UUID,
    payload: DistributionCreate,
    user: WriteUser,
    session: SessionDep,
) -> Distribution:
    """Record a distribution made to the beneficiary against this legacy.

    Record-keeping only: this notes that a payment was made outside the
    system. NO payment is made by code, ever (contract guardrail 1).
    """
    legacy = await _get_legacy_or_404(session, legacy_id)
    if legacy.archived_at is not None:
        raise HTTPException(
            status_code=409, detail="Cannot record a distribution against an archived legacy."
        )
    distribution = Distribution(
        **payload.model_dump(),
        estate_id=legacy.estate_id,
        beneficiary_legacy_id=legacy.id,
        created_by=user.email,
    )
    session.add(distribution)
    await session.flush()
    _audit(
        session,
        legacy.estate_id,
        user.email,
        "create",
        f"distribution:{distribution.id}",
        after=DistributionRead.model_validate(distribution).model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(distribution)
    return distribution


@router.get("/{legacy_id}/distributions", response_model=list[DistributionRead])
async def list_distributions(
    legacy_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> list[Distribution]:
    """List the recorded distributions for a legacy."""
    await _get_legacy_or_404(session, legacy_id)
    result = await session.execute(
        select(Distribution)
        .where(
            Distribution.beneficiary_legacy_id == legacy_id,
            Distribution.archived_at.is_(None),
        )
        .order_by(Distribution.date, Distribution.created_at)
    )
    return list(result.scalars().all())
