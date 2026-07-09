"""Pydantic schemas for the P3 PDF export layer.

Exports only ever create local document rows (build contract guardrail 1:
no automated filing or sending; a person approves, a person submits).
These schemas validate everything that crosses the export boundary
(Cardinal Rule 5).

The forms-draft payload shape is NOT defined here: the agent layer owns
it (app.schemas.agents.FormsDraftPayload, stored by the forms_draft graph
as a document of type "draft" whose JSON is ``{"draft_kind", "payload"}``)
and the exports router reuses it directly, so the two layers cannot
drift.

Letter drafts: the agent draft-letter graph has not landed a stored
payload model yet, so the convention of record is: a letter draft is a
document whose file bytes are one of
- the agent envelope ``{"draft_kind": ..., "payload": {...}}`` where the
  payload carries ``letter_text`` (and optionally ``contact_name``), or
- a JSON object matching ``LetterDraft`` below, or
- plain text, used as the letter body with the document title as subject.
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LetterDraft(BaseModel):
    """An approved notification letter, rendered on plain letterhead."""

    model_config = ConfigDict(extra="forbid")

    recipient_name: str = Field(default="")
    recipient_address: list[str] = Field(
        default_factory=list, description="Address lines, one list entry per line"
    )
    date: dt.date | None = Field(
        default=None, description="Letter date; defaults to the generation date"
    )
    subject: str = Field(default="")
    body: str = Field(
        default="", description="Letter body; blank lines separate paragraphs"
    )
    sender_name: str = Field(default="")
    sender_role: str = Field(
        default="", description="e.g. Executor of the estate"
    )


class BeneficiaryLine(BaseModel):
    """A beneficiary's legacy as recorded in the register, for display only.

    Every figure comes from the beneficiary_legacy row; the renderer lays
    it out and never computes.
    """

    model_config = ConfigDict(extra="forbid")

    beneficiary_id: str
    name: str = Field(default="")
    legacy_type: str | None = Field(default=None)
    amount_or_share: Decimal | None = Field(
        default=None,
        description="Money amount (pecuniary/specific) or residue fraction (residuary)",
    )
    exempt_or_chargeable: str | None = Field(default=None)
    status: str | None = Field(default=None)
