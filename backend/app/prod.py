"""Production ASGI entry point: the API app plus the built frontend.

app.main stays the API-only application used in development (Vite serves
the frontend there). This wrapper, used by the production image
(uvicorn app.prod:app), adds two things without touching app.main:

1. Serves the built SPA. When FRONTEND_DIST points at a directory that
   contains index.html (the Vite build output copied into the image), a
   small ASGI dispatcher serves REAL files from that directory first
   (necessary because Vite's hashed bundles live under /assets/, which
   would otherwise be captured by the /assets API router), passes every
   other request to the API, and unknown paths fall back to index.html so
   client-side routes (for example /iht) survive a full page reload.

2. Startup safety check. DEV_AUTH must be false in production: when it is
   true and the environment looks production-like (a RAILWAY_* variable is
   set), a prominent warning is logged at app creation. It warns rather
   than refuses so a misconfigured deploy stays diagnosable, but the
   X-Dev-User header being trusted in production is a real vulnerability
   and the warning says so.
"""

import logging
import os
import stat
from pathlib import Path

# StaticFiles raises the starlette HTTPException (the fastapi one is a
# subclass; catching that would miss these), so catch the starlette class.
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.main import create_app as create_api_app

logger = logging.getLogger(__name__)

FRONTEND_DIST_ENV = "FRONTEND_DIST"

# Any of these being set means we are almost certainly running on Railway.
_PROD_ENV_MARKERS = (
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_ID",
)


def _looks_like_production() -> bool:
    return any(os.environ.get(marker) for marker in _PROD_ENV_MARKERS)


class SpaStaticFiles(StaticFiles):
    """Static files with an index.html fallback for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


class SpaDispatcher:
    """ASGI dispatcher: real frontend files first, then the API.

    A plain mount at "/" is not enough because route matching is
    sequential: Vite's hashed bundles live under /assets/, and the API's
    /assets router would capture those requests (returning 401/422)
    before a trailing mount is ever consulted. So GET/HEAD requests whose
    path is a real file inside the dist directory are served directly
    (StaticFiles.lookup_path is traversal-safe); everything else,
    including all non-HTTP scopes such as lifespan, goes to the API app,
    where the SpaStaticFiles mount provides the index.html fallback for
    client-side routes.
    """

    def __init__(self, api: ASGIApp, dist_path: Path) -> None:
        self.api = api
        self.files = StaticFiles(directory=dist_path)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") in ("GET", "HEAD"):
            try:
                path = self.files.get_path(scope)
                _, stat_result = self.files.lookup_path(path)
            except (OSError, ValueError):
                # Over-long or malformed paths cannot be static files;
                # let the API produce its normal 404.
                stat_result = None
            if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
                await self.files(scope, receive, send)
                return
        await self.api(scope, receive, send)


def create_app() -> ASGIApp:
    """The production application: API routers plus the SPA."""
    app = create_api_app()
    settings = get_settings()

    if settings.DEV_AUTH and _looks_like_production():
        logger.warning(
            "DEV_AUTH is true but this environment looks like production "
            "(a RAILWAY_* variable is set). The X-Dev-User header is being "
            "trusted for identity, which lets anyone impersonate any user. "
            "Set DEV_AUTH=false in production immediately."
        )

    dist = os.environ.get(FRONTEND_DIST_ENV, "").strip()
    if dist:
        dist_path = Path(dist)
        if (dist_path / "index.html").is_file():
            app.mount("/", SpaStaticFiles(directory=dist_path, html=True), name="spa")
            logger.info("Serving the frontend from %s", dist_path)
            return SpaDispatcher(app, dist_path)
        logger.warning(
            "%s=%s does not contain index.html; the frontend is not being served.",
            FRONTEND_DIST_ENV,
            dist,
        )
    else:
        logger.info("%s not set; serving the API only.", FRONTEND_DIST_ENV)

    return app


app = create_app()
