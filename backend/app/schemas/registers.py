"""Pydantic v2 schemas for the P1 register routers (build contract section 8).

Registers covered: assets (with valuation events), liabilities, debtors,
creditors, and Section 27 creditor notices with their claims.

Conventions:
- Create schemas carry estate_id plus the business fields.
- Update schemas make every field optional; routers apply them with
  model_dump(exclude_unset=True) for true partial updates.
- Read schemas add id, estate_id and the audit columns (created_at,
  updated_at, created_by, archived_at, archive_reason).
- Registers store and return data only; no cost or income figure is ever
  calculated here (guardrail: deterministic money lives in app.domain).

Also hosts snapshot(), the JSON-safe serialiser used by the register
routers for audit_event before/after snapshots.
"""

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlmodel import SQLModel

from app.models.enums import OwnershipType, ValueBasis


def snapshot(row: SQLModel) -> dict[str, Any]:
    """Serialise a model row into a JSON-safe dict for audit snapshots.

    Decimal, date, datetime and UUID values are rendered as strings so the
    result can be stored in a JSON column and replayed without loss.
    """
    return json.loads(json.dumps(row.model_dump(), default=str))


class ArchiveRequest(BaseModel):
    """Body for soft-delete (archive) requests."""

    reason: str | None = None


class ReadAuditFields(BaseModel):
    """Identity and provenance columns shared by every Read schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estate_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by: str
    archived_at: dt.datetime | None
    archive_reason: str | None


# ---------------------------------------------------------------------------
# Assets and valuation events
# ---------------------------------------------------------------------------


class AssetBase(BaseModel):
    category: str
    sub_type: str | None = None
    description: str = ""
    holder_contact_id: uuid.UUID | None = None
    account_reference: str | None = None
    ownership: OwnershipType = OwnershipType.sole
    tic_share_pct: Decimal | None = None
    dod_value: Decimal | None = None
    value_basis: ValueBasis = ValueBasis.estimate
    valuation_source: str | None = None
    valuation_date: dt.date | None = None
    current_or_realised_value: Decimal | None = None
    realised_date: dt.date | None = None
    income_since_death: Decimal | None = None
    iht_schedule: str | None = None
    rnrb_qualifying: bool = False
    passes_outside_estate: bool = False
    status: str | None = None


class AssetCreate(AssetBase):
    estate_id: uuid.UUID


class AssetUpdate(BaseModel):
    category: str | None = None
    sub_type: str | None = None
    description: str | None = None
    holder_contact_id: uuid.UUID | None = None
    account_reference: str | None = None
    ownership: OwnershipType | None = None
    tic_share_pct: Decimal | None = None
    dod_value: Decimal | None = None
    value_basis: ValueBasis | None = None
    valuation_source: str | None = None
    valuation_date: dt.date | None = None
    current_or_realised_value: Decimal | None = None
    realised_date: dt.date | None = None
    income_since_death: Decimal | None = None
    iht_schedule: str | None = None
    rnrb_qualifying: bool | None = None
    passes_outside_estate: bool | None = None
    status: str | None = None


class AssetRead(AssetBase, ReadAuditFields):
    pass


class ValuationEventCreate(BaseModel):
    """A dated valuation of an asset; also refreshes the asset's current
    value fields (current_or_realised_value, value_basis, valuation_source,
    valuation_date)."""

    value: Decimal
    basis: ValueBasis = ValueBasis.estimate
    source: str | None = None
    date: dt.date


class ValuationEventRead(ReadAuditFields):
    asset_id: uuid.UUID
    value: Decimal
    basis: ValueBasis
    source: str | None
    date: dt.date


# ---------------------------------------------------------------------------
# Liabilities
# ---------------------------------------------------------------------------


class LiabilityBase(BaseModel):
    type: str
    creditor_contact_id: uuid.UUID | None = None
    amount: Decimal
    as_at_date: dt.date | None = None
    status: str | None = None
    iht_deductible: bool = True


class LiabilityCreate(LiabilityBase):
    estate_id: uuid.UUID


class LiabilityUpdate(BaseModel):
    type: str | None = None
    creditor_contact_id: uuid.UUID | None = None
    amount: Decimal | None = None
    as_at_date: dt.date | None = None
    status: str | None = None
    iht_deductible: bool | None = None


class LiabilityRead(LiabilityBase, ReadAuditFields):
    pass


# ---------------------------------------------------------------------------
# Debtors (money owed TO the estate)
# ---------------------------------------------------------------------------


class DebtorBase(BaseModel):
    source_contact_id: uuid.UUID | None = None
    type: str
    amount_expected: Decimal | None = None
    amount_received: Decimal | None = None
    status: str | None = None
    expected_date: dt.date | None = None
    received_into_asset_id: uuid.UUID | None = None


class DebtorCreate(DebtorBase):
    estate_id: uuid.UUID


class DebtorUpdate(BaseModel):
    source_contact_id: uuid.UUID | None = None
    type: str | None = None
    amount_expected: Decimal | None = None
    amount_received: Decimal | None = None
    status: str | None = None
    expected_date: dt.date | None = None
    received_into_asset_id: uuid.UUID | None = None


class DebtorRead(DebtorBase, ReadAuditFields):
    pass


# ---------------------------------------------------------------------------
# Creditors (money owed BY the estate)
# ---------------------------------------------------------------------------


class CreditorBase(BaseModel):
    creditor_contact_id: uuid.UUID | None = None
    type: str
    amount_claimed: Decimal | None = None
    amount_agreed: Decimal | None = None
    amount_paid: Decimal | None = None
    status: str | None = None
    priority_class: str | None = None
    paid_from_asset_id: uuid.UUID | None = None


class CreditorCreate(CreditorBase):
    estate_id: uuid.UUID


class CreditorUpdate(BaseModel):
    creditor_contact_id: uuid.UUID | None = None
    type: str | None = None
    amount_claimed: Decimal | None = None
    amount_agreed: Decimal | None = None
    amount_paid: Decimal | None = None
    status: str | None = None
    priority_class: str | None = None
    paid_from_asset_id: uuid.UUID | None = None


class CreditorRead(CreditorBase, ReadAuditFields):
    pass


# ---------------------------------------------------------------------------
# Section 27 creditor notices and claims received
# ---------------------------------------------------------------------------


class CreditorNoticeBase(BaseModel):
    gazette_ref: str | None = None
    gazette_date: dt.date | None = None
    local_paper: str | None = None
    local_date: dt.date | None = None


class CreditorNoticeCreate(CreditorNoticeBase):
    estate_id: uuid.UUID


class CreditorNoticeUpdate(BaseModel):
    gazette_ref: str | None = None
    gazette_date: dt.date | None = None
    local_paper: str | None = None
    local_date: dt.date | None = None


class CreditorNoticeRead(CreditorNoticeBase, ReadAuditFields):
    claim_deadline: dt.date | None
    safe_to_distribute: bool | None


class NoticeClaimCreate(BaseModel):
    claimant: str
    amount: Decimal | None = None
    status: str | None = None


class NoticeClaimUpdate(BaseModel):
    claimant: str | None = None
    amount: Decimal | None = None
    status: str | None = None


class NoticeClaimRead(ReadAuditFields):
    creditor_notice_id: uuid.UUID
    claimant: str
    amount: Decimal | None
    status: str | None


class SafeToDistributeResponse(BaseModel):
    """Overall distribution guard for Module 6: true only when every active
    Section 27 notice has a claim deadline in the past and no open claims."""

    safe_to_distribute: bool
    checked_on: dt.date
    reasons: list[str]
