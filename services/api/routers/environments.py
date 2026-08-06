"""Platform-admin connection settings — define the HANA/Datasphere connection
details Signal runs its read-only checks against.

An *environment* is a named connection target: host, port, technical user,
default schema and TLS options, plus a **secret reference** for the password.
The reference (e.g. ``env:HANA_PW_PROD``) is stored in ``environments.yml``;
the password value itself is resolved server-side at connect time and never
written to disk or returned to a client (secrets.py discipline, S-13).

Writes are restricted to the platform-owner (admin) role. The list/read is
admin-only too — even though it never exposes a secret value, it is operational
configuration. The non-secret name+schema list for the run dialog stays in the
``extract`` router (``GET /api/environments``); the live connection test stays
at ``POST /api/environments/{name}/test``.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.provider import Principal, require_roles
from ..deps import read_environments, write_environments
from ..secrets import secret_status, write_secret
from ..settings import get_settings

router = APIRouter(prefix="/api/admin/environments", tags=["admin", "environments"])

# Connection settings are a platform-owner concern (mirrors notifications).
require_admin = require_roles("admin")

# Environment names become YAML keys and travel in URLs; keep them boring.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class EnvironmentIn(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    user: str = Field(min_length=1, max_length=128)
    schema_: str = Field(default="", max_length=128, alias="schema")
    # Secret *reference*, not the secret: 'env:VAR', bare 'VAR', or 'plain:...'
    # (local dev only). Empty on update = keep the existing reference unchanged.
    password_ref: str = Field(default="", max_length=255)
    encrypt: bool = True
    validate_cert: bool = True

    model_config = {"populate_by_name": True}


def _public_view(name: str, cfg: dict) -> dict:
    """Project an on-disk entry to a client-safe shape — never the secret value.

    ``password_set`` reports whether a usable credential is configured: an inline
    legacy ``password`` counts, otherwise the ``password_ref`` is probed via the
    secret resolver (boolean only, the value is never touched here).
    """
    ref = str(cfg.get("password_ref") or "")
    has_inline = bool(cfg.get("password"))
    return {
        "name": name,
        "host": cfg.get("host", ""),
        "port": int(cfg.get("port", 443) or 443),
        "user": cfg.get("user", ""),
        "schema": cfg.get("schema", ""),
        # plain: refs embed the secret value directly — never surface them.
        # Other refs (env:VAR, bare VAR) are safe to display.
        "password_ref": "" if ref.startswith("plain:") else ref,
        "password_set": has_inline or secret_status(ref),
        "encrypt": bool(cfg.get("encrypt", True)),
        "validate_cert": bool(cfg.get("validate_cert", True)),
    }


def _entry_from_input(body: EnvironmentIn, existing: dict | None) -> dict:
    """Build the on-disk entry, preserving unknown keys and unchanged secrets.

    Starting from the existing entry keeps any hand-authored extras and the
    current credential; the managed scalar fields are then overwritten. The
    credential is only touched when a new reference is supplied.
    """
    entry = dict(existing or {})
    entry.update(
        host=body.host.strip(),
        port=body.port,
        user=body.user.strip(),
        schema=body.schema_.strip(),
        encrypt=body.encrypt,
        validate_cert=body.validate_cert,
    )
    ref = body.password_ref.strip()
    if ref:
        # A new reference supersedes any prior reference and any inline legacy
        # password (never keep a stale plaintext credential alongside a ref).
        entry["password_ref"] = ref
        entry.pop("password", None)
    # else (empty ref): keep whatever credential the entry already had. For a
    # brand-new entry that is simply nothing → password_set stays False.
    return entry


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="Environment name must be alphanumeric (with . _ -), max 64 chars.",
        )


@router.get("")
def list_environments(principal: Principal = require_admin):
    """All configured connection targets (admin-only, secret values hidden)."""
    envs = read_environments()
    return {
        "environments": [_public_view(name, cfg) for name, cfg in sorted(envs.items())],
        "can_edit": principal.has_role("admin"),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_environment(name: str, body: EnvironmentIn, principal: Principal = require_admin):
    _validate_name(name)
    envs = read_environments()
    if name in envs:
        raise HTTPException(status_code=409, detail=f"Environment {name!r} already exists.")
    envs[name] = _entry_from_input(body, existing=None)
    write_environments(envs)
    return _public_view(name, envs[name])


@router.put("/{name}")
def update_environment(name: str, body: EnvironmentIn, principal: Principal = require_admin):
    envs = read_environments()
    if name not in envs:
        raise HTTPException(status_code=404, detail=f"Environment {name!r} not found.")
    envs[name] = _entry_from_input(body, existing=envs[name])
    write_environments(envs)
    return _public_view(name, envs[name])


class SecretBody(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


@router.put("/{name}/secret", status_code=status.HTTP_204_NO_CONTENT)
def set_environment_secret(name: str, body: SecretBody, principal: Principal = require_admin):
    """Speichert das Passwort für ein Environment in secrets.local.yml (gitignored).

    Das Passwort verlässt diesen Endpoint nie — kein Log, keine Response (S-1).
    Die Referenz (password_ref) muss im Environment konfiguriert sein und darf
    kein plain:-Direktwert sein.
    """
    envs = read_environments()
    if name not in envs:
        raise HTTPException(status_code=404, detail=f"Environment {name!r} not found.")
    ref = str(envs[name].get("password_ref") or "")
    if not ref:
        raise HTTPException(
            status_code=422,
            detail="Environment hat keine password_ref konfiguriert.",
        )
    try:
        write_secret(ref, body.password, get_settings().secrets_file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(name: str, principal: Principal = require_admin):
    envs = read_environments()
    if name not in envs:
        raise HTTPException(status_code=404, detail=f"Environment {name!r} not found.")
    del envs[name]
    write_environments(envs)
