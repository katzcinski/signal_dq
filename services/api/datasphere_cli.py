"""@sap/datasphere-cli Wrapper — operator-Pfad mit reichster CSN-Abdeckung.

Optionaler Pfad neben dem REST-Client (``datasphere.py``): wo der SAP
``@sap/datasphere-cli`` lokal installiert und eingeloggt ist, liefert er die
vollständigsten Objektdefinitionen (CSN), aus denen ``_csn_reconstructor`` /
``_column_lineage`` Lineage rekonstruieren.

Dieses Modul ist bewusst framework-frei (nur stdlib: subprocess/shutil/json/os/
re/time) — es lebt in ``services`` benötigt aber kein FastAPI.

Konfiguration über Environment:
  DSP_CLI_PATH   expliziter Pfad zur ``datasphere`` / ``datasphere.cmd``
  DSP_CLI_HOST   Tenant-Host; wird als ``--host`` angehängt, wenn nicht gesetzt
  COMSPEC        Windows-Shell-Wrapper (Default ``cmd.exe``)
  APPDATA        Windows npm-Installationsverzeichnis (Fallback-Auflösung)

Sicherheit:
  - subprocess immer in Array-Form (``shell=False``), ``stdin=DEVNULL`` — kein
    Shell-Injection-Vektor, kein Hängen an interaktiven Prompts.
  - Auth-Prompt-Erkennung mappt auf ``CliAuthError`` mit umsetzbarem
    ``datasphere login --host <host>`` Hinweis (nie Secrets loggen).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("dq_cockpit.datasphere_cli")

DEFAULT_TIMEOUT_SEC = 30
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY_SEC = 60
PAGE_SIZE = 200

# Vollständige select-Felder; bei CLI-Inkompatibilität fällt list_objects auf
# diese tolerante Teilmenge zurück (ältere/abweichende CLI-Versionen).
DEFAULT_SELECT_FIELDS = "technicalName,businessName,semanticUsage,status,type"
FALLBACK_SELECT_FIELDS = "technicalName,businessName,semanticUsage,status"

# CSN-Content-Type für read_object --accept=csn.
CSN_ACCEPT = "application/vnd.sap.datasphere.object.content+json"

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

_AUTH_PROMPT_MARKERS = (
    "authentication code",
    "temporary authentication code",
    "passcode",
    "do you want to retrieve",
    "please enter your client id",
    "secrets file at location",
)


class CliError(RuntimeError):
    """Basis-Exception für Datasphere-CLI-Fehler."""


class CliAuthError(CliError):
    """CLI verlangt einen interaktiven Login (401/403/Auth-Prompt)."""


class CliTimeoutError(CliError):
    """CLI-Kommando hat sein Timeout auch nach allen Retries überschritten."""


@dataclass(frozen=True)
class CliResult:
    """Rohes Prozessergebnis eines CLI-Aufrufs."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


class DatasphereCli:
    """Dünner, nicht-interaktiver Wrapper um ``@sap/datasphere-cli``.

    Eine Instanz cached den aufgelösten CLI-Befehl (``_cli_cmd``). Alle Aufrufe
    laufen über ``_run_cli_with_retries`` (Timeout + Retries + 429-Backoff +
    401/403→CliAuthError). Stateless gegenüber dem CLI-Login-Status — dieser
    lebt im CLI-Secrets-Store, nicht in dieser Klasse.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        authorization_url: str | None = None,
        token_url: str | None = None,
        secrets_file: str | None = None,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        retries: int = DEFAULT_RETRIES,
        retry_delay_sec: int = DEFAULT_RETRY_DELAY_SEC,
    ) -> None:
        # UI-configured tenant host. ``DSP_CLI_HOST`` in the environment still
        # wins (resolved per-call in ``_run_cli_once``); this is the fallback so
        # the host can also be set from the connector UI.
        self._host = (host or "").strip() or None
        self._client_id = (client_id or "").strip() or None
        self._client_secret = (client_secret or "").strip() or None
        self._authorization_url = (authorization_url or "").strip() or None
        self._token_url = (token_url or "").strip() or None
        self._secrets_file = (secrets_file or "").strip() or None
        self.timeout_sec = timeout_sec
        self.retries = retries
        self.retry_delay_sec = retry_delay_sec
        self._cli_cmd: list[str] | None = None
        # Re-entry guard: building an auth-error message queries the configured
        # host via the CLI, which can itself surface an auth error. Without this
        # flag that would recurse infinitely.
        self._building_auth_message = False

    # ------------------------------------------------------------------
    # CLI resolution / availability
    # ------------------------------------------------------------------

    def _resolve_cli(self) -> list[str]:
        """Resolve the datasphere CLI invocation prefix (array form).

        Order: ``DSP_CLI_PATH`` env → ``shutil.which`` → ``%APPDATA%/npm``.
        On Windows the resolved ``.cmd`` is wrapped as ``[COMSPEC, '/c', cli]``
        so subprocess can launch it without ``shell=True``.
        """
        if os.name == "nt":
            cli = os.environ.get("DSP_CLI_PATH", "").strip()
            cli = cli or shutil.which("datasphere.cmd") or shutil.which("datasphere")
            if not cli:
                appdata = os.environ.get("APPDATA", "")
                candidate = os.path.join(appdata, "npm", "datasphere.cmd")
                if appdata and os.path.exists(candidate):
                    cli = candidate
            if not cli:
                raise CliError(
                    "datasphere.cmd nicht in PATH, DSP_CLI_PATH oder "
                    "%APPDATA%\\npm\\ gefunden. Installation: "
                    "npm install -g @sap/datasphere-cli"
                )
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", cli]

        cli = os.environ.get("DSP_CLI_PATH", "").strip()
        cli = cli or shutil.which("datasphere")
        if not cli:
            raise CliError(
                "datasphere CLI nicht in PATH oder DSP_CLI_PATH gefunden. "
                "Installation: npm install -g @sap/datasphere-cli"
            )
        return [cli]

    def _cli_command(self) -> list[str]:
        if self._cli_cmd is None:
            self._cli_cmd = self._resolve_cli()
        return list(self._cli_cmd)

    def is_available(self) -> bool:
        """Return True if the datasphere CLI can be resolved on this host."""
        try:
            self._cli_command()
            return True
        except CliError:
            return False

    # ------------------------------------------------------------------
    # Login / host
    # ------------------------------------------------------------------

    def configured_cli_host(self) -> str | None:
        """Return the host configured in the CLI, or None if unreadable."""
        try:
            host = self.run_cli_text(
                ["config", "host", "show"], timeout_sec=10, retries=0
            )
        except CliError:
            return None
        return host.strip() or None

    # Probe subcommands tried in order to detect an existing CLI login. They
    # vary across @sap/datasphere-cli versions, so we try several and treat the
    # first that exits cleanly as "logged in" — this is what makes an existing
    # ``datasphere login`` reliably get picked up regardless of CLI version.
    _LOGIN_PROBES = (
        ["config", "secrets", "check"],
        ["config", "secrets", "show"],
        ["login", "--check"],
        ["whoami"],
    )

    def check_login(self) -> bool:
        """Return True if the CLI session is usable; False if a login is needed.

        Tries a sequence of read-only probe subcommands (tolerant of CLI-version
        differences). The first that exits cleanly means an existing login was
        detected. Raises ``CliAuthError`` only when the CLI explicitly reports an
        auth prompt/error (which carries the actionable login hint); other CLI
        failures fall through to the next probe, and ``False`` if all fail.
        """
        for argv in self._LOGIN_PROBES:
            try:
                self.run_cli_text(argv, timeout_sec=15, retries=0)
                return True
            except CliAuthError:
                raise
            except CliError:
                logger.debug("CLI login check via %s failed; trying next.", argv)
        return False

    def _login_args(
        self,
        *,
        host: str | None = None,
        code: str | None = None,
        force: bool = False,
        include_secret: bool = False,
    ) -> list[str]:
        """Return the Meridian-style ``datasphere login`` argv.

        The Datasphere CLI reads OAuth client details interactively or from the
        optional secrets file. For the actual spawned login command we can also
        pass the configured client secret, but display helpers must keep it out.
        """
        args = ["login"]
        effective_host = (host or os.environ.get("DSP_CLI_HOST") or self._host or "").strip()
        if effective_host:
            args += ["--host", effective_host]
        if self._client_id:
            args += ["--client-id", self._client_id]
        if include_secret and self._client_secret:
            args += ["--client-secret", self._client_secret]
        if self._authorization_url:
            args += ["--authorization-url", self._authorization_url]
        if self._token_url:
            args += ["--token-url", self._token_url]
        if self._secrets_file:
            args += ["--secrets-file", self._secrets_file]
        if code:
            args += ["--code", code]
        if force:
            args.append("--force")
        return args

    def login_args(
        self,
        *,
        host: str | None = None,
        code: str | None = None,
        force: bool = False,
    ) -> list[str]:
        """Return a safe display/login argv without echoing the client secret."""
        return self._login_args(host=host, code=code, force=force, include_secret=False)

    def login_command(self, *, host: str | None = None) -> str:
        """Human-readable CLI login command, with OAuth overrides included."""
        return _display_cli_command(self.login_args(host=host))

    def open_login_cmd(self) -> str:
        """Open an interactive Windows CMD for ``datasphere login``.

        This mirrors Meridian's operator flow: login remains interactive and
        visible, while this service only supplies non-secret connection details.
        """
        if os.name != "nt":
            raise CliError("CMD-Login kann nur unter Windows gestartet werden.")

        cli_program = self._terminal_cli_program()
        login_args = self._login_args(include_secret=True)
        command_line = subprocess.list2cmdline([cli_program, *login_args])
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        try:
            subprocess.Popen(
                [comspec, "/k", command_line],
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except FileNotFoundError as exc:
            raise CliError(f"CMD kann nicht gestartet werden: {comspec!r}") from exc
        return self.login_command()

    def _terminal_cli_program(self) -> str:
        cli_cmd = self._cli_command()
        if (
            os.name == "nt"
            and len(cli_cmd) >= 3
            and cli_cmd[1].lower() in {"/c", "/k"}
        ):
            return cli_cmd[2]
        return cli_cmd[0]

    # ------------------------------------------------------------------
    # Spaces / objects
    # ------------------------------------------------------------------

    def list_spaces(self) -> list[dict[str, Any]]:
        """Return all visible spaces as dicts (paged)."""
        spaces: list[dict[str, Any]] = []
        skip = 0
        while True:
            payload = self.run_cli_json(
                ["spaces", "list", "--top", str(PAGE_SIZE), "--skip", str(skip)]
            )
            page = normalize_list_payload(payload)
            if not page:
                break
            spaces.extend(page)
            if len(page) < PAGE_SIZE:
                break
            skip += PAGE_SIZE
        return spaces

    def list_objects(
        self,
        space: str,
        *,
        object_type: str = "views",
        select_fields: str = DEFAULT_SELECT_FIELDS,
        top: int = PAGE_SIZE,
        filter_expr: str | None = None,
        throttle_delay_sec: float = 0.0,
    ) -> list[dict[str, Any]]:
        """List all objects of one type in a space (paged + field fallback).

        On a CLI error with non-fallback ``select_fields`` the whole call is
        retried once with ``FALLBACK_SELECT_FIELDS`` before giving up (returns
        ``[]``). ``CliAuthError`` always propagates.
        """
        items: list[dict[str, Any]] = []
        skip = 0
        page_size = max(1, min(top, PAGE_SIZE))

        while True:
            try:
                payload = self._list_objects_page(
                    space=space,
                    object_type=object_type,
                    select_fields=select_fields,
                    top=page_size,
                    skip=skip,
                    filter_expr=filter_expr,
                )
            except CliAuthError:
                raise
            except CliError as exc:
                if select_fields != FALLBACK_SELECT_FIELDS:
                    logger.warning(
                        "list %s/%s failed with configured select fields; "
                        "retrying with fallback. Original error: %s",
                        space, object_type, exc,
                    )
                    try:
                        payload = self._list_objects_page(
                            space=space,
                            object_type=object_type,
                            select_fields=FALLBACK_SELECT_FIELDS,
                            top=page_size,
                            skip=skip,
                            filter_expr=filter_expr,
                        )
                    except CliAuthError:
                        raise
                    except CliError as fallback_exc:
                        logger.warning(
                            "skipping %s/%s: %s", space, object_type, fallback_exc
                        )
                        return items
                else:
                    logger.warning("skipping %s/%s: %s", space, object_type, exc)
                    return items

            page = normalize_list_payload(payload)
            if not page:
                break
            items.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
            if throttle_delay_sec > 0:
                time.sleep(throttle_delay_sec)

        return items

    def _list_objects_page(
        self,
        *,
        space: str,
        object_type: str,
        select_fields: str,
        top: int,
        skip: int,
        filter_expr: str | None,
    ) -> Any:
        args = [
            "objects", object_type, "list",
            "--space", space,
            "--select", select_fields,
            "--top", str(top),
            "--skip", str(skip),
        ]
        if filter_expr:
            args += ["--filter", filter_expr]
        try:
            return self.run_cli_json(args)
        except CliError as exc:
            if "--format" in str(exc):
                raise CliError(
                    "Die installierte Datasphere-CLI unterstützt --format für "
                    "object-list nicht; der Scanner nutzt die native "
                    "JSON-Ausgabe."
                ) from exc
            raise

    def read_object(
        self,
        space: str,
        technical_name: str,
        *,
        object_type: str = "views",
        accept: str = "csn",
    ) -> dict[str, Any]:
        """Read one object definition. ``accept='csn'`` maps to the CSN header.

        ``accept`` accepts the shorthand ``'csn'`` (→ CSN content type) or any
        explicit ``--accept`` header value.
        """
        accept_header = CSN_ACCEPT if accept == "csn" else accept
        payload = self.run_cli_json(
            [
                "objects", object_type, "read",
                "--space", space,
                "--technical-name", technical_name,
                "--accept", accept_header,
            ]
        )
        if not isinstance(payload, dict):
            raise CliError(
                f"Erwartete Objekt-JSON für {space}/{object_type}/{technical_name}, "
                f"erhielt {type(payload).__name__}"
            )
        return payload

    # ------------------------------------------------------------------
    # Low-level run helpers
    # ------------------------------------------------------------------

    def run_cli_json(
        self,
        args: list[str],
        *,
        timeout_sec: int | None = None,
        retries: int | None = None,
    ) -> Any:
        """Run a CLI command and parse its (ANSI-stripped) stdout as JSON."""
        result = self._run_cli_with_retries(
            args, timeout_sec=timeout_sec, retries=retries
        )
        stdout = _strip_terminal_control(result.stdout).strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            if _looks_like_auth_prompt(stdout):
                raise CliAuthError(self._auth_error_message(args, stdout)) from exc
            raise CliError(
                f"Nicht-JSON-Antwort für: datasphere {' '.join(args)}\n"
                f"Ausgabe (erste 500 Zeichen): {stdout[:500]}"
            ) from exc

    def run_cli_text(
        self,
        args: list[str],
        *,
        timeout_sec: int | None = None,
        retries: int | None = None,
    ) -> str:
        """Run a CLI command and return its ANSI-stripped stdout text."""
        result = self._run_cli_with_retries(
            args, timeout_sec=timeout_sec, retries=retries
        )
        return _strip_terminal_control(result.stdout).strip()

    def _run_cli_with_retries(
        self,
        args: list[str],
        *,
        timeout_sec: int | None,
        retries: int | None,
    ) -> CliResult:
        timeout_sec = self.timeout_sec if timeout_sec is None else timeout_sec
        retries = self.retries if retries is None else retries
        attempts = retries + 1
        last_timeout: subprocess.TimeoutExpired | None = None

        for attempt in range(1, attempts + 1):
            try:
                result = self._run_cli_once(args, timeout_sec)
            except subprocess.TimeoutExpired as exc:
                last_timeout = exc
                if attempt < attempts:
                    logger.warning(
                        "CLI timeout for %s. Retry %s/%s.",
                        " ".join(args), attempt, retries,
                    )
                    continue
                break

            if _looks_like_auth_prompt(result.combined_output):
                raise CliAuthError(
                    self._auth_error_message(args, result.combined_output)
                )

            if result.returncode == 0:
                return result

            if _is_auth_error(result.combined_output):
                raise CliAuthError(
                    self._auth_error_message(args, result.combined_output)
                )

            if _is_rate_limit(result.combined_output) and attempt < attempts:
                logger.warning(
                    "Datasphere CLI reported rate limiting. Waiting %s s before retry.",
                    self.retry_delay_sec,
                )
                time.sleep(self.retry_delay_sec)
                continue

            raise CliError(
                f"CLI error (rc={result.returncode}): datasphere {' '.join(args)}\n"
                f"STDERR: {result.stderr.strip()[:500]}\n"
                f"STDOUT: {result.stdout.strip()[:500]}"
            )

        raise CliTimeoutError(
            f"CLI timeout after {attempts} attempt(s): datasphere {' '.join(args)}"
        ) from last_timeout

    def _run_cli_once(self, args: list[str], timeout_sec: int) -> CliResult:
        command = self._cli_command() + list(args)
        cli_host = os.environ.get("DSP_CLI_HOST") or self._host
        if cli_host and "--host" not in args:
            command += ["--host", cli_host]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=timeout_sec,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise CliError(
                f"Datasphere CLI kann nicht gestartet werden: {command[0]!r}"
            ) from exc

        return CliResult(
            args=list(args),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def _auth_error_message(self, args: list[str], output: str) -> str:
        # Resolving the host runs another CLI command which may itself fail with
        # an auth prompt — suppress the host lookup while already building a
        # message to avoid unbounded recursion.
        host = None
        if not self._building_auth_message:
            self._building_auth_message = True
            try:
                host = self.configured_cli_host()
            except CliError:
                host = None
            finally:
                self._building_auth_message = False
        login_cmd = self.login_command(host=host)
        return (
            "Datasphere CLI verlangt eine Authentifizierung, dieses Tool "
            "erwartet aber nicht-interaktive JSON-Ausgabe.\n"
            f"Befehl: datasphere {' '.join(args)}\n"
            f"Lösung: `{login_cmd}` in einem normalen Terminal ausführen, "
            "Login abschließen, dann erneut versuchen.\n"
            f"CLI-Ausgabe: {_strip_terminal_control(output).strip()[:500]}"
        )


# ----------------------------------------------------------------------
# Module-level helpers (stateless)
# ----------------------------------------------------------------------

def normalize_list_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize common CLI list-response shapes to a list of dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("value", "items", "objects", "spaces", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if all(not isinstance(value, (dict, list)) for value in payload.values()):
            return [payload]
    return []


def _strip_terminal_control(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _looks_like_auth_prompt(text: str) -> bool:
    cleaned = _strip_terminal_control(text).lower()
    return any(marker in cleaned for marker in _AUTH_PROMPT_MARKERS)


def _is_auth_error(text: str) -> bool:
    cleaned = _strip_terminal_control(text).lower()
    return any(token in cleaned for token in ("401", "403", "unauthorized", "forbidden"))


def _is_rate_limit(text: str) -> bool:
    cleaned = _strip_terminal_control(text).lower()
    return any(token in cleaned for token in ("429", "rate limit", "too many requests"))


def _display_cli_command(args: list[str]) -> str:
    return "datasphere " + " ".join(_quote_display_arg(arg) for arg in args)


def _quote_display_arg(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'\s|"', value):
        return '"' + value.replace('"', r'\"') + '"'
    return value
