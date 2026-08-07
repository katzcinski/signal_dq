from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SAFE_PRODUCT = re.compile(r"^[A-Za-z_]\w*$")


class ManifestValidationError(ValueError):
    """Structural validation error for a product manifest."""


@dataclass(frozen=True)
class OutputPort:
    dataset: str


@dataclass(frozen=True)
class InboundDep:
    product: str
    version: str


@dataclass(frozen=True)
class Product:
    product: str
    owners: list[str]
    output_ports: list[OutputPort] = field(default_factory=list)
    inbound: list[InboundDep] = field(default_factory=list)


def _require_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestValidationError(f"{label} must be a mapping")
    return value


def _required_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{label} must be a non-empty string")
    return value.strip()


def load_manifest(path: str | Path) -> Product:
    """Load one product manifest with structure-only validation.

    Referential checks are intentionally deferred to reconciliation so a single
    missing contract or lineage object does not make all products unqueryable.
    """
    manifest_path = Path(path)
    data = _require_mapping(
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {},
        label=str(manifest_path),
    )

    product_name = _required_string(data.get("product"), label="product")
    if not _SAFE_PRODUCT.match(product_name):
        raise ManifestValidationError(
            f"product {product_name!r} must match ^[A-Za-z_]\\w*$"
        )

    owners_raw = data.get("owners")
    if not isinstance(owners_raw, list) or not owners_raw:
        raise ManifestValidationError("owners must be a non-empty list")
    owners = [_required_string(owner, label="owners[]") for owner in owners_raw]

    ports_raw = data.get("output_ports", [])
    if not isinstance(ports_raw, list):
        raise ManifestValidationError("output_ports must be a list")
    output_ports: list[OutputPort] = []
    for idx, item in enumerate(ports_raw):
        port = _require_mapping(item, label=f"output_ports[{idx}]")
        output_ports.append(
            OutputPort(dataset=_required_string(port.get("dataset"), label=f"output_ports[{idx}].dataset"))
        )

    inbound_raw = data.get("inbound", [])
    if not isinstance(inbound_raw, list):
        raise ManifestValidationError("inbound must be a list")
    inbound: list[InboundDep] = []
    for idx, item in enumerate(inbound_raw):
        dep = _require_mapping(item, label=f"inbound[{idx}]")
        inbound.append(
            InboundDep(
                product=_required_string(dep.get("product"), label=f"inbound[{idx}].product"),
                version=_required_string(dep.get("version"), label=f"inbound[{idx}].version"),
            )
        )

    return Product(
        product=product_name,
        owners=owners,
        output_ports=output_ports,
        inbound=inbound,
    )


def load_all_manifests(products_dir: str | Path) -> list[Product]:
    """Load all valid product manifests below ``products_dir``.

    Malformed files are skipped with a warning by design; reconciliation
    findings handle referential gaps after the structurally valid set is known.
    """
    base = Path(products_dir)
    if not base.exists():
        return []

    manifests: list[Product] = []
    for path in sorted(base.glob("*.y*ml")):
        try:
            manifests.append(load_manifest(path))
        except Exception as exc:  # noqa: BLE001 - manifest errors must not break reads
            logger.warning("Skipping invalid product manifest %s: %s", path, exc)
    return manifests
