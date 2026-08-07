"""Tier-2 extraction orchestration — REST catalog path, no live tenant.

The catalog client is monkeypatched to return a synthetic object + CSN; we
assert run_extraction writes Meridian-shaped inventory.json + lineage.json with
real columnEdges. No customer data, no network.
"""
import json
from types import SimpleNamespace

import services.api.datasphere_catalog as catalog_mod
from services.api.extraction import extraction_available, run_extraction


class _FakeCatalog:
    """Returns one synthetic view with a small CSN query."""

    def list_objects(self, space):
        return [{
            "technicalName": "v_OrderSummary",
            "objectType": "views",
            "status": "Deployed",
            "businessName": "Order Summary",
        }]

    def read_object_definition(self, space, name):
        return {
            "query": {
                "SELECT": {
                    "from": {"ref": ["Sales_Orders"], "as": "o"},
                    "columns": [
                        {"ref": ["o", "OrderID"], "as": "OrderID"},
                        {"func": "SUM", "args": [{"ref": ["o", "Amount"]}], "as": "TotalAmount"},
                    ],
                }
            }
        }


def _settings(tmp_path):
    return SimpleNamespace(
        datasphere_space_id="DEMO_SPACE",
        datasphere_use_cli=False,
        inventory_file=str(tmp_path / "inventory.json"),
        lineage_file=str(tmp_path / "lineage.json"),
    )


def test_run_extraction_writes_meridian_shaped_files(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_mod, "get_catalog_client", lambda: _FakeCatalog())
    settings = _settings(tmp_path)
    progress: list[str] = []

    assert extraction_available(settings) is True
    summary = run_extraction(settings, on_progress=progress.append)
    assert summary is not None
    assert summary["inventory_items"] == 1
    assert summary["column_edges"] >= 2
    assert summary["source"] == "datasphere-catalog"
    assert any(line == "Source   : datasphere-catalog" for line in progress)
    assert any(line == "[views] listing..." for line in progress)
    assert any(line.startswith("@@progress ") for line in progress)

    inv = json.loads((tmp_path / "inventory.json").read_text(encoding="utf-8"))
    assert inv["meta"]["schemaVersion"]
    assert inv["space"] == "DEMO_SPACE"
    obj = inv["objects"][0]
    assert obj["technicalName"] == "v_OrderSummary"
    assert obj["objectType"] == "views"
    assert obj["csnProjection"]["projectionLineage"], "CSN projection lineage must be populated"

    lin = json.loads((tmp_path / "lineage.json").read_text(encoding="utf-8"))
    assert lin["meta"]["schemaVersion"]
    assert any(n["id"] == "v_OrderSummary" for n in lin["nodes"])
    col_edges = {(e["source"], e["sourceColumn"], e["target"], e["targetColumn"]) for e in lin["columnEdges"]}
    assert ("Sales_Orders", "OrderID", "v_OrderSummary", "OrderID") in col_edges
    assert ("Sales_Orders", "Amount", "v_OrderSummary", "TotalAmount") in col_edges


def test_run_extraction_returns_none_without_connectivity(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_mod, "get_catalog_client", lambda: None)
    settings = _settings(tmp_path)
    assert extraction_available(settings) is False
    assert run_extraction(settings) is None
    assert not (tmp_path / "inventory.json").exists()


def test_run_extraction_none_without_space(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_mod, "get_catalog_client", lambda: _FakeCatalog())
    settings = _settings(tmp_path)
    settings.datasphere_space_id = ""
    assert run_extraction(settings) is None
