"""Pydantic v2 schemas for the tasks and costs P1 routers.

Tasks carry dependency lists (blocked_by/blocks hold task UUIDs as
strings), a checklist of {text, done} items and nested comments. Costs
carry the reimbursement workflow flags and the by-type aggregation
response (sums of stored figures only; no derived computation).
"""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IhtTreatment


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
# Tasks
# ---------------------------------------------------------------------------


class ChecklistItem(BaseModel):
    text: str
    done: bool = False


class TaskCreate(BaseModel):
    estate_id: uuid.UUID
    title: str = Field(min_length=1)
    description: str | None = None
    assignees: list[str] = Field(default_factory=list)
    status: str | None = None
    priority: str | None = None
    start_date: dt.date | None = None
    due_date: dt.date | None = None
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    process_step_id: uuid.UUID | None = None
    source: str | None = None
    reminder: dt.date | None = None
    executor_private: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    assignees: list[str] | None = None
    status: str | None = None
    priority: str | None = None
    start_date: dt.date | None = None
    due_date: dt.date | None = None
    blocked_by: list[str] | None = None
    blocks: list[str] | None = None
    checklist: list[ChecklistItem] | None = None
    process_step_id: uuid.UUID | None = None
    source: str | None = None
    reminder: dt.date | None = None
    executor_private: bool | None = None


class TaskRead(ReadBase):
    title: str
    description: str | None
    assignees: list[str]
    status: str | None
    priority: str | None
    start_date: dt.date | None
    due_date: dt.date | None
    blocked_by: list[str]
    blocks: list[str]
    checklist: list[ChecklistItem]
    process_step_id: uuid.UUID | None
    source: str | None
    reminder: dt.date | None
    executor_private: bool


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1)


class TaskCommentRead(ReadBase):
    task_id: uuid.UUID
    body: str


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------


class CostCreate(BaseModel):
    estate_id: uuid.UUID
    description: str = Field(min_length=1)
    category: str = Field(min_length=1)
    amount: Decimal
    vat: Decimal | None = None
    date: dt.date
    paid_by: str | None = None
    payment_method: str | None = None
    reimbursable: bool = False
    reimbursed: bool = False
    reimbursed_date: dt.date | None = None
    iht_treatment: IhtTreatment = IhtTreatment.admin_not_deductible
    receipt_document_id: uuid.UUID | None = None
    executor_private: bool = False


class CostUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)
    amount: Decimal | None = None
    vat: Decimal | None = None
    date: dt.date | None = None
    paid_by: str | None = None
    payment_method: str | None = None
    reimbursable: bool | None = None
    reimbursed: bool | None = None
    reimbursed_date: dt.date | None = None
    iht_treatment: IhtTreatment | None = None
    receipt_document_id: uuid.UUID | None = None
    executor_private: bool | None = None


class CostRead(ReadBase):
    description: str
    category: str
    amount: Decimal
    vat: Decimal | None
    date: dt.date
    paid_by: str | None
    payment_method: str | None
    reimbursable: bool
    reimbursed: bool
    reimbursed_date: dt.date | None
    iht_treatment: IhtTreatment
    receipt_document_id: uuid.UUID | None
    executor_private: bool


class CategoryTotal(BaseModel):
    category: str
    total: Decimal


class TreatmentTotal(BaseModel):
    iht_treatment: IhtTreatment
    total: Decimal


class CostsByType(BaseModel):
    """Sums of stored cost amounts grouped by category and IHT treatment."""

    by_category: list[CategoryTotal]
    by_iht_treatment: list[TreatmentTotal]
