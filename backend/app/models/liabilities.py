"""Liability register: debts owed by the estate at the date of death."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType


class Liability(EstateScopedBase, table=True):
    """A liability of the estate (build contract section 6)."""

    __tablename__ = "liability"

    type: str = Field(index=True, description="e.g. mortgage, credit_card, utility")
    creditor_contact_id: uuid.UUID | None = Field(
        default=None, foreign_key="contact.id", index=True
    )
    amount: Decimal = Field(sa_type=MoneyType)
    as_at_date: dt.date | None = Field(default=None)
    status: str | None = Field(default=None)
    iht_deductible: bool = Field(default=True)
