"""FastAPI application factory.

Wires CORS for the frontend origin, the identity middleware (best-effort
resolution onto request.state for auditing; enforcement happens in the
route dependencies in app.core.auth), the API routers, and a lifespan that
checks database connectivity without failing startup in dev.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    admin_tax,
    agent_drafts,
    approvals,
    assets,
    audit_activity,
    beneficiaries,
    contacts,
    costs,
    creditor_notices,
    creditors,
    debtors,
    decisions,
    digital,
    documents,
    estate,
    exports,
    health,
    iht,
    iht_schedule_tasks,
    knowledge,
    knowledge_chat,
    liabilities,
    me,
    notifications,
    process,
    reliefs,
    tasks,
    tracing,
)
from app.core.auth import resolve_user
from app.core.config import get_settings
from app.db import dispose_engine, get_engine
from app.services import veteran

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Check DB connectivity at startup; never fatal in dev without a DB."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
    except Exception as exc:  # noqa: BLE001 - startup must survive a missing dev DB
        logger.warning("Database not reachable at startup (non-fatal in dev): %s", exc)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AD Assistant API",
        description=(
            "Estate administration and IHT tool (England and Wales). "
            "Informs and drafts; nothing is filed or sent automatically."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def identity_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Attach the resolved user (or None) to request.state for auditing.

        Enforcement (401/403) is done by the auth dependencies on each
        route; this middleware never rejects a request itself.
        """
        request.state.user = resolve_user(request, get_settings())
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(estate.router)
    app.include_router(iht.router)
    app.include_router(assets.router)
    app.include_router(liabilities.router)
    app.include_router(debtors.router)
    app.include_router(creditors.router)
    app.include_router(creditor_notices.router)
    app.include_router(contacts.router)
    app.include_router(tasks.router)
    app.include_router(costs.router)
    app.include_router(beneficiaries.router)
    app.include_router(decisions.router)
    app.include_router(documents.router)
    app.include_router(notifications.router)
    app.include_router(audit_activity.router)
    app.include_router(process.router)
    app.include_router(approvals.router)
    app.include_router(reliefs.router)
    app.include_router(admin_tax.router)
    app.include_router(digital.router)
    app.include_router(tracing.router)
    app.include_router(iht_schedule_tasks.router)
    app.include_router(veteran.router)
    app.include_router(knowledge.router)
    app.include_router(knowledge_chat.router)
    app.include_router(agent_drafts.router)
    app.include_router(exports.router)

    return app


app = create_app()
