"""Process timeline steps and the statutory deadlines engine."""

import datetime as dt
import uuid

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase


class Deadline(EstateScopedBase, table=True):
    """A statutory or derived deadline (build contract section 6)."""

    __tablename__ = "deadline"

    type: str = Field(
        index=True, description="e.g. iht_payment, creditor_claim, cgt_60_day"
    )
    derived_date: dt.date | None = Field(default=None)
    reminders: list[dict] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Reminder entries, e.g. {date, sent}",
    )


class ProcessStep(EstateScopedBase, table=True):
    """A step in the probate process timeline."""

    __tablename__ = "process_step"

    order: int = Field(default=0, index=True)
    name: str = Field(default="")
    status: str | None = Field(
        default=None, description="Derived from the state of linked tasks"
    )
    deadline_id: uuid.UUID | None = Field(
        default=None, foreign_key="deadline.id", index=True
    )
