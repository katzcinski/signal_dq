"""data-loads Space-Aufloesung: explizit > env > connector.yml (UI).

Regression: _resolve_space las frueher nur DATASPHERE_SPACE_ID (env). Nach der
Connector-UI-Arbeit muss ein via datasphere.yml gesetzter Space ebenfalls greifen,
konsistent zu datasphere.get_client.
"""
from __future__ import annotations


def _reset_settings(monkeypatch, tmp_path, *, env_space: str | None, file_space: str | None):
    import services.api.datasphere as datasphere_mod
    import services.api.datasphere_catalog as catalog_mod
    import services.api.settings as settings_mod
    from services.api.connector_config import write_connector_config

    connector_file = tmp_path / "datasphere.yml"
    if file_space is not None:
        write_connector_config(str(connector_file), {"space_id": file_space})

    for key in (
        "DATASPHERE_BASE_URL",
        "DATASPHERE_CLIENT_ID",
        "DATASPHERE_CLIENT_SECRET",
        "DATASPHERE_AUTHORIZATION_URL",
        "DATASPHERE_TOKEN_URL",
        "DATASPHERE_OAUTH_SECRETS_FILE",
        "DATASPHERE_MONITORING_SPACE",
    ):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("CONNECTOR_FILE", str(connector_file))
    monkeypatch.setenv("DATASPHERE_USE_CLI", "false")
    if env_space is None:
        monkeypatch.setenv("DATASPHERE_SPACE_ID", "")
    else:
        monkeypatch.setenv("DATASPHERE_SPACE_ID", env_space)
    settings_mod._settings = None
    datasphere_mod.reset_client()
    catalog_mod.reset_catalog_client()


def test_resolve_space_falls_back_to_connector_file(monkeypatch, tmp_path):
    from services.api.routers.data_loads import _resolve_space

    _reset_settings(monkeypatch, tmp_path, env_space=None, file_space="UI_SPACE")
    assert _resolve_space(None) == "UI_SPACE"


def test_resolve_space_env_wins_over_file(monkeypatch, tmp_path):
    from services.api.routers.data_loads import _resolve_space

    _reset_settings(monkeypatch, tmp_path, env_space="ENV_SPACE", file_space="UI_SPACE")
    assert _resolve_space(None) == "ENV_SPACE"


def test_resolve_space_explicit_arg_wins(monkeypatch, tmp_path):
    from services.api.routers.data_loads import _resolve_space

    _reset_settings(monkeypatch, tmp_path, env_space="ENV_SPACE", file_space="UI_SPACE")
    assert _resolve_space("ARG_SPACE") == "ARG_SPACE"


def test_resolve_space_empty_when_nothing_configured(monkeypatch, tmp_path):
    from services.api.routers.data_loads import _resolve_space

    _reset_settings(monkeypatch, tmp_path, env_space=None, file_space=None)
    assert _resolve_space(None) == ""
