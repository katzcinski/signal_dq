# Konzept — Signal als Managed Service (Provisionierung, Multi-Tenant-Security, Persistenz)

**Stand:** 2026-06-25 · **Status:** Konzept / Entscheidungsgrundlage
**Kontext:** Wie wird Signal als **Managed Service** für **mehrere Kunden**
bereitgestellt — konkret Infrastruktur, Mandanten-Isolation/Security und
Datenpersistenz. Baut auf [`Uebergabemodelle_und_Lizenz.md`](Uebergabemodelle_und_Lizenz.md)
(Modell A1) und [`Tooldokumentation.md`](Tooldokumentation.md) §10 auf.

> **Kernaussage vorab:** Signal ist heute **Single-Tenant-pro-Instanz**. Es gibt
> **kein `tenant_id`** im Result-Store, eine OIDC-Konfiguration, eine
> `environments.yml`, einen Store pro Prozess. „Managed Service für mehrere
> Kunden" heißt deshalb **eine isolierte Signal-Instanz pro Kunde** auf einer
> gemeinsamen Plattform — **nicht** ein gepoolter Multi-Tenant-SaaS. Isolation =
> **Infrastruktur-Isolation**, nicht App-interne Query-Filterung. Letzteres
> existiert nicht und darf nicht angenommen werden.

---

## 1 — Betriebsmodell (A1: Managed Service mit Betriebs-Split)

Der Umschalter Lokal→Managed ist **reine Konfiguration**, kein Code-Zweig:

| Aspekt | Managed-Wert | Quelle |
|---|---|---|
| Store | `store_backend=hana` (`dq_results_lt`) | `settings.py:29` |
| Auth | `auth_mode=oidc` | `settings.py:19` |
| Bind | `bind_host=0.0.0.0` **nur mit** Auth (Gate **S5**, fail-closed) | `settings.py:14`, `main.py:assert_bind_policy` |
| Mock | `allow_mock_connection=false` (kein Fail-Open, S-13) | `settings.py:58` |
| Secrets | `password_ref: env:…` statt Klartext | `secrets.py` |

**Betriebs-Split:** *Wir* betreiben technisch (Hosting, Patches, Store, OIDC,
Secrets, Scheduler), *der Kunde* betreibt fachlich (Contracts authoren, auf
Incidents/Ampel reagieren) und meldet sich per OIDC im gehosteten Cockpit an
(Rollen `viewer | steward | owner | admin`). Es wird **keine betreibbare
Instanz überlassen** → bleibt Dienstleistung, nicht Softwareüberlassung.

---

## 2 — Infrastruktur-Topologie (Instanz-pro-Tenant)

```
                          ┌──────────────────────────────────────────────┐
                          │            INGRESS / REVERSE-PROXY            │
                          │   TLS-Terminierung · OIDC-Issuer-Routing      │
                          │   je Tenant eigener Host: kundeA.signal.…     │
                          └───────┬───────────────────────┬──────────────┘
                                  │                       │
              ── Tenant A ────────┼────────   ── Tenant B ┼────────────────
             ┌────────────────────▼─────────┐ ┌───────────▼─────────────────┐
             │  Namespace / Pod-Gruppe A     │ │  Namespace / Pod-Gruppe B   │
             │  ┌─────────────────────────┐  │ │  ┌───────────────────────┐  │
             │  │ Cockpit (Vite-Bundle)   │  │ │  │ Cockpit               │  │
             │  ├─────────────────────────┤  │ │  ├───────────────────────┤  │
             │  │ API+Engine (uvicorn ≥2) │  │ │  │ API+Engine (uvicorn≥2)│  │
             │  │  ─ OIDC-Audience A      │  │ │  │  ─ OIDC-Audience B    │  │
             │  │  ─ environments.yml A   │  │ │  │  ─ environments.yml B │  │
             │  │  ─ interner Poller A    │  │ │  │  ─ interner Poller B  │  │
             │  └───────────┬─────────────┘  │ │  └──────────┬────────────┘  │
             └──────────────┼────────────────┘ └─────────────┼───────────────┘
                            │                                │
          ┌─────────────────▼──────────┐      ┌──────────────▼──────────────┐
          │  PERSISTENZ TENANT A        │      │  PERSISTENZ TENANT B        │
          │  (getrennt, siehe §4)       │      │  (getrennt, siehe §4)       │
          └─────────────────────────────┘      └─────────────────────────────┘
                            │
                            │  Secrets je Tenant gescopt
                  ┌─────────▼──────────┐
                  │ Vault / BTP Cred.  │   (secrets.py ist vault-ready: Protocol)
                  └────────────────────┘
```

**Bausteine je Tenant:**

- **API/Engine** — `uvicorn services.api.main:app`, **≥2 Worker**. Doppellauf
  ist durch die Run-Registry im Store (`idx_dq_runs_one_running`, Migration 003)
  ausgeschlossen (multi-worker verifiziert, F2). Stateless → horizontal
  skalierbar.
- **Frontend** — gebautes Vite-Bundle statisch hinter dem Ingress.
- **Scheduler** — extern (Cron/Task-Chain→CLI) **oder** interner Poller
  (`SCHEDULER_ENABLED=true`, ADR-0005), pro Tenant getrennt.
- **Secrets** — heute env-basiert; `secrets.py` ist über ein `SecretResolver`-
  Protocol vault-ready (HashiCorp Vault / BTP Credential Store), pro Tenant
  gescopt.

---

## 3 — Security bei mehreren Kunden

**a) Mandanten-Isolation = Infrastruktur-Isolation.** Da Signal keine app-interne
Mandantentrennung kennt, wird Isolation über getrennte Container/Namespaces,
getrennte Stores, getrennte OIDC-Audiences und getrennte `environments.yml`
erreicht. **Kein gemeinsamer Prozess über Kundengrenzen.**

**b) Auth/RBAC.** OIDC pro Tenant; Claim→Rolle-Mapping pro Engagement
(`oidc_role_mapping`). Write-Routes über `require_roles(...)` geschützt;
non-loopback Bind nur mit Auth (S5, fail-closed beim Start).

**c) HANA-Zugriff — der eigentliche Streitpunkt.** Extern gehostetes Signal muss
die **produktive Kunden-HANA lesen**. Zwei Wege:
- *Erlaubt:* VPN / Private Link / IP-Allowlisted-Tunnel, lesend, PII-Gate (G8).
- *Standard-Fallback **Hybrid-Executor**:* der framework-freie Runner
  (`cli/dq_check_runner.py`) läuft **im Netz des Kunden** nahe der HANA, nur die
  **Ergebnisse** fließen ins gehostete Cockpit/Store. HANA-Zugriff bleibt in der
  Kundenzone — meist genau das, was die Security durchwinkt.

**d) Egress/SSRF.** Alarm-Webhooks (Slack/Teams) laufen durch
`webhook.fire_webhook`: https-only, Host-Allowlist, Private-IP-Block, keine
Redirects. Routing kann nie zum SSRF-Bypass werden.

**e) PII-Gate (G8).** Rohzeilen verlassen HANA nie ohne Opt-in
(`diagnostics_enabled` + Spalten-Allowlist + TTL). Default: nur Aggregat-Metriken.

---

## 4 — Persistenz: drei getrennte Orte, pro Tenant

Signal trennt bewusst **drei** Persistenzorte (HANDOVER §0). Im Managed-Betrieb
ist jeder **mandantengetrennt** zu führen.

```
   ┌──────────────────────────── TENANT A — PERSISTENZ ───────────────────────────┐
   │                                                                              │
   │  4.1 GIT (Source of Truth)        4.2 RESULT-STORE          4.3 KUNDEN-HANA  │
   │  ┌────────────────────────┐       ┌────────────────────┐   ┌──────────────┐ │
   │  │ Repo  kundeA/contracts │       │ dq_results_lt (HANA)│   │ Produktive   │ │
   │  │ ─ contracts/*.yaml     │       │  ODER signal.db     │   │ Datasphere / │ │
   │  │ ─ *.active.yml (Snap.) │       │ ─ Runs              │   │ HANA-Tabellen│ │
   │  │ ─ checks/*/checks.yml  │       │ ─ Check-Ergebnisse  │   │ + Views      │ │
   │  │                        │       │ ─ Baselines (MAD…)  │   │              │ │
   │  │ Eigentum: Kunde        │       │ ─ Incidents+Events  │   │ NUR LESEND   │ │
   │  │ (Git = Wahrheit)       │       │ ─ Diagnostics (TTL) │   │ (G8 PII-Gate)│ │
   │  └───────────┬────────────┘       └─────────┬──────────┘   └──────┬───────┘ │
   │              │ git_repo.py                   │ store/base.py        │        │
   │       schreibt Contracts            schreibt Läufe/Verdikte   liest Daten   │
   │       (Autor = Aufrufer)            (Pass/Fail + Metrik)      (hdbcli/Mock) │
   │                                                                              │
   │   Identitäts-Join (mapping-frei):                                           │
   │   lineage.node.id == inventory.technicalName == object_name == product       │
   └──────────────────────────────────────────────────────────────────────────────┘

   Datenfluss:   HANA (4.3) ──liest──▶ Engine ──schreibt Metrik+Verdikt──▶ Store (4.2)
                 Contract-Änderung ──Git-Writer──▶ Repo (4.1) ──CI/Compiler──▶ checks.yml
```

### 4.1 — Git (Source of Truth)
Contracts (`contracts/<product>.yaml`), zertifizierte Snapshots
(`<product>.active.yml`), kompilierte Checks (`checks/<product>/checks.yml`). Die
API schreibt Contract-Änderungen über den Git-Writer (`services/api/git_repo.py`)
mit dem Aufrufer als Autor zurück.
→ **Pro Tenant ein eigenes Repo** (getrennte Historie, Autorenschaft, ACL).

### 4.2 — Result-Store
Läufe, Check-Ergebnisse, Baselines, Incidents + Event-Timeline, Compliance,
Diagnostics. SQLite (heute lauffähig) oder HANA `dq_results_lt`.
→ **Physisch getrennt pro Tenant** (eigenes Schema/DB bzw. eigenes Volume).
→ **Datenresidenz-Frage:** Hostet die Beratung, liegt dieser Store bei ihr.
Verlangt die Governance des Kunden Verbleib im Kunden-Tenant, wandert der Store
(oder per Hybrid der ganze Runner) in die Kundenzone.
> *Honesty-Note:* `HanaStore` ist im Code aktuell ein **Stub** — der produktive
> HANA-Result-Store ist ein offener Implementierungspunkt. SQLite-pro-Tenant auf
> eigenem Volume ist der heute lauffähige Pfad.

### 4.3 — Kunden-HANA / Datasphere
Die geprüften Produktivdaten. **Ausschließlich lesend** (`hdbcli`, in lokal/Demo
`MockConnection`). Nie Eigentum oder Verantwortung des Managed-Betreibers.

**Backup/Retention** betrifft praktisch nur 4.2; Diagnostics haben ohnehin eine
TTL (`diagnostics_ttl_days`). 4.1 ist über Git ohnehin versioniert/spiegelbar.

---

## 5 — Was für *echten* gepoolten Multi-Tenant-SaaS fehlt

Falls das Ziel über „Instanz-pro-Tenant" hinausgeht (ein Prozess, viele
Mandanten), sind das die offenen Bauarbeiten — heute **nicht** vorhanden:

- `tenant_id` als durchgängige Achse im Store + jede Query mandanten-gescoped
  (Row-Level-Isolation).
- Mandanten-Auflösung aus dem OIDC-Token statt globaler Konfiguration.
- Pro-Tenant-Scoping von `environments.yml`, Secrets, Git-Remote,
  Notification-Routing.
- Produktiver `HanaStore` (heute Stub).
- Provisioning-Automation: Tenant anlegen = Schema + OIDC-Client + Git-Repo +
  Config in einem Schritt.

---

## 6 — Empfehlung

**Instanz-pro-Tenant (Modell A1)** ist der mit dem heutigen Code gangbare Weg:
starke Isolation über Infrastruktur, minimaler Umbauaufwand. Gepooltes
Multi-Tenant-SaaS ist ein **eigenes, größeres Projekt** (§5) und sollte als
solches bewusst entschieden werden — nicht implizit angenommen.

Steht der HANA-Zugriff von außen unter Security-Veto, ist der **Hybrid-Executor**
(§3c) die Standard-Antwort: Ausführung in der Kundenzone, nur Ergebnisse ins
gehostete Cockpit.

## 7 — Anker-Referenzen

| Baustein | Datei / Stelle |
|---|---|
| Modi-Umschalter | `services/api/settings.py` |
| Bind-Policy (S5) | `services/api/main.py` (`assert_bind_policy`) |
| Secret-Auflösung (vault-ready) | `services/api/secrets.py` |
| Git-Writer (4.1) | `services/api/git_repo.py` |
| Store-Abstraktion (4.2) | `packages/dq_core/store/base.py`, `sqlite_store.py`, `hana_store.py` (Stub) |
| Read-only HANA-Zugriff (4.3) | `packages/dq_core/connect/db_connection.py` |
| Hybrid-Executor | `cli/dq_check_runner.py` |
| Webhook-SSRF-Guards | `services/api/webhook.py` |
| Betriebsmodell / Lizenz | `docs/Uebergabemodelle_und_Lizenz.md` |
| Deployment-Profile | `docs/Tooldokumentation.md` §10 |
