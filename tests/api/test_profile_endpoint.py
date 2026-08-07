"""POST /api/objects/{id}/profile — profiling over a (faked) HANA connection.

Reuses the profiler's synthetic FakeCursor; get_connection + get_environment are
monkeypatched so no live HANA is needed. Object DS_SALES_ORDERS comes from the
api_client fixture inventory.
"""
import time

from tests.unit.test_profile import (
    FakeCursor,
    _DEMO_AGG_ROW,
    _DEMO_COLUMNS,
    _DEMO_PROFILE_ROW,
)


def _wait_for_profile(api_client, op_id: str) -> dict:
    for _ in range(40):
        resp = api_client.get(f"/api/operations/{op_id}", headers={"X-DQ-Role": "steward"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] == "finished":
            assert any("Profiling" in row["line"] for row in body["progress"])
            return body["result"]
        if body["state"] == "error":
            raise AssertionError(body["error"])
        time.sleep(0.05)
    raise AssertionError("profile operation did not finish")


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _SampleCursor(FakeCursor):
    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        upper = text.upper()
        if upper.startswith('SELECT "ID", "AMOUNT" FROM ') and " LIMIT " in upper:
            self.description = [("ID",), ("AMOUNT",)]
            self._rows = [(1, 42.5), (2, 84.0)]
            self._scalar = None
            return
        super().execute(sql, params)


def _patch_live_hana(monkeypatch, cursor_factory=None):
    import dq_core.connect.db_connection as dbmod
    import services.api.routers.profile as profile_mod

    if cursor_factory is None:
        cursor_factory = lambda: FakeCursor(_DEMO_COLUMNS, _DEMO_AGG_ROW, _DEMO_PROFILE_ROW)

    monkeypatch.setattr(
        profile_mod, "get_environment",
        lambda name: {"host": "h", "port": 443, "user": "u", "password": "p", "schema": "CORE_DWH"},
    )
    monkeypatch.setattr(
        dbmod, "get_connection",
        lambda **kwargs: _FakeConn(cursor_factory()),
    )


def test_profile_returns_column_stats_and_pk_candidates(api_client, monkeypatch):
    _patch_live_hana(monkeypatch)
    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={"environment": "prod", "include_composite": True},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 202, resp.text
    data = _wait_for_profile(api_client, resp.json()["op_id"])
    assert data["row_count"] == 100
    assert data["column_count"] == 3
    by_col = {c["column"]: c for c in data["columns"]}
    assert by_col["ID"]["pk_candidate"] is True
    assert by_col["ID"]["uniqueness_pct"] == 100.0
    ranked = [c["column"] for c in data["pk_candidates"]["ranked_single"]]
    assert "ID" in ranked
    assert "AMOUNT" not in ranked  # decimal measure excluded from PK candidates


def test_profile_samples_disabled_by_default(api_client, monkeypatch):
    _patch_live_hana(monkeypatch)
    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={"environment": "prod", "include_samples": True},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 202, resp.text
    sample = _wait_for_profile(api_client, resp.json()["op_id"])["sample_rows"]
    assert sample["enabled"] is False
    assert sample["rows"] == []
    assert "disabled" in sample["reason"]


def test_profile_samples_require_allowlist(api_client, monkeypatch):
    import services.api.settings as settings_mod

    monkeypatch.setenv("ALLOW_PROFILE_SAMPLES", "true")
    settings_mod._settings = None
    _patch_live_hana(monkeypatch)

    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={"environment": "prod", "include_samples": True},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 202, resp.text
    sample = _wait_for_profile(api_client, resp.json()["op_id"])["sample_rows"]
    assert sample["enabled"] is False
    assert sample["rows"] == []
    assert "allowlisted" in sample["reason"]


def test_profile_samples_project_allowlisted_columns(api_client, monkeypatch):
    import services.api.settings as settings_mod

    monkeypatch.setenv("ALLOW_PROFILE_SAMPLES", "true")
    monkeypatch.setenv("PROFILE_SAMPLE_COLUMNS", '["ID","AMOUNT","SSN"]')
    settings_mod._settings = None
    _patch_live_hana(
        monkeypatch,
        cursor_factory=lambda: _SampleCursor(_DEMO_COLUMNS, _DEMO_AGG_ROW, _DEMO_PROFILE_ROW),
    )

    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={"environment": "prod", "include_samples": True, "sample_limit": 2},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 202, resp.text
    sample = _wait_for_profile(api_client, resp.json()["op_id"])["sample_rows"]
    assert sample["enabled"] is True
    assert sample["columns"] == ["ID", "AMOUNT"]
    assert sample["rows"] == [{"ID": 1, "AMOUNT": 42.5}, {"ID": 2, "AMOUNT": 84.0}]
    assert "SSN" not in sample["rows"][0]


def test_profile_forbidden_for_viewer(api_client, monkeypatch):
    _patch_live_hana(monkeypatch)
    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={"environment": "prod"},
        headers={"X-DQ-Role": "viewer"},
    )
    assert resp.status_code == 403


def test_profile_requires_environment(api_client):
    # No environment configured → fail-closed 422 (profiling needs real data).
    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/profile",
        json={},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 422


def test_profile_unknown_object_404(api_client, monkeypatch):
    _patch_live_hana(monkeypatch)
    resp = api_client.post(
        "/api/objects/NOPE/profile",
        json={"environment": "prod"},
        headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 404
