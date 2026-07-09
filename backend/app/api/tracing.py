"""Asset tracing and completeness router (Module 16, contract section 8).

Read-only module: GET /tracing/completeness computes a structured
checklist entirely from existing stored data (assets still on an
estimated basis, contacts awaiting notification, debtors not yet paid in
full, unlisted club-style holdings without a confirmed valuation) plus
the static list of free official tracing routes. No writes, no figures
beyond a subtraction of stored amounts (debtor outstanding).
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.estate import get_estate_or_404
from app.core.auth import ReadUser
from app.db import get_session
from app.models import Asset, Contact, Debtor
from app.models.enums import ValueBasis
from app.schemas.trackers import (
    TRACING_SEARCH_SUGGESTIONS,
    TRACING_WARNING,
    TracingAssetItem,
    TracingCompletenessRead,
    TracingDebtorItem,
)

router = APIRouter(prefix="/tracing", tags=["tracing"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Text markers that suggest an unlisted club-share style holding
# (gliding club shares, syndicates, memberships) alongside the IHT412
# unlisted-shares schedule mapping.
_UNLISTED_MARKERS = ("club", "unlisted", "syndicate", "membership")


@router.get("/completeness", response_model=TracingCompletenessRead)
async def tracing_completeness(
    session: SessionDep, user: ReadUser
) -> TracingCompletenessRead:
    """The completeness checklist for the active estate."""
    estate = await get_estate_or_404(session)

    estimate_stmt = (
        select(Asset)
        .where(Asset.estate_id == estate.id)
        .where(Asset.archived_at.is_(None))
        .where(Asset.value_basis == ValueBasis.estimate)
        .order_by(Asset.created_at)
    )
    estimated_assets = list((await session.execute(estimate_stmt)).scalars().all())

    unnotified_stmt = (
        select(func.count())
        .select_from(Contact)
        .where(Contact.estate_id == estate.id)
        .where(Contact.archived_at.is_(None))
        .where(Contact.notify_required.is_(True))
        .where(Contact.notified_date.is_(None))
    )
    unnotified_count = int((await session.execute(unnotified_stmt)).scalar_one())

    debtor_stmt = (
        select(Debtor)
        .where(Debtor.estate_id == estate.id)
        .where(Debtor.archived_at.is_(None))
        .where(Debtor.amount_expected.is_not(None))
        .where(Debtor.amount_expected > func.coalesce(Debtor.amount_received, 0))
        .order_by(Debtor.created_at)
    )
    debtors = list((await session.execute(debtor_stmt)).scalars().all())

    markers = [
        or_(
            func.lower(Asset.category).contains(marker),
            func.lower(func.coalesce(Asset.sub_type, "")).contains(marker),
            func.lower(Asset.description).contains(marker),
        )
        for marker in _UNLISTED_MARKERS
    ]
    unlisted_stmt = (
        select(Asset)
        .where(Asset.estate_id == estate.id)
        .where(Asset.archived_at.is_(None))
        .where(Asset.value_basis == ValueBasis.estimate)
        .where(or_(Asset.iht_schedule == "IHT412", *markers))
        .order_by(Asset.created_at)
    )
    unlisted = list((await session.execute(unlisted_stmt)).scalars().all())

    return TracingCompletenessRead(
        estimated_value_assets=[
            TracingAssetItem.model_validate(asset) for asset in estimated_assets
        ],
        unnotified_contacts_count=unnotified_count,
        outstanding_debtors=[
            TracingDebtorItem(
                id=debtor.id,
                type=debtor.type,
                amount_expected=debtor.amount_expected,
                amount_received=debtor.amount_received,
                outstanding=debtor.amount_expected - (debtor.amount_received or Decimal("0")),
                status=debtor.status,
            )
            for debtor in debtors
        ],
        unconfirmed_unlisted_holdings=[
            TracingAssetItem.model_validate(asset) for asset in unlisted
        ],
        search_suggestions=list(TRACING_SEARCH_SUGGESTIONS),
        warning=TRACING_WARNING,
    )
