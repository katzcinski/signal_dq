"""_diagnostic_sql: konservative COUNT(*)→SELECT-*-Umschreibung für
Diagnosezeilen. Fail-closed ([PII-GATE]): jede Form, die sich nicht sicher
umschreiben lässt, ergibt None — also keine Rohzeilen."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.check_engine import _diagnostic_sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            'SELECT COUNT(*) FROM "S"."T" WHERE "X" IS NULL',
            'SELECT * FROM "S"."T" WHERE "X" IS NULL LIMIT 100',
        ),
        # Semikolon-Terminator bricht die Umschreibung nicht mehr.
        (
            'SELECT COUNT(*) FROM "S"."T" WHERE "X" IS NULL;',
            'SELECT * FROM "S"."T" WHERE "X" IS NULL LIMIT 100',
        ),
        # Ohne WHERE: kompletter Tabellen-Sample.
        ("SELECT COUNT(*) FROM T", "SELECT * FROM T LIMIT 100"),
        # Whitespace-/Case-Varianten von COUNT(*).
        ("select count( * ) from t where x > 0", "SELECT * from t where x > 0 LIMIT 100"),
        ("SELECT COUNT(1) FROM T WHERE X = 1", "SELECT * FROM T WHERE X = 1 LIMIT 100"),
        # Mehrzeilig (DOTALL).
        ("SELECT COUNT(*)\nFROM T\nWHERE X > 0", "SELECT * FROM T WHERE X > 0 LIMIT 100"),
        # Subquery im WHERE bleibt erhalten.
        (
            "SELECT COUNT(*) FROM T WHERE ID IN (SELECT ID FROM U)",
            "SELECT * FROM T WHERE ID IN (SELECT ID FROM U) LIMIT 100",
        ),
    ],
)
def test_rewrites_count_queries(sql, expected):
    assert _diagnostic_sql(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "SELECT MAX(X) FROM T",
        "SELECT COUNT(DISTINCT X) FROM T",
        "DELETE FROM T",
        # SELECT * mit GROUP BY wäre ungültiges SQL → fail-closed.
        "SELECT COUNT(*) FROM T GROUP BY X",
        "SELECT COUNT(*) FROM T WHERE X > 0 GROUP BY Y HAVING COUNT(*) > 1",
        # Set-Operationen zählen etwas anderes als Tabellenzeilen.
        "SELECT COUNT(*) FROM T UNION ALL SELECT COUNT(*) FROM U",
        # Vorhandenes LIMIT/OFFSET würde doppelt angehängt.
        "SELECT COUNT(*) FROM T WHERE X > 0 LIMIT 1",
        "SELECT COUNT(*) FROM T OFFSET 10",
    ],
)
def test_fails_closed_for_unsafe_or_foreign_shapes(sql):
    assert _diagnostic_sql(sql) is None
