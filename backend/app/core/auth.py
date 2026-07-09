"""Identity and role resolution, enforced server-side (contract guardrail 4).

Identity comes from the Cf-Access-Authenticated-User-Email header set by
Cloudflare Access. In development only (settings.DEV_AUTH true) the
X-Dev-User header is accepted instead. The client is never trusted for
roles: the email is mapped to a role via the USER_ROLES setting (later a
database table). No identity yields 401; identity without a role yields 403.

Roles:
    executor  - full read and write on estate data
    admin     - full read and write, plus admin-only endpoints
    viewer    - strictly read-only; WRITE endpoints must NOT accept viewer

Every write route must depend on require_write (or require_admin), never on
require_read alone.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

CF_ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"
DEV_USER_HEADER = "X-Dev-User"


class Role(StrEnum):
    EXECUTOR = "executor"
    ADMIN = "admin"
    VIEWER = "viewer"


WRITE_ROLES: tuple[Role, ...] = (Role.EXECUTOR, Role.ADMIN)
READ_ROLES: tuple[Role, ...] = (Role.EXECUTOR, Role.ADMIN, Role.VIEWER)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    email: str
    role: Role


def parse_user_roles(raw: str) -> dict[str, Role]:
    """Parse the USER_ROLES setting ("email:role,email:role") into a mapping.

    Unknown roles and malformed entries are skipped with a warning rather
    than granting anything. An empty string yields an empty mapping, which
    means every request is refused with 403.
    """
    mapping: dict[str, Role] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        email, sep, role_name = entry.rpartition(":")
        if not sep or not email:
            logger.warning("USER_ROLES entry ignored (expected email:role): %r", entry)
            continue
        try:
            role = Role(role_name.strip().lower())
        except ValueError:
            logger.warning("USER_ROLES entry ignored (unknown role %r)", role_name)
            continue
        mapping[email.strip().lower()] = role
    return mapping


def resolve_email(request: Request, settings: Settings) -> str | None:
    """Extract the authenticated email from the request.

    Three modes (see app.core.cf_access for the full rationale):
    - DEV_AUTH true: the plain Cloudflare header, else the X-Dev-User shim.
    - Cloudflare Access configured: the signed Cf-Access-Jwt-Assertion is
      REQUIRED and authoritative; the plain header is never trusted alone
      because anyone reaching the origin directly can forge it.
    - Neither: fail closed. No identity resolves and every request is 401.
    """
    from app.core.cf_access import (
        CF_ACCESS_JWT_HEADER,
        cf_access_configured,
        validate_access_jwt,
    )

    if settings.DEV_AUTH:
        email = request.headers.get(CF_ACCESS_EMAIL_HEADER) or request.headers.get(
            DEV_USER_HEADER
        )
        email = (email or "").strip().lower()
        return email or None

    if cf_access_configured(settings):
        token = request.headers.get(CF_ACCESS_JWT_HEADER)
        if not token:
            return None
        return validate_access_jwt(token, settings)

    logger.warning(
        "No identity source: DEV_AUTH is false and Cloudflare Access is not "
        "configured (CF_ACCESS_TEAM_DOMAIN / CF_ACCESS_AUD). Failing closed."
    )
    return None


def resolve_user(request: Request, settings: Settings) -> AuthenticatedUser | None:
    """Best-effort resolution used by middleware; never raises."""
    email = resolve_email(request, settings)
    if not email:
        return None
    role = parse_user_roles(settings.USER_ROLES).get(email)
    if role is None:
        return None
    return AuthenticatedUser(email=email, role=role)


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """FastAPI dependency: the authenticated user, or 401/403."""
    email = resolve_email(request, settings)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    role = parse_user_roles(settings.USER_ROLES).get(email)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No role assigned for this account.",
        )
    return AuthenticatedUser(email=email, role=role)


def require_role(*roles: Role):
    """Dependency factory: allow only the given roles.

    Usage:
        @router.post("/assets", dependencies=[Depends(require_write)])
    or
        user: Annotated[AuthenticatedUser, Depends(require_role(Role.ADMIN))]
    """
    if not roles:
        raise ValueError("require_role needs at least one role")

    allowed = frozenset(roles)

    async def dependency(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not permit this action.",
            )
        return user

    return dependency


# Ready-made dependencies. Viewer is read-only by construction: it is absent
# from require_write and require_admin, so no write route can accept it.
require_read = require_role(*READ_ROLES)
require_write = require_role(*WRITE_ROLES)
require_admin = require_role(Role.ADMIN)

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
ReadUser = Annotated[AuthenticatedUser, Depends(require_read)]
WriteUser = Annotated[AuthenticatedUser, Depends(require_write)]
AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
