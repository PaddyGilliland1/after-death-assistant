"""Estate: the root record every business row belongs to."""

import datetime as dt
from decimal import Decimal

from sqlmodel import Field

from .base import MoneyType, PctType, SoftDeleteMixin, TableBase


class Estate(TableBase, SoftDeleteMixin, table=True):
    """A single estate under administration (build contract section 6)."""

    __tablename__ = "estate"

    name: str = Field(default="", description="Display name for the estate")
    date_of_death: dt.date | None = Field(default=None)
    grant_date: dt.date | None = Field(default=None)
    constants_version: str | None = Field(
        default=None, description="Version of the tax constants set in use"
    )
    nrb: Decimal | None = Field(
        default=None, sa_type=MoneyType, description="Nil rate band"
    )
    rnrb: Decimal | None = Field(
        default=None, sa_type=MoneyType, description="Residence nil rate band"
    )
    taper_threshold: Decimal | None = Field(default=None, sa_type=MoneyType)
    tnrb_pct: Decimal = Field(
        default=Decimal("0"),
        sa_type=PctType,
        description="Transferable NRB claimed, as a fraction (1.0 = 100 per cent)",
    )
    trnrb_pct: Decimal = Field(
        default=Decimal("0"),
        sa_type=PctType,
        description="Transferable RNRB claimed, as a fraction (1.0 = 100 per cent)",
    )
    residence_to_descendants_value: Decimal | None = Field(
        default=None,
        sa_type=MoneyType,
        description="Value of the residence passing to direct descendants",
    )
    charity_share_pct: Decimal = Field(
        default=Decimal("0"),
        sa_type=PctType,
        description="Share of the baseline amount left to charity, as a fraction",
    )
    claims_rnrb: bool | None = Field(
        default=None,
        description=(
            "Whether the estate claims the RNRB. None means derive at the app "
            "layer as residence_to_descendants_value > 0"
        ),
    )
    # Excepted-estate disqualifiers. All nullable: None means unknown, and the
    # app layer must treat unknown conservatively (not excepted until shown
    # otherwise).
    gifts_with_reservation: bool | None = Field(
        default=None,
        description="Any gifts with reservation of benefit; None means unknown",
    )
    foreign_assets_value: Decimal | None = Field(
        default=None,
        sa_type=MoneyType,
        description="Value of foreign assets; None means unknown",
    )
    trust_property_value: Decimal | None = Field(
        default=None,
        sa_type=MoneyType,
        description="Value of settled or trust property; None means unknown",
    )
    specified_transfers_value: Decimal | None = Field(
        default=None,
        sa_type=MoneyType,
        description=(
            "Value of specified transfers in the seven years before death; "
            "None means unknown"
        ),
    )
