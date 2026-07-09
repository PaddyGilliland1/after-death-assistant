"""PDF rendering for the P3 export layer, built on fpdf2.

A calm, clearly-branded document style: title block, estate name header,
generated date and page numbers on every page, and a "DRAFT for approval,
not filed" watermark where applicable (drafts carry it; an approved
letter does not).

Nothing here is sent anywhere (build contract guardrail 1): these
functions return PDF bytes for the exports router to store as local
document rows. Every figure comes from the data passed in; this module
performs no computation beyond layout. Money is always displayed with
pence. UK English throughout; no em dashes.

Renderers:
- render_estate_accounts: four-account trial balance, legacies,
  per-beneficiary distribution table, reconciliation status line.
- render_iht_draft: a structured completed-form DRAFT from a forms_draft
  payload. NOT the official HMRC form (the Crown copyright template is
  not shipped); the header states it mirrors the form's field references
  for transcription and checking.
- render_clearance_draft: an IHT30 clearance application DRAFT content
  sheet (estate facts, declaration placeholders, gap list).
- render_letter: an approved notification letter on plain letterhead.
"""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

from fpdf import FPDF

from app.schemas.agents import FormsDraftPayload
from app.schemas.estate import EstateAccountsRead, EstateSettingsRead
from app.schemas.exports import BeneficiaryLine, LetterDraft
from app.schemas.iht import IhtAssessmentRead

BRAND_NAME = "AD Assistant"
DRAFT_WATERMARK = "DRAFT for approval, not filed"
NOT_RECORDED = "not recorded"

# Calm palette: near-black ink, muted grey secondary, hairline rules.
_INK = (40, 44, 52)
_MUTED = (110, 116, 128)
_RULE = (200, 204, 210)
_WATERMARK = (228, 230, 234)

_PAGE_WIDTH = 210  # A4 portrait, millimetres
_MARGIN = 18


def format_money(amount: Decimal | None) -> str:
    """Display money with pence, UK style; None means not recorded."""
    if amount is None:
        return NOT_RECORDED
    pence = amount.quantize(Decimal("0.01"))
    if pence < 0:
        return f"-£{-pence:,.2f}"
    return f"£{pence:,.2f}"


def format_date(value: dt.date | None) -> str:
    """UK long date, e.g. 6 July 2026; None means not recorded."""
    if value is None:
        return NOT_RECORDED
    return f"{value.day} {value.strftime('%B %Y')}"


def _latin1(text: str) -> str:
    """Core PDF fonts are Latin-1; replace anything outside it."""
    return text.encode("latin-1", "replace").decode("latin-1")


class _BrandedPDF(FPDF):
    """Shared document chrome: header, footer, watermark, section helpers."""

    def __init__(
        self,
        *,
        doc_title: str,
        estate_name: str,
        generated_on: dt.date,
        draft: bool,
    ) -> None:
        super().__init__(orientation="portrait", unit="mm", format="A4")
        self.doc_title = doc_title
        self.estate_name = estate_name
        self.generated_on = generated_on
        self.draft = draft
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=22)
        self.alias_nb_pages()

    # -- chrome ---------------------------------------------------------

    def header(self) -> None:  # noqa: D102 (fpdf hook)
        if self.draft:
            self._watermark()
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, _latin1(self.estate_name), align="L", new_x="LMARGIN", new_y="TOP")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, BRAND_NAME, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_RULE)
        self.set_line_width(0.2)
        self.line(_MARGIN, self.get_y() + 1, _PAGE_WIDTH - _MARGIN, self.get_y() + 1)
        self.ln(6)
        self.set_text_color(*_INK)

    def footer(self) -> None:  # noqa: D102 (fpdf hook)
        self.set_y(-16)
        self.set_draw_color(*_RULE)
        self.set_line_width(0.2)
        self.line(_MARGIN, self.get_y(), _PAGE_WIDTH - _MARGIN, self.get_y())
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(
            0,
            5,
            _latin1(f"Generated {format_date(self.generated_on)}"),
            align="L",
            new_x="LMARGIN",
            new_y="TOP",
        )
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    def _watermark(self) -> None:
        self.set_font("Helvetica", "B", 40)
        self.set_text_color(*_WATERMARK)
        with self.rotation(angle=48, x=_PAGE_WIDTH / 2, y=148):
            self.text(x=22, y=160, text=DRAFT_WATERMARK)
        self.set_text_color(*_INK)

    # -- layout helpers --------------------------------------------------

    def title_block(self, subtitle: str = "") -> None:
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*_INK)
        self.multi_cell(0, 8, _latin1(self.doc_title), new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*_MUTED)
            self.multi_cell(0, 5, _latin1(subtitle), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_INK)
        self.ln(3)

    def section_heading(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_INK)
        self.cell(0, 7, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_RULE)
        self.line(_MARGIN, self.get_y(), _PAGE_WIDTH - _MARGIN, self.get_y())
        self.ln(2)

    def kv_row(self, label: str, value: str, *, bold: bool = False) -> None:
        """A label on the left, a value right-aligned, on one line."""
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 10)
        self.cell(120, 6, _latin1(label))
        self.cell(0, 6, _latin1(value), align="R", new_x="LMARGIN", new_y="NEXT")

    def table_header(self, widths: Sequence[float], titles: Sequence[str]) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_MUTED)
        for width, title in zip(widths, titles, strict=True):
            self.cell(width, 6, _latin1(title))
        self.ln(6)
        self.set_draw_color(*_RULE)
        self.line(_MARGIN, self.get_y(), _PAGE_WIDTH - _MARGIN, self.get_y())
        self.set_text_color(*_INK)

    def table_row(
        self,
        widths: Sequence[float],
        cells: Sequence[str],
        *,
        aligns: Sequence[str] | None = None,
    ) -> None:
        self.set_font("Helvetica", "", 9)
        aligns = aligns or ["L"] * len(widths)
        for width, cell, align in zip(widths, cells, aligns, strict=True):
            self.cell(width, 6, _latin1(cell), align=align)
        self.ln(6)

    def paragraph(self, text: str, *, muted: bool = False) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*(_MUTED if muted else _INK))
        self.multi_cell(0, 5.5, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_INK)
        self.ln(1)

    def gap_list(self, gaps: Sequence[str]) -> None:
        """The gap list, rendered prominently."""
        self.section_heading("Gaps: information still needed")
        if not gaps:
            self.paragraph("No gaps recorded. Check the draft against the sources.")
            return
        self.set_font("Helvetica", "B", 10)
        for gap in gaps:
            self.multi_cell(0, 6, _latin1(f"•  {gap}"), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def to_bytes(self) -> bytes:
        return bytes(self.output())


def _new_pdf(
    *,
    doc_title: str,
    estate_name: str,
    generated_on: dt.date | None,
    draft: bool,
) -> _BrandedPDF:
    pdf = _BrandedPDF(
        doc_title=doc_title,
        estate_name=estate_name,
        generated_on=generated_on or dt.date.today(),
        draft=draft,
    )
    pdf.set_title(doc_title)
    pdf.set_author(BRAND_NAME)
    pdf.add_page()
    return pdf


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_estate_accounts(
    accounts: EstateAccountsRead,
    beneficiaries: Sequence[BeneficiaryLine],
    *,
    estate_name: str,
    generated_on: dt.date | None = None,
) -> bytes:
    """The estate accounts: trial balance, legacies, distributions.

    Every figure comes from the accounts and beneficiary rows passed in
    (assembled by the estate router from the pure domain module); nothing
    is computed here.
    """
    pdf = _new_pdf(
        doc_title="Estate accounts",
        estate_name=estate_name,
        generated_on=generated_on,
        draft=True,
    )
    pdf.title_block(
        "Draft estate accounts for the executors' approval. "
        "Figures are drawn from the registers by the accounts module."
    )

    names = {line.beneficiary_id: line.name for line in beneficiaries if line.name}

    pdf.section_heading("Trial balance: the four accounts")
    pdf.kv_row("Net estate", format_money(accounts.net_estate), bold=True)
    pdf.kv_row("Capital account", format_money(accounts.capital_account))
    pdf.kv_row("Income account", format_money(accounts.income_account))
    pdf.kv_row("Administration account", format_money(accounts.administration_account))
    pdf.kv_row("Distribution account", format_money(accounts.distribution_account))
    pdf.kv_row("Legacies total", format_money(accounts.legacies_total))
    pdf.kv_row("Residue", format_money(accounts.residue), bold=True)

    pdf.section_heading("Legacies")
    if beneficiaries:
        widths = (58, 30, 44, 42)
        pdf.table_header(widths, ("Beneficiary", "Type", "Amount or share", "Status"))
        for line in beneficiaries:
            if line.legacy_type == "residuary":
                amount_or_share = (
                    NOT_RECORDED
                    if line.amount_or_share is None
                    else f"{line.amount_or_share:.4f} of residue"
                )
            else:
                amount_or_share = format_money(line.amount_or_share)
            pdf.table_row(
                widths,
                (
                    line.name or line.beneficiary_id,
                    line.legacy_type or NOT_RECORDED,
                    amount_or_share,
                    line.status or "",
                ),
                aligns=("L", "L", "R", "L"),
            )
    else:
        pdf.paragraph("No legacies are recorded in the register.", muted=True)

    pdf.section_heading("Distribution: per-beneficiary residuary shares")
    if accounts.distributions:
        widths = (54, 22, 34, 32, 32)
        pdf.table_header(
            widths, ("Beneficiary", "Share", "Entitlement", "Interim paid", "Remaining")
        )
        for row in accounts.distributions:
            pdf.table_row(
                widths,
                (
                    names.get(row.beneficiary_id, row.beneficiary_id),
                    f"{row.residuary_share:.4f}",
                    format_money(row.entitlement),
                    format_money(row.interim_received),
                    format_money(row.remaining_due),
                ),
                aligns=("L", "R", "R", "R", "R"),
            )
    else:
        pdf.paragraph("No residuary beneficiaries are recorded.", muted=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    if accounts.is_balanced:
        pdf.multi_cell(0, 6, "Reconciliation: the accounts balance.", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.multi_cell(
            0,
            6,
            _latin1(
                "Reconciliation: the accounts DO NOT balance. "
                "Review the registers before approving or distributing."
            ),
        )
    return pdf.to_bytes()


def render_iht_draft(
    form_payload: FormsDraftPayload,
    *,
    estate_name: str,
    generated_on: dt.date | None = None,
) -> bytes:
    """A structured completed-form DRAFT from a forms_draft payload.

    The payload is the agent layer's stored draft
    (app.schemas.agents.FormsDraftPayload): the main form plus each
    required schedule, every value a verbatim copy of register or engine
    data. This is NOT the official HMRC form: the Crown copyright
    template is not shipped. The document mirrors the form's field
    references so a person can transcribe each value onto the official
    form and check it. The gap list is rendered prominently at the end.
    """
    form_codes = ", ".join(form.form for form in form_payload.forms) or "IHT forms"
    pdf = _new_pdf(
        doc_title=f"Completed-form draft: {form_codes}",
        estate_name=estate_name,
        generated_on=generated_on,
        draft=True,
    )
    pdf.title_block(
        "This is not the official HMRC form (the Crown copyright template "
        "is not shipped). It mirrors the form's field references for "
        "transcription onto the official form and for checking. "
        "Draft for approval; nothing is filed by this document."
    )
    if form_payload.constants_version:
        pdf.paragraph(
            f"Tax constants version: {form_payload.constants_version}", muted=True
        )

    widths = (44, 66, 64)
    all_gaps: list[str] = []
    for form in form_payload.forms:
        heading = f"{form.form}: {form.title}" if form.title else form.form
        pdf.section_heading(heading)
        if not form.sections:
            pdf.paragraph("No fields drafted for this form.", muted=True)
        else:
            pdf.table_header(widths, ("Field ref", "Label", "Value"))
            for field in form.sections:
                pdf.table_row(
                    widths, (field.field_ref, field.label, field.value or "GAP")
                )
                if field.source_entity:
                    pdf.set_font("Helvetica", "I", 7)
                    pdf.set_text_color(*_MUTED)
                    pdf.cell(widths[0], 4, "")
                    pdf.cell(0, 4, _latin1(f"source: {field.source_entity}"))
                    pdf.ln(4)
                    pdf.set_text_color(*_INK)
        for gap in form.gaps:
            all_gaps.append(f"{form.form}: {gap.item} ({gap.action})")

    if form_payload.narrative:
        pdf.section_heading("Cover note (drafted, no figures)")
        pdf.paragraph(form_payload.narrative)

    pdf.gap_list(all_gaps)
    return pdf.to_bytes()


def render_clearance_draft(
    estate: EstateSettingsRead,
    assessment: IhtAssessmentRead,
    *,
    generated_on: dt.date | None = None,
) -> bytes:
    """An IHT30 clearance application DRAFT content sheet.

    Estate facts and the assessment figures come from the rows passed in;
    the declaration is placeholder text for the executors to complete.
    Missing facts appear in the gap list.
    """
    estate_name = estate.name or "Estate under administration"
    pdf = _new_pdf(
        doc_title="Application for a clearance certificate (IHT30): draft content",
        estate_name=estate_name,
        generated_on=generated_on,
        draft=True,
    )
    pdf.title_block(
        "A content sheet for preparing the IHT30 clearance application. "
        "This is not the official HMRC form. Draft for approval; "
        "nothing is filed by this document."
    )

    pdf.section_heading("Estate facts")
    pdf.kv_row("Estate", estate_name)
    pdf.kv_row("Date of death", format_date(estate.date_of_death))
    pdf.kv_row("Date of grant", format_date(estate.grant_date))
    pdf.kv_row("IHT reference", "[IHT reference: to be entered by the executors]")
    pdf.kv_row("Constants version", estate.constants_version or NOT_RECORDED)

    pdf.section_heading("Position per the latest IHT assessment")
    pdf.kv_row("Assessed on", format_date(assessment.created_at.date()))
    pdf.kv_row("Allowance (NRB plus RNRB)", format_money(assessment.allowance))
    pdf.kv_row("Taxable amount", format_money(assessment.taxable))
    pdf.kv_row("Tax", format_money(assessment.tax), bold=True)
    pdf.kv_row(
        "IHT400 required",
        "yes" if assessment.must_file_iht400 else "no (excepted estate)",
    )

    pdf.section_heading("Declaration (placeholders for the executors)")
    pdf.paragraph(
        "We, the undersigned, apply for a certificate of discharge in "
        "respect of the estate named above. To the best of our knowledge "
        "and belief the accounts and values delivered are correct and "
        "complete."
    )
    for placeholder in (
        "[Full name of first executor]    [Signature]    [Date]",
        "[Full name of second executor]   [Signature]    [Date]",
    ):
        pdf.kv_row(placeholder, "")

    gaps: list[str] = []
    if not estate.name:
        gaps.append("Estate name is not recorded.")
    if estate.date_of_death is None:
        gaps.append("Date of death is not recorded.")
    if estate.grant_date is None:
        gaps.append("Date of grant is not recorded.")
    gaps.append("HMRC IHT reference must be entered by the executors.")
    pdf.gap_list(gaps)
    return pdf.to_bytes()


def render_letter(
    letter_draft: LetterDraft,
    *,
    estate_name: str,
    generated_on: dt.date | None = None,
) -> bytes:
    """An approved notification letter on plain letterhead.

    Approved letters carry no draft watermark. The letter is only ever
    stored as a document row; it is never sent by code (guardrail 1).
    """
    pdf = _new_pdf(
        doc_title=letter_draft.subject or "Notification letter",
        estate_name=estate_name,
        generated_on=generated_on,
        draft=False,
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        _latin1(format_date(letter_draft.date or generated_on or dt.date.today())),
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    if letter_draft.recipient_name:
        pdf.cell(0, 6, _latin1(letter_draft.recipient_name), new_x="LMARGIN", new_y="NEXT")
    for line in letter_draft.recipient_address:
        pdf.cell(0, 6, _latin1(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    if letter_draft.subject:
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 6, _latin1(letter_draft.subject), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    for paragraph in (p.strip() for p in letter_draft.body.split("\n\n")):
        if paragraph:
            pdf.paragraph(paragraph)
            pdf.ln(1)

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Yours faithfully,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    if letter_draft.sender_name:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _latin1(letter_draft.sender_name), new_x="LMARGIN", new_y="NEXT")
    if letter_draft.sender_role:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 5, _latin1(letter_draft.sender_role), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_INK)
    return pdf.to_bytes()
