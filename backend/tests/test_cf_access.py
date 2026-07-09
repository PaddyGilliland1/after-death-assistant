"""Cloudflare Access JWT validation tests (the forged-header hole).

No network: the JWKS fetch seam is monkeypatched with a locally
generated RSA key pair.
"""

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import cf_access
from app.core.config import Settings, get_settings
from app.main import create_app

TEAM = "adtest.cloudflareaccess.com"
AUD = "test-aud-tag"
KID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
    _private_key.public_key(), as_dict=True
)
_public_jwk["kid"] = KID
_PEM = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)


def make_token(
    email: str = "exec@family.test",
    aud: str = AUD,
    iss: str = f"https://{TEAM}",
    exp_offset: int = 600,
    kid: str = KID,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "email": email,
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + exp_offset,
            "sub": str(uuid.uuid4()),
        },
        _PEM,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch):
    cf_access.clear_jwks_cache()
    monkeypatch.setattr(cf_access, "_fetch_jwks", lambda team: {KID: _public_jwk})
    yield
    cf_access.clear_jwks_cache()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEV_AUTH", "false")
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.setenv("USER_ROLES", "exec@family.test:executor")
    get_settings.cache_clear()
    app = create_app()
    yield TestClient(app)
    get_settings.cache_clear()


def settings_for(**overrides) -> Settings:
    base = dict(
        DEV_AUTH=False,
        CF_ACCESS_TEAM_DOMAIN=TEAM,
        CF_ACCESS_AUD=AUD,
        USER_ROLES="exec@family.test:executor",
    )
    base.update(overrides)
    return Settings(**base)


def test_valid_jwt_resolves_email():
    email = cf_access.validate_access_jwt(make_token(), settings_for())
    assert email == "exec@family.test"


def test_wrong_audience_rejected():
    assert cf_access.validate_access_jwt(
        make_token(aud="other-app"), settings_for()
    ) is None


def test_wrong_issuer_rejected():
    assert cf_access.validate_access_jwt(
        make_token(iss="https://evil.example.com"), settings_for()
    ) is None


def test_expired_rejected():
    assert cf_access.validate_access_jwt(
        make_token(exp_offset=-60), settings_for()
    ) is None


def test_unknown_kid_rejected():
    assert cf_access.validate_access_jwt(
        make_token(kid="unknown-key"), settings_for()
    ) is None


def test_forged_plain_header_rejected_when_cf_configured(client):
    response = client.get("/me", headers={
        "Cf-Access-Authenticated-User-Email": "exec@family.test",
    })
    assert response.status_code == 401


def test_valid_jwt_authenticates_via_endpoint(client):
    response = client.get("/me", headers={
        "Cf-Access-Jwt-Assertion": make_token(),
    })
    assert response.status_code == 200
    assert response.json()["email"] == "exec@family.test"
    assert response.json()["role"] == "executor"


def test_jwt_email_outside_user_roles_gets_403(client):
    response = client.get("/me", headers={
        "Cf-Access-Jwt-Assertion": make_token(email="stranger@family.test"),
    })
    assert response.status_code == 403


def test_fail_closed_when_nothing_configured(monkeypatch):
    monkeypatch.setenv("DEV_AUTH", "false")
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "")
    monkeypatch.setenv("CF_ACCESS_AUD", "")
    monkeypatch.setenv("USER_ROLES", "exec@family.test:executor")
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/me", headers={
        "Cf-Access-Authenticated-User-Email": "exec@family.test",
    })
    assert response.status_code == 401
    get_settings.cache_clear()


def test_dev_shim_still_works(monkeypatch):
    monkeypatch.setenv("DEV_AUTH", "true")
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "")
    monkeypatch.setenv("CF_ACCESS_AUD", "")
    monkeypatch.setenv("USER_ROLES", "exec@family.test:executor")
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/me", headers={"X-Dev-User": "exec@family.test"})
    assert response.status_code == 200
    get_settings.cache_clear()
