"""A6: Engine-Dataclasses ↔ Pydantic-API-Schemas dürfen nicht driften.

Der Snapshot-Vergleich prüft, dass jedes Feld, das die Engine liefert, im
API-Schema ankommt (FE-relevante Felder) — die drei gelieferten Drift-Bugs
(Incidents id/expected, Proposals-Status, RunState) wären hieran gescheitert.
"""
import sys
from dataclasses import fields as dc_fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.engine.models import CheckResult, RunSummary
from services.api.schemas.run_schemas import CheckResultOut, RunSummaryOut


def test_check_result_fields_covered():
    engine_fields = {f.name for f in dc_fields(CheckResult)}
    api_fields = set(CheckResultOut.model_fields)
    # diagnostic_rows verlässt die Engine bewusst nicht über dieses Schema (PII-GATE)
    expected_in_api = engine_fields - {"diagnostic_rows"}
    missing = expected_in_api - api_fields
    assert not missing, f"CheckResultOut fehlt Engine-Felder: {missing}"


def test_run_summary_fields_covered():
    engine_fields = {f.name for f in dc_fields(RunSummary)}
    api_fields = set(RunSummaryOut.model_fields)
    # schema heißt API-seitig schema_name (SQL-Spaltenname)
    expected_in_api = (engine_fields - {"schema"}) | {"schema_name"}
    missing = expected_in_api - api_fields
    assert not missing, f"RunSummaryOut fehlt Engine-Felder: {missing}"


def test_run_state_vocabulary():
    """FE/BE-Vokabular: running|finished|error (nicht 'failed')."""
    src = Path(__file__).parents[2] / "packages/dq_core/engine/models.py"
    assert "running | finished | error" in src.read_text()
