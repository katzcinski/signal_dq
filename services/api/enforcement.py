"""Materialisierung der Gate-Konsum-Oberfläche (Slices ③–⑦). [ENGINE-FROZEN]

Führt die von `dq_core.enforce` erzeugte DDL/DML gegen das Signal-eigene
Open-SQL-Schema aus — über dieselbe Verbindungsidentität wie die Checks
(ADR-0002-Amendment: read-only gegenüber Kundendaten, Schreiben nur im
eigenen Schema). Doppelt gegated: `ENFORCEMENT_MATERIALIZE_ENABLED`
(Kill-Switch, default aus) UND `DATASPHERE_SIGNAL_SCHEMA` (Ziel-Schema).

Slices ④–⑦: Split-Artefakte (CLEAN-Tabellen, Variante A) + Reconciler,
episodische Quarantäne (Snapshot, Episoden-Spiegel, Release-View, TTL),
SQL-Bridge-Poller-Helfer und Outbound-Trigger — jeweils hinter eigenen
Opt-ins, alle Default aus.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any

from dq_core.enforce import bootstrap_plan, split, verdict_upsert_statements

logger = logging.getLogger("dq_cockpit.enforcement")

# Bootstrap ist idempotent, aber nicht gratis (Katalog-Query + DDL) — je
# Prozess und Schema nur einmal, sofern kein force-Apply kommt.
_bootstrapped: set[str] = set()
_bootstrap_lock = threading.Lock()


def materialization_enabled(settings) -> bool:
    return bool(
        getattr(settings, "enforcement_materialize_enabled", False)
        and getattr(settings, "datasphere_signal_schema", "")
    )


def _existing_tables(conn: Any, schema: str) -> set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM SYS.TABLES WHERE SCHEMA_NAME = ?", (schema,)
        )
        rows = cursor.fetchall() or []
        return {str(row[0]) for row in rows if row and row[0]}
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass


def ensure_bootstrap(conn: Any, settings, *, force: bool = False) -> list[str]:
    """Gate-Infrastruktur sicherstellen (Tabellen nur wenn abwesend,
    View/Prozedur CREATE OR REPLACE). Liefert die ausgeführten Statements."""
    if not materialization_enabled(settings) or conn is None:
        return []
    schema = settings.datasphere_signal_schema
    with _bootstrap_lock:
        if schema in _bootstrapped and not force:
            return []
        statements = bootstrap_plan(
            existing_tables=_existing_tables(conn, schema),
            schema=schema,
            include_bridge=bool(getattr(settings, "enforcement_sql_bridge_enabled", False)),
        )
        cursor = conn.cursor()
        try:
            for stmt in statements:
                cursor.execute(stmt)
        finally:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass
        _bootstrapped.add(schema)
        if statements:
            logger.info("Enforcement bootstrap applied %d statement(s) in %s", len(statements), schema)
        return statements


def publish_verdict(conn: Any, summary, settings, *, contract_id: str = "") -> bool:
    """Verdict eines abgeschlossenen Laufs in DQ_GATE_STATUS(+HISTORY)
    publizieren. Projektion, nie primär: der Result-Store bleibt die Wahrheit —
    Fehler hier dürfen den Lauf nicht beeinflussen (Aufrufer fängt ab)."""
    if not materialization_enabled(settings) or conn is None:
        return False
    ensure_bootstrap(conn, settings)
    statements = verdict_upsert_statements(
        schema=settings.datasphere_signal_schema,
        object_id=summary.dataset,
        run_id=summary.run_id,
        gate_verdict=summary.gate_verdict,
        overall_status=summary.overall_status,
        evaluated_at=summary.finished_at or summary.started_at,
        contract_id=contract_id or summary.dataset,
        contract_version=summary.contract_version,
        manifest=summary.contract_hash,
        ttl_seconds=int(getattr(settings, "enforcement_verdict_ttl_seconds", 0) or 0),
    )
    cursor = conn.cursor()
    try:
        for sql, params in statements:
            cursor.execute(sql, params)
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass
    logger.info(
        "Published gate verdict %s for %s (run %s)",
        summary.gate_verdict, summary.dataset, summary.run_id,
    )
    return True


def reset_bootstrap_cache() -> None:
    """Testhilfe/Force-Reset — nächster Aufruf prüft den Katalog erneut."""
    with _bootstrap_lock:
        _bootstrapped.clear()


# ---------------------------------------------------------------------------
# Gemeinsame Helfer (Slices ④–⑥)
# ---------------------------------------------------------------------------

def _execute(conn: Any, statements: list) -> None:
    """Statements (str oder (sql, params)) über einen Cursor ausführen."""
    cursor = conn.cursor()
    try:
        for stmt in statements:
            if isinstance(stmt, tuple):
                cursor.execute(stmt[0], stmt[1])
            else:
                cursor.execute(stmt)
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass


def _fetch_all(conn: Any, sql: str, params: tuple = ()) -> list:
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params) if params else cursor.execute(sql)
        return list(cursor.fetchall() or [])
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass


def get_enforcement_connection(settings) -> Any | None:
    """Verbindung für Enforcement-Arbeiten außerhalb des Lauf-Pfads
    (Bridge-Poller, Episoden-Spiegel, Reconciler). None, wenn kein
    `ENFORCEMENT_ENVIRONMENT` konfiguriert oder unbekannt ist."""
    env_name = getattr(settings, "enforcement_environment", "") or ""
    if not env_name or not materialization_enabled(settings):
        return None
    from .deps import get_environment

    env_cfg = get_environment(env_name)
    if env_cfg is None:
        logger.warning("enforcement_environment %r ist nicht konfiguriert", env_name)
        return None
    from dq_core.connect.db_connection import get_connection

    return get_connection(
        host=env_cfg.get("host", ""),
        port=int(env_cfg.get("port", 443)),
        user=env_cfg.get("user", ""),
        password=env_cfg.get("password", ""),
        schema=settings.datasphere_signal_schema,
    )


# ---------------------------------------------------------------------------
# Slice ④ — Split-Artefakte (Variante A) + Registry
# ---------------------------------------------------------------------------

def desired_split_specs(settings, inventory: list[dict], *, default_schema: str = "") -> list[split.SplitSpec]:
    """Soll-Zustand der Split-Artefakte aus den kompilierten Checks-Dateien.
    Quell-Schema je Objekt aus dem Inventar (Fallback: default_schema) —
    Laufzeit-Bindung wie im Lauf-Pfad (G2)."""
    from pathlib import Path

    from dq_core.contract.compiler import bind_schema
    from dq_core.engine.check_engine import load_dataset_config

    base = Path(settings.checks_dir)
    if not base.exists():
        return []
    files = sorted(set(
        list(base.glob("*.yml")) + list(base.glob("*.yaml"))
        + list(base.glob("*/checks.yml")) + list(base.glob("*/checks.yaml"))
    ))
    by_id = {
        (o.get("id") or o.get("technicalName") or o.get("name")): o
        for o in inventory
    }
    specs: list[split.SplitSpec] = []
    for path in files:
        try:
            config = load_dataset_config(path)
        except Exception:  # noqa: BLE001 — kaputte Datei blockiert den Plan nicht
            continue
        obj = by_id.get(config.dataset) or {}
        schema = obj.get("schema") or default_schema
        if not schema:
            continue
        try:
            bind_schema(config, schema)
        except Exception:  # noqa: BLE001
            continue
        columns: list[str] = []
        for col in obj.get("columns") or []:
            if isinstance(col, dict) and col.get("name"):
                columns.append(str(col["name"]))
            elif isinstance(col, str):
                columns.append(col)
        spec = split.build_spec(config.dataset, config.checks, columns=columns)
        if spec is not None:
            specs.append(spec)
    return specs

def _style_wants(style: str, part: str) -> bool:
    """quarantine.style (Contract-Policy): continuous | episodic | both."""
    return style == "both" or style == part


def ensure_split_artifacts(conn: Any, settings, spec: split.SplitSpec, *, style: str = "both") -> list[str]:
    """CLEAN-/Quarantäne-Tabelle + Release-View sicherstellen und in der
    Registry verbuchen — gesteuert durch die Contract-Policy `quarantine.style`.
    Tabellen nie ersetzen (tragen Zustand); die View ist idempotent
    CREATE OR REPLACE."""
    schema = settings.datasphere_signal_schema
    existing = _existing_tables(conn, schema)
    applied: list[str] = []
    statements: list = []
    desired: list[tuple[str, str]] = []
    if _style_wants(style, "continuous") and spec.predicates:
        if spec.clean_table not in existing:
            statements.append(split.clean_create_ddl(spec, schema))
            applied.append(spec.clean_table)
        desired.append((spec.clean_table, "table"))
    if _style_wants(style, "episodic"):
        if spec.quarantine_table not in existing:
            statements.append(split.quarantine_create_ddl(spec, schema))
            applied.append(spec.quarantine_table)
        statements.append(split.released_view_ddl(spec, schema))
        desired.append((spec.quarantine_table, "table"))
        desired.append((spec.released_view, "view"))
    for name, kind in desired:
        statements.append(split.registry_upsert_statement(
            schema, name=name, kind=kind, object_id=spec.object_id,
            hash_=spec.manifest_hash, status="active",
        ))
    _execute(conn, statements)
    return applied


def refresh_clean(conn: Any, settings, spec: split.SplitSpec) -> bool:
    """CLEAN-Bestand je Lauf erneuern — punktgenau konsistent zum Verdict."""
    statements = split.clean_refresh_statements(spec, settings.datasphere_signal_schema)
    if not statements:
        return False
    _execute(conn, statements)
    return True


def reconcile_split(conn: Any, settings, specs: list[split.SplitSpec]) -> dict[str, Any]:
    """Desired-State-Abgleich (Konzept §7): Soll sicherstellen, Drift beheben,
    Waisen invalidieren, nach Grace-Period droppen. `DQ_Q_*` ist vom Drop
    ausgenommen — geparkte Zeilen verwaisen nicht, sie laufen ab (TTL)."""
    schema = settings.datasphere_signal_schema
    registry = {
        str(row[0]): {"kind": str(row[1]), "hash": str(row[3] or ""), "status": str(row[4] or "")}
        for row in _fetch_all(conn, split.registry_select_statement(schema))
    }

    # Drift (Prädikat-/Spalten-Änderung): CLEAN ist abgeleiteter Bestand →
    # Drop + Neuanlage, der nächste Refresh füllt. DQ_Q trägt geparkte Zeilen →
    # nie droppen, Drift nur ausweisen (Episoden laufen über TTL aus).
    drifted: list[str] = []
    drift_kept: list[str] = []
    for spec in specs:
        reg = registry.get(spec.clean_table)
        if reg and reg["status"] == "active" and reg["hash"] and reg["hash"] != spec.manifest_hash:
            _execute(conn, [split.drop_statement(schema, name=spec.clean_table, kind="table")])
            drifted.append(spec.clean_table)
        reg_q = registry.get(spec.quarantine_table)
        if reg_q and reg_q["status"] == "active" and reg_q["hash"] and reg_q["hash"] != spec.manifest_hash:
            drift_kept.append(spec.quarantine_table)

    ensured: list[str] = []
    for spec in specs:
        ensured.extend(ensure_split_artifacts(conn, settings, spec))

    desired_names = {
        name for spec in specs
        for name in (spec.clean_table, spec.quarantine_table, spec.released_view)
    }
    invalidated: list[str] = []
    dropped: list[str] = []
    grace_days = int(getattr(settings, "reconciler_drop_grace_days", 14) or 0)
    for name, reg in registry.items():
        if name in desired_names or not name.startswith(("DQ_CLEAN_", "DQ_Q_", "V_DQ_RELEASED_")):
            continue
        if reg["status"] == "active":
            # Invalidate zuerst — nie sofort droppen (Kunden-Flows referenzieren
            # das Artefakt möglicherweise als Quelle). CLEAN wird ab jetzt nicht
            # mehr refresht; der Drop nach Grace bricht den Import laut (O9).
            _execute(conn, [split.registry_mark_statement(schema, name=name, status="invalidated")])
            invalidated.append(name)
        elif reg["status"] == "invalidated" and not name.startswith("DQ_Q_"):
            due = _fetch_all(conn, *_grace_due_statement(schema, name, grace_days))
            if due and due[0] and int(due[0][0] or 0) == 1:
                _execute(conn, [
                    split.drop_statement(schema, name=name, kind=reg["kind"]),
                    split.registry_mark_statement(schema, name=name, status="dropped"),
                ])
                dropped.append(name)
    return {
        "ensured": ensured, "invalidated": invalidated, "dropped": dropped,
        "drifted": drifted, "drift_kept": drift_kept,
    }


def _grace_due_statement(schema: str, name: str, grace_days: int) -> tuple[str, tuple]:
    from dq_core.enforce import bind_signal_schema
    sql = bind_signal_schema(
        'SELECT CASE WHEN "INVALIDATED_AT" < ADD_DAYS(CURRENT_UTCTIMESTAMP, ?) THEN 1 ELSE 0 END '
        'FROM "{signal_schema}"."DQ_OBJECTS" WHERE "NAME" = ?',
        schema,
    )
    return sql, (-abs(int(grace_days)), name)


# ---------------------------------------------------------------------------
# Slice ⑤ — episodische Quarantäne
# ---------------------------------------------------------------------------

def snapshot_quarantine(
    conn: Any, settings, spec: split.SplitSpec, *, episode_id: int, generation: int, run_id: str
) -> int | None:
    """Bad-Zeilen der Episode parken (idempotent je Generation) und die
    beobachtete Zeilenzahl zurückgeben."""
    if not spec.predicates:
        return None
    schema = settings.datasphere_signal_schema
    _execute(conn, [split.quarantine_snapshot_statement(
        spec, schema, episode_id=episode_id, generation=generation, run_id=run_id,
    )])
    rows = _fetch_all(conn, *split.quarantine_row_count_statement(spec, schema, episode_id))
    try:
        return int(rows[0][0]) if rows else None
    except (TypeError, ValueError, IndexError):
        return None


def mirror_episode(conn: Any, settings, episode: dict[str, Any]) -> bool:
    """Episoden-Status nach `DQ_EPISODES` spiegeln (Release-View-Grundlage)."""
    if not materialization_enabled(settings) or conn is None or not episode:
        return False
    _execute(conn, [split.episode_mirror_statement(
        settings.datasphere_signal_schema,
        episode_id=int(episode["id"]),
        object_id=str(episode.get("product", "")),
        status=str(episode.get("status", "open")),
        run_id=str(episode.get("run_id", "") or ""),
        generation=episode.get("generation"),
        row_count=episode.get("row_count"),
        opened_at=episode.get("opened_at"),
        released_at=episode.get("released_at"),
        resolved_at=episode.get("resolved_at"),
    )])
    return True


def mirror_episode_via_environment(settings, episode: dict[str, Any]) -> bool:
    """Spiegel-Variante für API-Übergänge (Release/Confirm/Reconcile), wo
    keine Lauf-Verbindung existiert — nutzt `ENFORCEMENT_ENVIRONMENT`.
    Best-effort: ohne Environment kein Spiegel (Release-View bleibt dann
    hinter dem Store zurück, bis der nächste Lauf spiegelt)."""
    conn = None
    try:
        conn = get_enforcement_connection(settings)
        if conn is None:
            return False
        return mirror_episode(conn, settings, episode)
    except Exception:  # noqa: BLE001
        logger.exception("Episoden-Spiegel fehlgeschlagen (Episode %s)", episode.get("id"))
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def expire_quarantine(conn: Any, settings, store, spec: split.SplitSpec) -> int:
    """Pflicht-TTL (§5.2): abgelaufene Zeilen purgen und überfällige,
    nicht-terminale Episoden explizit als `resolved(expired)` schließen —
    G6: nie stilles Auslassen."""
    ttl_days = int(getattr(settings, "quarantine_ttl_days", 30) or 30)
    schema = settings.datasphere_signal_schema
    _execute(conn, [split.ttl_purge_statement(spec, schema, ttl_days)])
    expired = 0
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    for episode in store.list_quarantine(product=spec.object_id, limit=200):
        if episode.get("status") in ("resolved", "superseded"):
            continue
        try:
            opened = datetime.fromisoformat(str(episode.get("opened_at", "")).replace("Z", "+00:00"))
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if opened < cutoff:
            updated = store.resolve_quarantine(int(episode["id"]), "system", reason="expired")
            if updated:
                mirror_episode(conn, settings, updated)
                expired += 1
    return expired


# ---------------------------------------------------------------------------
# Post-Run-Hook — ein Eintrittspunkt für den Lauf-Pfad (Slices ③+④+⑤)
# ---------------------------------------------------------------------------

def post_run(
    conn: Any, summary, settings, store, *,
    episode_id: int | None = None, contract_id: str = "",
    policy: dict[str, Any] | None = None,
) -> None:
    """Nach Lauf-Abschluss: Verdict publizieren, CLEAN refreshen, bei
    Quarantäne-Verdict Snapshot + Episoden-Spiegel, TTL-Housekeeping —
    gesteuert durch die Contract-Policy `quarantine.style` (Default `both`).
    Nie run-kritisch — der Aufrufer fängt Fehler ab; Result-Store bleibt
    primäre Wahrheit."""
    if not materialization_enabled(settings) or conn is None:
        return
    publish_verdict(conn, summary, settings, contract_id=contract_id)

    style = str((policy or {}).get("style") or "both")
    spec = split.build_spec(summary.dataset, summary.results)
    if spec is None:
        if episode_id is not None:
            episode = store.get_quarantine(episode_id)
            mirror_episode(conn, settings, episode)
        return

    ensure_split_artifacts(conn, settings, spec, style=style)
    if _style_wants(style, "continuous"):
        refresh_clean(conn, settings, spec)

    if episode_id is not None and summary.gate_verdict == "quarantine":
        episode = store.get_quarantine(episode_id) or {}
        if _style_wants(style, "episodic"):
            count = snapshot_quarantine(
                conn, settings, spec,
                episode_id=episode_id,
                generation=int(episode.get("generation", 1) or 1),
                run_id=summary.run_id,
            )
            if count is not None and episode.get("status") in ("open", "reconciled"):
                episode = store.reconcile_quarantine(episode_id, count) or episode
        mirror_episode(conn, settings, episode)

    if _style_wants(style, "episodic"):
        expire_quarantine(conn, settings, store, spec)


def auto_release(
    settings, store, *, object_id: str, policy: dict[str, Any] | None, conn: Any = None
) -> int:
    """Self-Healing L4 (Default aus): offene/reconciled Episoden automatisch
    freigeben, wenn die letzten N Läufe des Objekts durchgängig `proceed`
    waren (Policy `quarantine.auto_release_after_green_runs` je Contract).
    Store-seitig immer möglich; der HANA-Spiegel läuft mit, wenn eine
    Verbindung da ist."""
    n = int((policy or {}).get("auto_release_after_green_runs") or 0)
    if n <= 0:
        return 0
    runs = [r for r in store.get_runs(object_id, limit=n * 2) if r.get("run_state") == "finished"]
    recent = runs[:n]
    if len(recent) < n or any((r.get("gate_verdict") or "proceed") != "proceed" for r in recent):
        return 0
    released = 0
    for episode in store.list_quarantine(product=object_id, limit=50):
        if episode.get("status") not in ("open", "reconciled"):
            continue
        updated = store.release_quarantine(
            int(episode["id"]), "system",
            note=f"Auto-Release: {n} aufeinanderfolgende grüne Läufe",
        )
        if updated:
            released += 1
            if conn is not None:
                try:
                    mirror_episode(conn, settings, updated)
                except Exception:  # noqa: BLE001
                    pass
    return released


# ---------------------------------------------------------------------------
# Slice ⑥ — Bridge-Poller (Claim-Muster wie dq_schedules)
# ---------------------------------------------------------------------------

_WORKER_ID = f"signal-{uuid.uuid4().hex[:12]}"


def bridge_enabled(settings) -> bool:
    return bool(
        getattr(settings, "enforcement_sql_bridge_enabled", False)
        and materialization_enabled(settings)
        and getattr(settings, "enforcement_environment", "")
    )


def bridge_tick(settings, store, inventory: list[dict], *, launch) -> int:
    """Ein Poller-Tick: offene Requests claimen und Läufe starten, danach
    abgeschlossene Läufe zurückstempeln (done/error — G6, nie still).
    `launch(object_id, obj, env_cfg) -> run_id|None` injizierbar (Tests)."""
    from dq_core.enforce import bridge as bridge_sql

    if not bridge_enabled(settings):
        return 0
    conn = get_enforcement_connection(settings)
    if conn is None:
        return 0
    schema = settings.datasphere_signal_schema
    launched = 0
    try:
        ensure_bootstrap(conn, settings)
        from .deps import get_environment
        env_cfg = get_environment(settings.enforcement_environment)

        for row in _fetch_all(conn, bridge_sql.select_requested_statement(schema)):
            request_id, object_id = str(row[0]), str(row[1])
            _execute(conn, [bridge_sql.claim_statement(schema, request_id=request_id, claimed_by=_WORKER_ID)])
            obj = next(
                (o for o in inventory
                 if (o.get("id") or o.get("technicalName") or o.get("name")) == object_id),
                None,
            )
            if obj is None:
                _execute(conn, [bridge_sql.finish_statement(schema, request_id=request_id, status="error")])
                logger.warning("bridge: Objekt %r nicht im Inventar — Request %s error", object_id, request_id)
                continue
            run_id = launch(object_id, obj, env_cfg)
            if run_id:
                _execute(conn, [bridge_sql.stamp_run_statement(schema, request_id=request_id, run_id=run_id)])
                launched += 1
            else:
                _execute(conn, [bridge_sql.finish_statement(schema, request_id=request_id, status="error")])

        # Abschluss-Stempel für zuvor geclaimte Requests dieses Workers.
        for row in _fetch_all(conn, *bridge_sql.select_claimed_statement(schema, claimed_by=_WORKER_ID)):
            request_id, run_id = str(row[0]), str(row[1])
            run = store.get_run(run_id)
            if not run or run.get("run_state") == "running":
                continue
            status = "done" if run.get("run_state") == "finished" else "error"
            _execute(conn, [bridge_sql.finish_statement(schema, request_id=request_id, status=status)])
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return launched


# ---------------------------------------------------------------------------
# Capability-Probe (Rest-O5/O6) — Pre-Flight VOR der Aktivierung
# ---------------------------------------------------------------------------

# Manuell zu verprobende Fähigkeiten (nicht automatisierbar — Data-Builder-UI
# bzw. zweiter DB-User nötig). Sie erscheinen als status='manual' in der Liste,
# bis jemand das Ergebnis über den Endpoint einträgt (G6: sichtbar offen).
MANUAL_CAPABILITIES: dict[str, str] = {
    "flow_table_import": "Tabelle aus dem Open-SQL-Schema im Data Builder importieren (zeigt live auf hdbtable) — laut Tenant-Erkenntnis 2026-07-11 bestätigt, hier gegenprüfen",
    "flow_view_import": "View aus dem Open-SQL-Schema als Flow-Quelle importierbar? (nur Split-Variante B)",
    "cross_space_sharing": "Importierte Entität per Sharing in einen zweiten Space reichen",
    "execute_grant_foreign_user": "EXECUTE auf P_DQ_ASSERT_GATE an fremden DB-User granten (nur Rezept R-D)",
    "invalidate_drop_loud": "O9: Flow bricht beim Drop der importierten hdbtable LAUT (kein stilles Leerlaufen)",
    "api_task_status_codes": "O8: Statuscode-Erwartung des API-Tasks am Tenant (202+Location, Polling-Verhalten)",
}


def run_capability_probes(conn: Any, settings, store) -> dict[str, dict[str, str]]:
    """Automatisierbare Fähigkeiten am Tenant verproben (harmlose Probe-Objekte
    im eigenen Schema, sofort wieder gedroppt) und Ergebnisse persistieren.
    Manuelle Checks werden als offen registriert, nie überschrieben, wenn
    bereits ein Ergebnis eingetragen wurde."""
    from dq_core.enforce import bind_signal_schema

    schema = settings.datasphere_signal_schema
    suffix = uuid.uuid4().hex[:8].upper()
    results: dict[str, dict[str, str]] = {}

    def _probe(key: str, statements: list[str], cleanup: list[str], *, unavailable_ok: bool = False):
        cursor = conn.cursor()
        try:
            for stmt in statements:
                cursor.execute(bind_signal_schema(stmt, schema))
            results[key] = {"status": "ok", "detail": ""}
        except Exception as exc:  # noqa: BLE001
            status = "unavailable" if unavailable_ok else "error"
            results[key] = {"status": status, "detail": str(exc)[:300]}
        finally:
            for stmt in cleanup:
                try:
                    cursor.execute(bind_signal_schema(stmt, schema))
                except Exception:  # noqa: BLE001
                    pass
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass

    table = f"DQ_PROBE_{suffix}"
    _probe(
        "open_sql_table_write",
        [f'CREATE TABLE "{{signal_schema}}"."{table}" ("X" INTEGER)',
         f'INSERT INTO "{{signal_schema}}"."{table}" VALUES (1)',
         f'SELECT COUNT(*) FROM "{{signal_schema}}"."{table}"'],
        [f'DROP TABLE "{{signal_schema}}"."{table}"'],
    )
    view = f"DQ_PROBE_V_{suffix}"
    _probe(
        "open_sql_view",
        [f'CREATE OR REPLACE VIEW "{{signal_schema}}"."{view}" AS SELECT 1 AS "X" FROM DUMMY',
         f'SELECT "X" FROM "{{signal_schema}}"."{view}"'],
        [f'DROP VIEW "{{signal_schema}}"."{view}"'],
    )
    proc = f"DQ_PROBE_P_{suffix}"
    _probe(
        "sqlscript_sync",  # O6 — gates P_DQ_GATE (Bridge-Warte-Schleife)
        [(f'CREATE OR REPLACE PROCEDURE "{{signal_schema}}"."{proc}" ()\n'
          "LANGUAGE SQLSCRIPT AS\nBEGIN\n  USING SQLSCRIPT_SYNC AS DQ_SYNC;\n"
          "  CALL DQ_SYNC:SLEEP_SECONDS(1);\nEND"),
         f'CALL "{{signal_schema}}"."{proc}" ()'],
        [f'DROP PROCEDURE "{{signal_schema}}"."{proc}"'],
        unavailable_ok=True,
    )
    _probe(
        "catalog_tables_read",
        ["SELECT COUNT(*) FROM SYS.TABLES WHERE SCHEMA_NAME = CURRENT_SCHEMA"],
        [],
    )

    env_name = getattr(settings, "enforcement_environment", "") or ""
    for key, res in results.items():
        store.set_capability(key, res["status"], res["detail"], env_name)
    existing = {c["key"] for c in store.list_capabilities()}
    for key, hint in MANUAL_CAPABILITIES.items():
        if key not in existing:
            store.set_capability(key, "manual", hint, env_name)
    return results


# ---------------------------------------------------------------------------
# Slice ⑦ — Outbound-Trigger (Remediation-Chain)
# ---------------------------------------------------------------------------

def trigger_remediation(settings, store, *, object_id: str, run_id: str) -> bool:
    """Bei `quarantine`-Verdict die hinterlegte Remediation-/Split-Chain
    auslösen. Kein Daten-Schreiben, aber ein Handeln auf dem Tenant —
    deshalb eigener Opt-in (`DATASPHERE_ALLOW_TRIGGER`, Default aus) und
    Audit über den Operations-Kanal (ADR-0005)."""
    if not getattr(settings, "datasphere_allow_trigger", False):
        return False
    mapping = (getattr(settings, "quarantine_trigger_chains", {}) or {}).get(object_id, "")
    space, _, chain = str(mapping).partition("/")
    if not space or not chain:
        return False
    from .datasphere import get_client

    client = get_client()
    if client is None:
        logger.warning("Outbound-Trigger konfiguriert, aber kein Datasphere-Client (Connector prüfen)")
        return False
    op_id = str(uuid.uuid4())
    store.begin_operation(op_id, "chain_trigger", created_by="system")
    try:
        client.trigger_task_chain(space, chain)
    except Exception as exc:  # noqa: BLE001
        store.finish_operation(op_id, "error", error=str(exc))
        logger.exception("Outbound-Trigger fehlgeschlagen: %s/%s (Objekt %s)", space, chain, object_id)
        return False
    store.finish_operation(op_id, "done", result_json=json.dumps({
        "space": space, "chain": chain, "object_id": object_id, "run_id": run_id,
    }))
    logger.info("Remediation-Chain %s/%s für %s ausgelöst (Run %s)", space, chain, object_id, run_id)
    return True
