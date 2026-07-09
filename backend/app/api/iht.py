"""IHT workbench endpoints (build contract section 8).

- POST /iht/recompute   assemble the engine input from the registers,
                        assess, persist a snapshot, audit (write roles)
- GET  /iht/assessment  the latest snapshot
- GET  /iht/schedules   required schedules with plain-English reasons

Every figure comes from the deterministic engine
(app.domain.iht_engine.assess with the England and Wales constants);
these routes only assemble inputs and store or present its output.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# Import shared within the API package: the single-estate resolution lives
# with the estate router.
from app.api.estate import get_estate_or_404
from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import IhtAssessment
from app.schemas.iht import IhtAssessmentRead, IhtSchedulesRead, ScheduleItem
from app.services.reevaluation import latest_assessment, run_recompute

router = APIRouter(prefix="/iht", tags=["iht"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Plain-English reasons per supplementary schedule. The engine derives
# WHICH schedules apply; this table only explains them (no figures).
_SCHEDULE_REASONS: dict[str, str] = {
    "IHT402": "A transferable nil rate band is claimed from a predeceased "
    "spouse or civil partner.",
    "IHT403": "Gifts were made in the seven years before death, or gifts "
    "with reservation of benefit are present.",
    "IHT405": "The estate includes land or buildings.",
    "IHT406": "The estate includes bank or building society accounts or "
    "NS&I holdings.",
    "IHT407": "The estate includes household and personal goods.",
    "IHT411": "The estate includes listed stocks and shares.",
    "IHT412": "The estate includes unlisted stocks and shares.",
    "IHT435": "The residence nil rate band is claimed.",
    "IHT436": "A transferred residence nil rate band is claimed from a "
    "predeceased spouse or civil partner.",
}
_FALLBACK_REASON = "Required by the latest assessment."


async def _latest_or_404(session: AsyncSession) -> IhtAssessment:
    estate = await get_estate_or_404(session)
    latest = await latest_assessment(session, estate.id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No IHT assessment has been computed yet. POST /iht/recompute first.",
        )
    return latest


@router.post("/recompute", response_model=IhtAssessmentRead)
async def recompute(session: SessionDep, user: WriteUser) -> IhtAssessmentRead:
    """Recompute the IHT position from the registers and snapshot it.

    Assembles the engine input from the database (asset estate shares,
    deductible liabilities, funeral costs, the estate settings for the
    transferable bands, the residence value and the excepted-estate
    facts), calls the pure engine with the England and Wales constants,
    persists an immutable iht_assessment snapshot (inputs + result +
    constants version) and emits an audit event.
    """
    estate = await get_estate_or_404(session)
    row, _, _ = await run_recompute(session, estate, user.email)
    await session.commit()
    return IhtAssessmentRead.from_row(row)


@router.get("/assessment", response_model=IhtAssessmentRead)
async def get_assessment(session: SessionDep, user: ReadUser) -> IhtAssessmentRead:
    """The latest IHT assessment snapshot."""
    latest = await _latest_or_404(session)
    return IhtAssessmentRead.from_row(latest)


@router.get("/schedules", response_model=IhtSchedulesRead)
async def get_schedules(session: SessionDep, user: ReadUser) -> IhtSchedulesRead:
    """The supplementary schedules the latest assessment requires, each
    with a plain-English reason."""
    latest = await _latest_or_404(session)
    result = latest.snapshot.get("result", {})
    codes = list(result.get("required_schedules", []))
    return IhtSchedulesRead(
        assessment_id=latest.id,
        assessed_at=latest.created_at,
        must_file_iht400=bool(result.get("must_file_iht400", True)),
        schedules=[
            ScheduleItem(code=code, reason=_SCHEDULE_REASONS.get(code, _FALLBACK_REASON))
            for code in codes
        ],
    )
