"""G-8 (ADR-0003): the `schema` and `type_conformance` checks must read both
SYS.TABLE_COLUMNS *and* SYS.VIEW_COLUMNS, so a View-backed dataset (HDLF object
shared into a monitoring space → View on top) is not a false breach.

Two levels of coverage:
  1. Template shape — the compiled SQL unions both catalogs (locks the fix).
  2. End-to-end — a catalog-aware fake cursor proves a View target *passes* the
     closed schema check (the reported bug) while a dropped object still breaches
     (drop detection preserved). The pre-G-8 templates queried TABLE_COLUMNS only
     and were masked in tests by the dumb scalar MockCursor (always 0).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.compiler import bind_schema, compile_contract
# aliased: bare `test_check` would be collected by pytest as a test case
from dq_core.engine.check_engine import test_check as run_single_check


def _schema_contract(columns: list[str], *, dataset: str = "DEMO_VIEW") -> dict:
    return {
        "product": dataset, "dataset": dataset, "version": "1.0.0",
        "guarantees": {"schema": {"columns": columns, "mode": "closed"}},
    }


def _compiled_check(contract: dict, name: str, schema: str = "CORE_DWH"):
    config = bind_schema(compile_contract(contract), schema)
    by_name = {c.name: c for c in config.checks}
    assert name in by_name, f"{name!r} not in {sorted(by_name)}"
    return by_name[name]


# ── 1. Template shape ─────────────────────────────────────────────────────────

def test_schema_check_unions_table_and_view_catalogs():
    sql = _compiled_check(_schema_contract(["A", "B", "C"]), "schema_columns").sql
    assert "TABLE_COLUMNS" in sql and "VIEW_COLUMNS" in sql
    assert "TABLE_NAME = '" in sql and "VIEW_NAME = '" in sql
    # still a single scalar count → expectation engine stays a scalar comparison
    assert sql.strip().upper().startswith("SELECT COUNT(*)")
    assert "{schema}" not in sql  # bound at runtime above


def test_type_conformance_unions_table_and_view_catalogs():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0", "guarantees": {},
        "checks": [{"id": "type_conformance",
                    "params": {"<SPALTE>": "ORDER_DATE", "<DATA_TYPE_NAME>": "DATE"}}],
    }
    sql = _compiled_check(contract, "type_conformance_ORDER_DATE").sql
    assert "TABLE_COLUMNS" in sql and "VIEW_COLUMNS" in sql
    assert sql.count("COLUMN_NAME = 'ORDER_DATE'") == 2  # both catalog branches filtered
    assert "<> 'DATE'" in sql


# ── 2. End-to-end against a catalog-aware fake cursor ─────────────────────────

class _CatalogCursor:
    """HANA SYS-catalog stand-in: faithfully answers the two catalog query shapes
    the templates emit by unioning both catalogs. `tables`/`views` map an object
    name to its ``{COLUMN_NAME: DATA_TYPE_NAME}``."""

    def __init__(self, *, tables: dict | None = None, views: dict | None = None) -> None:
        self.tables = tables or {}
        self.views = views or {}
        self.description: list = [("result",)]
        self._rows: list = [(0,)]

    def execute(self, sql, params=None) -> None:
        text = " ".join(str(sql).split())
        self.description = [("result",)]
        if text.upper().startswith("SET"):
            self._rows = []
            return
        rows = self._gather(text)
        if "CASE WHEN COUNT(*)" in text.upper():           # type_conformance
            expected = self._first(text, r"<>\s*'([^']*)'")
            present = [t for _c, t in rows]
            self._rows = [(0 if present and max(present) == expected else 1,)]
        else:                                              # schema: COUNT over union
            self._rows = [(len(rows),)]

    def _gather(self, text: str) -> list[tuple[str, str]]:
        col = self._first(text, r"COLUMN_NAME\s*=\s*'([^']*)'")
        out: list[tuple[str, str]] = []
        up = text.upper()
        if "TABLE_COLUMNS" in up:
            out += self._cols(self.tables.get(self._first(text, r"TABLE_NAME\s*=\s*'([^']*)'"), {}), col)
        if "VIEW_COLUMNS" in up:
            out += self._cols(self.views.get(self._first(text, r"VIEW_NAME\s*=\s*'([^']*)'"), {}), col)
        return out

    @staticmethod
    def _cols(cols: dict, col_filter: str | None) -> list[tuple[str, str]]:
        return [(c, t) for c, t in cols.items() if col_filter is None or c == col_filter]

    @staticmethod
    def _first(text: str, pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1) if m else None

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self) -> None:
        pass


class _Conn:
    def __init__(self, cursor: _CatalogCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _CatalogCursor:
        return self._cursor

    def close(self) -> None:
        pass


def test_view_backed_dataset_passes_schema_check():
    """The reported bug: a closed schema check (`= N`, critical) against a View
    counted 0 in TABLE_COLUMNS → false critical breach. It must now pass."""
    check = _compiled_check(_schema_contract(["COL_A", "COL_B", "COL_C"]), "schema_columns")
    view_cols = {"COL_A": "NVARCHAR", "COL_B": "INTEGER", "COL_C": "DATE"}
    conn = _Conn(_CatalogCursor(views={"DEMO_VIEW": view_cols}))

    result = run_single_check(conn, check)
    assert result.actual_value == 3
    assert result.passed is True
    assert result.error is None


def test_table_backed_dataset_still_passes_schema_check():
    """Regression guard: tables (the only pre-G-8 path) keep working."""
    check = _compiled_check(_schema_contract(["COL_A", "COL_B"]), "schema_columns")
    conn = _Conn(_CatalogCursor(tables={"DEMO_VIEW": {"COL_A": "INTEGER", "COL_B": "DATE"}}))
    assert run_single_check(conn, check).passed is True


def test_dropped_object_still_breaches_schema_check():
    """View-awareness must not turn the check into an always-pass: an object that
    exists in neither catalog still counts 0 → closed `= N` breaches (drop detect)."""
    check = _compiled_check(_schema_contract(["COL_A", "COL_B", "COL_C"]), "schema_columns")
    conn = _Conn(_CatalogCursor())  # empty catalog
    result = run_single_check(conn, check)
    assert result.actual_value == 0
    assert result.passed is False


def _type_conformance_check(expected_type: str):
    contract = {
        "product": "DEMO_VIEW", "dataset": "DEMO_VIEW", "version": "1.0.0",
        "guarantees": {},
        "checks": [{"id": "type_conformance",
                    "params": {"<SPALTE>": "COL_A", "<DATA_TYPE_NAME>": expected_type}}],
    }
    return _compiled_check(contract, "type_conformance_COL_A")


def test_view_column_type_conformance_passes_on_match():
    check = _type_conformance_check("DATE")  # expect = 0 (no mismatch)
    conn = _Conn(_CatalogCursor(views={"DEMO_VIEW": {"COL_A": "DATE"}}))
    result = run_single_check(conn, check)
    assert result.actual_value == 0
    assert result.passed is True


def test_view_column_type_conformance_fails_on_mismatch():
    check = _type_conformance_check("DATE")
    conn = _Conn(_CatalogCursor(views={"DEMO_VIEW": {"COL_A": "NVARCHAR"}}))
    result = run_single_check(conn, check)
    assert result.actual_value == 1
    assert result.passed is False
