"""Single source of truth for the data-quality check catalog.

The catalog lives in ``check_library.json`` next to this module and is consumed
by both the Python engine (defaults, validation help) and the web UI (picker,
templates, inline help) via the ``/api/dq/check-library`` endpoint.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LIBRARY_PATH = Path(__file__).resolve().parent / "check_library.json"


@lru_cache(maxsize=1)
def load_library() -> dict[str, Any]:
    """Load and cache the raw check library document."""
    data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
        raise ValueError("check_library.json muss ein Objekt mit 'checks'-Liste sein.")
    return data


def checks() -> list[dict[str, Any]]:
    return list(load_library().get("checks", []))


def categories() -> list[str]:
    return list(load_library().get("categories", []))


def families() -> list[str]:
    """Functional families (observability | quality) — the obs/quality axis,
    orthogonal to ``categories`` (the SQL-domain axis)."""
    return list(load_library().get("families", []))


def check_ids_where(field: str, value: str) -> frozenset[str]:
    """Check ids whose ``field`` equals ``value`` — the single source of truth
    for functional classification consumed by the engine (gating) and the store
    (family rollup), so those mappings no longer drift in hardcoded sets."""
    return frozenset(c["id"] for c in checks() if c.get(field) == value)


def check_by_id(check_id: str) -> dict[str, Any] | None:
    for check in checks():
        if check.get("id") == check_id:
            return check
    return None
