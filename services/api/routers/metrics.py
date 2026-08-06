"""Coverage-Metriken (R4-4) + Status-Badge (R4-5).

Coverage nach GX-Cloud-Vorbild: % Objekte mit aktivem Contract / mit Checks,
Objekte >30 Tage unvalidiert. Badge = dbt-Health-Tile-Analogon (SVG/JSON,
read-only) zur Einbettung in SAC/Confluence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..deps import StoreDep, get_inventory
from ..settings import get_settings

router = APIRouter(prefix="/api", tags=["metrics"])

_BADGE_COLORS = {
    "compliant": "#2da44e",
    "breached": "#d1242f",
    "unknown": "#6e7781",
}

# Cache the active-products scan: coverage_summary is hit on every dashboard
# load and re-parsing every contract YAML each time is wasteful at scale.
# Keyed by contracts dir; invalidated when the directory signature (file set +
# mtimes) changes, so a contract edit is picked up on the next request.
_active_products_cache: dict[str, tuple[tuple, set[str]]] = {}


def _dir_signature(contracts_dir: Path) -> tuple:
    parts = []
    for path in sorted(contracts_dir.glob("*.y*ml")):
        try:
            parts.append((path.name, path.stat().st_mtime_ns))
        except OSError:
            continue
    return tuple(parts)


def _active_products(contracts_dir: Path) -> set[str]:
    """Set of products with an active boundary contract, cached by dir signature."""
    if not contracts_dir.exists():
        return set()
    sig = _dir_signature(contracts_dir)
    cached = _active_products_cache.get(str(contracts_dir))
    if cached is not None and cached[0] == sig:
        return cached[1]
    active: set[str] = set()
    for path in contracts_dir.glob("*.y*ml"):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if data.get("lifecycle") == "active" and data.get("kind", "internal_gate") != "internal_gate":
            active.add(data.get("product") or path.stem)
    _active_products_cache[str(contracts_dir)] = (sig, active)
    return active


def _contract_kind(contracts_dir: Path, product: str) -> str | None:
    for ext in (".yaml", ".yml"):
        path = contracts_dir / f"{product}{ext}"
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return "internal_gate"
        return data.get("kind", "internal_gate")
    return None


@router.get("/metrics/health")
def service_health_metrics():
    """Self-observability: request counters, uptime, latency percentiles (JSON)."""
    from ..middleware import get_metrics
    return get_metrics()


@router.get("/coverage/health")
def health_trend(store: StoreDep = ...):
    """UX-N12: data-health trend for the cockpit gauge — share of datasets
    passing their latest run vs. one run earlier."""
    return store.get_health_trend()


@router.get("/coverage/heatmap")
def status_heatmap(
    days: int = Query(default=30, ge=7, le=90),
    store: StoreDep = ...,
):
    """UX-N10: object × day reliability heatmap (worst run status per day)."""
    return store.get_status_heatmap(days=days)


@router.get("/coverage/summary")
def coverage_summary(
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    settings = get_settings()
    object_ids = [
        o.get("id") or o.get("technicalName") or o.get("name") or ""
        for o in inventory
    ]
    object_ids = [o for o in object_ids if o]

    # Aktive Contracts je Produkt (Identitäts-Join: product == technicalName)
    contracts_dir = Path(settings.contracts_dir)
    active_products = _active_products(contracts_dir)
    internal_gate_products: set[str] = set()
    boundary_contract_products: set[str] = set()
    if contracts_dir.exists():
        for path in contracts_dir.glob("*.y*ml"):
            if path.name.endswith(".active.yml"):
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                internal_gate_products.add(path.stem)
                continue
            product = data.get("product") or path.stem
            if data.get("kind", "internal_gate") == "internal_gate":
                internal_gate_products.add(product)
            else:
                boundary_contract_products.add(product)

    checks_dir = Path(settings.checks_dir)
    with_checks = {
        obj_id for obj_id in object_ids
        if (checks_dir / obj_id / "checks.yml").exists()
        or (checks_dir / obj_id / "checks.yaml").exists()
        or (checks_dir / f"{obj_id}.yml").exists()
        or (checks_dir / f"{obj_id}.yaml").exists()
    }

    # Unvalidiert >30d: kein Lauf oder letzter Lauf älter als 30 Tage
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    last_runs = {s["dataset"]: s.get("last_run") for s in store.get_object_status()}
    unvalidated = sorted(
        obj_id for obj_id in object_ids
        if not last_runs.get(obj_id) or str(last_runs[obj_id]) < cutoff
    )

    total = len(object_ids)
    with_active = len([o for o in object_ids if o in active_products])
    contracts_breached = 0
    for product in boundary_contract_products:
        row = store.get_compliance(product)
        if row and row.get("compliance") == "breached":
            contracts_breached += 1
    return {
        "objects_total": total,
        "with_active_contract": with_active,
        "with_internal_gate": len([o for o in object_ids if o in internal_gate_products]),
        "with_contract_checks": len([o for o in object_ids if o in boundary_contract_products]),
        "contracts_breached": contracts_breached,
        "gates_failing": store.count_open_incidents(kind="internal_gate"),
        "with_checks": len(with_checks),
        "contract_coverage_pct": round(100.0 * with_active / total, 1) if total else 0.0,
        "unvalidated_30d": unvalidated,
    }


@router.get("/badge/{product}")
def status_badge(
    product: str,
    format: str = Query(default="svg"),
    store: StoreDep = ...,
):
    """Read-only Compliance-Badge. format=svg (default) | json."""
    import re
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", product):
        raise HTTPException(status_code=422, detail="Invalid product name")

    kind = _contract_kind(Path(get_settings().contracts_dir), product)
    compliance_row = None if kind == "internal_gate" else store.get_compliance(product)
    compliance = compliance_row["compliance"] if compliance_row else "unknown"
    version = compliance_row.get("contract_version", "") if compliance_row else ""

    if format == "json":
        return {"product": product, "compliance": compliance, "contract_version": version}

    color = _BADGE_COLORS.get(compliance, _BADGE_COLORS["unknown"])
    label = f"DQ {product}"
    value = compliance
    lw = 6 * len(label) + 12
    vw = 6 * len(value) + 12
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw + vw}" height="20" '
        f'role="img" aria-label="{label}: {value}">'
        f'<rect width="{lw}" height="20" fill="#24292f"/>'
        f'<rect x="{lw}" width="{vw}" height="20" fill="{color}"/>'
        f'<g fill="#fff" font-family="Verdana,sans-serif" font-size="10">'
        f'<text x="6" y="14">{label}</text>'
        f'<text x="{lw + 6}" y="14">{value}</text>'
        f'</g></svg>'
    )
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, max-age=60"},
    )
