"""Notifications API: each user sees and manages only their own rows.

GET is open to every read role; marking read is a write and therefore
requires a write role (viewer stays strictly read-only per the auth
contract; notifications are aimed at executors anyway).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.db import get_session
from app.models import Notification
from app.models.base import utcnow
from app.schemas.collab import NotificationOut, ReadAllResult

router = APIRouter(prefix="/notifications", tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[NotificationOut])
async def list_notifications(user: ReadUser, session: SessionDep) -> list[Notification]:
    """The caller's own notifications, unread first, then newest first."""
    result = await session.execute(
        select(Notification)
        .where(
            Notification.user_id == user.email,
            Notification.archived_at.is_(None),
        )
        .order_by(Notification.read_at.is_(None).desc(), Notification.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID, user: WriteUser, session: SessionDep
) -> Notification:
    """Mark one of the caller's own notifications as read."""
    notification = await session.get(Notification, notification_id)
    if (
        notification is None
        or notification.user_id != user.email
        or notification.archived_at is not None
    ):
        # 404 for other users' rows so their existence is not leaked.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found."
        )
    if notification.read_at is None:
        notification.read_at = utcnow()
        session.add(notification)
        await session.commit()
    return notification


@router.post("/read-all", response_model=ReadAllResult)
async def mark_all_read(user: WriteUser, session: SessionDep) -> ReadAllResult:
    """Mark all of the caller's unread notifications as read."""
    result = await session.execute(
        select(Notification).where(
            Notification.user_id == user.email,
            Notification.read_at.is_(None),
            Notification.archived_at.is_(None),
        )
    )
    now = utcnow()
    rows = list(result.scalars().all())
    for notification in rows:
        notification.read_at = now
        session.add(notification)
    await session.commit()
    return ReadAllResult(marked_read=len(rows))
