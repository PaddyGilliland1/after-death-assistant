"""Debtors owed to the estate, creditors claiming against it, and the
statutory Section 27 creditor notice with claims received."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType


class Debtor(EstateScopedBase, table=True):
    """Money owed TO the estate (build contract section 6)."""

    __tablename__ = "debtor"

    source_contact_id: uuid.UUID | None = Field(
        default=None, foreign_key="contact.id", index=True
    )
    type: str = Field(index=True, description="e.g. refund, pension_arrears, tax_repayment")
    amount_expected: Decimal | None = Field(default=None, sa_type=MoneyType)
    amount_received: Decimal | None = Field(default=None, sa_type=MoneyType)
    status: str | None = Field(default=None)
    expected_date: dt.date | None = Field(default=None)
    received_into_asset_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="asset.id",
        index=True,
        description="Asset (usually the executor account) the money was received into",
    )


class Creditor(EstateScopedBase, table=True):
    """Money owed BY the estate (build contract section 6)."""

    __tablename__ = "creditor"

    creditor_contact_id: uuid.UUID | None = Field(
        default=None, foreign_key="contact.id", index=True
    )
    type: str = Field(index=True)
    amount_claimed: Decimal | None = Field(default=None, sa_type=MoneyType)
    amount_agreed: Decimal | None = Field(default=None, sa_type=MoneyType)
    amount_paid: Decimal | None = Field(default=None, sa_type=MoneyType)
    status: str | None = Field(default=None)
    priority_class: str | None = Field(
        default=None, description="Statutory order of payment class"
    )
    paid_from_asset_id: uuid.UUID | None = Field(
        default=None, foreign_key="asset.id", index=True
    )


class CreditorNotice(EstateScopedBase, table=True):
    """Trustee Act 1925 Section 27 notice placed in The Gazette and a local paper."""

    __tablename__ = "creditor_notice"

    gazette_ref: str | None = Field(default=None)
    gazette_date: dt.date | None = Field(default=None)
    local_paper: str | None = Field(default=None)
    local_date: dt.date | None = Field(default=None)
    claim_deadline: dt.date | None = Field(
        default=None, description="Derived: two months from the later notice date"
    )
    safe_to_distribute: bool | None = Field(
        default=None, description="Derived: claim deadline passed and claims resolved"
    )


class NoticeClaim(EstateScopedBase, table=True):
    """A claim received in response to a creditor notice."""

    __tablename__ = "notice_claim"

    creditor_notice_id: uuid.UUID = Field(
        foreign_key="creditor_notice.id", index=True, nullable=False
    )
    claimant: str = Field(default="")
    amount: Decimal | None = Field(default=None, sa_type=MoneyType)
    status: str | None = Field(default=None)
