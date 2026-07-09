"""Re-evaluation service (spec section 20, build contract section 8).

Whenever an asset, liability or the estate settings change, the position
must be recomputed immediately, snapshotted, and the other executors
alerted when a material threshold is crossed. This module owns that flow:

- assemble_estate_input builds the pure engine's Estate from database rows;
- run_recompute calls the deterministic engine, persists an iht_assessment
  snapshot (inputs + result + constants version) and emits an audit event;
- reevaluate runs a recompute, compares the new assessment with the
  previous snapshot and creates notification rows for the other
  executor/admin users when a material threshold is crossed.

Every figure in a message or a snapshot comes from the domain engine (or
is a stored input the engine was given). This module adds, sums and
compares nothing beyond assembling engine inputs from rows, which the
build contract assigns to the API layer.
"""

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import WRITE_ROLES, parse_user_roles
from app.core.config import get_settings
from app.domain.estate_accounts import AccountAsset, Ownership
from app.domain.iht_engine import Assessment, AssetCategory, AssetItem, assess
from app.domain.iht_engine import Estate as EngineEstate
from app.domain.jurisdiction import ENGLAND_WALES
from app.models import Asset, AuditEvent, Cost, Estate, IhtAssessment, Liability, Notification
from app.models.enums import IhtTreatment

# Material single-change threshold (spec section 20 default: any single
# input change above this amount raises a re-evaluation alert).
MATERIAL_SINGLE_CHANGE_GBP = Decimal("10000")

# The re-evaluation alert notification type.
REEVALUATION_EVENT_TYPE = "reevaluation_alert"

# Engine input fields compared for the single-change threshold.
_COMPARED_INPUT_FIELDS = (
    "net_value",
    "gross_value",
    "residence_to_descendants_value",
    "exempt_transfers",
    "downsizing_addition",
    "gifts_in_seven_years",
    "trust_assets_value",
    "foreign_assets_value",
)

# Free-text asset.category values mapped to the engine's schedule-driving
# categories. Unknown categories fall back to OTHER (no schedule).
_CATEGORY_MAP: Mapping[str, AssetCategory] = {
    "property": AssetCategory.LAND_AND_BUILDINGS,
    "land": AssetCategory.LAND_AND_BUILDINGS,
    "land_and_buildings": AssetCategory.LAND_AND_BUILDINGS,
    "house": AssetCategory.LAND_AND_BUILDINGS,
    "cash": AssetCategory.BANK_ACCOUNTS,
    "bank": AssetCategory.BANK_ACCOUNTS,
    "bank_account": AssetCategory.BANK_ACCOUNTS,
    "bank_accounts": AssetCategory.BANK_ACCOUNTS,
    "isa": AssetCategory.BANK_ACCOUNTS,
    "savings": AssetCategory.BANK_ACCOUNTS,
    "current_account": AssetCategory.BANK_ACCOUNTS,
    "nsandi": AssetCategory.NSANDI,
    "ns&i": AssetCategory.NSANDI,
    "premium_bonds": AssetCategory.NSANDI,
    "household": AssetCategory.HOUSEHOLD_GOODS,
    "household_goods": AssetCategory.HOUSEHOLD_GOODS,
    "chattels": AssetCategory.HOUSEHOLD_GOODS,
    "vehicle": AssetCategory.HOUSEHOLD_GOODS,
    "car": AssetCategory.HOUSEHOLD_GOODS,
    "gift": AssetCategory.GIFTS,
    "gifts": AssetCategory.GIFTS,
    "shares": AssetCategory.LISTED_SHARES,
    "listed_shares": AssetCategory.LISTED_SHARES,
    "unlisted_shares": AssetCategory.UNLISTED_SHARES,
    "private_shares": AssetCategory.UNLISTED_SHARES,
}


def constants_version() -> str:
    """Version string for the jurisdiction constants in use (provenance)."""
    return f"{ENGLAND_WALES.code}:{ENGLAND_WALES.nrb.fetch_date.isoformat()}"


def _gbp(value: Decimal) -> str:
    """Format an engine figure for a plain-English message."""
    return f"£{value:,.2f}"


async def record_audit(
    session: AsyncSession,
    *,
    estate_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist an estate-scoped audit event on the caller's session.

    app.core.audit.emit_audit cannot currently be used against the real
    schema: audit_event.estate_id is NOT NULL and emit_audit has no way to
    set it (reported as a core gap). This helper writes the same shape of
    event with the estate scope populated; it flushes but never commits,
    so the audit row lives or dies with the caller's transaction.
    """
    event = AuditEvent(
        estate_id=estate_id,
        actor=actor,
        action=action,
        entity=entity,
        before=before,
        after=after,
        timestamp=dt.datetime.now(dt.UTC),
    )
    session.add(event)
    await session.flush()
    return event


async def load_account_assets(
    session: AsyncSession, estate_id: uuid.UUID
) -> tuple[AccountAsset, ...]:
    """Load the estate's assets as domain AccountAsset values.

    Archived rows and assets that pass outside the estate (survivorship,
    nominations) are excluded; the domain model itself zero-weights joint
    tenancies. Values are the date-of-death values (missing values count
    as zero until recorded).
    """
    result = await session.execute(
        select(Asset).where(
            Asset.estate_id == estate_id,
            Asset.archived_at.is_(None),  # type: ignore[union-attr]
            Asset.passes_outside_estate == False,  # noqa: E712
        )
    )
    assets = result.scalars().all()
    return tuple(
        AccountAsset(
            identifier=str(asset.id),
            value=asset.dod_value or Decimal("0"),
            ownership=Ownership(asset.ownership.value),
            tic_share_pct=(
                asset.tic_share_pct if asset.tic_share_pct is not None else Decimal("1")
            ),
        )
        for asset in assets
    )


async def sum_costs_by_treatment(
    session: AsyncSession, estate_id: uuid.UUID
) -> dict[IhtTreatment, Decimal]:
    """Total non-archived costs per IHT treatment (funeral vs admin)."""
    totals = {IhtTreatment.funeral_deductible: Decimal("0")}
    totals[IhtTreatment.admin_not_deductible] = Decimal("0")
    result = await session.execute(
        select(Cost.iht_treatment, Cost.amount).where(
            Cost.estate_id == estate_id,
            Cost.archived_at.is_(None),  # type: ignore[union-attr]
        )
    )
    for treatment, amount in result.all():
        totals[IhtTreatment(treatment)] += amount or Decimal("0")
    return totals


async def _load_deductible_liabilities_total(
    session: AsyncSession, estate_id: uuid.UUID
) -> Decimal:
    result = await session.execute(
        select(Liability.amount).where(
            Liability.estate_id == estate_id,
            Liability.archived_at.is_(None),  # type: ignore[union-attr]
            Liability.iht_deductible == True,  # noqa: E712
        )
    )
    return sum((amount or Decimal("0") for (amount,) in result.all()), Decimal("0"))


async def _load_asset_items(
    session: AsyncSession, estate_id: uuid.UUID
) -> tuple[AssetItem, ...]:
    """All non-archived assets as categorised engine items (schedules)."""
    result = await session.execute(
        select(Asset).where(
            Asset.estate_id == estate_id,
            Asset.archived_at.is_(None),  # type: ignore[union-attr]
        )
    )
    items = []
    for asset in result.scalars().all():
        category = _CATEGORY_MAP.get((asset.category or "").strip().lower(), AssetCategory.OTHER)
        items.append(
            AssetItem(
                category=category,
                description=asset.description or "",
                value=asset.dod_value if asset.dod_value and asset.dod_value > 0 else Decimal("0"),
            )
        )
    return tuple(items)


async def assemble_estate_input(session: AsyncSession, estate: Estate) -> EngineEstate:
    """Build the pure engine's Estate input from database rows.

    Gross value is the estate share of assets (sole in full, tenants in
    common at the deceased's share, joint tenancy zero, assets passing
    outside the estate excluded). Net value deducts deductible liabilities
    and funeral-deductible costs, clamped at zero.

    TODO: exempt_transfers is 0 for now. Spouse and charity exemptions
    will be derived from beneficiary legacies (exempt_or_chargeable) once
    the exemption attribution rules are specified; until then the engine
    sees no exempt transfers, which is the conservative direction.
    """
    account_assets = await load_account_assets(session, estate.id)
    gross = sum((asset.estate_share for asset in account_assets), Decimal("0"))
    liabilities_total = await _load_deductible_liabilities_total(session, estate.id)
    costs = await sum_costs_by_treatment(session, estate.id)
    net = max(gross - liabilities_total - costs[IhtTreatment.funeral_deductible], Decimal("0"))

    return EngineEstate(
        net_value=net,
        gross_value=gross,
        tnrb_pct=estate.tnrb_pct,
        trnrb_pct=estate.trnrb_pct,
        residence_to_descendants_value=(
            estate.residence_to_descendants_value or Decimal("0")
        ),
        exempt_transfers=Decimal("0"),
        charity_share=estate.charity_share_pct,
        claims_rnrb=estate.claims_rnrb,
        assets=await _load_asset_items(session, estate.id),
        gifts_in_seven_years=estate.specified_transfers_value,
        trust_assets_value=estate.trust_property_value,
        foreign_assets_value=estate.foreign_assets_value,
        gifts_with_reservation=estate.gifts_with_reservation,
    )


async def latest_assessment(
    session: AsyncSession, estate_id: uuid.UUID
) -> IhtAssessment | None:
    """The most recent iht_assessment snapshot for the estate, if any."""
    result = await session.execute(
        select(IhtAssessment)
        .where(IhtAssessment.estate_id == estate_id)
        .order_by(IhtAssessment.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    return result.scalars().first()


async def run_recompute(
    session: AsyncSession, estate: Estate, actor: str
) -> tuple[IhtAssessment, Assessment, EngineEstate]:
    """Assemble the engine input, assess, persist a snapshot and audit it.

    The snapshot stores the engine inputs and the full result with the
    constants version used, so the executors can always see how the
    position changed and why. Flushes, never commits: the caller owns the
    transaction.
    """
    engine_input = await assemble_estate_input(session, estate)
    assessment = assess(engine_input, ENGLAND_WALES)

    row = IhtAssessment(
        estate_id=estate.id,
        created_by=actor,
        snapshot={
            "inputs": engine_input.model_dump(mode="json"),
            "result": assessment.model_dump(mode="json"),
        },
        constants_version=constants_version(),
    )
    session.add(row)
    await session.flush()
    await record_audit(
        session,
        estate_id=estate.id,
        actor=actor,
        action="recompute",
        entity=f"iht_assessment:{row.id}",
        after=row.snapshot["result"],
    )
    return row, assessment, engine_input


def _dec(raw: Any) -> Decimal:
    """Stored snapshot figure back to Decimal (None means not recorded)."""
    return Decimal(str(raw)) if raw is not None else Decimal("0")


def _rnrb_cap_engaged(snapshot: Mapping[str, Any]) -> bool:
    """Whether the (tapered) RNRB maximum caps the qualifying residence
    value, read from a stored snapshot's engine figures."""
    result = snapshot.get("result", {})
    inputs = snapshot.get("inputs", {})
    residence = _dec(inputs.get("residence_to_descendants_value")) + _dec(
        inputs.get("downsizing_addition")
    )
    return _dec(result.get("rnrb")) < residence


def _material_reasons(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    single_change_threshold: Decimal,
) -> list[str]:
    """Plain-English reasons for every material threshold crossed between
    two snapshots. All figures quoted are the engine's own output (or the
    stored inputs it was given); nothing is computed here beyond
    comparisons."""
    reasons: list[str] = []
    prev_result = previous.get("result", {})
    curr_result = current.get("result", {})
    prev_inputs = previous.get("inputs", {})
    curr_inputs = current.get("inputs", {})

    prev_tax = _dec(prev_result.get("tax"))
    curr_tax = _dec(curr_result.get("tax"))
    if (prev_tax == 0) != (curr_tax == 0):
        if curr_tax > 0:
            reasons.append(
                "the estate has crossed the tax-free allowance: inheritance tax "
                f"is now {_gbp(curr_tax)} (was {_gbp(prev_tax)})"
            )
        else:
            reasons.append(
                "the estate has moved back within the tax-free allowance: "
                f"inheritance tax is now {_gbp(curr_tax)} (was {_gbp(prev_tax)})"
            )

    taper = ENGLAND_WALES.taper_threshold.value
    prev_net = _dec(prev_inputs.get("net_value"))
    curr_net = _dec(curr_inputs.get("net_value"))
    if (prev_net > taper) != (curr_net > taper):
        direction = "above" if curr_net > taper else "back below"
        reasons.append(
            f"the net estate ({_gbp(curr_net)}) has moved {direction} the "
            f"{_gbp(taper)} residence nil rate band taper threshold"
        )

    if bool(prev_result.get("is_excepted")) != bool(curr_result.get("is_excepted")):
        if curr_result.get("is_excepted"):
            reasons.append(
                "the estate now qualifies as an excepted estate"
            )
        else:
            reasons.append(
                "the estate is no longer an excepted estate; a full IHT400 "
                "account is required"
            )

    if _rnrb_cap_engaged(previous) != _rnrb_cap_engaged(current):
        curr_rnrb = _dec(curr_result.get("rnrb"))
        residence = _dec(curr_inputs.get("residence_to_descendants_value"))
        if _rnrb_cap_engaged(current):
            reasons.append(
                "the residence nil rate band cap is now engaged: only "
                f"{_gbp(curr_rnrb)} is available against a qualifying "
                f"residence value of {_gbp(residence)}"
            )
        else:
            reasons.append(
                "the residence nil rate band cap is no longer engaged: the "
                f"full qualifying residence value of {_gbp(residence)} is "
                "covered"
            )

    for field_name in _COMPARED_INPUT_FIELDS:
        prev_value = _dec(prev_inputs.get(field_name))
        curr_value = _dec(curr_inputs.get(field_name))
        if abs(curr_value - prev_value) > single_change_threshold:
            label = field_name.replace("_", " ")
            reasons.append(
                f"the {label} changed from {_gbp(prev_value)} to "
                f"{_gbp(curr_value)}, more than "
                f"{_gbp(single_change_threshold)} in one change"
            )

    return reasons


@dataclass(slots=True)
class ReevaluationOutcome:
    """What a re-evaluation did: the new snapshot row, the engine result,
    the material reasons found (empty when nothing material) and who was
    notified."""

    assessment_row: IhtAssessment
    assessment: Assessment
    reasons: list[str] = field(default_factory=list)
    notified: list[str] = field(default_factory=list)


async def reevaluate(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    change_context: Mapping[str, Any] | None = None,
    *,
    single_change_threshold: Decimal = MATERIAL_SINGLE_CHANGE_GBP,
) -> ReevaluationOutcome:
    """Recompute the estate position after a change and alert on material
    movement (spec section 20).

    Contract for callers (PUT /estate today; the asset, liability and cost
    routers as they land):

    - Call inside the same transaction as the write that changed the
      position, after flushing the change, so the recompute sees it.
    - Pass the acting user's email as actor: the actor made the change,
      so alerts go to every OTHER executor/admin user.
    - Pass change_context describing the change for the alert message,
      e.g. {"entity": "asset:<uuid>", "summary": "Asset value updated"}.
      Only its "summary" value is quoted; everything else is free-form.
    - This function adds rows (iht_assessment, audit_event, notification)
      and flushes; it never commits or rolls back. The caller owns the
      transaction and must commit.

    Material thresholds (spec section 20 defaults): tax crossing the
    allowance (nil to positive or the reverse), the net estate crossing
    the taper threshold, a change of excepted-estate status, a change in
    whether the RNRB cap is engaged, or any single engine input moving by
    more than single_change_threshold (default 10,000, module constant
    MATERIAL_SINGLE_CHANGE_GBP).

    The first ever recompute has nothing to compare against, so it
    snapshots without alerting. Every figure in an alert message comes
    from the engine's stored snapshots, never from this service.
    """
    estate = await session.get(Estate, estate_id)
    if estate is None:
        raise ValueError(f"estate {estate_id} not found")

    previous = await latest_assessment(session, estate_id)
    row, assessment, _ = await run_recompute(session, estate, actor)

    outcome = ReevaluationOutcome(assessment_row=row, assessment=assessment)
    if previous is None:
        return outcome

    outcome.reasons = _material_reasons(
        previous.snapshot, row.snapshot, single_change_threshold
    )
    if not outcome.reasons:
        return outcome

    summary = (change_context or {}).get("summary")
    context_part = f" Change: {summary}." if summary else ""
    message = (
        "Re-evaluation alert: "
        + "; ".join(outcome.reasons)
        + "."
        + context_part
        + " Position now: inheritance tax "
        + _gbp(assessment.tax)
        + ", allowance "
        + _gbp(assessment.allowance)
        + ", taxable "
        + _gbp(assessment.taxable)
        + "."
    )

    recipients = _alert_recipients(actor)
    for email in recipients:
        session.add(
            Notification(
                estate_id=estate_id,
                created_by=actor,
                user_id=email,
                event_type=REEVALUATION_EVENT_TYPE,
                entity_ref=f"iht_assessment:{row.id}",
                message=message,
            )
        )
    if recipients:
        await session.flush()
    outcome.notified = list(recipients)
    return outcome


def _alert_recipients(actor: str) -> Sequence[str]:
    """Every executor/admin user except the actor (viewers are read-only
    observers and receive no co-executor alerts)."""
    roles = parse_user_roles(get_settings().USER_ROLES)
    actor_lower = actor.strip().lower()
    return [
        email
        for email, role in sorted(roles.items())
        if role in WRITE_ROLES and email != actor_lower
    ]
