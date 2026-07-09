"""Database engines and session dependency.

Async engine (asyncpg) for the application, created lazily so importing the
app never requires a reachable database. A sync helper is provided for
Alembic and one-off scripts; note that a synchronous driver (for example
psycopg) must be installed to actually connect with it, since the project
ships asyncpg only. The Alembic env.py therefore uses the async engine.
"""

from collections.abc import AsyncIterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().DATABASE_URL,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession per request."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the shared engine (called at application shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def sync_database_url(url: str | None = None) -> str:
    """Convert the configured async URL to its synchronous form."""
    url = url or get_settings().DATABASE_URL
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def get_sync_engine(url: str | None = None) -> Engine:
    """Create a synchronous engine (Alembic / scripts helper).

    Requires a synchronous DB driver to be installed for the URL's dialect.
    """
    return create_engine(sync_database_url(url), pool_pre_ping=True)
