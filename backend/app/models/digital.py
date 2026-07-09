"""Digital assets and online accounts of the deceased."""

from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType


class DigitalItem(EstateScopedBase, table=True):
    """An online service, subscription or digital asset (contract section 6)."""

    __tablename__ = "digital_item"

    service: str = Field(index=True, description="e.g. Google, Netflix, Amazon")
    type: str | None = Field(
        default=None, description="e.g. email, subscription, social, storage"
    )
    login_known: bool = Field(default=False)
    action: str | None = Field(
        default=None, description="e.g. close, memorialise, transfer, cancel"
    )
    recurring_amount: Decimal | None = Field(default=None, sa_type=MoneyType)
    status: str | None = Field(default=None)
