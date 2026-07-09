"""Audit trail and human approvals of agent drafts."""

import datetime as dt

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase, TZDateTime, utcnow


class AuditEvent(EstateScopedBase, table=True):
    """An immutable record of a write action (build contract section 6)."""

    __tablename__ = "audit_event"

    actor: str = Field(index=True, description="Email address of the acting user")
    action: str = Field(index=True, description="e.g. create, update, archive, approve")
    entity: str = Field(
        index=True, description="Entity reference, e.g. asset:<uuid>"
    )
    before: dict | None = Field(
        default=None, sa_type=JSON, description="Entity state before the change"
    )
    after: dict | None = Field(
        default=None, sa_type=JSON, description="Entity state after the change"
    )
    timestamp: dt.datetime = Field(
        default_factory=utcnow, sa_type=TZDateTime, nullable=False
    )


class Approval(EstateScopedBase, table=True):
    """Human approval of an agent-produced draft. A draft stays a draft until
    a row here records who approved it and when."""

    __tablename__ = "approval"

    entity_ref: str = Field(
        index=True, description="Reference to the draft entity, e.g. document:<uuid>"
    )
    draft_kind: str = Field(
        index=True, description="e.g. iht400_draft, notification_letter, task_suggestion"
    )
    approved_by: str | None = Field(
        default=None, description="Email address of the approver; empty while pending"
    )
    approved_at: dt.datetime | None = Field(
        default=None, sa_type=TZDateTime, nullable=True
    )
