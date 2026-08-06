"""OIDC JWT authentication provider. [AUTHZ]

Echte Validierung (S-1 geschlossen): Signatur gegen JWKS, Issuer, Audience,
Expiry, Algorithmus-Pinning (nur asymmetrische Verfahren — kein 'none', kein
HS-Downgrade). JWKS wird aus OIDC_JWKS_URL (oder via Issuer-Discovery)
geladen und mit TTL gecacht; unbekannte `kid` erzwingen einen Refresh
(Key-Rollover).
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Optional

from fastapi import HTTPException, status

from .provider import Principal
from ..settings import get_settings

ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

_JWKS_TTL_S = 300
_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}


def _jwks_url(settings) -> str:
    if settings.oidc_jwks_url:
        return settings.oidc_jwks_url
    if settings.oidc_issuer:
        discovery = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        with urllib.request.urlopen(discovery, timeout=5) as resp:
            return json.loads(resp.read()).get("jwks_uri", "")
    return ""


def _fetch_jwks(settings, *, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    if not force and _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL_S:
        return _jwks_cache["keys"]
    url = _jwks_url(settings)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC misconfigured: no JWKS URL resolvable",
        )
    with urllib.request.urlopen(url, timeout=5) as resp:
        _jwks_cache["keys"] = json.loads(resp.read())
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def _key_for_token(token: str, settings) -> dict[str, Any]:
    from jose import jwt

    header = jwt.get_unverified_header(token)
    if header.get("alg") not in ALLOWED_ALGORITHMS:
        raise HTTPException(status_code=401, detail="Token algorithm not allowed")
    kid = header.get("kid")
    jwks = _fetch_jwks(settings)
    keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    if kid not in keys:
        jwks = _fetch_jwks(settings, force=True)  # Key-Rollover
        keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    if kid not in keys:
        raise HTTPException(status_code=401, detail="Unknown signing key")
    return keys[kid]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def get_oidc_principal(authorization: Optional[str]) -> Principal:
    settings = get_settings()
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC misconfigured: OIDC_ISSUER and OIDC_AUDIENCE are required",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len("Bearer "):]

    from jose import jwt
    from jose.exceptions import JWTError

    try:
        key = _key_for_token(token, settings)
        payload = jwt.decode(
            token,
            key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except HTTPException:
        raise
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token validation failed") from exc

    sub = str(payload.get("sub", "unknown"))
    raw_roles = _as_list(payload.get(settings.oidc_role_claim, []))
    role_map = settings.oidc_role_mapping or {}
    roles = sorted({role_map.get(r, r) for r in raw_roles if role_map.get(r, r)})
    return Principal(
        sub=sub,
        name=str(payload.get("name", sub)),
        roles=roles,
        groups=_as_list(payload.get(settings.oidc_groups_claim, [])),
    )
