"""Exports API: render estate paperwork to PDF and store it locally.

Guardrail 1 (no automated filing or sending): every endpoint here ONLY
creates a local document row (type "export") holding the rendered PDF.
Nothing is filed with HMRC, emailed, posted or paid by code; a person
downloads the export through the documents module and acts on it.

Endpoints (write roles only; the viewer role reads previously generated
exports through GET /documents, which is viewer-safe):

- POST /exports/estate-accounts   the trial balance, legacies and
                                  distributions, assembled exactly as
                                  GET /estate/accounts assembles them
                                  (the estate router's function is reused,
                                  not duplicated)
- POST /exports/iht-draft         a completed-form DRAFT from the LATEST
                                  APPROVED forms_draft (the agent layer
                                  stores drafts as documents of type
                                  "draft" wrapping {"draft_kind",
                                  "payload"} with an Approval row of kind
                                  "iht400_draft"); a payload may also be
                                  supplied in the request body as the
                                  documented fallback, e.g. before any
                                  agent draft exists
- POST /exports/clearance-draft   an IHT30 clearance application DRAFT
                                  content sheet from the estate settings
                                  and the latest IHT assessment snapshot
- POST /exports/letter/{draft_id} an APPROVED notification letter draft
                                  (a document whose file is LetterDraft
                                  JSON or plain text); exporting an
                                  unapproved draft returns 409

Every export emits an audit event. Every figure in a PDF comes from the
registers or a stored engine snapshot; the renderer only lays it out.
"""

import datetime as dt
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.estate import estate_accounts as assemble_estate_accounts
from app.api.estate import get_estate_or_404
from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import Approval, BeneficiaryLegacy, Contact, Document
from app.schemas.agents import FormsDraftPayload
from app.schemas.collab import DocumentOut
from app.schemas.estate import EstateSettingsRead
from app.schemas.exports import BeneficiaryLine, LetterDraft
from app.schemas.iht import IhtAssessmentRead
from app.services.pdf_render import (
    render_clearance_draft,
    render_estate_accounts,
    render_iht_draft,
    render_letter,
)
from app.services.reevaluation import latest_assessment
from app.services.seeding import record_audit
from app.services.storage import StorageError, get_storage

router = APIRouter(prefix="/exports", tags=["exports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

EXPORT_DOC_TYPE = "export"


async def _store_export(
    session: AsyncSession,
    *,
    estate_id: uuid.UUID,
    actor: str,
    pdf_bytes: bytes,
    title: str,
    kind: str,
    links: list[dict] | None = None,
) -> Document:
    """Store the PDF locally, create the document row and audit it.

    This is the whole side effect of an export: a local document row
    (guardrail 1: nothing is sent anywhere).
    """
    file_key = get_storage().save(pdf_bytes, suffix=".pdf")
    document = Document(
        estate_id=estate_id,
        title=title,
        type=EXPORT_DOC_TYPE,
        file_key=file_key,
        mime="application/pdf",
        version=1,
        access_roles=[],
        links=links or [],
        created_by=actor,
    )
    session.add(document)
    await session.flush()
    await record_audit(
        session,
        estate_id,
        actor,
        "create",
        f"document:{document.id}",
        after={"title": title, "type": EXPORT_DOC_TYPE, "export_kind": kind},
    )
    await session.commit()
    return document


def _dated_title(stem: str) -> str:
    return f"{stem} {dt.date.today().isoformat()}"


@router.post(
    "/estate-accounts",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Render the estate accounts to PDF and store it as a local document "
        "row. Nothing is filed or sent (guardrail 1)."
    ),
)
async def export_estate_accounts(session: SessionDep, user: WriteUser) -> Document:
    """Export the estate accounts as a branded draft PDF.

    The accounts are assembled exactly as GET /estate/accounts assembles
    them, by calling the estate router's function (no duplicated
    assembly). Beneficiary names come from the contact register.
    """
    estate = await get_estate_or_404(session)
    accounts = await assemble_estate_accounts(session=session, user=user)

    result = await session.execute(
        select(BeneficiaryLegacy, Contact)
        .join(Contact, BeneficiaryLegacy.beneficiary_contact_id == Contact.id)  # type: ignore[arg-type]
        .where(
            BeneficiaryLegacy.estate_id == estate.id,
            BeneficiaryLegacy.archived_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(BeneficiaryLegacy.created_at)  # type: ignore[arg-type]
    )
    beneficiaries = [
        BeneficiaryLine(
            beneficiary_id=str(legacy.beneficiary_contact_id),
            name=contact.name,
            legacy_type=legacy.legacy_type.value if legacy.legacy_type else None,
            amount_or_share=legacy.amount_or_share,
            exempt_or_chargeable=legacy.exempt_or_chargeable,
            status=legacy.status,
        )
        for legacy, contact in result.all()
    ]

    pdf_bytes = render_estate_accounts(
        accounts,
        beneficiaries,
        estate_name=estate.name or "Estate under administration",
    )
    return await _store_export(
        session,
        estate_id=estate.id,
        actor=user.email,
        pdf_bytes=pdf_bytes,
        title=_dated_title("Estate accounts export"),
        kind="estate_accounts",
    )


IHT_DRAFT_KIND = "iht400_draft"


async def _latest_approved_forms_draft(
    session: AsyncSession, estate_id: uuid.UUID
) -> FormsDraftPayload | None:
    """The latest APPROVED forms_draft payload from the agent draft store.

    Convention (app.agents.tools / app.agents.graphs.forms_draft): the
    draft is a document of type "draft" whose JSON file is
    {"draft_kind": "iht400_draft", "payload": <FormsDraftPayload>}, with
    an Approval row (entity_ref "document:<id>", draft_kind
    "iht400_draft") that a person completes via the approvals flow.
    """
    result = await session.execute(
        select(Approval.entity_ref, Approval.approved_at)
        .where(
            Approval.estate_id == estate_id,
            Approval.draft_kind == IHT_DRAFT_KIND,
            Approval.archived_at.is_(None),  # type: ignore[union-attr]
            Approval.approved_at.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(Approval.approved_at.desc())  # type: ignore[union-attr]
    )
    for entity_ref, _approved_at in result.all():
        prefix, _, raw_id = entity_ref.partition(":")
        if prefix != "document":
            continue
        try:
            document = await session.get(Document, uuid.UUID(raw_id))
        except ValueError:
            continue
        if document is None or document.archived_at is not None or not document.file_key:
            continue
        try:
            envelope = json.loads(get_storage().read(document.file_key))
            return FormsDraftPayload.model_validate(envelope.get("payload", envelope))
        except (StorageError, json.JSONDecodeError, UnicodeDecodeError, ValidationError):
            continue
    return None


@router.post(
    "/iht-draft",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Render a completed-form DRAFT (field references, labels, values "
        "and gaps) to PDF and store it as a local document row. Not the "
        "official HMRC form. Nothing is filed or sent (guardrail 1). "
        "With no request body, the latest APPROVED agent forms draft is "
        "used; a forms_draft payload may be supplied in the body as a "
        "fallback."
    ),
)
async def export_iht_draft(
    session: SessionDep, user: WriteUser, payload: FormsDraftPayload | None = None
) -> Document:
    """Export the latest approved forms_draft as a completed-form DRAFT.

    Source resolution: a payload supplied in the request body wins (the
    documented fallback for callers holding a draft, e.g. before any
    agent draft exists); otherwise the latest approved draft is read from
    the agent draft store (documents of type "draft" with an approved
    Approval row of kind "iht400_draft"). 404 when neither is available.
    """
    estate = await get_estate_or_404(session)
    if payload is None:
        payload = await _latest_approved_forms_draft(session, estate.id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No approved forms draft exists. Run the forms_draft agent "
                "and approve its draft, or supply a forms_draft payload in "
                "the request body."
            ),
        )
    form_codes = ", ".join(form.form for form in payload.forms) or "IHT forms"
    pdf_bytes = render_iht_draft(
        payload, estate_name=estate.name or "Estate under administration"
    )
    return await _store_export(
        session,
        estate_id=estate.id,
        actor=user.email,
        pdf_bytes=pdf_bytes,
        title=_dated_title(f"{form_codes} draft export"),
        kind="iht_draft",
    )


@router.post(
    "/clearance-draft",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Render an IHT30 clearance application DRAFT content sheet to PDF "
        "and store it as a local document row. Nothing is filed or sent "
        "(guardrail 1)."
    ),
)
async def export_clearance_draft(session: SessionDep, user: WriteUser) -> Document:
    """Export the IHT30 clearance DRAFT content sheet.

    Estate facts come from the estate settings; the figures come from the
    latest IHT assessment snapshot (404 if none has been computed yet,
    matching the IHT workbench convention).
    """
    estate = await get_estate_or_404(session)
    latest = await latest_assessment(session, estate.id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No IHT assessment has been computed yet. POST /iht/recompute first.",
        )
    pdf_bytes = render_clearance_draft(
        EstateSettingsRead.model_validate(estate),
        IhtAssessmentRead.from_row(latest),
    )
    return await _store_export(
        session,
        estate_id=estate.id,
        actor=user.email,
        pdf_bytes=pdf_bytes,
        title=_dated_title("IHT30 clearance draft export"),
        kind="clearance_draft",
    )


async def _approved(
    session: AsyncSession, estate_id: uuid.UUID, entity_ref: str
) -> bool:
    """Whether a non-archived approval with an approval timestamp exists."""
    result = await session.execute(
        select(Approval.id)
        .where(
            Approval.estate_id == estate_id,
            Approval.entity_ref == entity_ref,
            Approval.archived_at.is_(None),  # type: ignore[union-attr]
            Approval.approved_at.is_not(None),  # type: ignore[union-attr]
        )
        .limit(1)
    )
    return result.scalars().first() is not None


def _load_letter_draft(document: Document) -> LetterDraft:
    """Read the draft document's stored file as a LetterDraft.

    Convention (documented in app.schemas.exports): the file bytes are
    the agent envelope {"draft_kind", "payload"} with a payload carrying
    letter_text (and optionally contact_name), or LetterDraft JSON, or
    plain text used as the body with the document title as subject.
    """
    if not document.file_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The letter draft document has no stored file to render.",
        )
    try:
        raw = get_storage().read(document.file_key)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The letter draft's stored file is missing.",
        ) from exc
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return LetterDraft(
            subject=document.title, body=raw.decode("utf-8", errors="replace")
        )
    if isinstance(data, dict) and "payload" in data:
        payload = data.get("payload")
        if isinstance(payload, dict):
            if "letter_text" in payload:
                return LetterDraft(
                    recipient_name=str(payload.get("contact_name", "")),
                    subject=document.title,
                    body=str(payload.get("letter_text", "")),
                )
            data = payload
    try:
        return LetterDraft.model_validate(data)
    except ValidationError:
        return LetterDraft(
            subject=document.title, body=raw.decode("utf-8", errors="replace")
        )


@router.post(
    "/letter/{draft_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Render an APPROVED notification letter draft to PDF on plain "
        "letterhead and store it as a local document row. The letter is "
        "never sent by code (guardrail 1); 409 if the draft has not been "
        "approved."
    ),
)
async def export_letter(
    draft_id: uuid.UUID, session: SessionDep, user: WriteUser
) -> Document:
    """Export an approved letter draft (a document row) as a letter PDF.

    The draft must have a recorded approval (POST /approvals with
    entity_ref "document:<draft_id>" and an approval timestamp);
    exporting an unapproved draft returns 409 with a clear message.
    """
    estate = await get_estate_or_404(session)
    draft = await session.get(Document, draft_id)
    if draft is None or draft.archived_at is not None or draft.estate_id != estate.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Letter draft not found."
        )
    if not await _approved(session, estate.id, f"document:{draft_id}"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The letter draft has not been approved. Record a human "
                "approval (POST /approvals with entity_ref "
                f'"document:{draft_id}") before exporting; drafts are '
                "never sent or exported unapproved."
            ),
        )
    letter = _load_letter_draft(draft)
    pdf_bytes = render_letter(
        letter, estate_name=estate.name or "Estate under administration"
    )
    return await _store_export(
        session,
        estate_id=estate.id,
        actor=user.email,
        pdf_bytes=pdf_bytes,
        title=_dated_title("Notification letter export"),
        kind="notification_letter",
        links=[{"kind": "rendered_from", "entity_type": "document", "entity_id": str(draft_id)}],
    )


@router.get(
    "",
    response_model=list[DocumentOut],
    description=(
        "Previously generated exports (document rows of type 'export'), "
        "newest first. Read-only and viewer-safe; the file bytes are "
        "downloaded through GET /documents/{id}/download."
    ),
)
async def list_exports(session: SessionDep, user: ReadUser) -> list[Document]:
    """List previously generated exports for the estate, newest first."""
    estate = await get_estate_or_404(session)
    result = await session.execute(
        select(Document)
        .where(
            Document.estate_id == estate.id,
            Document.type == EXPORT_DOC_TYPE,
            Document.archived_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(Document.created_at.desc())  # type: ignore[arg-type]
    )
    return list(result.scalars().all())
