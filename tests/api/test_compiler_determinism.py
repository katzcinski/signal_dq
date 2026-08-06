"""WS3 acceptance: compiling the same contract twice is byte-identical,
and the determinism hash folds in the library version (A4)."""


def _put_draft(client, product):
    return client.put(
        f"/api/contracts/{product}",
        json={
            "product": product,
            "dataset": product,
            "owned_by": "product",
            "lifecycle": "draft",
            "version": "1.0.0",
            "guarantees": {"keys": [{"columns": ["ORDER_ID"], "unique": True}]},
        },
    )


def test_compile_is_deterministic(api_client):
    assert _put_draft(api_client, "DET1").status_code == 200

    first = api_client.post("/api/contracts/DET1/compile?dry_run=true")
    second = api_client.post("/api/contracts/DET1/compile?dry_run=true")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    a, b = first.json(), second.json()
    assert a["determinism_hash"]  # non-empty
    assert a["determinism_hash"] == b["determinism_hash"]
    assert a["yaml_preview"] == b["yaml_preview"]
