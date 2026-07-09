"""Beneficiary legacies and distributions made against them."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import Numeric
from sqlmodel import Field

from .base import EstateScopedBase, MoneyType
from .enums import LegacyType, str_enum_type

# amount_or_share holds either a money amount (pecuniary) or a fractional
# share (residuary, e.g. 0.5), so it carries four decimal places.
AmountOrShareType = Numeric(14, 4)


class BeneficiaryLegacy(EstateScopedBase, table=True):
    """A legacy left to a beneficiary under the will (contract section 6)."""

    __tablename__ = "beneficiary_legacy"

    beneficiary_contact_id: uuid.UUID = Field(
        foreign_key="contact.id", index=True, nullable=False
    )
    legacy_type: LegacyType = Field(sa_type=str_enum_type(LegacyType), index=True)
    amount_or_share: Decimal | None = Field(
        default=None,
        sa_type=AmountOrShareType,
        description="Money amount for pecuniary, fraction of residue for residuary",
    )
    exempt_or_chargeable: str | None = Field(
        default=None, description="exempt (e.g. spouse, charity) or chargeable"
    )
    tax_bearing: bool | None = Field(
        default=None, description="Whether the legacy bears its own tax"
    )
    status: str | None = Field(default=None)


class Distribution(EstateScopedBase, table=True):
    """A payment made to a beneficiary against a legacy."""

    __tablename__ = "distribution"

    beneficiary_legacy_id: uuid.UUID = Field(
        foreign_key="beneficiary_legacy.id", index=True, nullable=False
    )
    amount: Decimal = Field(sa_type=MoneyType)
    date: dt.date = Field()
    method: str | None = Field(default=None)
