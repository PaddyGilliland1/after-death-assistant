"""forms_draft graph: DETERMINISTIC mapping of estate data to IHT400 field
entries plus each required schedule.

No LLM touches a value (contract guardrail 2): every field entry is a
verbatim copy of a stored register value or of the deterministic engine's
snapshot, with its source entity recorded. The LLM is used ONLY for the
optional cover narrative, which is given no figures at all; without an
API key the graph still runs in full and the narrative is omitted.

The draft is stored as a document row with an approval-pending record and
the graph interrupts before the finalise node: a person approves before
the draft is treated as final, and a person submits anything to HMRC.
"""

import uuid
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.agents import llm, tools
from app.agents.tools import AgentContext
from app.domain.jurisdiction.england_wales import ENGLAND_WALES
from app.models import Asset, Estate
from app.schemas.agents import FormDraft, FormFieldEntry, FormGap
from app.services.reevaluation import _CATEGORY_MAP

FINALISE_NODE = "finalise"
DRAFT_KIND = "iht400_draft"

MAIN_FORM = "IHT400"

_SCHEDULE_TITLES = {
    "IHT400": "Inheritance Tax account",
    "IHT402": "Claim to transfer unused nil rate band",
    "IHT403": "Gifts and other transfers of value",
    "IHT405": "Houses, land, buildings and interests in land",
    "IHT406": "Bank and building society accounts and National Savings and Investments",
    "IHT407": "Household and personal goods",
    "IHT411": "Listed stocks and shares",
    "IHT412": "Unlisted stocks and shares and control holdings",
    "IHT435": "Claim for residence nil rate band",
    "IHT436": "Claim to transfer any unused residence nil rate band",
}

NARRATIVE_SYSTEM_PROMPT = """You write a short cover note for a drafted set of \
UK inheritance tax forms. Rules:
1. State NO figures, amounts or numbers of any kind.
2. Describe which forms were drafted and what the executors must still check, \
using the gap list supplied.
3. Make clear everything is a draft for human review and nothing has been or \
will be filed automatically.
4. Write in UK English. Do not use em dashes. Keep it under 200 words."""


class FormsDraftState(BaseModel):
    """Typed state for one forms_draft run."""

    form_code: str | None = None
    forms: list[FormDraft] = Field(default_factory=list)
    narrative: str | None = None
    constants_version: str = ""
    document_id: str | None = None
    approval_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Deterministic mapping (pure of LLMs; unit-tested end to end)
# ---------------------------------------------------------------------------


def _engine_category(asset: Asset) -> str | None:
    return _CATEGORY_MAP.get((asset.category or "").strip().lower())


def _schedule_for_asset(asset: Asset) -> str | None:
    """The schedule an asset reports on: explicit override first, then the
    jurisdiction's category map."""
    if asset.iht_schedule:
        return asset.iht_schedule
    category = _engine_category(asset)
    if category is None:
        return None
    return ENGLAND_WALES.CATEGORY_SCHEDULE_MAP.get(category.value)


def _asset_gaps(assets: list[Asset]) -> list[FormGap]:
    gaps: list[FormGap] = []
    for asset in assets:
        ref = f"asset:{asset.id}"
        if asset.dod_value is None:
            gaps.append(
                FormGap(
                    item=f"No date of death value recorded for {asset.description or 'an asset'}",
                    action="Obtain and record the date of death valuation.",
                    source_entity=ref,
                )
            )
        elif asset.value_basis is not None and str(asset.value_basis) == "estimate":
            gaps.append(
                FormGap(
                    item=f"The value of {asset.description or 'an asset'} is an estimate",
                    action="Confirm the value with the holder or a valuer before filing.",
                    source_entity=ref,
                )
            )
    return gaps


def _estate_fact_gaps(estate: Estate) -> list[FormGap]:
    ref = f"estate:{estate.id}"
    checks = (
        (estate.gifts_with_reservation, "whether there were gifts with reservation of benefit"),
        (estate.foreign_assets_value, "the value of any foreign assets"),
        (estate.trust_property_value, "the value of any settled or trust property"),
        (
            estate.specified_transfers_value,
            "the value of transfers in the seven years before death",
        ),
    )
    gaps = [
        FormGap(
            item=f"Unknown fact: {description}",
            action="Establish and record this before the account can be finalised.",
            source_entity=ref,
        )
        for value, description in checks
        if value is None
    ]
    if estate.claims_rnrb is None and not estate.residence_to_descendants_value:
        gaps.append(
            FormGap(
                item="The residence nil rate band claim is not confirmed",
                action="Confirm whether a qualifying residence passes to direct descendants.",
                source_entity=ref,
            )
        )
    return gaps


def _main_form(estate: Estate, snapshot: dict, assessment_ref: str) -> FormDraft:
    inputs = snapshot.get("inputs", {}) or {}
    result = snapshot.get("result", {}) or {}
    estate_ref = f"estate:{estate.id}"

    def entry(field_ref: str, label: str, value: object, source: str) -> FormFieldEntry:
        return FormFieldEntry(
            field_ref=field_ref, label=label, value=str(value), source_entity=source
        )

    sections = [
        entry("IHT400.estate_name", "Estate", estate.name, estate_ref),
        entry(
            "IHT400.date_of_death",
            "Date of death",
            estate.date_of_death or "not recorded",
            estate_ref,
        ),
    ]
    for field_ref, label, key in (
        ("IHT400.gross_value", "Gross value of the estate", "gross_value"),
        ("IHT400.net_value", "Net value of the estate", "net_value"),
        ("IHT400.exempt_transfers", "Exemptions and reliefs deducted", "exempt_transfers"),
    ):
        if inputs.get(key) is not None:
            sections.append(entry(field_ref, label, inputs[key], assessment_ref))
    for field_ref, label, key in (
        ("IHT400.nrb", "Nil rate band (including transferred band)", "nrb"),
        ("IHT400.rnrb", "Residence nil rate band applied", "rnrb"),
        ("IHT400.allowance", "Total allowance", "allowance"),
        ("IHT400.taxable", "Amount chargeable to tax", "taxable"),
        ("IHT400.rate", "Rate of tax", "rate"),
        ("IHT400.tax", "Inheritance tax", "tax"),
    ):
        if result.get(key) is not None:
            sections.append(entry(field_ref, label, result[key], assessment_ref))
    sections.append(
        entry(
            "IHT400.must_file_iht400",
            "Full IHT400 account required",
            bool(result.get("must_file_iht400")),
            assessment_ref,
        )
    )
    sections.append(
        entry(
            "IHT400.required_schedules",
            "Supplementary schedules required",
            ", ".join(result.get("required_schedules") or []) or "none",
            assessment_ref,
        )
    )
    return FormDraft(form=MAIN_FORM, title=_SCHEDULE_TITLES[MAIN_FORM], sections=sections)


def _schedule_form(
    code: str, estate: Estate, assets: list[Asset], snapshot: dict, assessment_ref: str
) -> FormDraft:
    inputs = snapshot.get("inputs", {}) or {}
    result = snapshot.get("result", {}) or {}
    estate_ref = f"estate:{estate.id}"
    sections: list[FormFieldEntry] = []
    gaps: list[FormGap] = []

    if code == "IHT402":
        sections.append(
            FormFieldEntry(
                field_ref="IHT402.tnrb_pct",
                label="Transferable nil rate band claimed (fraction)",
                value=str(inputs.get("tnrb_pct", estate.tnrb_pct)),
                source_entity=estate_ref,
            )
        )
    elif code == "IHT435":
        sections.append(
            FormFieldEntry(
                field_ref="IHT435.residence_value",
                label="Value of the residence passing to direct descendants",
                value=str(
                    inputs.get(
                        "residence_to_descendants_value",
                        estate.residence_to_descendants_value,
                    )
                ),
                source_entity=estate_ref,
            )
        )
        if result.get("rnrb") is not None:
            sections.append(
                FormFieldEntry(
                    field_ref="IHT435.rnrb",
                    label="Residence nil rate band due",
                    value=str(result["rnrb"]),
                    source_entity=assessment_ref,
                )
            )
    elif code == "IHT436":
        sections.append(
            FormFieldEntry(
                field_ref="IHT436.trnrb_pct",
                label="Transferable residence nil rate band claimed (fraction)",
                value=str(inputs.get("trnrb_pct", estate.trnrb_pct)),
                source_entity=estate_ref,
            )
        )
    elif code == "IHT403" and estate.specified_transfers_value is not None:
        sections.append(
            FormFieldEntry(
                field_ref="IHT403.transfers_seven_years",
                label="Transfers in the seven years before death",
                value=str(estate.specified_transfers_value),
                source_entity=estate_ref,
            )
        )

    schedule_assets = [asset for asset in assets if _schedule_for_asset(asset) == code]
    for position, asset in enumerate(schedule_assets, start=1):
        sections.append(
            FormFieldEntry(
                field_ref=f"{code}.item_{position}",
                label=asset.description or f"{asset.category} asset",
                value=str(asset.dod_value) if asset.dod_value is not None else "value missing",
                source_entity=f"asset:{asset.id}",
            )
        )
    if not sections:
        gaps.append(
            FormGap(
                item=f"No register entries were found for schedule {code}",
                action="Record the relevant assets or claims before completing this schedule.",
                source_entity=estate_ref,
            )
        )
    return FormDraft(
        form=code, title=_SCHEDULE_TITLES.get(code, code), sections=sections, gaps=gaps
    )


def build_form_drafts(
    estate: Estate,
    assets: list[Asset],
    snapshot: dict,
    assessment_ref: str,
    form_code: str | None = None,
) -> list[FormDraft]:
    """Deterministically map estate data to the requested form drafts.

    Default: the IHT400 main form plus every schedule in the latest
    assessment's required_schedules. Gap items land on the form they
    belong to; register-wide gaps land on the main form.
    """
    result = snapshot.get("result", {}) or {}
    required = list(result.get("required_schedules") or [])
    codes = [MAIN_FORM, *required]
    if form_code:
        wanted = form_code.strip().upper()
        codes = [code for code in codes if code == wanted] or [wanted]

    forms: list[FormDraft] = []
    for code in codes:
        if code == MAIN_FORM:
            draft = _main_form(estate, snapshot, assessment_ref)
            draft.gaps = [*_asset_gaps(assets), *_estate_fact_gaps(estate)]
        else:
            draft = _schedule_form(code, estate, assets, snapshot, assessment_ref)
        forms.append(draft)
    return forms


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def _map_fields_node(ctx: AgentContext, state: FormsDraftState) -> dict:
    estate = await tools.read_estate(ctx)
    if estate is None:
        return {"error": "Estate not found."}
    row = await tools.read_latest_assessment(ctx)
    if row is None:
        return {"error": "No IHT assessment snapshot exists yet; run a recompute first."}
    assets = await tools.read_assets(ctx)
    forms = build_form_drafts(
        estate,
        assets,
        row.snapshot or {},
        f"iht_assessment:{row.id}",
        form_code=state.form_code,
    )
    return {"forms": forms, "constants_version": row.constants_version or ""}


async def _narrative_node(ctx: AgentContext, state: FormsDraftState) -> dict:
    """Optional LLM cover note. Receives NO figures: form names and gap
    text only, so it cannot state a number that matters."""
    if not llm.llm_enabled(ctx.settings):
        return {"narrative": None}
    form_names = ", ".join(f"{form.form} ({form.title})" for form in state.forms)
    gap_lines = [gap.item for form in state.forms for gap in form.gaps]
    gap_block = "\n".join(f"- {line}" for line in gap_lines) or "- none recorded"
    user_prompt = (
        f"Forms drafted: {form_names}\n\nOutstanding gaps:\n{gap_block}\n\n"
        "Write the cover note."
    )
    return {"narrative": llm.call_llm(NARRATIVE_SYSTEM_PROMPT, user_prompt, ctx.settings)}


async def _store_draft_node(ctx: AgentContext, state: FormsDraftState) -> dict:
    payload = {
        "forms": [form.model_dump(mode="json") for form in state.forms],
        "narrative": state.narrative,
        "constants_version": state.constants_version,
    }
    title = (
        f"{state.form_code.strip().upper()} draft" if state.form_code else "IHT400 pack draft"
    )
    document = await tools.store_draft_document(
        ctx, title=title, payload=payload, draft_kind=DRAFT_KIND
    )
    approval = await tools.create_pending_approval(
        ctx, entity_ref=f"document:{document.id}", draft_kind=DRAFT_KIND
    )
    return {"document_id": str(document.id), "approval_id": str(approval.id)}


def _finalise_node(state: FormsDraftState) -> dict:
    """Post-interrupt no-op: a person approves before the draft is final."""
    return {}


def _route_after_map(state: FormsDraftState) -> str:
    return END if state.error else "narrative"


def build_graph(ctx: AgentContext):
    """Compile with the explicit interrupt before the draft is finalised."""
    graph = StateGraph(FormsDraftState)
    graph.add_node("map_fields", partial(_map_fields_node, ctx))
    graph.add_node("narrative", partial(_narrative_node, ctx))
    graph.add_node("store_draft", partial(_store_draft_node, ctx))
    graph.add_node(FINALISE_NODE, _finalise_node)
    graph.set_entry_point("map_fields")
    graph.add_conditional_edges("map_fields", _route_after_map)
    graph.add_edge("narrative", "store_draft")
    graph.add_edge("store_draft", FINALISE_NODE)
    graph.add_edge(FINALISE_NODE, END)
    return graph.compile(checkpointer=MemorySaver(), interrupt_before=[FINALISE_NODE])


async def run_forms_draft(ctx: AgentContext, form_code: str | None = None) -> FormsDraftState:
    """Run to the human-review interrupt and return the drafted state."""
    app = build_graph(ctx)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = await app.ainvoke(FormsDraftState(form_code=form_code).model_dump(), config)
    return FormsDraftState.model_validate(result)
