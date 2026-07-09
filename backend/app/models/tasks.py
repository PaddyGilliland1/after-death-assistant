"""Tasks with dependencies, checklists and comments."""

import datetime as dt
import uuid

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase


class Task(EstateScopedBase, table=True):
    """A unit of executor work (build contract section 6)."""

    __tablename__ = "task"

    title: str = Field(index=True)
    description: str | None = Field(default=None)
    assignees: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Email addresses of assigned executors",
    )
    status: str | None = Field(default=None, index=True)
    priority: str | None = Field(default=None)
    start_date: dt.date | None = Field(default=None)
    due_date: dt.date | None = Field(default=None)
    blocked_by: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="UUIDs (as strings) of tasks that block this one",
    )
    blocks: list[str] = Field(
        default_factory=list,
        sa_type=JSON,
        description="UUIDs (as strings) of tasks this one blocks",
    )
    checklist: list[dict] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Checklist items, e.g. {text, done}",
    )
    process_step_id: uuid.UUID | None = Field(
        default=None, foreign_key="process_step.id", index=True
    )
    source: str | None = Field(
        default=None, description="Where the task came from, e.g. seed, agent, manual"
    )
    reminder: dt.date | None = Field(default=None)
    executor_private: bool = Field(
        default=False,
        description=(
            "Rows flagged true are never returned to the viewer role; "
            "enforced server-side"
        ),
    )


class TaskComment(EstateScopedBase, table=True):
    """A comment left on a task by an executor."""

    __tablename__ = "task_comment"

    task_id: uuid.UUID = Field(foreign_key="task.id", index=True, nullable=False)
    body: str = Field(default="")
