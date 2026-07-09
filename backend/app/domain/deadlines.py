"""Statutory date derivations for estate administration, England and Wales.

Every derivation is a pure function of the dates it is given (date of
death, notice date, completion date and so on) and returns the derived
date together with a short citation of its statutory basis.

Pure module: no I/O, no clock reads, no environment access.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict


class StatutoryDeadline(BaseModel):
    """A derived statutory date with its legal basis."""

    model_config = ConfigDict(frozen=True)

    name: str
    due_date: date
    basis: str


# ---------------------------------------------------------------------------
# Date arithmetic helpers (calendar months, clamped to month end).
# ---------------------------------------------------------------------------


def _add_months(start: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's end."""
    total = start.year * 12 + (start.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _end_of_month(value: date) -> date:
    return date(
        value.year, value.month, calendar.monthrange(value.year, value.month)[1]
    )


# ---------------------------------------------------------------------------
# Derivations.
# ---------------------------------------------------------------------------


def iht_payment_due(date_of_death: date) -> StatutoryDeadline:
    """Inheritance tax is due at the end of the sixth month after the
    month in which the death occurred."""
    due = _end_of_month(_add_months(date_of_death.replace(day=1), 6))
    return StatutoryDeadline(
        name="iht_payment_due",
        due_date=due,
        basis=(
            "IHTA 1984 s.226(1): tax due at the end of the sixth month "
            "after that in which the death occurred"
        ),
    )


def iht400_filing_due(date_of_death: date) -> StatutoryDeadline:
    """The IHT400 account must be delivered within 12 months from the
    end of the month in which the death occurred."""
    due = _end_of_month(_add_months(date_of_death.replace(day=1), 12))
    return StatutoryDeadline(
        name="iht400_filing_due",
        due_date=due,
        basis=(
            "IHTA 1984 s.216(6)(a): account within 12 months from the end "
            "of the month in which the death occurred"
        ),
    )


def gazette_claim_deadline(notice_date: date) -> StatutoryDeadline:
    """Creditor claim deadline after a section 27 notice: the notice must
    allow at least two months, so the customary deadline is two months
    and one day from the notice."""
    due = _add_months(notice_date, 2) + timedelta(days=1)
    return StatutoryDeadline(
        name="gazette_claim_deadline",
        due_date=due,
        basis=(
            "Trustee Act 1925 s.27(1): notice must allow not less than two "
            "months; deadline set at two months and one day from the notice"
        ),
    )


def instalment_dates(
    date_of_death: date, instalments: int = 10
) -> tuple[StatutoryDeadline, ...]:
    """The instalment option for qualifying property: ten equal yearly
    instalments, the first due when the tax would normally be due."""
    first = iht_payment_due(date_of_death).due_date
    basis = (
        "IHTA 1984 s.227: tax on qualifying property payable in ten equal "
        "yearly instalments, the first at the normal due date"
    )
    return tuple(
        StatutoryDeadline(
            name=f"iht_instalment_{number}",
            due_date=_add_months(first, 12 * (number - 1)),
            basis=basis,
        )
        for number in range(1, instalments + 1)
    )


def cgt_60_day_deadline(completion_date: date) -> StatutoryDeadline:
    """UK residential property disposal: report and pay capital gains tax
    within 60 days of completion."""
    return StatutoryDeadline(
        name="cgt_60_day_deadline",
        due_date=completion_date + timedelta(days=60),
        basis=(
            "FA 2019 Sch.2, as amended by FA 2022 s.23: UK residential "
            "property disposals reported and tax paid within 60 days of "
            "completion"
        ),
    )


def isa_exemption_end(
    date_of_death: date, administration_completed: date | None = None
) -> StatutoryDeadline:
    """A deceased investor's ISA keeps its tax-free status until the
    completion of the administration of the estate or the third
    anniversary of the death, whichever comes first."""
    third_anniversary = _add_months(date_of_death, 36)
    if administration_completed is not None:
        due = min(administration_completed, third_anniversary)
    else:
        due = third_anniversary
    return StatutoryDeadline(
        name="isa_exemption_end",
        due_date=due,
        basis=(
            "ISA Regulations 1998 (SI 1998/1870) reg.2(1) 'continuing "
            "account of a deceased investor' (inserted by SI 2017/1089): "
            "exemption ends on completion of administration or the third "
            "anniversary of death, whichever is first"
        ),
    )


def grant_application_earliest(
    iht400_submitted: date, working_days: int = 20
) -> StatutoryDeadline:
    """Grant application prerequisite: HMRC ask applicants to wait 20
    working days after submitting the IHT400 before applying for the
    grant of probate. Working days here are Monday to Friday; public
    holidays are not modelled and should be checked separately."""
    current = iht400_submitted
    remaining = working_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return StatutoryDeadline(
        name="grant_application_earliest",
        due_date=current,
        basis=(
            "HMRC and HMCTS guidance: wait 20 working days after sending "
            "the IHT400 before applying for the grant (weekends excluded; "
            "check public holidays separately)"
        ),
    )
