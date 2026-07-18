"""Admin Params page endpoints.

GET  /settings/params      current parameters and embedding status
POST /settings/params      switch embeddings on or off (admin only)

Embeddings are OFF by default: the local model is a ~0.6 GB one-time
download with a CPU inference load that not every self-hosted machine
can run. Enabling starts a background backfill of the existing chunks;
progress and any failure are reported here and search continues on
full-text either way.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AdminUser, ReadUser
from app.core.config import get_settings
from app.db import get_session, get_session_factory
from app.ingest.embedder import LOCAL_MODEL, get_embedding_provider
from app.models import KnowledgeChunk
from app.services.app_settings import (
    CHAT_DAILY_LIMIT_KEY,
    EMBEDDINGS_ENABLED_KEY,
    EMBEDDINGS_STATUS_KEY,
    TOPIC_GUARD_KEY,
    embeddings_enabled,
    get_setting,
    set_setting,
)
from app.services.seeding import get_active_estate, record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["params"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ParamsOut(BaseModel):
    embeddings_enabled: bool
    embeddings_status: str
    embedding_model: str
    embedded_chunks: int
    total_chunks: int
    chat_daily_limit: int
    topic_guard_enabled: bool


class ParamsUpdate(BaseModel):
    """All fields optional: only supplied parameters change."""

    embeddings_enabled: bool | None = None
    chat_daily_limit: int | None = None
    topic_guard_enabled: bool | None = None


async def _counts(session: AsyncSession) -> tuple[int, int]:
    total = (
        await session.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.archived_at.is_(None))
        )
    ).scalar_one()
    embedded = (
        await session.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.archived_at.is_(None))
            .where(KnowledgeChunk.embedding.is_not(None))
        )
    ).scalar_one()
    return embedded, total


async def _params_out(session: AsyncSession) -> ParamsOut:
    embedded, total = await _counts(session)
    return ParamsOut(
        embeddings_enabled=await embeddings_enabled(session),
        embeddings_status=str(await get_setting(session, EMBEDDINGS_STATUS_KEY, "idle")),
        embedding_model=LOCAL_MODEL,
        embedded_chunks=embedded,
        total_chunks=total,
        chat_daily_limit=int(
            await get_setting(
                session, CHAT_DAILY_LIMIT_KEY, get_settings().CHAT_DAILY_LIMIT
            )
        ),
        topic_guard_enabled=bool(await get_setting(session, TOPIC_GUARD_KEY, True)),
    )


async def _backfill_job() -> None:
    """Embed all chunks without vectors; report status via app settings."""
    factory = get_session_factory()
    try:
        provider = get_embedding_provider()
        async with factory() as session:
            result = await session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.embedding.is_(None))
                .where(KnowledgeChunk.archived_at.is_(None))
            )
            chunks = list(result.scalars().all())
            batch = 32
            for start in range(0, len(chunks), batch):
                part = chunks[start : start + batch]
                vectors = provider.embed_texts([chunk.text for chunk in part])
                if vectors is None:
                    raise RuntimeError("Embedding provider is switched off.")
                for chunk, vector in zip(part, vectors, strict=True):
                    chunk.embedding = vector
                    session.add(chunk)
                await session.commit()
            await set_setting(session, EMBEDDINGS_STATUS_KEY, "complete")
            await session.commit()
            logger.info("Embedding backfill complete: %d chunk(s).", len(chunks))
    except Exception as exc:  # noqa: BLE001 - report, never crash the app
        logger.warning("Embedding backfill failed: %s", exc)
        async with factory() as session:
            await set_setting(
                session, EMBEDDINGS_STATUS_KEY, f"error: {str(exc)[:200]}"
            )
            await session.commit()


@router.get("/params", response_model=ParamsOut)
async def get_params(session: SessionDep, user: ReadUser) -> ParamsOut:
    return await _params_out(session)


@router.post("/params", response_model=ParamsOut)
async def update_params(
    payload: ParamsUpdate,
    background: BackgroundTasks,
    session: SessionDep,
    user: AdminUser,
) -> ParamsOut:
    estate = await get_active_estate(session)

    async def apply(key: str, value, extra=None) -> None:
        before = await get_setting(session, key)
        if before == value:
            return
        await set_setting(session, key, value, actor=user.email)
        if estate is not None:
            await record_audit(
                session,
                estate.id,
                user.email,
                "update",
                f"app_setting:{key}",
                before={"value": before},
                after={"value": value, **(extra or {})},
            )

    if payload.embeddings_enabled is not None:
        was_enabled = await embeddings_enabled(session)
        await apply(EMBEDDINGS_ENABLED_KEY, payload.embeddings_enabled)
        if payload.embeddings_enabled and not was_enabled:
            await set_setting(session, EMBEDDINGS_STATUS_KEY, "running", actor=user.email)
            background.add_task(_backfill_job)
        if not payload.embeddings_enabled:
            await set_setting(session, EMBEDDINGS_STATUS_KEY, "idle", actor=user.email)
    if payload.chat_daily_limit is not None:
        limit = max(1, min(payload.chat_daily_limit, 10000))
        await apply(CHAT_DAILY_LIMIT_KEY, limit)
    if payload.topic_guard_enabled is not None:
        await apply(TOPIC_GUARD_KEY, payload.topic_guard_enabled)
    await session.commit()
    return await _params_out(session)
