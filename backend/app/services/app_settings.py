"""Read and write application parameters (the admin Params page).

Embeddings are OFF unless explicitly enabled here: some self-hosted
machines cannot run the local model (a ~0.6 GB one-time download and a
CPU inference load), so nothing downloads or embeds until an admin
switches it on. Search falls back to full-text only while off.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting
from app.models.base import utcnow

logger = logging.getLogger(__name__)

EMBEDDINGS_ENABLED_KEY = "embeddings_enabled"
EMBEDDINGS_STATUS_KEY = "embeddings_status"  # idle | running | complete | error:<msg>
CHAT_DAILY_LIMIT_KEY = "chat_daily_limit"
TOPIC_GUARD_KEY = "topic_guard_enabled"


async def get_setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(AppSetting, key)
    return default if row is None else row.value


async def set_setting(
    session: AsyncSession, key: str, value: Any, actor: str = "system"
) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_by=actor)
    else:
        row.value = value
        row.updated_by = actor
        row.updated_at = utcnow()
    session.add(row)
    await session.flush()


async def embeddings_enabled(session: AsyncSession) -> bool:
    return bool(await get_setting(session, EMBEDDINGS_ENABLED_KEY, False))
