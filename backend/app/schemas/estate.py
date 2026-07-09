"""Schemas for the estate settings, dashboard summary and estate accounts.

All money is Decimal end to end; Pydantic serialises Decimal as a string
in JSON so no precision is lost on the wire. No figure here is computed:
values come from the estate row, SQL aggregates, or the pure domain module
app.domain.estate_accounts.
"""

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class EstateSettingsRead(BaseModel):
    """The estate settings row, including the RNRB claim and the
    excepted-estate disqualifier facts (None means unknown, which the
    engine treats conservatively as not excepted)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    date_of_death: dt.date | None
    grant_date: dt.date | None
    constants_version: str | None
    nrb: Decimal | None
    rnrb: Decimal | None
    taper_threshold: Decimal | None
    tnrb_pct: Decimal
    trnrb_pct: Decimal
    residence_to_descendants_value: Decimal | None
    charity_share_pct: Decimal
    claims_rnrb: bool | None
    gifts_with_reservation: bool | None
    foreign_assets_value: Decimal | None
    trust_property_value: Decimal | None
    specified_transfers_value: Decimal | None
    created_at: dt.datetime
    updated_at: dt.datetime


class EstateSettingsUpdate(BaseModel):
    """Writable estate settings. Only fields present in the request body
    are applied (exclude_unset semantics). The tax constants themselves
    (nrb, rnrb, taper_threshold, constants_version) are not writable here:
    they belong to the jurisdiction module with provenance."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    date_of_death: dt.date | None = None
    grant_date: dt.date | None = None
    tnrb_pct: Decimal | None = Field(default=None, ge=0, le=1)
    trnrb_pct: Decimal | None = Field(default=None, ge=0, le=1)
    residence_to_descendants_value: Decimal | None = Field(default=None, ge=0)
    charity_share_pct: Decimal | None = Field(default=None, ge=0, le=1)
    claims_rnrb: bool | None = None
    gifts_with_reservation: bool | None = None
    foreign_assets_value: Decimal | None = Field(default=None, ge=0)
    trust_property_value: Decimal | None = Field(default=None, ge=0)
    specified_transfers_value: Decimal | None = Field(default=None, ge=0)


class EstateSummary(BaseModel):
    """Dashboard aggregates (SQL aggregates; IHT due from the latest
    engine snapshot). All zeros on an empty database."""

    gross_assets_at_dod: Decimal = Field(
        description="Sum of asset values at the date of death (whole register)"
    )
    net_estate: Decimal = Field(
        description=(
            "Estate share of assets (sole in full, tenants-in-common at the "
            "deceased's share) less deductible liabilities and funeral costs"
        )
    )
    iht_due: Decimal = Field(
        description="Tax figure from the latest IHT assessment snapshot; 0 when none"
    )
    open_task_count: int
    unnotified_contact_count: int = Field(
        description="Contacts requiring notification with no notified date"
    )
    costs_total: Decimal = Field(
        description="Sum of cost amounts (VAT is recorded separately per cost)"
    )


class AccountsDistributionRead(BaseModel):
    """One residuary beneficiary's position, from the domain module."""

    beneficiary_id: str
    residuary_share: Decimal
    entitlement: Decimal
    interim_received: Decimal
    remaining_due: Decimal


class EstateAccountsRead(BaseModel):
    """The drawn-up estate accounts (four-account structure) plus the
    reconciliation flag. Every figure comes from
    app.domain.estate_accounts.compute_accounts."""

    net_estate: Decimal
    capital_account: Decimal
    income_account: Decimal
    administration_account: Decimal
    legacies_total: Decimal
    residue: Decimal
    distribution_account: Decimal
    distributions: list[AccountsDistributionRead]
    is_balanced: bool
