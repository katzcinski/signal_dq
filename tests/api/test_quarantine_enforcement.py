"""End-to-End der Enforcement-Achse über die API: Run-Trigger mit
Quarantäne-Check (Mock-HANA) → Verdict + Episode, AP-1-Status-Endpoint
(RUNNING/COMPLETED/FAILED + fail_on), Quarantäne-Rollenmatrix und
Enforcement-Plan/Apply-Gating."""
from __future__ import annotations

import time


def _write_checks(client, name, enforcement="quarantine", expect="> 100"):
    """Failing-Check-Fixture ins CHECKS_DIR des Test-Settings legen.
    MockCursor liefert für Skalar-SQL immer 0 → expect '> 100' schlägt fehl."""
    from services.api.settings import get_settings
    from pathlib import Path
    checks = Path(get_settings().checks_dir) / f"{name}.yml"
    checks.write_text(
        f"""dataset: {name}
schema: "{{schema}}"
checks:
  - name: quality_check
    sql: SELECT COUNT(*) FROM DUMMY
    expect: "{expect}"
    severity: fail
    enforcement: {enforcement}
""",
        encoding="utf-8",
    )


def _run_to_completion(client, object_id, timeout_s=10.0):
    resp = client.post(f"/api/objects/{object_id}/run", json={})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    # AP-1: die 202-Antwort trägt den Location-Header auf den Status-Endpoint.
    assert resp.headers["location"] == f"/api/runs/{run_id}/status"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["run_state"] != "running":
            return run_id, run
        time.sleep(0.05)
    raise AssertionError("run did not finish in time")


class TestRunVerdictEndToEnd:
    def test_quarantine_check_produces_verdict_and_episode(self, api_client):
        _write_checks(api_client, "DS_SALES_ORDERS", enforcement="quarantine")
        run_id, run = _run_to_completion(api_client, "DS_SALES_ORDERS")
        assert run["gate_verdict"] == "quarantine"
        assert run["results"][0]["enforcement"] == "quarantine"

        episodes = api_client.get("/api/quarantine").json()
        assert len(episodes) == 1
        assert episodes[0]["product"] == "DS_SALES_ORDERS"
        assert episodes[0]["status"] == "open"
        assert episodes[0]["run_id"] == run_id
        assert episodes[0]["failed_checks"] == ["quality_check"]

    def test_monitor_fail_no_episode_proceed(self, api_client):
        _write_checks(api_client, "DS_SALES_ORDERS", enforcement="monitor")
        _, run = _run_to_completion(api_client, "DS_SALES_ORDERS")
        assert run["overall_status"] == "fail"
        assert run["gate_verdict"] == "proceed"
        assert api_client.get("/api/quarantine").json() == []


class TestRunStatusEndpoint:
    def test_status_mapping_fail_on(self, api_client):
        _write_checks(api_client, "DS_SALES_ORDERS", enforcement="quarantine")
        run_id, _ = _run_to_completion(api_client, "DS_SALES_ORDERS")
        # fail-closed Default: quarantine → FAILED
        status = api_client.get(f"/api/runs/{run_id}/status").json()
        assert status["status"] == "FAILED"
        assert status["gate_verdict"] == "quarantine"
        # CLEAN-View-Pipeline: fail_on=block → quarantine läuft weiter
        status = api_client.get(f"/api/runs/{run_id}/status", params={"fail_on": "block"}).json()
        assert status["status"] == "COMPLETED"

    def test_status_completed_on_green(self, api_client):
        _write_checks(api_client, "DS_SALES_ORDERS", enforcement="gate", expect=">= 0")
        run_id, _ = _run_to_completion(api_client, "DS_SALES_ORDERS")
        status = api_client.get(f"/api/runs/{run_id}/status").json()
        assert status["status"] == "COMPLETED"
        assert status["gate_verdict"] == "proceed"

    def test_status_failed_on_block(self, api_client):
        _write_checks(api_client, "DS_SALES_ORDERS", enforcement="gate")
        run_id, _ = _run_to_completion(api_client, "DS_SALES_ORDERS")
        status = api_client.get(f"/api/runs/{run_id}/status").json()
        assert status["status"] == "FAILED"
        assert status["gate_verdict"] == "block"

    def test_unknown_fail_on_rejected(self, api_client):
        assert api_client.get("/api/runs/x/status", params={"fail_on": "never"}).status_code == 422

    def test_unknown_run_404(self, api_client):
        assert api_client.get("/api/runs/nope/status").status_code == 404


class TestQuarantineApi:
    def _open_episode(self, api_client):
        import services.api.deps as deps_mod
        return deps_mod.get_store().open_quarantine("DS_SALES_ORDERS", "r1", ["c1"])

    def test_viewer_cannot_release(self, api_client):
        qid = self._open_episode(api_client)
        resp = api_client.post(
            f"/api/quarantine/{qid}/release", headers={"X-DQ-Role": "viewer"}, json={}
        )
        assert resp.status_code == 403

    def test_steward_release_and_confirm(self, api_client):
        qid = self._open_episode(api_client)
        resp = api_client.post(
            f"/api/quarantine/{qid}/release",
            headers={"X-DQ-Role": "steward"}, json={"note": "geprüft"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "released"
        resp = api_client.post(
            f"/api/quarantine/{qid}/confirm-reprocess",
            headers={"X-DQ-Role": "steward"}, json={},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "resolved" and body["resolve_reason"] == "reprocessed"

    def test_invalid_transition_conflicts(self, api_client):
        qid = self._open_episode(api_client)
        api_client.post(f"/api/quarantine/{qid}/confirm-reprocess", json={})
        resp = api_client.post(f"/api/quarantine/{qid}/release", json={})
        assert resp.status_code == 409

    def test_reconcile_reports_row_count(self, api_client):
        qid = self._open_episode(api_client)
        resp = api_client.post(f"/api/quarantine/{qid}/reconcile", json={"row_count": 42})
        assert resp.status_code == 200
        assert resp.json()["row_count"] == 42

    def test_unknown_episode_404(self, api_client):
        assert api_client.get("/api/quarantine/999").status_code == 404
        assert api_client.post("/api/quarantine/999/release", json={}).status_code == 404

    def test_status_filter_validation(self, api_client):
        assert api_client.get("/api/quarantine", params={"status": "weird"}).status_code == 422


class TestEnforcementApi:
    def test_plan_requires_steward(self, api_client):
        resp = api_client.get("/api/enforcement/plan", headers={"X-DQ-Role": "viewer"})
        assert resp.status_code == 403

    def test_plan_shows_slice3_objects(self, api_client):
        resp = api_client.get("/api/enforcement/plan")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False  # Kill-Switch default aus
        names = {o["name"] for o in body["objects"]}
        assert {"DQ_GATE_STATUS", "DQ_GATE_STATUS_HISTORY",
                "V_DQ_GATE_STATUS", "P_DQ_ASSERT_GATE"} <= names

    def test_apply_disabled_conflicts(self, api_client):
        resp = api_client.post("/api/enforcement/apply", json={"environment": "dev"})
        assert resp.status_code == 409

    def test_apply_requires_owner(self, api_client):
        resp = api_client.post(
            "/api/enforcement/apply", headers={"X-DQ-Role": "steward"},
            json={"environment": "dev"},
        )
        assert resp.status_code == 403


class TestVerdictPublication:
    def test_publish_verdict_gated_and_writes(self, api_client, monkeypatch):
        """Kill-Switch aus ⇒ kein Write; an + Schema ⇒ Bootstrap + Upsert
        über die (Fake-)Connection — Statements landen im eigenen Schema."""
        from services.api import enforcement as enf
        from services.api.settings import get_settings
        from dq_core.engine.models import RunSummary

        executed: list[str] = []

        class _Cursor:
            def execute(self, sql, params=None):
                executed.append(str(sql))

            def fetchall(self):
                return []

            def close(self):
                pass

        class _Conn:
            def cursor(self):
                return _Cursor()

        summary = RunSummary(
            run_id="r1", dataset="DS", schema="S",
            started_at="2026-07-10T00:00:00+00:00", finished_at="2026-07-10T00:01:00+00:00",
            overall_status="fail", total=1, passed=0, failed=1, warnings=0,
            gate_verdict="block",
        )
        settings = get_settings()
        assert enf.publish_verdict(_Conn(), summary, settings) is False
        assert executed == []

        monkeypatch.setattr(settings, "enforcement_materialize_enabled", True)
        monkeypatch.setattr(settings, "datasphere_signal_schema", "SIGNAL_SQL")
        enf.reset_bootstrap_cache()
        assert enf.publish_verdict(_Conn(), summary, settings) is True
        assert any('UPSERT "SIGNAL_SQL"."DQ_GATE_STATUS"' in s for s in executed)
        assert any('"SIGNAL_SQL"."DQ_GATE_STATUS_HISTORY"' in s for s in executed)
        assert any("P_DQ_ASSERT_GATE" in s for s in executed)  # Bootstrap lief mit
        enf.reset_bootstrap_cache()
