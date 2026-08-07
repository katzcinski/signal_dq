"""Database connection helper. [SCHEMA-MAP] schema is bound at run-time, never hardcoded."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

_LOG = logging.getLogger(__name__)

from .query_helpers import qualified

# Substrings that mark a *transient* connect failure worth retrying (network
# blips, dropped/expired sessions). Deliberately excludes the bare word
# "connection" so genuine auth/config errors fail fast instead of being retried.
TRANSIENT_ERROR_MARKERS = (
    "connection closed",
    "connection broken",
    "connection reset",
    "session closed",
    "session expired",
    "temporarily unavailable",
    "network",
)

ProgressCallback = Callable[[str], None]


class DbCursor(Protocol):
    description: Any

    def execute(self, sql: str, params: Any = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchmany(self, size: int = 100) -> list: ...

    def fetchall(self) -> list: ...

    def close(self) -> None: ...


class DbConnection(Protocol):
    def cursor(self) -> DbCursor: ...

    def close(self) -> None: ...


def _is_transient_error(exc: Exception) -> bool:
    message = " ".join(str(part) for part in exc.args if part).strip().lower()
    if not message:
        message = exc.__class__.__name__.lower()
    return any(marker in message for marker in TRANSIENT_ERROR_MARKERS)


class MockConnection:
    """In-process mock for development when no HANA is available."""

    def cursor(self) -> "MockCursor":
        return MockCursor()

    def close(self) -> None:
        pass


class MockCursor:
    """Verhält sich wie ein echter Ein-Zeilen-Skalar-Cursor: fetchone liefert
    genau eine Zeile und danach None; Batch-SQL (UNION ALL mit check_name)
    liefert je Check eine (name, 0)-Zeile."""

    def __init__(self) -> None:
        self.description: list = [("result",)]
        self._rows: list = []

    def execute(self, sql: str, params: Any = None) -> None:
        import re
        if str(sql).strip().upper().startswith("SET"):
            self._rows = []
            return
        names = re.findall(r"'((?:[^']|'')*)' AS check_name", str(sql))
        if names:
            self.description = [("check_name",), ("actual_value",)]
            self._rows = [(n.replace("''", "'"), 0) for n in names]
        else:
            self.description = [("result",)]
            self._rows = [(0,)]

    def fetchone(self) -> tuple | None:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list:
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, size: int = 100) -> list:
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def close(self) -> None:
        pass


def get_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    schema: str,  # [SCHEMA-MAP] bound here, not in contract
    *,
    encrypt: bool = True,
    validate_cert: bool = True,
    statement_timeout_ms: int = 120_000,
    max_retry_attempts: int = 3,
    on_progress: ProgressCallback | None = None,
) -> Any:
    """Return a hdbcli connection.

    Fail-closed (S-13): fehlt der Treiber, gibt es einen harten Fehler statt
    eines stillen Mock-Fallbacks — fake-grüne Checks in Prod sind schlimmer
    als ein Startfehler. Mock-Nutzung ist eine explizite Caller-Entscheidung.

    Härtung (übernommen aus Meridian/datasphere-tools): transiente
    Verbindungsfehler (Netz, abgelaufene Session) werden mit exponentiellem
    Backoff erneut versucht — Auth-/Konfigfehler dagegen sofort durchgereicht.
    Pro Verbindung wird ein ``statementTimeout`` gesetzt, damit Runaway-Queries
    nicht unbegrenzt laufen (``statement_timeout_ms <= 0`` deaktiviert das).
    """
    try:
        from hdbcli import dbapi  # type: ignore[import]
    except ImportError as exc:
        _LOG.error(
            "hdbcli import failed (%s). "
            "Verify that hdbcli is installed in the same Python environment "
            "that runs this process (check 'pip show hdbcli' inside the venv).",
            exc,
        )
        raise RuntimeError(
            f"hdbcli ist nicht installiert oder nicht importierbar "
            f"({exc}). "
            "Stelle sicher dass hdbcli im selben Python-Environment wie der "
            "API-Prozess installiert ist."
        ) from exc

    def _connect() -> Any:
        if on_progress:
            on_progress("HANA-Verbindung wird aufgebaut ...")
        conn = dbapi.connect(
            address=host,
            port=port,
            user=user,
            password=password,
            currentSchema=schema,
            encrypt=encrypt,
            sslValidateCertificate=validate_cert,
        )
        if statement_timeout_ms and statement_timeout_ms > 0:
            cursor = conn.cursor()
            try:
                cursor.execute(f"SET 'statementTimeout' = '{int(statement_timeout_ms)}'")
            finally:
                cursor.close()
        if on_progress:
            on_progress("HANA-Verbindung hergestellt.")
        return conn

    attempt = 1
    while True:
        try:
            return _connect()
        except Exception as exc:  # noqa: BLE001 — retry only transient connect errors
            if attempt >= max_retry_attempts or not _is_transient_error(exc):
                raise
            if on_progress:
                on_progress(
                    f"Transienter Verbindungsfehler - Versuch {attempt + 1}/{max_retry_attempts} ..."
                )
            time.sleep(2.0 * (2 ** (attempt - 1)))
            attempt += 1


def check_connection(
    host: str,
    port: int,
    user: str,
    password: str,
    schema: str,
    *,
    encrypt: bool = True,
    validate_cert: bool = True,
    probe_object: str | None = None,
    on_progress: ProgressCallback | None = None,
    environment_name: str | None = None,
) -> dict[str, Any]:
    """Check whether a configured HANA/Datasphere environment is usable.

    Expected HANA failures return a verdict instead of raising. The returned
    error string is safe for API clients and intentionally does not include raw
    driver details, SQL text, stack traces, or credentials.
    """
    conn: DbConnection | None = None
    started = time.perf_counter()
    server_version: str | None = None

    def _latency_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    if on_progress:
        if environment_name:
            on_progress(f'Verbinde mit Environment "{environment_name}" ...')
        else:
            on_progress("Verbinde mit HANA ...")

    try:
        conn = get_connection(
            host,
            port,
            user,
            password,
            schema,
            encrypt=encrypt,
            validate_cert=validate_cert,
            on_progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001 - return a safe verdict
        stage, message = _safe_connect_failure(exc)
        return _connection_result(
            ok=False,
            latency_ms=_latency_ms(),
            server_version=None,
            schema_visible=False,
            failure_stage=stage,
            error=message,
        )

    try:
        if on_progress:
            on_progress("Liveness pruefen ...")
        _execute_scalar(conn, "SELECT 1 FROM DUMMY")
    except Exception:  # noqa: BLE001 - safe verdict, no raw DB details
        _close_connection(conn)
        return _connection_result(
            ok=False,
            latency_ms=_latency_ms(),
            server_version=None,
            schema_visible=False,
            failure_stage="liveness",
            error="Liveness check failed.",
        )

    if on_progress:
        on_progress("Serverversion pruefen ...")
    try:
        server_version = _read_server_version(conn)
    except Exception:  # noqa: BLE001 - version is diagnostic metadata only
        server_version = None
        if on_progress:
            on_progress("Version konnte nicht gelesen werden.")

    if on_progress:
        on_progress(f'Schema "{schema}" pruefen ...')
    schema_visible = (
        _probe_object_access(conn, schema, probe_object)
        if probe_object
        else _schema_is_visible(conn, schema)
    )
    if not schema_visible:
        _close_connection(conn)
        return _connection_result(
            ok=False,
            latency_ms=_latency_ms(),
            server_version=server_version,
            schema_visible=False,
            failure_stage="schema",
            error="Configured schema is not visible to this user.",
        )

    if on_progress:
        on_progress("Connection-Test abgeschlossen.")
    try:
        return _connection_result(
            ok=True,
            latency_ms=_latency_ms(),
            server_version=server_version,
            schema_visible=True,
            failure_stage=None,
            error=None,
        )
    finally:
        _close_connection(conn)


def _connection_result(
    *,
    ok: bool,
    latency_ms: int,
    server_version: str | None,
    schema_visible: bool,
    failure_stage: str | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "latency_ms": latency_ms,
        "server_version": server_version,
        "schema_visible": schema_visible,
        "failure_stage": failure_stage,
        "error": error,
    }


def _safe_connect_failure(exc: Exception) -> tuple[str, str]:
    message = " ".join(str(part) for part in exc.args if part).strip().lower()
    if isinstance(exc, RuntimeError) and "hdbcli" in message:
        # Surface the underlying ImportError so the user can diagnose env issues.
        cause = str(exc.__cause__) if exc.__cause__ else ""
        detail = f" ({cause})" if cause else ""
        return "driver", f"HANA driver is not installed or not importable.{detail}"
    auth_markers = ("auth", "credential", "password", "invalid user", "invalid username")
    if any(marker in message for marker in auth_markers):
        return "connect", "Authentication failed or credentials are not valid."
    return "connect", "HANA connection could not be established."


def _execute_scalar(conn: DbConnection, sql: str, params: Any = None) -> Any:
    cursor = conn.cursor()
    try:
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def _read_server_version(conn: DbConnection) -> str | None:
    value = _execute_scalar(conn, "SELECT VERSION FROM SYS.M_DATABASE")
    return str(value) if value is not None else None


def _schema_is_visible(conn: DbConnection, schema: str) -> bool:
    if not str(schema or "").strip():
        return False
    try:
        value = _execute_scalar(
            conn,
            "SELECT COUNT(*) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?",
            (schema,),
        )
        return bool(int(value or 0) > 0)
    except Exception:  # noqa: BLE001 - if we cannot prove it, fail closed
        return False


def _probe_object_access(conn: DbConnection, schema: str, probe_object: str | None) -> bool:
    if not probe_object:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {qualified(schema, probe_object)} WHERE 1 = 0")
        cursor.fetchall()
        return True
    except Exception:  # noqa: BLE001 - if we cannot prove it, fail closed
        return False
    finally:
        cursor.close()


def _close_connection(conn: DbConnection | None) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass
