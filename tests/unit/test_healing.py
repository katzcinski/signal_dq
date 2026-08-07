"""Healing-Artefakte (Konzept_Manuelles_Healing H1/H3) — reine SQL-Erzeugung."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.enforce import healing
from dq_core.enforce.healing import HealingError, build_patch_spec
from dq_core.enforce.split import SplitSpec, RowPredicate

SCHEMA = "SIGNAL_SCHEMA"


def _spec() -> SplitSpec:
    return SplitSpec(
        object_id="DS_SALES_ORDERS",
        source='"CORE"."DS_SALES_ORDERS"',
        predicates=[RowPredicate("amount_not_null", "missing", 'DQ_SRC."AMOUNT" IS NULL')],
        columns=["ID", "AMOUNT", "CURRENCY"],
    )


# --------------------------------------------------------------- H1 Parkbucht

def test_heal_upgrade_adds_shadow_columns():
    stmts = healing.heal_upgrade_statements(_spec(), SCHEMA)
    joined = "\n".join(stmts)
    assert '"DQ_Q_DS_SALES_ORDERS"' in joined
    for name, _type in healing.HEAL_COLUMNS:
        assert f'"{name}"' in joined
    # G2: kein Platzhalter mehr, Schema gebunden
    assert "{signal_schema}" not in joined
    assert f'"{SCHEMA}"' in joined


def test_correction_statement_targets_parking_bay_only():
    sql, params = healing.correction_statement(
        _spec(), SCHEMA, episode_id=7, keys={"ID": "42"},
        column="AMOUNT", new_value="100", actor="anna", reason="Tippfehler",
    )
    # Schreibt ausschließlich in die Parkbucht — nie in die Quelle (ADR-0002).
    assert sql.startswith(f'UPDATE "{SCHEMA}"."DQ_Q_DS_SALES_ORDERS"')
    assert '"CORE"."DS_SALES_ORDERS"' not in sql
    # Audit-Stempel + Heal-Zustand
    assert '"_DQ_HEAL_STATE" = \'corrected\'' in sql
    assert '"_DQ_CORRECTED_BY"' in sql and '"_DQ_ORIGINAL"' in sql
    # Guard: Episode + nicht freigegeben + Zeilenschlüssel
    assert '"_DQ_EPISODE_ID" = ?' in sql
    assert '"_DQ_HEAL_STATE" <> \'released\'' in sql
    assert '"ID" = ?' in sql
    assert "anna" in params and "Tippfehler" in params and 7 in params


def test_correction_rejects_unknown_and_system_columns():
    spec = _spec()
    with pytest.raises(HealingError):
        healing.correction_statement(
            spec, SCHEMA, episode_id=1, keys={"ID": "1"},
            column="NICHT_DA", new_value="x", actor="a", reason="",
        )
    with pytest.raises(HealingError):
        healing.correction_statement(
            spec, SCHEMA, episode_id=1, keys={"ID": "1"},
            column="_DQ_HEAL_STATE", new_value="released", actor="a", reason="",
        )


def test_correction_rejects_injection_in_identifiers():
    spec = SplitSpec(
        object_id="DS_X", source='"CORE"."DS_X"',
        predicates=[RowPredicate("c", "missing", "1=1")],
        columns=['ID"; DROP TABLE X --', "ID"],
    )
    with pytest.raises(HealingError):
        healing.correction_statement(
            spec, SCHEMA, episode_id=1, keys={"ID": "1"},
            column='ID"; DROP TABLE X --', new_value="x", actor="a", reason="",
        )


def test_correction_requires_row_key():
    with pytest.raises(HealingError):
        healing.correction_statement(
            _spec(), SCHEMA, episode_id=1, keys={},
            column="AMOUNT", new_value="1", actor="a", reason="",
        )


def test_recheck_uses_the_original_bad_predicate():
    sql, params = healing.recheck_statement(_spec(), SCHEMA, episode_id=7)
    assert "COUNT(*)" in sql
    assert 'DQ_SRC."AMOUNT" IS NULL' in sql          # dasselbe Prädikat wie beim Parken
    assert '"_DQ_EPISODE_ID" = ?' in sql
    assert params == (7,)


def test_recheck_without_row_predicates_is_explicit():
    spec = SplitSpec(object_id="DS_X", source='"C"."DS_X"', predicates=[], columns=["ID"])
    with pytest.raises(HealingError):
        healing.recheck_statement(spec, SCHEMA, episode_id=1)


def test_correct_row_procedure_is_definer_and_guarded():
    ddl = healing.correct_row_procedure_ddl()
    assert "SQL SECURITY DEFINER" in ddl
    # Zwei Verteidigungslinien: Registry-Lookup + Katalog-Prüfung der Spalten
    assert '"DQ_OBJECTS"' in ddl and "SYS.TABLE_COLUMNS" in ddl
    # Systemspalten sind nicht korrigierbar
    assert "COLUMN_NAME NOT LIKE" in ddl
    # Jede Ausführung auditiert
    assert '"DQ_HEAL_LOG"' in ddl


def test_procedure_is_part_of_the_desired_state():
    from dq_core.enforce import desired_objects

    names = {o.name for o in desired_objects()}
    assert "P_DQ_CORRECT_ROW" in names
    assert "DQ_HEAL_LOG" in names  # aus Remote-Migration 003


# ------------------------------------------------------------- H3 Patch-Overlay

def _patch_spec():
    return build_patch_spec(
        "DS_SALES_ORDERS", '"CORE"."DS_SALES_ORDERS"',
        key_columns=["ID"], patch_columns=["AMOUNT"],
        all_columns=["ID", "AMOUNT", "CURRENCY"],
    )


def test_patch_spec_validates_shape():
    with pytest.raises(HealingError):
        build_patch_spec("O", "S", key_columns=[], patch_columns=["A"], all_columns=["A"])
    with pytest.raises(HealingError):
        build_patch_spec("O", "S", key_columns=["A"], patch_columns=[], all_columns=["A"])
    # Schlüssel dürfen nicht gepatcht werden
    with pytest.raises(HealingError):
        build_patch_spec("O", "S", key_columns=["A"], patch_columns=["A"], all_columns=["A"])


def test_patch_table_lives_in_the_signal_schema():
    ddl = healing.patch_table_ddl(_patch_spec(), SCHEMA)
    assert f'CREATE TABLE "{SCHEMA}"."DQ_PATCH_DS_SALES_ORDERS"' in ddl
    assert "WHERE 1 = 0" in ddl                       # Typen aus der Quelle, keine Daten
    assert '"_DQ_PATCH_STATUS"' in ddl and '"_DQ_VALID_UNTIL"' in ddl


def test_healed_view_coalesces_patch_over_source():
    ddl = healing.healed_view_ddl(_patch_spec(), SCHEMA)
    assert f'CREATE OR REPLACE VIEW "{SCHEMA}"."V_DQ_HEALED_DS_SALES_ORDERS"' in ddl
    # Gepatchte Spalte via COALESCE, ungepatchte direkt aus der Quelle
    assert 'COALESCE(DQ_P."AMOUNT", DQ_SRC."AMOUNT")' in ddl
    assert 'DQ_SRC."CURRENCY" AS "CURRENCY"' in ddl
    assert 'COALESCE(DQ_P."CURRENCY"' not in ddl
    # Nur aktive, nicht abgelaufene Patches wirken
    assert '"_DQ_PATCH_STATUS" = \'active\'' in ddl
    assert '"_DQ_VALID_UNTIL" IS NULL OR' in ddl
    # LEFT JOIN: ohne Patch bleibt die Quellzeile unverändert sichtbar
    assert "LEFT JOIN" in ddl


def test_patch_upsert_requires_complete_key_and_known_columns():
    spec = _patch_spec()
    sql, params = healing.patch_upsert_statement(
        spec, SCHEMA, patch_id="p-1", keys={"ID": "42"}, values={"AMOUNT": "100"},
        actor="bob", reason="Quellfehler", valid_until=None,
    )
    assert f'UPSERT "{SCHEMA}"."DQ_PATCH_DS_SALES_ORDERS"' in sql
    assert "p-1" in params and "bob" in params

    with pytest.raises(HealingError):      # unvollständiger Schlüssel
        healing.patch_upsert_statement(
            spec, SCHEMA, patch_id="p", keys={}, values={"AMOUNT": "1"}, actor="b", reason="",
        )
    with pytest.raises(HealingError):      # Spalte ist nicht patchbar
        healing.patch_upsert_statement(
            spec, SCHEMA, patch_id="p", keys={"ID": "1"}, values={"CURRENCY": "EUR"},
            actor="b", reason="",
        )
    with pytest.raises(HealingError):      # leerer Patch
        healing.patch_upsert_statement(
            spec, SCHEMA, patch_id="p", keys={"ID": "1"}, values={}, actor="b", reason="",
        )


def test_patch_revoke_keeps_the_audit_row():
    sql, params = healing.patch_revoke_statement(_patch_spec(), SCHEMA, "p-1")
    assert sql.startswith(f'UPDATE "{SCHEMA}"."DQ_PATCH_DS_SALES_ORDERS"')
    assert "revoked" in sql and "DELETE" not in sql
    assert params == ("p-1",)


def test_manifest_hash_changes_with_the_shape():
    a = _patch_spec()
    b = build_patch_spec(
        "DS_SALES_ORDERS", '"CORE"."DS_SALES_ORDERS"',
        key_columns=["ID"], patch_columns=["AMOUNT", "CURRENCY"],
        all_columns=["ID", "AMOUNT", "CURRENCY"],
    )
    assert a.manifest_hash != b.manifest_hash
