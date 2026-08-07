# Handover — Observability-Quellen, Quarantäne-MVP & Task-Chain-Orchestrierung

**Status:** teilweise überholt (2026-07-23): Der Quarantäne-/Gating-Teil ist über [`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md) Slices ①–③ **implementiert** (Enforcement-Achse, `/api/quarantine`, Verdict-Materialisierung, API-Task-Vertrag `GET /api/runs/{id}/status`). Offen bleiben die Observability-Quellen-Pakete (Task-Log-Freshness) und Slices ④–⑦.
**Bereich:** Engine (`dq_core`), API (`services/api`), CLI, Datasphere-Integration
**Branch des Reviews:** `claude/ess-observability-quarantine-wcgnh6`
**Stand:** 2026-07-09

> **Grundlage:** [`REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md`](REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md)
> — dort stehen Ist-Stand-Analyse, Begründungen und Quellen. Dieses Handover
> übersetzt die Empfehlungen in umsetzbare Arbeitspakete mit Dateipfaden,
> vorhandenen Bausteinen und Acceptance-Kriterien.
> Verwandt: `Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md` (inkl.
> Update-Hinweis §3) · `ADR-0005_Scheduling.md` · `OPEN_TASKS.md` (E/F/J/N/O2).

---

## Kontext in drei Sätzen

Signal misst Freshness/Volume heute über SQL-Scans + adaptive Baselines +
REST-Run-Historie; Quarantäne existiert nur als Konzept (kein
`enforcement_mode` im Code); Scheduling ist geliefert (Poller + `external`).
**Zentrale neue Erkenntnis des Reviews:** SAP Datasphere Task Chains können
seit 2025 über **API-Tasks** ausgehende HTTP-Calls machen (POST/PUT, synchron
≤ 60 s oder asynchron mit Status-Polling über den `Location`-Header) — die
bisherige Prämisse „Chain kann Signal nicht rufen" ist überholt. Damit wird
das Promotion-Gate (Quarantäne-MVP B2) **nativ in Datasphere** abbildbar.

## Wichtigste Korrekturen gegenüber älteren Docs

| Doc | Überholte Aussage | Korrektur |
|---|---|---|
| `Konzept_Enforcement_Modi_*` §3 | „Task-Chain kann keinen HTTP-Call machen" | API-Tasks existieren; Update-Hinweis ist eingepflegt |
| `OPEN_TASKS.md` E1 | „Verdikt-Pfad nutzt `compute_bounds` (mean±σ)" | Code nutzt `compute_robust_bounds` (Median/MAD, Migration 010) — E1 ist faktisch ✅ |

---

## Arbeitspakete (priorisiert)

### AP-1 — API-Task-Vertrag: async Run-Endpoint `[M]` — **zuerst**

Task Chain ruft Signal nativ: `[Load → Staging] → [API-Task: Signal-Lauf] →
[Promote nur bei COMPLETED]`.

**Vorhanden (wiederverwenden):**

| Baustein | Ort | Zweck |
|---|---|---|
| `POST /api/objects/{id}/run` | `services/api/routers/objects.py:422` (`trigger_run`) | startet Hintergrund-Lauf, liefert `run_id` |
| `start_object_run(...)` | `routers/objects.py:470` | geteilter Ausführungspfad (HTTP + Poller), F2-Doppellauf-Schutz |
| `GET /api/runs/{run_id}` | `services/api/routers/runs.py` | Lauf-Status/-Ergebnis |
| Auth/Rollen | `services/api/auth/provider.py`, `require_roles` | technischer Principal für den Chain-Aufruf (steward+) |

**Zu bauen:**
1. Status-Endpoint mit API-Task-kompatibler Semantik, z. B.
   `GET /api/runs/{run_id}/status`: solange der Lauf läuft „RUNNING"-Antwort,
   danach COMPLETED/FAILED gemäß Verdict-Mapping (`proceed`→COMPLETED,
   `block`/vorerst auch `quarantine`→FAILED). **Exakte Status-Code-Erwartung
   des API-Tasks am Tenant verifizieren** (Feature jung, Details
   versionsabhängig) — erst Spike, dann Contract festzurren.
2. Run-Start-Variante mit `202 Accepted` + `Location`-Header auf den
   Status-Endpoint (asynchroner Modus; der 60-s-Sync-Modus ist für DQ-Läufe
   ungeeignet).
3. Doku: HTTP-Connection-Einrichtung in Datasphere (Host/Credentials),
   Hinweis auf S5 (`noauth` bindet nur loopback — Chain-Aufruf braucht echte
   Auth) in `Tooldokumentation.md` §Deployment.

**Acceptance:** Eine Task Chain mit API-Task (async) startet einen Signal-Lauf,
wartet auf das Ergebnis und promotet nur bei grünem Verdict; `tests/api/`
decken 202+Location und die Status-Übergänge ab.

### AP-2 — CLI-Verdict-Exit-Code `[S]`

Für Nicht-DSP-Orchestratoren (Airflow/Cron/CI) und Lite. Heute:
`cli/dq_check_runner.py:73` wirft pass+warn auf `0`, alles andere auf `1`.

- Exit `0` proceed · `1` block · `3` quarantine (**nicht** `2` — belegt durch
  argparse und fehlendes `--host`, `dq_check_runner.py:39`).
- `--no-enforce`-Flag: Beobachtungslauf endet unabhängig vom Urteil mit `0`.
- Verdict zusätzlich in Text-/JSON-Ausgabe.
- Solange `enforcement_mode` (AP-4) fehlt, ist das Mapping
  `overall_status`-basiert (`critical|fail`→1); das Feld kommt mit AP-4 dazu.

**Acceptance:** Fixture-Lauf mit failendem Check → Exit 1; mit `--no-enforce`
→ Exit 0 und Verdict in der JSON-Summary.

### AP-3 — O2-Spike: Katalog-/Monitoring-View-Zugriff `[S, 1–2 PT]`

Verifizieren, was der Least-Privilege-Space-User (ADR-0002) tatsächlich sieht:
`SYS.M_TABLES`, `SYS.M_CS_TABLES`, `SYS.M_TABLE_STATISTICS` — für eigene
Objekte, im Open-SQL-Schema, am echten Tenant. Ergebnis als Capability-Probe
im Connector persistieren (analog `secret_status`). **Blockiert AP-6.**
Erwartung dokumentieren: Katalog-Metriken existieren nur für physische
Tabellen (Replication-Targets), nicht für Consumption-/Wrapper-Views.

### AP-4 — Enforcement-Achse MVP: B2 Promotion-Gate `[M/L]`

Implementierungs-Slice steht in `Konzept_Enforcement_Modi_*` §4 (Layer 1–5)
und bleibt gültig; durch AP-1 entfällt der CLI-Umweg für DSP-Pipelines.
Ergänzungen aus dem Review (§3.3):

- **Episoden-Lifecycle:** `open → reconciled → released → resolved`
  (+ `superseded`); `released` unterscheidet manuelle Freigabe von
  Auto-Release (Policy „N grüne Läufe", Default aus).
- **Reconcile-Vertrag:** `manifest_hash` + Generation-Zähler; Rückkanal
  meldet beobachtete Counts + `applied_manifest_hash`; Hash-Mismatch ⇒
  Episode `stale`.
- **Fähigkeits-Matrix:** zeilenbasierter Split nur für
  `not_null`/`completeness`/`keys`/`referential`; `freshness`/`volume`/
  `schema` immer objektgranular.
- **Reihenfolge:** B2 (Objekt-Gate) zuerst; B1 (View-Split) später, gekoppelt
  an C5/WS G (Reject-Store) — gemeinsam entscheiden (siehe `OPEN_TASKS.md` F/C5).
- G8 bleibt dicht: Quarantäne-Zeilen leben nur in Datasphere; Signal speichert
  Counts + Prädikat (`_diagnostic_sql`, `check_engine.py:375`, liefert die
  Splitregel).

### AP-5 — `on_load`-Schedule-Modus `[M]`

Dritter Modus neben `internal`/`external` (Migration 009, `dq_schedules.mode`):
der Poller (`services/api/scheduler.py`) fragt pro Tick die Run-Historie
(`DatasphereClient.get_data_loads`, **Bulk statt N+1**, Backlog J5) und startet
`start_object_run(...)`, wenn ein neuer erfolgreicher Load für das Objekt
erscheint. Dedupe über Run-ID (letzte gesehene Run-ID am Schedule persistieren),
Debounce, Catch-up wie ADR-0005 §3.3. Für Objekte, deren Chains man nicht
anfassen kann, und als Fallback ohne API-Task.

**Acceptance:** Mock-Datasphere liefert neuen Run → genau ein Check-Lauf mit
`triggered_by="scheduler:on_load"`; derselbe Run erneut geliefert → kein
zweiter Lauf.

### AP-6 — Katalog-Evidenz-Templates `[M]` — nach AP-3

Neue `check_library.json`-Templates `row_count_catalog` und `load_lag_catalog`
(Familie `observability`, gating `standard`), nur aktivierbar wenn (a)
Capability-Probe grün und (b) Objekt physische Tabelle (Inventar-Typ).
Kennzeichnung als „Proxy-Evidenz" im Cockpit; **kein Ersatz** des
`COUNT(*)`-Pfads (Contract-Aussage bleibt SQL), sondern billige
Kadenz-Erhöhung. Evidenz-Hierarchie: Business-Timestamp > Run-Evidenz >
Katalog-Proxy > unknown.

### AP-7 — Run-Quellen vervollständigen (= Backlog J) `[M]`

`services/api/datasphere.py`: Transformation Flows + Persist-Tasks abrufen;
**echten Replication-Run-Payload vom Tenant pinnen** (Fixture!), dann
`records_transferred`/`is_delta`/`last_delta_at` typisieren
(`DataLoadOut`, `routers/data_loads.py`; FE `DataLoad`). Voraussetzung für
AP-5 auf allen Objekttypen und für die Volumen-Serie aus Delta-Counts.

### AP-8 — Self-Healing L4-Paket `[M]` — nach AP-4

Aufsteigender Eingriff, alle Default **aus**, budgetiert, als Activity-Event
auditiert, globaler Kill-Switch (Setting):

1. Auto-Re-Check bei `state=error` (ein Retry mit Backoff, Engine/Runner).
2. Auto-Release der Quarantäne nach N grünen Läufen (Policy je Contract).
3. Load-Retry: fehlgeschlagener Replication-Run → (opt-in
   `DATASPHERE_ALLOW_TRIGGER`) Retry-Chain über die öffentliche Task-Chain-API
   auslösen, Retry-Budget, danach Incident + RCA.
4. Schema-Drift → automatisch generierter Contract-Patch-**Vorschlag**
   (G3-konform, nie Auto-Apply bei Breaking).

Vorhandene Bausteine: `store.auto_resolve_incidents` + Compliance-Auto-Recovery
(`routers/objects.py:636/728/809`), `obs/rca.py`, Proposal-Miner
(`obs/miner.py`, deterministische IDs), `schema_drift_service.py`.

### AP-9 — Doku-Pflege `[XS]`

- `OPEN_TASKS.md`: E1 auf ✅; neue AP-IDs dieses Handovers unter N/F/J
  verlinken.
- `ADR-0005`: Hinweis auf API-Task-Feature als vierte Option ergänzen (Chain →
  Signal-API), sobald AP-1 verprobt ist.

---

## Offene Entscheidungen (vor bzw. während der Umsetzung)

1. **AP-1:** Exakte Status-Code-/Response-Erwartung des API-Tasks (Tenant-Spike;
   SAP-Doku: *Run API Tasks in a Task Chain*). Erst danach den Endpoint-Contract
   fixieren.
2. **AP-4:** `quarantine`-Verdict im binären API-Task-Ergebnis — FAILED +
   Signal triggert Split-Chain outbound (empfohlen) vs. zwei getrennte Chains.
3. **AP-4/C5:** B1-Zeilen-Split gemeinsam mit Reject-Store entscheiden
   (`OPEN_TASKS.md` F ↔ C5).
4. **J1 (unverändert offen):** `skipped_stale` vs. `downgraded` bei
   Run-basierter Staleness — vor Gate-Integration der Freshness-Achse klären.
5. **AP-6:** Ob ein neuer G6-State „skipped_unchanged" (Proxy unverändert →
   teuren Lauf sparen) den Nutzen rechtfertigt — nur mit Beleg einführen.

## Gates / Invarianten (bei allen APs)

G1 (kein SQL im Contract — Enforcement ist ein Dataclass-Feld) · G2 (Schema
nur zur Laufzeit binden, auch in neuen Templates `{schema}`) · G6 (neue
States explizit, nie stilles Auslassen) · G7 (`dq_core` bleibt frameworkfrei —
API-Task-Vertrag lebt in `services/`) · G8 (Quarantäne-Zeilen nie in Signal;
Diagnose nur über den gegateten Pfad) · S5 (Chain-Aufruf braucht echte Auth).

## Verifikation (lokal, vor Push)

```bash
make test                                  # Backend inkl. G5-Regression
cd apps/cockpit && npm run typecheck && npm run lint && npm run test -- --run
python cli/dq_check_runner.py --schema MY --checks <fixture> --mock  # Exit-Codes (AP-2)
```
