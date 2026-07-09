"""Contacts CRM: every person and organisation the estate deals with."""

import datetime as dt
import uuid

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase
from .enums import ContactCategory, str_enum_type


class Contact(EstateScopedBase, table=True):
    """A person or organisation connected to the estate."""

    __tablename__ = "contact"

    kind: str | None = Field(
        default=None, description="Free-text kind, e.g. person or organisation"
    )
    category: ContactCategory = Field(
        default=ContactCategory.other,
        sa_type=str_enum_type(ContactCategory),
        index=True,
    )
    name: str = Field(index=True)
    org: str | None = Field(default=None)
    relationship: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    address: str | None = Field(default=None)
    references: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Account or policy references held with this contact",
    )
    holds_or_handles: str | None = Field(
        default=None, description="What this contact holds or handles for the estate"
    )
    notify_required: bool = Field(default=False)
    notification_status: str | None = Field(default=None)
    notified_date: dt.date | None = Field(default=None)
    notified_method: str | None = Field(default=None)


class ContactInteraction(EstateScopedBase, table=True):
    """A logged interaction (call, letter, email) with a contact."""

    __tablename__ = "contact_interaction"

    contact_id: uuid.UUID = Field(foreign_key="contact.id", index=True, nullable=False)
    date: dt.date = Field()
    channel: str | None = Field(default=None)
    direction: str | None = Field(default=None, description="inbound or outbound")
    summary: str | None = Field(default=None)
    follow_up_date: dt.date | None = Field(default=None)
    by_user: str = Field(default="", description="Email of the executor who logged it")
    executor_private: bool = Field(
        default=False,
        description=(
            "Rows flagged true are never returned to the viewer role; "
            "enforced server-side"
        ),
    )
