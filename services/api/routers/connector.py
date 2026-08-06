"""Datasphere connector admin endpoint.

GET  /api/admin/connector  — aktuelle Konfiguration + CLI-Status
PUT  /api/admin/connector  — in datasphere.yml oder .env persistieren
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth.provider import Principal, require_roles
from ..settings import get_settings

logger = logging.getLogger("dq_cockpit.connector")
router = APIRouter(prefix="/api/admin/connector", tags=["admin", "connector"])
require_admin = require_roles("admin")
ENV_FILE = ".env"


class ConnectorIn(BaseModel):
    persist_target: Literal["file", "env"] = "file"
    space_id: str = Field(default="", max_length=128)
    use_cli: bool = False
    cli_host: str = Field(default="", max_length=512)
    base_url: str = Field(default="", max_length=512)
    client_id: str = Field(default="", max_length=256)
    token_url: str = Field(default="", max_length=512)
    client_secret: str = Field(default="", max_length=4096)
    clear_secret: bool = False
    cli_client_id: str = Field(default="", max_length=256)
    cli_authorization_url: str = Field(default="", max_length=512)
    cli_token_url: str = Field(default="", max_length=512)
    cli_oauth_secrets_file: str = Field(default="", max_length=1024)
    cli_client_secret: str = Field(default="", max_length=4096)
    clear_cli_secret: bool = False


def _env_present(name: str) -> bool:
    return str(os.environ.get(name, "") or "").strip() != ""


def _env_file_path() -> str:
    return str(Path(ENV_FILE))


def _reset_runtime_config() -> None:
    from .. import datasphere, datasphere_catalog
    from ..secrets import init_resolver
    from .. import settings as settings_mod

    settings_mod._settings = None
    settings = get_settings()
    init_resolver(settings.secrets_file)
    datasphere_catalog.reset_catalog_client()
    datasphere.reset_client()


def _build_status(principal: Principal) -> dict:
    from ..connector_config import (
        cli_secret_configured,
        effective_authorization_url,
        effective_base_url,
        effective_cli_client_id,
        effective_cli_host,
        effective_cli_oauth_secrets_file,
        effective_cli_token_url,
        effective_client_id,
        effective_space_id,
        effective_token_url,
        effective_use_cli,
        read_connector_config,
        secret_configured,
    )
    from ..datasphere_catalog import get_catalog_client

    settings = get_settings()
    file_cfg = read_connector_config(settings.connector_file)
    configured_host = effective_cli_host(settings)
    cli_authorization_url = effective_authorization_url(settings)
    cli_token_url = effective_cli_token_url(settings)
    cli_oauth_secrets_file = effective_cli_oauth_secrets_file(settings)

    cli_available = False
    cli_logged_in = False
    cli_host: str | None = None
    try:
        from ..datasphere_cli import DatasphereCli

        cli = DatasphereCli(
            host=configured_host or None,
            client_id=effective_cli_client_id(settings) or None,
            authorization_url=cli_authorization_url or None,
            token_url=cli_token_url or None,
            secrets_file=cli_oauth_secrets_file or None,
        )
        cli_available = cli.is_available()
        if cli_available:
            try:
                cli_logged_in = cli.check_login()
                cli_host = cli.configured_cli_host() or (configured_host or None)
            except Exception as exc:
                logger.debug("CLI login check failed: %s", exc)
                cli_host = configured_host or None
    except Exception as exc:
        logger.debug("CLI availability check failed: %s", exc)

    catalog_configured = get_catalog_client() is not None
    space = effective_space_id(settings)
    use_cli = effective_use_cli(settings)

    if space and use_cli and cli_available and cli_logged_in:
        source_mode = "cli"
    elif space and catalog_configured:
        source_mode = "catalog"
    else:
        source_mode = "none"

    return {
        "space_id": space,
        "use_cli": use_cli,
        "cli_available": cli_available,
        "cli_logged_in": cli_logged_in,
        "cli_host": cli_host,
        "catalog_configured": catalog_configured,
        "source_mode": source_mode,
        "config_file": settings.connector_file,
        "env_file": _env_file_path(),
        "base_url": effective_base_url(settings),
        "client_id": effective_client_id(settings),
        "token_url": effective_token_url(settings),
        "secret_configured": secret_configured(settings),
        "cli_client_id": effective_cli_client_id(settings),
        "cli_authorization_url": cli_authorization_url,
        "cli_token_url": cli_token_url,
        "cli_oauth_secrets_file": cli_oauth_secrets_file,
        "cli_secret_configured": cli_secret_configured(settings),
        "login_command": cli.login_command() if cli_available else "",
        "file_space_id": file_cfg.get("space_id", ""),
        "file_use_cli": bool(file_cfg.get("use_cli", False)),
        "file_cli_host": file_cfg.get("cli_host", ""),
        "file_base_url": file_cfg.get("base_url", ""),
        "file_client_id": file_cfg.get("client_id", ""),
        "file_token_url": file_cfg.get("token_url", ""),
        "file_cli_client_id": file_cfg.get("cli_client_id", ""),
        "file_cli_authorization_url": file_cfg.get("cli_authorization_url", ""),
        "file_cli_token_url": file_cfg.get("cli_token_url", ""),
        "file_cli_oauth_secrets_file": file_cfg.get("cli_oauth_secrets_file", ""),
        "env_space_id": getattr(settings, "datasphere_space_id", ""),
        "env_use_cli": getattr(settings, "datasphere_use_cli", False),
        "env_cli_host": getattr(settings, "datasphere_cli_host", ""),
        "env_base_url": getattr(settings, "datasphere_base_url", ""),
        "env_client_id": getattr(settings, "datasphere_client_id", ""),
        "env_token_url": getattr(settings, "datasphere_token_url", ""),
        "env_cli_client_id": getattr(settings, "datasphere_cli_client_id", ""),
        "env_cli_authorization_url": getattr(settings, "datasphere_cli_authorization_url", "")
        or getattr(settings, "datasphere_authorization_url", ""),
        "env_cli_token_url": getattr(settings, "datasphere_cli_token_url", ""),
        "env_cli_oauth_secrets_file": getattr(settings, "datasphere_cli_oauth_secrets_file", "")
        or getattr(settings, "datasphere_oauth_secrets_file", ""),
        "env_has_space_id": _env_present("DATASPHERE_SPACE_ID"),
        "env_has_use_cli": _env_present("DATASPHERE_USE_CLI"),
        "env_has_cli_host": _env_present("DSP_CLI_HOST"),
        "env_has_base_url": _env_present("DATASPHERE_BASE_URL"),
        "env_has_client_id": _env_present("DATASPHERE_CLIENT_ID"),
        "env_has_client_secret": _env_present("DATASPHERE_CLIENT_SECRET"),
        "env_has_token_url": _env_present("DATASPHERE_TOKEN_URL"),
        "env_has_cli_client_id": _env_present("DATASPHERE_CLI_CLIENT_ID"),
        "env_has_cli_client_secret": _env_present("DATASPHERE_CLI_CLIENT_SECRET"),
        "env_has_cli_authorization_url": _env_present("DATASPHERE_CLI_AUTHORIZATION_URL")
        or _env_present("DATASPHERE_AUTHORIZATION_URL"),
        "env_has_cli_token_url": _env_present("DATASPHERE_CLI_TOKEN_URL"),
        "env_has_cli_oauth_secrets_file": _env_present("DATASPHERE_CLI_OAUTH_SECRETS_FILE")
        or _env_present("DATASPHERE_OAUTH_SECRETS_FILE"),
    }


@router.get("")
def get_connector_status(principal: Principal = require_admin):
    """Aktuelle Connector-Konfiguration und CLI-Verfügbarkeit."""
    return _build_status(principal)


@router.post("/login")
def open_connector_login(principal: Principal = require_admin):
    """Start the interactive Datasphere CLI OAuth login in a visible CMD window."""
    from ..connector_config import (
        effective_authorization_url,
        effective_cli_client_id,
        effective_cli_client_secret,
        effective_cli_host,
        effective_cli_oauth_secrets_file,
        effective_cli_token_url,
    )
    from ..datasphere_cli import CliError, DatasphereCli

    settings = get_settings()
    cli = DatasphereCli(
        host=effective_cli_host(settings) or None,
        client_id=effective_cli_client_id(settings) or None,
        client_secret=effective_cli_client_secret(settings) or None,
        authorization_url=effective_authorization_url(settings) or None,
        token_url=effective_cli_token_url(settings) or None,
        secrets_file=effective_cli_oauth_secrets_file(settings) or None,
    )
    if not cli.is_available():
        raise HTTPException(status_code=400, detail="Datasphere CLI ist nicht verfuegbar.")
    try:
        command = cli.open_login_cmd()
    except CliError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "command": command}


def _write_config_file(body: ConnectorIn) -> None:
    from ..connector_config import (
        DEFAULT_CLI_SECRET_REF,
        DEFAULT_SECRET_REF,
        read_connector_config,
        write_connector_config,
    )
    from ..secrets import write_secret

    settings = get_settings()
    existing = read_connector_config(settings.connector_file)
    rest_secret_ref = str(existing.get("secret_ref") or "")
    cli_secret_ref = str(existing.get("cli_secret_ref") or "")

    if body.clear_secret:
        rest_secret_ref = ""
    elif body.client_secret:
        rest_secret_ref = rest_secret_ref or DEFAULT_SECRET_REF
        write_secret(rest_secret_ref, body.client_secret, settings.secrets_file)

    if body.clear_cli_secret:
        cli_secret_ref = ""
    elif body.cli_client_secret:
        cli_secret_ref = cli_secret_ref or DEFAULT_CLI_SECRET_REF
        write_secret(cli_secret_ref, body.cli_client_secret, settings.secrets_file)

    write_connector_config(settings.connector_file, {
        "space_id": body.space_id.strip(),
        "use_cli": body.use_cli,
        "cli_host": body.cli_host.strip(),
        "base_url": body.base_url.strip(),
        "client_id": body.client_id.strip(),
        "token_url": body.token_url.strip(),
        "secret_ref": rest_secret_ref,
        "cli_client_id": body.cli_client_id.strip(),
        "cli_authorization_url": body.cli_authorization_url.strip(),
        "cli_token_url": body.cli_token_url.strip(),
        "cli_oauth_secrets_file": body.cli_oauth_secrets_file.strip(),
        "cli_secret_ref": cli_secret_ref,
    })


def _write_env_file(body: ConnectorIn) -> None:
    from ..env_file import read_env_file, write_env_updates

    current = read_env_file(ENV_FILE)

    rest_secret = current.get("DATASPHERE_CLIENT_SECRET", "")
    if body.clear_secret:
        rest_secret = ""
    elif body.client_secret:
        rest_secret = body.client_secret

    cli_secret = current.get("DATASPHERE_CLI_CLIENT_SECRET", "")
    if body.clear_cli_secret:
        cli_secret = ""
    elif body.cli_client_secret:
        cli_secret = body.cli_client_secret

    write_env_updates(ENV_FILE, {
        "DATASPHERE_SPACE_ID": body.space_id.strip(),
        "DATASPHERE_USE_CLI": "true" if body.use_cli else "false",
        "DSP_CLI_HOST": body.cli_host.strip(),
        "DATASPHERE_BASE_URL": body.base_url.strip(),
        "DATASPHERE_CLIENT_ID": body.client_id.strip(),
        "DATASPHERE_CLIENT_SECRET": rest_secret,
        "DATASPHERE_TOKEN_URL": body.token_url.strip(),
        "DATASPHERE_CLI_CLIENT_ID": body.cli_client_id.strip(),
        "DATASPHERE_CLI_CLIENT_SECRET": cli_secret,
        "DATASPHERE_CLI_AUTHORIZATION_URL": body.cli_authorization_url.strip(),
        "DATASPHERE_CLI_TOKEN_URL": body.cli_token_url.strip(),
        "DATASPHERE_CLI_OAUTH_SECRETS_FILE": body.cli_oauth_secrets_file.strip(),
    })


@router.put("")
def put_connector_config(body: ConnectorIn, principal: Principal = require_admin):
    """Speichert Connector-Konfiguration in datasphere.yml oder .env.

    REST und CLI können getrennte OAuth-Clients verwenden. Secrets werden je
    nach Ziel entweder referenzbasiert in ``secrets.local.yml`` (persist_target
    ``file``) oder direkt in ``.env`` (persist_target ``env``) gespeichert.
    """
    if body.persist_target == "env":
        _write_env_file(body)
    else:
        _write_config_file(body)

    _reset_runtime_config()
    return _build_status(principal)
