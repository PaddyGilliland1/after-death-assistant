"""Pydantic schemas for the P3 agent layer (contract section 9).

Everything an agent exchanges with the API layer or stores as a draft
payload is validated here (Cardinal Rule 5). Draft payloads are stored
as JSON in the documents vault; the same models parse them back when a
pending draft is approved, so nothing untyped crosses the boundary.

Figures never originate here: every numeric value in these models is a
verbatim copy of stored register data or of the deterministic engine's
assessment snapshot.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

DRAFT_STATUS_PENDING = "pending_approval"


# ---------------------------------------------------------------------------
# forms_draft
# ---------------------------------------------------------------------------


class FormFieldEntry(BaseModel):
    """One deterministic field entry on a drafted form."""

    field_ref: str = Field(description="Form field reference, e.g. IHT400.net_value")
    label: str
    value: str = Field(description="Verbatim stored or engine value, formatted")
    source_entity: str = Field(description="Provenance, e.g. asset:<uuid>")


class FormGap(BaseModel):
    """A missing or unconfirmed item the executors must resolve."""

    item: str
    action: str = Field(description="What to do to close the gap")
    source_entity: str | None = None


class FormDraft(BaseModel):
    """A drafted form: the main IHT400 or one required schedule."""

    form: str = Field(description="Form code, e.g. IHT400 or IHT405")
    title: str = ""
    sections: list[FormFieldEntry] = Field(default_factory=list)
    gaps: list[FormGap] = Field(default_factory=list)


class FormsDraftPayload(BaseModel):
    """The stored draft payload for a forms_draft run."""

    forms: list[FormDraft] = Field(default_factory=list)
    narrative: str | None = None
    constants_version: str = ""


class DraftFormRequest(BaseModel):
    """POST /agents/draft-form body."""

    form_code: str | None = Field(
        default=None,
        description="Draft only this form; default is IHT400 plus every required schedule",
        max_length=16,
    )


class DraftFormResponse(BaseModel):
    """The drafted forms plus their approval-pending reference."""

    draft_id: uuid.UUID
    approval_id: uuid.UUID
    status: str = DRAFT_STATUS_PENDING
    forms: list[FormDraft] = Field(default_factory=list)
    narrative: str | None = None
    constants_version: str = ""


# ---------------------------------------------------------------------------
# iht_narration
# ---------------------------------------------------------------------------


class NarrationCitation(BaseModel):
    """A source the narration cites, with provenance."""

    title: str
    source_url: str | None = None
    fetch_date: dt.date | None = None
    form_code: str | None = None


class NarrationResponse(BaseModel):
    """A drafted plain-English assessment breakdown, pending approval."""

    draft_id: uuid.UUID
    approval_id: uuid.UUID
    status: str = DRAFT_STATUS_PENDING
    narration: str
    citations: list[NarrationCitation] = Field(default_factory=list)
    constants_version: str
    validated: bool = Field(
        description="Whether every figure in the narration exists in the snapshot"
    )


# ---------------------------------------------------------------------------
# draft-letter
# ---------------------------------------------------------------------------


class DraftLetterRequest(BaseModel):
    """POST /agents/draft-letter body."""

    contact_id: uuid.UUID
    purpose: str = Field(
        min_length=3,
        max_length=500,
        description="What the letter is for, e.g. notify of the death",
    )


class DraftLetterResponse(BaseModel):
    """A drafted notification letter, pending approval. Never sent by code."""

    draft_id: uuid.UUID
    approval_id: uuid.UUID
    status: str = DRAFT_STATUS_PENDING
    letter_text: str
    contact_id: uuid.UUID
    contact_name: str
    references: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# next_actions
# ---------------------------------------------------------------------------


class TaskSuggestion(BaseModel):
    """One proposed task. It becomes a real task only on approval."""

    title: str
    description: str = ""
    due_date: dt.date | None = None
    priority: str | None = None
    depends_on: list[int] = Field(
        default_factory=list,
        description="Indices of other suggestions in this batch this one depends on",
    )
    source_ref: str | None = Field(
        default=None, description="What prompted the suggestion, e.g. contact:<uuid>"
    )


class TaskSuggestionsPayload(BaseModel):
    """The stored draft payload for a next_actions run."""

    suggestions: list[TaskSuggestion] = Field(default_factory=list)


class SuggestTasksResponse(BaseModel):
    """Proposed tasks plus their approval-pending reference."""

    draft_id: uuid.UUID
    approval_id: uuid.UUID
    status: str = DRAFT_STATUS_PENDING
    suggestions: list[TaskSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Approvals and the pending-drafts listing
# ---------------------------------------------------------------------------


class ApproveDraftRequest(BaseModel):
    """POST /agents/drafts/{approval_id}/approve body."""

    accepted: list[int] | None = Field(
        default=None,
        description=(
            "For task suggestions: indices of the accepted suggestions; "
            "None accepts all of them"
        ),
    )


class ApproveDraftResponse(BaseModel):
    """The completed approval and anything it materialised."""

    approval_id: uuid.UUID
    entity_ref: str
    draft_kind: str
    approved_by: str
    approved_at: dt.datetime
    created_task_ids: list[uuid.UUID] = Field(default_factory=list)


class PendingDraftOut(BaseModel):
    """One draft awaiting human approval."""

    model_config = ConfigDict(from_attributes=True)

    approval_id: uuid.UUID
    entity_ref: str
    draft_kind: str
    draft_id: uuid.UUID | None = None
    title: str | None = None
    created_at: dt.datetime
    created_by: str = ""
