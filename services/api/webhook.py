"""SSRF-safe outbound webhook caller for compliance breach notifications. [S6]"""
from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import ssl
from typing import Any


_PRIVATE_RANGES = [
    ipaddress.ip_network(r)
    for r in [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",  # link-local
        "::1/128",
        "fc00::/7",
    ]
]


def _is_private_host(hostname: str) -> bool:
    """Return True if hostname resolves to a private/loopback address."""
    try:
        results = socket.getaddrinfo(hostname, None)
        for *_, sockaddr in results:
            addr = ipaddress.ip_address(sockaddr[0])
            if any(addr in r for r in _PRIVATE_RANGES):
                return True
        return False
    except Exception:
        return True  # fail-safe: treat unresolvable as private


def _host_in_allowlist(hostname: str, allowlist: list[str]) -> bool:
    return any(re.fullmatch(pat, hostname or "") for pat in allowlist)


def _resolve_pinned_ip(hostname: str, port: int) -> str:
    """S-3: DNS genau einmal auflösen, ALLE Adressen gegen die Private-Ranges
    prüfen und eine validierte IP für die eigentliche Verbindung zurückgeben.

    So schließen wir das DNS-Rebinding-TOCTOU: ein Angreifer-DNS mit TTL 0 kann
    nicht mehr zwischen Prüfung und Connect von öffentlich auf privat umschwenken,
    weil wir auf genau die geprüfte IP verbinden (die TLS-Prüfung bleibt via SNI
    an den Hostnamen gebunden)."""
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:  # fail-safe: unauflösbar wie privat behandeln
        raise ValueError(f"SSRF: host {hostname!r} could not be resolved") from exc
    ips = [ai[4][0] for ai in infos]
    if not ips:
        raise ValueError(f"SSRF: host {hostname!r} could not be resolved")
    for ip in ips:
        if any(ipaddress.ip_address(ip) in r for r in _PRIVATE_RANGES):
            raise ValueError(f"SSRF: host {hostname!r} resolves to a private IP range")
    return ips[0]


def fire_webhook(
    url: str,
    payload: dict[str, Any],
    allowlist: list[str],
    timeout: int = 5,
) -> None:
    """Fire webhook with SSRF protection. Raises ValueError on policy violations.

    Safeguards (S6):
    - Host must match an entry in allowlist (regex patterns)
    - Host must not resolve to a private/loopback IP range
    - Connection is pinned to the validated IP (no DNS-rebinding TOCTOU, S-3)
    - Redirects are not followed (http.client returns 3xx without following)
    - Timeout enforced
    """
    if not url:
        return

    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if parsed.scheme != "https":
        raise ValueError(f"SSRF: webhook scheme must be https, got {parsed.scheme!r}")

    if not _host_in_allowlist(hostname, allowlist):
        raise ValueError(f"SSRF: host {hostname!r} not in WEBHOOK_ALLOWLIST")

    port = parsed.port or 443
    pinned_ip = _resolve_pinned_ip(hostname, port)  # raises on private/unresolvable

    body = json.dumps(payload).encode()
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    context = ssl.create_default_context()
    try:
        # Auf die geprüfte IP verbinden, TLS aber gegen den Hostnamen prüfen (SNI).
        raw = socket.create_connection((pinned_ip, port), timeout=timeout)
        try:
            tls_sock = context.wrap_socket(raw, server_hostname=hostname)
        except Exception:
            raw.close()
            raise
        conn = http.client.HTTPSConnection(hostname, port, timeout=timeout)
        conn.sock = tls_sock  # gepinnte Verbindung übernehmen, kein zweiter Lookup
        try:
            conn.request(
                "POST",
                path,
                body=body,
                headers={"Content-Type": "application/json", "User-Agent": "dq-cockpit/1"},
            )
            conn.getresponse()  # 3xx wird NICHT verfolgt (http.client-Default)
        finally:
            conn.close()
    except Exception:
        pass  # best-effort: webhook failure must not break the main flow
