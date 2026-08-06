"""Unit tests for the Datasphere Catalog REST client.

All HTTP traffic is mocked with respx — NO live calls. Fixtures use purely
synthetic, made-up names (e.g. "Sales_Orders", "v_Demo"); no real
customer/tenant/person data appears anywhere.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from services.api.datasphere_catalog import (
    CatalogClient,
    CatalogError,
    _extract_definition,
    _extract_list,
    _odata_quote,
    get_catalog_client,
)

BASE = "https://demo-tenant.example.hcs.cloud.sap"
TOKEN_URL = f"{BASE}/oauth/token"
SPACE = "DEMO_SPACE"


def _make_client() -> CatalogClient:
    return CatalogClient(
        base_url=BASE + "/",  # trailing slash should be stripped
        client_id="demo-client",
        client_secret="demo-secret",
    )


def _token_route(expires_in: int = 3600) -> respx.Route:
    return respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok-abc", "expires_in": expires_in}
        )
    )


# ------------------------------------------------------------------
# Token handling
# ------------------------------------------------------------------

@respx.mock
def test_token_is_fetched_once_and_reused():
    token = _token_route()
    spaces = respx.get(f"{BASE}/api/v1/dwc/catalog/spaces").mock(
        return_value=httpx.Response(200, json={"value": []})
    )

    client = _make_client()
    client.list_spaces()
    client.list_spaces()

    # Two catalog calls, but the token endpoint is hit only once (cache reuse).
    assert token.call_count == 1
    assert spaces.call_count == 2
    # Bearer header derived from the cached token.
    assert spaces.calls[0].request.headers["Authorization"] == "Bearer tok-abc"


@respx.mock
def test_token_refreshes_after_expiry():
    # expires_in below the 60 s buffer -> already considered expired -> refetch.
    token = _token_route(expires_in=1)
    respx.get(f"{BASE}/api/v1/dwc/catalog/spaces").mock(
        return_value=httpx.Response(200, json={"value": []})
    )

    client = _make_client()
    client.list_spaces()
    client.list_spaces()

    assert token.call_count == 2


@respx.mock
def test_token_post_sends_client_credentials():
    _token_route()
    respx.get(f"{BASE}/api/v1/dwc/catalog/spaces").mock(
        return_value=httpx.Response(200, json={"value": []})
    )

    client = _make_client()
    client.list_spaces()

    body = respx.calls[0].request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=demo-client" in body
    assert "client_secret=demo-secret" in body


# ------------------------------------------------------------------
# list_spaces / list_objects normalization
# ------------------------------------------------------------------

@respx.mock
def test_list_spaces_normalizes_odata_value():
    _token_route()
    respx.get(f"{BASE}/api/v1/dwc/catalog/spaces").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"spaceId": "DEMO_SPACE", "status": "ACTIVE"},
                    {"spaceId": "DEMO_STAGING", "status": "ACTIVE"},
                ]
            },
        )
    )

    spaces = _make_client().list_spaces()
    assert [s["spaceId"] for s in spaces] == ["DEMO_SPACE", "DEMO_STAGING"]


@respx.mock
def test_list_objects_uses_odata_key_and_normalizes():
    _token_route()
    route = respx.get(
        f"{BASE}/api/v1/dwc/catalog/spaces('{SPACE}')/objects"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "technicalName": "Sales_Orders",
                        "objectType": "local-tables",
                        "businessName": "Sales Orders",
                        "status": "DEPLOYED",
                    },
                    {"technicalName": "v_Demo", "objectType": "views"},
                ]
            },
        )
    )

    objects = _make_client().list_objects(SPACE)

    assert route.called
    assert objects[0]["technicalName"] == "Sales_Orders"
    assert objects[1]["objectType"] == "views"


@respx.mock
def test_list_objects_handles_plain_list_response():
    _token_route()
    respx.get(f"{BASE}/api/v1/dwc/catalog/spaces('{SPACE}')/objects").mock(
        return_value=httpx.Response(200, json=[{"technicalName": "v_Demo"}])
    )

    objects = _make_client().list_objects(SPACE)
    assert objects == [{"technicalName": "v_Demo"}]


# ------------------------------------------------------------------
# read_object_definition
# ------------------------------------------------------------------

@respx.mock
def test_read_object_definition_returns_embedded_csn():
    _token_route()
    respx.get(
        f"{BASE}/api/v1/dwc/catalog/spaces('{SPACE}')/objects('v_Demo')"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "technicalName": "v_Demo",
                "definition": {"kind": "view", "query": "SELECT 1"},
            },
        )
    )

    definition = _make_client().read_object_definition(SPACE, "v_Demo")
    assert definition == {"kind": "view", "query": "SELECT 1"}


@respx.mock
def test_read_object_definition_returns_none_when_absent():
    _token_route()
    respx.get(
        f"{BASE}/api/v1/dwc/catalog/spaces('{SPACE}')/objects('v_Demo')"
    ).mock(
        return_value=httpx.Response(200, json={"technicalName": "v_Demo"})
    )

    assert _make_client().read_object_definition(SPACE, "v_Demo") is None


@respx.mock
def test_read_object_definition_returns_none_on_http_error():
    _token_route()
    respx.get(
        f"{BASE}/api/v1/dwc/catalog/spaces('{SPACE}')/objects('v_Demo')"
    ).mock(return_value=httpx.Response(404, text="not found"))

    # 4xx from the detail endpoint is treated as "not available via catalog".
    assert _make_client().read_object_definition(SPACE, "v_Demo") is None


# ------------------------------------------------------------------
# Error propagation for list endpoints
# ------------------------------------------------------------------

@respx.mock
def test_list_spaces_raises_on_server_error():
    _token_route()
    respx.get(f"{BASE}/api/v1/dwc/catalog/spaces").mock(
        return_value=httpx.Response(500, text="boom")
    )

    with pytest.raises(CatalogError):
        _make_client().list_spaces()


# ------------------------------------------------------------------
# Factory: graceful None when unconfigured
# ------------------------------------------------------------------

def test_get_catalog_client_returns_none_when_unconfigured(monkeypatch):
    import services.api.datasphere_catalog as mod
    from services.api import settings as settings_mod

    class _Cfg:
        datasphere_base_url = ""
        datasphere_client_id = ""
        datasphere_client_secret = ""
        datasphere_token_url = ""

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(mod, "_client", None)

    assert get_catalog_client() is None


def test_get_catalog_client_builds_and_caches_when_configured(monkeypatch):
    import services.api.datasphere_catalog as mod
    from services.api import settings as settings_mod

    class _Cfg:
        datasphere_base_url = BASE
        datasphere_client_id = "demo-client"
        datasphere_client_secret = "demo-secret"
        datasphere_token_url = ""

    monkeypatch.setattr(settings_mod, "get_settings", lambda: _Cfg())
    monkeypatch.setattr(mod, "_client", None)

    first = get_catalog_client()
    second = get_catalog_client()
    assert isinstance(first, CatalogClient)
    assert first is second  # cached singleton


# ------------------------------------------------------------------
# Pure helpers
# ------------------------------------------------------------------

def test_extract_list_variants():
    assert _extract_list([{"a": 1}]) == [{"a": 1}]
    assert _extract_list({"value": [{"a": 1}]}) == [{"a": 1}]
    assert _extract_list({"objects": [{"a": 1}]}) == [{"a": 1}]
    assert _extract_list({"nope": 1}) == []
    assert _extract_list("garbage") == []
    # Non-dict entries are filtered out.
    assert _extract_list([{"a": 1}, "x", 2]) == [{"a": 1}]


def test_extract_definition_variants():
    assert _extract_definition({"definition": {"k": 1}}) == {"k": 1}
    assert _extract_definition({"csn": {"k": 2}}) == {"k": 2}
    assert _extract_definition({"definition": {}}) is None
    assert _extract_definition({"other": 1}) is None
    assert _extract_definition("garbage") is None


def test_odata_quote_escapes_single_quotes():
    assert _odata_quote("v_Demo") == "'v_Demo'"
    assert _odata_quote("O'Brien") == "'O''Brien'"
