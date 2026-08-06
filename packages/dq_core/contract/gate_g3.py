"""Gate G3 CLI: breaking contract changes require a SemVer major bump.

Internal gates are ceremony-free: they may still have a breaking-shaped diff,
but this check exits successfully for them.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from .diff import DiffEntry, diff_contracts, is_breaking

CONTRACT_KINDS = {"consumer_contract", "provider_contract"}


@dataclass
class GateG3Result:
    kind: str
    from_version: str
    to_version: str
    breaking: bool
    blocking: bool
    entries: list[DiffEntry]


def semver_major(version: Any) -> int:
    try:
        return int(str(version or "0").split(".")[0] or "0")
    except (TypeError, ValueError, IndexError):
        return 0


def load_contract(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def evaluate_contracts(base: dict[str, Any], head: dict[str, Any]) -> GateG3Result:
    kind = str(head.get("kind", "internal_gate"))
    entries = diff_contracts(base, head)
    breaking = is_breaking(entries)
    blocking = (
        kind in CONTRACT_KINDS
        and breaking
        and semver_major(head.get("version")) <= semver_major(base.get("version"))
    )
    return GateG3Result(
        kind=kind,
        from_version=str(base.get("version", "")),
        to_version=str(head.get("version", "")),
        breaking=breaking,
        blocking=blocking,
        entries=entries,
    )


def evaluate_paths(base_path: str | Path, head_path: str | Path) -> GateG3Result:
    return evaluate_contracts(load_contract(base_path), load_contract(head_path))


def _print_result(result: GateG3Result, head_path: str | Path) -> None:
    name = Path(head_path).name
    version_span = f"{result.from_version} -> {result.to_version}"
    if result.blocking:
        print(f"G3 FAIL - {name}: breaking contract change without major bump ({version_span})")
        for entry in result.entries:
            if entry.breaking:
                print(f"  {entry.kind}: {entry.path} {entry.old_value!r} -> {entry.new_value!r}")
        return
    if result.kind not in CONTRACT_KINDS:
        print(f"G3 OK - {name}: {result.kind} is ceremony-free")
    elif result.breaking:
        print(f"G3 OK - {name}: breaking change has major bump ({version_span})")
    else:
        print(f"G3 OK - {name}: no breaking contract change")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="Base YAML contract path")
    parser.add_argument("head", help="Head YAML contract path")
    args = parser.parse_args(argv)

    result = evaluate_paths(args.base, args.head)
    _print_result(result, args.head)
    return 1 if result.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
