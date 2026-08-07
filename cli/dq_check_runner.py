#!/usr/bin/env python3
"""CLI for running DQ checks. Imports dq_core (framework-free)."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages"))


def main():
    parser = argparse.ArgumentParser(description="DQ Check Runner")
    parser.add_argument("--schema", required=True, help="Schema name [SCHEMA-MAP] — bindet '{schema}'")
    parser.add_argument("--checks", required=True, help="Path to checks YAML file")
    parser.add_argument("--db", default="dq_results.db", help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist results")
    parser.add_argument("--mock", action="store_true", help="Run against MockConnection (no HANA)")
    parser.add_argument("--host", default="", help="HANA host")
    parser.add_argument("--port", type=int, default=443, help="HANA port")
    parser.add_argument("--user", default=os.environ.get("HANA_USER", ""))
    parser.add_argument("--password", default=os.environ.get("HANA_PASSWORD", ""))
    parser.add_argument("--execution-mode", choices=["auto", "batch", "isolated"], default="auto")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument(
        "--no-enforce", action="store_true",
        help="Beobachtungslauf: Exit-Code ist unabhängig vom Gate-Verdict immer 0.",
    )
    args = parser.parse_args()

    from dq_core.connect.db_connection import MockConnection, get_connection
    from dq_core.contract.compiler import bind_schema
    from dq_core.engine.check_engine import load_dataset_config, run_checks

    config = load_dataset_config(Path(args.checks))
    bind_schema(config, args.schema)  # [SCHEMA-MAP] Laufzeit-Bindung (G2)

    if args.mock:
        conn = MockConnection()
    else:
        if not args.host:
            print("FEHLER: --host fehlt (oder nutze --mock für einen Lauf ohne HANA).", file=sys.stderr)
            sys.exit(2)
        conn = get_connection(
            host=args.host, port=args.port,
            user=args.user, password=args.password, schema=args.schema,
        )

    try:
        summary = run_checks(
            config,
            conn,
            results_db=None if args.dry_run else Path(args.db),
            on_progress=lambda line: print(line),
            execution_mode=args.execution_mode,
            triggered_by="cli",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if args.output == "json":
        print(json.dumps({
            "run_id": summary.run_id,
            "overall_status": summary.overall_status,
            "gate_verdict": summary.gate_verdict,
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
        }, indent=2))
    else:
        print(f"\nRun: {summary.run_id}")
        print(f"Status: {summary.overall_status.upper()}")
        print(f"Verdict: {summary.gate_verdict.upper()}")
        print(f"Checks: {summary.passed}/{summary.total} passed")

    # Verdict → Exit-Code für externe Orchestratoren (Airflow/Cron/CI):
    # proceed=0, block=1, quarantine=3. Bewusst nicht 2 — belegt durch argparse
    # und fehlendes --host (oben). monitor-Fails eskalieren das Urteil nie.
    if args.no_enforce:
        sys.exit(0)
    sys.exit({"proceed": 0, "block": 1, "quarantine": 3}.get(summary.gate_verdict, 1))


if __name__ == "__main__":
    main()
