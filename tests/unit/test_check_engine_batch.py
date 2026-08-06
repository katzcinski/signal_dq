"""Batch-Pfad der Engine: _build_batch_sql, _batch_rows_to_values und
_run_checks_batch inkl. Timeout, Fehlerzuordnung und Auto-Fallback auf
Einzelchecks (execution_mode auto | batch)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.check_engine import (
    _batch_rows_to_values,
    _build_batch_sql,
    _execute,
)
from dq_core.engine.models import CheckDef


class _BatchCursor:
    """Fake cursor: beantwortet den Batch mit vorgegebenen (name, value)-Zeilen
    oder wirft, wenn der Owner einen Batch-Fehler simuliert."""

    def __init__(self, owner):
        self._owner = owner
        self.description = [("check_name",), ("actual_value",)]

    def execute(self, sql, params=None):
        self._owner.statements.append(sql)
        if str(sql).strip().upper().startswith("SET"):
            return
        if self._owner.batch_error:
            raise RuntimeError(self._owner.batch_error)

    def fetchall(self):
        return list(self._owner.batch_rows)

    def close(self):
        self._owner.closed += 1


class _BatchConn:
    def __init__(self, batch_rows=None, batch_error=None):
        self.batch_rows = batch_rows or []
        self.batch_error = batch_error
        self.statements = []
        self.closed = 0

    def cursor(self):
        return _BatchCursor(self)


class _FallbackCursor:
    """Batch-SQL (erkennbar an check_name-Spalte) schlägt fehl, Einzelchecks
    liefern einen Skalar — simuliert den Auto-Fallback-Fall."""

    def __init__(self, owner):
        self._owner = owner
        self.description = [("CNT",)]
        self._rows = []

    def execute(self, sql, params=None):
        self._owner.statements.append(sql)
        if str(sql).strip().upper().startswith("SET"):
            return
        if "check_name" in str(sql):
            raise RuntimeError("Batch kaputt")
        self._rows = [(0,)]

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        pass


class _FallbackConn:
    def __init__(self):
        self.statements = []

    def cursor(self):
        return _FallbackCursor(self)


def _check(name, *, sql="SELECT COUNT(*) FROM T", timeout_s=60, expect="= 0"):
    return CheckDef(name=name, sql=sql, expect=expect, severity="fail", timeout_s=timeout_s)


# ---------------------------------------------------------------- _build_batch_sql

def test_build_batch_sql_wraps_checks_and_strips_terminators():
    sql = _build_batch_sql([
        _check("c1", sql="SELECT COUNT(*) FROM T1;"),
        _check("c2", sql="SELECT COUNT(*) FROM T2"),
    ])
    assert "UNION ALL" in sql
    assert sql.count("FROM DUMMY") == 2
    assert ";" not in sql
    assert "'c1' AS check_name, (SELECT COUNT(*) FROM T1) AS actual_value" in sql


def test_build_batch_sql_escapes_quotes_in_check_names():
    sql = _build_batch_sql([_check("o'brien")])
    assert "'o''brien' AS check_name" in sql


# ---------------------------------------------------------- _batch_rows_to_values

def test_batch_rows_to_values_maps_names_to_values():
    assert _batch_rows_to_values([("a", 1), ("b", None)]) == {"a": 1, "b": None}


def test_batch_rows_to_values_rejects_wrong_row_shape():
    with pytest.raises(ValueError, match="zwei Spalten"):
        _batch_rows_to_values([("a",)])


def test_batch_rows_to_values_rejects_duplicate_check_names():
    with pytest.raises(ValueError, match="doppelte Zeile"):
        _batch_rows_to_values([("a", 1), ("a", 2)])


# -------------------------------------------------------------- _run_checks_batch

def test_batch_happy_path_evaluates_each_check():
    conn = _BatchConn(batch_rows=[("c1", 0), ("c2", 5)])
    results = _execute(conn, [_check("c1"), _check("c2")], "batch", None, {})
    by_name = {r.name: r for r in results}
    assert by_name["c1"].passed is True
    assert by_name["c2"].passed is False
    assert all(r.state == "executed" for r in results)
    assert conn.closed == 1


def test_batch_sets_statement_timeout_to_max_of_checks():
    conn = _BatchConn(batch_rows=[("c1", 0), ("c2", 0)])
    _execute(conn, [_check("c1", timeout_s=30), _check("c2", timeout_s=90)], "batch", None, {})
    assert conn.statements[0] == "SET 'statementTimeout' = '90000'"


def test_batch_missing_value_becomes_error_result_g6():
    # G6: ein Check ohne Batch-Zeile wird als expliziter error persistierbar,
    # nie stillschweigend ausgelassen.
    conn = _BatchConn(batch_rows=[("c1", 0)])
    results = _execute(conn, [_check("c1"), _check("c2")], "batch", None, {})
    by_name = {r.name: r for r in results}
    assert by_name["c1"].state == "executed"
    assert by_name["c2"].state == "error"
    assert "Batch-Ergebnis" in by_name["c2"].error


def test_batch_mode_failure_yields_error_results_without_fallback():
    conn = _BatchConn(batch_error="Batch kaputt")
    results = _execute(conn, [_check("c1"), _check("c2")], "batch", None, {})
    assert [r.state for r in results] == ["error", "error"]
    assert all("Batch kaputt" in r.error for r in results)


def test_auto_mode_falls_back_to_isolated_on_batch_failure():
    conn = _FallbackConn()
    progress: list[str] = []
    results = _execute(conn, [_check("c1"), _check("c2")], "auto", progress.append, {})
    assert all(r.state == "executed" and r.passed for r in results)
    assert any("Einzelchecks" in line for line in progress)
    # Nach dem Fallback wurde jeder Check einzeln ausgeführt.
    singles = [s for s in conn.statements if "check_name" not in s and not s.startswith("SET")]
    assert len(singles) == 2
