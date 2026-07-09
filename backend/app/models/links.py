"""Generic cross-reference link table.

Any record can link to any other (contacts, tasks, costs, documents and so
on) via typed endpoints. Per the build contract this table carries estate_id
and created_at/created_by only; links are removed, not soft deleted.
"""

import datetime as dt
import uuid

from sqlmodel import Field, SQLModel

from .base import TZDateTime, utcnow


class Link(SQLModel, table=True):
    """A directed cross-reference between two records (contract section 6)."""

    __tablename__ = "link"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    estate_id: uuid.UUID = Field(foreign_key="estate.id", index=True, nullable=False)
    from_type: str = Field(index=True, description="Source table name, e.g. asset")
    from_id: uuid.UUID = Field(index=True)
    to_type: str = Field(index=True, description="Target table name, e.g. document")
    to_id: uuid.UUID = Field(index=True)
    created_at: dt.datetime = Field(
        default_factory=utcnow, sa_type=TZDateTime, nullable=False
    )
    created_by: str = Field(
        default="", description="Email address of the user who created the link"
    )
