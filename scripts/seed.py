#!/usr/bin/env python3
"""Seed the local demo workspace with stable, UI-friendly demo data.

The seed covers:
- historical run data for both legacy DS_* samples and the current DEMO_* catalog
- profile snapshots so object diff/profiling screens have baseline data
- persistent incidents and proposal decisions for the activity feed
- data-product manifests plus governance contracts/compliance for product pages

The script is additive and mostly idempotent:
- runs use deterministic run_ids
- proposals are inserted with INSERT OR REPLACE
- incidents/profiles are only inserted when the demo set is not already present
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SQLITE_DB", "signal.db")
os.environ.setdefault("INVENTORY_FILE", "data/inventory.json")
os.environ.setdefault("LINEAGE_FILE", "data/lineage.json")
os.environ.setdefault("CONTRACTS_DIR", "contracts")
os.environ.setdefault("CHECKS_DIR", "checks")
os.environ.setdefault("PRODUCTS_DIR", "products")

from dq_core.engine.expectation import evaluate
from dq_core.engine.models import CheckResult, RunSummary
from dq_core.store.sqlite_store import ResultStore

DEMO_PROFILE_ENV = "seed-demo"

RUN_SCENARIOS: dict[str, dict[str, Any]] = {
    "DS_SALES_ORDERS": {
        "schema": "DS_SALES_ORDERS",
        "contract_version": "1.0.0",
        "kind": "consumer_contract",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 1000 AND 999999", "severity": "fail", "type": "row_count"},
            {"name": "null_ORDER_ID", "expect": "= 0", "severity": "critical", "type": "completeness"},
            {"name": "null_CUSTOMER_ID", "expect": "= 0", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_ORDER_ID", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
            {"name": "freshness_ORDER_DATE", "expect": "<= 26", "severity": "warn", "type": "freshness"},
        ],
        "actuals": {
            "row_count": (45000, 55000),
            "null_ORDER_ID": (0, 2),
            "null_CUSTOMER_ID": (0, 5),
            "duplicate_ORDER_ID": (0, 1),
            "freshness_ORDER_DATE": (1, 24),
        },
    },
    "DS_CUSTOMERS": {
        "schema": "DS_CUSTOMERS",
        "contract_version": "",
        "kind": "internal_gate",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 100 AND 999999", "severity": "fail", "type": "row_count"},
            {"name": "null_CUSTOMER_ID", "expect": "= 0", "severity": "critical", "type": "completeness"},
            {"name": "duplicate_CUSTOMER_ID", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (8000, 9200),
            "null_CUSTOMER_ID": (0, 0),
            "duplicate_CUSTOMER_ID": (0, 0),
        },
    },
    "DS_PRODUCTS": {
        "schema": "DS_PRODUCTS",
        "contract_version": "",
        "kind": "internal_gate",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 50 AND 99999", "severity": "fail", "type": "row_count"},
            {"name": "null_PRODUCT_ID", "expect": "= 0", "severity": "critical", "type": "completeness"},
            {"name": "duplicate_PRODUCT_ID", "expect": "= 0", "severity": "fail", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (1200, 1500),
            "null_PRODUCT_ID": (0, 0),
            "duplicate_PRODUCT_ID": (0, 1),
        },
    },
    "DS_REVENUE_SUMMARY": {
        "schema": "DS_REVENUE_SUMMARY",
        "contract_version": "1.2.0",
        "kind": "consumer_contract",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 12 AND 9999", "severity": "fail", "type": "row_count"},
            {"name": "null_YEAR_MONTH", "expect": "= 0", "severity": "critical", "type": "completeness"},
            {"name": "null_GROSS_REVENUE", "expect": "= 0", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_YEAR_MONTH_REGION", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (24, 36),
            "null_YEAR_MONTH": (0, 0),
            "null_GROSS_REVENUE": (0, 0),
            "duplicate_YEAR_MONTH_REGION": (0, 0),
        },
    },
    "DEMO_BUS_01": {
        "schema": "B",
        "contract_version": "2.1.0",
        "kind": "provider_contract",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 10000 AND 18000", "severity": "warn", "type": "row_count"},
            {"name": "freshness_BUS_COL_01", "expect": "<= 12", "severity": "warn", "type": "freshness"},
            {"name": "null_BUS_COL_03", "expect": "<= 15", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_BUS_COL_01", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (11800, 16200),
            "freshness_BUS_COL_01": (1, 10),
            "null_BUS_COL_03": (2, 18),
            "duplicate_BUS_COL_01": (0, 0.6),
        },
    },
    "DEMO_BUS_02": {
        "schema": "B",
        "contract_version": "1.4.0",
        "kind": "consumer_contract",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 8000 AND 15000", "severity": "warn", "type": "row_count"},
            {"name": "freshness_BUS_COL_01", "expect": "<= 8", "severity": "warn", "type": "freshness"},
            {"name": "null_BUS_COL_04", "expect": "<= 5", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_BUS_COL_01", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (9200, 14100),
            "freshness_BUS_COL_01": (2, 11),
            "null_BUS_COL_04": (0, 7),
            "duplicate_BUS_COL_01": (0, 1.1),
        },
    },
    "DEMO_BUS_06": {
        "schema": "B",
        "contract_version": "1.0.0",
        "kind": "consumer_contract",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 5000 AND 14000", "severity": "warn", "type": "row_count"},
            {"name": "freshness_BUS_COL_01", "expect": "<= 24", "severity": "warn", "type": "freshness"},
            {"name": "null_BUS_COL_06", "expect": "<= 3", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_BUS_COL_01", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (6400, 12400),
            "freshness_BUS_COL_01": (4, 28),
            "null_BUS_COL_06": (0, 4),
            "duplicate_BUS_COL_01": (0, 0.7),
        },
    },
    "DEMO_HARM_01": {
        "schema": "H",
        "contract_version": "",
        "kind": "internal_gate",
        "checks": [
            {"name": "row_count", "expect": "BETWEEN 4000 AND 20000", "severity": "warn", "type": "row_count"},
            {"name": "freshness_HARM_COL_01", "expect": "<= 6", "severity": "warn", "type": "freshness"},
            {"name": "null_HARM_COL_02", "expect": "<= 2", "severity": "fail", "type": "completeness"},
            {"name": "duplicate_HARM_COL_01", "expect": "= 0", "severity": "critical", "type": "uniqueness"},
        ],
        "actuals": {
            "row_count": (4800, 15400),
            "freshness_HARM_COL_01": (1, 9),
            "null_HARM_COL_02": (0, 4),
            "duplicate_HARM_COL_01": (0, 0.9),
        },
    },
}

DEMO_PRODUCT_MANIFESTS: dict[str, dict[str, Any]] = {
    "commercial_core.yaml": {
        "product": "commercial_core",
        "owners": ["team-commercial"],
        "output_ports": [{"dataset": "DEMO_BUS_01"}],
        "inbound": [],
    },
    "revenue_mart.yaml": {
        "product": "revenue_mart",
        "owners": ["team-finance"],
        "output_ports": [{"dataset": "DEMO_BUS_02"}],
        "inbound": [{"product": "commercial_core", "version": "2.0.0"}],
    },
    "operations_signal.yaml": {
        "product": "operations_signal",
        "owners": ["team-ops"],
        "output_ports": [{"dataset": "DEMO_BUS_06"}],
        "inbound": [{"product": "revenue_mart", "version": "1.3.0"}],
    },
}

DEMO_GOVERNANCE_CONTRACTS: dict[str, dict[str, Any]] = {
    "DEMO_BUS_01.yaml": {
        "product": "DEMO_BUS_01",
        "kind": "provider_contract",
        "dataset": "DEMO_BUS_01",
        "owned_by": "product",
        "owners": ["team-commercial"],
        "version": "2.1.0",
        "lifecycle": "active",
        "description": "Commercial core facts exposed as a stable provider port.",
        "guarantees": {
            "schema": {"columns": ["BUS_COL_01", "BUS_COL_02", "BUS_COL_03", "BUS_COL_04"], "mode": "closed"},
            "keys": [{"columns": ["BUS_COL_01"], "unique": True, "severity": "critical"}],
            "not_null": [{"columns": ["BUS_COL_01", "BUS_COL_02"], "severity": "fail"}],
            "volume": {"min_rows": 10000, "severity": "warn"},
            "freshness": {"column": "BUS_COL_01", "max_age": "PT12H", "severity": "warn"},
        },
    },
    "DEMO_BUS_02.yaml": {
        "product": "DEMO_BUS_02",
        "kind": "consumer_contract",
        "dataset": "DEMO_BUS_02",
        "owned_by": "product",
        "owners": ["team-finance"],
        "version": "1.4.0",
        "lifecycle": "active",
        "description": "Revenue mart consumed by finance and planning workflows.",
        "quality_proposals": [
            {
                "check_name": "freshness_BUS_COL_01",
                "proposed_expect": "<= 10",
                "rationale": "Weekend loads settle later than the original draft threshold.",
                "accepted_by": "Mia Steward",
            }
        ],
        "guarantees": {
            "schema": {"columns": ["BUS_COL_01", "BUS_COL_02", "BUS_COL_03", "BUS_COL_04"], "mode": "closed"},
            "keys": [{"columns": ["BUS_COL_01"], "unique": True, "severity": "critical"}],
            "not_null": [{"columns": ["BUS_COL_01", "BUS_COL_04"], "severity": "fail"}],
            "volume": {"min_rows": 8000, "severity": "warn"},
            "freshness": {"column": "BUS_COL_01", "max_age": "PT8H", "severity": "warn"},
        },
    },
    "DEMO_BUS_06.yaml": {
        "product": "DEMO_BUS_06",
        "kind": "consumer_contract",
        "dataset": "DEMO_BUS_06",
        "owned_by": "product",
        "owners": ["team-ops"],
        "version": "1.0.0",
        "lifecycle": "active",
        "description": "Operational signal pack for downstream monitoring consumers.",
        "guarantees": {
            "schema": {"columns": ["BUS_COL_01", "BUS_COL_02", "BUS_COL_03", "BUS_COL_04"], "mode": "closed"},
            "keys": [{"columns": ["BUS_COL_01"], "unique": True, "severity": "critical"}],
            "not_null": [{"columns": ["BUS_COL_01", "BUS_COL_06"], "severity": "fail"}],
            "volume": {"min_rows": 5000, "severity": "warn"},
            "freshness": {"column": "BUS_COL_01", "max_age": "PT24H", "severity": "warn"},
        },
    },
}

DEMO_COMPLIANCE = [
    {"product": "DEMO_BUS_01", "version": "2.1.0", "compliance": "compliant", "run_id": "seed-demo_bus_01-34"},
    {"product": "DEMO_BUS_02", "version": "1.4.0", "compliance": "breached", "run_id": "seed-demo_bus_02-34"},
    {"product": "DEMO_BUS_06", "version": "1.0.0", "compliance": "warning", "run_id": "seed-demo_bus_06-34"},
]

DEMO_PROPOSALS = [
    {
        "id": "seed-proposal-demo-bus-02-freshness",
        "product": "DEMO_BUS_02",
        "guarantee_patch": "<= 10",
        "evidence": {"metric": "freshness_BUS_COL_01", "reason": "Weekend ingest variance"},
        "status": "accepted",
        "created_at": "2026-06-28T09:15:00+00:00",
    },
    {
        "id": "seed-proposal-demo-bus-06-volume",
        "product": "DEMO_BUS_06",
        "guarantee_patch": "BETWEEN 4500 AND 15000",
        "evidence": {"metric": "row_count", "reason": "Recent portfolio expansion"},
        "status": "snoozed",
        "created_at": "2026-06-29T07:30:00+00:00",
    },
]


def _profile_column(
    row_count: int,
    *,
    column: str,
    data_type: str,
    distinct: int,
    null_pct: float = 0.0,
    empty_pct: float | None = None,
    pk_candidate: bool = False,
    minimum: Any = None,
    maximum: Any = None,
    avg: Any = None,
    median: Any = None,
) -> dict[str, Any]:
    nulls = int(round(row_count * (null_pct / 100.0)))
    empties = None if empty_pct is None else int(round(row_count * (empty_pct / 100.0)))
    uniqueness = round((distinct / row_count) * 100.0, 2) if row_count else 0.0
    return {
        "column": column,
        "data_type": data_type,
        "total": row_count,
        "nulls": nulls,
        "null_pct": round(null_pct, 2),
        "distinct": distinct,
        "uniqueness_pct": uniqueness,
        "pk_candidate": pk_candidate,
        "empty_count": empties,
        "empty_pct": None if empty_pct is None else round(empty_pct, 2),
        "min": minimum,
        "max": maximum,
        "avg": avg,
        "median": median,
    }


def _profile_result(
    object_id: str,
    schema: str,
    row_count: int,
    columns: list[dict[str, Any]],
    *,
    key_columns: list[str],
    score: int,
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ranked_single = []
    for idx, column in enumerate(key_columns):
        ranked_single.append(
            {
                "column": column,
                "exact": idx == 0,
                "distinct": row_count,
                "uniqueness_pct": 100.0,
                "rank_reason": "Stable demo seed candidate",
                "technical_score": 92 - idx,
                "business_score": 88 - idx,
                "final_score": 90 - idx,
                "reasons": ["nonnull", "unique", "business key naming"],
            }
        )
    numeric_stats = [
        {
            "column": col["column"],
            "min": col["min"],
            "max": col["max"],
            "avg": col["avg"],
            "median": col["median"],
        }
        for col in columns
        if col.get("avg") is not None
    ]
    empty_string_columns = [
        {
            "column": col["column"],
            "empty_count": col["empty_count"],
            "empty_pct": col["empty_pct"],
        }
        for col in columns
        if col.get("empty_count") not in (None, 0)
    ]
    return {
        "schema": schema,
        "table": object_id,
        "view": object_id,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "pk_candidates": {
            "single": key_columns,
            "composite": [key_columns] if len(key_columns) > 1 else [],
            "ranked_single": ranked_single,
            "ranked_composite": [],
            "search_meta": {
                "max_width": 3,
                "eligible_columns": len(columns),
                "eligible_column_names": [col["column"] for col in columns],
                "heuristic_combo_count": 0,
            },
        },
        "profiling": {
            "empty_string_columns": empty_string_columns,
            "numeric_stats": numeric_stats,
        },
        "issues": issues or [],
        "scores": {
            "overall_key_confidence": score,
            "uniqueness": 95,
            "completeness": 88,
            "business_fit": 86,
            "compound_viability": 72,
        },
        "heuristics": {"seeded": True},
    }


DEMO_PROFILE_SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "DEMO_BUS_01": [
        _profile_result(
            "DEMO_BUS_01",
            "B",
            12840,
            [
                _profile_column(12840, column="BUS_COL_01", data_type="cds.String", distinct=12840, pk_candidate=True, empty_pct=0.0),
                _profile_column(12840, column="BUS_COL_02", data_type="cds.String", distinct=214, null_pct=0.0, empty_pct=0.6),
                _profile_column(12840, column="BUS_COL_03", data_type="cds.Decimal", distinct=12110, null_pct=2.8, minimum=12.4, maximum=998.8, avg=431.2, median=429.4),
                _profile_column(12840, column="BUS_COL_04", data_type="cds.Decimal", distinct=11792, null_pct=0.7, minimum=0.0, maximum=126.5, avg=18.7, median=17.9),
            ],
            key_columns=["BUS_COL_01"],
            score=90,
        ),
        _profile_result(
            "DEMO_BUS_01",
            "B",
            13420,
            [
                _profile_column(13420, column="BUS_COL_01", data_type="cds.String", distinct=13420, pk_candidate=True, empty_pct=0.0),
                _profile_column(13420, column="BUS_COL_02", data_type="cds.String", distinct=228, null_pct=0.0, empty_pct=0.9),
                _profile_column(13420, column="BUS_COL_03", data_type="cds.Decimal", distinct=12540, null_pct=4.6, minimum=11.9, maximum=1012.4, avg=438.6, median=434.8),
                _profile_column(13420, column="BUS_COL_04", data_type="cds.Decimal", distinct=12201, null_pct=0.9, minimum=0.0, maximum=131.8, avg=19.4, median=18.2),
                _profile_column(13420, column="BUS_COL_05", data_type="cds.String", distinct=8, null_pct=0.0, empty_pct=1.2),
            ],
            key_columns=["BUS_COL_01"],
            score=89,
            issues=[{"column": "BUS_COL_03", "type": "null_spike", "detail": "Null rate increased after the latest business rollout."}],
        ),
    ],
    "DEMO_BUS_02": [
        _profile_result(
            "DEMO_BUS_02",
            "B",
            9820,
            [
                _profile_column(9820, column="BUS_COL_01", data_type="cds.Date", distinct=9820, pk_candidate=True),
                _profile_column(9820, column="BUS_COL_02", data_type="cds.String", distinct=460, null_pct=0.0, empty_pct=0.4),
                _profile_column(9820, column="BUS_COL_03", data_type="cds.String", distinct=470, null_pct=0.2, empty_pct=1.1),
                _profile_column(9820, column="BUS_COL_04", data_type="cds.String", distinct=9300, null_pct=1.6, empty_pct=0.0),
            ],
            key_columns=["BUS_COL_01"],
            score=92,
        ),
        _profile_result(
            "DEMO_BUS_02",
            "B",
            10360,
            [
                _profile_column(10360, column="BUS_COL_01", data_type="cds.Date", distinct=10360, pk_candidate=True),
                _profile_column(10360, column="BUS_COL_02", data_type="cds.String", distinct=462, null_pct=0.0, empty_pct=0.5),
                _profile_column(10360, column="BUS_COL_03", data_type="cds.String", distinct=472, null_pct=0.2, empty_pct=1.3),
                _profile_column(10360, column="BUS_COL_04", data_type="cds.String", distinct=9521, null_pct=3.9, empty_pct=0.0),
            ],
            key_columns=["BUS_COL_01"],
            score=88,
            issues=[{"column": "BUS_COL_04", "type": "completeness_regression", "detail": "Completeness slipped past the contract target."}],
        ),
    ],
}


def _summary_counts(results: list[CheckResult]) -> tuple[int, int, int, str]:
    """Roll up results into (passed, failed, warnings, overall_status) in one pass."""
    passed = failed = warnings = 0
    critical = False
    for result in results:
        if result.passed:
            passed += 1
        elif result.severity in {"critical", "fail"}:
            failed += 1
            if result.severity == "critical":
                critical = True
        elif result.severity == "warn":
            warnings += 1
    if critical:
        overall = "critical"
    elif failed:
        overall = "fail"
    elif warnings:
        overall = "warn"
    else:
        overall = "pass"
    return passed, failed, warnings, overall


def _seed_run_id(dataset: str, run_idx: int) -> str:
    return f"seed-{dataset.lower()}-{run_idx:02d}"


def _latest_seed_run_id(dataset: str) -> str:
    return _seed_run_id(dataset, 34)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def seed_run_history(store: ResultStore, *, base_now: datetime | None = None) -> tuple[int, dict[str, str]]:
    rng = random.Random(42)
    now = base_now or datetime.now(timezone.utc)
    count = 0
    latest_runs: dict[str, str] = {}
    for dataset, scenario in RUN_SCENARIOS.items():
        checks = scenario["checks"]
        actuals_range = scenario["actuals"]
        for run_idx in range(35):
            started = now - timedelta(days=34 - run_idx, hours=rng.randint(0, 23))
            finished = started + timedelta(seconds=rng.randint(5, 120))
            run_id = _seed_run_id(dataset, run_idx)
            results: list[CheckResult] = []
            for check in checks:
                lo, hi = actuals_range.get(check["name"], (0.0, 10.0))
                actual = round(rng.uniform(lo, hi), 2)
                passed = evaluate(actual, check["expect"])
                results.append(
                    CheckResult(
                        name=check["name"],
                        sql=f"-- mock: {check['name']}",
                        expect=check["expect"],
                        severity=check["severity"],
                        passed=passed,
                        actual_value=str(actual),
                        duration_ms=rng.randint(10, 500),
                        state="executed",
                        type=check.get("type", ""),
                        kind=scenario.get("kind", "internal_gate"),
                    )
                )
            passed, failed, warnings, overall = _summary_counts(results)
            summary = RunSummary(
                run_id=run_id,
                dataset=dataset,
                schema=scenario.get("schema", dataset),
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                overall_status=overall,
                total=len(results),
                passed=passed,
                failed=failed,
                warnings=warnings,
                results=results,
                triggered_by="seed",
                actor="seed_script",
                contract_version=scenario.get("contract_version", ""),
                run_state="finished",
            )
            store.save_run(summary)
            latest_runs[dataset] = run_id
            count += 1
    return count, latest_runs


def seed_demo_products(products_dir: Path, contracts_dir: Path) -> int:
    written = 0
    for name, manifest in DEMO_PRODUCT_MANIFESTS.items():
        _write_yaml(products_dir / name, manifest)
        written += 1
    for name, contract in DEMO_GOVERNANCE_CONTRACTS.items():
        _write_yaml(contracts_dir / name, contract)
        written += 1
    return written


def seed_demo_compliance(store: ResultStore) -> int:
    for record in DEMO_COMPLIANCE:
        store.set_compliance(record["product"], record["version"], record["compliance"], record["run_id"])
    return len(DEMO_COMPLIANCE)


def seed_profile_snapshots(store: ResultStore) -> int:
    inserted = 0
    with sqlite3.connect(store.db_path) as conn:
        for object_id, snapshots in DEMO_PROFILE_SCENARIOS.items():
            existing = conn.execute(
                "SELECT COUNT(*) FROM dq_profile_snapshots WHERE object_name=? AND environment=?",
                (object_id, DEMO_PROFILE_ENV),
            ).fetchone()[0]
            if existing:
                continue
            for snapshot in snapshots:
                store.save_profile_snapshot(object_id, snapshot, environment=DEMO_PROFILE_ENV)
                inserted += 1
    return inserted


def seed_proposal_decisions(store: ResultStore) -> int:
    with sqlite3.connect(store.db_path) as conn:
        for proposal in DEMO_PROPOSALS:
            conn.execute(
                """INSERT OR REPLACE INTO dq_proposals
                   (id, product, guarantee_patch, evidence, status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    proposal["id"],
                    proposal["product"],
                    proposal["guarantee_patch"],
                    json.dumps(proposal["evidence"]),
                    proposal["status"],
                    proposal["created_at"],
                ),
            )
        conn.commit()
    return len(DEMO_PROPOSALS)


def seed_incidents(store: ResultStore, latest_runs: dict[str, str]) -> int:
    titles = [
        "Demo incident: Revenue mart completeness drift",
        "Demo incident: Harmonization freshness breach",
        "Demo incident: Commercial core duplicate keys",
    ]
    with sqlite3.connect(store.db_path) as conn:
        existing = conn.execute(
            f"SELECT COUNT(*) FROM dq_incidents WHERE title IN ({','.join('?' for _ in titles)})",
            titles,
        ).fetchone()[0]
    if existing:
        return 0

    first = store.open_incident_record(
        "DEMO_BUS_02",
        latest_runs["DEMO_BUS_02"],
        "fail",
        "Demo incident: Revenue mart completeness drift",
        ["null_BUS_COL_04"],
        "1.4.0",
        kind="consumer_contract",
        actor="signal-bot",
        impacted_objects=[
            {
                "product": "DEMO_BUS_06",
                "distance": 1,
                "object_type": "views",
                "space": "B",
                "layer": "Business",
                "role": "consumption",
            }
        ],
    )
    second = store.open_incident_record(
        "DEMO_HARM_01",
        latest_runs["DEMO_HARM_01"],
        "critical",
        "Demo incident: Harmonization freshness breach",
        ["freshness_HARM_COL_01"],
        "",
        kind="internal_gate",
        actor="signal-bot",
        impacted_objects=[
            {
                "product": "DEMO_BUS_01",
                "distance": 1,
                "object_type": "views",
                "space": "B",
                "layer": "Business",
                "role": "consumption",
            },
            {
                "product": "DEMO_BUS_02",
                "distance": 2,
                "object_type": "views",
                "space": "B",
                "layer": "Business",
                "role": "consumption",
            },
        ],
    )
    third = store.open_incident_record(
        "DEMO_BUS_01",
        latest_runs["DEMO_BUS_01"],
        "critical",
        "Demo incident: Commercial core duplicate keys",
        ["duplicate_BUS_COL_01"],
        "2.1.0",
        kind="provider_contract",
        actor="signal-bot",
        impacted_objects=[
            {
                "product": "DEMO_BUS_02",
                "distance": 1,
                "object_type": "views",
                "space": "B",
                "layer": "Business",
                "role": "consumption",
            }
        ],
    )

    if first:
        store.transition_incident(first.incident_id, "acknowledged", actor="Mia Steward", owner="finance.oncall")
        store.transition_incident(first.incident_id, "resolved", actor="Mia Steward", note="Backfill completed after source replay.")
        store.save_incident_rca(
            first.incident_id,
            {
                "probable_cause_object": "DEMO_BUS_01",
                "cause_confidence": 0.71,
                "cause_candidates": [{"object": "DEMO_BUS_01", "score": 0.71}],
                "affected_contracts": [{"product": "DEMO_BUS_06", "version": "1.0.0"}],
                "affected_internal_gates": [],
                "recurrence_count": 1,
                "recurrence_last_at": "2026-06-21T08:30:00+00:00",
                "computed_at": "2026-06-29T08:02:00+00:00",
            },
        )
    if second:
        store.transition_incident(second.incident_id, "acknowledged", actor="Platform Ops", owner="platform.ops", note="Investigating delayed upstream refresh.")
        store.save_incident_rca(
            second.incident_id,
            {
                "probable_cause_object": "DEMO_HARM_01",
                "cause_confidence": 0.88,
                "cause_candidates": [{"object": "DEMO_HARM_01", "score": 0.88}],
                "affected_contracts": [{"product": "DEMO_BUS_01", "version": "2.1.0"}],
                "affected_internal_gates": [{"product": "DEMO_HARM_01"}],
                "recurrence_count": 2,
                "recurrence_last_at": "2026-06-28T06:45:00+00:00",
                "computed_at": "2026-06-29T08:04:00+00:00",
            },
        )
    if third:
        store.transition_incident(third.incident_id, "investigating", actor="Lucas Owner", owner="commercial.oncall", note="Duplicate source keys isolated to one upstream partition.")
        store.save_incident_rca(
            third.incident_id,
            {
                "probable_cause_object": "DEMO_BUS_01",
                "cause_confidence": 0.93,
                "cause_candidates": [{"object": "DEMO_BUS_01", "score": 0.93}],
                "affected_contracts": [{"product": "DEMO_BUS_02", "version": "1.4.0"}],
                "affected_internal_gates": [],
                "recurrence_count": 3,
                "recurrence_last_at": "2026-06-25T04:15:00+00:00",
                "computed_at": "2026-06-29T08:06:00+00:00",
            },
        )
    return 3


def seed_workspace(
    *,
    db_path: str | Path,
    products_dir: str | Path,
    contracts_dir: str | Path,
    base_now: datetime | None = None,
) -> dict[str, int]:
    store = ResultStore(str(db_path))
    run_count, latest_runs = seed_run_history(store, base_now=base_now)
    product_files = seed_demo_products(Path(products_dir), Path(contracts_dir))
    compliance_rows = seed_demo_compliance(store)
    profile_rows = seed_profile_snapshots(store)
    incident_rows = seed_incidents(store, latest_runs)
    proposal_rows = seed_proposal_decisions(store)
    return {
        "runs": run_count,
        "product_files": product_files,
        "compliance_rows": compliance_rows,
        "profile_rows": profile_rows,
        "incident_rows": incident_rows,
        "proposal_rows": proposal_rows,
    }


def main() -> None:
    summary = seed_workspace(
        db_path=os.environ["SQLITE_DB"],
        products_dir=os.environ["PRODUCTS_DIR"],
        contracts_dir=os.environ["CONTRACTS_DIR"],
    )
    print(f"Seeded {summary['runs']} runs.")
    print(f"Seeded {summary['profile_rows']} profile snapshots.")
    print(f"Seeded {summary['incident_rows']} incidents and {summary['proposal_rows']} proposal decisions.")
    print(f"Wrote {summary['product_files']} demo product/contract files and refreshed {summary['compliance_rows']} compliance rows.")
    print(f"Database: {os.environ['SQLITE_DB']}")


if __name__ == "__main__":
    main()
