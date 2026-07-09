"""Contacts CRM router: CRUD, the notification tracker and interactions.

Estate-scoped, soft delete via DELETE (archived_at/archive_reason), every
write emits an audit_event, and the viewer role is read-only (enforced by
require_write). Contact interactions flagged executor_private are never
returned to the viewer role.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, Role, WriteUser
from app.db import get_session
from app.models import AuditEvent, Contact, ContactInteraction, Estate
from app.models.base import utcnow
from app.models.enums import ContactCategory
from app.schemas.people import (
    ContactCreate,
    ContactInteractionCreate,
    ContactInteractionRead,
    ContactRead,
    ContactUpdate,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _snapshot(row: Contact) -> dict:
    return ContactRead.model_validate(row).model_dump(mode="json")


def _audit(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            estate_id=estate_id,
            actor=actor,
            action=action,
            entity=entity,
            before=before,
            after=after,
            created_by=actor,
        )
    )


async def _ensure_estate(session: AsyncSession, estate_id: uuid.UUID) -> None:
    estate = await session.get(Estate, estate_id)
    if estate is None or estate.archived_at is not None:
        raise HTTPException(status_code=404, detail="Estate not found.")


async def _get_contact_or_404(session: AsyncSession, contact_id: uuid.UUID) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return contact


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    user: WriteUser,
    session: SessionDep,
) -> Contact:
    """Create a contact."""
    await _ensure_estate(session, payload.estate_id)
    contact = Contact(**payload.model_dump(), created_by=user.email)
    session.add(contact)
    await session.flush()
    _audit(
        session,
        contact.estate_id,
        user.email,
        "create",
        f"contact:{contact.id}",
        after=_snapshot(contact),
    )
    await session.commit()
    await session.refresh(contact)
    return contact


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    user: ReadUser,
    session: SessionDep,
    estate_id: uuid.UUID | None = None,
    category: ContactCategory | None = None,
    notify_required: bool | None = None,
    notification_status: str | None = None,
    include_archived: bool = False,
) -> list[Contact]:
    """List contacts. notify_required and notification_status together give
    the notification chase list (who still needs telling)."""
    stmt = select(Contact).order_by(Contact.created_at)
    if not include_archived:
        stmt = stmt.where(Contact.archived_at.is_(None))
    if estate_id is not None:
        stmt = stmt.where(Contact.estate_id == estate_id)
    if category is not None:
        stmt = stmt.where(Contact.category == category)
    if notify_required is not None:
        stmt = stmt.where(Contact.notify_required == notify_required)
    if notification_status is not None:
        stmt = stmt.where(Contact.notification_status == notification_status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> Contact:
    """Fetch a single contact."""
    return await _get_contact_or_404(session, contact_id)


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    user: WriteUser,
    session: SessionDep,
) -> Contact:
    """Partially update a contact, including the notification tracker fields
    (notification_status, notified_date, notified_method)."""
    contact = await _get_contact_or_404(session, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return contact
    before = _snapshot(contact)
    for field, value in changes.items():
        setattr(contact, field, value)
    contact.updated_at = utcnow()
    session.add(contact)
    await session.flush()
    _audit(
        session,
        contact.estate_id,
        user.email,
        "update",
        f"contact:{contact.id}",
        before=before,
        after=_snapshot(contact),
    )
    await session.commit()
    await session.refresh(contact)
    return contact


@router.delete("/{contact_id}", response_model=ContactRead)
async def archive_contact(
    contact_id: uuid.UUID,
    user: WriteUser,
    session: SessionDep,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> Contact:
    """Soft delete: archive the contact. Nothing is physically deleted."""
    contact = await _get_contact_or_404(session, contact_id)
    if contact.archived_at is not None:
        raise HTTPException(status_code=409, detail="Contact is already archived.")
    before = _snapshot(contact)
    contact.archived_at = utcnow()
    contact.archive_reason = reason
    contact.updated_at = utcnow()
    session.add(contact)
    await session.flush()
    _audit(
        session,
        contact.estate_id,
        user.email,
        "archive",
        f"contact:{contact.id}",
        before=before,
        after=_snapshot(contact),
    )
    await session.commit()
    await session.refresh(contact)
    return contact


@router.post(
    "/{contact_id}/interactions",
    response_model=ContactInteractionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_interaction(
    contact_id: uuid.UUID,
    payload: ContactInteractionCreate,
    user: WriteUser,
    session: SessionDep,
) -> ContactInteraction:
    """Log an interaction (call, letter, email) with a contact."""
    contact = await _get_contact_or_404(session, contact_id)
    interaction = ContactInteraction(
        **payload.model_dump(),
        estate_id=contact.estate_id,
        contact_id=contact.id,
        by_user=user.email,
        created_by=user.email,
    )
    session.add(interaction)
    await session.flush()
    _audit(
        session,
        contact.estate_id,
        user.email,
        "create",
        f"contact_interaction:{interaction.id}",
        after=ContactInteractionRead.model_validate(interaction).model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(interaction)
    return interaction


@router.get("/{contact_id}/interactions", response_model=list[ContactInteractionRead])
async def list_interactions(
    contact_id: uuid.UUID,
    user: ReadUser,
    session: SessionDep,
) -> list[ContactInteraction]:
    """List interactions for a contact. Rows flagged executor_private are
    excluded when the caller has the viewer role."""
    await _get_contact_or_404(session, contact_id)
    stmt = (
        select(ContactInteraction)
        .where(
            ContactInteraction.contact_id == contact_id,
            ContactInteraction.archived_at.is_(None),
        )
        .order_by(ContactInteraction.date, ContactInteraction.created_at)
    )
    if user.role == Role.VIEWER:
        stmt = stmt.where(ContactInteraction.executor_private.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())
