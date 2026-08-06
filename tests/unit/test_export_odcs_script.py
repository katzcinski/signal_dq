"""scripts/export_odcs.py — wiederverwendbarer ODCS-Export-Entrypoint.

Deckt die Datei-/Skip-Logik ab (die `to_odcs()`-Korrektheit prüft
test_odcs_export.py gegen das Bitol-Schema).
"""
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "packages"))

_spec = importlib.util.spec_from_file_location("export_odcs", ROOT / "scripts" / "export_odcs.py")
export_odcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_odcs)


def _write(path: Path, contract: dict) -> None:
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")


_GOV = {
    "product": "DS_X",
    "kind": "consumer_contract",
    "dataset": "DS_X",
    "version": "1.0.0",
    "lifecycle": "active",
    "guarantees": {"schema": {"columns": ["A", "B"], "mode": "closed"}},
}


def test_exports_governance_contract_to_out_dir(tmp_path):
    src = tmp_path / "DS_X.yaml"
    _write(src, _GOV)
    out = tmp_path / "out"

    rc = export_odcs.main([str(src), "--out-dir", str(out)])

    assert rc == 0
    written = out / "DS_X.odcs.yaml"
    assert written.exists()
    odcs = yaml.safe_load(written.read_text())
    assert odcs["kind"] == "DataContract"
    assert odcs["id"] == "DS_X"


def test_skips_internal_gate(tmp_path):
    src = tmp_path / "GATE.yaml"
    _write(src, {"product": "GATE", "kind": "internal_gate", "guarantees": {}})
    out = tmp_path / "out"

    ok, message = export_odcs.export_one(src, out, "yaml")

    assert ok is False
    assert "internal_gate" in message
    assert not (out / "GATE.odcs.yaml").exists()


def test_skips_active_snapshot(tmp_path):
    src = tmp_path / "DS_X.active.yml"
    _write(src, _GOV)

    ok, message = export_odcs.export_one(src, tmp_path / "out", "yaml")

    assert ok is False
    assert "active snapshot" in message


def test_json_format(tmp_path):
    src = tmp_path / "DS_X.yaml"
    _write(src, _GOV)
    out = tmp_path / "out"

    export_odcs.main([str(src), "--out-dir", str(out), "--format", "json"])

    written = out / "DS_X.odcs.json"
    assert written.exists()
    assert written.read_text().lstrip().startswith("{")
