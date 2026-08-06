"""S-1: OIDC-Validierung muss Signatur, Issuer, Audience und Algorithmus prüfen."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

jose_jwt = pytest.importorskip("jose.jwt")
from cryptography.hazmat.primitives.asymmetric import rsa

from jose import jwk

ISSUER = "https://idp.example.com"
AUDIENCE = "dq-cockpit"


@pytest.fixture()
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from cryptography.hazmat.primitives import serialization
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
    return priv_pem, pub_jwk


@pytest.fixture()
def oidc_env(monkeypatch, rsa_keys):
    _, pub_jwk = rsa_keys
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)

    import services.api.settings as settings_mod
    settings_mod._settings = None

    import services.api.auth.oidc as oidc_mod
    oidc_mod._jwks_cache["keys"] = {"keys": [pub_jwk]}
    oidc_mod._jwks_cache["fetched_at"] = 10**12  # nie ablaufen lassen im Test
    monkeypatch.setattr(oidc_mod, "_fetch_jwks", lambda settings, force=False: {"keys": [pub_jwk]})
    yield oidc_mod
    settings_mod._settings = None


def _token(priv_pem: str, *, iss=ISSUER, aud=AUDIENCE, alg="RS256", headers=None, **claims):
    payload = {"sub": "u1", "name": "User One", "iss": iss, "aud": aud,
               "exp": 4102444800, "roles": ["steward"], **claims}
    return jose_jwt.encode(payload, priv_pem, algorithm=alg,
                           headers=headers or {"kid": "test-key"})


def test_valid_token_yields_principal(oidc_env, rsa_keys):
    priv, _ = rsa_keys
    principal = oidc_env.get_oidc_principal(f"Bearer {_token(priv)}")
    assert principal.sub == "u1"
    assert principal.roles == ["steward"]


def test_wrong_audience_rejected(oidc_env, rsa_keys):
    priv, _ = rsa_keys
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        oidc_env.get_oidc_principal(f"Bearer {_token(priv, aud='other-app')}")
    assert exc.value.status_code == 401


def test_wrong_issuer_rejected(oidc_env, rsa_keys):
    priv, _ = rsa_keys
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        oidc_env.get_oidc_principal(f"Bearer {_token(priv, iss='https://evil.example.com')}")
    assert exc.value.status_code == 401


def test_expired_token_rejected(oidc_env, rsa_keys):
    priv, _ = rsa_keys
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        oidc_env.get_oidc_principal(f"Bearer {_token(priv, exp=1)}")
    assert exc.value.status_code == 401


def test_hs256_downgrade_rejected(oidc_env):
    """Algorithm-Confusion: HS256-Token (mit beliebigem Secret signiert) → 401."""
    from fastapi import HTTPException
    token = jose_jwt.encode(
        {"sub": "u1", "iss": ISSUER, "aud": AUDIENCE, "exp": 4102444800},
        "secret", algorithm="HS256", headers={"kid": "test-key"},
    )
    with pytest.raises(HTTPException) as exc:
        oidc_env.get_oidc_principal(f"Bearer {token}")
    assert exc.value.status_code == 401


def test_unsigned_garbage_rejected(oidc_env):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        oidc_env.get_oidc_principal("Bearer not.a.jwt")
    with pytest.raises(HTTPException) as exc:
        oidc_env.get_oidc_principal(None)
    assert exc.value.status_code == 401
