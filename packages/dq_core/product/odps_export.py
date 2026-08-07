"""ODPS-1.0-Export (E3): Signal-Product-Manifest → Open Data Product Standard.

Produktseitiges Analog zum ODCS-Contract-Seam (`contract/odcs_export.py`): das
Product-Aggregat (`products/<name>.yaml`, geladen als `product.model.Product`)
wird als einseitiges Derivat nach ODPS 1.0 emittiert — dieselbe Regel wie bei
CSN/ORD/ODCS: **YAML = Source of Truth, ODPS = Schaufenster** für einen externen
Marktplatz (z. B. Entropy Data, das ODPS 1.0 nativ trägt).

Status (⚠ best guess, flagged): Das ODPS-1.0-Feldschema ist hier nach dem
öffentlich dokumentierten Stand nachgebildet; solange kein realer Marktplatz-
Endpunkt gegenverifiziert ist (offener Punkt E3), trägt jedes Dokument
`x-signal-validation: unverified`. Der Aufrufer/das Routing MUSS das respektieren
(kein Silent-Publish gegen einen unbestätigten Standard).

Framework-frei (G7), rein und deterministisch: Input ist der geladene `Product`
plus optionale Contract-Lookups; kein I/O, kein Web-Import.
"""
from __future__ import annotations

from typing import Any, Callable

from .model import Product

ODPS_VERSION = "1.0"

# Marker, der jedes Dokument als noch-nicht-gegen-echten-Marktplatz-validiert
# kennzeichnet. Wird entfernt/überschrieben, sobald E3 gegen eine reale ODPS-API
# geschlossen ist (dann trägt der Aufrufer `verified=True` herein).
UNVERIFIED_MARK = "unverified"


def to_odps(
    product: Product,
    *,
    contract_lookup: Callable[[str], dict[str, Any] | None] | None = None,
    verified: bool = False,
) -> dict[str, Any]:
    """Emit an ODPS-1.0 data product document from a Signal product manifest.

    `contract_lookup(dataset) -> contract dict | None` liefert für einen
    Output-Port das zugehörige Contract (für `outputPorts[].contractId`/`type`).
    Fehlt der Lookup oder das Contract, bleibt der Port dennoch deklariert
    (Deklaration ≠ Enforcement) — mit einer Notiz in `customProperties`.
    """
    lookup = contract_lookup or (lambda _dataset: None)

    output_ports: list[dict[str, Any]] = []
    for port in product.output_ports:
        entry: dict[str, Any] = {
            "name": port.dataset,
            "description": f"Output port for {port.dataset}",
            # ODPS-Port trägt einen Verweis auf das Schema/den Vertrag, garantiert
            # ihn aber nicht selbst (Port-Topologie vs. Garantie, ORD-Analogie).
            "type": "SQL",
        }
        contract = lookup(port.dataset)
        if contract:
            kind = contract.get("kind", "internal_gate")
            entry["contractId"] = f"sap.dq:{contract.get('product', port.dataset)}:odcs:v{contract.get('version', '1')}"
            entry["contractKind"] = kind
            # Nur Grenz-Contracts sind ein echtes veröffentlichtes Versprechen.
            entry["governed"] = kind in ("consumer_contract", "provider_contract")
        else:
            entry["governed"] = False
            entry.setdefault("customProperties", []).append(
                {"key": "signal:note", "value": "no governed contract bound to this output port"}
            )
        output_ports.append(entry)

    input_ports: list[dict[str, Any]] = [
        {
            "name": dep.product,
            "description": f"Inbound dependency on {dep.product} v{dep.version}",
            "sourceDataProductId": f"sap.dq:{dep.product}:dataProduct:v{dep.version}",
            "version": dep.version,
        }
        for dep in product.inbound
    ]

    doc: dict[str, Any] = {
        "apiVersion": ODPS_VERSION,
        "kind": "DataProduct",
        "id": f"sap.dq:{product.product}:dataProduct:v1",
        "name": product.product,
        "info": {
            "title": product.product,
            "owner": product.owners[0] if product.owners else "",
            "status": "active",
        },
        "outputPorts": output_ports,
    }
    if input_ports:
        doc["inputPorts"] = input_ports

    custom: list[dict[str, Any]] = [
        {"key": "signal:owners", "value": ",".join(product.owners)},
        {"key": "signal:sourceSpec", "value": "dq-cockpit/product-manifest-v1"},
    ]
    # E3: solange kein realer ODPS-Marktplatz gegenverifiziert ist, ehrlich
    # flaggen — das Routing (services/api/entropy.py) blockt Silent-Publish.
    doc["x-signal-validation"] = "verified" if verified else UNVERIFIED_MARK
    if not verified:
        custom.append({
            "key": "signal:validation",
            "value": "ODPS-1.0 shape is a documented best-guess; external marketplace endpoint not yet confirmed (E3).",
        })
    doc["customProperties"] = custom

    return doc
