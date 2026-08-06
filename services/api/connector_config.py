"""Datasphere connector runtime config — persisted to datasphere.yml.

Env vars always take precedence over this file; it is a runtime alternative for
operators who cannot set env vars. It is git-ignored by convention (like
secrets.local.yml).

Persisted keys:
  space_id              technischer Name des Datasphere-Space
  use_cli               @sap/datasphere-cli als (CSN-)Quelle bevorzugen
  cli_host              Tenant-Host für die CLI (entspricht DSP_CLI_HOST)
  base_url              REST-Katalog Basis-URL (entspricht DATASPHERE_BASE_URL)
  client_id             REST OAuth2 Client-ID (entspricht DATASPHERE_CLIENT_ID)
  token_url             REST Token-Endpoint-Override
  secret_ref            REST-Client-Secret-Referenz (nie Klartext)
  cli_client_id         CLI OAuth2 Client-ID
  cli_authorization_url CLI Authorization-URL
  cli_token_url         CLI Token-URL
  cli_oauth_secrets_file optionale CLI Secrets-Datei
  cli_secret_ref        CLI-Client-Secret-Referenz (nie Klartext)

Der Client-Secret-Klartext landet NIE in dieser Datei (S-13): die Config hält nur
Referenzen, die zur Laufzeit über den Secret-Resolver aufgelöst werden.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Stabile Default-Referenzen, unter denen die UI Secrets ablegt
# (secrets.local.yml / env). Bare Name → env-Var bzw. Secrets-Datei.
DEFAULT_SECRET_REF = "DATASPHERE_CLIENT_SECRET"
DEFAULT_CLI_SECRET_REF = "DATASPHERE_CLI_CLIENT_SECRET"

_DEFAULTS: dict[str, Any] = {
    "space_id": "",
    "use_cli": False,
    "cli_host": "",
    "base_url": "",
    "client_id": "",
    "token_url": "",
    "secret_ref": "",
    "cli_client_id": "",
    "cli_authorization_url": "",
    "cli_token_url": "",
    "cli_oauth_secrets_file": "",
    "cli_secret_ref": "",
}


def read_connector_config(connector_file: str) -> dict[str, Any]:
    import yaml
    path = Path(connector_file)
    if not path.exists():
        return dict(_DEFAULTS)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return dict(_DEFAULTS)
    return {
        "space_id": str(data.get("space_id") or ""),
        "use_cli": bool(data.get("use_cli", False)),
        "cli_host": str(data.get("cli_host") or ""),
        "base_url": str(data.get("base_url") or ""),
        "client_id": str(data.get("client_id") or ""),
        "token_url": str(data.get("token_url") or ""),
        "secret_ref": str(data.get("secret_ref") or ""),
        "cli_client_id": str(data.get("cli_client_id") or data.get("client_id") or ""),
        "cli_authorization_url": str(data.get("cli_authorization_url") or data.get("authorization_url") or ""),
        "cli_token_url": str(data.get("cli_token_url") or data.get("token_url") or ""),
        "cli_oauth_secrets_file": str(data.get("cli_oauth_secrets_file") or data.get("oauth_secrets_file") or ""),
        "cli_secret_ref": str(data.get("cli_secret_ref") or ""),
    }


def write_connector_config(connector_file: str, cfg: dict[str, Any]) -> None:
    import yaml
    path = Path(connector_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {
        "space_id": str(cfg.get("space_id") or ""),
        "use_cli": bool(cfg.get("use_cli", False)),
        "cli_host": str(cfg.get("cli_host") or ""),
        "base_url": str(cfg.get("base_url") or ""),
        "client_id": str(cfg.get("client_id") or ""),
        "token_url": str(cfg.get("token_url") or ""),
        # NIE der Klartext — nur die Referenz (S-13).
        "secret_ref": str(cfg.get("secret_ref") or ""),
        "cli_client_id": str(cfg.get("cli_client_id") or ""),
        "cli_authorization_url": str(cfg.get("cli_authorization_url") or ""),
        "cli_token_url": str(cfg.get("cli_token_url") or ""),
        "cli_oauth_secrets_file": str(cfg.get("cli_oauth_secrets_file") or ""),
        "cli_secret_ref": str(cfg.get("cli_secret_ref") or ""),
    }
    path.write_text(
        yaml.safe_dump(safe, sort_keys=True, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _file_cfg(settings: Any) -> dict[str, Any]:
    return read_connector_config(getattr(settings, "connector_file", "datasphere.yml"))


def effective_space_id(settings: Any) -> str:
    """Effective space: env var wins, then datasphere.yml."""
    env_val = str(getattr(settings, "datasphere_space_id", "") or "")
    if env_val:
        return env_val
    return str(_file_cfg(settings).get("space_id") or "")


def effective_use_cli(settings: Any) -> bool:
    """Effective use_cli: env var wins (True → True), then datasphere.yml."""
    if getattr(settings, "datasphere_use_cli", False):
        return True
    return bool(_file_cfg(settings).get("use_cli", False))


def effective_cli_host(settings: Any) -> str:
    """Effective CLI tenant host: DSP_CLI_HOST env wins, then datasphere.yml.

    ``DatasphereCli`` honours ``DSP_CLI_HOST`` from the environment directly; this
    helper lets callers also pass a UI-configured host into the CLI explicitly.
    """
    env_val = str(os.environ.get("DSP_CLI_HOST", "") or "")
    if env_val:
        return env_val
    settings_val = str(getattr(settings, "datasphere_cli_host", "") or "")
    if settings_val:
        return settings_val
    file_cfg = _file_cfg(settings)
    file_host = str(file_cfg.get("cli_host") or "")
    if file_host:
        return file_host
    return str(getattr(settings, "datasphere_base_url", "") or file_cfg.get("base_url") or "")


def effective_base_url(settings: Any) -> str:
    """Effective REST catalog base URL: env var wins, then datasphere.yml."""
    env_val = str(getattr(settings, "datasphere_base_url", "") or "")
    if env_val:
        return env_val
    return str(_file_cfg(settings).get("base_url") or "")


def effective_client_id(settings: Any) -> str:
    """Effective OAuth2 client id: env var wins, then datasphere.yml."""
    env_val = str(getattr(settings, "datasphere_client_id", "") or "")
    if env_val:
        return env_val
    return str(_file_cfg(settings).get("client_id") or "")


def effective_authorization_url(settings: Any) -> str:
    """Effective CLI OAuth2 authorization URL: CLI env wins, then legacy shared, then file."""
    env_val = str(getattr(settings, "datasphere_cli_authorization_url", "") or "")
    if env_val:
        return env_val
    legacy_val = str(getattr(settings, "datasphere_authorization_url", "") or "")
    if legacy_val:
        return legacy_val
    return str(_file_cfg(settings).get("cli_authorization_url") or "")


def effective_token_url(settings: Any) -> str:
    """Effective OAuth2 token URL override: env var wins, then datasphere.yml."""
    env_val = str(getattr(settings, "datasphere_token_url", "") or "")
    if env_val:
        return env_val
    return str(_file_cfg(settings).get("token_url") or "")


def effective_cli_client_id(settings: Any) -> str:
    """Effective CLI OAuth client id: CLI-specific config wins, then REST fallback."""
    env_val = str(getattr(settings, "datasphere_cli_client_id", "") or "")
    if env_val:
        return env_val
    file_val = str(_file_cfg(settings).get("cli_client_id") or "")
    if file_val:
        return file_val
    return effective_client_id(settings)


def effective_cli_token_url(settings: Any) -> str:
    """Effective CLI OAuth token URL: CLI-specific config wins, then shared fallback."""
    env_val = str(getattr(settings, "datasphere_cli_token_url", "") or "")
    if env_val:
        return env_val
    file_val = str(_file_cfg(settings).get("cli_token_url") or "")
    if file_val:
        return file_val
    return effective_token_url(settings)


def effective_oauth_secrets_file(settings: Any) -> str:
    """Effective Datasphere CLI OAuth secrets-file path: env var wins, then file."""
    env_val = str(getattr(settings, "datasphere_oauth_secrets_file", "") or "")
    if env_val:
        return env_val
    return str(_file_cfg(settings).get("oauth_secrets_file") or "")


def effective_cli_oauth_secrets_file(settings: Any) -> str:
    """Effective CLI secrets-file path: CLI-specific config wins, then shared fallback."""
    env_val = str(getattr(settings, "datasphere_cli_oauth_secrets_file", "") or "")
    if env_val:
        return env_val
    file_val = str(_file_cfg(settings).get("cli_oauth_secrets_file") or "")
    if file_val:
        return file_val
    return effective_oauth_secrets_file(settings)


def effective_secret_ref(settings: Any) -> str:
    """Reference under which the client secret is resolved (never the value).

    Env ``DATASPHERE_CLIENT_SECRET`` (if set) is exposed as the bare-name ref so
    status checks and resolution share one code path; otherwise the file's
    ``secret_ref`` is used.
    """
    if str(getattr(settings, "datasphere_client_secret", "") or ""):
        return DEFAULT_SECRET_REF
    return str(_file_cfg(settings).get("secret_ref") or "")


def effective_cli_secret_ref(settings: Any) -> str:
    """Reference under which the CLI client secret is resolved."""
    if str(getattr(settings, "datasphere_cli_client_secret", "") or ""):
        return DEFAULT_CLI_SECRET_REF
    cli_ref = str(_file_cfg(settings).get("cli_secret_ref") or "")
    if cli_ref:
        return cli_ref
    return effective_secret_ref(settings)


def effective_client_secret(settings: Any) -> str:
    """Resolve the client secret VALUE for the immediate consumer (the client).

    Order: explicit env ``DATASPHERE_CLIENT_SECRET`` → secret resolver applied to
    the configured ``secret_ref``. Returns ``""`` when nothing is configured. The
    value must never be logged or returned to clients (S-13).
    """
    env_val = str(getattr(settings, "datasphere_client_secret", "") or "")
    if env_val:
        return env_val
    ref = str(_file_cfg(settings).get("secret_ref") or "")
    if not ref:
        return ""
    from .secrets import get_secret
    return get_secret(ref) or ""


def effective_cli_client_secret(settings: Any) -> str:
    """Resolve the CLI client secret value, falling back to the REST secret."""
    env_val = str(getattr(settings, "datasphere_cli_client_secret", "") or "")
    if env_val:
        return env_val
    cli_ref = str(_file_cfg(settings).get("cli_secret_ref") or "")
    if cli_ref:
        from .secrets import get_secret
        return get_secret(cli_ref) or ""
    return effective_client_secret(settings)


def secret_configured(settings: Any) -> bool:
    """True when a client secret resolves (env or via the configured ref)."""
    if str(getattr(settings, "datasphere_client_secret", "") or ""):
        return True
    ref = str(_file_cfg(settings).get("secret_ref") or "")
    if not ref:
        return False
    from .secrets import secret_status
    return secret_status(ref)


def cli_secret_configured(settings: Any) -> bool:
    """True when a CLI client secret resolves (or falls back to the REST secret)."""
    if str(getattr(settings, "datasphere_cli_client_secret", "") or ""):
        return True
    ref = str(_file_cfg(settings).get("cli_secret_ref") or "")
    if ref:
        from .secrets import secret_status
        return secret_status(ref)
    return secret_configured(settings)
