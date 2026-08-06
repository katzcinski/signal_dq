import json
import time


def _configure_env(tmp_path, monkeypatch):
    env_file = tmp_path / "environments.yml"
    env_file.write_text(
        "\n".join([
            "prod:",
            "  host: hana.example.invalid",
            "  port: 443",
            "  user: SIGNAL_TEST",
            "  password: test-password",
            "  schema: CORE",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENVIRONMENTS_FILE", str(env_file))

    import services.api.settings as settings_mod

    settings_mod._settings = None


def _wait_for_finished(api_client, op_id: str, headers: dict | None = None) -> dict:
    for _ in range(40):
        resp = api_client.get(f"/api/operations/{op_id}", headers=headers or {})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] in {"finished", "error"}:
            return body
        time.sleep(0.05)
    raise AssertionError("operation did not finish")


def _sse_events(text: str) -> list[dict]:
    events = []
    for chunk in text.split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk[len("data: "):]))
    return events


def test_connection_test_endpoint_streams_and_polls_result(api_client, tmp_path, monkeypatch):
    _configure_env(tmp_path, monkeypatch)

    import dq_core.connect.db_connection as dbmod

    def fake_check_connection(*, on_progress=None, environment_name=None, **kwargs):
        if on_progress:
            on_progress(f'Verbinde mit Environment "{environment_name}" ...')
            on_progress('Schema "CORE" pruefen ...')
        return {
            "ok": True,
            "latency_ms": 12,
            "server_version": "4.00.000",
            "schema_visible": True,
            "failure_stage": None,
            "error": None,
        }

    monkeypatch.setattr(dbmod, "check_connection", fake_check_connection)

    started = api_client.post(
        "/api/environments/prod/test",
        headers={"X-DQ-Role": "steward"},
    )
    assert started.status_code == 202, started.text
    op_id = started.json()["op_id"]

    polled = _wait_for_finished(api_client, op_id, headers={"X-DQ-Role": "steward"})
    assert polled["kind"] == "connection_test"
    assert polled["state"] == "finished"
    assert polled["result"]["ok"] is True
    assert [row["line"] for row in polled["progress"]] == [
        'Verbinde mit Environment "prod" ...',
        'Schema "CORE" pruefen ...',
    ]

    with api_client.stream(
        "GET",
        f"/api/operations/{op_id}/events",
        headers={"X-DQ-Role": "steward"},
    ) as stream:
        assert stream.status_code == 200
        events = _sse_events("".join(stream.iter_text()))

    assert [event["type"] for event in events] == [
        "connected",
        "progress",
        "progress",
        "finished",
    ]
    assert events[-1]["result"]["ok"] is True


def test_connection_test_requires_steward(api_client, tmp_path, monkeypatch):
    _configure_env(tmp_path, monkeypatch)

    resp = api_client.post(
        "/api/environments/prod/test",
        headers={"X-DQ-Role": "viewer"},
    )

    assert resp.status_code == 403


def test_connection_test_unknown_environment(api_client):
    resp = api_client.post(
        "/api/environments/nope/test",
        headers={"X-DQ-Role": "steward"},
    )

    assert resp.status_code == 422


def test_operation_read_requires_admin_or_creator(api_client):
    from services.api.deps import get_store

    store = get_store()
    assert store.begin_operation("op-other", "connection_test", created_by="someone-else")
    store.finish_operation("op-other", "finished", result_json=json.dumps({"ok": True}))

    denied = api_client.get(
        "/api/operations/op-other",
        headers={"X-DQ-Role": "steward"},
    )
    assert denied.status_code == 403

    allowed = api_client.get("/api/operations/op-other")
    assert allowed.status_code == 200
    assert allowed.json()["result"]["ok"] is True
