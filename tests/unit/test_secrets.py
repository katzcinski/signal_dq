"""Tests für den env-backed Secret-Resolver (services.api.secrets).

Nutzt nur synthetische Var-Namen/Werte; keine echten Credentials.
"""
from __future__ import annotations

import logging

from services.api import secrets
from services.api.secrets import (
    EnvSecretResolver,
    SecretResolver,
    get_secret,
    secret_status,
)


# ---- env: resolution ----

def test_env_prefix_resolves_from_environ(monkeypatch):
    monkeypatch.setenv("HANA_PW_DEMO", "s3cr3t-demo")
    r = EnvSecretResolver()
    assert r.get("env:HANA_PW_DEMO") == "s3cr3t-demo"


def test_env_prefix_with_whitespace(monkeypatch):
    monkeypatch.setenv("HANA_PW_DEMO", "val")
    r = EnvSecretResolver()
    assert r.get("  env: HANA_PW_DEMO  ") == "val"


# ---- bare VAR_NAME resolution ----

def test_bare_name_resolves_from_environ(monkeypatch):
    monkeypatch.setenv("DEMO_TOKEN", "tok-123")
    r = EnvSecretResolver()
    assert r.get("DEMO_TOKEN") == "tok-123"


# ---- plain: passthrough ----

def test_plain_prefix_passthrough():
    r = EnvSecretResolver()
    assert r.get("plain:literal-value") == "literal-value"


def test_plain_prefix_warns_without_logging_value(caplog):
    r = EnvSecretResolver()
    with caplog.at_level(logging.WARNING, logger=secrets.LOGGER.name):
        value = r.get("plain:super-secret-xyz")
    assert value == "super-secret-xyz"
    # Gewarnt wird, aber der Wert darf nicht im Log-Text auftauchen.
    assert any("plain:" in rec.getMessage() for rec in caplog.records)
    assert all("super-secret-xyz" not in rec.getMessage() for rec in caplog.records)


def test_plain_empty_value_is_none():
    r = EnvSecretResolver()
    assert r.get("plain:") is None


# ---- missing -> None ----

def test_missing_env_var_returns_none(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST_XYZ", raising=False)
    r = EnvSecretResolver()
    assert r.get("env:DOES_NOT_EXIST_XYZ") is None
    assert r.get("DOES_NOT_EXIST_XYZ") is None


def test_empty_env_var_returns_none(monkeypatch):
    monkeypatch.setenv("EMPTY_VAR", "")
    r = EnvSecretResolver()
    assert r.get("env:EMPTY_VAR") is None


def test_none_and_blank_ref_return_none():
    r = EnvSecretResolver()
    assert r.get(None) is None
    assert r.get("") is None
    assert r.get("   ") is None
    assert r.get("env:") is None
    assert r.get("env:   ") is None


# ---- status booleans ----

def test_status_true_when_present(monkeypatch):
    monkeypatch.setenv("PRESENT_PW", "x")
    r = EnvSecretResolver()
    assert r.status("env:PRESENT_PW") is True


def test_status_false_when_missing(monkeypatch):
    monkeypatch.delenv("ABSENT_PW", raising=False)
    r = EnvSecretResolver()
    assert r.status("env:ABSENT_PW") is False
    assert r.status(None) is False
    assert r.status("") is False


def test_status_true_for_plain():
    r = EnvSecretResolver()
    assert r.status("plain:dev-only") is True


# ---- available() ----

def test_available_is_true():
    assert EnvSecretResolver().available() is True


# ---- module helpers use a default EnvSecretResolver ----

def test_get_secret_helper(monkeypatch):
    monkeypatch.setenv("HELPER_PW", "helper-val")
    assert get_secret("env:HELPER_PW") == "helper-val"
    assert get_secret("env:HELPER_MISSING") is None


def test_secret_status_helper(monkeypatch):
    monkeypatch.setenv("HELPER_PW2", "v")
    assert secret_status("env:HELPER_PW2") is True
    assert secret_status("env:HELPER_MISSING2") is False


def test_default_resolver_is_env_resolver():
    # After F5, init_resolver() changes the default to ChainedSecretResolver (includes EnvSecretResolver).
    # In a fresh module state it's still EnvSecretResolver. Accept both.
    from services.api.secrets import ChainedSecretResolver
    assert isinstance(secrets.default_resolver(), (EnvSecretResolver, ChainedSecretResolver))


# ---- Protocol conformance ----

def test_env_resolver_satisfies_protocol():
    # runtime_checkable Protocol: EnvSecretResolver erfüllt SecretResolver.
    assert isinstance(EnvSecretResolver(), SecretResolver)
