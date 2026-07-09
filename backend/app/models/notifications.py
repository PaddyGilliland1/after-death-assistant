"""In-app notifications to executors (cost recorded, approval needed, etc.)."""

import datetime as dt

from sqlmodel import Field

from .base import EstateScopedBase, TZDateTime


class Notification(EstateScopedBase, table=True):
    """A notification for one user (build contract section 6)."""

    __tablename__ = "notification"

    user_id: str = Field(index=True, description="Email address of the recipient")
    event_type: str = Field(
        index=True, description="e.g. cost_recorded, asset_added, approval_needed"
    )
    entity_ref: str | None = Field(
        default=None, description="Reference to the entity, e.g. cost:<uuid>"
    )
    message: str = Field(default="")
    read_at: dt.datetime | None = Field(
        default=None, sa_type=TZDateTime, nullable=True
    )
