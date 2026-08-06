"""Admin connection-settings CRUD (routers/environments.py).

The environments file is a temp path per test; settings are reset so the lazy
get_settings() picks it up (same pattern as test_connection_test.py).
"""
import yaml


def _use_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / "environments.yml"
    monkeypatch.setenv("ENVIRONMENTS_FILE", str(env_file))
    import services.api.settings as settings_mod
    settings_mod._settings = None
    return env_file


ADMIN = {"X-DQ-Role": "admin"}


def test_create_list_and_secret_is_never_returned(api_client, tmp_path, monkeypatch):
    env_file = _use_env_file(tmp_path, monkeypatch)
    monkeypatch.setenv("HANA_PW_PROD", "super-secret")

    created = api_client.post(
        "/api/admin/environments",
        params={"name": "prod"},
        headers=ADMIN,
        json={
            "host": "hana.example.invalid", "port": 30015, "user": "SIGNAL_RO",
            "schema": "CORE", "password_ref": "env:HANA_PW_PROD",
            "encrypt": True, "validate_cert": False,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "prod"
    assert body["password_set"] is True
    assert body["validate_cert"] is False
    # The secret value must never leak through the API.
    assert "password" not in body
    assert "super-secret" not in created.text

    listed = api_client.get("/api/admin/environments", headers=ADMIN)
    assert listed.status_code == 200
    data = listed.json()
    assert data["can_edit"] is True
    assert [e["name"] for e in data["environments"]] == ["prod"]
    assert data["environments"][0]["password_ref"] == "env:HANA_PW_PROD"

    # On disk: the reference is stored, the plaintext value is not.
    on_disk = yaml.safe_load(env_file.read_text(encoding="utf-8"))
    assert on_disk["prod"]["password_ref"] == "env:HANA_PW_PROD"
    assert "password" not in on_disk["prod"]


def test_duplicate_name_conflicts(api_client, tmp_path, monkeypatch):
    _use_env_file(tmp_path, monkeypatch)
    payload = {"host": "h", "user": "u", "password_ref": "plain:x"}
    first = api_client.post("/api/admin/environments", params={"name": "dev"}, headers=ADMIN, json=payload)
    assert first.status_code == 201
    again = api_client.post("/api/admin/environments", params={"name": "dev"}, headers=ADMIN, json=payload)
    assert again.status_code == 409


def test_invalid_name_rejected(api_client, tmp_path, monkeypatch):
    _use_env_file(tmp_path, monkeypatch)
    resp = api_client.post(
        "/api/admin/environments", params={"name": "bad name/../x"}, headers=ADMIN,
        json={"host": "h", "user": "u"},
    )
    assert resp.status_code == 422


def test_update_keeps_existing_secret_when_ref_empty(api_client, tmp_path, monkeypatch):
    env_file = _use_env_file(tmp_path, monkeypatch)
    api_client.post(
        "/api/admin/environments", params={"name": "prod"}, headers=ADMIN,
        json={"host": "h", "user": "u", "password_ref": "plain:keepme"},
    )
    updated = api_client.put(
        "/api/admin/environments/prod", headers=ADMIN,
        json={"host": "newhost", "user": "u", "password_ref": ""},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["host"] == "newhost"
    assert updated.json()["password_set"] is True
    on_disk = yaml.safe_load(env_file.read_text(encoding="utf-8"))
    assert on_disk["prod"]["password_ref"] == "plain:keepme"


def test_delete(api_client, tmp_path, monkeypatch):
    _use_env_file(tmp_path, monkeypatch)
    api_client.post(
        "/api/admin/environments", params={"name": "prod"}, headers=ADMIN,
        json={"host": "h", "user": "u"},
    )
    deleted = api_client.delete("/api/admin/environments/prod", headers=ADMIN)
    assert deleted.status_code == 204
    listed = api_client.get("/api/admin/environments", headers=ADMIN)
    assert listed.json()["environments"] == []
    missing = api_client.delete("/api/admin/environments/prod", headers=ADMIN)
    assert missing.status_code == 404


def test_writes_require_admin(api_client, tmp_path, monkeypatch):
    _use_env_file(tmp_path, monkeypatch)
    for role in ("viewer", "steward", "owner"):
        resp = api_client.post(
            "/api/admin/environments", params={"name": "prod"},
            headers={"X-DQ-Role": role}, json={"host": "h", "user": "u"},
        )
        assert resp.status_code == 403, role
        listed = api_client.get("/api/admin/environments", headers={"X-DQ-Role": role})
        assert listed.status_code == 403, role
