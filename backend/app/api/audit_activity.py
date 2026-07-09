"""Audit trail, activity feed and cross-entity search.

- GET /audit: full audit events with before/after payloads; admin and
  executor only (never the viewer).
- GET /activity: a summarised recent-events feed (no payloads), newest
  first, paginated; available to every read role.
- GET /search: basic ILIKE search across contacts, assets, tasks,
  documents and costs, returning typed hits. Viewer results respect
  executor_private flags and document access_roles.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, ReadUser, Role, require_role
from app.db import get_session
from app.models import Asset, AuditEvent, Contact, Cost, Document, Task
from app.schemas.collab import ActivityItemOut, AuditEventOut, SearchHit
from app.services.seeding import get_active_estate

router = APIRouter(tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuditUser = Annotated[AuthenticatedUser, Depends(require_role(Role.ADMIN, Role.EXECUTOR))]

_PER_TYPE_LIMIT = 10


async def _estate_id(session: AsyncSession):
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No estate is configured yet. Seed one first.",
        )
    return estate.id


@router.get("/audit", response_model=list[AuditEventOut])
async def list_audit_events(
    user: AuditUser,
    session: SessionDep,
    entity: Annotated[str | None, Query(description="Entity ref filter, prefix match")] = None,
    actor: Annotated[str | None, Query(description="Exact actor email")] = None,
    since: Annotated[dt.datetime | None, Query(description="Events at or after")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEvent]:
    """Full audit events, newest first. Admin and executor only."""
    estate_id = await _estate_id(session)
    query = select(AuditEvent).where(AuditEvent.estate_id == estate_id)
    if entity:
        query = query.where(AuditEvent.entity.ilike(f"{entity}%"))
    if actor:
        query = query.where(AuditEvent.actor == actor)
    if since:
        query = query.where(AuditEvent.timestamp >= since)
    query = query.order_by(AuditEvent.timestamp.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/activity", response_model=list[ActivityItemOut])
async def activity_feed(
    user: ReadUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEvent]:
    """Recent audit events across the estate, newest first, paginated.

    Summary fields only; the before/after payloads stay on /audit.
    """
    estate_id = await _estate_id(session)
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.estate_id == estate_id)
        .order_by(AuditEvent.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/search", response_model=list[SearchHit])
async def search(
    user: ReadUser,
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
) -> list[SearchHit]:
    """Basic ILIKE search returning typed hits {type, id, label}."""
    estate_id = await _estate_id(session)
    pattern = f"%{q}%"
    viewer = user.role == Role.VIEWER
    hits: list[SearchHit] = []

    contacts = await session.execute(
        select(Contact)
        .where(
            Contact.estate_id == estate_id,
            Contact.archived_at.is_(None),
            Contact.name.ilike(pattern) | Contact.org.ilike(pattern),
        )
        .limit(_PER_TYPE_LIMIT)
    )
    for contact in contacts.scalars():
        label = contact.name if not contact.org else f"{contact.name} ({contact.org})"
        hits.append(SearchHit(type="contact", id=contact.id, label=label))

    assets = await session.execute(
        select(Asset)
        .where(
            Asset.estate_id == estate_id,
            Asset.archived_at.is_(None),
            Asset.description.ilike(pattern),
        )
        .limit(_PER_TYPE_LIMIT)
    )
    for asset in assets.scalars():
        hits.append(SearchHit(type="asset", id=asset.id, label=asset.description))

    task_query = select(Task).where(
        Task.estate_id == estate_id,
        Task.archived_at.is_(None),
        Task.title.ilike(pattern),
    )
    if viewer:
        task_query = task_query.where(Task.executor_private.is_(False))
    tasks = await session.execute(task_query.limit(_PER_TYPE_LIMIT))
    for task in tasks.scalars():
        hits.append(SearchHit(type="task", id=task.id, label=task.title))

    document_query = select(Document).where(
        Document.estate_id == estate_id,
        Document.archived_at.is_(None),
        Document.title.ilike(pattern),
    )
    if viewer:
        document_query = document_query.where(Document.executor_private.is_(False))
    documents = await session.execute(document_query.limit(_PER_TYPE_LIMIT))
    for document in documents.scalars():
        if document.access_roles and user.role.value not in document.access_roles:
            continue
        hits.append(SearchHit(type="document", id=document.id, label=document.title))

    cost_query = select(Cost).where(
        Cost.estate_id == estate_id,
        Cost.archived_at.is_(None),
        Cost.description.ilike(pattern),
    )
    if viewer:
        cost_query = cost_query.where(Cost.executor_private.is_(False))
    costs = await session.execute(cost_query.limit(_PER_TYPE_LIMIT))
    for cost in costs.scalars():
        hits.append(SearchHit(type="cost", id=cost.id, label=cost.description))

    return hits
