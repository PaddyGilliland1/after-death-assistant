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
from app.db import get_session, get_session_factory
from app.ingest.embedder import LOCAL_MODEL, get_embedding_provider
from app.models import KnowledgeChunk
from app.services.app_settings import (
    EMBEDDINGS_ENABLED_KEY,
    EMBEDDINGS_STATUS_KEY,
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


class ParamsUpdate(BaseModel):
    embeddings_enabled: bool


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
    was_enabled = await embeddings_enabled(session)
    await set_setting(
        session, EMBEDDINGS_ENABLED_KEY, payload.embeddings_enabled, actor=user.email
    )
    if payload.embeddings_enabled and not was_enabled:
        await set_setting(session, EMBEDDINGS_STATUS_KEY, "running", actor=user.email)
        background.add_task(_backfill_job)
    if not payload.embeddings_enabled:
        await set_setting(session, EMBEDDINGS_STATUS_KEY, "idle", actor=user.email)
    estate = await get_active_estate(session)
    if estate is not None:
        await record_audit(
            session,
            estate.id,
            user.email,
            "update",
            "app_setting:embeddings_enabled",
            after={"enabled": payload.embeddings_enabled},
        )
    await session.commit()
    return await _params_out(session)
