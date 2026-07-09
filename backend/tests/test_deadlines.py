"""Tests for statutory deadline derivations (England and Wales).

All dates are synthetic examples. No personal data.
"""

from datetime import date

from app.domain.deadlines import (
    StatutoryDeadline,
    cgt_60_day_deadline,
    gazette_claim_deadline,
    grant_application_earliest,
    iht400_filing_due,
    iht_payment_due,
    instalment_dates,
    isa_exemption_end,
)

# ---------------------------------------------------------------------------
# IHT payment due: end of the sixth month after the month of death.
# ---------------------------------------------------------------------------


def test_iht_payment_due_mid_month():
    d = iht_payment_due(date(2025, 1, 15))
    assert d.due_date == date(2025, 7, 31)
    assert "226" in d.basis


def test_iht_payment_due_clamps_to_short_month():
    # Death in August: sixth month after is February.
    d = iht_payment_due(date(2025, 8, 31))
    assert d.due_date == date(2026, 2, 28)


def test_iht_payment_due_leap_year():
    d = iht_payment_due(date(2023, 8, 15))
    assert d.due_date == date(2024, 2, 29)


# ---------------------------------------------------------------------------
# IHT400 filing: 12 months from the end of the month of death.
# ---------------------------------------------------------------------------


def test_iht400_filing_due():
    d = iht400_filing_due(date(2025, 1, 15))
    assert d.due_date == date(2026, 1, 31)
    assert "216" in d.basis


def test_iht400_filing_due_february():
    d = iht400_filing_due(date(2024, 2, 29))
    assert d.due_date == date(2025, 2, 28)


# ---------------------------------------------------------------------------
# Gazette section 27 notice: two months and one day from the notice.
# ---------------------------------------------------------------------------


def test_gazette_claim_deadline():
    d = gazette_claim_deadline(date(2025, 3, 15))
    assert d.due_date == date(2025, 5, 16)
    assert "27" in d.basis
    assert "Trustee Act 1925" in d.basis


def test_gazette_claim_deadline_month_end():
    d = gazette_claim_deadline(date(2025, 12, 31))
    # Two months from 31 December clamps to 28 February, plus one day.
    assert d.due_date == date(2026, 3, 1)


# ---------------------------------------------------------------------------
# Instalment option: first instalment at the normal due date, then nine
# further yearly instalments (ten in total).
# ---------------------------------------------------------------------------


def test_instalment_dates():
    dates = instalment_dates(date(2025, 1, 15))
    assert len(dates) == 10
    assert dates[0].due_date == date(2025, 7, 31)
    assert dates[1].due_date == date(2026, 7, 31)
    assert dates[9].due_date == date(2034, 7, 31)
    assert all("227" in d.basis for d in dates)


# ---------------------------------------------------------------------------
# CGT 60-day reporting deadline for UK residential property disposals.
# ---------------------------------------------------------------------------


def test_cgt_60_day_deadline():
    d = cgt_60_day_deadline(date(2025, 1, 1))
    assert d.due_date == date(2025, 3, 2)
    assert "60" in d.basis


# ---------------------------------------------------------------------------
# ISA exemption: completion of administration or third anniversary of
# death, whichever comes first.
# ---------------------------------------------------------------------------


def test_isa_exemption_end_third_anniversary():
    d = isa_exemption_end(date(2025, 6, 10))
    assert d.due_date == date(2028, 6, 10)
    assert "1998/1870" in d.basis


def test_isa_exemption_end_completion_first():
    d = isa_exemption_end(
        date(2025, 6, 10), administration_completed=date(2026, 9, 1)
    )
    assert d.due_date == date(2026, 9, 1)


def test_isa_exemption_end_anniversary_before_late_completion():
    d = isa_exemption_end(
        date(2025, 6, 10), administration_completed=date(2029, 1, 1)
    )
    assert d.due_date == date(2028, 6, 10)


def test_isa_exemption_end_leap_day_death():
    d = isa_exemption_end(date(2024, 2, 29))
    assert d.due_date == date(2027, 2, 28)


# ---------------------------------------------------------------------------
# Grant application: wait 20 working days after submitting the IHT400
# before applying for the grant.
# ---------------------------------------------------------------------------


def test_grant_application_earliest():
    # Monday 6 January 2025 plus 20 working days is Monday 3 February 2025.
    d = grant_application_earliest(date(2025, 1, 6))
    assert d.due_date == date(2025, 2, 3)
    assert "20 working days" in d.basis


def test_grant_application_earliest_from_friday():
    # Friday 3 January 2025 plus 20 working days is Friday 31 January 2025.
    d = grant_application_earliest(date(2025, 1, 3))
    assert d.due_date == date(2025, 1, 31)


# ---------------------------------------------------------------------------
# Every derivation returns a citation.
# ---------------------------------------------------------------------------


def test_all_deadlines_carry_citations():
    results = [
        iht_payment_due(date(2025, 1, 15)),
        iht400_filing_due(date(2025, 1, 15)),
        gazette_claim_deadline(date(2025, 3, 15)),
        cgt_60_day_deadline(date(2025, 1, 1)),
        isa_exemption_end(date(2025, 6, 10)),
        grant_application_earliest(date(2025, 1, 6)),
        *instalment_dates(date(2025, 1, 15)),
    ]
    for r in results:
        assert isinstance(r, StatutoryDeadline)
        assert r.basis.strip() != ""
        assert isinstance(r.due_date, date)
