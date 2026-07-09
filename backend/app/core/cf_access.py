"""Cloudflare Access JWT validation (closes the forged-header hole).

When Cloudflare Access fronts the app it adds two things to every request:
the plain Cf-Access-Authenticated-User-Email header and a signed JWT in
Cf-Access-Jwt-Assertion. The plain header alone is forgeable by anyone who
can reach the origin directly (for example the raw Railway URL), so in
production the JWT is REQUIRED and authoritative:

  - signature verified against the team's public signing keys (JWKS from
    https://<team domain>/cdn-cgi/access/certs, cached, refreshed on an
    unknown key id),
  - audience must contain CF_ACCESS_AUD,
  - issuer must be the team domain,
  - expiry enforced,
  - the identity email comes from the JWT's email claim, never the plain
    header.

Configuration matrix (see app.core.auth.resolve_email):
  - DEV_AUTH=true: development shim, JWT not consulted.
  - DEV_AUTH=false and CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD set: strict
    JWT validation as above.
  - DEV_AUTH=false and Cloudflare Access not configured: FAIL CLOSED. No
    identity resolves at all, so every request is 401. This is deliberate:
    trusting the plain header without the JWT would let anyone impersonate
    any user.
"""

import logging
import threading
import time

import httpx
import jwt
from jwt import PyJWK

from app.core.config import Settings

logger = logging.getLogger(__name__)

CF_ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"

_JWKS_TTL_SECONDS = 3600
_jwks_lock = threading.Lock()
_jwks_cache: dict[str, tuple[float, dict[str, dict]]] = {}


def _certs_url(team_domain: str) -> str:
    domain = team_domain.strip().rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    return f"{domain}/cdn-cgi/access/certs"


def _fetch_jwks(team_domain: str) -> dict[str, dict]:
    """Fetch the team's JWKS and index keys by kid. Seam for tests."""
    response = httpx.get(_certs_url(team_domain), timeout=10)
    response.raise_for_status()
    keys = response.json().get("keys", [])
    return {key["kid"]: key for key in keys if "kid" in key}


def _get_signing_key(team_domain: str, kid: str) -> dict | None:
    """Cached JWKS lookup; refreshes once when the kid is unknown."""
    now = time.monotonic()
    with _jwks_lock:
        cached = _jwks_cache.get(team_domain)
        if cached and now - cached[0] < _JWKS_TTL_SECONDS and kid in cached[1]:
            return cached[1].get(kid)
    keys = _fetch_jwks(team_domain)
    with _jwks_lock:
        _jwks_cache[team_domain] = (now, keys)
    return keys.get(kid)


def clear_jwks_cache() -> None:
    """Test helper."""
    with _jwks_lock:
        _jwks_cache.clear()


def validate_access_jwt(token: str, settings: Settings) -> str | None:
    """Validate a Cf-Access-Jwt-Assertion token; return the email claim.

    Returns None (never raises) on any validation failure, logging the
    reason at warning level. Callers treat None as unauthenticated.
    """
    team_domain = (settings.CF_ACCESS_TEAM_DOMAIN or "").strip()
    audience = (settings.CF_ACCESS_AUD or "").strip()
    if not team_domain or not audience:
        logger.warning("Access JWT presented but Cloudflare Access is not configured.")
        return None
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        if not kid:
            logger.warning("Access JWT rejected: no key id in header.")
            return None
        jwk = _get_signing_key(team_domain, kid)
        if jwk is None:
            logger.warning("Access JWT rejected: unknown signing key id.")
            return None
        issuer = _certs_url(team_domain).removesuffix("/cdn-cgi/access/certs")
        claims = jwt.decode(
            token,
            key=PyJWK.from_dict(jwk).key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Access JWT rejected: %s", exc)
        return None
    except httpx.HTTPError as exc:
        logger.warning("Access JWT rejected: JWKS fetch failed: %s", exc)
        return None
    email = (claims.get("email") or "").strip().lower()
    if not email:
        logger.warning("Access JWT rejected: no email claim.")
        return None
    return email


def cf_access_configured(settings: Settings) -> bool:
    return bool(
        (settings.CF_ACCESS_TEAM_DOMAIN or "").strip()
        and (settings.CF_ACCESS_AUD or "").strip()
    )
