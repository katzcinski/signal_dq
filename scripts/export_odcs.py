#!/usr/bin/env python3
"""ODCS-3.1-Export als wiederverwendbarer Entrypoint.

Eine Quelle der Wahrheit für `to_odcs()` (Bitol / ODCS v3.1) — genutzt von:
  * lokal:  `python scripts/export_odcs.py [PATHS...] --out-dir DIR`
  * CI:     Job `odcs-second-opinion` in `.github/workflows/ci.yml`
            (Zweitmeinung via `datacontract breaking`, statt eines inline-Heredocs).

Framework-frei (G7): importiert nur `dq_core`, kein FastAPI/Service-Code.

Regeln (deckungsgleich mit dem ODCS-API-Endpoint):
  * `internal_gate` (auch fehlendes `kind`) → übersprungen, nie exportiert (A1).
  * `*.active.yml`-Snapshots → übersprungen (keine autor-seitige Quelle).

Ohne PATHS werden alle `contracts/*.y{,a}ml` (außer `.active.yml`) exportiert.
Mit `--out-dir` wird je Contract `<stem>.odcs.<ext>` geschrieben, sonst nach stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

DEFAULT_CONTRACTS_DIR = ROOT / "contracts"


def _iter_default_contracts() -> list[Path]:
    base = DEFAULT_CONTRACTS_DIR
    if not base.exists():
        return []
    return sorted(p for p in base.glob("*.y*ml") if not p.name.endswith(".active.yml"))


def _skip_reason(path: Path, contract: dict[str, Any]) -> str | None:
    """Return a human-readable reason if this contract is not ODCS-exportable."""
    if path.name.endswith(".active.yml"):
        return "active snapshot (not an authored source)"
    if contract.get("kind", "internal_gate") == "internal_gate":
        return "internal_gate has no ODCS export"
    return None


def export_one(path: Path, out_dir: Path | None, fmt: str) -> tuple[bool, str]:
    """Export a single contract file. Returns (exported, message)."""
    import yaml

    from dq_core.contract.odcs_export import to_odcs

    contract = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    reason = _skip_reason(path, contract)
    if reason is not None:
        return False, f"SKIP  {path} — {reason}"

    odcs = to_odcs(contract)
    if fmt == "json":
        rendered = json.dumps(odcs, indent=2, sort_keys=False) + "\n"
    else:
        rendered = yaml.safe_dump(odcs, sort_keys=False, allow_unicode=True)

    if out_dir is None:
        sys.stdout.write(rendered)
        return True, f"OK    {path} → stdout"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}.odcs.{fmt}"
    out_path.write_text(rendered, encoding="utf-8")
    return True, f"OK    {path} → {out_path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Signal contracts to ODCS v3.1.")
    parser.add_argument("paths", nargs="*", type=Path,
                        help="Contract YAML files (default: all contracts/*.y{,a}ml).")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Write <stem>.odcs.<ext> here (default: print to stdout).")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml")
    args = parser.parse_args(argv)

    paths = args.paths or _iter_default_contracts()
    if not paths:
        print("No contracts to export.", file=sys.stderr)
        return 0

    exported = 0
    failed = 0
    for path in paths:
        if not path.exists():
            print(f"SKIP  {path} — file not found", file=sys.stderr)
            continue
        try:
            ok, message = export_one(path, args.out_dir, args.format)
        except Exception as exc:  # genuine export error — visible, but per-file
            failed += 1
            print(f"FAIL  {path} — {exc}", file=sys.stderr)
            continue
        exported += int(ok)
        print(message, file=sys.stderr)

    print(f"Exported {exported} contract(s); {failed} failed.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
