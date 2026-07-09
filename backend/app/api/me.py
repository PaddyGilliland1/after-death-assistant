"""Current-user endpoint (contract section 8: GET /me role from CF Access)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.auth import CurrentUser, Role

router = APIRouter(tags=["auth"])


class MeResponse(BaseModel):
    email: str
    role: Role


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> MeResponse:
    """Return the authenticated user's email and resolved role."""
    return MeResponse(email=user.email, role=user.role)
