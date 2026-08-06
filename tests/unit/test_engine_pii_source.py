"""S-8: PII-Unterdrückung an der Quelle — die Engine holt Rohzeilen nur, wenn
der Check Diagnostik explizit erlaubt, und projiziert auf die Allowlist."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.check_engine import _run_one_check
from dq_core.engine.models import CheckDef


class _Cursor:
    """Fake cursor: COUNT-Query liefert 5 (Check schlägt fehl), Diagnose-Query
    liefert Zeilen mit PII-Spalten."""

    def __init__(self, owner):
        self._owner = owner
        self.description = [("CNT",)]
        self._rows = []

    def execute(self, sql, params=None):
        if sql.startswith("SET"):
            return
        if sql.strip().upper().startswith("SELECT *"):
            self._owner.diag_queries += 1
            self.description = [("ID",), ("EMAIL",)]
            self._rows = [(1, "a@example.com"), (2, "b@example.com")]
        else:
            self.description = [("CNT",)]
            self._rows = [(5,)]

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchmany(self, size=100):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.diag_queries = 0

    def cursor(self):
        return _Cursor(self)


def _check(**kwargs) -> CheckDef:
    return CheckDef(
        name="c", sql='SELECT COUNT(*) FROM "S"."T" WHERE "X" IS NULL',
        expect="= 0", severity="fail", **kwargs,
    )


def test_no_diagnostics_without_flag():
    conn = _Conn()
    result = _run_one_check(conn, _check())
    assert result.passed is False
    assert result.diagnostic_rows == []
    assert conn.diag_queries == 0  # nicht einmal abgefragt


def test_diagnostics_with_allowlist_projects_columns():
    conn = _Conn()
    result = _run_one_check(
        conn, _check(diagnostics_enabled=True, diagnostics_columns=["ID"])
    )
    assert conn.diag_queries == 1
    assert result.diagnostic_rows == [{"ID": 1}, {"ID": 2}]
    assert all("EMAIL" not in row for row in result.diagnostic_rows)
