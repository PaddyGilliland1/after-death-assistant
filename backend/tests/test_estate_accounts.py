"""Tests for the pure estate accounts module.

All names and figures are synthetic and generic. No personal data.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.estate_accounts import (
    AccountAsset,
    AccountLiability,
    EstateAccountsInput,
    Legacy,
    LegacyType,
    Ownership,
    compute_accounts,
)

D = Decimal


def seed_style_input(**overrides) -> EstateAccountsInput:
    """A generic estate: one chargeable pecuniary legacy of 200000 to
    beneficiary_a, residue split 50/50 between beneficiary_b and beneficiary_c.
    """
    defaults = {
        "assets": (
            AccountAsset(identifier="property_1", value=D("340000")),
            AccountAsset(identifier="cash_1", value=D("600000")),
            AccountAsset(identifier="vehicle_1", value=D("20000")),
        ),
        "liabilities": (
            AccountLiability(identifier="utility_bill", amount=D("6000")),
        ),
        "funeral_costs": D("4000"),
        "realisation_gains": D("0"),
        "admin_costs": D("12000"),
        "iht_due": D("28000"),
        "legacies": (
            Legacy(
                beneficiary_id="beneficiary_a",
                legacy_type=LegacyType.PECUNIARY,
                amount=D("200000"),
                chargeable=True,
            ),
            Legacy(
                beneficiary_id="beneficiary_b",
                legacy_type=LegacyType.RESIDUARY,
                share=D("0.5"),
            ),
            Legacy(
                beneficiary_id="beneficiary_c",
                legacy_type=LegacyType.RESIDUARY,
                share=D("0.5"),
            ),
        ),
        "interim_distributions": {},
    }
    defaults.update(overrides)
    return EstateAccountsInput(**defaults)


def test_net_estate_sole_assets():
    accounts = compute_accounts(seed_style_input())
    # 340000 + 600000 + 20000 - 6000 - 4000 = 950000
    assert accounts.net_estate == D("950000")


def test_residue_after_costs_tax_and_legacies():
    accounts = compute_accounts(seed_style_input())
    # 950000 + 0 - 12000 - 28000 - 200000 = 710000
    assert accounts.residue == D("710000")


def test_fifty_fifty_residuary_split():
    accounts = compute_accounts(seed_style_input())
    by_id = {d.beneficiary_id: d for d in accounts.distributions}
    assert by_id["beneficiary_b"].entitlement == D("355000")
    assert by_id["beneficiary_c"].entitlement == D("355000")
    assert by_id["beneficiary_b"].remaining_due == D("355000")


def test_is_balanced_on_seed_style_estate():
    accounts = compute_accounts(seed_style_input())
    assert accounts.is_balanced() is True


def test_joint_tenant_assets_pass_outside_estate():
    accounts = compute_accounts(
        seed_style_input(
            assets=(
                AccountAsset(identifier="cash_1", value=D("600000")),
                AccountAsset(
                    identifier="joint_account",
                    value=D("50000"),
                    ownership=Ownership.JOINT_TENANTS,
                ),
            ),
            liabilities=(),
            funeral_costs=D("0"),
            admin_costs=D("0"),
            iht_due=D("0"),
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("1"),
                ),
            ),
        )
    )
    assert accounts.net_estate == D("600000")
    assert accounts.is_balanced() is True


def test_tenants_in_common_share_included():
    accounts = compute_accounts(
        seed_style_input(
            assets=(
                AccountAsset(identifier="cash_1", value=D("600000")),
                AccountAsset(
                    identifier="tic_property",
                    value=D("400000"),
                    ownership=Ownership.TENANTS_IN_COMMON,
                    tic_share_pct=D("0.5"),
                ),
            ),
            liabilities=(
                AccountLiability(identifier="loan_1", amount=D("10000")),
            ),
            funeral_costs=D("4000"),
            admin_costs=D("6000"),
            iht_due=D("28000"),
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_a",
                    legacy_type=LegacyType.PECUNIARY,
                    amount=D("200000"),
                    chargeable=True,
                ),
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_c",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
            ),
            realisation_gains=D("2000"),
        )
    )
    # net = 600000 + 200000 - 10000 - 4000 = 786000
    assert accounts.net_estate == D("786000")
    # residue = 786000 + 2000 - 6000 - 28000 - 200000 = 554000
    assert accounts.residue == D("554000")
    assert accounts.is_balanced() is True


def test_non_deductible_liability_excluded():
    accounts = compute_accounts(
        seed_style_input(
            liabilities=(
                AccountLiability(identifier="deductible_1", amount=D("6000")),
                AccountLiability(
                    identifier="not_deductible_1",
                    amount=D("5000"),
                    deductible=False,
                ),
            )
        )
    )
    assert accounts.net_estate == D("950000")
    assert accounts.is_balanced() is True


def test_interim_distributions_reduce_remaining_due():
    accounts = compute_accounts(
        seed_style_input(interim_distributions={"beneficiary_b": D("50000")})
    )
    by_id = {d.beneficiary_id: d for d in accounts.distributions}
    assert by_id["beneficiary_b"].entitlement == D("355000")
    assert by_id["beneficiary_b"].interim_received == D("50000")
    assert by_id["beneficiary_b"].remaining_due == D("305000")
    assert by_id["beneficiary_c"].remaining_due == D("355000")
    assert accounts.is_balanced() is True


def test_penny_rounding_still_balances():
    accounts = compute_accounts(
        seed_style_input(
            assets=(
                AccountAsset(identifier="cash_1", value=D("100000.01")),
            ),
            liabilities=(),
            funeral_costs=D("0"),
            admin_costs=D("0"),
            iht_due=D("0"),
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_c",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
            ),
        )
    )
    total = sum(d.entitlement for d in accounts.distributions)
    assert total == accounts.residue
    assert accounts.is_balanced() is True


def test_three_way_uneven_split_balances():
    accounts = compute_accounts(
        seed_style_input(
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_a",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.25"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_c",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.25"),
                ),
            )
        )
    )
    total = sum(d.entitlement for d in accounts.distributions)
    assert total == accounts.residue
    assert accounts.is_balanced() is True


def test_residuary_shares_must_sum_to_one():
    with pytest.raises(ValidationError):
        seed_style_input(
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.5"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_c",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("0.4"),
                ),
            )
        )


def test_residuary_legacy_requires_share():
    with pytest.raises(ValidationError):
        Legacy(beneficiary_id="beneficiary_b", legacy_type=LegacyType.RESIDUARY)


def test_pecuniary_legacy_requires_amount():
    with pytest.raises(ValidationError):
        Legacy(beneficiary_id="beneficiary_a", legacy_type=LegacyType.PECUNIARY)


def test_income_account_distributed_with_residue():
    accounts = compute_accounts(
        seed_style_input(
            income_received=D("5000"),
            income_expenses=D("500"),
            income_tax=D("1000"),
        )
    )
    # income account = 5000 - 500 - 1000 = 3500
    assert accounts.income_account == D("3500")
    # capital account = 950000 + 0 gains
    assert accounts.capital_account == D("950000")
    # administration account = 12000 + 28000
    assert accounts.administration_account == D("40000")
    # residue = 950000 + 3500 - 40000 - 200000 = 713500
    assert accounts.residue == D("713500")
    by_id = {d.beneficiary_id: d for d in accounts.distributions}
    assert by_id["beneficiary_b"].entitlement == D("356750")
    assert by_id["beneficiary_c"].entitlement == D("356750")
    assert accounts.is_balanced() is True


def test_distribution_account_equals_legacies_plus_residue():
    accounts = compute_accounts(seed_style_input())
    assert accounts.distribution_account == accounts.legacies_total + accounts.residue
    assert accounts.is_balanced() is True


def test_tampered_accounts_fail_is_balanced():
    accounts = compute_accounts(seed_style_input())
    tampered = accounts.model_copy(update={"residue": accounts.residue + D("1")})
    assert tampered.is_balanced() is False


def test_specific_legacy_treated_as_fixed_amount():
    accounts = compute_accounts(
        seed_style_input(
            legacies=(
                Legacy(
                    beneficiary_id="beneficiary_a",
                    legacy_type=LegacyType.SPECIFIC,
                    amount=D("20000"),
                ),
                Legacy(
                    beneficiary_id="beneficiary_b",
                    legacy_type=LegacyType.RESIDUARY,
                    share=D("1"),
                ),
            )
        )
    )
    # residue = 950000 - 12000 - 28000 - 20000 = 890000
    assert accounts.residue == D("890000")
    assert accounts.is_balanced() is True
