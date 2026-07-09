"""Shared test fixtures.

Minimal by design: dev-auth environment, cached-settings reset, and a
TestClient factory that sends X-Dev-User. Domain and model modules are
never imported here; they are owned by other test modules and may not
exist yet.
"""

import os

import pytest

# Test environment must be in place before app.core.config is imported
# anywhere, so set it at collection time, not inside a fixture.
_TEST_ENV = {
    "DEV_AUTH": "true",
    "USER_ROLES": ("admin@test.local:admin,executor@test.local:executor,viewer@test.local:viewer"),
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "FRONTEND_ORIGIN": "http://localhost:5173",
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value


DEFAULT_TEST_USER = "executor@test.local"


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Ensure every test sees settings built from the test environment."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings():
    from app.core.config import get_settings

    return get_settings()


@pytest.fixture
def client_factory():
    """Build a TestClient authenticated via the dev shim.

    Usage:
        client = client_factory()                        # executor
        client = client_factory("viewer@test.local")     # specific user
        client = client_factory(None)                    # anonymous
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(user: str | None = DEFAULT_TEST_USER) -> TestClient:
        client = TestClient(create_app())
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    return _make


@pytest.fixture
def client(client_factory):
    """TestClient authenticated as the default executor test user."""
    return client_factory()
