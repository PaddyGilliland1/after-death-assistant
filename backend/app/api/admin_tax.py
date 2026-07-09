"""Administration-period tax tracker router (Module 15, contract section 8).

CRUD on admin_tax rows keyed by tax year ("2026-27"). Derivations, all
from stored data and app.domain.deadlines:

- cgt_60day_deadlines: one entry per stored disposal with a disposal
  date, via domain.cgt_60_day_deadline (60 days from completion).
- isa_exemption_end: read-only, from the estate's date of death via
  domain.isa_exemption_end (third anniversary rule).
- estate_complex: comparison of stored figures against the documented
  informal-route thresholds (app.schemas.trackers
  .INFORMAL_ROUTE_THRESHOLDS, each with its source citation). The
  estate-value condition is checked against the latest stored IHT
  assessment input; when none exists it is unknown and the year is
  conservatively flagged complex.

No tax figure is computed anywhere in this module.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.domain import deadlines as domain_deadlines
from app.models import AdminTax, Estate
from app.models.base import utcnow
from app.schemas.registers import snapshot
from app.schemas.trackers import (
    INFORMAL_ROUTE_THRESHOLDS,
    AdminTaxCreate,
    AdminTaxRead,
    AdminTaxUpdate,
    CgtDisposal,
    derive_estate_complex,
)
from app.services.reevaluation import latest_assessment
from app.services.seeding import record_audit

router = APIRouter(prefix="/admin-tax", tags=["admin-tax"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_estate(session: AsyncSession, estate_id: uuid.UUID) -> Estate:
    estate = await session.get(Estate, estate_id)
    if estate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estate not found.")
    return estate


async def _get_row(session: AsyncSession, admin_tax_id: uuid.UUID) -> AdminTax:
    row = await session.get(AdminTax, admin_tax_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin tax year not found.")
    return row


def _derive_cgt_deadlines(disposals: list[CgtDisposal]) -> list[dict]:
    """One 60-day entry per disposal that has a date, via the domain."""
    entries: list[dict] = []
    for disposal in disposals:
        if disposal.disposal_date is None:
            continue
        derived = domain_deadlines.cgt_60_day_deadline(disposal.disposal_date)
        entries.append(
            {
                "disposal_date": disposal.disposal_date.isoformat(),
                "deadline": derived.due_date.isoformat(),
                "basis": derived.basis,
            }
        )
    return entries


async def _net_value_from_latest(
    session: AsyncSession, estate_id: uuid.UUID
) -> Decimal | None:
    """The net estate value stored by the latest IHT assessment, if any."""
    latest = await latest_assessment(session, estate_id)
    if latest is None:
        return None
    raw = (latest.snapshot or {}).get("inputs", {}).get("net_value")
    if raw is None:
        return None
    return Decimal(str(raw))


async def _derive_complex(
    session: AsyncSession, row: AdminTax
) -> tuple[bool, list[str]]:
    disposals = [CgtDisposal.model_validate(entry) for entry in row.cgt_disposals]
    gains = [d.gain for d in disposals if d.gain is not None]
    net_value = await _net_value_from_latest(session, row.estate_id)
    return derive_estate_complex(row.income_total, gains, net_value)


async def _to_read(session: AsyncSession, row: AdminTax) -> AdminTaxRead:
    _, reasons = await _derive_complex(session, row)
    read = AdminTaxRead.model_validate(row, from_attributes=True)
    read.complex_reasons = reasons
    return read


def _apply_derivations(row: AdminTax, estate: Estate) -> None:
    """Refresh every derived column from the stored inputs."""
    disposals = [CgtDisposal.model_validate(entry) for entry in row.cgt_disposals]
    row.cgt_60day_deadlines = _derive_cgt_deadlines(disposals)
    if estate.date_of_death is not None:
        row.isa_exemption_end = domain_deadlines.isa_exemption_end(
            estate.date_of_death
        ).due_date
    else:
        row.isa_exemption_end = None


@router.get("/thresholds")
async def informal_route_thresholds(user: ReadUser) -> dict[str, dict[str, str]]:
    """The informal-route thresholds as data, each with its source."""
    return INFORMAL_ROUTE_THRESHOLDS


@router.get("", response_model=list[AdminTaxRead])
async def list_admin_tax(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    tax_year: str | None = None,
    include_archived: bool = False,
) -> list[AdminTaxRead]:
    stmt = select(AdminTax)
    if estate_id is not None:
        stmt = stmt.where(AdminTax.estate_id == estate_id)
    if tax_year is not None:
        stmt = stmt.where(AdminTax.tax_year == tax_year)
    if not include_archived:
        stmt = stmt.where(AdminTax.archived_at.is_(None))
    stmt = stmt.order_by(AdminTax.tax_year, AdminTax.created_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    return [await _to_read(session, row) for row in rows]


@router.get("/{admin_tax_id}", response_model=AdminTaxRead)
async def get_admin_tax(
    admin_tax_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> AdminTaxRead:
    row = await _get_row(session, admin_tax_id)
    return await _to_read(session, row)


@router.post("", response_model=AdminTaxRead, status_code=status.HTTP_201_CREATED)
async def create_admin_tax(
    payload: AdminTaxCreate, session: SessionDep, user: WriteUser
) -> AdminTaxRead:
    estate = await _require_estate(session, payload.estate_id)

    duplicate = await session.execute(
        select(AdminTax)
        .where(AdminTax.estate_id == payload.estate_id)
        .where(AdminTax.tax_year == payload.tax_year)
        .where(AdminTax.archived_at.is_(None))
        .limit(1)
    )
    if duplicate.scalars().first() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tax year {payload.tax_year} already exists for this estate.",
        )

    row = AdminTax(
        estate_id=payload.estate_id,
        tax_year=payload.tax_year,
        income_total=payload.income_total,
        cgt_disposals=[d.model_dump(mode="json") for d in payload.cgt_disposals],
        created_by=user.email,
    )
    _apply_derivations(row, estate)
    row.estate_complex, _ = await _derive_complex(session, row)
    session.add(row)
    await session.flush()
    await record_audit(
        session, row.estate_id, user.email, "create", f"admin_tax:{row.id}", None, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return await _to_read(session, row)


@router.patch("/{admin_tax_id}", response_model=AdminTaxRead)
async def update_admin_tax(
    admin_tax_id: uuid.UUID,
    payload: AdminTaxUpdate,
    session: SessionDep,
    user: WriteUser,
) -> AdminTaxRead:
    row = await _get_row(session, admin_tax_id)
    estate = await _require_estate(session, row.estate_id)
    before = snapshot(row)

    changes = payload.model_dump(exclude_unset=True)
    if "tax_year" in changes:
        row.tax_year = changes["tax_year"]
    if "income_total" in changes:
        row.income_total = changes["income_total"]
    if "cgt_disposals" in changes:
        disposals = payload.cgt_disposals or []
        row.cgt_disposals = [d.model_dump(mode="json") for d in disposals]

    _apply_derivations(row, estate)
    row.estate_complex, _ = await _derive_complex(session, row)
    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "update", f"admin_tax:{row.id}", before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return await _to_read(session, row)


@router.delete("/{admin_tax_id}", response_model=AdminTaxRead)
async def archive_admin_tax(
    admin_tax_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> AdminTaxRead:
    row = await _get_row(session, admin_tax_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admin tax year is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    await record_audit(
        session, row.estate_id, user.email, "archive", f"admin_tax:{row.id}", before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return await _to_read(session, row)
