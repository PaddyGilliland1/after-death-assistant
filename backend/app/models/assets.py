"""Asset register and valuation history."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType, PctType
from .enums import OwnershipType, ValueBasis, str_enum_type


class Asset(EstateScopedBase, table=True):
    """An asset of the estate (build contract section 6)."""

    __tablename__ = "asset"

    category: str = Field(index=True, description="e.g. property, cash, isa, shares")
    sub_type: str | None = Field(default=None)
    description: str = Field(default="")
    holder_contact_id: uuid.UUID | None = Field(
        default=None, foreign_key="contact.id", index=True
    )
    account_reference: str | None = Field(default=None)
    ownership: OwnershipType = Field(
        default=OwnershipType.sole, sa_type=str_enum_type(OwnershipType)
    )
    tic_share_pct: Decimal | None = Field(
        default=None,
        sa_type=PctType,
        description="Deceased's share as a fraction where tenants in common",
    )
    dod_value: Decimal | None = Field(
        default=None, sa_type=MoneyType, description="Value at the date of death"
    )
    value_basis: ValueBasis = Field(
        default=ValueBasis.estimate, sa_type=str_enum_type(ValueBasis)
    )
    valuation_source: str | None = Field(default=None)
    valuation_date: dt.date | None = Field(default=None)
    current_or_realised_value: Decimal | None = Field(
        default=None, sa_type=MoneyType
    )
    realised_date: dt.date | None = Field(default=None)
    income_since_death: Decimal | None = Field(default=None, sa_type=MoneyType)
    iht_schedule: str | None = Field(
        default=None, description="IHT400 schedule this asset reports on, e.g. IHT405"
    )
    rnrb_qualifying: bool = Field(default=False)
    passes_outside_estate: bool = Field(
        default=False, description="e.g. joint tenancy survivorship or nominated policy"
    )
    status: str | None = Field(default=None)


class ValuationEvent(EstateScopedBase, table=True):
    """A dated valuation of an asset, preserving the valuation history."""

    __tablename__ = "valuation_event"

    asset_id: uuid.UUID = Field(foreign_key="asset.id", index=True, nullable=False)
    value: Decimal = Field(sa_type=MoneyType)
    basis: ValueBasis = Field(
        default=ValueBasis.estimate, sa_type=str_enum_type(ValueBasis)
    )
    source: str | None = Field(default=None)
    date: dt.date = Field()
