"""Knowledge chat router: conversational, cited Q&A.

POST /knowledge/chat            ask a question (new or existing thread)
GET  /knowledge/chats           list this estate's conversations
GET  /knowledge/chats/{id}/messages   full thread
DELETE /knowledge/chats/{id}    archive a conversation (reason optional)

Questions require a write role: chat turns are estate records (viewer
stays strictly read-only and can read threads only).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ReadUser, WriteUser
from app.core.config import get_settings
from app.db import get_session
from app.models import QaConversation, QaMessage
from app.models.base import utcnow
from app.schemas.qa_chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSource,
    ConversationOut,
)
from app.services.qa_chat import is_question_on_topic, run_chat_turn
from app.services.seeding import get_active_estate, record_audit

router = APIRouter(prefix="/knowledge", tags=["knowledge-chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _message_out(message: QaMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        sources_cited=[ChatSource(**s) for s in message.sources_cited or []],
        related_sources=[ChatSource(**s) for s in message.related_sources or []],
        created_at=message.created_at,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, session: SessionDep, user: WriteUser) -> ChatResponse:
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY.strip():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The knowledge chat is unavailable: ANTHROPIC_API_KEY is not "
            "configured. Search and the document viewer remain available.",
        )
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No estate found.")

    # Usage ceiling: a hard daily cap on questions per estate protects
    # against runaway loops and unbounded spend (HTTP 429 when reached).
    from datetime import UTC, datetime

    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    asked_today = (
        await session.execute(
            select(func.count())
            .select_from(QaMessage)
            .where(QaMessage.estate_id == estate.id)
            .where(QaMessage.role == "user")
            .where(QaMessage.created_at >= day_start)
        )
    ).scalar_one()
    from app.services.app_settings import (
        CHAT_DAILY_LIMIT_KEY,
        TOPIC_GUARD_KEY,
        get_setting,
    )

    daily_limit = int(
        await get_setting(session, CHAT_DAILY_LIMIT_KEY, settings.CHAT_DAILY_LIMIT)
    )
    if asked_today >= daily_limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "The daily question limit for this estate has been reached. "
            "It resets at midnight UTC; the Library and Search remain available.",
        )

    # Scope guard: unrelated questions stop for confirmation before any
    # expensive call runs or anything is stored.
    guard_on = bool(await get_setting(session, TOPIC_GUARD_KEY, True))
    if (
        guard_on
        and not payload.confirmed
        and not is_question_on_topic(payload.question, settings)
    ):
        return ChatResponse(
            needs_confirmation=True,
            notice=(
                "This question looks unrelated to estate administration and "
                "bereavement, which is all this assistant covers. It can try "
                "anyway, but the answer will be limited to the cached official "
                "guidance. Ask anyway?"
            ),
        )

    try:
        conversation, message = await run_chat_turn(
            session,
            estate_id=estate.id,
            actor=user.email,
            question=payload.question,
            conversation_id=payload.conversation_id,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ChatResponse(conversation_id=conversation.id, message=_message_out(message))


@router.get("/chats", response_model=list[ConversationOut])
async def list_conversations(session: SessionDep, user: ReadUser) -> list[ConversationOut]:
    estate = await get_active_estate(session)
    if estate is None:
        return []
    result = await session.execute(
        select(QaConversation)
        .where(QaConversation.estate_id == estate.id)
        .where(QaConversation.archived_at.is_(None))
        .order_by(QaConversation.updated_at.desc())
        .limit(50)
    )
    return [
        ConversationOut(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in result.scalars().all()
    ]


@router.get("/chats/{conversation_id}/messages", response_model=list[ChatMessageOut])
async def conversation_messages(
    conversation_id: uuid.UUID, session: SessionDep, user: ReadUser
) -> list[ChatMessageOut]:
    estate = await get_active_estate(session)
    conversation = await session.get(QaConversation, conversation_id)
    if (
        conversation is None
        or conversation.archived_at is not None
        or estate is None
        or conversation.estate_id != estate.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    result = await session.execute(
        select(QaMessage)
        .where(QaMessage.conversation_id == conversation_id)
        .where(QaMessage.archived_at.is_(None))
        .order_by(QaMessage.created_at)
    )
    return [_message_out(message) for message in result.scalars().all()]


@router.delete("/chats/{conversation_id}", response_model=ConversationOut)
async def archive_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    user: WriteUser,
    reason: Annotated[str | None, Body(embed=True)] = None,
) -> QaConversation:
    estate = await get_active_estate(session)
    conversation = await session.get(QaConversation, conversation_id)
    if (
        conversation is None
        or conversation.archived_at is not None
        or estate is None
        or conversation.estate_id != estate.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    conversation.archived_at = utcnow()
    conversation.archive_reason = reason
    conversation.updated_at = utcnow()
    session.add(conversation)
    await session.flush()
    await record_audit(
        session,
        conversation.estate_id,
        user.email,
        "archive",
        f"qa_conversation:{conversation.id}",
        after={"reason": reason},
    )
    await session.commit()
    return conversation
