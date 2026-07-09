"""Executor decision log (Module 19).

Decisions are immutable by convention: rows carry the common base columns
plus estate scope but no soft-delete columns, and the API layer forbids
update and delete. The log protects the executors by recording what was
decided, why, and who agreed.
"""

import datetime as dt
import uuid

from sqlalchemy import JSON
from sqlmodel import Field

from .base import TableBase


class Decision(TableBase, table=True):
    """A recorded executor decision. Immutable by convention."""

    __tablename__ = "decision"

    estate_id: uuid.UUID = Field(foreign_key="estate.id", index=True, nullable=False)
    date: dt.date = Field()
    title: str = Field(index=True)
    rationale: str | None = Field(default=None)
    options_considered: list | None = Field(
        default=None,
        sa_type=JSON,
        description="Options weighed before deciding, e.g. [{option, notes}]",
    )
    agreed_by: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Email addresses of the executors who agreed",
    )
    made_by: str = Field(
        default="", description="Email address of the executor who recorded it"
    )
    executor_private: bool = Field(
        default=False,
        description=(
            "Rows flagged true are never returned to the viewer role; "
            "enforced server-side"
        ),
    )
