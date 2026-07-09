"""Pydantic v2 schemas and pure derivation helpers for the P2 tracker
routers (build contract sections 6 and 8; FEATURES.md modules 14 to 18).

Trackers covered: reliefs and reclaims (Module 14), administration-period
tax (Module 15), asset tracing completeness (Module 16), digital items
(Module 17), the veteran checklist (Module 18) and IHT schedule task
seeding.

Conventions match app.schemas.registers:
- Create schemas carry estate_id plus the business fields.
- Update schemas make every field optional; routers apply them with
  model_dump(exclude_unset=True) for true partial updates.
- Read schemas add id, estate_id and the audit columns.
- No tax is ever computed here. The only arithmetic permitted is date
  derivation (statutory windows, mirroring app.domain.deadlines) and
  subtraction or summation of figures the user has already stored.
"""

import calendar
import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReliefType
from app.schemas.registers import ReadAuditFields

# ---------------------------------------------------------------------------
# Module 14: reliefs and reclaims
# ---------------------------------------------------------------------------


def _add_months(start: dt.date, months: int) -> dt.date:
    """Add calendar months, clamping the day to the target month's end.

    Mirrors app.domain.deadlines._add_months; duplicated here because the
    domain module does not yet expose IHT35/IHT38 window derivations (see
    the model-gap report for this build).
    """
    total = start.year * 12 + (start.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


# Sale windows for the loss reliefs, as months from the date of death,
# each with its statutory basis. Only iht35 and iht38 have a fixed window
# derivable from the date of death; RNRB downsizing and BPR/APR deadlines
# are entered manually.
RELIEF_WINDOW_MONTHS: dict[ReliefType, tuple[int, str]] = {
    ReliefType.iht35: (
        12,
        "IHTA 1984 ss.178-179 (claimed on form IHT35): relief for "
        "qualifying investments sold at an overall loss within 12 months "
        "of the date of death, all such sales netted. The claim itself "
        "must be made within four years after the end of that 12 month "
        "period.",
    ),
    ReliefType.iht38: (
        48,
        "IHTA 1984 ss.190-191 (claimed on form IHT38): relief for land or "
        "buildings sold below probate value within four years of the date "
        "of death; relief for sales in the fourth year is restricted to "
        "sales at a loss.",
    ),
}

RECLAIM_NOTE = (
    "Difference between the stored probate value and sale value only. "
    "The actual reclaim depends on the estate rate of inheritance tax "
    "actually paid, and yields cash back only if IHT was paid; no tax is "
    "computed here."
)


def derive_relief_window(
    relief_type: ReliefType, date_of_death: dt.date | None
) -> tuple[dt.date, str] | None:
    """The (window_deadline, basis) for a relief type, or None when the
    type has no derivable window or the date of death is unknown."""
    if date_of_death is None:
        return None
    entry = RELIEF_WINDOW_MONTHS.get(relief_type)
    if entry is None:
        return None
    months, basis = entry
    return _add_months(date_of_death, months), basis


def derive_potential_reclaim(
    probate_value: Decimal | None, sale_value: Decimal | None
) -> Decimal | None:
    """probate_value minus sale_value, floored at zero. A subtraction of
    stored figures only; never a tax computation (see RECLAIM_NOTE)."""
    if probate_value is None or sale_value is None:
        return None
    return max(probate_value - sale_value, Decimal("0"))


class ReliefBase(BaseModel):
    relief_type: ReliefType
    asset_id: uuid.UUID | None = None
    probate_value: Decimal | None = None
    sale_value: Decimal | None = None
    sale_date: dt.date | None = None
    window_deadline: dt.date | None = None
    potential_reclaim: Decimal | None = None
    status: str | None = None


class ReliefCreate(ReliefBase):
    estate_id: uuid.UUID


class ReliefUpdate(BaseModel):
    relief_type: ReliefType | None = None
    asset_id: uuid.UUID | None = None
    probate_value: Decimal | None = None
    sale_value: Decimal | None = None
    sale_date: dt.date | None = None
    window_deadline: dt.date | None = None
    potential_reclaim: Decimal | None = None
    status: str | None = None


class ReliefRead(ReadAuditFields, ReliefBase):
    """A relief row plus derived context. window_basis and reclaim_note
    are recomputed on read, not stored (the relief table has no basis
    column; reported as a model gap)."""

    window_basis: str | None = None
    reclaim_note: str | None = None


class ReliefWatchlistItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estate_id: uuid.UUID
    relief_type: ReliefType
    asset_id: uuid.UUID | None
    window_deadline: dt.date
    days_remaining: int
    potential_reclaim: Decimal | None
    status: str | None


# ---------------------------------------------------------------------------
# Module 15: administration-period tax
# ---------------------------------------------------------------------------

# Informal-route thresholds documented as data with source citations
# (never hard-coded silently). Amounts are strings: they are statutory
# constants for comparison, not computed figures.
INFORMAL_ROUTE_THRESHOLDS: dict[str, dict[str, str]] = {
    "income_de_minimis": {
        "amount": "500",
        "meaning": (
            "No income tax to report for a tax year in which the estate's "
            "total income is 500 pounds or less."
        ),
        "source": (
            "GOV.UK, Dealing with the estate of someone who has died: "
            "https://www.gov.uk/probate-estate/managing-and-selling-assets"
        ),
    },
    "gains_annual_exempt_amount": {
        "amount": "3000",
        "meaning": (
            "Estates get the capital gains annual exempt amount (3,000 "
            "pounds from 2024-25) for the year of death and the two "
            "following tax years; total gains above it need reporting."
        ),
        "source": (
            "GOV.UK, Capital Gains Tax allowances: "
            "https://www.gov.uk/capital-gains-tax/allowances"
        ),
    },
    "complex_estate_conditions": {
        "amount": "2500000",
        "meaning": (
            "An estate is complex and must register for the Trust and "
            "Estate route if its value exceeds 2.5 million pounds, tax due "
            "for any one tax year exceeds 10,000 pounds, or assets sold in "
            "any one tax year exceed 500,000 pounds."
        ),
        "source": (
            "GOV.UK, Register an estate as a personal representative: "
            "https://www.gov.uk/guidance/register-an-estate-as-a-personal-representative"
        ),
    },
}


def derive_estate_complex(
    income_total: Decimal | None,
    gains: list[Decimal],
    estate_net_value: Decimal | None,
) -> tuple[bool, list[str]]:
    """Whether the estate counts as complex for this tax year's figures.

    Pure comparison of stored figures against the documented thresholds
    (INFORMAL_ROUTE_THRESHOLDS). estate_net_value is the latest stored
    IHT assessment input; None means the estate-value condition cannot be
    verified, which is treated conservatively as complex until confirmed.
    Returns (estate_complex, reasons).
    """
    reasons: list[str] = []
    income_limit = Decimal(INFORMAL_ROUTE_THRESHOLDS["income_de_minimis"]["amount"])
    gains_limit = Decimal(INFORMAL_ROUTE_THRESHOLDS["gains_annual_exempt_amount"]["amount"])
    value_limit = Decimal(INFORMAL_ROUTE_THRESHOLDS["complex_estate_conditions"]["amount"])

    if income_total is not None and income_total > income_limit:
        reasons.append(
            f"Income of {income_total} exceeds the {income_limit} pound "
            "de minimis for the year."
        )
    total_gains = sum(gains, Decimal("0"))
    if total_gains > gains_limit:
        reasons.append(
            f"Total stored gains of {total_gains} exceed the {gains_limit} "
            "pound annual exempt amount."
        )
    if estate_net_value is None:
        reasons.append(
            "The estate-value condition cannot be verified (no IHT "
            "assessment stored); treated as complex until confirmed."
        )
    elif estate_net_value > value_limit:
        reasons.append(
            f"The latest assessed net estate of {estate_net_value} exceeds "
            f"the {value_limit} pound complex-estate limit."
        )
    return (bool(reasons), reasons)


class CgtDisposal(BaseModel):
    """One disposal in the cgt_disposals JSON list."""

    description: str = ""
    disposal_date: dt.date | None = None
    proceeds: Decimal | None = None
    gain: Decimal | None = None


class CgtDeadlineEntry(BaseModel):
    """One derived 60-day reporting deadline (from app.domain.deadlines)."""

    disposal_date: dt.date
    deadline: dt.date
    basis: str


class AdminTaxBase(BaseModel):
    tax_year: str = Field(pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-27")
    income_total: Decimal | None = None
    cgt_disposals: list[CgtDisposal] = Field(default_factory=list)


class AdminTaxCreate(AdminTaxBase):
    estate_id: uuid.UUID


class AdminTaxUpdate(BaseModel):
    tax_year: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    income_total: Decimal | None = None
    cgt_disposals: list[CgtDisposal] | None = None


class AdminTaxRead(ReadAuditFields):
    tax_year: str
    income_total: Decimal | None
    estate_complex: bool | None
    cgt_disposals: list[CgtDisposal]
    cgt_60day_deadlines: list[CgtDeadlineEntry]
    isa_exemption_end: dt.date | None
    complex_reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module 17: digital items
# ---------------------------------------------------------------------------


class DigitalItemBase(BaseModel):
    service: str
    type: str | None = None
    login_known: bool = False
    action: str | None = None
    recurring_amount: Decimal | None = None
    status: str | None = None


class DigitalItemCreate(DigitalItemBase):
    estate_id: uuid.UUID


class DigitalItemUpdate(BaseModel):
    service: str | None = None
    type: str | None = None
    login_known: bool | None = None
    action: str | None = None
    recurring_amount: Decimal | None = None
    status: str | None = None


class DigitalItemRead(ReadAuditFields, DigitalItemBase):
    pass


class RecurringTotalRead(BaseModel):
    """Sum of stored recurring amounts for active items (aggregation of
    stored figures only; payment frequency is not normalised)."""

    recurring_total: Decimal
    item_count: int
    note: str


# ---------------------------------------------------------------------------
# Module 16: asset tracing and completeness
# ---------------------------------------------------------------------------


class TracingAssetItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    sub_type: str | None
    description: str
    dod_value: Decimal | None
    value_basis: str


class TracingDebtorItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    amount_expected: Decimal | None
    amount_received: Decimal | None
    outstanding: Decimal
    status: str | None


class TracingSearchSuggestion(BaseModel):
    name: str
    url: str
    covers: str


class TracingCompletenessRead(BaseModel):
    estimated_value_assets: list[TracingAssetItem]
    unnotified_contacts_count: int
    outstanding_debtors: list[TracingDebtorItem]
    unconfirmed_unlisted_holdings: list[TracingAssetItem]
    search_suggestions: list[TracingSearchSuggestion]
    warning: str


# Official, free tracing routes (Module 16). Static reference data.
TRACING_SEARCH_SUGGESTIONS: tuple[TracingSearchSuggestion, ...] = (
    TracingSearchSuggestion(
        name="My Lost Account",
        url="https://www.mylostaccount.org.uk",
        covers="Lost or dormant bank and building society accounts and NS&I savings",
    ),
    TracingSearchSuggestion(
        name="NS&I tracing service",
        url="https://www.nsandi.com/get-to-know-us/why-nsi/tracing-service",
        covers="Premium Bonds and other NS&I holdings, including unclaimed prizes",
    ),
    TracingSearchSuggestion(
        name="Pension Tracing Service (DWP)",
        url="https://www.gov.uk/find-pension-contact-details",
        covers="Contact details for lost workplace and personal pension schemes",
    ),
    TracingSearchSuggestion(
        name="Unclaimed Assets Register (Experian)",
        url="https://www.uar.co.uk",
        covers="Lost life policies, pensions, unit trusts and share dividends",
    ),
)

TRACING_WARNING = (
    "These official searches are free. Never pay a reclaim firm to run "
    "them on the estate's behalf."
)


# ---------------------------------------------------------------------------
# IHT schedule task seeding
# ---------------------------------------------------------------------------


class ScheduleSeedResult(BaseModel):
    """Titles created and skipped by POST /iht/schedules/seed-tasks."""

    created: list[str]
    skipped: list[str]


# ---------------------------------------------------------------------------
# Module 18: veteran checklist
# ---------------------------------------------------------------------------


class VeteranChecklistItem(BaseModel):
    """One entry in seed_templates/veteran_checklist.json."""

    order: int
    title: str
    description: str
    url: str | None = None


class VeteranChecklistEntry(VeteranChecklistItem):
    """A checklist item with the status of its tracking task, if seeded."""

    task_id: uuid.UUID | None = None
    task_status: str | None = None


class VeteranSeedResult(BaseModel):
    created: list[str]
    skipped: list[str]
