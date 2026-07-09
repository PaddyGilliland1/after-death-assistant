"""Administration-period tax: income tax and CGT per tax year."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase, MoneyType


class AdminTax(EstateScopedBase, table=True):
    """Administration-period tax position for one tax year (contract section 6)."""

    __tablename__ = "admin_tax"

    tax_year: str = Field(index=True, description="e.g. 2026-27")
    income_total: Decimal | None = Field(default=None, sa_type=MoneyType)
    estate_complex: bool | None = Field(
        default=None,
        description="Derived: whether the estate counts as complex for HMRC reporting",
    )
    cgt_disposals: list[dict] = Field(
        default_factory=list,
        sa_type=JSON,
        description="Disposal entries, e.g. {asset_id, date, proceeds, gain}",
    )
    cgt_60day_deadlines: list[dict] = Field(
        default_factory=list,
        sa_type=JSON,
        description="60-day CGT reporting deadlines, e.g. {disposal_ref, due_date}",
    )
    isa_exemption_end: dt.date | None = Field(default=None)
