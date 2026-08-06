"""Entropy-Data-Publisher (Ergebnis- + Contract-Registrierung).

Signal positioniert sich als **SAP/HANA-Quality-Backend hinter einem
Data-Product-Marktplatz**: Entropy Data führt selbst keine Checks aus, sondern
*ingestiert publizierte Ergebnisse* (der `datacontract test --publish`-Pfad, der
für HANA strukturell kein Backend hat). Signal liefert das verifizierte Grün.

Architektur bewusst identisch zum geplanten OpenLineage-Emitter und zur
Enforcement-Materialisierung (`enforcement.py`):

  - **opt-in** — `ENTROPY_PUBLISH_ENABLED` (Kill-Switch, default aus) UND
    `ENTROPY_URL`. Ohne beides bleibt alles inert.
  - **fail-open** — ein Fehler hier darf einen Lauf nie beeinflussen; der
    Result-Store bleibt die Wahrheit, der Marktplatz ist Projektion.
  - **G7-neutral** — liegt in `services/`, importiert nichts aus dem eingefrorenen
    `dq_core`-Kern außer den reinen Mapping-Funktionen (`to_odcs`).
  - **SSRF-sicher (S6)** — jeder Ziel-Host wird gegen `ENTROPY_ALLOWLIST`
    geprüft und auf eine verifizierte öffentliche IP gepinnt; https-only.

⚠ **Validierungs-Vorbehalt (E2/E3):** Die exakte Form/Auth des Entropy-
Ingest-Endpunkts ist noch nicht gegen die reale API gegenverifiziert. Solange
`ENTROPY_MARKETPLACE_VERIFIED` false ist, läuft JEDER Publish als **Dry-Run**:
der Payload wird gebaut und zurückgegeben, aber **nicht** über das Netz gesendet.
So kann die Integration Ende-zu-Ende getestet werden, ohne gegen einen
unbestätigten Endpunkt zu schreiben.
"""
from __future__ import annotations

import http.client
import json
import logging
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlparse

from .webhook import _host_in_allowlist, _resolve_pinned_ip

logger = logging.getLogger("dq_cockpit.entropy")

# Payload-Schema-Version, die wir mitsenden — macht die Best-Guess-Annahme im
# Wire-Format explizit, statt sie stumm zu lassen.
_PAYLOAD_SPEC = "signal-entropy/0.1-unverified"


def publish_enabled(settings: Any) -> bool:
    """Publish ist scharf, wenn Kill-Switch AN und eine Ziel-URL gesetzt ist."""
    return bool(
        getattr(settings, "entropy_publish_enabled", False)
        and getattr(settings, "entropy_url", "")
    )


def marketplace_verified(settings: Any) -> bool:
    return bool(getattr(settings, "entropy_marketplace_verified", False))


def source_of_truth(settings: Any) -> str:
    return str(getattr(settings, "entropy_source_of_truth", "signal") or "signal")


def _post_json(url: str, payload: dict[str, Any], token: str, allowlist: list[str], timeout: int = 6) -> int:
    """SSRF-sicherer POST mit Bearer-Token. Gibt den HTTP-Status zurück.

    Wiederverwendet die Guards aus `webhook.py` (https-only, Allowlist,
    Private-IP-Block, IP-Pinning gegen DNS-Rebinding). Raises ValueError bei
    Policy-Verstoß; Netzfehler werden vom Aufrufer als fail-open behandelt.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https":
        raise ValueError(f"SSRF: Entropy URL scheme must be https, got {parsed.scheme!r}")
    if not _host_in_allowlist(hostname, allowlist):
        raise ValueError(f"SSRF: host {hostname!r} not in ENTROPY_ALLOWLIST")

    port = parsed.port or 443
    pinned_ip = _resolve_pinned_ip(hostname, port)  # raises on private/unresolvable

    body = json.dumps(payload).encode()
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "dq-cockpit/1",
        "X-Payload-Spec": _PAYLOAD_SPEC,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    context = ssl.create_default_context()
    raw = socket.create_connection((pinned_ip, port), timeout=timeout)
    try:
        tls_sock = context.wrap_socket(raw, server_hostname=hostname)
    except Exception:
        raw.close()
        raise
    conn = http.client.HTTPSConnection(hostname, port, timeout=timeout)
    conn.sock = tls_sock
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status
    finally:
        conn.close()


def _quality_payload(summary: Any, contract: dict[str, Any] | None) -> dict[str, Any]:
    """RunSummary/CheckResult → Entropy-Quality-Ingest-Payload (best guess).

    Nur Aggregat-Ergebnisse (Name, Status, Wert, Severity) — nie Rohzeilen
    (G8 unberührt). Die Struktur bildet den `datacontract test`-Ergebnis-Report
    nach, den der Marktplatz in seiner „Data Quality"-Sektion erwartet.
    """
    product = str(getattr(summary, "dataset", "") or "")
    version = str(getattr(summary, "contract_version", "") or "")
    kind = (contract or {}).get("kind", "internal_gate")
    checks = []
    for r in getattr(summary, "results", []) or []:
        checks.append({
            "name": getattr(r, "name", ""),
            "type": getattr(r, "type", ""),
            "passed": bool(getattr(r, "passed", False)),
            "severity": getattr(r, "severity", ""),
            "state": getattr(r, "state", "executed"),
            "value": (None if getattr(r, "actual_value", None) is None else str(r.actual_value)),
            "expectation": getattr(r, "expect_expr", "") or getattr(r, "expect", ""),
        })
    passed = sum(1 for c in checks if c["passed"])
    return {
        "spec": _PAYLOAD_SPEC,
        "dataProductId": f"sap.dq:{product}:dataProduct:v1",
        "contractId": f"sap.dq:{product}:odcs:v{version or '1'}",
        "contractKind": kind,
        "run": {
            "id": str(getattr(summary, "run_id", "") or ""),
            "startedAt": getattr(summary, "started_at", "") or "",
            "finishedAt": getattr(summary, "finished_at", "") or "",
            "status": getattr(summary, "overall_status", "") or "",
            "gateVerdict": getattr(summary, "gate_verdict", "") or "",
        },
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "checks": checks,
        "engine": {"vendor": "signal", "target": "sap-hana", "readOnly": True},
    }


def publish_run_result(summary: Any, contract: dict[str, Any] | None, settings: Any) -> dict[str, Any]:
    """Publiziere das Ergebnis eines abgeschlossenen Laufs nach Entropy.

    Liefert immer einen Status-Dict (`sent | dry_run | skipped | error`), damit
    der Aufrufer (Run-Hook oder manueller Endpunkt) das Ergebnis melden kann.
    Netzfehler werden als `error` zurückgegeben, ohne zu werfen (fail-open).
    """
    if not publish_enabled(settings):
        return {"status": "skipped", "reason": "entropy publish disabled"}
    # E1: im "entropy authort"-Modus authort der Marktplatz — wir schieben keine
    # Contract-Registrierung zurück, aber Ergebnisse (das verifizierte Grün)
    # bleiben sinnvoll. Ergebnis-Publish ist in beiden Modi erlaubt.
    payload = _quality_payload(summary, contract)
    return _dispatch(payload, path="quality/results", settings=settings)


def publish_contract_registration(contract: dict[str, Any], settings: Any) -> dict[str, Any]:
    """Registriere ein Contract als ODCS-Derivat im Marktplatz (Einweg-Export).

    Nur im Source-of-Truth-Modus "signal" (Signal authort → Entropy zeigt). Im
    "entropy"-Modus authort der Marktplatz — ein Push wäre die vermiedene
    bidirektionale Sync-Falle, daher `skipped`.
    """
    if not publish_enabled(settings):
        return {"status": "skipped", "reason": "entropy publish disabled"}
    if source_of_truth(settings) != "signal":
        return {
            "status": "skipped",
            "reason": "source_of_truth=entropy — marketplace authors the contract; no push-back (E1, no bidirectional sync).",
        }
    from dq_core.contract.odcs_export import to_odcs

    if contract.get("kind", "internal_gate") == "internal_gate":
        return {"status": "skipped", "reason": "internal gates are not published as contracts (ODCS export forbidden)."}

    odcs = to_odcs(contract)
    payload = {"spec": _PAYLOAD_SPEC, "kind": "contract-registration", "odcs": odcs}
    return _dispatch(payload, path="contracts", settings=settings)


def _dispatch(payload: dict[str, Any], *, path: str, settings: Any) -> dict[str, Any]:
    """Gemeinsamer Sende-/Dry-Run-Pfad. Dry-Run, solange der Marktplatz nicht
    gegenverifiziert ist (E2/E3) — Payload gebaut, aber nicht gesendet."""
    if not marketplace_verified(settings):
        logger.info("Entropy dry-run (%s): marketplace not verified, payload built but not sent.", path)
        return {
            "status": "dry_run",
            "reason": "ENTROPY_MARKETPLACE_VERIFIED is false — external endpoint not confirmed (E2/E3); payload built, not sent.",
            "endpoint": path,
            "payload": payload,
        }
    base = str(getattr(settings, "entropy_url", "") or "")
    target = urljoin(base if base.endswith("/") else base + "/", path)
    token = str(getattr(settings, "entropy_token", "") or "")
    allowlist = list(getattr(settings, "entropy_allowlist", []) or [])
    try:
        status = _post_json(target, payload, token, allowlist)
    except ValueError as exc:  # Policy-Verstoß (SSRF) — sichtbar, aber nicht werfend
        logger.warning("Entropy publish policy error: %s", exc)
        return {"status": "error", "reason": str(exc), "endpoint": path}
    except Exception as exc:  # noqa: BLE001 — Netzfehler: fail-open
        logger.warning("Entropy publish failed: %s", exc)
        return {"status": "error", "reason": "network error", "endpoint": path}
    ok = 200 <= status < 300
    logger.info("Entropy publish to %s → HTTP %s", path, status)
    return {"status": "sent" if ok else "error", "http_status": status, "endpoint": path}


def config_status(settings: Any) -> dict[str, Any]:
    """Nicht-sensibler Konfig-Status für die UI (nie das Token spiegeln, S-14)."""
    return {
        "enabled": bool(getattr(settings, "entropy_publish_enabled", False)),
        "url_set": bool(getattr(settings, "entropy_url", "")),
        "token_set": bool(getattr(settings, "entropy_token", "")),
        "allowlist_count": len(getattr(settings, "entropy_allowlist", []) or []),
        "source_of_truth": source_of_truth(settings),
        "marketplace_verified": marketplace_verified(settings),
        # Solange nicht verifiziert, läuft jeder Publish als Dry-Run — das ist der
        # ehrliche Zustand, den die UI anzeigen muss.
        "mode": "live" if (publish_enabled(settings) and marketplace_verified(settings))
                else ("dry_run" if publish_enabled(settings) else "off"),
    }
