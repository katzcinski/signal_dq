from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    sql: str = ""
    expect: str = ""
    severity: str = "fail"
    passed: bool = False
    actual_value: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    state: str = "executed"
    type: str = ""
    kind: str = "internal_gate"
    enforcement: str = "monitor"


class RunSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    dataset: str
    schema_name: str = ""
    started_at: str = ""
    finished_at: str = ""
    overall_status: str = "pass"
    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    triggered_by: str = "manual"
    contract_version: str = ""
    contract_hash: str = ""
    actor: str = ""
    run_state: str = "finished"
    gate_verdict: str = "proceed"
    results: list[CheckResultOut] = []


class RunListItem(BaseModel):
    run_id: str
    dataset: str
    started_at: str = ""
    finished_at: str = ""
    overall_status: str = "pass"
    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    run_state: str = "finished"
    triggered_by: str = "manual"
    gate_verdict: str = "proceed"


class RunStatusOut(BaseModel):
    """API-Task-kompatibler Lauf-Status (AP-1): Datasphere pollt diesen
    Endpoint (Location-Header) bis RUNNING → COMPLETED/FAILED."""

    status: str  # RUNNING | COMPLETED | FAILED
    run_id: str
    run_state: str = "finished"
    overall_status: str = "pass"
    gate_verdict: str = "proceed"
    fail_on: str = "block_and_quarantine"
