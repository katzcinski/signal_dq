"""Connector hardening (ported from Meridian): transient-error retry +
statement timeout, without regressing the S-13 fail-closed contract.

No live HANA — the driver's ``connect`` is monkeypatched.
"""
import pytest

# T-11: hdbcli ist der proprietäre SAP-Treiber. Fehlt er (frische Umgebung ohne
# `make install`), skippt dieses Modul selbst statt mit ImportError zu erroren.
pytest.importorskip("hdbcli")

from dq_core.connect import db_connection
from dq_core.connect.db_connection import (
    MockConnection,
    _is_transient_error,
    check_connection,
    get_connection,
)


class _FakeCursor:
    def execute(self, *args, **kwargs):
        pass

    def close(self):
        pass


class _FakeConn:
    def cursor(self):
        return _FakeCursor()


class _CheckCursor:
    def __init__(self, *, version_error=False, schema_count=1):
        self.description = [("result",)]
        self._rows = []
        self._version_error = version_error
        self._schema_count = schema_count

    def execute(self, sql, params=None):
        upper = str(sql).upper()
        if "SYS.M_DATABASE" in upper:
            if self._version_error:
                raise Exception("insufficient privilege")
            self.description = [("VERSION",)]
            self._rows = [("4.00.000",)]
            return
        if "SYS.SCHEMAS" in upper:
            self.description = [("COUNT",)]
            self._rows = [(self._schema_count,)]
            return
        if "WHERE 1 = 0" in upper:
            self.description = [("COL",)]
            self._rows = []
            return
        self.description = [("result",)]
        self._rows = [(1,)]

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, size=100):
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def close(self):
        pass


class _CheckConn:
    def __init__(self, *, version_error=False, schema_count=1):
        self.closed = False
        self._version_error = version_error
        self._schema_count = schema_count

    def cursor(self):
        return _CheckCursor(
            version_error=self._version_error,
            schema_count=self._schema_count,
        )

    def close(self):
        self.closed = True


def test_is_transient_error_only_matches_network_session_failures():
    assert _is_transient_error(Exception("Network is unreachable"))
    assert _is_transient_error(Exception("session expired, please re-login"))
    assert _is_transient_error(Exception("connection broken"))
    # Auth / privilege / config errors must NOT be treated as transient.
    assert not _is_transient_error(Exception("authentication failed: invalid credentials"))
    assert not _is_transient_error(Exception("insufficient privilege"))


def test_get_connection_retries_transient_then_succeeds(monkeypatch):
    import hdbcli.dbapi as dbapi

    calls = {"n": 0}

    def fake_connect(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("network error: connection broken")
        return _FakeConn()

    monkeypatch.setattr(dbapi, "connect", fake_connect)
    monkeypatch.setattr(db_connection.time, "sleep", lambda *_: None)

    conn = get_connection("host", 443, "user", "pw", "SCHEMA", max_retry_attempts=3)
    assert isinstance(conn, _FakeConn)
    assert calls["n"] == 3


def test_get_connection_does_not_retry_auth_error(monkeypatch):
    import hdbcli.dbapi as dbapi

    calls = {"n": 0}

    def fake_connect(**kwargs):
        calls["n"] += 1
        raise Exception("authentication failed")

    monkeypatch.setattr(dbapi, "connect", fake_connect)
    monkeypatch.setattr(db_connection.time, "sleep", lambda *_: None)

    with pytest.raises(Exception, match="authentication failed"):
        get_connection("host", 443, "user", "pw", "SCHEMA")
    assert calls["n"] == 1  # fail-fast, no retry on auth errors


def test_get_connection_sets_statement_timeout(monkeypatch):
    import hdbcli.dbapi as dbapi

    executed: list[str] = []

    class RecordingCursor(_FakeCursor):
        def execute(self, sql, *args, **kwargs):
            executed.append(sql)

    class RecordingConn(_FakeConn):
        def cursor(self):
            return RecordingCursor()

    monkeypatch.setattr(dbapi, "connect", lambda **kwargs: RecordingConn())

    get_connection("host", 443, "user", "pw", "SCHEMA", statement_timeout_ms=5000)
    assert any("statementTimeout" in sql and "5000" in sql for sql in executed)


def test_mock_connection_still_returns_scalar_row():
    cur = MockConnection().cursor()
    cur.execute("SELECT 1 AS result FROM DUMMY")
    assert cur.fetchone() == (0,)
    assert cur.fetchone() is None


def test_get_connection_emits_progress_for_retry(monkeypatch):
    import hdbcli.dbapi as dbapi

    calls = {"n": 0}
    progress: list[str] = []

    def fake_connect(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("network error: connection broken")
        return _FakeConn()

    monkeypatch.setattr(dbapi, "connect", fake_connect)
    monkeypatch.setattr(db_connection.time, "sleep", lambda *_: None)

    get_connection("host", 443, "user", "pw", "SCHEMA", on_progress=progress.append)
    assert calls["n"] == 2
    assert any("Versuch 2/3" in line for line in progress)
    assert progress[-1] == "HANA-Verbindung hergestellt."


def test_check_connection_returns_ok_with_version_and_schema(monkeypatch):
    import hdbcli.dbapi as dbapi

    conn = _CheckConn()
    progress: list[str] = []
    monkeypatch.setattr(dbapi, "connect", lambda **kwargs: conn)

    result = check_connection(
        "host",
        443,
        "user",
        "pw",
        "CORE",
        on_progress=progress.append,
        environment_name="prod",
    )

    assert result["ok"] is True
    assert result["server_version"] == "4.00.000"
    assert result["schema_visible"] is True
    assert result["failure_stage"] is None
    assert conn.closed is True
    assert progress[0] == 'Verbinde mit Environment "prod" ...'
    assert "Schema \"CORE\" pruefen ..." in progress


def test_check_connection_version_failure_is_not_terminal(monkeypatch):
    import hdbcli.dbapi as dbapi

    monkeypatch.setattr(dbapi, "connect", lambda **kwargs: _CheckConn(version_error=True))

    result = check_connection("host", 443, "user", "pw", "CORE")

    assert result["ok"] is True
    assert result["server_version"] is None
    assert result["schema_visible"] is True


def test_check_connection_schema_invisible_is_safe_verdict(monkeypatch):
    import hdbcli.dbapi as dbapi

    conn = _CheckConn(schema_count=0)
    monkeypatch.setattr(dbapi, "connect", lambda **kwargs: conn)

    result = check_connection("host", 443, "user", "pw", "CORE")

    assert result["ok"] is False
    assert result["failure_stage"] == "schema"
    assert result["error"] == "Configured schema is not visible to this user."
    assert conn.closed is True


def test_check_connection_auth_failure_is_safe_and_not_retried(monkeypatch):
    import hdbcli.dbapi as dbapi

    calls = {"n": 0}

    def fake_connect(**kwargs):
        calls["n"] += 1
        raise Exception("authentication failed for password=secret")

    monkeypatch.setattr(dbapi, "connect", fake_connect)
    monkeypatch.setattr(db_connection.time, "sleep", lambda *_: None)

    result = check_connection("host", 443, "user", "pw", "CORE")

    assert calls["n"] == 1
    assert result["ok"] is False
    assert result["failure_stage"] == "connect"
    assert result["error"] == "Authentication failed or credentials are not valid."
    assert "secret" not in result["error"].lower()
