"""Healing-Materialisierung (H1/H3) — Store ist Wahrheit, HANA ist Projektion.

Führt die von `dq_core.enforce.healing` erzeugten Statements gegen das
Signal-eigene Open-SQL-Schema aus. Dieselbe Disziplin wie `enforcement.py`:

* Doppelt gegated über `materialization_enabled` (Kill-Switch + Ziel-Schema).
* Die **Quelle bleibt read-only** (ADR-0002) — geschrieben wird nur in
  `DQ_Q_<OBJ>` (H1) bzw. `DQ_PATCH_<OBJ>` (H3), beide im Signal-Schema.
* Fehlschläge sind nie fachlich kritisch: die Korrektur/der Patch ist im
  Result-Store auditiert, `applied=0` weist die fehlende Projektion aus (G6).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from dq_core.enforce import healing as heal_sql
from dq_core.enforce.healing import HealingError

from .enforcement import _execute, _fetch_all, get_enforcement_connection, materialization_enabled

logger = logging.getLogger("dq_cockpit.healing")

_GOVERNANCE_KINDS = {"consumer_contract", "provider_contract"}


def contract_kind_of(product: str, settings) -> str:
    """`kind` des Contracts zu einem Objekt — bestimmt, ob die Vier-Augen-Regel
    greift. Ohne Contract gilt `internal_gate` (Engineering-Signal)."""
    contracts_dir = Path(settings.contracts_dir)
    for ext in (".yaml", ".yml"):
        path = contracts_dir / f"{product}{ext}"
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 — kaputter Contract ⇒ konservativ
            return "internal_gate"
        return str(data.get("kind", "internal_gate"))
    return "internal_gate"


def requires_four_eyes(product: str, settings) -> bool:
    """Contract-Kinds verlangen Korrigierender ≠ Freigebender (Konzept §2)."""
    return contract_kind_of(product, settings) in _GOVERNANCE_KINDS


def split_spec_for(settings, inventory: list[dict], object_id: str):
    """Split-/Quarantäne-Spezifikation eines Objekts (Prädikate + Spalten)."""
    from .enforcement import desired_split_specs

    for spec in desired_split_specs(settings, inventory):
        if spec.object_id == object_id:
            return spec
    return None


def object_columns(inventory: list[dict], object_id: str) -> list[dict[str, Any]]:
    for obj in inventory or []:
        ident = obj.get("id") or obj.get("technicalName") or obj.get("name")
        if ident == object_id:
            return list(obj.get("columns") or [])
    return []


def key_columns_of(inventory: list[dict], object_id: str) -> list[str]:
    """Schlüsselspalten aus dem Inventar (Flag `key`) — Default-Zuschnitt des
    Overlays, wenn der Aufrufer keinen eigenen angibt."""
    out = []
    for col in object_columns(inventory, object_id):
        if isinstance(col, dict) and col.get("name") and str(col.get("key", "")).strip().lower() in ("true", "1", "yes", "x"):
            out.append(str(col["name"]))
    return out


def source_of(inventory: list[dict], object_id: str, settings) -> str:
    """Gebundene Quelle `"SCHEMA"."OBJEKT"` für Patch-Artefakte (G2)."""
    for obj in inventory or []:
        ident = obj.get("id") or obj.get("technicalName") or obj.get("name")
        if ident == object_id:
            schema = str(obj.get("schema") or "")
            if schema:
                return f'"{schema}"."{object_id}"'
    return ""


# ---------------------------------------------------------------------------
# H1 — Korrektur + Re-Check
# ---------------------------------------------------------------------------

def apply_correction(
    settings, spec, *, episode_id: int, keys: dict[str, Any], column: str,
    new_value: Any, actor: str, reason: str,
) -> tuple[bool, str]:
    """Korrektur in die Parkbucht materialisieren. `(applied, error)` —
    ohne Materialisierung `(False, "")`, das ist kein Fehler."""
    if not materialization_enabled(settings):
        return False, ""
    conn = None
    try:
        conn = get_enforcement_connection(settings)
        if conn is None:
            return False, ""
        schema = settings.datasphere_signal_schema
        # Schattenspalten sind additiv; auf bestehenden Parkbuchten fehlen sie.
        for stmt in heal_sql.heal_upgrade_statements(spec, schema):
            try:
                _execute(conn, [stmt])
            except Exception:  # noqa: BLE001 — Spalte existiert bereits
                pass
        _execute(conn, [heal_sql.correction_statement(
            spec, schema, episode_id=episode_id, keys=keys, column=column,
            new_value=new_value, actor=actor, reason=reason,
        )])
        key_col = sorted(keys)[0]
        _execute(conn, [heal_sql.heal_log_statement(
            schema, table_name=spec.quarantine_table, episode_id=episode_id,
            key_column=key_col, key_value=keys[key_col], column=column,
            new_value=new_value, reason=reason, actor=actor,
        )])
        return True, ""
    except HealingError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Korrektur-Materialisierung fehlgeschlagen (Episode %s)", episode_id)
        return False, str(exc)[:300]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def run_recheck(settings, spec, episode_id: int) -> int | None:
    """Zeilen der Episode, die das Bad-Prädikat weiterhin erfüllen.
    `None` = nicht ermittelbar (keine Materialisierung/Verbindung)."""
    if not materialization_enabled(settings):
        return None
    conn = None
    try:
        conn = get_enforcement_connection(settings)
        if conn is None:
            return None
        rows = _fetch_all(conn, *heal_sql.recheck_statement(
            spec, settings.datasphere_signal_schema, episode_id,
        ))
        return int(rows[0][0]) if rows and rows[0] else 0
    except Exception:  # noqa: BLE001
        logger.exception("Re-Check fehlgeschlagen (Episode %s)", episode_id)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# H3 — Patch-Overlay
# ---------------------------------------------------------------------------

def apply_patch(settings, patch_spec, *, patch_id: str, keys: dict[str, Any],
                values: dict[str, Any], actor: str, reason: str,
                valid_until: str | None) -> tuple[bool, str]:
    """Overlay-Artefakte sicherstellen und die Patch-Zeile setzen."""
    if not materialization_enabled(settings):
        return False, ""
    conn = None
    try:
        conn = get_enforcement_connection(settings)
        if conn is None:
            return False, ""
        schema = settings.datasphere_signal_schema
        try:
            _execute(conn, [heal_sql.patch_table_ddl(patch_spec, schema)])
        except Exception:  # noqa: BLE001 — Tabelle existiert bereits
            pass
        _execute(conn, [heal_sql.healed_view_ddl(patch_spec, schema)])
        _execute(conn, [heal_sql.patch_upsert_statement(
            patch_spec, schema, patch_id=patch_id, keys=keys, values=values,
            actor=actor, reason=reason, valid_until=valid_until,
        )])
        return True, ""
    except HealingError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Patch-Materialisierung fehlgeschlagen (%s)", patch_id)
        return False, str(exc)[:300]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def revoke_patch(settings, patch_spec, patch_id: str) -> bool:
    if not materialization_enabled(settings):
        return False
    conn = None
    try:
        conn = get_enforcement_connection(settings)
        if conn is None:
            return False
        _execute(conn, [heal_sql.patch_revoke_statement(
            patch_spec, settings.datasphere_signal_schema, patch_id,
        )])
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Patch-Rücknahme fehlgeschlagen (%s)", patch_id)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
