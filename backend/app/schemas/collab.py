"""Pydantic schemas for the P1 collaboration layer.

Covers documents, notifications, audit and activity, search, process
steps, timeline, deadlines, approvals, and the seed-file structure the
seeding service validates before touching the database (Cardinal Rule 5:
all data exchange goes through Pydantic).
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROLE_NAMES = frozenset({"executor", "admin", "viewer"})


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    type: str | None = None
    mime: str | None = None
    version: int
    access_roles: list[str] = Field(default_factory=list)
    executor_private: bool = False
    links: list[dict] = Field(default_factory=list)
    created_at: dt.datetime
    created_by: str = ""


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    entity_ref: str | None = None
    message: str = ""
    read_at: dt.datetime | None = None
    created_at: dt.datetime


class ReadAllResult(BaseModel):
    marked_read: int


# ---------------------------------------------------------------------------
# Audit, activity and search
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: str
    action: str
    entity: str
    before: dict | None = None
    after: dict | None = None
    timestamp: dt.datetime


class ActivityItemOut(BaseModel):
    """Audit event summarised for the activity feed (no before/after payloads)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: str
    action: str
    entity: str
    timestamp: dt.datetime


class SearchHit(BaseModel):
    type: Literal["contact", "asset", "task", "document", "cost"]
    id: uuid.UUID
    label: str


# ---------------------------------------------------------------------------
# Process steps, timeline and deadlines
# ---------------------------------------------------------------------------


class ProcessStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order: int
    name: str
    status: str | None = None
    deadline_id: uuid.UUID | None = None


class ProcessStepPatch(BaseModel):
    """PATCH body for a process step: status only."""

    status: Literal["not_started", "in_progress", "done", "blocked"]


class TimelineEntryOut(BaseModel):
    step_id: uuid.UUID
    order: int
    name: str
    stored_status: str | None = None
    derived_status: Literal["done", "current", "upcoming"]
    deadline_type: str | None = None
    deadline_date: dt.date | None = None


class DeadlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    derived_date: dt.date | None = None
    reminders: list[dict] = Field(default_factory=list)


class DeadlineRecomputeOut(BaseModel):
    created: int
    updated: int
    deadlines: list[DeadlineOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


class ApprovalCreate(BaseModel):
    entity_ref: str = Field(min_length=3, description="e.g. document:<uuid>")
    draft_kind: str = Field(min_length=2, description="e.g. iht400_draft")


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_ref: str
    draft_kind: str
    approved_by: str | None = None
    approved_at: dt.datetime | None = None
    created_at: dt.datetime


# ---------------------------------------------------------------------------
# Seed file structure (validated before any database write)
# ---------------------------------------------------------------------------


class SeedEstateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    date_of_death: dt.date | None = None
    grant_date: dt.date | None = None
    constants_version: str | None = None
    tnrb_pct: Decimal = Decimal("0")
    trnrb_pct: Decimal = Decimal("0")
    residence_to_descendants_value: Decimal | None = None
    charity_share_pct: Decimal = Decimal("0")


class SeedAssetIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    sub_type: str | None = None
    description: str = ""
    ownership: str = "sole"
    dod_value: Decimal | None = None
    value_basis: str = "estimate"
    rnrb_qualifying: bool = False
    iht_schedule: str | None = None
    status: str | None = None


class SeedLegacyIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    beneficiary_name: str
    legacy_type: str
    amount_or_share: Decimal | None = None
    exempt_or_chargeable: str | None = None
    status: str | None = None


class SeedGiftIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = ""
    amount: Decimal | None = None
    value_basis: str = "estimate"


class SeedTasksIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    seed_from: str | None = None
    note: str | None = None


class SeedFileIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    estate: SeedEstateIn
    assets: list[SeedAssetIn] = Field(default_factory=list)
    beneficiary_legacies: list[SeedLegacyIn] = Field(default_factory=list)
    gifts: list[SeedGiftIn] = Field(default_factory=list)
    tasks: SeedTasksIn | None = None


class Section25EntryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order: int
    phase: str | None = None
    title: str
    description: str | None = None
    depends_on: list[int] = Field(default_factory=list)
    suggested_owner_role: str | None = None


class SeedReport(BaseModel):
    """What a seed run did (or skipped)."""

    skipped: bool = False
    estate_created: bool = False
    contacts_created: int = 0
    assets_created: int = 0
    legacies_created: int = 0
    steps_created: int = 0
    tasks_created: int = 0
    skipped_gifts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
