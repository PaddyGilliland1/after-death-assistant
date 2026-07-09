"""Health endpoint (unauthenticated liveness probe)."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check for compose healthchecks and Railway."""
    return {"status": "ok"}
