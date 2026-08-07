# REVIEW — Observability-Quellen (Freshness/Volume), Quarantäne, Orchestrierung & Self-Healing

**Adressat:** Plattform-Team, Beratung · **Stand:** 2026-07-08
**Status:** Review + Konzept-Ergänzung (kein Code geändert)
**Zweck:** Vier Fragen beantworten: (1) Wie überwachen wir Freshness/Volume
heute, und sollten andere HANA-Monitoring-Views als Quelle dienen? (2) Was ist
der Stand der Quarantäne von schlechten Werten? (3) Wie sieht die Anbindung an
Task Chains / native Datasphere-Orchestrierung aus, was fehlt? (4) Welche
Self-Healing-Möglichkeiten hat ein Tool wie Signal?

> Verwandte Dokumente: `Konzept_Runs_Freshness.md` (Run-Evidenz) ·
> `Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md` (Quarantäne-Proposal) ·
> `ADR-0002_Datasphere-DB-Zugriff.md` (Least-Privilege, Hub-Topologie) ·
> `ADR-0005_Scheduling.md` (externes vs. internes Scheduling) ·
> `OPEN_TASKS.md` (Backlog-IDs E/F/J/N/C5/O2).

---

## 0 — Kurzantworten

1. **Freshness/Volume:** solide dreiteilige Basis (SQL-Checks + adaptive
   Baselines + Run-Historie via REST), aber jede Messung kostet heute einen
   Table-Scan und Objekte ohne Business-Timestamp-Spalte sind blind.
   **HANA-Monitoring-Views (`M_TABLES`, `M_CS_TABLES`, `M_TABLE_STATISTICS`)
   taugen als dritte, billige Evidenz-Stufe („Load-Lag/Volume-Proxy"), nicht
   als Ersatz** — wegen Privilegien (ADR-0002) und weil die meisten
   Prüfobjekte Views sind, für die es keine Katalog-Zeilenzahl gibt. Vorher
   Spike O2.
2. **Quarantäne: nicht implementiert.** Es existiert ein tragfähiges Konzept
   (`Konzept_Enforcement_Modi_*`, Backlog F) plus der optionale Reject-Store
   (C5/WS G). Dieses Dokument ergänzt das Konzept um Episoden-Lifecycle,
   Reconcile-Vertrag, Fähigkeits-Matrix pro Check-Familie und eine
   MVP-Reihenfolge (Promotion-Gate vor View-Split).
3. **Orchestrierung:** ADR-0005 ist geliefert (Store-backed Poller,
   `external`-Modus dokumentiert Task-Chain-Hoheit). **Korrektur gegenüber den
   bestehenden Konzept-Docs:** Task Chains können seit 2025 über **API-Tasks**
   ausgehende HTTP-Calls machen (POST/PUT über eine HTTP-Connection, synchron
   ≤ 60 s oder asynchron mit Status-Polling). Eine Chain kann Signal also
   **nativ rufen** — größter Hebel ist ein async-kompatibler Run-Endpoint
   (202 + `Location` → Status-Endpoint), der `proceed`/`block` auf
   COMPLETED/FAILED mappt und damit das Promotion-Gate ohne CLI-Umweg
   ermöglicht. Ergänzend: „on_load"-Trigger für nicht orchestrierte Objekte,
   Verdict-Exit-Code in der CLI für Nicht-DSP-Orchestratoren.
4. **Self-Healing:** Signal hat die Grundbausteine bereits (Auto-Recovery von
   Compliance/Incidents bei grünem Lauf, adaptive Baselines, Proposal-Miner,
   RCA). Ausbau entlang einer Reifegrad-Leiter: erkennen → diagnostizieren →
   vorschlagen → mit Freigabe handeln → begrenzt autonom handeln. Signal
   bleibt Entscheidungsebene; die Ausführung (Re-Load, Split, Retry) gehört
   nach Datasphere — mit Budget, Audit und Kill-Switch.

---

## 1 — Ist-Stand: Wie Freshness & Volume heute überwacht werden

### 1.1 SQL-basierte Checks (Primärpfad)

Quelle: `packages/dq_core/library/check_library.json`, kompiliert aus
Contract-Garantien (`contract/compiler.py:267-282`):

| Check | SQL-Muster | Kosten | Bemerkung |
|---|---|---|---|
| `freshness` | `SECONDS_BETWEEN(MAX("<col>"), CURRENT_TIMESTAMP)` | Spalten-Scan | braucht Business-Timestamp-Spalte; gating=`gate` |
| `row_count` / `volume_min_rows` | `COUNT(*)` | Scan (Column-Store: billig) | statische Untergrenze |
| `volume_anomaly` | `COUNT(*)` + Baseline-Bewertung | Scan | gating=`gate` |
| `volume_delta` | `COUNT(*)` + `DELTA <= x%` gegen Vorlauf | Scan | Run-over-Run, nutzt `get_previous_actuals` |
| `recent_volume` | `COUNT(*) WHERE <col> >= ADD_DAYS(now,-1)` | Scan | „frisch nachgeladen?" |
| `column_count` | `SYS.TABLE_COLUMNS` ∪ `SYS.VIEW_COLUMNS` | Katalog | bereits der Beweis, dass Katalog-Views als Quelle funktionieren |

Ausführung: Batch-`UNION ALL` über `DUMMY` mit Statement-Timeout
(`check_engine.py:260-303`) — effizient und gehärtet.

### 1.2 Adaptive Baselines (Observability-Schicht)

`obs/baselines.py` + `obs/resolver.py`: pro Objekt/Metrik rollierende oder
saisonale Baselines (`dow`/`eom`/`hour`-Buckets, Migrationen 010/011),
robuste Bounds über **Median/MAD** (`compute_robust_bounds`, Sensitivity
k=2/3/4), Warmup-Gate (5 Läufe). Der Resolver injiziert
`volume_adaptive_rows` / `freshness_adaptive_<col>` zur Laufzeit; ohne reife
Baseline wird ehrlich `downgraded` gemeldet (G6), nie geraten.

> **Doku-Drift:** `OPEN_TASKS.md` E1 („Verdikt-Pfad nutzt weiter
> `compute_bounds`") ist überholt — der Resolver nutzt
> `compute_robust_bounds`, `median_v`/`mad` sind persistiert (Migration 010).
> E1 sollte auf ✅ gestellt werden.

### 1.3 Gating

Freshness-/Volume-Anomalie-Checks sind `gating=gate`: schlagen sie fehl,
werden teure Konsistenz-Checks als `skipped_stale` markiert statt Phantom-
Failures zu produzieren (`check_engine.py:214-240`). Das ist die vorhandene
Verbindung „Aktualität gates Korrektheit".

### 1.4 Run-basierte Freshness (REST-Evidenz)

`services/api/datasphere.py` (OAuth2 Client-Credentials) holt **Task-Chain- und
Replication-Flow-Runs**; `routers/data_loads.py` normalisiert zu `DataLoadOut`.
Bekannte Lücken (siehe `Konzept_Runs_Freshness.md`, Backlog J):

- Transformation Flows und Persist-Tasks werden **nicht** abgerufen.
- Feldnamen sind ungepinnt (`_normalise`-Rateketten, keine Fixture vom echten
  Tenant); Row-Counts/Delta-Modus nicht modelliert.
- N+1-Fan-out pro Objekt (Rate-Limit-Risiko bei Tenant-Scale).

### 1.5 Bewertung

Die Architektur ist richtig (zwei Achsen: korrekt? × aktuell?; Ehrlichkeits-
Regel „unknown ≠ fresh"). Drei strukturelle Schwächen:

1. **Jede Messung scannt.** `COUNT(*)`/`MAX(col)` sind im Column-Store billig,
   aber nicht kostenlos — bei hoher Kadenz und vielen Objekten summiert sich
   das, und der Scan läuft mit dem Least-Privilege-User im Consumption-Layer.
2. **Blinde Objekte.** Ohne nutzbare Timestamp-Spalte gibt es keine
   SQL-Freshness (bekannt als E2/O2: HDLF/Data-Lake-Views, technische Views).
3. **Run-Evidenz unvollständig** (1.4) — genau die Quelle, die blinde Objekte
   abdecken würde.

---

## 2 — Andere HANA-Monitoring-Views als Quelle? (die konkrete Frage)

### 2.1 Kandidaten

| View | Liefert | Nutzen für Signal |
|---|---|---|
| `SYS.M_TABLES` | `RECORD_COUNT`, `TABLE_SIZE` pro physischer Tabelle | Volume-Proxy **ohne Scan**; Volumen-Zeitreihe fast gratis |
| `SYS.M_CS_TABLES` | `RECORD_COUNT`, Memory, `LAST_MERGE_TIME`, Delta-Größe | Load-Lag-Proxy („wann zuletzt geschrieben/gemerged") + Speicher-Anomalien |
| `SYS.M_TABLE_STATISTICS` | DML-Zähler (Insert/Update/Delete), letzte Änderung | Änderungs-Evidenz: „hat sich seit dem letzten Lauf überhaupt etwas geändert?" |
| `SYS.TABLE_COLUMNS` / `SYS.VIEW_COLUMNS` | Schema | bereits in Nutzung (`column_count`, Schema-Drift) |

### 2.2 Die drei ehrlichen Einschränkungen

**(a) Privilegien — Konflikt mit ADR-0002.** `M_*`-Monitoring-Views sind
privilegien-gefiltert und brauchen je nach View Katalog-/Monitoring-Rechte.
Der beschlossene technische Space-User ist strikt least-privilege (SELECT nur
auf Prüf-Views); der Database Analysis User ist ausdrücklich ausgeschlossen.
**Ob der Open-SQL-Space-User `M_TABLES`/`M_CS_TABLES` für die eigenen Objekte
sieht, ist aus dem Repo nicht verifizierbar** — exakt der bestehende Spike
**O2** („Zugriffspfad Katalog-/Lastmetadaten"). Der Spike muss vor jedem Bau
laufen; Ergebnis als Capability-Probe im Connector persistieren.

**(b) Reichweite — Views haben keine Katalog-Zeilenzahl.** Katalog-Metriken
existieren nur für **physische Tabellen**. Signals Prüfobjekte sind per
Hub-Topologie (ADR-0002 §7) fast immer **Wrapper-/Consumption-Views**; deren
`RECORD_COUNT` gibt es im Katalog nicht, und die internen Persistenz-Tabellen
persistierter Views liegen vermutlich außerhalb des Open-SQL-Schemas. Der
Katalog-Pfad hilft also primär für **Replication-Targets (lokale Tabellen)**
— dort dafür sehr gut.

**(c) Semantik — Load-Lag ≠ Freshness.** `CONTEXT.md` trennt bereits sauber:
Katalog-Änderungszeit ist **Load-Lag** (technische Pipeline-Lebendigkeit),
nicht die Contract-Garantie „jüngster Geschäftsfakt ≤ X alt". Ein Merge kann
laufen, ohne dass neue Geschäftsdaten kamen — und umgekehrt.

### 2.3 Empfehlung: Evidenz-Hierarchie um eine dritte Stufe erweitern

Die Freshness-Evidenz-Hierarchie aus `Konzept_Runs_Freshness.md` wird zu:

```
Stufe 1 (stark)   Business-Timestamp per SQL (MAX(col))          → Contract-Garantie
Stufe 2 (mittel)  Run-Evidenz (Replication/Chain, Delta-Counts)  → Load-Lag + Volumen-Serie
Stufe 3 (schwach) Katalog/Monitoring-Views (M_TABLES, M_CS_*)    → Load-Lag-/Volume-PROXY
Keine Quelle      „unknown" — nie als frisch darstellen
```

Konkret:

- **Neue Library-Templates** `row_count_catalog` und `load_lag_catalog`
  (Familie `observability`, gating `standard`), nur aktivierbar, wenn die
  Capability-Probe (2.2a) grün ist **und** das Objekt eine physische Tabelle
  ist (Inventar kennt den Typ). Kennzeichnung im Cockpit als „Proxy-Evidenz".
- **Kein Ersatz des `COUNT(*)`-Pfads.** Katalog-Zahlen sind Näherungen
  (MVCC/Delta); die Contract-Aussage bleibt SQL-basiert. Der Proxy dient der
  **Kadenz-Erhöhung** (z. B. stündlicher billiger Proxy, täglicher echter
  Check) und als Vor-Gate: Proxy unverändert → teuren Lauf überspringen
  (`skipped_stale`-Analogon „skipped_unchanged" wäre ein neuer G6-State —
  nur einführen, wenn der Nutzen belegt ist).
- **Reihenfolge:** O2-Spike → Capability-Probe → Templates. Kein neues
  Privileg jenseits dessen, was der Space-User ohnehin sieht (ADR-0002 §5
  bleibt unangetastet: niemals der Analysis User).
- **Parallel J weitertreiben** (Transformation Flows + Persist-Tasks abrufen,
  Payload pinnen, Row-Counts modellieren) — für View-Objekte ist Run-Evidenz
  die einzige scanfreie Quelle, wichtiger als der Katalog-Pfad.

---

## 3 — Quarantäne schlechter Werte: Ist-Stand & Konzept-Ergänzung

### 3.1 Ist-Stand: nicht implementiert

Im Code existiert **kein** `enforcement_mode`, keine `dq_quarantine`-Tabelle,
kein Verdict-Feld (Grep über `packages/`, `services/`, `apps/` — einziger
Treffer ist ein Notification-Testname). Die CLI kennt nur Exit 0/1
(`cli/dq_check_runner.py:73`). Was existiert, ist das **Proposal**
`Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md` (Backlog **F**) und der
angrenzende Reject-Store **C5/WS G**.

### 3.2 Bewertung des vorhandenen Konzepts

Das Konzept ist tragfähig und bleibt die Grundlage; seine Kernentscheidungen
halten dem Review stand:

- **Signal entscheidet, Datasphere handelt** — konsistent mit read-only
  (ADR-0002) und der Hub-/Manifest-Mechanik des Monitoring-Share-Hubs.
- **Prädikat = Splitregel gratis** — `_diagnostic_sql` (`check_engine.py:375`)
  liefert die `WHERE <bad>`-Form bereits.
- **Default `monitor`** — keine grüne Pipeline wird zum Überraschungs-Stopp.
- **Exit-Code 3** (nicht 2) für `quarantine` — Kollision mit argparse vermieden.

### 3.3 Ergänzungen (dieses Review)

**(1) Episoden-Lifecycle explizit machen.** Analog Incident-Lifecycle
(Migration 004):

```
open ──(Skript meldet Split)──► reconciled ──(Freigabe/N grüne Läufe)──► released ──► resolved
  └─(Kontrakt geändert / Prädikat obsolet)──► superseded
```

`released` unterscheidet manuelle Steward-Freigabe von **Auto-Release**
(Policy je Contract: „nach N aufeinanderfolgenden grünen Läufen" — der erste
sichere Self-Healing-Loop, siehe §5). Auto-Release ist default **aus**.

**(2) Reconcile-Vertrag härten.** Das Manifest (Soll-Zustand) braucht:
`manifest_hash` (Prädikat + Contract-Version + Zielobjekt), einen
Generation-Zähler und im Rückkanal die **beobachteten** Zahlen
(`row_count_quarantined`, `row_count_clean`, `applied_manifest_hash`).
Meldet das Skript einen anderen Hash als den aktuellen, ist die Episode
`stale` — Signal zeigt „Quarantäne-Regel veraltet" statt falscher Zahlen.
Reconcile ist idempotent: gleiche Generation zweimal anwenden = No-Op.

**(3) Fähigkeits-Matrix pro Garantie-Familie** (präzisiert §2 des Konzepts):

| Familie | Zeilen-Split (B1) | Objekt-Gate (B2) |
|---|---|---|
| `not_null`, `completeness` | ✓ (`WHERE col IS NULL …`) | ✓ |
| `keys` (Duplikate) | ✓ (Fenster über PK) | ✓ |
| `referential` (Orphans) | ✓ (`NOT EXISTS` Parent) | ✓ |
| `distribution`/`aggregate` | (✓) nur wenn zeilenweise formulierbar | ✓ |
| `freshness`, `volume`, `schema` | ✗ (Objekt-Eigenschaft) | ✓ |

**(4) MVP-Reihenfolge: B2 vor B1.** Das Staging-Promotion-Gate (objektgranular,
keine Zusatz-Views) liefert 80 % des Werts mit 20 % der Mechanik und braucht
nur: `enforcement_mode`-Feld (Layer 1–2 des Konzepts), CLI-Exit-Code 3,
Episode + Badge. **Neu (§4.2):** über den API-Task-Schritttyp der Task Chains
ist B2 sogar **nativ** abbildbar — die Chain ruft Signals Run-Endpoint
asynchron und promotet nur bei COMPLETED; der CLI-Umweg entfällt für
DSP-orchestrierte Pipelines. Der zeilenbasierte View-Split (B1) folgt, wenn
ein Kunde ihn zieht — er hängt ohnehin an C5/WS G (Reject-Store) und am
Reconcile-Skript.

**(5) PII bleibt dicht (G8).** Quarantäne-Zeilen leben ausschließlich in
Datasphere (`V_<obj>_QUARANTINE`); Signal speichert nur Counts + Prädikat +
Episode. Drilldown in Zeilen läuft über den bestehenden, gegateten
Diagnostics-Pfad — keine neue Rohzeilen-Erfassung.

---

## 4 — Task Chains & Datasphere-native Orchestrierung

### 4.1 Was heute existiert (verifiziert)

| Baustein | Stand |
|---|---|
| Externes Scheduling (Task Chain/Cron → CLI) | dokumentierter Default (ADR-0005); CLI läuft engine-direkt |
| Interner Poller | **geliefert**: `dq_schedules` (Migration 009), claim-basiert, `services/api/scheduler.py`, `routers/schedules.py`, `SCHEDULER_ENABLED` opt-in |
| `external`-Modus | dokumentiert Task-Chain-Hoheit im Cockpit, Poller fasst das Objekt nie an |
| REST-Client | Run-Historie lesend (Task Chains, Replication Flows) |
| `@sap/datasphere-cli`-Wrapper | `datasphere_cli.py`: Spaces/Objekte/CSN — **kein** Task-Chain-Trigger |
| Doppellauf-Schutz | `try_begin_run` (partieller Unique-Index) — prozessübergreifend |

### 4.2 Korrektur: Task Chains können HTTP — API-Tasks

Die Aussage in `Konzept_Enforcement_Modi_*` §3 („eine Task-Chain kann nicht
nativ einen ausgehenden HTTP-Call machen") ist **überholt**. SAP hat 2025
**API-Tasks** als Schritttyp in Task Chains eingeführt (SAP Help: *Run API
Tasks in a Task Chain*):

- **Aufruf:** HTTP **POST oder PUT** über eine vorab definierte, generische
  **HTTP-Connection** (Host, Pfad, Credentials liegen in der Connection).
- **Synchron:** wartet max. **60 s** auf die Antwort; Status-Code →
  COMPLETED/FAILED des Tasks.
- **Asynchron:** Request wird abgesetzt, danach pollt Datasphere einen
  **Status-Endpoint** (aus dem `Location`-Response-Header oder explizit
  konfiguriert) bis RUNNING → COMPLETED/FAILED.
- **Grenze:** das Ergebnis ist **binär** (Task erfolgreich/fehlgeschlagen).
  Task Chains verzweigen nicht auf Response-Inhalte — ein Drei-Wege-Verdict
  (`proceed|quarantine|block`) ist nativ nicht abbildbar, wohl aber das
  Zwei-Wege-Gate.

Voraussetzungen auf Signal-Seite: Signal muss aus dem Tenant per HTTPS
erreichbar sein, und der Aufruf braucht echte Auth (S5: `noauth` bindet nur
loopback — für den Chain-Aufruf ist ein technischer Principal mit
Run-Trigger-Recht nötig, `require_roles(steward,…)`).

### 4.3 Empfehlungen

**R1 — Inbound-Integration über API-Task (größter Hebel).** Signals
vorhandenes Muster passt bereits fast: `POST /api/objects/{id}/run` startet
einen Hintergrund-Lauf und liefert `run_id`; `GET /api/runs/{run_id}`
existiert. Für den API-Task-Async-Modus fehlt nur der formale Vertrag:
Run-Start antwortet **202 + `Location: /api/runs/{run_id}/status`**, und der
Status-Endpoint mappt den Lauf auf die von Datasphere erwartete
RUNNING/COMPLETED/FAILED-Semantik — inkl. Verdict-Mapping `proceed`→
COMPLETED, `block` (und vorerst auch `quarantine`) → FAILED. Damit wird die
Chain `[Load → Staging] → [API-Task: Signal-Lauf] → [Promote nur bei Erfolg]`
zum **nativen Promotion-Gate (B2) ohne CLI-Umweg**. Die exakten
Status-Code-Erwartungen des API-Tasks sind am Tenant zu verifizieren
(Feature ist jung, Details versionsabhängig); der 60-s-Sync-Modus ist für
DQ-Läufe ungeeignet → async ist der Zielpfad.

**R2 — „on_load"-Trigger (additiv, für nicht orchestrierte Objekte).**
Dritter Schedule-Modus neben `internal`/`external`: der vorhandene Poller
fragt die Run-Historie (bestehender `DatasphereClient`) und startet
`start_object_run(...)`, sobald für das Objekt ein **neuer erfolgreicher
Load** erscheint (Dedupe über `run_id`, Debounce, Catch-up-Politik wie 3.3
der ADR). Wichtig für Objekte, deren Chains man nicht anfassen darf/kann,
und als Fallback ohne API-Task. N+1-Problem (J5) durch Bulk-Abruf im Tick
lösen. Erweitert ADR-0005 additiv (Backlog N).

**R3 — Verdict-Exit-Code in der CLI (klein, sofort).** Exit 0/1/3 +
`--no-enforce` + Verdict in der JSON-Ausgabe (Layer 3 des
Enforcement-Konzepts). Bleibt relevant für **Nicht-DSP-Orchestratoren**
(Airflow, Cron, CI) und Lite-Deployments ohne laufenden Service. Heute wirft
die CLI Warn und Pass in einen Topf (`0`) und alles andere auf `1`.

**R4 — Outbound-Trigger als bewusstes Opt-in.** Für Remediation-Flows kann
Signal Chains **auslösen** — die öffentliche Task-Chain-API existiert
(`POST /api/v1/datasphere/tasks/chains/<space>/run/<chain>`). Das ist kein
Daten-Schreiben, aber ein Handeln auf dem Tenant: eigener technischer User,
eigenes Setting (`DATASPHERE_ALLOW_TRIGGER`, Default **false**), jede
Auslösung als Activity-Event auditiert. Zusammen mit R1 schließt sich der
Kreis: Chain ruft Signal (Gate), Signal ruft bei `quarantine` die
Split-/Remediation-Chain (Drei-Wege-Verdict trotz binärem API-Task).

**R5 — Kein Task-Monitor-Nachbau.** Abgrenzung aus `Konzept_Runs_Freshness.md`
bestätigt: tiefe Job-Logs verlinken, nicht spiegeln; Run-Info lebt in
Objekt/Grid/Lineage/Incidents.

**R6 — Run-Quellen vervollständigen (= Backlog J).** Transformation Flows +
Persist-Tasks abrufen, echten Payload pinnen, `records_transferred`/`is_delta`
modellieren — Voraussetzung für R2 auf allen Objekttypen und für die
Volumen-Serie „gratis" aus Delta-Counts.

---

## 5 — Self-Healing-Möglichkeiten

### 5.1 Was Signal heute schon „selbst heilt" (verifiziert)

- **Auto-Recovery:** grüner Folgelauf setzt Compliance zurück und schließt
  offene Incidents (`store.auto_resolve_incidents`, `routers/objects.py:636/728/809`).
- **Adaptive Schwellen:** Baselines lernen rollierend/saisonal; Schwellen
  „heilen" mit dem Datenprofil mit, statt zu veralten (§1.2).
- **Proposal-Miner:** driftet ein Istwert dauerhaft, entsteht ein
  daten­getriebener Vorschlag mit deterministischer ID — Steward entscheidet.
- **RCA + Blast-Radius:** `obs/rca.py` rankt Upstream-Ursachen-Kandidaten und
  berechnet betroffene Contracts — die Diagnose-Hälfte des Heilens.
- **Gating:** stale Daten erzeugen `skipped_stale` statt Phantom-Failures —
  verhindert, dass „Heilung" auf falsche Alarme reagiert.
- **Scheduler-Robustheit:** Catch-up-Politik (ein Aufhol-Lauf, kein
  Backfill-Sturm), claim-basiert, Doppellauf-sicher.

### 5.2 Reifegrad-Leiter für Self-Healing-Pipelines

```
L0 Erkennen        Checks, Baselines, Run-Evidenz            ✅ vorhanden
L1 Diagnostizieren RCA, Blast-Radius, Lineage-Propagation    ◑ vorhanden (Propagation offen, J3)
L2 Vorschlagen     Threshold-/Contract-Patch-Proposals       ◑ Thresholds ja; Schema-Drift-Patch offen
L3 Handeln mit     Quarantäne-Release, Proposal-Accept,      ◻ braucht F (Enforcement-Achse)
   Freigabe        Re-Run-Knopf am Incident
L4 Begrenzt        Auto-Release, Auto-Re-Check, Load-Retry   ◻ Konzept unten
   autonom         mit Budget
```

### 5.3 Konkrete Kandidaten (read-only-verträglich, aufsteigender Eingriff)

1. **Auto-Re-Check bei `error`** (L4, klein): Checks mit `state=error`
   (Timeout, Verbindungsabriss) einmal mit Backoff wiederholen, bevor ein
   Incident entsteht. Reine Engine-/Runner-Mechanik, kein Datasphere-Eingriff.
2. **Auto-Release der Quarantäne** (L4, an F gekoppelt): Episode schließt nach
   N aufeinanderfolgenden grünen Läufen automatisch (Policy je Contract,
   Default aus) — spiegelt die vorhandene Compliance-Auto-Recovery.
3. **Load-Retry-Orchestrierung** (L4, an R4 gekoppelt): fehlgeschlagener
   Replication-Run erkannt → (opt-in) Retry-Chain auslösen, **Retry-Budget**
   (z. B. max. 2), danach Eskalation als Incident mit RCA. Ohne Opt-in:
   Notification mit Runbook-Link statt Trigger.
4. **Schema-Drift-Selbstheilung** (L2/L3): erkannte Drift
   (`schema_drift_service.py` existiert) → automatisch generierter
   Contract-Patch-Vorschlag (minor additiv / major bei Bruch, G3-konform) zur
   Steward-Freigabe. **Nie** Auto-Apply bei Breaking Changes.
5. **Baseline-Re-Anchor nach gewolltem Regimewechsel** (L3): Accept eines
   Volumen-Proposals setzt die Baseline neu auf, statt wochenlang gegen das
   alte Regime zu warnen.
6. **Freshness-getriebenes Nachfassen** (L4, an R2 gekoppelt): Objekt `late`
   und kein Run in Sicht → gezielter Check-Lauf + Timeliness-Incident statt
   stilles Warten auf den nächsten Slot.

### 5.4 Leitplanken (nicht verhandelbar)

- **Signal bleibt Entscheidungsebene** — jede Daten-Aktion (Split, Re-Load,
  Promotion) führt Datasphere/der Orchestrator aus (ADR-0002).
- **Autonomie ist budgetiert und auditiert**: jede autonome Aktion ist ein
  Activity-/Operation-Event, hat ein Retry-/Aktions-Budget und einen
  globalen Kill-Switch; Defaults sind aus (dieselbe Disziplin wie
  „Default `monitor`").
- **G6/G8 unverändert**: auch Self-Healing-Ergebnisse sind explizite Zustände
  (nie stilles Auslassen), Rohzeilen bleiben hinter dem PII-Gate.

---

## 6 — Priorisierte Empfehlungen (mit Backlog-Bezug)

| # | Empfehlung | Aufwand | Bezug |
|---|---|---|---|
| 1 | API-Task-Vertrag: 202+`Location`-Status-Endpoint für Run-Start, Verdict→COMPLETED/FAILED | M | §4.3 R1 (neu, entsperrt natives B2-Gate) |
| 2 | CLI-Verdict-Exit-Code (0/1/3, `--no-enforce`) | S | F Layer 3, §4.3 R3 |
| 3 | O2-Spike: Katalog-/Monitoring-View-Zugriff des Space-Users verifizieren | S (1–2 PT) | K/O2, §2.2 |
| 4 | `on_load`-Schedule-Modus (Run-getriggerte Checks) | M | N (neu), §4.3 R2 |
| 5 | Run-Quellen vervollständigen + Payload pinnen | M | J, §4.3 R6 |
| 6 | Enforcement-Achse MVP = B2 Promotion-Gate + Episoden-Lifecycle | M/L | F + §3.3, nutzt #1 |
| 7 | Katalog-Evidenz-Templates (`row_count_catalog`, `load_lag_catalog`) | M | §2.3, nach #3 |
| 8 | Self-Healing L4-Paket (Auto-Re-Check, Auto-Release, Retry-Budget) | M | §5.3, nach #6 |
| 9 | `OPEN_TASKS.md` E1 auf ✅ korrigieren; Enforcement-Konzept §3 aktualisieren | XS | §1.2, §4.2 |

**Reihenfolge-Logik:** #1 macht Signal für DSP-orchestrierte Pipelines nativ
gate-fähig und ist die Voraussetzung für das Quarantäne-MVP (#6); #2/#3 sind
klein und entsperren die übrigen Pfade; #4/#5 machen die Freshness-Achse
ereignisgetrieben statt kadenz-geraten; #7/#8 bauen auf den verifizierten
Fundamenten auf.
