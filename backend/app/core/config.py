"""Application settings loaded from the environment (and .env in dev).

All configuration flows through the Settings model so every consumer sees
validated, typed values. Use get_settings() (cached) or depend on it in
FastAPI routes so tests can override it.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the AD Assistant backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ad_assistant"

    # Auth. DEV_AUTH must be false in production; when true the backend
    # accepts the X-Dev-User header in place of Cloudflare Access.
    DEV_AUTH: bool = False
    CF_ACCESS_TEAM_DOMAIN: str = ""
    CF_ACCESS_AUD: str = ""

    # Role mapping until roles move to the database.
    # Format: "email:role,email:role" with roles executor | admin | viewer.
    # Empty means nobody has a role, so every request is refused with 403.
    USER_ROLES: str = ""

    # Agents / knowledge library
    ANTHROPIC_API_KEY: str = ""
    EMBEDDING_MODEL: str = "local"

    # Object storage (dev: local path; prod: Cloudflare R2 or Railway volume)
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "./storage"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""

    # App
    BACKEND_PORT: int = 8471
    FRONTEND_ORIGIN: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance.

    Tests may call get_settings.cache_clear() after adjusting environment
    variables, or override this dependency on the FastAPI app.
    """
    return Settings()
