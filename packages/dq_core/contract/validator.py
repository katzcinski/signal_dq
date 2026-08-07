# [CONTRACT-SQL-FREE] — Gate G1: contracts carry guarantees, never SQL.
# Two layers: (1) structural jsonschema validation of the canonical contract
# schema v1, (2) lint pass — SQL smuggling patterns and identifier safety (S2)
# on EVERY identifier-bearing field, including list-valued guarantees.
from __future__ import annotations

import re
from typing import Any

import jsonschema

# Identifier safety (S2) — anything that becomes a SQL identifier or filename.
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ISO-8601 duration (the only accepted freshness notation; PT26H, P1D, PT30M …)
ISO_DURATION = re.compile(r"^P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

VALID_LIFECYCLES = {"draft", "active", "deprecated"}
VALID_OWNED_BY = {"platform", "product"}
VALID_SEVERITIES = {"critical", "fail", "warn"}
VALID_KINDS = {"internal_gate", "consumer_contract", "provider_contract"}
VALID_ENFORCEMENT = {"gate", "quarantine", "monitor"}

_IDENT = {"type": "string", "pattern": SAFE_IDENTIFIER.pattern}
_IDENT_LIST = {"type": "array", "items": _IDENT, "minItems": 1}
_SEVERITY = {"enum": sorted(VALID_SEVERITIES)}
_ENFORCEMENT = {"enum": sorted(VALID_ENFORCEMENT)}
_OBS_BASELINE = {"enum": ["rolling", "seasonal"]}
_OBS_SEASON = {"type": "array", "items": {"enum": ["dow", "eom", "hour"]}, "uniqueItems": True}
_OBS_SENSITIVITY = {"enum": ["low", "medium", "high"]}
_OBS_FAMILY = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "baseline": _OBS_BASELINE,
        "season": _OBS_SEASON,
        "sensitivity": _OBS_SENSITIVITY,
    },
}

# Canonical contract schema v1 (HANDOVER §1.5). additionalProperties: false is
# the structural half of G1 — an `sql:`/`query:` key anywhere is rejected.
CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["product", "dataset", "version", "guarantees"],
    "properties": {
        "product": _IDENT,
        "kind": {"enum": sorted(VALID_KINDS)},
        "dataset": _IDENT,
        "owned_by": {"enum": sorted(VALID_OWNED_BY)},
        "kind": {"enum": sorted(VALID_KINDS)},
        "owners": {"type": "array", "items": {"type": "string"}},
        "version": {"type": "string", "pattern": SEMVER.pattern},
        "lifecycle": {"enum": sorted(VALID_LIFECYCLES)},
        "enforcement_default": _ENFORCEMENT,
        # Quarantäne-Policy (Slices ④/⑤): style steuert die Materialisierung
        # (continuous=CLEAN-Tabelle, episodic=Zeilen-Parken, both=beides);
        # auto_release schließt Episoden nach N grünen Läufen (Default: aus).
        "quarantine": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "style": {"enum": ["continuous", "episodic", "both"]},
                "auto_release_after_green_runs": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
        "description": {"type": "string"},
        # Accepted but ignored by the compiler; written by proposal accepts.
        "quality_proposals": {"type": "array"},
        "observability": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "volume": _OBS_FAMILY,
                "freshness": _OBS_FAMILY,
            },
        },
        "guarantees": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["columns"],
                    "properties": {
                        "columns": _IDENT_LIST,
                        "mode": {"enum": ["closed", "open"]},
                        "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                        # Optionale, rein deklarative Typ-/Nullability-/Key-Spezifikation
                        # (Konzept §A.5). Trägt KEIN SQL — Schlüssel sind Spaltennamen
                        # (S2-Identifier), Werte sind Enum-/Boolean-Metadaten. Speist den
                        # Schema-Drift-Detektor (type_changed/nullable_relaxed/key_changed).
                        "types": {
                            "type": "object",
                            "propertyNames": {"pattern": SAFE_IDENTIFIER.pattern},
                            "additionalProperties": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "type": {
                                        "enum": [
                                            "string", "integer", "decimal",
                                            "boolean", "date", "time",
                                            "timestamp", "binary",
                                        ]
                                    },
                                    "nullable": {"type": "boolean"},
                                    "key": {"type": "boolean"},
                                },
                            },
                        },
                    },
                },
                "keys": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["columns"],
                        "properties": {
                            "columns": _IDENT_LIST,
                            "unique": {"type": "boolean"},
                            "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                            "proposed": {"type": "boolean"},
                        },
                    },
                },
                "referential": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["fk", "parent", "parent_key"],
                        "properties": {
                            "fk": _IDENT_LIST,
                            "parent": _IDENT,
                            "parent_key": _IDENT_LIST,
                            "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                        },
                    },
                },
                "freshness": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["column", "max_age"],
                    "properties": {
                        "column": _IDENT,
                        "max_age": {"type": "string", "pattern": ISO_DURATION.pattern},
                        "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                    },
                },
                "volume": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "min_rows": {"type": "integer", "minimum": 0},
                        "baseline": {"enum": ["rolling"]},
                        "bounds": {"enum": ["auto"]},
                        "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                    },
                },
                "completeness": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["column", "min_pct"],
                        "properties": {
                            "column": _IDENT,
                            "min_pct": {"type": "number", "minimum": 0, "maximum": 100},
                            "segment_by": _IDENT,
                            "max_segments": {"type": "integer", "minimum": 1, "maximum": 500},
                            "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                        },
                    },
                },
                "not_null": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["columns"],
                        "properties": {
                            "columns": _IDENT_LIST,
                            "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                        },
                    },
                },
            },
        },
        # checks[]: library-instantiated checks (internal gates, Iteration 1).
        # Structural shape only — semantic validation (id exists, params complete
        # and type-correct) lives in the compiler, which is library-aware.
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    # string for scalar params; array of strings for value_list.
                    "params": {
                        "type": "object",
                        "additionalProperties": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                        },
                    },
                    "expect": {"type": "string"},
                    "severity": _SEVERITY,
                        "enforcement": _ENFORCEMENT,
                },
            },
        },
    },
}

_VALIDATOR = jsonschema.Draft202012Validator(CONTRACT_SCHEMA)

# Lint patterns: SQL keywords/structure that must never appear in identifier or
# structural fields. Descriptions are exempt (the schema constrains where these
# patterns are scanned, so prose like "harmonised from RAW_SALES" stays legal).
_SQL_SMUGGLE = re.compile(
    r"(;|--|/\*|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\bUNION\b"
    r"|\bMERGE\b|\bEXEC\b|'|\")",
    re.IGNORECASE,
)

_FREE_TEXT_FIELDS = {"description", "rationale", "_note"}


def _lint_strings(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _SQL_SMUGGLE.search(value):
            errors.append(f"[G1] SQL-verdaechtiges Muster in '{path}': {value[:80]!r}")
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in _FREE_TEXT_FIELDS:
                continue
            _lint_strings(v, f"{path}.{k}", errors)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _lint_strings(v, f"{path}[{i}]", errors)


def validate_contract(data: dict[str, Any]) -> list[str]:
    """Return a list of validation error strings; empty = valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Contract muss ein YAML-Objekt sein."]

    # A2: schema binding happens at run time, never in the contract.
    if "schema" in data:
        errors.append(
            "[A2] 'schema' gehoert nicht in den Contract — Schema wird zur "
            "Laufzeit ueber das Environment gebunden."
        )
        data = {k: v for k, v in data.items() if k != "schema"}

    for err in sorted(_VALIDATOR.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = ".".join(str(p) for p in err.absolute_path) or "root"
        errors.append(f"[SCHEMA] {loc}: {err.message}")

    # Lint everything except free-text fields AND checks[].params — the latter
    # legitimately carry quotes/regex/value-lists; their injection safety is
    # enforced by the compiler's type-aware binding (S2), not by this prose
    # linter. checks[].id/expect/severity are still linted.
    lint_data = {k: v for k, v in data.items() if k not in _FREE_TEXT_FIELDS}
    checks_for_lint = lint_data.pop("checks", None)
    _lint_strings(lint_data, "root", errors)
    if isinstance(checks_for_lint, list):
        for i, chk in enumerate(checks_for_lint):
            if isinstance(chk, dict):
                _lint_strings(
                    {k: v for k, v in chk.items() if k != "params"},
                    f"root.checks[{i}]",
                    errors,
                )
    return errors
