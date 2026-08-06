import time


CONTRACT = """\
product: DS_SALES_ORDERS
kind: internal_gate
dataset: DS_SALES_ORDERS
owned_by: platform
version: 0.1.0
guarantees:
  schema:
    columns: [ORDER_ID, CUSTOMER_ID]
    mode: closed
"""


def _write_contract(tmp_path):
    contract_path = tmp_path / "contracts" / "DS_SALES_ORDERS.yaml"
    contract_path.write_text(CONTRACT, encoding="utf-8")


def _wait_for_finished(api_client, op_id: str) -> dict:
    for _ in range(40):
        resp = api_client.get(f"/api/operations/{op_id}", headers={"X-DQ-Role": "steward"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] == "finished":
            return body
        if body["state"] == "error":
            raise AssertionError(body["error"])
        time.sleep(0.05)
    raise AssertionError("dry-run operation did not finish")


def test_dry_run_with_environment_returns_operation(api_client, tmp_path, monkeypatch):
    _write_contract(tmp_path)

    import dq_core.connect.db_connection as dbmod
    from dq_core.connect.db_connection import MockConnection
    import services.api.routers.checks as checks_mod

    monkeypatch.setattr(
        checks_mod,
        "get_environment",
        lambda name: {"host": "h", "port": 443, "user": "u", "password": "p", "schema": "CORE_DWH"},
    )

    def fake_get_connection(*, on_progress=None, **kwargs):
        if on_progress:
            on_progress("HANA-Verbindung hergestellt.")
        return MockConnection()

    monkeypatch.setattr(dbmod, "get_connection", fake_get_connection)

    started = api_client.post(
        "/api/checks/DS_SALES_ORDERS/dry-run",
        json={"environment": "prod"},
        headers={"X-DQ-Role": "steward"},
    )

    assert started.status_code == 202, started.text
    op = _wait_for_finished(api_client, started.json()["op_id"])
    assert op["kind"] == "dry_run"
    assert op["result"]["mode"] == "executed"
    assert op["result"]["dataset"] == "DS_SALES_ORDERS"
    assert op["result"]["total"] >= 1
    assert any("HANA-Verbindung" in row["line"] for row in op["progress"])


def test_dry_run_without_environment_stays_compile_only(api_client, tmp_path):
    _write_contract(tmp_path)

    resp = api_client.post(
        "/api/checks/DS_SALES_ORDERS/dry-run",
        json={},
        headers={"X-DQ-Role": "steward"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "compile_only"
