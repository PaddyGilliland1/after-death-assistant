"""Agent drafts router (P3, contract section 9).

Every endpoint is write-role (the viewer role can invoke NO agent
endpoint), every write is audited with its estate scope, and every draft
is returned together with its approval-pending reference. Nothing here
sends, files or pays: drafts stay in the system until a person approves
them, and a person acts outside the system.

- POST /agents/draft-form       deterministic IHT400 + schedules field
                                mapping (works without an API key; the
                                optional cover narrative is then omitted)
- POST /agents/draft-narration  plain-English cited breakdown of the
                                latest engine snapshot (LLM, 503 without key)
- POST /agents/draft-letter     notification letter draft for a contact
                                (LLM, 503 without key)
- POST /agents/suggest-tasks    deterministic task suggestions
- POST /agents/drafts/{id}/approve  complete the pending approval row;
                                for task suggestions this materialises
                                the accepted tasks
- GET  /agents/drafts           pending (unapproved) drafts
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm, tools
from app.agents.graphs import forms_draft as forms_draft_graph
from app.agents.graphs import iht_narration as iht_narration_graph
from app.agents.graphs import next_actions as next_actions_graph
from app.agents.tools import AgentContext
from app.core.auth import AuthenticatedUser, WriteUser
from app.core.config import get_settings
from app.db import get_session
from app.models import Approval, Document, Estate, Task
from app.models.base import utcnow
from app.schemas.agents import (
    ApproveDraftRequest,
    ApproveDraftResponse,
    DraftFormRequest,
    DraftFormResponse,
    DraftLetterRequest,
    DraftLetterResponse,
    FormDraft,
    NarrationCitation,
    NarrationResponse,
    PendingDraftOut,
    SuggestTasksResponse,
    TaskSuggestion,
    TaskSuggestionsPayload,
)
from app.services.seeding import get_active_estate, record_audit

router = APIRouter(prefix="/agents", tags=["agents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

LETTER_DRAFT_KIND = "notification_letter"

LETTER_SYSTEM_PROMPT = """You draft a notification letter for the executors of \
an estate in England and Wales to send to an institution. Rules:
1. Use ONLY the stored details supplied: the contact's name and address, the \
account or policy references, and the estate references. Copy references \
verbatim.
2. State NO monetary figures of any kind: the letter ASKS the institution for \
the balances or valuations at the date of death, it never asserts them.
3. Ask the institution to confirm the date of death balance for each reference, \
freeze the accounts as appropriate, and say what they require next.
4. Head the letter clearly as a DRAFT prepared for executor review; it is not \
sent by this system.
5. Write in UK English. Do not use em dashes. No placeholders for data you were \
given; use square-bracket placeholders only for the sender's signature block."""


async def _require_estate(session: AsyncSession) -> Estate:
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No estate is configured yet. Seed one first.",
        )
    return estate


def _context(session: AsyncSession, estate: Estate, user: AuthenticatedUser) -> AgentContext:
    return AgentContext(
        session=session, estate_id=estate.id, actor=user.email, settings=get_settings()
    )


def _require_llm() -> None:
    if not llm.llm_enabled(get_settings()):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "This agent needs a language model and ANTHROPIC_API_KEY is not "
            "configured. Deterministic drafting (draft-form, suggest-tasks) "
            "remains available.",
        )


# ---------------------------------------------------------------------------
# Drafting endpoints
# ---------------------------------------------------------------------------


@router.post("/draft-form", response_model=DraftFormResponse)
async def draft_form(
    payload: DraftFormRequest, user: WriteUser, session: SessionDep
) -> DraftFormResponse:
    """Deterministically draft the IHT400 pack (or one form) for approval."""
    estate = await _require_estate(session)
    ctx = _context(session, estate, user)
    state = await forms_draft_graph.run_forms_draft(ctx, form_code=payload.form_code)
    if state.error:
        raise HTTPException(status.HTTP_409_CONFLICT, state.error)
    await record_audit(
        session,
        estate.id,
        user.email,
        "agent_draft",
        f"document:{state.document_id}",
        after={
            "draft_kind": forms_draft_graph.DRAFT_KIND,
            "approval_id": state.approval_id,
            "forms": [form.form for form in state.forms],
        },
    )
    await session.commit()
    return DraftFormResponse(
        draft_id=uuid.UUID(state.document_id),
        approval_id=uuid.UUID(state.approval_id),
        forms=state.forms,
        narrative=state.narrative,
        constants_version=state.constants_version,
    )


@router.post("/draft-narration", response_model=NarrationResponse)
async def draft_narration(user: WriteUser, session: SessionDep) -> NarrationResponse:
    """Draft the plain-English, cited breakdown of the latest assessment."""
    _require_llm()
    estate = await _require_estate(session)
    ctx = _context(session, estate, user)
    state = await iht_narration_graph.run_iht_narration(ctx)
    if state.error:
        raise HTTPException(status.HTTP_409_CONFLICT, state.error)
    await record_audit(
        session,
        estate.id,
        user.email,
        "agent_draft",
        f"document:{state.document_id}",
        after={
            "draft_kind": "iht_narration",
            "approval_id": state.approval_id,
            "validated": state.validated,
            "constants_version": state.constants_version,
        },
    )
    await session.commit()
    return NarrationResponse(
        draft_id=uuid.UUID(state.document_id),
        approval_id=uuid.UUID(state.approval_id),
        narration=state.narration,
        citations=state.citations,
        constants_version=state.constants_version,
        validated=state.validated,
    )


@router.post("/draft-letter", response_model=DraftLetterResponse)
async def draft_letter(
    payload: DraftLetterRequest, user: WriteUser, session: SessionDep
) -> DraftLetterResponse:
    """Draft a notification letter to a stored contact, for approval.

    The letter is composed FROM stored data only: the contact's details
    and the account references held with them. It contains no figures;
    it asks the institution for the date of death balances. It is a
    draft; nothing is sent by the system.
    """
    _require_llm()
    estate = await _require_estate(session)
    ctx = _context(session, estate, user)

    contact = await tools.read_contact(ctx, payload.contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found.")

    references = list(contact.references or [])
    for asset in await tools.read_assets(ctx):
        if asset.holder_contact_id == contact.id and asset.account_reference:
            if asset.account_reference not in references:
                references.append(asset.account_reference)

    details = [
        f"Contact: {contact.name}" + (f" ({contact.org})" if contact.org else ""),
        f"Contact address: {contact.address or 'not recorded'}",
        f"What they hold or handle: {contact.holds_or_handles or 'not recorded'}",
        f"Account or policy references: {', '.join(references) or 'none recorded'}",
        f"Estate: {estate.name}",
        f"Date of death: {estate.date_of_death or 'not recorded'}",
        f"Purpose: {payload.purpose}",
    ]
    letter_text = llm.call_llm(
        LETTER_SYSTEM_PROMPT, "\n".join(details), ctx.settings
    )

    document = await tools.store_draft_document(
        ctx,
        title=f"Notification letter to {contact.name} (draft)",
        payload={
            "letter_text": letter_text,
            "contact_id": str(contact.id),
            "purpose": payload.purpose,
            "references": references,
        },
        draft_kind=LETTER_DRAFT_KIND,
    )
    approval = await tools.create_pending_approval(
        ctx, entity_ref=f"document:{document.id}", draft_kind=LETTER_DRAFT_KIND
    )
    await record_audit(
        session,
        estate.id,
        user.email,
        "agent_draft",
        f"document:{document.id}",
        after={
            "draft_kind": LETTER_DRAFT_KIND,
            "approval_id": str(approval.id),
            "contact_id": str(contact.id),
        },
    )
    await session.commit()
    return DraftLetterResponse(
        draft_id=document.id,
        approval_id=approval.id,
        letter_text=letter_text,
        contact_id=contact.id,
        contact_name=contact.name,
        references=references,
    )


@router.post("/suggest-tasks", response_model=SuggestTasksResponse)
async def suggest_tasks(user: WriteUser, session: SessionDep) -> SuggestTasksResponse:
    """Propose tasks from process state. Accepted suggestions become tasks
    only through the approval endpoint."""
    estate = await _require_estate(session)
    ctx = _context(session, estate, user)
    state = await next_actions_graph.run_next_actions(ctx)
    await record_audit(
        session,
        estate.id,
        user.email,
        "agent_draft",
        f"document:{state.document_id}",
        after={
            "draft_kind": next_actions_graph.DRAFT_KIND,
            "approval_id": state.approval_id,
            "suggestion_count": len(state.suggestions),
        },
    )
    await session.commit()
    return SuggestTasksResponse(
        draft_id=uuid.UUID(state.document_id),
        approval_id=uuid.UUID(state.approval_id),
        suggestions=state.suggestions,
    )


# ---------------------------------------------------------------------------
# Approval and listing
# ---------------------------------------------------------------------------


async def _materialise_tasks(
    ctx: AgentContext,
    document: Document,
    accepted: list[int] | None,
) -> list[Task]:
    """Create the accepted suggestions as real tasks with dependencies."""
    try:
        payload = TaskSuggestionsPayload.model_validate(tools.read_draft_payload(ctx, document))
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Stored suggestion payload is invalid: {exc}"
        ) from exc

    suggestions = payload.suggestions
    indices = list(range(len(suggestions))) if accepted is None else sorted(set(accepted))
    if any(index < 0 or index >= len(suggestions) for index in indices):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "An accepted index does not exist in the suggestion batch.",
        )

    created: dict[int, Task] = {}
    for index in indices:
        suggestion: TaskSuggestion = suggestions[index]
        task = Task(
            estate_id=ctx.estate_id,
            title=suggestion.title,
            description=suggestion.description or None,
            status="not_started",
            priority=suggestion.priority,
            due_date=suggestion.due_date,
            source=next_actions_graph.TASK_SOURCE,
            created_by=ctx.actor,
        )
        ctx.session.add(task)
        created[index] = task
    await ctx.session.flush()

    # Wire dependencies between tasks accepted in the same batch.
    for index, task in created.items():
        blockers = [
            created[dep] for dep in suggestions[index].depends_on if dep in created
        ]
        if blockers:
            task.blocked_by = [str(blocker.id) for blocker in blockers]
            for blocker in blockers:
                blocker.blocks = [*blocker.blocks, str(task.id)]
    await ctx.session.flush()
    return list(created.values())


@router.post("/drafts/{approval_id}/approve", response_model=ApproveDraftResponse)
async def approve_draft(
    approval_id: uuid.UUID,
    payload: ApproveDraftRequest,
    user: WriteUser,
    session: SessionDep,
) -> ApproveDraftResponse:
    """Complete the pending approval row: record who approved and when.

    For task suggestions, the accepted suggestions are materialised as
    tasks (source "agent_suggested") in the same transaction.
    """
    estate = await _require_estate(session)
    approval = await session.get(Approval, approval_id)
    if approval is None or approval.estate_id != estate.id or approval.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pending draft not found.")
    if approval.approved_by:
        raise HTTPException(status.HTTP_409_CONFLICT, "This draft is already approved.")

    ctx = _context(session, estate, user)
    created_tasks: list[Task] = []
    if approval.draft_kind == next_actions_graph.DRAFT_KIND:
        document_id = approval.entity_ref.removeprefix("document:")
        document = await session.get(Document, uuid.UUID(document_id))
        if document is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "The draft document behind this approval is missing."
            )
        created_tasks = await _materialise_tasks(ctx, document, payload.accepted)

    approval.approved_by = user.email
    approval.approved_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        estate.id,
        user.email,
        "approve",
        approval.entity_ref,
        after={
            "draft_kind": approval.draft_kind,
            "approval_id": str(approval.id),
            "created_task_ids": [str(task.id) for task in created_tasks],
        },
    )
    await session.commit()
    return ApproveDraftResponse(
        approval_id=approval.id,
        entity_ref=approval.entity_ref,
        draft_kind=approval.draft_kind,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        created_task_ids=[task.id for task in created_tasks],
    )


@router.get("/drafts", response_model=list[PendingDraftOut])
async def list_pending_drafts(user: WriteUser, session: SessionDep) -> list[PendingDraftOut]:
    """Drafts awaiting approval (viewer role cannot see agent drafts)."""
    estate = await _require_estate(session)
    result = await session.execute(
        select(Approval)
        .where(
            Approval.estate_id == estate.id,
            Approval.archived_at.is_(None),
            Approval.approved_by.is_(None),
        )
        .order_by(Approval.created_at.desc())
    )
    approvals = list(result.scalars().all())

    documents: dict[uuid.UUID, Document] = {}
    doc_ids = []
    for approval in approvals:
        if approval.entity_ref.startswith("document:"):
            doc_ids.append(uuid.UUID(approval.entity_ref.removeprefix("document:")))
    if doc_ids:
        rows = await session.execute(select(Document).where(Document.id.in_(doc_ids)))
        documents = {doc.id: doc for doc in rows.scalars().all()}

    out: list[PendingDraftOut] = []
    for approval in approvals:
        doc_id = (
            uuid.UUID(approval.entity_ref.removeprefix("document:"))
            if approval.entity_ref.startswith("document:")
            else None
        )
        document = documents.get(doc_id) if doc_id else None
        out.append(
            PendingDraftOut(
                approval_id=approval.id,
                entity_ref=approval.entity_ref,
                draft_kind=approval.draft_kind,
                draft_id=doc_id,
                title=document.title if document else None,
                created_at=approval.created_at,
                created_by=approval.created_by,
            )
        )
    return out


# Re-exported for typing clarity in tests.
__all__ = ["router", "FormDraft", "NarrationCitation"]
