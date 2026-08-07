from __future__ import annotations

import yaml

from dq_core.contract.gate_g3 import evaluate_contracts, main


def _contract(kind: str, version: str, keys: list[str]) -> dict:
    return {
        "product": "P1",
        "kind": kind,
        "dataset": "P1",
        "owned_by": "product",
        "version": version,
        "guarantees": {"keys": [{"columns": keys, "unique": True}]},
    }


def _write_contract(tmp_path, name: str, data: dict) -> str:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(path)


def test_breaking_contract_without_major_bump_blocks():
    base = _contract("consumer_contract", "1.0.0", ["ORDER_ID"])
    head = _contract("consumer_contract", "1.1.0", ["ORDER_ID", "ITEM_NO"])

    result = evaluate_contracts(base, head)

    assert result.breaking is True
    assert result.blocking is True


def test_same_breaking_change_on_internal_gate_passes():
    base = _contract("internal_gate", "1.0.0", ["ORDER_ID"])
    head = _contract("internal_gate", "1.1.0", ["ORDER_ID", "ITEM_NO"])

    result = evaluate_contracts(base, head)

    assert result.breaking is True
    assert result.blocking is False


def test_non_breaking_contract_change_passes():
    base = _contract("provider_contract", "1.0.0", ["ORDER_ID"])
    head = {
        **base,
        "version": "1.1.0",
        "guarantees": {
            **base["guarantees"],
            "volume": {"min_rows": 100, "severity": "warn"},
        },
    }

    result = evaluate_contracts(base, head)

    assert result.breaking is False
    assert result.blocking is False


def test_cli_exit_code_for_blocking_contract(tmp_path):
    base = _write_contract(tmp_path, "base.yaml", _contract("consumer_contract", "1.0.0", ["ORDER_ID"]))
    head = _write_contract(tmp_path, "head.yaml", _contract("consumer_contract", "1.1.0", ["CUSTOMER_ID"]))

    assert main([base, head]) == 1


def test_cli_exit_code_for_internal_gate(tmp_path):
    base = _write_contract(tmp_path, "base.yaml", _contract("internal_gate", "1.0.0", ["ORDER_ID"]))
    head = _write_contract(tmp_path, "head.yaml", _contract("internal_gate", "1.1.0", ["CUSTOMER_ID"]))

    assert main([base, head]) == 0
