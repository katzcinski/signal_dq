# [ENGINE-FROZEN] — pure dataclasses, zero framework imports
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

VALID_OWNERS: frozenset[str] = frozenset({"platform", "product"})
VALID_SEVERITIES: frozenset[str] = frozenset({"critical", "fail", "warn"})
VALID_KINDS: frozenset[str] = frozenset({"internal_gate", "consumer_contract", "provider_contract"})
# Durchsetzungs-Achse (orthogonal zu severity): was ein Breach auslöst.
# Default 'monitor' — nur beobachten, nie blockieren/isolieren.
VALID_ENFORCEMENT: frozenset[str] = frozenset({"gate", "quarantine", "monitor"})
VALID_VERDICTS: frozenset[str] = frozenset({"proceed", "quarantine", "block"})


@dataclass
class CheckDef:
    name: str
    sql: str
    expect: str
    severity: str = "fail"
    description: str = ""
    timeout_s: int = 60
    enabled: bool = True
    type: str = ""
    unit: str = ""
    owned_by: str = "platform"
    kind: str = "internal_gate"
    # Durchsetzung bei Breach: gate (blockieren) | quarantine (isolieren) |
    # monitor (nur beobachten). Eskaliert das Run-Verdict, nie den Status.
    enforcement: str = "monitor"
    # [PII-GATE] WS0-6: Diagnostik nur je Check mit Spalten-Allowlist.
    # Default off — ohne enabled+Allowlist verlassen keine Rohzeilen HANA.
    diagnostics_enabled: bool = False
    diagnostics_columns: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    name: str
    sql: str
    expect: str
    severity: str
    passed: bool
    actual_value: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0
    diagnostic_rows: list[dict[str, Any]] = field(default_factory=list)
    # Gating state — never silently omit (G6)
    state: str = "executed"
    # allowed: executed | skipped_stale | skipped_dependency | downgraded | error
    # Garantie-Typ des Checks (Rückverfolgbarkeit + Familien-Rollup, WS3-1)
    type: str = ""
    kind: str = "internal_gate"
    enforcement: str = "monitor"


@dataclass
class DatasetConfig:
    dataset: str
    schema: str
    contract_version: str = ""
    owned_by: str = "platform"
    checks: list[CheckDef] = field(default_factory=list)


@dataclass
class RunSummary:
    run_id: str
    dataset: str
    schema: str
    started_at: str
    finished_at: str
    overall_status: str
    total: int
    passed: int
    failed: int
    warnings: int
    results: list[CheckResult] = field(default_factory=list)
    triggered_by: str = "manual"
    contract_version: str = ""
    contract_hash: str = ""
    actor: str = ""
    run_state: str = "finished"
    # allowed: running | finished | error
    # Gate-Verdict des Laufs (Enforcement-Rollup): proceed | quarantine | block
    gate_verdict: str = "proceed"
