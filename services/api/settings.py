from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    bind_host: str = Field(default="127.0.0.1")  # S5: default loopback
    bind_port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # Auth — S5: if noauth + non-loopback bind, fail-closed at startup
    auth_mode: Literal["noauth", "oidc"] = Field(default="noauth")
    oidc_issuer: str = Field(default="")
    oidc_audience: str = Field(default="")
    oidc_jwks_url: str = Field(default="")  # optional override; sonst Issuer-Discovery
    oidc_role_claim: str = Field(default="roles")
    oidc_groups_claim: str = Field(default="groups")
    # Claim-Wert → Cockpit-Rolle (viewer|steward|owner|admin), pro Engagement (O4)
    oidc_role_mapping: dict[str, str] = Field(default_factory=dict)

    # Store
    store_backend: Literal["sqlite", "hana"] = Field(default="sqlite")
    sqlite_db: str = Field(default="signal.db")

    # Git / Contracts
    git_remote: str = Field(default="")
    contracts_dir: str = Field(default="contracts")
    checks_dir: str = Field(default="checks")
    products_dir: str = Field(default="products")

    # Data
    data_dir: str = Field(default="data")
    inventory_file: str = Field(default="data/inventory.json")
    lineage_file: str = Field(default="data/lineage.json")

    # Environments
    environments_file: str = Field(default="environments.yml")
    secrets_file: str = Field(default="secrets.local.yml")

    # Diagnostics PII gate (S1)
    allow_local_diagnostics: bool = Field(default=False)
    diagnostics_ttl_days: int = Field(default=7)
    allow_profile_samples: bool = Field(default=False)
    profile_sample_columns: list[str] = Field(default=[])
    segment_value_columns: list[str] = Field(default=[])

    # F5: Staleness threshold for inventory/lineage extract (days)
    extract_stale_days: int = Field(default=7)

    # Lokalmodus: Runs ohne konfiguriertes Environment laufen gegen den Mock.
    # In Kunden-Deployments MUSS dies false sein — dann erfordert jeder Run ein
    # Environment mit echter HANA-Verbindung (kein stiller Fail-Open, S-13).
    allow_mock_connection: bool = Field(default=True)

    # Scheduler (Option E) — in-process poller for internal schedules. Opt-in:
    # off by default so the documented external-scheduler model is unchanged
    # unless an operator turns the poller on. Tick is the poll cadence in
    # seconds (how often due schedules are claimed), not the run interval.
    scheduler_enabled: bool = Field(default=False)
    scheduler_tick_seconds: int = Field(default=30, ge=5, le=3600)

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    # Webhook (WS5-3) — breach notification
    webhook_url: str = Field(default="")
    webhook_allowlist: list[str] = Field(default=[])  # host patterns (regex), e.g. [".*\\.example\\.com"]
    # Notification routing (R4-2): owner → channel(s). Optional YAML file; when
    # absent, webhook_url acts as an implicit default target. Every target URL is
    # still validated against webhook_allowlist (no SSRF bypass via routing).
    notifications_file: str = Field(default="notifications.yml")
    incident_cluster_window_minutes: int = Field(default=15, ge=1, le=1440)
    # Qualitäts-Digest (V4): periodischer Rollup an abonnierte Kanäle
    # (digest_enabled, Opt-in). Versand über den Scheduler-Tick, Claim-basiert.
    digest_enabled: bool = Field(default=False)
    digest_interval_hours: int = Field(default=24, ge=1, le=168)

    # Datasphere connector config file (runtime alternative to env vars, git-ignored)
    connector_file: str = Field(default="datasphere.yml")

    # Datasphere REST API — headless catalog / load status
    # base_url: e.g. https://mytenant.eu10.hcs.cloud.sap
    # token_url: defaults to {base_url}/oauth/token when empty
    datasphere_base_url: str = Field(default="")
    datasphere_client_id: str = Field(default="")
    datasphere_client_secret: str = Field(default="")
    datasphere_token_url: str = Field(default="")
    datasphere_space_id: str = Field(default="")
    # Datasphere CLI OAuth / host config. The legacy shared env names
    # DATASPHERE_AUTHORIZATION_URL and DATASPHERE_OAUTH_SECRETS_FILE are kept so
    # older local setups continue to work; the split UI now prefers the
    # DATASPHERE_CLI_* names.
    datasphere_cli_host: str = Field(default="", validation_alias="DSP_CLI_HOST")
    datasphere_cli_client_id: str = Field(default="")
    datasphere_cli_client_secret: str = Field(default="")
    datasphere_cli_authorization_url: str = Field(default="")
    datasphere_cli_token_url: str = Field(default="")
    datasphere_cli_oauth_secrets_file: str = Field(default="")
    datasphere_authorization_url: str = Field(default="")
    datasphere_oauth_secrets_file: str = Field(default="")
    # Tier-2 extraction: REST/OAuth catalog is the default source; set true to
    # also use the local @sap/datasphere-cli when available (richest CSN).
    datasphere_use_cli: bool = Field(default=False)

    # "Make available for monitoring" (Hybrid): Signal records the desired-state
    # set; an external, privileged script reconciles share + projection view in
    # this monitoring hub space and reports status back. Signal never writes to
    # Datasphere itself (stays read-only) — it only needs the hub space name.
    datasphere_monitoring_space: str = Field(default="")
    # S-2: dediziertes Service-Token für die maschinellen Monitoring-Endpunkte
    # (GET /manifest, PUT …/status), die das externe Reconcile-Skript aufruft.
    # Gesetzt ⇒ Header X-Service-Token wird erzwungen; leer ⇒ Fallback auf einen
    # steward+-Principal (nie anonym offen). EventSource/Skript nutzen das Token.
    monitoring_service_token: str = Field(default="")

    # Enforcement-Materialisierung (Slice ③, Konzept_Datasphere_Integration_*):
    # Signal publiziert Gate-Verdicts als SQL-Oberfläche (DQ_GATE_STATUS +
    # P_DQ_ASSERT_GATE) in SEIN Open-SQL-Schema — nie in Kundenschemata
    # (ADR-0002-Amendment). Kill-Switch default AUS; ohne gesetztes Schema
    # bleibt alles inert. Schema-Name wird zur Laufzeit gebunden (G2).
    enforcement_materialize_enabled: bool = Field(default=False)
    datasphere_signal_schema: str = Field(default="")
    # TTL des publizierten Verdicts in Sekunden (0 = kein Verfall). Abgelaufene
    # Verdicts behandelt P_DQ_ASSERT_GATE wie fehlende — fail-closed.
    enforcement_verdict_ttl_seconds: int = Field(default=0, ge=0)
    # Slices ④–⑦ (alle Default aus / leer — Aktivierung ist ein Betriebsentscheid):
    # Environment-Name für Enforcement-Arbeiten außerhalb des Lauf-Pfads
    # (Bridge-Poller, Episoden-Spiegel bei API-Übergängen, Reconciler-Apply).
    enforcement_environment: str = Field(default="")
    # SQL-Trigger-Bridge (Slice ⑥): Poller claimt DQ_RUN_REQUESTS. O6-Spike
    # (SQLSCRIPT_SYNC) gilt nur für P_DQ_GATE — der Poller ist unabhängig davon.
    enforcement_sql_bridge_enabled: bool = Field(default=False)
    # Retention der episodischen Quarantäne (Slice ⑤) — Pflicht-TTL in Tagen.
    quarantine_ttl_days: int = Field(default=30, ge=1)
    # Grace-Period des invalidate-then-drop (Reconciler, Slice ④).
    reconciler_drop_grace_days: int = Field(default=14, ge=0)
    # Outbound-Trigger (Slice ⑦): Signal darf bei quarantine-Verdict die
    # hinterlegte Remediation-Chain auslösen. Kein Daten-Schreiben, aber ein
    # Handeln auf dem Tenant → eigener Opt-in, jede Auslösung auditiert.
    datasphere_allow_trigger: bool = Field(default=False)
    # object_id → "SPACE/CHAIN_ID" (JSON-Objekt via Env setzbar).
    quarantine_trigger_chains: dict[str, str] = Field(default_factory=dict)

    # ── Entropy-Data-Integration (Contract-/Result-Marktplatz) ────────────────
    # Signal = das SAP/HANA-Quality-Backend hinter einem Data-Product-Marktplatz
    # (Entropy Data): es erzeugt das verifizierte Grün, das der Marktplatz nur
    # anzeigt. Architektur wie der geplante OpenLineage-Emitter: opt-in,
    # fail-open, außerhalb von dq_core (G7-neutral).
    #
    # Kill-Switch default AUS. Ohne gesetzte URL bleibt alles inert. Jeder
    # Ziel-Host wird — wie beim Breach-Webhook — gegen die Allowlist geprüft
    # (kein SSRF-Bypass, S6). Das Token wird nie in Responses gespiegelt (S-14).
    entropy_publish_enabled: bool = Field(default=False)
    entropy_url: str = Field(default="")            # Basis-URL der Entropy-Result-/Registry-API
    entropy_token: str = Field(default="")          # Bearer-Token (nie in Responses)
    entropy_allowlist: list[str] = Field(default=[])  # Host-Regex-Muster (SSRF-Gate, S6)
    # E1 — Source-of-Truth pro Kunde, NIE bidirektional:
    #   "signal"  → Signal authort, Entropy zeigt (Default; Einweg-Export).
    #   "entropy" → Entropy authort, Signal konsumiert ODCS & erzwingt (Import-Pfad).
    entropy_source_of_truth: Literal["signal", "entropy"] = Field(default="signal")
    # E2/E3 — Ehrliches Flag: ist ein externer Marktplatz wie Entropy als reale,
    # gegenverifizierte API bestätigt? Solange false, ist der Export ein
    # Best-Guess-Payload und läuft NUR als Dry-Run (kein Netz-Publish), damit wir
    # nicht gegen einen unbestätigten Endpunkt/Standard schreiben.
    entropy_marketplace_verified: bool = Field(default=False)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
