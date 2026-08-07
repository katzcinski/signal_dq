"""„Für Monitoring verfügbar machen" — Hybrid-Modell (ADR-0002, Monitoring-Hub).

Signal schreibt **nur den Soll-Zustand**: welche Objekte überwacht werden sollen.
Ein externes, privilegiertes Skript reconciled daraus Share + Projektions-View
(``Expose for Consumption``) im Monitoring-Hub und meldet den Status zurück.
Signal selbst schreibt **nie** nach Datasphere (bleibt read-only).

Dieses Modul kapselt die Soll-Zustands-Registry (JSON) und zwei reine,
testbare Helfer: den deterministischen View-Namen und das vorgeschlagene
Projektions-SQL (explizite Spaltenliste).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import get_settings

logger = logging.getLogger("dq_cockpit.monitoring_share")

STATUS_REQUESTED = "requested"     # vom Cockpit vorgemerkt
STATUS_PROVISIONED = "provisioned"  # Skript hat Share + View angelegt
STATUS_ERROR = "error"             # Skript meldet Fehler
VALID_STATUS = {STATUS_REQUESTED, STATUS_PROVISIONED, STATUS_ERROR}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_path() -> Path:
    return Path(get_settings().data_dir) / "monitoring_shares.json"


# --- pure, testable helpers -------------------------------------------------

def view_name(source_space: str, object_id: str) -> str:
    """Deterministischer, kollisionsarmer View-Name ``<SPACE>__<OBJECT>`` — der
    Space-Präfix erlaubt die Auflösung „wo liegt's" im Cockpit."""
    raw = f"{source_space}__{object_id}"
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def normalize_columns(columns: Any) -> list[str]:
    """Spaltennamen aus heterogenem Inventar-Input ziehen (str oder {name})."""
    out: list[str] = []
    for col in columns or []:
        if isinstance(col, str):
            name = col
        elif isinstance(col, dict):
            name = col.get("name") or col.get("technicalName") or ""
        else:
            name = ""
        if name:
            out.append(str(name))
    return out


def build_projection_sql(
    *,
    monitoring_space: str,
    view: str,
    source_space: str,
    technical_name: str,
    columns: list[str],
) -> str:
    """Vorgeschlagenes Projektions-SQL für die Wrapper-View. Explizite
    Spaltenliste (schema-drift-sichtbar); ohne bekannte Spalten Fallback auf
    ``SELECT *`` — das Skript ist autoritativ und darf das überschreiben."""
    cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
    return (
        f'CREATE VIEW "{monitoring_space}"."{view}" AS '
        f'SELECT {cols} FROM "{source_space}"."{technical_name}"'
    )


# --- desired-state registry -------------------------------------------------

def load_entries() -> list[dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("monitoring_shares.json unlesbar — behandelt als leer.")
        return []
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return sorted(entries, key=lambda e: e.get("object_id", ""))


def get_entry(object_id: str) -> dict[str, Any] | None:
    return next((e for e in load_entries() if e.get("object_id") == object_id), None)


def _save(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda e: e.get("object_id", ""))
    path.write_text(json.dumps({"entries": ordered}, indent=2), encoding="utf-8")
    return ordered


def upsert_request(
    *,
    object_id: str,
    source_space: str,
    technical_name: str,
    object_type: str,
    columns: list[str],
    view: str,
) -> dict[str, Any]:
    """Objekt vormerken. Idempotent: existiert es bereits, werden die
    Identitätsfelder aktualisiert, der Status aber nicht zurückgesetzt."""
    entries = load_entries()
    existing = next((e for e in entries if e.get("object_id") == object_id), None)
    if existing is not None:
        existing.update(
            source_space=source_space, technical_name=technical_name,
            object_type=object_type, columns=columns, view=view,
        )
        _save(entries)
        return existing
    entry = {
        "object_id": object_id,
        "source_space": source_space,
        "technical_name": technical_name,
        "object_type": object_type,
        "columns": columns,
        "view": view,
        "status": STATUS_REQUESTED,
        "error": None,
        "requested_at": _now(),
        "provisioned_at": None,
    }
    entries.append(entry)
    _save(entries)
    return entry


def set_status(
    object_id: str, status: str, *, view: str | None = None, error: str | None = None
) -> dict[str, Any] | None:
    if status not in VALID_STATUS:
        raise ValueError(f"Ungültiger Status: {status!r}")
    entries = load_entries()
    entry = next((e for e in entries if e.get("object_id") == object_id), None)
    if entry is None:
        return None
    entry["status"] = status
    entry["error"] = error
    if view:
        entry["view"] = view
    if status == STATUS_PROVISIONED:
        entry["provisioned_at"] = _now()
    _save(entries)
    return entry


def remove_entry(object_id: str) -> bool:
    entries = load_entries()
    remaining = [e for e in entries if e.get("object_id") != object_id]
    if len(remaining) == len(entries):
        return False
    _save(remaining)
    return True
