"""Pydantic v2 schemas for the people-facing P1 routers.

Covers contacts (with the notification tracker fields and nested
interactions), beneficiary legacies with recorded distributions, and the
immutable executor decision log. Create/Update/Read triples follow the
project CRUD conventions: Update schemas are fully optional and applied
with exclude_unset, Read schemas serialise straight from ORM rows.
"""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContactCategory, LegacyType


class ReadBase(BaseModel):
    """Common read-side columns shared by every business table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estate_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by: str
    archived_at: dt.datetime | None = None
    archive_reason: str | None = None


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


class ContactCreate(BaseModel):
    estate_id: uuid.UUID
    name: str = Field(min_length=1)
    kind: str | None = None
    category: ContactCategory = ContactCategory.other
    org: str | None = None
    relationship: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    references: list[str] = Field(default_factory=list)
    holds_or_handles: str | None = None
    notify_required: bool = False
    notification_status: str | None = None
    notified_date: dt.date | None = None
    notified_method: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    kind: str | None = None
    category: ContactCategory | None = None
    org: str | None = None
    relationship: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    references: list[str] | None = None
    holds_or_handles: str | None = None
    notify_required: bool | None = None
    notification_status: str | None = None
    notified_date: dt.date | None = None
    notified_method: str | None = None


class ContactRead(ReadBase):
    name: str
    kind: str | None
    category: ContactCategory
    org: str | None
    relationship: str | None
    email: str | None
    phone: str | None
    address: str | None
    references: list[str]
    holds_or_handles: str | None
    notify_required: bool
    notification_status: str | None
    notified_date: dt.date | None
    notified_method: str | None


class ContactInteractionCreate(BaseModel):
    date: dt.date
    channel: str | None = None
    direction: str | None = None
    summary: str | None = None
    follow_up_date: dt.date | None = None
    executor_private: bool = False


class ContactInteractionRead(ReadBase):
    contact_id: uuid.UUID
    date: dt.date
    channel: str | None
    direction: str | None
    summary: str | None
    follow_up_date: dt.date | None
    by_user: str
    executor_private: bool


# ---------------------------------------------------------------------------
# Beneficiary legacies and distributions
# ---------------------------------------------------------------------------


class BeneficiaryLegacyCreate(BaseModel):
    estate_id: uuid.UUID
    beneficiary_contact_id: uuid.UUID
    legacy_type: LegacyType
    amount_or_share: Decimal | None = None
    exempt_or_chargeable: str | None = None
    tax_bearing: bool | None = None
    status: str | None = None


class BeneficiaryLegacyUpdate(BaseModel):
    beneficiary_contact_id: uuid.UUID | None = None
    legacy_type: LegacyType | None = None
    amount_or_share: Decimal | None = None
    exempt_or_chargeable: str | None = None
    tax_bearing: bool | None = None
    status: str | None = None


class BeneficiaryLegacyRead(ReadBase):
    beneficiary_contact_id: uuid.UUID
    legacy_type: LegacyType
    amount_or_share: Decimal | None
    exempt_or_chargeable: str | None
    tax_bearing: bool | None
    status: str | None
    distributed_total: Decimal = Decimal("0")


class DistributionCreate(BaseModel):
    amount: Decimal
    date: dt.date
    method: str | None = None


class DistributionRead(ReadBase):
    beneficiary_legacy_id: uuid.UUID
    amount: Decimal
    date: dt.date
    method: str | None


# ---------------------------------------------------------------------------
# Decisions (Module 19, immutable once recorded)
# ---------------------------------------------------------------------------


class DecisionCreate(BaseModel):
    estate_id: uuid.UUID
    date: dt.date
    title: str = Field(min_length=1)
    rationale: str | None = None
    options_considered: list[dict] | None = None
    agreed_by: list[str] = Field(default_factory=list)
    executor_private: bool = False


class DecisionRead(BaseModel):
    """Decisions carry no soft-delete columns, so no ReadBase here."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estate_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by: str
    date: dt.date
    title: str
    rationale: str | None
    options_considered: list[dict] | None
    agreed_by: list[str]
    made_by: str
    executor_private: bool
