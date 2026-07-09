"""Pure, deterministic inheritance tax engine (contract section 7).

Exposes assess(estate, constants) -> Assessment. No I/O, no clock reads,
no environment access. All money is Decimal. No LLM computes a figure;
agents may explain the output of this module, never produce it.

The residence nil rate band claim (claims_rnrb) may be set explicitly;
when left as None it is derived from the presence of a qualifying
residence value passing to descendants. The downsizing addition extends
the value the RNRB can be set against, capped by the tapered maximum.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # interface only; no runtime import needed
    from app.domain.jurisdiction import Jurisdiction

_PENCE = Decimal("0.01")


def _money(amount: Decimal) -> Decimal:
    """Quantise to pence without scientific notation artefacts."""
    return amount.quantize(_PENCE, rounding=ROUND_HALF_UP)


class AssetCategory(StrEnum):
    """Asset categories the schedule derivation is driven from."""

    LAND_AND_BUILDINGS = "land_and_buildings"
    BANK_ACCOUNTS = "bank_accounts"
    NSANDI = "nsandi"
    HOUSEHOLD_GOODS = "household_goods"
    GIFTS = "gifts"
    LISTED_SHARES = "listed_shares"
    UNLISTED_SHARES = "unlisted_shares"
    OTHER = "other"


class AssetItem(BaseModel):
    """A categorised asset, used only to derive required schedules."""

    model_config = ConfigDict(frozen=True)

    category: AssetCategory
    description: str = ""
    value: Decimal = Field(default=Decimal("0"), ge=0)


class Estate(BaseModel):
    """The engine's input snapshot of an estate. Synthetic and generic;
    holds no personal data.

    The excepted-estate facts (gifts, trusts, foreign assets, gifts with
    reservation of benefit) default to None, meaning unknown. Unknown is
    treated conservatively: an estate with unknown facts is never
    excepted, so a full IHT400 account is required until the facts are
    established.
    """

    model_config = ConfigDict(frozen=True)

    net_value: Decimal = Field(ge=0)
    gross_value: Decimal | None = Field(default=None, ge=0)
    tnrb_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    trnrb_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    residence_to_descendants_value: Decimal = Field(default=Decimal("0"), ge=0)
    downsizing_addition: Decimal = Field(default=Decimal("0"), ge=0)
    exempt_transfers: Decimal = Field(default=Decimal("0"), ge=0)
    charity_share: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    claims_rnrb: bool | None = None
    assets: tuple[AssetItem, ...] = ()
    gifts_in_seven_years: Decimal | None = Field(default=None, ge=0)
    trust_assets_value: Decimal | None = Field(default=None, ge=0)
    trust_count: int | None = Field(default=None, ge=0)
    foreign_assets_value: Decimal | None = Field(default=None, ge=0)
    gifts_with_reservation: bool | None = None

    @property
    def rnrb_claimed(self) -> bool:
        """Whether the residence nil rate band is being claimed.

        Explicit claims_rnrb wins; when it is None the claim is derived
        from the presence of a qualifying residence value passing to
        descendants.
        """
        if self.claims_rnrb is not None:
            return self.claims_rnrb
        return self.residence_to_descendants_value > 0


class Assessment(BaseModel):
    """The engine's deterministic output."""

    model_config = ConfigDict(frozen=True)

    jurisdiction_code: str
    nrb: Decimal
    rnrb_max: Decimal
    rnrb: Decimal
    allowance: Decimal
    taxable: Decimal
    rate: Decimal
    tax: Decimal
    is_excepted: bool
    must_file_iht400: bool
    required_schedules: tuple[str, ...]


def assess(estate: Estate, constants: Jurisdiction) -> Assessment:
    """Assess inheritance tax for an estate under the given jurisdiction.

    Implements contract section 7 exactly:

        nrb        = constants.NRB * (1 + estate.tnrb_pct)
        rnrb_max   = constants.RNRB * (1 + estate.trnrb_pct)
        if net_value > constants.TAPER_THRESHOLD:
            rnrb_max = max(rnrb_max - (net_value - TAPER_THRESHOLD) / 2, 0)
        rnrb       = min(rnrb_max, residence_to_descendants + downsizing)
        allowance  = nrb + rnrb
        taxable    = max(net_value - exempt_transfers - allowance, 0)
        rate       = 0.36 if charity_share >= 0.10 else 0.40
        tax        = taxable * rate
        must_file_iht400 = claims_rnrb or not is_excepted(estate, constants)
        required_schedules = derive_from_asset_categories(estate)
    """
    nrb = constants.nrb.value * (1 + estate.tnrb_pct)
    rnrb_max = constants.rnrb.value * (1 + estate.trnrb_pct)

    taper_threshold = constants.taper_threshold.value
    if estate.net_value > taper_threshold:
        reduction = (estate.net_value - taper_threshold) / 2
        rnrb_max = max(rnrb_max - reduction, Decimal("0"))

    rnrb = min(
        rnrb_max,
        estate.residence_to_descendants_value + estate.downsizing_addition,
    )
    allowance = nrb + rnrb
    taxable = max(estate.net_value - estate.exempt_transfers - allowance, Decimal("0"))

    if estate.charity_share >= constants.charity_rate_threshold.value:
        rate = constants.reduced_rate.value
    else:
        rate = constants.standard_rate.value

    tax = _money(taxable * rate)

    excepted = constants.is_excepted(estate)
    must_file_iht400 = estate.rnrb_claimed or not excepted
    required_schedules = constants.required_schedules(estate)

    return Assessment(
        jurisdiction_code=constants.code,
        nrb=_money(nrb),
        rnrb_max=_money(rnrb_max),
        rnrb=_money(rnrb),
        allowance=_money(allowance),
        taxable=_money(taxable),
        rate=rate,
        tax=tax,
        is_excepted=excepted,
        must_file_iht400=must_file_iht400,
        required_schedules=required_schedules,
    )
