"""Cost tracking: funeral and administration expenses with IHT treatment."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType
from .enums import IhtTreatment, str_enum_type


class Cost(EstateScopedBase, table=True):
    """An expense incurred by the estate or an executor (contract section 6)."""

    __tablename__ = "cost"

    description: str = Field(default="")
    category: str = Field(index=True, description="e.g. funeral, probate, valuation")
    amount: Decimal = Field(sa_type=MoneyType)
    vat: Decimal | None = Field(default=None, sa_type=MoneyType)
    date: dt.date = Field()
    paid_by: str | None = Field(
        default=None, description="Who paid: the estate or a named executor"
    )
    payment_method: str | None = Field(default=None)
    reimbursable: bool = Field(default=False)
    reimbursed: bool = Field(default=False)
    reimbursed_date: dt.date | None = Field(default=None)
    iht_treatment: IhtTreatment = Field(
        default=IhtTreatment.admin_not_deductible,
        sa_type=str_enum_type(IhtTreatment),
    )
    receipt_document_id: uuid.UUID | None = Field(
        default=None, foreign_key="document.id", index=True
    )
    executor_private: bool = Field(
        default=False,
        description=(
            "Rows flagged true are never returned to the viewer role; "
            "enforced server-side"
        ),
    )
