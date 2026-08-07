"""S-1: fail-closed globales AuthN im oidc-Modus.

Ohne per-Route-`PrincipalDep` blieben Read-Endpunkte früher anonym erreichbar.
Der äußere Zaun (`enforce_authentication`) dreht das auf opt-out: alles außer der
Public-Allowlist (health, docs) braucht einen gültigen Token. `/api/library` hat
selbst keine `PrincipalDep` — genau der Fall, den S-1 adressiert.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

jose_jwt = pytest.importorskip("jose.jwt")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk

ISSUER = "https://idp.example.com"
AUDIENCE = "dq-cockpit"


@pytest.fixture()
def oidc_client(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_jwk = jwk.construct(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode(),
        algorithm="RS256",
    ).to_dict()
    pub_jwk["kid"] = "test-key"

    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("SQLITE_DB", str(tmp_path / "test.db"))

    import services.api.settings as settings_mod
    import services.api.deps as deps_mod
    import services.api.auth.oidc as oidc_mod
    settings_mod._settings = None
    deps_mod._store_instance = None
    monkeypatch.setattr(oidc_mod, "_fetch_jwks", lambda settings, force=False: {"keys": [pub_jwk]})

    from fastapi.testclient import TestClient
    from services.api.main import create_app
    client = TestClient(create_app())
    yield client, priv_pem

    settings_mod._settings = None
    deps_mod._store_instance = None


def _token(priv_pem: str, **claims):
    payload = {"sub": "u1", "name": "User One", "iss": ISSUER, "aud": AUDIENCE,
               "exp": 4102444800, "roles": ["viewer"], **claims}
    return jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": "test-key"})


def test_health_is_public(oidc_client):
    client, _ = oidc_client
    assert client.get("/api/health").status_code == 200


def test_read_endpoint_without_token_is_401(oidc_client):
    client, _ = oidc_client
    # /api/library trägt selbst keine PrincipalDep — der globale Zaun schützt es.
    assert client.get("/api/library").status_code == 401


def test_read_endpoint_with_valid_token_ok(oidc_client):
    client, priv = oidc_client
    resp = client.get("/api/library", headers={"Authorization": f"Bearer {_token(priv)}"})
    assert resp.status_code == 200
