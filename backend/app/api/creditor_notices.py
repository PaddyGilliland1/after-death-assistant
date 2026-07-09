"""Section 27 creditor notice router (Trustee Act 1925 s.27).

CRUD for the notice register plus the statutory workflow:

- claim_deadline is DERIVED, never entered: two months and one day from the
  later of the Gazette and local paper notice dates, via
  app.domain.deadlines.gazette_claim_deadline.
- safe_to_distribute is DERIVED: true only when a claim deadline exists and
  is in the past AND no notice_claim rows are open. It is recomputed on
  every notice or claim write.
- GET /creditor-notices/safe-to-distribute evaluates the guard live across
  all active notices and returns the overall boolean with reasons. Module 6
  (distributions) must consult this before paying anyone.

Same register conventions as the other routers: estate-scoped lists
excluding archived rows unless include_archived, newest first, soft delete
only, audit_event on every write, viewer read-only.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, WriteUser
from app.db import get_session
from app.domain.deadlines import gazette_claim_deadline
from app.models import AuditEvent, CreditorNotice, Estate, NoticeClaim
from app.models.base import utcnow
from app.schemas.registers import (
    CreditorNoticeCreate,
    CreditorNoticeRead,
    CreditorNoticeUpdate,
    NoticeClaimCreate,
    NoticeClaimRead,
    NoticeClaimUpdate,
    SafeToDistributeResponse,
    snapshot,
)

router = APIRouter(prefix="/creditor-notices", tags=["creditor-notices"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# A claim in any of these states no longer blocks distribution. Anything
# else (including no status at all) counts as open.
CLOSED_CLAIM_STATUSES = frozenset(
    {"resolved", "rejected", "withdrawn", "paid", "settled", "closed"}
)


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


async def _get_notice(session: AsyncSession, notice_id: uuid.UUID) -> CreditorNotice:
    row = await session.get(CreditorNotice, notice_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Creditor notice not found.")
    return row


def _derive_claim_deadline(
    gazette_date: dt.date | None, local_date: dt.date | None
) -> dt.date | None:
    """Two months and one day from the later notice date (s.27 minimum)."""
    dates = [d for d in (gazette_date, local_date) if d is not None]
    if not dates:
        return None
    return gazette_claim_deadline(max(dates)).due_date


def _open_claims_stmt(notice_id: uuid.UUID):
    return (
        select(func.count())
        .select_from(NoticeClaim)
        .where(
            NoticeClaim.creditor_notice_id == notice_id,
            NoticeClaim.archived_at.is_(None),
            or_(
                NoticeClaim.status.is_(None),
                func.lower(NoticeClaim.status).notin_(CLOSED_CLAIM_STATUSES),
            ),
        )
    )


async def _open_claim_count(session: AsyncSession, notice_id: uuid.UUID) -> int:
    return int((await session.execute(_open_claims_stmt(notice_id))).scalar_one())


async def _recompute_derived(
    session: AsyncSession, notice: CreditorNotice, today: dt.date
) -> None:
    """Refresh the derived claim_deadline and safe_to_distribute fields."""
    notice.claim_deadline = _derive_claim_deadline(notice.gazette_date, notice.local_date)
    open_claims = await _open_claim_count(session, notice.id)
    notice.safe_to_distribute = (
        notice.claim_deadline is not None
        and notice.claim_deadline < today
        and open_claims == 0
    )


# ---------------------------------------------------------------------------
# Distribution guard (declared before /{notice_id} so the path wins)
# ---------------------------------------------------------------------------


@router.get("/safe-to-distribute", response_model=SafeToDistributeResponse)
async def safe_to_distribute(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
) -> SafeToDistributeResponse:
    """Overall distribution guard, evaluated live against today's date.

    Safe only when at least one active Section 27 notice exists and every
    active notice has a claim deadline in the past with no open claims.
    """
    today = dt.date.today()
    stmt = select(CreditorNotice).where(CreditorNotice.archived_at.is_(None))
    if estate_id is not None:
        stmt = stmt.where(CreditorNotice.estate_id == estate_id)
    notices = list((await session.execute(stmt)).scalars().all())

    reasons: list[str] = []
    if not notices:
        reasons.append(
            "No Section 27 creditor notice has been recorded; place notices in "
            "The Gazette and a local paper before distributing."
        )
    for notice in notices:
        deadline = _derive_claim_deadline(notice.gazette_date, notice.local_date)
        if deadline is None:
            reasons.append(
                f"Notice {notice.id} has no notice dates, so no claim deadline "
                "can be derived."
            )
        elif deadline >= today:
            reasons.append(
                f"Notice {notice.id} claim deadline {deadline.isoformat()} has "
                "not yet passed."
            )
        open_claims = await _open_claim_count(session, notice.id)
        if open_claims:
            reasons.append(
                f"Notice {notice.id} has {open_claims} open claim(s) awaiting "
                "resolution."
            )

    safe = bool(notices) and not reasons
    if safe:
        reasons.append(
            "All notice claim deadlines have passed and no claims remain open."
        )
    return SafeToDistributeResponse(
        safe_to_distribute=safe, checked_on=today, reasons=reasons
    )


# ---------------------------------------------------------------------------
# Notice CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CreditorNoticeRead])
async def list_notices(
    session: SessionDep,
    user: ReadUser,
    estate_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[CreditorNotice]:
    stmt = select(CreditorNotice)
    if estate_id is not None:
        stmt = stmt.where(CreditorNotice.estate_id == estate_id)
    if not include_archived:
        stmt = stmt.where(CreditorNotice.archived_at.is_(None))
    stmt = stmt.order_by(CreditorNotice.created_at.desc(), CreditorNotice.id)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{notice_id}", response_model=CreditorNoticeRead)
async def get_notice(
    notice_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> CreditorNotice:
    return await _get_notice(session, notice_id)


@router.post("", response_model=CreditorNoticeRead, status_code=status.HTTP_201_CREATED)
async def create_notice(
    payload: CreditorNoticeCreate, session: SessionDep, user: WriteUser
) -> CreditorNotice:
    await _require_estate(session, payload.estate_id)
    row = CreditorNotice(**payload.model_dump(), created_by=user.email)
    session.add(row)
    await session.flush()
    await _recompute_derived(session, row, dt.date.today())
    _audit(
        session, user, "create", f"creditor_notice:{row.id}", row.estate_id, None, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.patch("/{notice_id}", response_model=CreditorNoticeRead)
async def update_notice(
    notice_id: uuid.UUID,
    payload: CreditorNoticeUpdate,
    session: SessionDep,
    user: WriteUser,
) -> CreditorNotice:
    row = await _get_notice(session, notice_id)
    before = snapshot(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await _recompute_derived(session, row, dt.date.today())
    row.updated_at = utcnow()
    _audit(
        session, user, "update", f"creditor_notice:{row.id}", row.estate_id, before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{notice_id}", response_model=CreditorNoticeRead)
async def archive_notice(
    notice_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> CreditorNotice:
    row = await _get_notice(session, notice_id)
    if row.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Creditor notice is already archived.")
    before = snapshot(row)
    row.archived_at = utcnow()
    row.archive_reason = reason
    row.updated_at = utcnow()
    _audit(
        session, user, "archive", f"creditor_notice:{row.id}", row.estate_id, before, snapshot(row)
    )
    await session.commit()
    await session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Claims received in response to a notice
# ---------------------------------------------------------------------------


@router.get("/{notice_id}/claims", response_model=list[NoticeClaimRead])
async def list_claims(
    notice_id: uuid.UUID,
    session: SessionDep,
    user: ReadUser,
    include_archived: bool = False,
) -> list[NoticeClaim]:
    await _get_notice(session, notice_id)
    stmt = select(NoticeClaim).where(NoticeClaim.creditor_notice_id == notice_id)
    if not include_archived:
        stmt = stmt.where(NoticeClaim.archived_at.is_(None))
    stmt = stmt.order_by(NoticeClaim.created_at.desc(), NoticeClaim.id)
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/{notice_id}/claims",
    response_model=NoticeClaimRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_claim(
    notice_id: uuid.UUID,
    payload: NoticeClaimCreate,
    session: SessionDep,
    user: WriteUser,
) -> NoticeClaim:
    notice = await _get_notice(session, notice_id)
    notice_before = snapshot(notice)
    claim = NoticeClaim(
        estate_id=notice.estate_id,
        creditor_notice_id=notice.id,
        created_by=user.email,
        **payload.model_dump(),
    )
    session.add(claim)
    await session.flush()
    await _recompute_derived(session, notice, dt.date.today())
    notice.updated_at = utcnow()
    _audit(
        session, user, "create", f"notice_claim:{claim.id}", claim.estate_id, None, snapshot(claim)
    )
    _audit(
        session,
        user,
        "update",
        f"creditor_notice:{notice.id}",
        notice.estate_id,
        notice_before,
        snapshot(notice),
    )
    await session.commit()
    await session.refresh(claim)
    return claim


@router.patch("/{notice_id}/claims/{claim_id}", response_model=NoticeClaimRead)
async def update_claim(
    notice_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: NoticeClaimUpdate,
    session: SessionDep,
    user: WriteUser,
) -> NoticeClaim:
    notice = await _get_notice(session, notice_id)
    claim = await session.get(NoticeClaim, claim_id)
    if claim is None or claim.creditor_notice_id != notice.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notice claim not found.")
    notice_before = snapshot(notice)
    before = snapshot(claim)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(claim, field, value)
    claim.updated_at = utcnow()
    await session.flush()
    await _recompute_derived(session, notice, dt.date.today())
    notice.updated_at = utcnow()
    _audit(
        session,
        user,
        "update",
        f"notice_claim:{claim.id}",
        claim.estate_id,
        before,
        snapshot(claim),
    )
    _audit(
        session,
        user,
        "update",
        f"creditor_notice:{notice.id}",
        notice.estate_id,
        notice_before,
        snapshot(notice),
    )
    await session.commit()
    await session.refresh(claim)
    return claim
