# Hypothese: voller Ersatz der Signal-Prüfkette durch datacontract-cli *mit* HANA-Engine

> Drittes Begleitdokument der `datacontract-cli_*`-Serie, nach
> [`datacontract-cli_Integration.md`](datacontract-cli_Integration.md)
> (Feature-Landkarte) und [`datacontract-cli_Bewertung.md`](datacontract-cli_Bewertung.md)
> (Entscheidungsgrundlage). Während die Bewertung in §6 die Frage *„lohnt voller
> Ersatz?"* **argumentativ** verneint, zeichnet dieses Dokument denselben Fall
> **konstruktiv durch**: Wie *sähe* die Architektur konkret aus, wenn
> (a) `datacontract test` einen echten **HANA-Executor** (`type: hana`) bekäme und
> (b) Signal seine native Prüfkette (`validator → compiler → check_engine`)
> **dadurch ersetzt**?
>
> Zweck: ein präzises Soll-Bild als Diskussions- und Schaubild-Grundlage — inkl.
> der Teile, die *nicht* verschwinden, sondern als **Shim** zurückkehren. Stand:
> Konzept, nicht-bindend. **Empfehlung am Ende bleibt: nicht voll ersetzen** —
> hier aber mit konkreter Architektur belegt statt nur behauptet.

---

## 0. Die Prämisse — was wir für dieses Gedankenexperiment annehmen

| # | Annahme | Realität heute |
|---|---|---|
| P1 | `datacontract test` besitzt ein **HANA-Backend** (`servers: type: hana`) — seit v1.0.0 ein **ibis-Backend** (Ausführung via ibis→`sqlglot`, nicht mehr Soda Core), realistisch auf `hdbcli`/`sqlalchemy-hana` | existiert **nicht** (kein ibis-HANA-Backend; ibis kennt DuckDB/Snowflake/BigQuery/Postgres/Spark …, kein HANA) |
| P2 | Quality wird **im Contract-YAML** geschrieben (`quality:`-Sektion, Ebene B) statt aus Garantien kompiliert | bei Signal verboten (Gate G1) |
| P3 | Wir akzeptieren das **datacontract.com-/ODCS-YAML-Format** als kanonische Quelle der Wahrheit statt unseres Schemas v1 | heute ist `contracts/*.yaml` (Schema v1) die Wahrheit, ODCS nur Einweg-Export |

Unter P1–P3 fällt die Existenzberechtigung dreier Kern-Bausteine — `validator.py`
(G1-Gate), `compiler.py` (einziger SQL-Erzeuger) und `check_engine.py` (HANA-Runner)
— weg. **Alles andere bleibt** und muss neu angedockt werden. Genau das ist der
Knackpunkt.

---

## 1. Ist-Architektur (heute, nativer Pfad)

Referenz: `README.md` (Repo-Layout), `packages/dq_core/`.

```
contracts/*.yaml      packages/dq_core/                                          services/        apps/
(Schema v1,           ─────────────────────────────────────────────────────     ─────────        ─────
 SQL-frei)
   │
   ▼  G1            ┌───────────┐  G1   ┌───────────┐  CheckDef  ┌──────────────┐   ┌──────────┐  ┌─────────┐
┌──────────┐ json   │validator  │──────▶│ compiler  │──────────▶│ check_engine │──▶│  store   │─▶│ Cockpit │
│ Contract │schema  │.py        │guaran-│.py        │ (SQL aus   │.py           │   │ sqlite/  │  │ React   │
│ YAML     │───────▶│           │ tees  │+library/  │ Templates) │ hdbcli,      │   │ hana     │  │ Grid/   │
└──────────┘        └───────────┘ →SQL  │check_lib  │            │ NUR LESEND   │   │+compli-  │  │ SLA/    │
                                         │.json      │            │ batch/gating │   │ ance.py  │  │ Cover.  │
                                         └───────────┘            │ PII-Gate(G8) │   └──────────┘  └─────────┘
                                                                  └──────────────┘        │  ▲
   obs/ (baselines, miner) ─ proposals ─▶ contracts             lineage/ (CSN)            │  │ compliance/
                                                                                          │  │ SLA-Events
   to_odcs() ──▶ *.odcs.yaml (Einweg, Interop)                  cli/dq_check_runner.py ───┘  │ (Store-only, A1)
```

**Eigenschaften, die wir später als Anforderungen wiederfinden:**

- **G1** — kein SQL im Contract; `compiler.py` ist der *einzige* SQL-Erzeuger,
  deterministisch aus `check_library.json` (~v4-Katalog inkl. SAP/HANA-Checks).
- **G2** — `{schema}`-Platzhalter, erst zur Laufzeit gebunden (`bind_schema`).
- **G6** — Gating sichtbar: günstige Frische-Gates entscheiden über teure
  Konsistenz-Checks; übersprungene Checks erscheinen als `skipped_stale`
  (`check_engine._run_with_gating`).
- **G7** — `dq_core` ist frameworkfrei (keine Tool-/Framework-Importe).
- **G8** — PII-Gate: Rohzeilen verlassen HANA nur mit explizitem
  `diagnostics.enabled` am Check (`check_engine._run_one_check`).
- **HANA-Native-SQL** — Batch via `UNION ALL ... FROM DUMMY`, `statementTimeout`,
  `APPROXIMATE_COUNT_DISTINCT`, `LIKE_REGEXPR`, `SYS`-Views, SAP-Input-Parameter.
- **A1** — Compliance/SLA leben **nur** im Store (`compliance.py`), nie im YAML.

---

## 2. Soll-Architektur unter der Hypothese (voller Ersatz)

Die CLI wird zum **Executor**. Drei native Bausteine entfallen, **vier Schichten
um die CLI herum bleiben** und ein neuer **Adapter/Harness** entsteht.

```
contracts/*.dcs.yaml    NEU: signal_harness/                       datacontract-cli      services/   apps/
(datacontract.com-      ────────────────────────────────────      (extern, mit          ─────────   ─────
 Format, MIT quality:)                                              HANA-Engine)
   │
   ▼                  ┌──────────────┐   subprocess   ┌─────────────────────────────┐
┌──────────┐          │ ro/PII-Shim  │───────────────▶│ datacontract test           │
│ Contract │          │ (Ex-G8/G7/   │   datacontract │  servers.type: hana         │
│ YAML mit │─────────▶│  read-only)  │   test --output│  → ibis/sqlglot → hdbcli/   │
│ quality: │ dc lint  │              │◀───────────────│    sqlalchemy-hana → HANA(RO?)│
└──────────┘ (Ex-G1?) └──────┬───────┘   run.json     └─────────────────────────────┘
                             │  parse run.json (pass/fail je Check)
                             ▼
                      ┌──────────────┐   ┌──────────┐   ┌──────────┐  ┌─────────┐
                      │ result-mapper│──▶│  store   │──▶│   API    │─▶│ Cockpit │
                      │ run.json →   │   │ +compli- │   │ (FastAPI)│  │ (unver- │
                      │ RunSummary   │   │ ance.py  │   │          │  │  ändert)│
                      └──────────────┘   └──────────┘   └──────────┘  └─────────┘
                             ▲
   obs/ · lineage/ · lifecycle · Diff/Breaking  ── bleiben, docken an run.json/YAML an
```

### 2.1 Was **stirbt** (durch die CLI ersetzt)

| Baustein heute | Schicksal | Ersetzt durch |
|---|---|---|
| `contract/validator.py` (G1-Gate) | **entfällt** | `datacontract lint` (ODCS-Spec-Konformität) — semantisch **schwächer**, s. §4 |
| `contract/compiler.py` (Garantie→SQL) | **entfällt** | `datacontract test` kompiliert intern zu ibis→`sqlglot`-SQL |
| `library/check_library.json` (Template-Katalog) | **entfällt als Laufzeitpfad** | `quality.type: library`-Metriken + im YAML geschriebene `type: sql`-Checks |
| `engine/check_engine.py` (HANA-Runner, Batch/Gating) | **entfällt** | `datacontract test` (ibis-Engine) |
| `engine/expectation.py` (Soll-Grammatik `= 0`, `>= 1000`) | **entfällt** | ODCS-Operatoren (`mustBe…`, `unit: percent`) |

### 2.2 Was **bleibt** (CLI kann es konzeptionell nicht)

| Baustein | Warum es bleibt |
|---|---|
| `store/` + `contract/compliance.py` | CLI ist **zustandslos** (run→pass/fail). `compliant↔breached`-Transition, SLA-Fenster, Incident-Timeline gibt es nur hier (A1). |
| `apps/cockpit/` | Status-Grid, Coverage-Map, Workbench, Runs, Incidents, Proposals — kein CLI-Äquivalent. |
| `obs/` (baselines, miner) | Rolling-Baselines + datengetriebene Garantie-Vorschläge. ODCS modelliert keine Laufzeit-Historie. |
| `lineage/` (CSN) | Spalten-Lineage/CSN-Rekonstruktion. |
| Lifecycle/SemVer/Approval, `diff.py`/`gate_g3.py` | Git-als-Wahrheit, Breaking-Schutz (G3). `datacontract breaking` ist hier nur Zweitmeinung. |
| `services/api/` + Auth/OIDC | REST-Fläche, fail-closed OIDC, SSE — die CLI ist kein Server. |

### 2.3 Was **neu** gebaut werden muss (der Preis des Ersatzes)

| Neuer Baustein | Aufgabe | Ersetzt verlorene Garantie |
|---|---|---|
| **read-only/PII-Shim** | erzwingt read-only Technical User + unterdrückt Rohzeilen, *bevor* die CLI läuft | **G8** (PII) + Read-only — die CLI garantiert beides **nicht** |
| **result-mapper** | parst `datacontract test --output run.json` → `RunSummary`/`CheckResult` für den Store | die heute integrierte Engine→Store-Naht |
| **subprocess/runtime-isolation** | CLI als Fremdprozess kapseln, Timeouts, Fehlerklassifikation, Secrets-Handling | `statementTimeout`, `execution_mode`, Batch-Fallback aus `check_engine` |
| **YAML-Bridge** | unser Schema v1 ↔ datacontract.com-Format (oder Vollumstieg auf dc-Format) | Authoring-Pfad + `to_odcs()` |
| **Gating-Reimplementierung** | günstige Gates vor teure Checks; `skipped_stale` sichtbar | **G6** — die CLI/ibis-Engine kennt unser Gating-Modell nicht |

> **Die unbequeme Symmetrie:** Drei Bausteine entfallen (2.1), aber fünf neue
> entstehen (2.3) — und vier davon existieren **nur**, um Garantien
> wiederherzustellen (G1, G6, G8, Read-only), die die native Engine *gratis*
> mitbringt. Der gelöschte Teil kehrt als Security-/Governance-Schicht zurück.

#### Warum der read-only/PII-Shim *strukturell schwächer* ist (nicht nur mehr Arbeit)

Beide Garantien sind nativ **bauartbedingt**; als Shim werden sie zu
**nachgelagerten, extern zu auditierenden** Zusicherungen — beim PII-Gate sogar zu
einer prinzipiell unterlegenen.

- **Read-only — von Architektur zu Konvention.** Nativ gibt es **keinen
  Schreibpfad**: `compiler.py` erzeugt nur SELECT/COUNT aus Library-Templates, G1
  verbietet beliebiges SQL, der HANA-User ist read-only, `statementTimeout` deckelt
  Runaways — drei unabhängige Sperren. Mit der CLI erlaubt `quality.type: sql`
  beliebiges SQL → die *architektonische* „kein Schreibpfad"-Garantie entfällt;
  read-only ist nur noch eine **betriebliche** Zusage (TU-Rechte + Audit des
  generierten SQL), keine Bauart mehr.

- **PII — Prävention statt Nachreinigung.** Das native Gate ist **Default-Deny in
  vier Schichten**: (1) Rohzeilen werden *an der Quelle* nur bei
  `diagnostics_enabled` geholt (Normalfall = nur ein Skalar) + Spalten-Allowlist;
  (2) der Store persistiert sie nur mit `allow_diagnostics`; (3) TTL-Verfall;
  (4) API-Sicht nur für `steward+`. datacontract-cli v1.0.0 hat „bad row"-Diagnostik
  dagegen **ausgebaut** (gegenteiliges Default) und hat weder Store noch Rollen.
  Entscheidend: bis die CLI-Ausgabe existiert, haben die Zeilen **HANA schon
  verlassen** — der Shim kann nur **nachreinigen** (holen, dann strippen), während
  die Engine **präveniert** (nie holen). *Prävention > Nachreinigung* — der Ersatz
  ist nicht bloß teurer, sondern schwächer.

> **Merksatz:** Nativ sind read-only und PII *bauartbedingt* (kein Schreibpfad;
> Rohzeilen werden an der Quelle gar nicht erst geholt). Als Shim werden sie
> *nachgelagert* — und für PII heißt das prinzipiell unterlegen, weil die Daten die
> Quelle bereits verlassen haben.

---

## 3. Datenfluss im Detail — ein Run unter der Hypothese

```
1. Trigger        services/api  POST /objects/{id}/run     (unverändert)
                       │
2. Resolve        Harness lädt contracts/<ds>.dcs.yaml + bindet Server/Schema
                       │                                   (Ex-G2: jetzt in der YAML
                       │                                    'servers:' statt {schema})
3. Guard          ro/PII-Shim:  ── read-only TU prüfen ── PII-Spalten maskieren ──┐
                       │                                                            │ Ex-G8/Read-only
4. Execute        subprocess:  datacontract test contracts/<ds>.dcs.yaml \         │ (NEU, war im
                                 --server hana_prod --output run.json              │  Engine gratis)
                       │            │                                              │
                       │            └─▶ ibis/sqlglot ─▶ hdbcli/sqlalchemy-hana ─▶ HANA ◀┘
                       │
5. Map            result-mapper:  run.json → RunSummary(run_id, results[], …)
                       │           (Verlust: kein 'state=skipped_stale', kein
                       │            HANA-Batch-UNION, kein Diagnostics-Gate-Feld)
                       │
6. Persist        store.save_run(summary)  +  compliance.compute_compliance()   (unverändert)
                       │
7. Surface        API → SSE → Cockpit (Grid/SLA/Incidents)                      (unverändert)
```

**Reibungspunkte gegenüber heute (Schritt 4–5):**

- **Gating (G6)** muss der Harness *außerhalb* der CLI nachbauen: erst die
  Frische-Checks als eigener `datacontract test`-Lauf, dann — nur bei frischen
  Daten — die teuren Checks. Das native `_run_with_gating` (ein Prozess, ein
  Batch) wird zu **mehreren CLI-Aufrufen** mit eigener Orchestrierung.
- **Batch-Effizienz** geht verloren: `check_engine._build_batch_sql` bündelt heute
  ~20 Checks in *ein* `UNION ALL ... FROM DUMMY`. Die ibis-Engine fährt pro
  Metrik/Query; Round-Trips gegen HANA steigen.
- **PII-Diagnostik (G8)** war ein *Feld am Check* (`diagnostics.enabled` +
  Spalten-Allowlist) mit Unterdrückung **an der Quelle**. Mit der CLI gibt es kein
  äquivalentes per-Check-Flag — die Unterdrückung muss vor- und nachgelagert um
  den Fremdprozess herum erzwungen werden (fehleranfälliger).

---

## 4. Der Authoring-/Governance-Bruch (P2/P3)

Heute (SQL-frei, Garantie-zentriert, `contracts/DS_SALES_ORDERS.yaml`):

```yaml
guarantees:
  keys:
    - columns: [ORDER_ID]
      unique: true
  freshness:
    column: ORDER_DATE
    max_age: PT26H
```

Unter der Hypothese (datacontract.com-Format, Quality **in** der YAML):

```yaml
models:
  sales_orders:
    fields:
      ORDER_ID: { type: string, unique: true, primaryKey: true }   # Ebene 1: deklarativ, kein SQL
      ORDER_DATE: { type: timestamp }
servers:
  hana_prod:
    type: hana            # ← die hypothetische neue Engine
    host: ...
    schema: SALES
quality:
  - type: library         # Ebene 2: benannte Metrik + Operator → KEIN SQL
    metric: rowCount
    mustBeGreaterOrEqualTo: 1000
  - type: sql             # Ebene 3: Escape-Hatch → SQL kehrt in den Contract zurück
    query: |
      SELECT SECONDS_BETWEEN(MAX(ORDER_DATE), CURRENT_TIMESTAMP) FROM sales_orders
    mustBeLessThan: 93600
```

**Wichtige Präzisierung (Stand datacontract-cli v1.0.0, 2026-06):** Die CLI
schreibt **nicht** überall SQL. `datacontract test` kompiliert Schema- und
Quality-Checks seit v1.0.0 in **ibis-Ausdrücke** (→ dialekt-korrektes SQL via
`sqlglot`); die frühere **Soda-Core-Engine ist ersetzt**, und **rohe SodaCL-Custom-
Checks (`type: custom`, `engine: soda`) werden nicht mehr ausgeführt** (nur Warnung,
Migration nach `type: sql` *oder* `library`-Metrik empfohlen). Es bleiben **drei**
Ebenen:

| Ebene | Mechanik | SQL im Contract? | Verhältnis zu G1 |
|---|---|---|---|
| 1 — Schema/Model | `type`·`required`·`unique`·`enum`·`pattern` automatisch | **nein** | **kein** Bruch — mappt sauber auf Signal-Garantien |
| 2 — `quality.type: library` | benannte Metrik (`rowCount`, `nullValues`, `unit: percent`) + Operator | **nein** | **kein** Bruch — deklarativ, wie Signals Familien |
| 3 — `quality.type: sql` | inline `query:` + Schwellwert | **ja** | **Bruch** — Roh-SQL im Vertrag |

**Was das kostet:**

1. **G1 fällt nur an Ebene 3 — aber genau dort, wo Signals Wert liegt.** Für
   generische Checks (Ebene 1/2) ist die CLI deklarativ; kein G1-Problem. Der Bruch
   beginnt bei `type: sql`. Und der **deklarative Mittelweg „SodaCL-Template
   schreiben" wurde in v1.0.0 entfernt** — es bleibt library-Metrik (begrenzter
   Katalog) **oder** Roh-SQL. `datacontract lint` prüft **Spec-Konformität**, nicht
   „kein SQL"; ein „No-SQL"-Gate müsste man neu bauen (und entwertete dann Ebene 3).
2. **Determinismus/Diffbarkeit** sinkt für Ebene-3-Checks. Ein library-Check bleibt
   ein Bedeutungs-Diff; ein `type: sql`-Check wird ein SQL-String-Diff —
   `diff.py`/`gate_g3.py` müssten dafür auf SQL-Heuristik umgestellt werden.
3. **SAP/HANA-Semantik wandert zwangsläufig auf Ebene 3.** BSEG-Balance,
   BKPF-Orphan, Fiscal Completeness, `SYS`-Views, Input-Parameter haben **keine**
   `library`-Metrik → landen als `type: sql`. Der ~v4-Katalog aus
   `check_library.json` wird von **einem zentralen, getesteten Template** zu
   **kopiertem SQL pro YAML** — die Differenzierung ist genau der Teil, der nicht
   deklarativ bleibt.
4. **G7 bröckelt.** Der Harness importiert/ruft ein Framework (CLI + ibis/sqlglot).
   `dq_core` bliebe nur frameworkfrei, wenn der CLI-Aufruf strikt in
   `services/`/`signal_harness/` gekapselt wird — `dq_core` verlöre dann aber
   seinen Zweck (Engine/Compiler sind ja weg).

---

## 5. Migrationspfad (falls man es *trotzdem* täte)

Ein verantwortbarer Umstieg wäre **nie** ein Big-Bang, sondern schrittweise mit
Doppelbetrieb:

| Stufe | Schritt | Sicherung |
|---|---|---|
| M0 | HANA-Connector zur CLI beisteuern/abwarten (`type: hana`), read-only ausgelegt | s. Bewertung §10, „Weg 2" |
| M1 | **Advisory-Doppellauf**: CLI parallel zur Engine, Ergebnisse vergleichen (analog `odcs-second-opinion`) | Engine bleibt Produktionspfad; Diskrepanz = Report |
| M2 | result-mapper + read-only/PII-Shim bauen, in den Store schreiben | G5 (Engine-Regression) als Vergleichsnetz |
| M3 | Gating + Diagnostics-Äquivalent im Harness; Cockpit liest CLI-Runs | G6/G8 nachweislich erhalten, sonst Stop |
| M4 | Contract-Format-Bridge (Schema v1 ↔ dc/ODCS); Authoring umstellen | `validate_contract` als Quality-Gate beibehalten, bis Bridge steht |
| M5 | Engine/Compiler/Validator deprecaten — **nur** wenn M1–M4 grün | Rückrollbar bis hier |

**Abbruchkriterien (jede ist allein ausreichend):** Read-only/PII nicht beweisbar
(G8) · Gating/`skipped_stale` nicht reproduzierbar (G6) · SAP-Checks nur als
Roh-SQL realisierbar (G1) · Performance-Regression durch Round-Trips · CLI kann
HANA-Native-SQL nicht ausdrücken.

---

## 6. Bewertung der Soll-Architektur — ehrliche Bilanz

**Was man gewinnt**

- Ein **Standard-Executor** statt Eigenbau-Engine; Ökosystem-Anschluss (Soda/GX-Export,
  dbt-Export, breite Backends).
- `check_engine.py`/`compiler.py`/`library` als Wartungslast entfallen
  (~der „leichteste" 20–30 %-Layer, Bewertung §6).

**Was man verliert oder neu bezahlt**

- **Vier Garantien als Shim zurück**: G1, G6, G8, Read-only (2.3) — der eigentliche
  Aufwand, nicht das `COUNT(*)`-SQL.
- **HANA-Native-Performance** (Batch-UNION) und **SAP-Check-Bibliothek** als
  zentrale, getestete Templates.
- **Determinismus/Diffbarkeit** der Verträge (Bedeutung statt SQL-String).
- **Marketing-Differenzierer** „einzige mit HANA-Runner" (verschenkt an den Markt,
  Bewertung §10 „Commoditize your complement").

**Bleibt unangetastet** (≈70 % von Signal): Store/Compliance/SLA, Cockpit,
Observability, Lineage, Lifecycle, ORD/CSN, Auth. Genau deshalb ersetzt die CLI —
selbst *mit* HANA-Engine — **nicht das Produkt, nur einen Motor**.

---

## 6.5 Ein Executor oder zwei? — die Dual-Engine-Frage

Naheliegender Einwand zum empfohlenen Mittelweg: Wenn **Delta-Tabellen über die
CLI** und **HANA-Objekte über die eigene Engine** geprüft werden — sind das nicht
**zwei Runner**, also genau das in Integration.md §0 verbotene Anti-Pattern? Und
wäre die CLI als *single tool* für alle Ausführung dann nicht ein großer Mehrwert?

**Was der Leitsatz „niemals ein zweiter Check-Runner" wirklich verbietet:**
*dasselbe Objekt* durch zwei Engines laufen zu lassen und **zwei Wahrheiten** auf
identischen Daten zu erzeugen. Der Substrat-Split ist etwas anderes:

```
HANA-Objekt  ──▶ genau EINE Engine (Signal)     ┐
                                                 ├─▶ EIN Store · EIN compliance.py · EIN Cockpit
Delta-Objekt ──▶ genau EINE Engine (CLI)         ┘
```

Jedes Objekt hat **genau einen** maßgeblichen Runner; nichts wird doppelt geprüft.
Das ist „ein Runner *pro Substrat*", nicht „zwei Runner *auf einer Quelle*". Genau
deshalb sagt Bewertung §8, die CLI sei als Executor *nur* in der Databricks-Plane
tragfähig — dort gibt es kein HANA, mit dem sie kollidieren könnte.

**Die entscheidende Frage ist: *was* muss „single" sein?** Der Mehrwert eines
single tool ist **Konsistenz** — die zählt aber **nicht beim Executor**, sondern
eine Ebene höher:

| Schicht | muss einheitlich sein? | im Split? |
|---|---|---|
| Contract-Semantik (Garantien) | **ja** | ✅ eine Quelle |
| Result-/Compliance-Modell | **ja** | ✅ ein Store, ein `compliance.py` |
| Cockpit / Status / SLA | **ja** | ✅ eine Oberfläche |
| **Executor (Binary)** | **nein** | ❌ zwei — *und das ist ok* |

Solange Contract + Result-Modell + Cockpit **eins** sind, ist „zwei Executoren"
kein zweites Tool, sondern **zwei Adapter hinter einer Plattform** (dasselbe
Muster, mit dem die ibis-Engine intern an verschiedene Backends dispatcht). Die CLI ist
dann ein **untergeordneter Executor unter Signals Result-Modell**, kein
gleichrangiges Tool — und diese Unterordnung löst die Anti-Pattern-Sorge auf.

**Warum „CLI als single tool" den Mehrwert nicht gratis bringt:** Damit die CLI
*alles* prüft, müsste sie auch HANA prüfen — also exakt das Hypothese-Szenario aus
§2.3. Der single-tool-Vorteil (eine Mental-Map, ein Skillset, ein Config-Modell)
wird erkauft mit **G1, G8, Read-only und Gating als Shim** zurück, SAP-/HANA-SQL in
jeden Contract kopiert und dem verschenkten Differenzierer. Man tauscht „zwei
saubere Adapter" gegen „ein Tool + vier Shims, die genau die gratis verlorenen
Garantien rekonstruieren".

**Die ehrlichen Kosten des Splits** (umsonst ist er nicht):

| Kosten | Reales Risiko | Gegenmittel |
|---|---|---|
| Zwei Codepfade (HANA-Engine + CLI-Harness + result-mapper) | Wartungs-/Testlast verdoppelt | gemeinsamer Result-Mapper-Vertrag; ein Schema für `RunSummary` |
| **Semantik-Drift** — `unique: true` (Compiler) ≠ ibis-Duplicate-Check der CLI? | faktisch doch *zwei Wahrheiten*, nur auf verschiedenen Objekten | **Autorität „Garantie → Check-Definition" bleibt in *einer* Spezifikation** (Library/Mapping); CLI führt nur aus, definiert nicht |
| Zwei Failure-Modes, zwei Config-Welten (hdbcli vs. databricks/duckdb) | Betriebskomplexität | klare Plane-Zuordnung pro Objekt im Inventar; eine Trigger-API |
| Zwei Performance-Profile (Batch-UNION vs. ibis-Round-Trips pro Metrik) | inkonsistente Laufzeiten | Erwartung pro Plane dokumentieren, nicht angleichen wollen |

**Wann single tool *doch* gewinnt:** Es ist eine **Portfolio-Frage**. Ist die
Flotte überwiegend Delta/BDC und HANA marginal, kann die operative Einfachheit
*eines* Executors den Verlust der HANA-Native-Kante überwiegen. Ist HANA der Kern
(heute der Fall), gewinnt der Split — weil der einzige Weg zum single tool über die
HANA-Shim-Steuer (§2.3) führt.

> **Merksatz:** Zwei Executoren hinter *einem* Contract-/Result-/Cockpit-Modell
> sind kein Anti-Pattern, sondern „richtiges Werkzeug pro Substrat". Das
> Anti-Pattern wäre erst zwei *Wahrheiten*. Der single-tool-Mehrwert ist real,
> kostet auf der HANA-Seite aber genau die Governance-Garantien, die Signals Pitch
> ausmachen.

---

## 6.6 Und wenn Signal selbst Delta/HDLF prüfen will?

Folgefrage: Soll Signal später auch Objekte im **HDLF-Space** (Tabellen im
**Delta-Format**) prüfen — müssten dann nicht dieselben Garantien (read-only, PII,
G1, Gating) **auch dort neu gebaut** werden? Kurz: teils ja, teils nein — und die
Antwort verschiebt die §6.5-Empfehlung.

### Zwei Klassen von Garantien — nur eine ist executor-nah

| Garantie | Ebene | Für Delta neu? |
|---|---|---|
| Result-/Compliance-Modell (`store/`, `compliance.py`) | **Plattform** (substrat-agnostisch) | **nein** — wiederverwendet |
| Cockpit · SLA · Incidents · Lineage · Lifecycle | **Plattform** | **nein** |
| **G1** (kein SQL im Contract) | **Authoring-Gate** (`validator.py`) | **nein** — gilt für die YAML, *egal wo* sie läuft |
| **Read-only** auf die Delta-Quelle | **Executor** (pro Pfad) | **ja** |
| **PII-Gate (G8)** auf Delta-Rohzeilen | **Executor** | **ja** |
| **Gating/`skipped_stale` (G6)** | **Executor** | **ja** — oder wiederverwendbar (s. Option B) |

Der Großteil dessen, was Signal ausmacht, ist **substrat-agnostisch** und wird
mitbenutzt. Neu ist nur die **executor-nahe** Schicht — genau das, was §2.3 „Shim"
nennt.

### Warum das *nicht* derselbe Verlust ist wie der HANA-Voll-Ersatz

Beim HANA-Voll-Ersatz (dieses Doc) reißt man eine *funktionierende native* Engine
heraus und baut ihre Garantien als Shim wieder auf — **reiner Verlust**, um wieder
dort zu landen, wo man war. Bei Delta/HDLF gibt es **noch keine** Signal-Engine
(Signals Engine ist HANA-only via `hdbcli`). Man ersetzt nichts, man erschließt
**Neuland** — die Executor-Garantien sind **netto-neue Arbeit für netto-neuen
Scope**, kein Wiederaufbau.

### Die zwei realen Optionen für Delta

Weil read-only + PII + Gating für den Delta-Pfad **so oder so** anfallen, schrumpft
der Vorteil der CLI — es bleiben zwei echte Wege:

| | **Option A — CLI als Delta-Executor** (Bewertung §8) | **Option B — eigene Engine auf Delta erweitern** |
|---|---|---|
| Neu zu bauen | read-only/PII-Shim · result-mapper · Gating-Orchestrierung *um* den Fremdprozess | DuckDB/ibis-Connector in `connect/` · Delta-Dialekt der SQL-Templates |
| Wiederverwendet | store/compliance/cockpit/G1-Authoring | **alles oben + read-only/PII/Gating nativ** (`check_engine` ist verbindungs-agnostisch) |
| Gespart | CLI bringt Delta-Connectoren fertig (`[duckdb]`/`[databricks]`) inkl. Dialekt | kein Fremdprozess, kein Mapper, **eine** Engine |
| Kostet | Fremdprozess · zweite Engine · Dual-Engine-Risiko (§6.5) | Connector + Template-Transpile (ironischerweise via demselben `sqlglot`) |
| Nebenwirkung | zwei Executoren (vgl. §6.5) | **kollabiert den Dual-Engine-Split** — eine Engine für HANA *und* Delta, kein G7-Bruch |

**Der eigentliche Tausch:** A spart den **Connector** (Delta-Lesen + Dialekt sind
geschenkt), zahlt aber Shim + Mapper + Fremdprozess + zweite Engine. B spart
**Shim/Mapper/Fremdprozess** (alles nativ wiederverwendet), zahlt aber Connector +
Template-Dialekt selbst. Weil Signal Compiler + Engine + Gating **schon hat**, sind
Option B's Mehrkosten realistisch *nur* „ein DuckDB/ibis-Adapter + `sqlglot`-Transpile
der HANA-Templates" — möglicherweise **billiger als A** *und* sauberer.

> **Konstante über beide Optionen:** G1 bleibt nur erhalten, wenn Signals
> **SQL-freies Schema die Quelle der Wahrheit** bleibt und daraus kompiliert wird —
> **nicht**, wenn das CLI-`quality: type:sql`-Format als Autorenformat übernommen
> wird. *Der Executor darf wechseln, das Vertragsformat nicht.*

**Fazit §6.6:** Die *Executor*-Garantien (read-only/PII/Gating) müssen für Delta
bereitstehen — die *Plattform*-Garantien (Compliance/Cockpit/G1-Authoring) **nicht**
neu gebaut werden. Und weil die Executor-Garantien ohnehin anfallen, ist das das
stärkste Argument, Delta **nicht** über die CLI, sondern über eine
**DuckDB/ibis-Erweiterung der eigenen Engine** (Option B) zu fahren — was nebenbei
die Zwei-Engine-Frage aus §6.5 auflöst.

---

## 7. Fazit

Unter P1–P3 ist der volle Ersatz **technisch konstruierbar** (§2–§3), aber er
tauscht *einen* gelöschten Baustein (die Engine) gegen *fünf* neue (§2.3), von
denen vier nur verlorene Sicherheits-/Governance-Garantien rekonstruieren. Die
Architektur wird **größer und schwächer**: mehr bewegliche Teile (Fremdprozess,
Mapper, Shims), weniger harte Garantien (G1 weg, G6/G8 nur noch „best effort").

→ Konsistent mit Bewertung §6/§10 lautet die Empfehlung: **nicht voll ersetzen.**
Falls der HANA-Connector je existiert, ist sein Platz der **Advisory-Executor**
(M1, Doppellauf) — nicht der Produktionspfad. Dieses Dokument liefert das Soll-Bild,
um genau diese Grenze im Schaubild sichtbar zu machen: *Motor austauschbar, Auto
nicht.*

---

## 8. Anker-Referenzen

| Baustein | Datei |
|---|---|
| Nativer Runner (entfiele) | `packages/dq_core/engine/check_engine.py` |
| Compiler / einziger SQL-Erzeuger (entfiele) | `packages/dq_core/contract/compiler.py` |
| Validator / G1-Gate (entfiele) | `packages/dq_core/contract/validator.py` |
| Check-Bibliothek (entfiele als Laufzeitpfad) | `packages/dq_core/library/check_library.json` |
| Compliance-Zustand (bliebe) | `packages/dq_core/contract/compliance.py` |
| ODCS-Export / Format-Brücke | `packages/dq_core/contract/odcs_export.py` |
| Breaking-Diff / G3 (bliebe) | `packages/dq_core/contract/diff.py` · `gate_g3.py` |
| Begründung „nicht ersetzen" | `docs/datacontract-cli_Bewertung.md` §6, §10 |
| Feature-Landkarte | `docs/datacontract-cli_Integration.md` |
</content>
</invoke>
