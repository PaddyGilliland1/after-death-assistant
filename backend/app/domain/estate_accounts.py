"""Pure estate accounts: trial balance and beneficiary shares.

Four-account structure (capital, income, administration, distribution):

    net estate     = sole assets + tenants-in-common shares
                     - deductible liabilities - funeral costs
    capital        = net estate + realisation gains
    income         = income received since death - income expenses
                     - income tax
    administration = admin costs + IHT
    residue        = capital + income - administration
                     - legacies (pecuniary and specific)
    distribution   = legacies + residue; per residuary beneficiary,
                     residue x residuary share - interim distributions
                     already made

Income received during the administration is distributed with the
residue. The module always reconciles: is_balanced() must hold for any
accounts produced by compute_accounts(). All money is Decimal,
quantised to pence; any penny left by rounding residuary shares is
allocated to the final residuary beneficiary so the accounts balance
exactly.

Pure module: no I/O, no clock reads, no environment access.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_PENCE = Decimal("0.01")
_SHARE_TOLERANCE = Decimal("0.0001")


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(_PENCE, rounding=ROUND_HALF_UP)


class Ownership(StrEnum):
    SOLE = "sole"
    JOINT_TENANTS = "joint_tenants"
    TENANTS_IN_COMMON = "tenants_in_common"


class LegacyType(StrEnum):
    PECUNIARY = "pecuniary"
    SPECIFIC = "specific"
    RESIDUARY = "residuary"


class AccountAsset(BaseModel):
    """An asset with the ownership basis that determines its estate share."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    value: Decimal = Field(ge=0)
    ownership: Ownership = Ownership.SOLE
    tic_share_pct: Decimal = Field(default=Decimal("1"), ge=0, le=1)

    @property
    def estate_share(self) -> Decimal:
        """The part of this asset that falls into the estate accounts.

        Sole assets count in full, tenants-in-common assets count at the
        deceased's share, and joint tenancy assets pass outside the
        estate accounts by survivorship.
        """
        if self.ownership is Ownership.SOLE:
            return self.value
        if self.ownership is Ownership.TENANTS_IN_COMMON:
            return self.value * self.tic_share_pct
        return Decimal("0")


class AccountLiability(BaseModel):
    model_config = ConfigDict(frozen=True)

    identifier: str
    amount: Decimal = Field(ge=0)
    deductible: bool = True


class Legacy(BaseModel):
    """A gift under the will: pecuniary or specific (fixed amount) or
    residuary (a share of the residue)."""

    model_config = ConfigDict(frozen=True)

    beneficiary_id: str
    legacy_type: LegacyType
    amount: Decimal | None = Field(default=None, ge=0)
    share: Decimal | None = Field(default=None, ge=0, le=1)
    chargeable: bool = True

    @model_validator(mode="after")
    def _check_shape(self) -> Legacy:
        if self.legacy_type is LegacyType.RESIDUARY:
            if self.share is None:
                raise ValueError("a residuary legacy requires a share")
        else:
            if self.amount is None:
                raise ValueError(
                    "a pecuniary or specific legacy requires an amount"
                )
        return self


class EstateAccountsInput(BaseModel):
    """Everything needed to draw up the estate accounts."""

    model_config = ConfigDict(frozen=True)

    assets: tuple[AccountAsset, ...] = ()
    liabilities: tuple[AccountLiability, ...] = ()
    funeral_costs: Decimal = Field(default=Decimal("0"), ge=0)
    realisation_gains: Decimal = Decimal("0")
    admin_costs: Decimal = Field(default=Decimal("0"), ge=0)
    iht_due: Decimal = Field(default=Decimal("0"), ge=0)
    income_received: Decimal = Field(default=Decimal("0"), ge=0)
    income_expenses: Decimal = Field(default=Decimal("0"), ge=0)
    income_tax: Decimal = Field(default=Decimal("0"), ge=0)
    legacies: tuple[Legacy, ...] = ()
    interim_distributions: Mapping[str, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_residuary_shares(self) -> EstateAccountsInput:
        shares = [
            legacy.share
            for legacy in self.legacies
            if legacy.legacy_type is LegacyType.RESIDUARY
            and legacy.share is not None
        ]
        if shares:
            total = sum(shares, Decimal("0"))
            if abs(total - 1) > _SHARE_TOLERANCE:
                raise ValueError(
                    f"residuary shares must sum to 1, got {total}"
                )
        return self


class BeneficiaryDistribution(BaseModel):
    """One residuary beneficiary's position."""

    model_config = ConfigDict(frozen=True)

    beneficiary_id: str
    residuary_share: Decimal
    entitlement: Decimal
    interim_received: Decimal
    remaining_due: Decimal


class EstateAccounts(BaseModel):
    """The drawn-up accounts, in the four-account structure.
    is_balanced() must always hold."""

    model_config = ConfigDict(frozen=True)

    inputs: EstateAccountsInput
    net_estate: Decimal
    capital_account: Decimal
    income_account: Decimal
    administration_account: Decimal
    legacies_total: Decimal
    residue: Decimal
    distribution_account: Decimal
    distributions: tuple[BeneficiaryDistribution, ...]

    def is_balanced(self, tolerance: Decimal = _PENCE) -> bool:
        """Reconciliation check across the whole account.

        Verifies, from the raw inputs, that:
        1. the net estate equals estate asset shares less deductible
           liabilities and funeral costs;
        2. the capital account equals the net estate plus realisation
           gains;
        3. the income account equals income received since death less
           income expenses and income tax;
        4. the administration account equals admin costs plus IHT;
        5. the residue equals capital plus income less administration
           and fixed legacies (income is distributed with residue);
        6. the distribution account equals fixed legacies plus residue,
           which equals capital plus income less administration;
        7. residuary entitlements sum exactly to the residue;
        8. each remaining amount equals entitlement less interim
           distributions already made.
        """
        expected_net = _money(
            sum(
                (asset.estate_share for asset in self.inputs.assets),
                Decimal("0"),
            )
            - sum(
                (
                    liability.amount
                    for liability in self.inputs.liabilities
                    if liability.deductible
                ),
                Decimal("0"),
            )
            - self.inputs.funeral_costs
        )
        if abs(self.net_estate - expected_net) > tolerance:
            return False

        expected_capital = _money(self.net_estate + self.inputs.realisation_gains)
        if abs(self.capital_account - expected_capital) > tolerance:
            return False

        expected_income = _money(
            self.inputs.income_received
            - self.inputs.income_expenses
            - self.inputs.income_tax
        )
        if abs(self.income_account - expected_income) > tolerance:
            return False

        expected_administration = _money(
            self.inputs.admin_costs + self.inputs.iht_due
        )
        if abs(self.administration_account - expected_administration) > tolerance:
            return False

        expected_legacies = _money(
            sum(
                (
                    legacy.amount
                    for legacy in self.inputs.legacies
                    if legacy.legacy_type is not LegacyType.RESIDUARY
                ),
                Decimal("0"),
            )
        )
        if abs(self.legacies_total - expected_legacies) > tolerance:
            return False

        expected_residue = _money(
            self.capital_account
            + self.income_account
            - self.administration_account
            - self.legacies_total
        )
        if abs(self.residue - expected_residue) > tolerance:
            return False

        expected_distribution = _money(self.legacies_total + self.residue)
        if abs(self.distribution_account - expected_distribution) > tolerance:
            return False
        if (
            abs(
                self.distribution_account
                - (
                    self.capital_account
                    + self.income_account
                    - self.administration_account
                )
            )
            > tolerance
        ):
            return False

        if self.distributions:
            entitlement_total = sum(
                (d.entitlement for d in self.distributions), Decimal("0")
            )
            if abs(entitlement_total - self.residue) > tolerance:
                return False
            for d in self.distributions:
                if abs(d.remaining_due - (d.entitlement - d.interim_received)) > tolerance:
                    return False

        return True


def compute_accounts(inputs: EstateAccountsInput) -> EstateAccounts:
    """Draw up the estate accounts from the inputs.

    Deterministic and side-effect free. The final residuary beneficiary
    absorbs any penny difference left by rounding so that entitlements
    sum exactly to the residue.
    """
    net_estate = _money(
        sum((asset.estate_share for asset in inputs.assets), Decimal("0"))
        - sum(
            (
                liability.amount
                for liability in inputs.liabilities
                if liability.deductible
            ),
            Decimal("0"),
        )
        - inputs.funeral_costs
    )

    capital_account = _money(net_estate + inputs.realisation_gains)
    income_account = _money(
        inputs.income_received - inputs.income_expenses - inputs.income_tax
    )
    administration_account = _money(inputs.admin_costs + inputs.iht_due)

    legacies_total = _money(
        sum(
            (
                legacy.amount
                for legacy in inputs.legacies
                if legacy.legacy_type is not LegacyType.RESIDUARY
                and legacy.amount is not None
            ),
            Decimal("0"),
        )
    )

    residue = _money(
        capital_account + income_account - administration_account - legacies_total
    )

    residuary = [
        (legacy, legacy.share)
        for legacy in inputs.legacies
        if legacy.legacy_type is LegacyType.RESIDUARY
        and legacy.share is not None
    ]

    distributions: list[BeneficiaryDistribution] = []
    allocated = Decimal("0")
    for index, (legacy, share) in enumerate(residuary):
        if index < len(residuary) - 1:
            entitlement = _money(residue * share)
            allocated += entitlement
        else:
            entitlement = _money(residue - allocated)
        interim = _money(
            inputs.interim_distributions.get(legacy.beneficiary_id, Decimal("0"))
        )
        distributions.append(
            BeneficiaryDistribution(
                beneficiary_id=legacy.beneficiary_id,
                residuary_share=share,
                entitlement=entitlement,
                interim_received=interim,
                remaining_due=_money(entitlement - interim),
            )
        )

    return EstateAccounts(
        inputs=inputs,
        net_estate=net_estate,
        capital_account=capital_account,
        income_account=income_account,
        administration_account=administration_account,
        legacies_total=legacies_total,
        residue=residue,
        distribution_account=_money(legacies_total + residue),
        distributions=tuple(distributions),
    )
