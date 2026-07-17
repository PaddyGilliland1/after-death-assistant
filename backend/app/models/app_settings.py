"""Application-level parameters, editable from the admin Params page.

Key-value rows; values are JSON so booleans, numbers and small objects
all fit. Not estate-scoped: these switch application behaviour.
"""

import datetime as dt

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.models.base import utcnow


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"

    key: str = Field(primary_key=True, max_length=100)
    value: dict | list | bool | int | str | None = Field(
        default=None, sa_column=Column(JSON)
    )
    updated_at: dt.datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True))
    )
    updated_by: str = Field(default="system")
