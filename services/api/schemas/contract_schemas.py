from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ContractIn(BaseModel):
    """Lifecycle ist bewusst KEIN Eingabefeld — Übergänge laufen nur über
    approve/deprecate; PUT erzwingt draft (S-2)."""
    product: str
    kind: str = "internal_gate"
    dataset: str = ""
    owned_by: str = "platform"
    owners: list[str] = []
    version: str = "0.1.0"
    kind: str = "internal_gate"
    description: str = ""
    guarantees: dict[str, Any] = {}
    observability: dict[str, Any] = {}
    # checks[]: library-instantiated checks (internal gates, Iteration 1). Rides
    # through model_dump() → validate → save; the compiler turns each into a
    # CheckDef. G1 stays intact — these reference library templates, never raw SQL.
    checks: list[dict[str, Any]] = []


class ContractOut(BaseModel):
    product: str
    kind: str = "internal_gate"
    dataset: str = ""
    owned_by: str = "platform"
    owners: list[str] = []
    version: str = "0.1.0"
    kind: str = "internal_gate"
    lifecycle: str = "draft"
    description: str = ""
    guarantees: dict[str, Any] = {}
    observability: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []
    compliance: Optional[str] = None
    certified: bool = False


class CheckDefOut(BaseModel):
    name: str
    sql: str
    expect: str
    severity: str
    type: str = ""
    unit: str = ""
    owned_by: str = "platform"
    kind: str = "internal_gate"


class CompileOut(BaseModel):
    product: str
    dataset: str
    checks: list[CheckDefOut] = []
    yaml_preview: str = ""
    conflicts: list[str] = []
    determinism_hash: str = ""


# ── Observed reality (P6): beobachtete Realität je Garantie ────────────────────
# Read-only-Rollup: die Garantien werden (via Compiler) auf ihre Checks
# abgebildet und mit der persistierten Result-Historie verbunden — letzter
# Messwert, Zeitreihe (Sparkline) und PASS/FAIL. Aggregat-Werte, keine Rohzeilen
# (kein PII-Gate-Belang, G8).
class ObservedPoint(BaseModel):
    at: str = ""
    value: Optional[float] = None      # numerischer actual_value für die Sparkline
    raw: Optional[str] = None          # unveränderter actual_value
    passed: Optional[bool] = None
    state: str = "executed"
    run_id: str = ""


class ObservedCheck(BaseModel):
    name: str
    type: str = ""
    family: Optional[str] = None       # Garantie-Familie oder None (Bibliotheks-Check)
    severity: str = ""
    expect: str = ""
    last_value: Optional[str] = None
    passed: Optional[bool] = None
    state: str = ""
    points: list[ObservedPoint] = []


class ObservedGuarantee(BaseModel):
    family: str
    state: str = "unknown"             # pass | fail | unknown
    checks: list[ObservedCheck] = []


class ObservedOut(BaseModel):
    product: str
    dataset: str
    guarantees: list[ObservedGuarantee] = []


# ── Garantie-Backtesting (V1): „Wie oft hätte das historisch gefeuert?" ────────
# Simulation eines Expectation-Entwurfs gegen die persistierte Messwert-Historie
# (rein lesend, `dq_core.obs.backtest`). Zwei Eingabeformen: kompletter
# Contract-Entwurf (Workbench — der Compiler liefert die Check-Namen) oder
# explizite (check_name, expect)-Paare (Proposal-Badge).
class BacktestCheckIn(BaseModel):
    check_name: str
    expect: str


class BacktestIn(BaseModel):
    contract: Optional[dict] = None
    checks: Optional[list[BacktestCheckIn]] = None
    window_days: list[int] = [30, 90]


class BacktestWindowOut(BaseModel):
    days: int
    points: int
    breaches: int


class BacktestBreachOut(BaseModel):
    run_id: str = ""
    at: str = ""
    value: Optional[str] = None
    breach: bool = True


class BacktestCheckOut(BaseModel):
    check_name: str
    expect: str
    type: str = ""
    severity: str = ""
    points: int = 0
    evaluated: int = 0
    skipped: int = 0
    breaches: int = 0
    breach_rate: float = 0.0
    first_breach_at: Optional[str] = None
    last_breach_at: Optional[str] = None
    sample: list[BacktestBreachOut] = []
    windows: list[BacktestWindowOut] = []


class BacktestSummaryWindow(BaseModel):
    days: int
    breaches: int
    checks_firing: int


class BacktestOut(BaseModel):
    product: str
    dataset: str
    window_days: list[int]
    checks: list[BacktestCheckOut]
    checks_total: int
    checks_with_history: int
    summary_windows: list[BacktestSummaryWindow]
