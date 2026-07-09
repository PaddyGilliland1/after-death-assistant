"""Estate endpoints: settings, dashboard summary, estate accounts and the
UK GDPR export and erasure endpoints.

- GET  /estate          settings (RNRB claim and excepted-estate facts)
- PUT  /estate          update settings (write roles); audited; triggers
                        the section 20 re-evaluation
- GET  /estate/summary  dashboard aggregates (SQL aggregates; zeros on an
                        empty database)
- GET  /estate/accounts trial balance from the pure domain module
- GET  /estate/export   complete JSON export of every estate-scoped table
                        (UK GDPR portability; admin and executor)
- POST /estate/erase    HARD-DELETES every estate row (UK GDPR erasure;
                        admin only, explicit confirmation string required)

The estate is single-row for now (the first row is the estate under
administration; the seed loader creates it), but estate_id stays explicit
in every query so multi-estate support needs no query changes.
"""

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.core.auth import AdminUser, ReadUser, WriteUser
from app.db import get_session
from app.domain.estate_accounts import (
    AccountLiability,
    EstateAccountsInput,
    Legacy,
    LegacyType,
    compute_accounts,
)
from app.models import (
    Asset,
    BeneficiaryLegacy,
    Contact,
    Cost,
    Distribution,
    Estate,
    Liability,
    Task,
)
from app.models.enums import IhtTreatment, OwnershipType
from app.models.enums import LegacyType as DbLegacyType
from app.schemas.estate import (
    AccountsDistributionRead,
    EstateAccountsRead,
    EstateSettingsRead,
    EstateSettingsUpdate,
    EstateSummary,
)
from app.services.reevaluation import (
    latest_assessment,
    load_account_assets,
    record_audit,
    reevaluate,
    sum_costs_by_treatment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estate", tags=["estate"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Task statuses counted as closed for the dashboard's open-task figure.
_CLOSED_TASK_STATUSES = ("done", "completed", "closed", "cancelled")


async def get_estate_or_404(session: AsyncSession) -> Estate:
    """The estate under administration: the first non-archived estate row."""
    result = await session.execute(
        select(Estate)
        .where(Estate.archived_at.is_(None))  # type: ignore[union-attr]
        .order_by(Estate.created_at)  # type: ignore[arg-type]
        .limit(1)
    )
    estate = result.scalars().first()
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate has been set up yet.",
        )
    return estate


def _jsonable(value: Any) -> Any:
    """Audit snapshots must be JSON-safe; Decimals stay exact as strings."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


@router.get("", response_model=EstateSettingsRead)
async def get_estate(session: SessionDep, user: ReadUser) -> EstateSettingsRead:
    """The estate settings, including the RNRB claim and the
    excepted-estate disqualifier facts (None means unknown)."""
    estate = await get_estate_or_404(session)
    return EstateSettingsRead.model_validate(estate)


@router.put("", response_model=EstateSettingsRead)
async def update_estate(
    body: EstateSettingsUpdate, session: SessionDep, user: WriteUser
) -> EstateSettingsRead:
    """Update the estate settings (write roles only).

    Emits an audit event with the before and after state of the changed
    fields, then triggers the section 20 re-evaluation: recompute,
    snapshot, and alert the other executors on a material change.
    """
    estate = await get_estate_or_404(session)
    changes = body.model_dump(exclude_unset=True)

    before = {name: _jsonable(getattr(estate, name)) for name in changes}
    for name, value in changes.items():
        setattr(estate, name, value)
    after = {name: _jsonable(value) for name, value in changes.items()}
    await session.flush()

    await record_audit(
        session,
        estate_id=estate.id,
        actor=user.email,
        action="update",
        entity=f"estate:{estate.id}",
        before=before,
        after=after,
    )
    await reevaluate(
        session,
        estate.id,
        user.email,
        change_context={
            "entity": f"estate:{estate.id}",
            "summary": "estate settings updated ("
            + ", ".join(sorted(changes)) + ")",
        },
    )
    await session.commit()
    return EstateSettingsRead.model_validate(estate)


@router.get("/summary", response_model=EstateSummary)
async def estate_summary(session: SessionDep, user: ReadUser) -> EstateSummary:
    """Dashboard aggregates, computed with SQL aggregates. On an empty
    database (no estate row yet) every figure is zero. The IHT due figure
    is read from the latest engine snapshot, never computed here."""
    result = await session.execute(
        select(Estate)
        .where(Estate.archived_at.is_(None))  # type: ignore[union-attr]
        .order_by(Estate.created_at)  # type: ignore[arg-type]
        .limit(1)
    )
    estate = result.scalars().first()
    if estate is None:
        zero = Decimal("0")
        return EstateSummary(
            gross_assets_at_dod=zero,
            net_estate=zero,
            iht_due=zero,
            open_task_count=0,
            unnotified_contact_count=0,
            costs_total=zero,
        )

    estate_id = estate.id
    zero = Decimal("0")

    gross = (
        await session.execute(
            select(func.coalesce(func.sum(func.coalesce(Asset.dod_value, 0)), 0)).where(
                Asset.estate_id == estate_id,
                Asset.archived_at.is_(None),  # type: ignore[union-attr]
            )
        )
    ).scalar_one()

    # Estate share per asset: sole in full, tenants in common at the
    # deceased's share, joint tenancy passes by survivorship (zero).
    share_expr = case(
        (
            Asset.ownership == OwnershipType.sole,
            func.coalesce(Asset.dod_value, 0),
        ),
        (
            Asset.ownership == OwnershipType.tenants_in_common,
            func.coalesce(Asset.dod_value, 0) * func.coalesce(Asset.tic_share_pct, 1),
        ),
        else_=0,
    )
    estate_share_total = (
        await session.execute(
            select(func.coalesce(func.sum(share_expr), 0)).where(
                Asset.estate_id == estate_id,
                Asset.archived_at.is_(None),  # type: ignore[union-attr]
                Asset.passes_outside_estate == False,  # noqa: E712
            )
        )
    ).scalar_one()
    deductible_liabilities = (
        await session.execute(
            select(func.coalesce(func.sum(Liability.amount), 0)).where(
                Liability.estate_id == estate_id,
                Liability.archived_at.is_(None),  # type: ignore[union-attr]
                Liability.iht_deductible == True,  # noqa: E712
            )
        )
    ).scalar_one()
    funeral_costs = (
        await session.execute(
            select(func.coalesce(func.sum(Cost.amount), 0)).where(
                Cost.estate_id == estate_id,
                Cost.archived_at.is_(None),  # type: ignore[union-attr]
                Cost.iht_treatment == IhtTreatment.funeral_deductible,
            )
        )
    ).scalar_one()

    open_tasks = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.estate_id == estate_id,
                Task.archived_at.is_(None),  # type: ignore[union-attr]
                (Task.status.is_(None))  # type: ignore[union-attr]
                | (Task.status.not_in(_CLOSED_TASK_STATUSES)),  # type: ignore[union-attr]
            )
        )
    ).scalar_one()

    unnotified_contacts = (
        await session.execute(
            select(func.count()).select_from(Contact).where(
                Contact.estate_id == estate_id,
                Contact.archived_at.is_(None),  # type: ignore[union-attr]
                Contact.notify_required == True,  # noqa: E712
                Contact.notified_date.is_(None),  # type: ignore[union-attr]
            )
        )
    ).scalar_one()

    costs_total = (
        await session.execute(
            select(func.coalesce(func.sum(Cost.amount), 0)).where(
                Cost.estate_id == estate_id,
                Cost.archived_at.is_(None),  # type: ignore[union-attr]
            )
        )
    ).scalar_one()

    latest = await latest_assessment(session, estate_id)
    iht_due = zero
    if latest is not None:
        tax = latest.snapshot.get("result", {}).get("tax")
        if tax is not None:
            iht_due = Decimal(str(tax))

    return EstateSummary(
        gross_assets_at_dod=Decimal(gross),
        net_estate=Decimal(estate_share_total)
        - Decimal(deductible_liabilities)
        - Decimal(funeral_costs),
        iht_due=iht_due,
        open_task_count=int(open_tasks),
        unnotified_contact_count=int(unnotified_contacts),
        costs_total=Decimal(costs_total),
    )


@router.get("/accounts", response_model=EstateAccountsRead)
async def estate_accounts(session: SessionDep, user: ReadUser) -> EstateAccountsRead:
    """The trial balance: estate accounts drawn up by the pure domain
    module from the registers, with the reconciliation flag.

    Inputs are assembled from rows: assets with their ownership basis,
    deductible liabilities, funeral and admin costs by IHT treatment,
    income received since death, legacies, interim distributions against
    residuary legacies, and the IHT due from the latest engine snapshot.
    """
    estate = await get_estate_or_404(session)

    account_assets = await load_account_assets(session, estate.id)

    liabilities_result = await session.execute(
        select(Liability).where(
            Liability.estate_id == estate.id,
            Liability.archived_at.is_(None),  # type: ignore[union-attr]
        )
    )
    liabilities = tuple(
        AccountLiability(
            identifier=str(liability.id),
            amount=liability.amount,
            deductible=liability.iht_deductible,
        )
        for liability in liabilities_result.scalars().all()
    )

    costs = await sum_costs_by_treatment(session, estate.id)

    income_received = (
        await session.execute(
            select(func.coalesce(func.sum(Asset.income_since_death), 0)).where(
                Asset.estate_id == estate.id,
                Asset.archived_at.is_(None),  # type: ignore[union-attr]
                Asset.passes_outside_estate == False,  # noqa: E712
            )
        )
    ).scalar_one()

    legacies_result = await session.execute(
        select(BeneficiaryLegacy).where(
            BeneficiaryLegacy.estate_id == estate.id,
            BeneficiaryLegacy.archived_at.is_(None),  # type: ignore[union-attr]
        )
    )
    legacies = []
    for legacy in legacies_result.scalars().all():
        residuary = legacy.legacy_type == DbLegacyType.residuary
        legacies.append(
            Legacy(
                beneficiary_id=str(legacy.beneficiary_contact_id),
                legacy_type=LegacyType(legacy.legacy_type.value),
                amount=None if residuary else (legacy.amount_or_share or Decimal("0")),
                share=legacy.amount_or_share if residuary else None,
                chargeable=(legacy.exempt_or_chargeable or "").strip().lower() != "exempt",
            )
        )

    # Interim distributions count against residuary entitlements only;
    # payments against pecuniary or specific legacies settle the legacy.
    interim_result = await session.execute(
        select(
            BeneficiaryLegacy.beneficiary_contact_id,
            func.coalesce(func.sum(Distribution.amount), 0),
        )
        .select_from(Distribution)
        .join(
            BeneficiaryLegacy,
            Distribution.beneficiary_legacy_id == BeneficiaryLegacy.id,  # type: ignore[arg-type]
        )
        .where(
            Distribution.estate_id == estate.id,
            Distribution.archived_at.is_(None),  # type: ignore[union-attr]
            BeneficiaryLegacy.legacy_type == DbLegacyType.residuary,
        )
        .group_by(BeneficiaryLegacy.beneficiary_contact_id)  # type: ignore[arg-type]
    )
    interim = {str(contact_id): Decimal(total) for contact_id, total in interim_result.all()}

    latest = await latest_assessment(session, estate.id)
    iht_due = Decimal("0")
    if latest is not None:
        tax = latest.snapshot.get("result", {}).get("tax")
        if tax is not None:
            iht_due = Decimal(str(tax))

    try:
        inputs = EstateAccountsInput(
            assets=account_assets,
            liabilities=liabilities,
            funeral_costs=costs[IhtTreatment.funeral_deductible],
            admin_costs=costs[IhtTreatment.admin_not_deductible],
            iht_due=iht_due,
            income_received=Decimal(income_received),
            legacies=tuple(legacies),
            interim_distributions=interim,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Estate accounts cannot be drawn up from the registers: {exc}",
        ) from exc

    accounts = compute_accounts(inputs)
    return EstateAccountsRead(
        net_estate=accounts.net_estate,
        capital_account=accounts.capital_account,
        income_account=accounts.income_account,
        administration_account=accounts.administration_account,
        legacies_total=accounts.legacies_total,
        residue=accounts.residue,
        distribution_account=accounts.distribution_account,
        distributions=[
            AccountsDistributionRead(
                beneficiary_id=d.beneficiary_id,
                residuary_share=d.residuary_share,
                entitlement=d.entitlement,
                interim_received=d.interim_received,
                remaining_due=d.remaining_due,
            )
            for d in accounts.distributions
        ],
        is_balanced=accounts.is_balanced(),
    )


# ---------------------------------------------------------------------------
# UK GDPR: estate data export and estate erasure (VALIDATION.md RQ-1)
# ---------------------------------------------------------------------------


def _export_safe(value: Any) -> Any:
    """Make any raw column value JSON-safe for the export payload.

    Extends _jsonable to the extra shapes raw table rows can carry:
    nested lists and dicts (JSON columns), pgvector embeddings (numpy
    arrays or float lists) and bytes.
    """
    if isinstance(value, dict):
        return {key: _export_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_export_safe(item) for item in value]
    if hasattr(value, "tolist"):  # numpy array (pgvector embedding)
        return _export_safe(value.tolist())
    if isinstance(value, bytes):
        return value.hex()
    return _jsonable(value)


def _estate_scoped_tables() -> list[Any]:
    """Every table that carries estate_id, in FK dependency order
    (parents first). The estate table itself is handled separately."""
    return [
        table
        for table in SQLModel.metadata.sorted_tables
        if table.name != "estate" and "estate_id" in table.c
    ]


@router.get("/export")
async def export_estate(session: SessionDep, user: WriteUser) -> dict[str, Any]:
    """Complete JSON export of the estate (UK GDPR Article 20 portability).

    Available to admin and executor roles. Iterates every estate-scoped
    table registered on the model metadata, so new tables are exported
    automatically, and serialises each row JSON-safe (Decimals as exact
    strings, dates and UUIDs as ISO strings, embeddings as float lists).
    The export itself is audited.
    """
    estate = await get_estate_or_404(session)

    tables: dict[str, list[dict[str, Any]]] = {}
    for table in _estate_scoped_tables():
        result = await session.execute(
            table.select().where(table.c.estate_id == estate.id)
        )
        tables[table.name] = [
            {column: _export_safe(value) for column, value in row.items()}
            for row in result.mappings().all()
        ]

    estate_result = await session.execute(
        SQLModel.metadata.tables["estate"].select().where(
            SQLModel.metadata.tables["estate"].c.id == estate.id
        )
    )
    estate_row = estate_result.mappings().one()

    await record_audit(
        session,
        estate_id=estate.id,
        actor=user.email,
        action="export",
        entity=f"estate:{estate.id}",
        after={"tables": len(tables), "rows": sum(len(rows) for rows in tables.values())},
    )
    await session.commit()

    return {
        "format": "ad-assistant-estate-export",
        "format_version": 1,
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "exported_by": user.email,
        "estate": {column: _export_safe(value) for column, value in estate_row.items()},
        "tables": tables,
    }


class EstateEraseRequest(BaseModel):
    """Erasure must be confirmed by typing the estate's exact name."""

    confirm: str = Field(description="Must exactly match the estate name")


class EstateEraseResult(BaseModel):
    erased_estate_id: uuid.UUID
    rows_deleted: dict[str, int]


@router.post("/erase", response_model=EstateEraseResult)
async def erase_estate(
    body: EstateEraseRequest, session: SessionDep, user: AdminUser
) -> EstateEraseResult:
    """HARD-DELETE the estate and every row belonging to it (UK GDPR
    Article 17 erasure).

    This is the ONE endpoint in the application allowed to hard-delete.
    Soft delete (archiving) is not erasure: erased personal data must not
    remain recoverable in the database. Guards, deliberately layered:

    - Admin role only (enforced by the AdminUser dependency).
    - The request body must carry the estate's exact name in "confirm";
      anything else is refused with 400 and nothing is touched.
    - An estate with no name cannot be erased until one is set, so the
      confirmation string can never be an empty match.

    Deletion runs inside a single transaction, child tables before parents
    (reverse FK dependency order), finishing with the estate row itself.
    The audit trail dies with the estate by design, so the erasure is
    recorded as a survivor line in the application log (estate id and row
    counts only, no personal data). Stored document files are removed from
    object storage best-effort after the transaction commits.
    """
    estate = await get_estate_or_404(session)

    if not (estate.name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This estate has no name, so the confirmation string cannot be "
                "verified. Set the estate name before requesting erasure."
            ),
        )
    if body.confirm != estate.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Confirmation text does not match the estate name exactly. "
                "Nothing has been deleted."
            ),
        )

    # Collect object-storage keys before the rows disappear.
    document_table = SQLModel.metadata.tables["document"]
    file_keys: list[str] = []
    documents_result = await session.execute(
        select(document_table.c.file_key, document_table.c.links).where(
            document_table.c.estate_id == estate.id
        )
    )
    for file_key, links in documents_result.all():
        if file_key:
            file_keys.append(file_key)
        for link in links or []:
            previous = link.get("file_key") if isinstance(link, dict) else None
            if previous:
                file_keys.append(previous)
    knowledge_table = SQLModel.metadata.tables["knowledge_doc"]
    raw_keys_result = await session.execute(
        select(knowledge_table.c.raw_file_key).where(
            knowledge_table.c.estate_id == estate.id,
            knowledge_table.c.raw_file_key.is_not(None),
        )
    )
    file_keys.extend(key for (key,) in raw_keys_result.all() if key)

    # Hard delete, children before parents, one transaction.
    rows_deleted: dict[str, int] = {}
    for table in reversed(_estate_scoped_tables()):
        result = await session.execute(
            table.delete().where(table.c.estate_id == estate.id)
        )
        if result.rowcount:
            rows_deleted[table.name] = result.rowcount
    estate_table = SQLModel.metadata.tables["estate"]
    await session.execute(estate_table.delete().where(estate_table.c.id == estate.id))
    rows_deleted["estate"] = 1
    await session.commit()

    # Survivor log line: the audit rows were deleted with the estate.
    logger.warning(
        "ESTATE ERASED (UK GDPR): estate_id=%s erased_by=%s rows_deleted=%s",
        estate.id,
        user.email,
        rows_deleted,
    )

    from app.services.storage import get_storage

    storage = get_storage()
    for key in file_keys:
        try:
            storage.delete(key)
        except Exception as exc:  # noqa: BLE001 - best-effort file cleanup
            logger.warning("Erasure: could not delete stored file %s: %s", key, exc)

    return EstateEraseResult(erased_estate_id=estate.id, rows_deleted=rows_deleted)
