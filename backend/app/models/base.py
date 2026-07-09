"""Shared base classes, mixins and column types for the AD Assistant data model.

Conventions (build contract section 6):
- UUID primary keys with uuid4 defaults.
- created_at / updated_at stored as timezone-aware UTC timestamps.
- created_by holds the acting user's email address.
- Soft delete via archived_at / archive_reason on all business tables.
- Every business row belongs to exactly one estate via estate_id.
- Money is Numeric(14, 2) mapped to Decimal; percentages are Numeric(7, 4).
"""

import datetime as dt
import uuid

from sqlalchemy import DateTime, Numeric
from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    """Timezone-aware current UTC time, used for all timestamp defaults."""
    return dt.datetime.now(dt.UTC)


# Reusable SQLAlchemy type instances (type instances are safe to share
# across columns; Column objects are not).
TZDateTime = DateTime(timezone=True)
MoneyType = Numeric(14, 2)
PctType = Numeric(7, 4)


class TableBase(SQLModel):
    """Common identity and provenance columns for every table."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: dt.datetime = Field(
        default_factory=utcnow, sa_type=TZDateTime, nullable=False
    )
    updated_at: dt.datetime = Field(
        default_factory=utcnow,
        sa_type=TZDateTime,
        sa_column_kwargs={"onupdate": utcnow},
        nullable=False,
    )
    created_by: str = Field(
        default="", description="Email address of the user who created the row"
    )


class SoftDeleteMixin(SQLModel):
    """Soft delete columns. Rows are archived, never physically deleted."""

    archived_at: dt.datetime | None = Field(
        default=None, sa_type=TZDateTime, nullable=True
    )
    archive_reason: str | None = Field(default=None)


class EstateScopedBase(TableBase, SoftDeleteMixin):
    """Base for all business tables: identity, soft delete and estate scope."""

    estate_id: uuid.UUID = Field(foreign_key="estate.id", index=True, nullable=False)
