"""@sap/datasphere-cli Wrapper (TASK B) — alle subprocess-Aufrufe gemockt.

Keine echten CLI-Aufrufe: ``subprocess.run`` wird per monkeypatch durch
kanonisierte stdout/stderr-Ergebnisse ersetzt. Abgedeckt:
  - CLI-Auflösung (DSP_CLI_PATH / which / %APPDATA%) inkl. win32-COMSPEC-Wrap
  - ANSI-Stripping vor json.loads
  - Auth-Prompt- und 401/403-Erkennung → CliAuthError mit Login-Hinweis
  - 429 Backoff-Retry, Timeout → CliTimeoutError
  - Paging in list_objects + FALLBACK_SELECT_FIELDS-Toleranz
  - DSP_CLI_HOST wird als --host angehängt
  - read_object accept='csn' → CSN-Header
Synthetische Fixtures only (Sales_Orders, v_Demo) — keine Kundendaten.
"""
import ntpath
import subprocess

import pytest

from services.api import datasphere_cli
from services.api.datasphere_cli import (
    CSN_ACCEPT,
    FALLBACK_SELECT_FIELDS,
    CliAuthError,
    CliError,
    CliTimeoutError,
    DatasphereCli,
    normalize_list_payload,
    _is_auth_error,
    _is_rate_limit,
    _looks_like_auth_prompt,
    _strip_terminal_control,
)


# ----------------------------------------------------------------------
# subprocess.run fake plumbing
# ----------------------------------------------------------------------

def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _RunRecorder:
    """Records each subprocess.run call and replays scripted results."""

    def __init__(self, results):
        # results: a single CompletedProcess, a callable, or a list (queue).
        self._results = results
        self.calls: list[dict] = []

    def __call__(self, command, **kwargs):
        self.calls.append({"command": command, "kwargs": kwargs})
        res = self._results
        if isinstance(res, list):
            item = res[min(len(self.calls) - 1, len(res) - 1)]
        else:
            item = res
        if callable(item):
            return item(command, **kwargs)
        if isinstance(item, BaseException):
            raise item
        return item


def _patch_run(monkeypatch, results):
    rec = _RunRecorder(results)
    monkeypatch.setattr(datasphere_cli.subprocess, "run", rec)
    return rec


def _cli(monkeypatch, **kw):
    """Build a DatasphereCli with a pre-resolved (fake) cli command."""
    cli = DatasphereCli(**kw)
    cli._cli_cmd = ["datasphere"]
    return cli


# ----------------------------------------------------------------------
# CLI resolution
# ----------------------------------------------------------------------

def test_resolve_cli_prefers_dsp_cli_path_on_win32(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "nt")
    monkeypatch.setenv("DSP_CLI_PATH", r"C:\tools\datasphere.cmd")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    cmd = DatasphereCli()._resolve_cli()
    assert cmd == [r"C:\Windows\System32\cmd.exe", "/c", r"C:\tools\datasphere.cmd"]


def test_resolve_cli_uses_which_then_comspec_wrap_on_win32(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "nt")
    monkeypatch.delenv("DSP_CLI_PATH", raising=False)
    monkeypatch.setenv("COMSPEC", "cmd.exe")
    monkeypatch.setattr(
        datasphere_cli.shutil,
        "which",
        lambda name: r"C:\npm\datasphere.cmd" if name == "datasphere.cmd" else None,
    )
    cmd = DatasphereCli()._resolve_cli()
    assert cmd == ["cmd.exe", "/c", r"C:\npm\datasphere.cmd"]


def test_resolve_cli_falls_back_to_appdata_npm_on_win32(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "nt")
    # Faithfully simulate Windows path semantics: os.path.join must emit
    # backslashes, otherwise on a POSIX runner the candidate never matches the
    # monkeypatched exists() and resolution wrongly falls through.
    monkeypatch.setattr(datasphere_cli.os, "path", ntpath)
    monkeypatch.delenv("DSP_CLI_PATH", raising=False)
    monkeypatch.setenv("COMSPEC", "cmd.exe")
    monkeypatch.setenv("APPDATA", r"C:\Users\demo\AppData\Roaming")
    monkeypatch.setattr(datasphere_cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        ntpath,
        "exists",
        lambda p: p == r"C:\Users\demo\AppData\Roaming\npm\datasphere.cmd",
    )
    cmd = DatasphereCli()._resolve_cli()
    assert cmd == ["cmd.exe", "/c", r"C:\Users\demo\AppData\Roaming\npm\datasphere.cmd"]


def test_resolve_cli_raises_when_not_found_on_win32(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "nt")
    monkeypatch.delenv("DSP_CLI_PATH", raising=False)
    monkeypatch.setenv("APPDATA", r"C:\Users\demo\AppData\Roaming")
    monkeypatch.setattr(datasphere_cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(datasphere_cli.os.path, "exists", lambda p: False)
    with pytest.raises(CliError, match="datasphere.cmd"):
        DatasphereCli()._resolve_cli()


def test_resolve_cli_posix_uses_which(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "posix")
    monkeypatch.delenv("DSP_CLI_PATH", raising=False)
    monkeypatch.setattr(
        datasphere_cli.shutil, "which", lambda name: "/usr/local/bin/datasphere"
    )
    assert DatasphereCli()._resolve_cli() == ["/usr/local/bin/datasphere"]


def test_is_available_true_and_false(monkeypatch):
    monkeypatch.setattr(datasphere_cli.os, "name", "posix")
    monkeypatch.setattr(
        datasphere_cli.shutil, "which", lambda name: "/usr/local/bin/datasphere"
    )
    assert DatasphereCli().is_available() is True

    monkeypatch.delenv("DSP_CLI_PATH", raising=False)
    monkeypatch.setattr(datasphere_cli.shutil, "which", lambda name: None)
    assert DatasphereCli().is_available() is False


# ----------------------------------------------------------------------
# ANSI stripping + JSON parsing
# ----------------------------------------------------------------------

def test_strip_terminal_control_removes_ansi():
    raw = "\x1b[32m[{\"a\": 1}]\x1b[0m"
    assert _strip_terminal_control(raw) == '[{"a": 1}]'


def test_run_cli_json_strips_ansi_before_parsing(monkeypatch):
    cli = _cli(monkeypatch)
    ansi_json = '\x1b[1m\x1b[32m[{"technicalName": "v_Demo"}]\x1b[0m\n'
    _patch_run(monkeypatch, _completed(stdout=ansi_json))
    result = cli.run_cli_json(["objects", "views", "list"])
    assert result == [{"technicalName": "v_Demo"}]


def test_run_cli_json_empty_stdout_returns_none(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(stdout="   \n"))
    assert cli.run_cli_json(["spaces", "list"]) is None


def test_run_cli_json_non_json_raises_clierror(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(stdout="not json at all"))
    with pytest.raises(CliError, match="Nicht-JSON"):
        cli.run_cli_json(["spaces", "list"])


# ----------------------------------------------------------------------
# Auth detection / mapping
# ----------------------------------------------------------------------

def test_auth_prompt_in_stdout_maps_to_cliautherror(monkeypatch):
    cli = _cli(monkeypatch)
    prompt = "Please enter your client id and temporary authentication code:"
    # configured_cli_host() also runs subprocess.run; return a host for the hint.
    _patch_run(monkeypatch, _completed(stdout=prompt))
    with pytest.raises(CliAuthError) as exc:
        cli.run_cli_json(["objects", "views", "list"])
    assert "datasphere login" in str(exc.value)


def test_auth_error_message_includes_configured_host(monkeypatch):
    cli = _cli(monkeypatch)

    def fake_run(command, **kwargs):
        if command[-3:] == ["config", "host", "show"]:
            return _completed(stdout="demo.tenant.example\n")
        return _completed(returncode=1, stderr="HTTP 401 Unauthorized")

    _patch_run(monkeypatch, fake_run)
    with pytest.raises(CliAuthError) as exc:
        cli.run_cli_json(["objects", "views", "list"], retries=0)
    assert "datasphere login --host demo.tenant.example" in str(exc.value)


def test_401_in_stderr_maps_to_cliautherror(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=1, stderr="403 Forbidden"))
    with pytest.raises(CliAuthError):
        cli.run_cli_json(["objects", "views", "list"], retries=0)


def test_helper_detectors():
    assert _looks_like_auth_prompt("Temporary authentication code")
    assert not _looks_like_auth_prompt("everything fine")
    assert _is_auth_error("got 401 here")
    assert _is_auth_error("UNAUTHORIZED")
    assert not _is_auth_error("all good")
    assert _is_rate_limit("429 Too Many Requests")
    assert not _is_rate_limit("ok")


# ----------------------------------------------------------------------
# Retries / rate-limit / timeout
# ----------------------------------------------------------------------

def test_rate_limit_backoff_then_success(monkeypatch):
    cli = _cli(monkeypatch, retries=2, retry_delay_sec=0)
    monkeypatch.setattr(datasphere_cli.time, "sleep", lambda *_: None)
    results = [
        _completed(returncode=1, stderr="429 rate limit exceeded"),
        _completed(returncode=0, stdout='[{"id": "ok"}]'),
    ]
    rec = _patch_run(monkeypatch, results)
    assert cli.run_cli_json(["spaces", "list"]) == [{"id": "ok"}]
    assert len(rec.calls) == 2


def test_timeout_exhausts_retries_raises_clitimeouterror(monkeypatch):
    cli = _cli(monkeypatch, retries=1)
    monkeypatch.setattr(datasphere_cli.time, "sleep", lambda *_: None)
    err = subprocess.TimeoutExpired(cmd="datasphere", timeout=1)
    _patch_run(monkeypatch, err)
    with pytest.raises(CliTimeoutError):
        cli.run_cli_json(["spaces", "list"])


def test_filenotfound_maps_to_clierror(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, FileNotFoundError("no such file"))
    with pytest.raises(CliError, match="nicht gestartet"):
        cli.run_cli_json(["spaces", "list"], retries=0)


def test_nonzero_returncode_raises_clierror(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=2, stderr="boom"))
    with pytest.raises(CliError, match="rc=2"):
        cli.run_cli_json(["spaces", "list"], retries=0)


# ----------------------------------------------------------------------
# Argument shape: shell=False, stdin=DEVNULL, DSP_CLI_HOST, --host
# ----------------------------------------------------------------------

def test_run_once_uses_safe_subprocess_invocation(monkeypatch):
    cli = _cli(monkeypatch)
    monkeypatch.delenv("DSP_CLI_HOST", raising=False)
    rec = _patch_run(monkeypatch, _completed(stdout="[]"))
    cli.run_cli_json(["spaces", "list"])
    kwargs = rec.calls[0]["kwargs"]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_dsp_cli_host_appended_as_host(monkeypatch):
    cli = _cli(monkeypatch)
    monkeypatch.setenv("DSP_CLI_HOST", "demo.tenant.example")
    rec = _patch_run(monkeypatch, _completed(stdout="[]"))
    cli.run_cli_json(["spaces", "list"])
    assert rec.calls[0]["command"][-2:] == ["--host", "demo.tenant.example"]


def test_dsp_cli_host_not_duplicated_when_present(monkeypatch):
    cli = _cli(monkeypatch)
    monkeypatch.setenv("DSP_CLI_HOST", "demo.tenant.example")
    rec = _patch_run(monkeypatch, _completed(stdout="[]"))
    cli.run_cli_json(["spaces", "list", "--host", "explicit.example"])
    cmd = rec.calls[0]["command"]
    assert cmd.count("--host") == 1
    assert "explicit.example" in cmd


# ----------------------------------------------------------------------
# configured_cli_host / check_login
# ----------------------------------------------------------------------

def test_configured_cli_host_strips_and_returns(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(stdout="\x1b[36mdemo.tenant.example\x1b[0m\n"))
    assert cli.configured_cli_host() == "demo.tenant.example"


def test_configured_cli_host_none_on_failure(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=1, stderr="nope"))
    assert cli.configured_cli_host() is None


def test_check_login_true_when_secrets_check_ok(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(stdout="ok"))
    assert cli.check_login() is True


def test_check_login_false_when_both_checks_fail(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=1, stderr="generic failure"))
    assert cli.check_login() is False


def test_check_login_uses_later_probe_when_earlier_unsupported(monkeypatch):
    """An existing login is detected even if early probe subcommands are unknown.

    Tolerance across @sap/datasphere-cli versions: the first probes return a
    generic non-zero (unknown subcommand), a later one (e.g. whoami) succeeds.
    """
    cli = _cli(monkeypatch)
    results = [
        _completed(returncode=1, stderr="unknown command 'secrets check'"),
        _completed(returncode=1, stderr="unknown command 'secrets show'"),
        _completed(returncode=1, stderr="unknown flag --check"),
        _completed(returncode=0, stdout="logged in as svc_user"),
    ]
    _patch_run(monkeypatch, results)
    assert cli.check_login() is True


def test_host_param_appended_when_env_unset(monkeypatch):
    monkeypatch.delenv("DSP_CLI_HOST", raising=False)
    cli = _cli(monkeypatch, host="tenant.example")
    rec = _patch_run(monkeypatch, _completed(stdout="[]"))
    cli.run_cli_json(["spaces", "list"])
    assert rec.calls[0]["command"][-2:] == ["--host", "tenant.example"]


def test_env_host_wins_over_host_param(monkeypatch):
    monkeypatch.setenv("DSP_CLI_HOST", "env.tenant")
    cli = _cli(monkeypatch, host="param.tenant")
    rec = _patch_run(monkeypatch, _completed(stdout="[]"))
    cli.run_cli_json(["spaces", "list"])
    cmd = rec.calls[0]["command"]
    assert cmd.count("--host") == 1
    assert "env.tenant" in cmd and "param.tenant" not in cmd


def test_check_login_propagates_auth_error(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=1, stderr="401 Unauthorized"))
    with pytest.raises(CliAuthError):
        cli.check_login()


def test_login_command_matches_meridian_oauth_overrides(monkeypatch, tmp_path):
    secrets_file = str(tmp_path / "datasphere-secrets.json")
    cli = _cli(
        monkeypatch,
        host="https://tenant.example",
        client_id="cli-client",
        authorization_url="https://auth.example/oauth/authorize",
        token_url="https://auth.example/oauth/token",
        secrets_file=secrets_file,
    )
    assert cli.login_args() == [
        "login",
        "--host", "https://tenant.example",
        "--client-id", "cli-client",
        "--authorization-url", "https://auth.example/oauth/authorize",
        "--token-url", "https://auth.example/oauth/token",
        "--secrets-file", secrets_file,
    ]
    command = cli.login_command()
    assert command.startswith("datasphere login --host https://tenant.example")
    assert "--client-id cli-client" in command
    assert "--authorization-url https://auth.example/oauth/authorize" in command
    assert "--token-url https://auth.example/oauth/token" in command
    assert f"--secrets-file {secrets_file}" in command


def test_open_login_cmd_starts_visible_windows_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(datasphere_cli.os, "name", "nt")
    monkeypatch.setenv("COMSPEC", "cmd.exe")
    cli = DatasphereCli(
        host="https://tenant.example",
        client_id="cli-client",
        client_secret="cli-secret",
        token_url="https://auth.example/oauth/token",
        secrets_file=str(tmp_path / "secrets.json"),
    )
    cli._cli_cmd = ["cmd.exe", "/c", r"C:\tools\datasphere.cmd"]
    calls = []

    class _Proc:
        pass

    def fake_popen(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return _Proc()

    monkeypatch.setattr(datasphere_cli.subprocess, "Popen", fake_popen)
    display = cli.open_login_cmd()
    assert display.startswith("datasphere login --host https://tenant.example")
    assert "--client-id cli-client" in display
    assert "cli-secret" not in display
    assert calls[0]["command"][0:2] == ["cmd.exe", "/k"]
    assert r"C:\tools\datasphere.cmd" in calls[0]["command"][2]
    assert "--client-id cli-client" in calls[0]["command"][2]
    assert "--client-secret cli-secret" in calls[0]["command"][2]
    assert "--token-url https://auth.example/oauth/token" in calls[0]["command"][2]
    assert calls[0]["kwargs"]["shell"] is False


def test_auth_error_message_includes_oauth_login_command(monkeypatch, tmp_path):
    cli = _cli(
        monkeypatch,
        authorization_url="https://auth.example/oauth/authorize",
        token_url="https://auth.example/oauth/token",
        secrets_file=str(tmp_path / "secrets.json"),
    )

    def fake_run(command, **kwargs):
        if command[-3:] == ["config", "host", "show"]:
            return _completed(stdout="https://tenant.example\n")
        return _completed(returncode=1, stderr="HTTP 401 Unauthorized")

    _patch_run(monkeypatch, fake_run)
    with pytest.raises(CliAuthError) as exc:
        cli.run_cli_json(["objects", "views", "list"], retries=0)
    message = str(exc.value)
    assert "datasphere login --host https://tenant.example" in message
    assert "--authorization-url https://auth.example/oauth/authorize" in message
    assert "--token-url https://auth.example/oauth/token" in message
    assert "--secrets-file" in message


# ----------------------------------------------------------------------
# list_spaces / list_objects paging + fallback
# ----------------------------------------------------------------------

def test_list_spaces_normalizes_value_envelope(monkeypatch):
    cli = _cli(monkeypatch)
    payload = '{"value": [{"name": "DEMO_SPACE"}, {"name": "OTHER_SPACE"}]}'
    _patch_run(monkeypatch, _completed(stdout=payload))
    spaces = cli.list_spaces()
    assert [s["name"] for s in spaces] == ["DEMO_SPACE", "OTHER_SPACE"]


def test_list_objects_returns_items_single_page(monkeypatch):
    cli = _cli(monkeypatch)
    page = '[{"technicalName": "Sales_Orders"}, {"technicalName": "v_Demo"}]'
    _patch_run(monkeypatch, _completed(stdout=page))
    objs = cli.list_objects("DEMO_SPACE", object_type="views")
    assert [o["technicalName"] for o in objs] == ["Sales_Orders", "v_Demo"]


def test_list_objects_falls_back_to_fallback_select_fields(monkeypatch):
    cli = _cli(monkeypatch)

    def fake_run(command, **kwargs):
        # First call (full select) fails; fallback call (FALLBACK fields) ok.
        if FALLBACK_SELECT_FIELDS in command:
            return _completed(stdout='[{"technicalName": "v_Demo"}]')
        return _completed(returncode=1, stderr="unknown select field 'type'")

    rec = _patch_run(monkeypatch, fake_run)
    objs = cli.list_objects("DEMO_SPACE", object_type="views")
    assert [o["technicalName"] for o in objs] == ["v_Demo"]
    # Two underlying CLI calls: full attempt + fallback attempt.
    assert len(rec.calls) == 2
    assert FALLBACK_SELECT_FIELDS in rec.calls[1]["command"]


def test_list_objects_auth_error_propagates(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(returncode=1, stderr="401 Unauthorized"))
    with pytest.raises(CliAuthError):
        cli.list_objects("DEMO_SPACE", object_type="views")


# ----------------------------------------------------------------------
# read_object — CSN accept header
# ----------------------------------------------------------------------

def test_read_object_uses_csn_accept_header(monkeypatch):
    cli = _cli(monkeypatch)
    rec = _patch_run(
        monkeypatch, _completed(stdout='{"definitions": {"v_Demo": {"kind": "entity"}}}')
    )
    obj = cli.read_object("DEMO_SPACE", "v_Demo", object_type="views", accept="csn")
    assert "definitions" in obj
    cmd = rec.calls[0]["command"]
    assert "--accept" in cmd
    assert CSN_ACCEPT in cmd
    assert "--technical-name" in cmd and "v_Demo" in cmd


def test_read_object_passthrough_accept_header(monkeypatch):
    cli = _cli(monkeypatch)
    rec = _patch_run(monkeypatch, _completed(stdout='{"ok": true}'))
    cli.read_object("DEMO_SPACE", "v_Demo", accept="application/json")
    assert "application/json" in rec.calls[0]["command"]


def test_read_object_non_dict_raises(monkeypatch):
    cli = _cli(monkeypatch)
    _patch_run(monkeypatch, _completed(stdout="[1, 2, 3]"))
    with pytest.raises(CliError, match="Erwartete Objekt-JSON"):
        cli.read_object("DEMO_SPACE", "v_Demo")


# ----------------------------------------------------------------------
# normalize_list_payload
# ----------------------------------------------------------------------

def test_normalize_list_payload_shapes():
    assert normalize_list_payload(None) == []
    assert normalize_list_payload([{"a": 1}, "skip", 5]) == [{"a": 1}]
    assert normalize_list_payload({"items": [{"x": 1}]}) == [{"x": 1}]
    # Flat scalar dict treated as a single record.
    assert normalize_list_payload({"name": "Sales_Orders"}) == [{"name": "Sales_Orders"}]
    # Dict with no recognised list key and nested structures → empty.
    assert normalize_list_payload({"meta": {"nested": 1}}) == []
