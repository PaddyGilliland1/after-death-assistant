"""Tests for the pure IHT engine (contract section 7).

Constants: NRB 325000, RNRB 175000, taper threshold 2000000.
All figures are synthetic. No personal data.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.iht_engine import Assessment, AssetCategory, AssetItem, Estate, assess
from app.domain.jurisdiction import ProvenancedValue
from app.domain.jurisdiction.england_wales import ENGLAND_WALES

D = Decimal


def make_estate(**kwargs) -> Estate:
    """Estate factory with the excepted-estate facts established as
    known-safe values, so tests exercise one rule at a time. Facts left
    as None mean unknown and are conservatively not excepted."""
    defaults = {
        "net_value": D("0"),
        "tnrb_pct": D("0"),
        "trnrb_pct": D("0"),
        "residence_to_descendants_value": D("0"),
        "exempt_transfers": D("0"),
        "charity_share": D("0"),
        "claims_rnrb": None,
        "gifts_in_seven_years": D("0"),
        "trust_assets_value": D("0"),
        "trust_count": 0,
        "foreign_assets_value": D("0"),
        "gifts_with_reservation": False,
    }
    defaults.update(kwargs)
    return Estate(**defaults)


# ---------------------------------------------------------------------------
# The exact executable table from contract section 7 (5 rows).
# ---------------------------------------------------------------------------

CONTRACT_TABLE = [
    # net_value, tnrb_pct, trnrb_pct, residence_to_descendants, allowance, tax
    (D("960000"), D("1.0"), D("1.0"), D("340000"), D("990000"), D("0")),
    (D("1000000"), D("1.0"), D("1.0"), D("380000"), D("1000000"), D("0")),
    (D("1020000"), D("1.0"), D("1.0"), D("400000"), D("1000000"), D("8000")),
    (D("1060000"), D("1.0"), D("1.0"), D("340000"), D("990000"), D("28000")),
    (D("960000"), D("0.5"), D("0.5"), D("340000"), D("750000"), D("84000")),
]


@pytest.mark.parametrize(
    "net_value,tnrb_pct,trnrb_pct,residence,expected_allowance,expected_tax",
    CONTRACT_TABLE,
)
def test_contract_table(
    net_value, tnrb_pct, trnrb_pct, residence, expected_allowance, expected_tax
):
    estate = make_estate(
        net_value=net_value,
        tnrb_pct=tnrb_pct,
        trnrb_pct=trnrb_pct,
        residence_to_descendants_value=residence,
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.allowance == expected_allowance
    assert result.tax == expected_tax


# ---------------------------------------------------------------------------
# claims_rnrb forces IHT400 (the critical rule).
# ---------------------------------------------------------------------------


def test_claims_rnrb_forces_iht400():
    estate = make_estate(net_value=D("300000"), claims_rnrb=True)
    result = assess(estate, ENGLAND_WALES)
    assert result.must_file_iht400 is True


def test_claims_rnrb_forces_iht400_even_when_otherwise_excepted():
    # Without the claim this estate is a low-value excepted estate.
    without_claim = assess(make_estate(net_value=D("300000")), ENGLAND_WALES)
    assert without_claim.is_excepted is True
    assert without_claim.must_file_iht400 is False

    with_claim = assess(
        make_estate(net_value=D("300000"), claims_rnrb=True), ENGLAND_WALES
    )
    assert with_claim.must_file_iht400 is True


# ---------------------------------------------------------------------------
# claims_rnrb derivation: None derives from the residence value.
# ---------------------------------------------------------------------------


def test_claims_rnrb_derived_from_residence_value():
    estate = make_estate(
        net_value=D("800000"),
        residence_to_descendants_value=D("175000"),
        claims_rnrb=None,
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.must_file_iht400 is True
    assert "IHT435" in result.required_schedules


def test_explicit_false_claim_with_no_residence_stays_excepted_eligible():
    estate = make_estate(net_value=D("300000"), claims_rnrb=False)
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is True
    assert result.must_file_iht400 is False


# ---------------------------------------------------------------------------
# Downsizing addition extends the value the RNRB is set against.
# ---------------------------------------------------------------------------


def test_downsizing_addition_extends_rnrb():
    estate = make_estate(
        net_value=D("1000000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("300000"),
        downsizing_addition=D("100000"),
    )
    result = assess(estate, ENGLAND_WALES)
    # min(350000, 300000 + 100000) = 350000
    assert result.rnrb == D("350000")
    assert result.allowance == D("675000")


def test_zero_downsizing_addition_changes_nothing():
    base = make_estate(
        net_value=D("960000"),
        tnrb_pct=D("1.0"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("340000"),
    )
    result = assess(base, ENGLAND_WALES)
    assert result.allowance == D("990000")
    assert result.tax == D("0")


# ---------------------------------------------------------------------------
# The £2m taper.
# ---------------------------------------------------------------------------


def test_taper_reduces_rnrb_above_two_million():
    estate = make_estate(
        net_value=D("2100000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("350000"),
    )
    result = assess(estate, ENGLAND_WALES)
    # rnrb_max = 350000 - (2100000 - 2000000) / 2 = 300000
    assert result.rnrb_max == D("300000")
    assert result.rnrb == D("300000")


def test_no_taper_at_exactly_two_million():
    estate = make_estate(
        net_value=D("2000000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("350000"),
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.rnrb_max == D("350000")
    assert result.rnrb == D("350000")


def test_taper_floors_rnrb_at_zero():
    estate = make_estate(
        net_value=D("3000000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("350000"),
    )
    result = assess(estate, ENGLAND_WALES)
    # Reduction would be 500000, more than the 350000 maximum: floor at 0.
    assert result.rnrb_max == D("0")
    assert result.rnrb == D("0")


def test_rnrb_capped_at_residence_to_descendants_value():
    estate = make_estate(
        net_value=D("900000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("120000"),
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.rnrb == D("120000")


# ---------------------------------------------------------------------------
# Charity rate: 36% at charity_share >= 0.10, else 40%.
# ---------------------------------------------------------------------------


def test_charity_rate_applies_at_ten_percent():
    estate = make_estate(
        net_value=D("1500000"), tnrb_pct=D("1.0"), charity_share=D("0.10")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.rate == D("0.36")
    # taxable = 1500000 - 650000 = 850000; tax = 850000 * 0.36
    assert result.taxable == D("850000")
    assert result.tax == D("306000")


def test_standard_rate_just_below_ten_percent():
    estate = make_estate(
        net_value=D("1500000"), tnrb_pct=D("1.0"), charity_share=D("0.0999")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.rate == D("0.40")
    assert result.tax == D("340000")


def test_boundary_exactly_ten_percent_charity():
    estate = make_estate(
        net_value=D("1000000"), charity_share=D("0.10")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.rate == D("0.36")


# ---------------------------------------------------------------------------
# Exempt transfers reduce the taxable amount.
# ---------------------------------------------------------------------------


def test_exempt_transfers_reduce_taxable():
    estate = make_estate(net_value=D("1000000"), exempt_transfers=D("600000"))
    result = assess(estate, ENGLAND_WALES)
    # taxable = max(1000000 - 600000 - 325000, 0) = 75000
    assert result.taxable == D("75000")
    assert result.tax == D("30000")


def test_taxable_floors_at_zero():
    estate = make_estate(net_value=D("200000"))
    result = assess(estate, ENGLAND_WALES)
    assert result.taxable == D("0")
    assert result.tax == D("0")


# ---------------------------------------------------------------------------
# Excepted estate rules (England and Wales).
# ---------------------------------------------------------------------------


def test_low_value_estate_is_excepted():
    result = assess(make_estate(net_value=D("300000")), ENGLAND_WALES)
    assert result.is_excepted is True
    assert result.must_file_iht400 is False


def test_full_transferred_nrb_extends_excepted_limit():
    estate = make_estate(net_value=D("600000"), tnrb_pct=D("1.0"))
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is True


def test_partial_transferred_nrb_blocks_excepted_status():
    # A partial transferred NRB claim needs a full account (IHT402 with IHT400).
    estate = make_estate(net_value=D("400000"), tnrb_pct=D("0.5"))
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False
    assert result.must_file_iht400 is True


def test_exempt_excepted_estate():
    # Large gross but mostly spouse or charity exempt: still excepted.
    estate = make_estate(
        net_value=D("2000000"), exempt_transfers=D("1800000")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is True


def test_gifts_above_limit_block_excepted_status():
    estate = make_estate(
        net_value=D("300000"), gifts_in_seven_years=D("300000")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False
    assert result.must_file_iht400 is True


def test_foreign_assets_above_limit_block_excepted_status():
    estate = make_estate(
        net_value=D("300000"), foreign_assets_value=D("150000")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False


def test_trust_assets_above_limit_block_excepted_status():
    estate = make_estate(
        net_value=D("300000"), trust_assets_value=D("300000")
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False


def test_unknown_facts_are_conservative_not_excepted():
    # Bare model defaults leave the excepted-estate facts as None
    # (unknown), so the estate must not be treated as excepted.
    estate = Estate(net_value=D("300000"))
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False
    assert result.must_file_iht400 is True


def test_gifts_with_reservation_block_excepted_status():
    estate = make_estate(
        net_value=D("300000"), gifts_with_reservation=True
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False
    assert result.must_file_iht400 is True


def test_more_than_one_trust_blocks_excepted_status():
    estate = make_estate(
        net_value=D("300000"),
        trust_assets_value=D("100000"),
        trust_count=2,
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is False


def test_single_trust_within_limit_allows_excepted_status():
    estate = make_estate(
        net_value=D("300000"),
        trust_assets_value=D("100000"),
        trust_count=1,
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.is_excepted is True


# ---------------------------------------------------------------------------
# Required schedules, data-driven from asset categories and claims.
# ---------------------------------------------------------------------------


def test_iht402_when_transferred_nrb_claimed():
    estate = make_estate(net_value=D("700000"), tnrb_pct=D("1.0"))
    result = assess(estate, ENGLAND_WALES)
    assert "IHT402" in result.required_schedules


def test_iht435_when_claiming_rnrb():
    estate = make_estate(
        net_value=D("700000"),
        residence_to_descendants_value=D("175000"),
        claims_rnrb=True,
    )
    result = assess(estate, ENGLAND_WALES)
    assert "IHT435" in result.required_schedules
    assert "IHT436" not in result.required_schedules


def test_iht436_when_claiming_transferred_rnrb():
    estate = make_estate(
        net_value=D("700000"),
        trnrb_pct=D("1.0"),
        residence_to_descendants_value=D("340000"),
        claims_rnrb=True,
    )
    result = assess(estate, ENGLAND_WALES)
    assert "IHT435" in result.required_schedules
    assert "IHT436" in result.required_schedules


def test_asset_category_schedule_mapping():
    estate = make_estate(
        net_value=D("900000"),
        assets=(
            AssetItem(category=AssetCategory.LAND_AND_BUILDINGS, value=D("340000")),
            AssetItem(category=AssetCategory.BANK_ACCOUNTS, value=D("400000")),
            AssetItem(category=AssetCategory.NSANDI, value=D("50000")),
            AssetItem(category=AssetCategory.HOUSEHOLD_GOODS, value=D("10000")),
            AssetItem(category=AssetCategory.LISTED_SHARES, value=D("80000")),
            AssetItem(category=AssetCategory.UNLISTED_SHARES, value=D("20000")),
        ),
    )
    result = assess(estate, ENGLAND_WALES)
    for code in ("IHT405", "IHT406", "IHT407", "IHT411", "IHT412"):
        assert code in result.required_schedules


def test_iht403_when_gifts_present():
    estate = make_estate(
        net_value=D("500000"), gifts_in_seven_years=D("9000")
    )
    result = assess(estate, ENGLAND_WALES)
    assert "IHT403" in result.required_schedules


def test_no_schedules_for_bare_estate():
    estate = make_estate(net_value=D("300000"))
    result = assess(estate, ENGLAND_WALES)
    assert result.required_schedules == ()


def test_schedules_sorted_and_deduplicated():
    estate = make_estate(
        net_value=D("900000"),
        assets=(
            AssetItem(category=AssetCategory.BANK_ACCOUNTS, value=D("100000")),
            AssetItem(category=AssetCategory.NSANDI, value=D("50000")),
            AssetItem(category=AssetCategory.LAND_AND_BUILDINGS, value=D("340000")),
        ),
    )
    result = assess(estate, ENGLAND_WALES)
    assert result.required_schedules == tuple(sorted(set(result.required_schedules)))
    assert result.required_schedules.count("IHT406") == 1


# ---------------------------------------------------------------------------
# Provenance and immutability guardrails.
# ---------------------------------------------------------------------------


def test_constants_carry_provenance():
    for pv in (
        ENGLAND_WALES.nrb,
        ENGLAND_WALES.rnrb,
        ENGLAND_WALES.taper_threshold,
        ENGLAND_WALES.charity_rate_threshold,
        ENGLAND_WALES.standard_rate,
        ENGLAND_WALES.reduced_rate,
    ):
        assert isinstance(pv, ProvenancedValue)
        assert pv.source_url.startswith("https://")
        assert pv.fetch_date is not None


def test_default_constant_values():
    assert ENGLAND_WALES.nrb.value == D("325000")
    assert ENGLAND_WALES.rnrb.value == D("175000")
    assert ENGLAND_WALES.taper_threshold.value == D("2000000")
    assert ENGLAND_WALES.charity_rate_threshold.value == D("0.10")
    assert ENGLAND_WALES.standard_rate.value == D("0.40")
    assert ENGLAND_WALES.reduced_rate.value == D("0.36")


def test_models_are_frozen():
    estate = make_estate(net_value=D("100000"))
    with pytest.raises(ValidationError):
        estate.net_value = D("200000")
    result = assess(estate, ENGLAND_WALES)
    assert isinstance(result, Assessment)
    with pytest.raises(ValidationError):
        result.tax = D("1")


def test_assessment_carries_jurisdiction_code():
    result = assess(make_estate(net_value=D("100000")), ENGLAND_WALES)
    assert result.jurisdiction_code == "england_wales"
