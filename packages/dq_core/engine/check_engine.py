from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .expectation import evaluate, validate_expectation
from .models import (
    CheckDef,
    CheckResult,
    DatasetConfig,
    RunSummary,
    VALID_ENFORCEMENT,
    VALID_KINDS,
    VALID_SEVERITIES,
)
from ..library.check_library import check_ids_where
from ..store.sqlite_store import ResultStore


def load_dataset_config(path: Path, *, allow_empty: bool = False) -> DatasetConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Checks-Datei muss ein YAML-Objekt enthalten.")

    dataset = str(raw.get("dataset") or "").strip()
    schema = str(raw.get("schema") or "").strip()
    checks_raw = raw.get("checks")
    if not dataset:
        raise ValueError('"dataset" ist erforderlich.')
    if not schema:
        raise ValueError('"schema" ist erforderlich.')
    if checks_raw is None:
        checks_raw = []
    if not isinstance(checks_raw, list):
        raise ValueError('"checks" muss eine Liste sein.')
    if not checks_raw and not allow_empty:
        raise ValueError("Mindestens ein Check ist erforderlich.")

    seen: set[str] = set()
    checks: list[CheckDef] = []
    for index, item in enumerate(checks_raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Check #{index}: Objekt erwartet.")
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError(f'Check #{index}: "name" fehlt.')
        if name in seen:
            raise ValueError(f'Doppelter Check-Name: "{name}"')
        seen.add(name)

        sql = str(item.get("sql") or "").strip()
        expect = str(item.get("expect") or "").strip()
        severity = str(item.get("severity") or "fail").strip().lower()
        kind = str(item.get("kind") or "internal_gate").strip()
        enforcement = str(item.get("enforcement") or "monitor").strip().lower()
        if not sql:
            raise ValueError(f'Check "{name}": "sql" fehlt.')
        if not expect:
            raise ValueError(f'Check "{name}": "expect" fehlt.')
        if severity not in VALID_SEVERITIES:
            raise ValueError(f'Check "{name}": severity muss critical/fail/warn sein.')
        if kind not in VALID_KINDS:
            raise ValueError(f'Check "{name}": kind muss internal_gate/consumer_contract/provider_contract sein.')
        if enforcement not in VALID_ENFORCEMENT:
            raise ValueError(f'Check "{name}": enforcement muss gate/quarantine/monitor sein.')
        try:
            validate_expectation(expect)
        except ValueError as exc:
            raise ValueError(f'Check "{name}": Ungueltiger Ausdruck "{expect}"') from exc

        diagnostics = item.get("diagnostics") or {}
        checks.append(
            CheckDef(
                name=name,
                sql=sql,
                expect=expect,
                severity=severity,
                description=str(item.get("description") or ""),
                timeout_s=_positive_int(item.get("timeout_s"), default=60),
                enabled=bool(item.get("enabled", True)),
                type=str(item.get("type") or "").strip(),
                unit=str(item.get("unit") or "").strip(),
                kind=kind,
                enforcement=enforcement,
                diagnostics_enabled=bool(diagnostics.get("enabled", False)),
                diagnostics_columns=[str(c) for c in (diagnostics.get("columns") or [])],
            )
        )

    return DatasetConfig(
        dataset=dataset,
        schema=schema,
        contract_version=str(raw.get("contract_version") or ""),
        checks=checks,
    )


def dataset_config_to_yaml(config: DatasetConfig) -> str:
    payload: dict[str, Any] = {
        "dataset": config.dataset,
        "schema": config.schema,
    }
    if config.contract_version:
        payload["contract_version"] = config.contract_version
    payload["checks"] = [
        {
            "name": check.name,
            "sql": check.sql,
            "expect": check.expect,
            "severity": check.severity,
            **({"description": check.description} if check.description else {}),
            "timeout_s": check.timeout_s,
            "enabled": check.enabled,
            **({"type": check.type} if check.type else {}),
            **({"unit": check.unit} if check.unit else {}),
            "kind": check.kind,
            "enforcement": check.enforcement,
            **(
                {"diagnostics": {"enabled": True, "columns": list(check.diagnostics_columns)}}
                if check.diagnostics_enabled
                else {}
            ),
        }
        for check in config.checks
    ]
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


# Gating (Konzept §2: günstige Checks gaten teure). Frische-Checks entscheiden,
# ob teure Konsistenz-Checks überhaupt sinnvoll sind — stale Daten erzeugen
# sonst Phantom-Failures. Übersprungene Checks erscheinen IMMER als explizites
# Ergebnis mit state='skipped_stale' (G6), nie als stilles Auslassen.
#
# Die Klassifikation (gate | expensive | standard) lebt in der Check-Bibliothek
# (`library/check_library.json`, Feld `gating`) — Single Source of Truth statt
# hier dupliziert. Ein neuer Check wird dadurch automatisch korrekt gegated.
GATE_TYPES: frozenset[str] = check_ids_where("gating", "gate")
EXPENSIVE_TYPES: frozenset[str] = check_ids_where("gating", "expensive")


def run_checks(
    config: DatasetConfig,
    conn: Any,
    results_db: Path | None,
    on_progress: Callable[[str], None] | None = None,
    *,
    triggered_by: str = "ui",
    execution_mode: str = "auto",
    gating: bool = False,
) -> RunSummary:
    run_id = str(uuid.uuid4())
    started_at = _utc_now()
    enabled_checks = [check for check in config.checks if check.enabled]
    mode = str(execution_mode or "auto").strip().lower()
    if mode not in {"auto", "batch", "isolated"}:
        raise ValueError("execution_mode muss auto, batch oder isolated sein.")

    previous: dict[str, str] = {}
    if results_db is not None and Path(results_db).exists():
        try:
            previous = ResultStore(Path(results_db)).get_previous_actuals(config.dataset)
        except Exception:  # noqa: BLE001
            pass

    if not enabled_checks:
        results: list[CheckResult] = []
    elif gating:
        results = _run_with_gating(conn, enabled_checks, mode, on_progress, previous)
    else:
        results = _execute(conn, enabled_checks, mode, on_progress, previous)

    overall = _overall_status(results)
    verdict = _gate_verdict(results)
    executed = [r for r in results if r.state in ("executed", "error")]
    summary = RunSummary(
        run_id=run_id,
        dataset=config.dataset,
        schema=config.schema,
        started_at=started_at,
        finished_at=_utc_now(),
        overall_status=overall,
        total=len(results),
        passed=sum(1 for result in executed if result.passed),
        failed=sum(1 for result in executed if not result.passed and result.severity in {"critical", "fail"}),
        warnings=sum(1 for result in executed if not result.passed and result.severity == "warn"),
        results=results,
        triggered_by=triggered_by,
        gate_verdict=verdict,
    )

    if results_db is not None:
        ResultStore(Path(results_db)).save_run(summary)

    return summary


def _execute(
    conn: Any,
    checks: list[CheckDef],
    mode: str,
    on_progress: Callable[[str], None] | None,
    previous: dict[str, str],
) -> list[CheckResult]:
    if not checks:
        return []
    if mode == "isolated":
        return _run_checks_isolated(conn, checks, on_progress, previous)
    try:
        return _run_checks_batch(conn, checks, on_progress, previous)
    except Exception as exc:  # noqa: BLE001
        if mode == "auto":
            if on_progress:
                on_progress(f"[DQ] Batch-Ausfuehrung fehlgeschlagen, wechsle auf Einzelchecks: {exc}")
            return _run_checks_isolated(conn, checks, on_progress, previous)
        message = str(exc)
        results = [_error_result(check, message, 0) for check in checks]
        for result in results:
            if on_progress:
                _emit_result_progress(result, on_progress)
        return results


def _run_with_gating(
    conn: Any,
    checks: list[CheckDef],
    mode: str,
    on_progress: Callable[[str], None] | None,
    previous: dict[str, str],
) -> list[CheckResult]:
    gates = [c for c in checks if c.type in GATE_TYPES]
    rest = [c for c in checks if c.type not in GATE_TYPES]
    gate_results = _execute(conn, gates, mode, on_progress, previous)
    stale = any(not r.passed and r.state == "executed" for r in gate_results)
    if not stale:
        return gate_results + _execute(conn, rest, mode, on_progress, previous)

    cheap = [c for c in rest if c.type not in EXPENSIVE_TYPES]
    expensive = [c for c in rest if c.type in EXPENSIVE_TYPES]
    results = gate_results + _execute(conn, cheap, mode, on_progress, previous)
    for check in expensive:
        skipped = CheckResult(
            name=check.name, sql=check.sql, expect=check.expect,
            severity=check.severity, passed=False,
            state="skipped_stale", type=check.type, kind=check.kind,
            enforcement=check.enforcement,
        )
        results.append(skipped)
        if on_progress:
            on_progress(f"[DQ]   SKIPPED (stale): {check.name} — Frische-Gate verletzt, Check uebersprungen")
    return results


def _run_checks_isolated(
    conn: Any,
    checks: list[CheckDef],
    on_progress: Callable[[str], None] | None,
    previous: dict[str, str] | None = None,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for index, check in enumerate(checks, 1):
        if on_progress:
            on_progress(f"[DQ] ({index}/{len(checks)}) Pruefe {check.name}...")
        result = _run_one_check(conn, check, previous_value=(previous or {}).get(check.name))
        results.append(result)
        if on_progress:
            _emit_result_progress(result, on_progress)
    return results


def _run_checks_batch(
    conn: Any,
    checks: list[CheckDef],
    on_progress: Callable[[str], None] | None,
    previous: dict[str, str] | None = None,
) -> list[CheckResult]:
    if on_progress:
        on_progress(f"[DQ] Fuehre {len(checks)} Checks als HANA-Batch aus...")

    t0 = time.monotonic()
    cursor = None
    try:
        cursor = conn.cursor()
        # Härtung: der Batch läuft — wie _run_one_check — mit Statement-Timeout.
        # Da alle Checks in einem Statement stecken, gilt das Maximum der
        # Einzel-Timeouts; ohne SET liefe der Batch unbegrenzt.
        timeout_ms = max(int(check.timeout_s) for check in checks) * 1000
        cursor.execute(f"SET 'statementTimeout' = '{timeout_ms}'")
        cursor.execute(_build_batch_sql(checks))
        rows = _fetch_all(cursor)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass

    elapsed = _elapsed_ms(t0)
    values_by_name = _batch_rows_to_values(rows)
    results: list[CheckResult] = []
    for check in checks:
        if check.name not in values_by_name:
            result = _error_result(check, "Batch-Ergebnis enthaelt keinen Wert fuer diesen Check.", elapsed)
        else:
            result = _result_from_actual(
                check,
                values_by_name[check.name],
                elapsed,
                previous_value=(previous or {}).get(check.name),
            )
        results.append(result)
        if on_progress:
            _emit_result_progress(result, on_progress)
    return results


def test_check(conn: Any, check: CheckDef) -> CheckResult:
    """Public entry point for single-check testing (used by the test-check API endpoint)."""
    return _run_one_check(conn, check)


def _run_one_check(conn: Any, check: CheckDef, previous_value: Any = None) -> CheckResult:
    t0 = time.monotonic()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(f"SET 'statementTimeout' = '{int(check.timeout_s) * 1000}'")
        cursor.execute(check.sql)
        description = getattr(cursor, "description", None) or []
        if len(description) > 1:
            raise ValueError("Check-SQL muss genau eine Spalte zurueckgeben.")
        row = cursor.fetchone()
        second = cursor.fetchone()
        if second is not None:
            raise ValueError("Check-SQL muss genau eine Zeile zurueckgeben.")
        actual = row[0] if row else None
        result = _result_from_actual(check, actual, _elapsed_ms(t0), previous_value=previous_value)
        # [PII-GATE] S1: Rohzeilen werden nur geholt, wenn der Check es explizit
        # erlaubt — Unterdrückung an der Quelle, nicht erst am Store.
        if not result.passed and not result.error and check.diagnostics_enabled:
            rows = _fetch_diagnostic_rows(conn, check.sql)
            if check.diagnostics_columns:
                allow = set(check.diagnostics_columns)
                rows = [{k: v for k, v in r.items() if k in allow} for r in rows]
            result.diagnostic_rows = rows
        return result
    except Exception as exc:  # noqa: BLE001
        return _error_result(check, str(exc), _elapsed_ms(t0))
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass


def _fetch_diagnostic_rows(conn: Any, sql: str) -> list[dict]:
    diag_sql = _diagnostic_sql(sql)
    if not diag_sql:
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(diag_sql)
        cols = [col[0] for col in (getattr(cursor, "description", None) or [])]
        if not cols:
            return []
        rows = cursor.fetchmany(100)
        return [dict(zip(cols, row)) for row in rows]
    except Exception:  # noqa: BLE001
        return []
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass


# Klauseln, bei denen die SELECT-*-Umschreibung die Semantik ändern oder
# ungültiges SQL erzeugen würde (SELECT * mit GROUP BY; doppeltes LIMIT;
# Set-Operationen zählen etwas anderes als Zeilen).
_DIAG_UNSAFE = re.compile(r"(?i)\b(?:GROUP\s+BY|HAVING|UNION|INTERSECT|EXCEPT|LIMIT|OFFSET)\b")


def _diagnostic_sql(sql: str) -> str | None:
    """Rewrite 'SELECT COUNT(*) FROM t WHERE ...' → 'SELECT * FROM t WHERE ... LIMIT 100'.

    [PII-GATE] Fail-closed: alles, was sich nicht sicher umschreiben lässt,
    liefert None (= keine Diagnosezeilen) statt einer semantisch falschen oder
    kaputten Query. Akzeptiert COUNT(*)/COUNT(1) mit beliebigem Whitespace und
    einen optionalen Semikolon-Terminator.
    """
    cleaned = _strip_sql_terminator(sql)
    m = re.match(
        r"(?i)^SELECT\s+COUNT\s*\(\s*(?:\*|1)\s*\)\s+(FROM\s+.+?)(?:\s+(WHERE\s+.+))?$",
        cleaned,
        re.DOTALL,
    )
    if not m:
        return None
    from_clause = m.group(1).strip()
    where_clause = (m.group(2) or "").strip()
    if _DIAG_UNSAFE.search(from_clause) or _DIAG_UNSAFE.search(where_clause):
        return None
    parts = ["SELECT *", from_clause]
    if where_clause:
        parts.append(where_clause)
    parts.append("LIMIT 100")
    return " ".join(parts)


def _result_from_actual(check: CheckDef, actual: Any, duration_ms: int, *, previous_value: Any = None) -> CheckResult:
    try:
        passed = evaluate(actual, check.expect, previous_value)
        return CheckResult(
            name=check.name,
            sql=check.sql,
            expect=check.expect,
            severity=check.severity,
            passed=passed,
            actual_value=actual,
            duration_ms=duration_ms,
            type=check.type,
            kind=check.kind,
            enforcement=check.enforcement,
        )
    except Exception as exc:  # noqa: BLE001
        return _error_result(check, str(exc), duration_ms, actual_value=actual)


def _error_result(
    check: CheckDef,
    message: str,
    duration_ms: int,
    *,
    actual_value: Any = None,
) -> CheckResult:
    return CheckResult(
        name=check.name,
        sql=check.sql,
        expect=check.expect,
        severity=check.severity,
        passed=False,
        actual_value=actual_value,
        error=message,
        duration_ms=duration_ms,
        state="error",
        type=check.type,
        kind=check.kind,
        enforcement=check.enforcement,
    )


def _build_batch_sql(checks: list[CheckDef]) -> str:
    parts = []
    for check in checks:
        sql = _strip_sql_terminator(check.sql)
        parts.append(
            "SELECT "
            f"'{_sql_string_literal(check.name)}' AS check_name, "
            f"({sql}) AS actual_value "
            "FROM DUMMY"
        )
    return "\nUNION ALL\n".join(parts)


def _strip_sql_terminator(sql: str) -> str:
    return str(sql or "").strip().rstrip(";").strip()


def _sql_string_literal(value: str) -> str:
    return str(value).replace("'", "''")


def _fetch_all(cursor: Any) -> list[Any]:
    if hasattr(cursor, "fetchall"):
        return list(cursor.fetchall())
    rows = []
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        rows.append(row)
    return rows


def _batch_rows_to_values(rows: list[Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in rows:
        if len(row) != 2:
            raise ValueError("Batch-Ergebnis muss genau zwei Spalten enthalten.")
        check_name = str(row[0])
        if check_name in values:
            raise ValueError(f'Batch-Ergebnis enthaelt doppelte Zeile fuer Check "{check_name}".')
        values[check_name] = row[1]
    return values


def _emit_result_progress(result: CheckResult, on_progress: Callable[[str], None]) -> None:
    status = _line_status(result)
    detail = f"Fehler: {result.error}" if result.error else f"Ist={result.actual_value}, Soll={result.expect}"
    on_progress(f"[DQ]   {status}: {result.name} ({detail})")


def _overall_status(results: list[CheckResult]) -> str:
    """State-bewusst (G6): übersprungene Checks zählen weder als pass noch
    als fail — sie sind sichtbar, aber statusneutral."""
    executed = [r for r in results if r.state in ("executed", "error")]
    if any(result.error for result in executed):
        return "error"
    failed = [result.severity for result in executed if not result.passed]
    if "critical" in failed:
        return "critical"
    if "fail" in failed:
        return "fail"
    if "warn" in failed:
        return "warn"
    return "pass"


def _gate_verdict(results: list[CheckResult]) -> str:
    """Enforcement-Rollup (state-bewusst wie _overall_status, G6): nur
    executed/error zählen. `monitor`-Fails eskalieren das Urteil NIE; ein
    `warn`-Fail ist ein weiches Signal und blockiert ebenfalls nicht."""
    failed = [
        r for r in results
        if r.state in ("executed", "error") and not r.passed
        and r.severity in ("critical", "fail")
    ]
    if any(r.enforcement == "gate" for r in failed):
        return "block"
    if any(r.enforcement == "quarantine" for r in failed):
        return "quarantine"
    return "proceed"


def _line_status(result: CheckResult) -> str:
    if result.passed:
        return "PASS"
    if result.error:
        return "ERROR"
    return result.severity.upper()


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
