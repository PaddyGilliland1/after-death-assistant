"""Document store metadata. File bytes live in object storage under file_key."""


from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase


class Document(EstateScopedBase, table=True):
    """A stored document (build contract section 6)."""

    __tablename__ = "document"

    title: str = Field(index=True)
    type: str | None = Field(
        default=None, description="e.g. will, death_certificate, valuation, receipt"
    )
    file_key: str | None = Field(
        default=None, description="Object storage key for the file bytes"
    )
    mime: str | None = Field(default=None)
    version: int = Field(default=1)
    access_roles: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Roles allowed to view, e.g. executor, admin, viewer",
    )
    links: list[dict] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Inline cross-references, e.g. {entity_type, entity_id}",
    )
    executor_private: bool = Field(
        default=False,
        description=(
            "Rows flagged true are never returned to the viewer role; "
            "enforced server-side"
        ),
    )
