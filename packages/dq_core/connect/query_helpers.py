"""Dict-row Query-Helfer für dq_core (framework-free).

Konsumiert einen DB-Cursor, der dem hdbcli/PEP-249-Kontrakt folgt
(``execute(sql, params)``, ``description``, ``fetchall``/``fetchone``) — exakt
das, was ``db_connection.MockCursor`` ebenfalls liefert. Es werden **niemals**
eigene Verbindungen geöffnet; der Aufrufer ist für Lifecycle und Schema-Bindung
zuständig.

Security-Posture (S-policy): Nur Aggregate/Metadaten. Bezeichner werden via
Double-Quote-Quoting eingebettet; Werte gehören als Parameter in ``execute``.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

__all__ = [
    "jsonable",
    "quote_identifier",
    "qualified",
    "query",
    "query_one",
    "get_columns",
]


# ---------------------------------------------------------------------------
# JSON-Normalisierung
# ---------------------------------------------------------------------------

def jsonable(value: Any) -> Any:
    """Make a scalar JSON-serialisable: Decimal->int/float, temporal->isoformat.

    Decimals ohne Nachkommaanteil werden zu ``int``, sonst zu ``float`` —
    damit IDs/Counts nicht als ``1.0`` herausfallen. ``bytes`` werden best-effort
    dekodiert (Roh-Binärdaten sollten ohnehin nie das Aggregat-Layer erreichen).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — defensiv, nie crashen wegen Serialisierung
            return str(value)
    return value


# ---------------------------------------------------------------------------
# Quoting / Bezeichner
# ---------------------------------------------------------------------------

def quote_identifier(identifier: str) -> str:
    """Return a safely double-quoted SQL identifier (HANA-Style)."""
    if identifier is None or not str(identifier).strip():
        raise ValueError("Identifier cannot be empty")
    return '"' + str(identifier).replace('"', '""') + '"'


def qualified(schema: str, table: str) -> str:
    """Return ``"SCHEMA"."TABLE"`` mit korrektem Quoting beider Teile."""
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


# ---------------------------------------------------------------------------
# Kern-Query-Helfer (dict rows)
# ---------------------------------------------------------------------------

def query(cursor: Any, sql: str, params: Any = None) -> list[dict]:
    """Execute *sql* on *cursor* and return rows as a list of dicts.

    Spaltennamen kommen aus ``cursor.description`` (erstes Tuple-Element).
    ``params`` wird nur durchgereicht, wenn nicht ``None`` — so funktionieren
    sowohl parametrierte als auch parameterlose Cursors/Mocks.
    """
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)
    description = cursor.description or []
    cols = [d[0] for d in description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def query_one(cursor: Any, sql: str, params: Any = None) -> dict | None:
    """Wie :func:`query`, liefert aber nur die erste Zeile (oder ``None``)."""
    rows = query(cursor, sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Spalten-Metadaten (Katalog)
# ---------------------------------------------------------------------------

def get_columns(cursor: Any, schema: str, table: str) -> list[dict]:
    """Return column metadata for a table or view.

    Probiert ``SYS.TABLE_COLUMNS`` zuerst (lokale/replizierte Tabellen), fällt
    dann auf ``SYS.VIEW_COLUMNS`` zurück (Calculation/SQL/grafische Views).
    Jeder Eintrag: ``{name, data_type, is_nullable, position}``.

    Reines Metadaten-Lesen aus dem SYS-Katalog — keine Nutzdaten.
    """
    sql_template = (
        "SELECT COLUMN_NAME, DATA_TYPE_NAME, IS_NULLABLE, POSITION "
        "FROM {catalog} "
        "WHERE SCHEMA_NAME = ? AND {name_col} = ? "
        "ORDER BY POSITION"
    )
    for catalog, name_col in (
        ("SYS.TABLE_COLUMNS", "TABLE_NAME"),
        ("SYS.VIEW_COLUMNS", "VIEW_NAME"),
    ):
        rows = query(
            cursor,
            sql_template.format(catalog=catalog, name_col=name_col),
            (schema, table),
        )
        if rows:
            return [
                {
                    "name": r.get("COLUMN_NAME"),
                    "data_type": r.get("DATA_TYPE_NAME"),
                    "is_nullable": r.get("IS_NULLABLE"),
                    "position": r.get("POSITION"),
                }
                for r in rows
            ]
    return []
