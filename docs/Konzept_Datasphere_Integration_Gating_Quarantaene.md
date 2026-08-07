# Konzept — Integration von Signal-Ausführung, Gating & Quarantäne in Datasphere-Pipelines

**Adressat:** Plattform-Team, Beratung, Governance · **Stand:** 2026-07-11
**Status:** Implementiert — Slices ①–⑦ (Enforcement-Achse, API-Task-Vertrag,
Verdict-Materialisierung, Split-Artefakte Variante A + Reconciler mit
Drift-Erkennung, episodische Quarantäne inkl. Episoden-Spiegel/Release-View/TTL,
SQL-Bridge, Outbound-Trigger) sowie Aktivierungs-Werkzeuge: Capability-Probe
(Rest-O5/O6, `/api/enforcement/probe|capabilities`), Quarantäne-Policy
(`quarantine.style` + `auto_release_after_green_runs`), `on_load`-Schedule-Modus
(AP-5) und das Enforcement-Panel im Cockpit. Slices ④–⑦ sind hinter Opt-ins
dormant (`ENFORCEMENT_MATERIALIZE_ENABLED`, `ENFORCEMENT_SQL_BRIDGE_ENABLED`,
`DATASPHERE_ALLOW_TRIGGER`, alle Default aus) — die **Aktivierung** am Tenant
bleibt durch die Rest-Spikes gegated (Spike-Kit + O10-Dossier liegen bereit:
`docs/spikes/Spike_Kit_Enforcement_Aktivierung.md`,
`docs/O10_Datenschutz_Review_Custody_Zone.md`).
**Branch:** `claude/signals-datasphere-integration-n8726p`
**Zweck:** Festlegen, wie Signal-Läufe, Gating und Quarantäne in **bestehende**
Datasphere-Pipelines eingebettet werden — Task Chains, Transformation Flows und
HANA-/SQLScript-Prozeduren — unter einer **neuen Prämisse**: Signal darf in
seinem **eigenen Open-SQL-Schema Objekte anlegen** (Tabellen, Views,
Prozeduren). Die bisherige Auslagerung an ein externes Reconcile-Skript entfällt
dort, wo Signal die Artefakte selbst materialisieren kann.

> Verwandte Dokumente:
> `Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md` (Enforcement-Achse,
> Verdict-Regel, Layer-Slice — bleibt Grundlage) ·
> `REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md` (API-Tasks,
> Episoden-Lifecycle, Fähigkeits-Matrix) ·
> `HANDOVER_Observability_Quarantaene_Orchestrierung.md` (AP-1…AP-9) ·
> `ADR-0002_Datasphere-DB-Zugriff.md` (Identität — wird durch §2 amendiert) ·
> `ADR-0005_Scheduling.md` (Poller, `external`-Modus).

---

## 0 — Kernaussage

Bisher galt: *„Signal entscheidet, Datasphere handelt"* — Signal ist strikt
read-only, jede Materialisierung (Split-Views, Quarantäne-Tabellen) macht ein
externes, privilegiertes Reconcile-Skript nach Manifest. Mit Schreibrecht im
**eigenen** Open-SQL-Schema wird daraus:

> **Signal entscheidet *und* materialisiert sein Urteil als SQL-Oberfläche im
> eigenen Schema. Datasphere konsumiert diese Oberfläche nativ — per
> Prozedur-Schritt, per View-Quelle oder per API-Task. Kundendaten bleiben
> unberührt: Signal schreibt niemals außerhalb seines Schemas.**

Damit werden vier Objektklassen im Signal-Schema zum Integrationsvertrag:

| # | Objektklasse | Zweck | Konsument |
|---|---|---|---|
| 1 | **Verdict-Tabellen** | Gate-Zustand je Objekt/Lauf, SQL-lesbar | Prozeduren, Chains, Ad-hoc-SQL |
| 2 | **Gate-Prozeduren** | `CALL` → Erfolg oder `SIGNAL_SQL_ERROR` (fail-closed) | Task-Chain-Prozedur-Schritt, Kunden-SQLScript |
| 3 | **Split-Artefakte** | `DQ_CLEAN_<OBJ>` (Tabelle je Lauf, empfohlen) oder `V_…_CLEAN`/`V_…_QUARANTINE` (Views) — kontinuierliche Zeilen-Quarantäne | Transformation Flows (Import + Sharing), Views, Chains |
| 4 | **Quarantäne-Tabellen** | episodisches Zeilen-Parken mit Lifecycle & Freigabe | Steward (Cockpit), Re-Load-Flow des Kunden |

**Die harte Grenze (nicht verhandelbar):** Signal schreibt **ausschließlich in
sein eigenes Open-SQL-Schema**. Das Zurückführen freigegebener Zeilen in
Staging/Ziele ist immer ein Kunden-Flow, der aus Signals Release-View **liest**.
Signal parkt und reicht zurück — es schiebt nie.

---

## 1 — Einordnung: was dieses Konzept voraussetzt und was es ersetzt

**Vorausgesetzt (wird referenziert, nicht neu entworfen):**

- Die **Enforcement-Achse** `enforcement_mode ∈ {gate, quarantine, monitor}`
  mit `gate_verdict ∈ {proceed, quarantine, block}` auf `RunSummary`,
  Verdict-Regel und Layer-1/2-Slice aus `Konzept_Enforcement_Modi_*` §4.
  Default bleibt `monitor` — keine heute grüne Pipeline wird zum
  Überraschungs-Stopp.
- Der **API-Task-Vertrag** (AP-1): `POST` → `202 Accepted` +
  `Location: /api/runs/{run_id}/status`, Status-Endpoint mit
  RUNNING/COMPLETED/FAILED-Semantik.
- Die **CLI-Exit-Codes** `0/1/3` + `--no-enforce` (AP-2) für
  Nicht-DSP-Orchestratoren (Airflow, Cron, CI).

**Ersetzt/überholt durch dieses Konzept:**

| Bisherige Aussage | Neu |
|---|---|
| Split-Views legt ein externes Reconcile-Skript nach Manifest an (`Konzept_Enforcement_Modi_*` §2 B1) | Signal materialisiert Split-Views **selbst** (§4); das Manifest-Muster wandert nach innen (Soll-Zustand → Reconciler in Signal, §7) |
| Quarantäne-Zeilen leben ausschließlich in Datasphere-Views | Zusätzlich: **episodische** Quarantäne als physische Tabellen im Signal-Schema (§5) |
| Rückkanal: Skript meldet Counts + `applied_manifest_hash` | Entfällt für Signal-materialisierte Artefakte — Signal kennt seine Counts selbst; `manifest_hash`/Generation bleiben als interne Idempotenz-Anker |
| ADR-0002: Verbindungsidentität ist strikt SELECT-only | Amendment §2: read-only gegenüber Kundendaten, **Schreiben nur im eigenen Schema** |

Der externe Reconcile-Pfad bleibt als **Fallback dokumentiert** für Tenants,
die Signals Schreibrecht im Open-SQL-Schema organisatorisch nicht freigeben —
das Manifest-API aus dem Monitoring-Share-Hub-Muster ist dafür weiterhin die
Schnittstelle.

---

## 2 — ADR-0002-Amendment: Identität & Vertrauensmodell

**Entscheidung:** Signal verbindet weiterhin über den **einen technischen
Open-SQL-Space-User**. Dessen Schreibrechte im eigenen Open-SQL-Schema sind
inhärent (Schema-Owner) — es wird **kein zusätzliches HANA-Privileg** benötigt
und **kein zweiter Writer-User** angelegt (doppelte Rotations-Oberfläche ohne
echten Isolationsgewinn).

Die Invariante aus ADR-0002 wird präzisiert:

> **Read-only gegenüber Kundendaten; Schreiben ausschließlich innerhalb des
> Signal-eigenen Open-SQL-Schemas.**

Das ist enger prüfbar als „read-only": ein User, ein beschreibbares Schema,
klare Audit-Linie. Alles Weitere aus ADR-0002 bleibt unverändert (kein
Database Analysis User, TLS-Pflicht, Secret-Handling, Hub-Topologie §7).

**Vertrauensmodell der Gate-Objekte:**

- **Nur Signals User schreibt** Verdict-Tabellen, Registry und
  Quarantäne-Tabellen. Pipeline-User erhalten per `GRANT` ausschließlich
  `SELECT` (Views, Verdict-Lesesicht) bzw. `EXECUTE` (Gate-Prozeduren).
  Verdicts sind damit nicht fälschbar durch Pipeline-Identitäten.
- Gate-Prozeduren laufen mit **`SQL SECURITY DEFINER`**: der Aufrufer braucht
  kein direktes Leserecht auf die Verdict-Tabelle — die Prozedur ist die
  einzige Tür.
- Die Ausnahme von „nur Signal schreibt": `P_DQ_REQUEST_RUN` (§6.3) fügt im
  Auftrag des Aufrufers eine Zeile in `DQ_RUN_REQUESTS` ein — ebenfalls über
  eine `DEFINER`-Prozedur, nie per direktem `INSERT`-Grant.

**Spike O5 — geschrumpft (Tenant-Erkenntnis 2026-07-11):** Tabellen aus dem
Open-SQL-Schema sind als Space-Entität importierbar (Entität zeigt **live**
auf die hdbtable) und per Standard-Sharing space-übergreifend nutzbar — der
Flow-/Sharing-Konsumpfad ist damit **ohne Grants und ohne zweiten DB-User
bestätigt**. Als Rest-O5 zu verifizieren bleiben nur: (a) haben **Views**
denselben Import-/Sharing-Pfad (relevant nur für Split-Variante B, §5.1) und
(b) `EXECUTE`-Grant an fremde DB-User für `P_DQ_ASSERT_GATE` (relevant nur
für Rezept R-D, wenn Kunden-Prozeduren unter anderer Identität laufen).
Ergebnis als Capability-Probe im Connector persistieren (analog O2).

---

## 3 — Objektklasse 1: Verdict-Tabellen

Der Gate-Zustand wird nach jedem Lauf **zusätzlich zum Result-Store** in das
Open-SQL-Schema geschrieben — als SQL-lesbare Wahrheit für Prozeduren und
Chains, ohne HTTP.

```sql
-- Aktueller Zustand je Objekt (Upsert durch Signal nach jedem Lauf)
CREATE TABLE DQ_GATE_STATUS (
  OBJECT_ID         NVARCHAR(256) PRIMARY KEY,  -- Inventar-ID des Prüfobjekts
  CONTRACT_ID       NVARCHAR(128),
  CONTRACT_VERSION  NVARCHAR(32),
  RUN_ID            NVARCHAR(64)  NOT NULL,
  GATE_VERDICT      NVARCHAR(16)  NOT NULL,     -- proceed | quarantine | block
  OVERALL_STATUS    NVARCHAR(8)   NOT NULL,     -- pass | warn | fail | critical
  MANIFEST_HASH     NVARCHAR(64),               -- Prädikat+Version+Objekt (§7)
  GENERATION        INTEGER,
  EVALUATED_AT      TIMESTAMP     NOT NULL,
  EXPIRES_AT        TIMESTAMP                    -- optionales Verfallsdatum
);

-- Append-only-Historie (Audit, Trend, Debugging der Gate-Entscheidungen)
CREATE TABLE DQ_GATE_STATUS_HISTORY ( … gleiche Spalten + SEQ … );
```

Regeln:

- **Signal ist einziger Schreiber** (Upsert im Lauf-Abschluss, Service-Layer).
- Konsumenten lesen nie die Tabelle direkt, sondern die Prozedur (§4) oder die
  Lesesicht `V_DQ_GATE_STATUS` — so bleibt das Spaltenlayout evolvierbar.
- `EXPIRES_AT` erlaubt fail-closed per Zeitablauf: ein Verdict, dessen
  Gültigkeit abgelaufen ist, zählt wie „kein Verdict" (§4). Damit ist die
  Staleness-Politik auch dann wirksam, wenn der Aufrufer keine `max_age`
  übergibt.
- Der Result-Store (SQLite/HANA `dq_results_lt`) bleibt die **primäre**
  Persistenz; `DQ_GATE_STATUS` ist eine **projizierte Konsum-Oberfläche**.
  Divergenz ⇒ Result-Store gewinnt, Reconciler (§7) schreibt nach.

---

## 4 — Objektklasse 2: Gate-Prozeduren

Die Prozeduren machen HANA-Prozedur-Pipelines und Task-Chain-Prozedur-Schritte
zu erstklassigen Integrationsflächen: **`CALL` → kommt zurück oder wirft.**
Eine geworfene `SIGNAL_SQL_ERROR` lässt den Prozedur-Schritt der Chain
fehlschlagen — die Chain stoppt; in Kunden-SQLScript propagiert der Fehler wie
jeder SQL-Fehler (bzw. wird per `EXIT HANDLER` gezielt behandelt).

### 4.1 `P_DQ_ASSERT_GATE` — Verdict lesen, fail-closed prüfen

```sql
CREATE OR REPLACE PROCEDURE P_DQ_ASSERT_GATE (
  IN in_object_id       NVARCHAR(256),
  IN in_max_age_seconds INTEGER       DEFAULT 3600,
  IN in_min_evaluated_after TIMESTAMP DEFAULT NULL,  -- z. B. Load-Startzeit der Chain
  IN in_fail_on         NVARCHAR(32)  DEFAULT 'block_and_quarantine'
) LANGUAGE SQLSCRIPT SQL SECURITY DEFINER READS SQL DATA AS
BEGIN
  -- Pseudocode der Regel (Implementierung generiert Signal deterministisch):
  -- 1. kein Verdict für OBJECT_ID            → SIGNAL_SQL_ERROR 10050 (fail-closed)
  -- 2. EVALUATED_AT älter als max_age
  --    oder < in_min_evaluated_after
  --    oder EXPIRES_AT überschritten          → 10051  "Verdict veraltet"
  -- 3. GATE_VERDICT = 'block'                 → 10052  "Gate: block"
  -- 4. GATE_VERDICT = 'quarantine'
  --    und in_fail_on = 'block_and_quarantine'→ 10053  "Gate: quarantine"
  -- 5. sonst                                  → return (Gate offen)
END;
```

**Semantik-Entscheidungen:**

- **Fail-closed ist Default.** Fehlendes oder veraltetes Verdict blockiert.
  Wer „weich" gaten will, nutzt `monitor`-Enforcement im Contract — nicht
  einen laxen Gate-Aufruf.
- **`in_fail_on` koppelt Gate und Quarantäne-Semantik:** Eine Pipeline, die
  ohnehin aus `V_…_CLEAN` liest (kontinuierliche Quarantäne, §5.1), setzt
  `in_fail_on='block'` — ein `quarantine`-Verdict stoppt sie nicht, denn die
  Isolation trägt bereits die View. Eine Pipeline auf dem Rohobjekt lässt den
  Default stehen. Damit ist das Drei-Wege-Verdict trotz binärer
  Schritt-Semantik vollständig abgebildet.
- **`in_min_evaluated_after`** bindet das Verdict an den konkreten Load: die
  Chain übergibt ihre Load-Startzeit; ein Verdict von *vor* dem Load gilt als
  veraltet. Das ist der präziseste Staleness-Schutz und dem reinen
  `max_age` vorzuziehen, wo verfügbar.

**Fehlercode-Vertrag** (stabil, dokumentiert, spiegelt die CLI-Exit-Codes):

| Code | Bedeutung | CLI-Analogon |
|---|---|---|
| `10050` | kein Verdict vorhanden (fail-closed) | — |
| `10051` | Verdict veraltet / abgelaufen | — |
| `10052` | Verdict `block` | Exit 1 |
| `10053` | Verdict `quarantine` (bei `block_and_quarantine`) | Exit 3 |
| `10054` | Timeout beim Warten auf angeforderten Lauf (§6.3) | — |
| `10055` | angeforderter Lauf endete mit `error` | — |

### 4.2 `P_DQ_REQUEST_RUN` / `P_DQ_GATE` — siehe §6.3 (Trigger-Bridge)

---

## 5 — Objektklassen 3 & 4: die zwei Quarantäne-Semantiken

Beide Semantiken existieren nebeneinander und werden **pro Contract/Garantie**
gewählt; sie teilen sich das Prädikat (`WHERE <bad>`), das die Engine bereits
als `_diagnostic_sql` erzeugt (`check_engine.py`) — G1 bleibt intakt, SQL
entsteht nur im Compiler/Generator.

### 5.1 Kontinuierliche Quarantäne — Split-Artefakte (Klasse 3)

> **Update 2026-07-11 — Tenant-Erkenntnis eingearbeitet.** Tabellen aus dem
> Open-SQL-Schema sind als Space-Entität importierbar (zeigen **live** auf die
> hdbtable) und per Standard-Sharing in andere Spaces reichbar — der
> Flow-/Sharing-Konsumpfad braucht **keine** DB-Grants und keinen zweiten
> DB-User. Deshalb ist die empfohlene Default-Form jetzt die **materialisierte
> CLEAN-Tabelle** (Variante A); die ursprüngliche Prädikat-View bleibt als
> Variante B erhalten.

**Variante A (empfohlen): materialisierte CLEAN-Tabelle, Refresh je Lauf.**
Signal schreibt im selben Post-Run-Schritt, der das Verdict publiziert
(§Prozess C), den bereinigten Bestand in eine Tabelle im eigenen Schema:

```sql
-- je Lauf, atomar (DELETE+INSERT in einer Transaktion bzw. Staging-Swap):
DELETE FROM "<signal_schema>"."DQ_CLEAN_<OBJ>";
INSERT INTO "<signal_schema>"."DQ_CLEAN_<OBJ>"
  SELECT <explizite Spaltenprojektion aus Inventar/CSN>
  FROM   "<gebundenes_schema>"."<objekt>"
  WHERE  NOT ( <bad_1> OR <bad_2> OR … );      -- OR-Vereinigung aller Quarantäne-Prädikate
```

- **Konsum (bestätigt):** Tabelle einmal in den Space importieren (Entität
  zeigt auf die hdbtable) → als Quelle in Transformation Flows nutzen → per
  Sharing in Konsumenten-Spaces reichen. Keine Grants, kein zweiter User.
- **Konsistenz-Gewinn:** der CLEAN-Bestand ist **punktgenau konsistent zum
  Verdict**, das ihn validiert hat — kein Drift zwischen Prüfung und Lesen.
  Das Prädikat läuft einmal je Lauf statt je Lesen (O7 entfällt für A).
- **Trade-offs, ehrlich:** (a) Frische zwischen Läufen — upstream geheilte
  Zeilen kehren erst mit dem nächsten Lauf zurück; der `on_load`-Trigger
  (AP-5) hält die Lücke klein. (b) Schreib-/Speicherkosten einer Kopie des
  guten Bestands je Lauf — bei sehr großen Objekten Größen-Schwelle als
  Setting (darüber Variante B oder nur Objekt-Gate B2).

**Variante B (Option): Prädikat-Views** (`V_DQ_<OBJ>_CLEAN` /
`V_DQ_<OBJ>_QUARANTINE`, `WHERE NOT(<bad>)` bzw. `WHERE <bad>`) — immer
aktuell, keine Kopie, selbstheilend beim Upstream-Fix. Setzt voraus, dass
Views aus dem Open-SQL-Schema denselben Import-/Sharing-Pfad haben wie
Tabellen (**O5-Rest**) und die Prädikat-Kosten je Lesen tragbar sind
(**O7 — nur für B relevant**; `keys`/`referential` erzeugen
Fenster-/`NOT EXISTS`-Formen).

Für beide Varianten gilt:

- **Explizite Spaltenprojektion, kein `SELECT *`** (wie Hub-Views,
  ADR-0002 §7) — Schema-Drift bleibt sichtbar.
- **Fähigkeits-Matrix** (aus Review §3.3, unverändert gültig): zeilenbasiert
  nur für `not_null`, `completeness`, `keys`, `referential` sowie zeilenweise
  formulierbare `distribution`/`aggregate`-Garantien. `freshness`, `volume`,
  `schema` sind Objekt-Eigenschaften → niemals Teil des Split-Prädikats,
  sie wirken über das Objekt-Gate (§4/§6).
- **Ehrlichkeits-Grenze:** das CLEAN-Artefakt schützt nur Konsumenten, die es
  auch benutzen. Es ersetzt kein Gate — Empfehlung ist Gate **und**
  Split-Artefakt (Belt-and-Suspenders): Gate stoppt bei `block`, das Artefakt
  filtert bei `quarantine`.

**Anti-Pattern (im Doc-Sinne verboten):** eine „gated View", die bei
`block`-Verdict **0 Zeilen** liefert. Das ist stiller Datenverlust — ein
leerer Load sieht aus wie ein leerer Quelltag. Blockieren dürfen nur
Mechanismen, die **laut** fehlschlagen (Prozedur, API-Task, Exit-Code).

### 5.2 Episodische Quarantäne — physische Tabellen (Klasse 4)

Für Garantien, die ein **auditierbares Parken** mit Steward-Freigabe brauchen,
schnappschusst Signal die schlechten Zeilen **selbst** (das externe
Reconcile-Skript entfällt):

```
Lauf endet, gate_verdict = quarantine
  └─ Signal (Service-Layer, eigene Schreib-Connection):
       1. Episode öffnen (Store) — Lifecycle wie Review §3.3
       2. INSERT INTO DQ_Q_<OBJ> (EPISODE_ID, RUN_ID, GENERATION, QUARANTINED_AT, <payload…>)
          SELECT :episode, :run, :gen, CURRENT_TIMESTAMP, <spalten>
          FROM   "<schema>"."<objekt>" WHERE <bad>
          — idempotent je (EPISODE_ID, GENERATION): NOT-EXISTS-Guard, zweimal anwenden = No-Op
       3. Counts aus dem eigenen INSERT → Episode sofort `reconciled`
          (der frühere Rückkanal des Skripts ist internalisiert)
```

- **Lifecycle:** `open → reconciled → released → resolved`
  (+ `superseded` bei Contract-/Prädikatswechsel, + `resolved(reason=expired)`
  bei TTL-Ablauf). Auto-Release nach N grünen Läufen bleibt Policy je
  Contract, Default **aus** (Self-Healing-Leiter L4).
- **Freigabe & Rückführung:** Steward gibt im Cockpit frei
  (`released`, rollen-gegated `steward+`). Freigegebene Zeilen erscheinen in
  der **Release-View** `V_DQ_<OBJ>_RELEASED`; der **Kunden-Flow** liest sie
  und lädt sie in sein Ziel zurück (harte Grenze §0 — Signal schiebt nie).
  Anschließend bestätigt der Flow per `CALL P_DQ_CONFIRM_REPROCESS(:episode)`
  (oder der Steward im Cockpit) → Episode `resolved`, Zeilen fallen aus der
  Release-View.
- **Datenhoheit & Retention:** Klasse-4-Tabellen enthalten **vollständige
  Rohzeilen inkl. potenzieller PII** — bewusst, denn nur vollständige Zeilen
  sind rückführbar. Konsequenzen:
  - Die Zeilen **verlassen HANA nie** (Buchstabe von G8 gewahrt); das Cockpit
    zeigt sie ausschließlich über den bestehenden, gegateten Diagnostics-Pfad
    (`diagnostics_enabled` + Spalten-Allowlist).
  - **Retention/TTL ist Pflichtfeld** der Quarantäne-Policy je Contract
    (Default z. B. 30 Tage). Ein Housekeeping-Job purgt abgelaufene Zeilen
    und schließt die Episode als `resolved(expired)` — explizit, nie still
    (G6-Disziplin).
  - Das Signal-Schema wird damit formal zur **Data-Custody-Zone**: eigener
    Abschnitt in der Betriebsdoku (wer darf Grants, wie lange liegen Daten,
    Löschkonzept).
- **Ausnahme vom Reconciler-Drop (§7):** Quarantäne-Tabellen werden **nie**
  durch Desired-State-Abgleich gedroppt — sie verwaisen nicht, sie **laufen
  ab** (TTL) oder werden per Freigabe geleert.

### 5.3 Wahl der Semantik

| Kriterium | Kontinuierlich (Split-Artefakt) | Episodisch (Tabellen) |
|---|---|---|
| Audit-Trail „was war wann geparkt" | ✗ | ✓ |
| Freigabe-Workflow / Vier-Augen | ✗ (implizit) | ✓ |
| Selbstheilend bei Upstream-Fix | ✓ (A: nächster Lauf · B: sofort) | ✗ (Freigabe nötig) |
| Kosten | A: Kopie je Lauf · B: Prädikat je Lesen | Kopie + Speicher + TTL-Jobs |
| Rückführung kompletter Zeilen | n/a (nie kopiert) | ✓ Release-View |
| Default-Empfehlung | Standard für Flows | für regulierte/auditpflichtige Objekte |

Konfiguriert wird die Semantik am Contract (`quarantine.style:
continuous | episodic | both`), **Default `both`** — die episodische Hälfte
trägt die Freigabe-/Rückführungs-Story (und später Healing); wer nur
kontinuierlich isolieren will, stellt bewusst um. Ergänzend:
`quarantine.auto_release_after_green_runs: N` (Default aus) gibt Episoden
nach N durchgängig grünen Läufen automatisch frei (Self-Healing L4).

---

## 6 — Ausführungs- & Trigger-Topologie

Drei Pfade bringen ein frisches Verdict in `DQ_GATE_STATUS`; welcher passt,
hängt vom Orchestrator ab:

| Orchestrator | Empfohlener Pfad |
|---|---|
| Task Chain, HTTP-Connection erlaubt | **API-Task** (async) → danach optional Prozedur-Gate |
| Task Chain ohne HTTP-Freigabe | Prozedur-Schritt mit **`P_DQ_GATE`** (Trigger-Bridge) |
| Transformation Flow (alleinstehend) | `on_load`-Trigger (AP-5) + CLEAN-View als Quelle |
| HANA-/SQLScript-Prozedur-Pipeline | `CALL P_DQ_GATE` (frisch) oder `P_DQ_ASSERT_GATE` (Verdict-Read) |
| Airflow / Cron / CI | CLI mit Exit-Codes 0/1/3 (AP-2) |

### 6.1 API-Task (Standard für Task Chains)

Unverändert AP-1; hier nur die Verdict-Abbildung präzisiert:

- Status-Endpoint mappt `proceed` → COMPLETED, `block` → FAILED.
- `quarantine` ist **konfigurierbar je Run-Anforderung**
  (`fail_on=block | block_and_quarantine`, Default fail-closed
  `block_and_quarantine`) — dieselbe Semantik wie `in_fail_on` der Prozedur
  (§4.1). Chains, deren Folge-Schritte aus `V_…_CLEAN` lesen, setzen
  `fail_on=block` und laufen bei Quarantäne weiter.
- Drei-Wege-Verzweigung trotz binärem Task: Variante A — zwei Chains
  (Promote-Chain gated mit `block_and_quarantine`; Quarantine-Chain wird von
  Signal outbound getriggert, R4, opt-in `DATASPHERE_ALLOW_TRIGGER`).
  Variante B — eine Chain mit `fail_on=block` + CLEAN-View-Konsum.

### 6.2 SQL-nativer Verdict-Read (Muster a — sicherer Kern)

```
Task Chain:  [Load → Staging] → [API-Task: Signal-Lauf]
                              → [Prozedur-Schritt: CALL P_DQ_ASSERT_GATE('<obj>',
                                     in_min_evaluated_after => <load_start>)]
                              → [Promote / Folge-Flows]
```

Kein neues Ausführungs-Machinery; die Prozedur prüft nur, **fail-closed**.
Sinnvoll auch als zweites Netz *nach* einem API-Task-Gate (der API-Task kann
COMPLETED sein, während ein späterer Schritt auf ein anderes Objekt gaten
will).

### 6.3 SQL-Trigger-Bridge (Muster b — voller Loop ohne HTTP, Opt-in)

Für Chains ohne HTTP-Connection-Freigabe und für **reine
SQLScript-Pipelines** (gar keine Chain): der Lauf wird per SQL angefordert.

```sql
CREATE TABLE DQ_RUN_REQUESTS (
  REQUEST_ID    NVARCHAR(64)  PRIMARY KEY,     -- von Prozedur generiert (UUID)
  OBJECT_ID     NVARCHAR(256) NOT NULL,
  REQUESTED_BY  NVARCHAR(128) NOT NULL,        -- SESSION_CONTEXT / CURRENT_USER
  REQUESTED_AT  TIMESTAMP     NOT NULL,
  STATUS        NVARCHAR(16)  NOT NULL,        -- requested | claimed | done | error | expired
  CLAIMED_BY    NVARCHAR(64),                  -- Signal-Instanz (Claim-Muster wie dq_schedules)
  RUN_ID        NVARCHAR(64),
  FINISHED_AT   TIMESTAMP
);
```

```
P_DQ_REQUEST_RUN(obj) → INSERT (requested) → REQUEST_ID zurück
P_DQ_GATE(obj, timeout=900s, poll=10s, fail_on=…):
  1. REQUEST_RUN
  2. Warte-Schleife: SQLSCRIPT_SYNC:SLEEP_SECONDS(poll), Status lesen
       done  → P_DQ_ASSERT_GATE (auf den frischen RUN_ID gepinnt)
       error → SIGNAL_SQL_ERROR 10055
       Timeout überschritten → 10054 (fail-closed), Request als expired markiert
```

Signal-seitig übernimmt der **vorhandene Scheduler-Poller**
(`services/api/scheduler.py`, Claim-Muster der `dq_schedules`) eine zweite
Quelle: pro Tick offene Requests claimen (`UPDATE … WHERE STATUS='requested'`,
optimistisch), `start_object_run(..., triggered_by="sql_bridge")` starten —
der F2-Doppellauf-Schutz (`try_begin_run`) greift unverändert. Nach Lauf-Ende
Request auf `done`/`error` + `RUN_ID` setzen.

Eigenschaften, ehrlich benannt: Latenz = Poller-Tick + Lauf + Poll-Intervall;
ein belegter Chain-/Prozedur-Slot während der Wartezeit; Signal-Service muss
laufen (wie beim API-Task). Deshalb **Opt-in** per Setting
(`ENFORCEMENT_SQL_BRIDGE_ENABLED`, Default `false`) und dokumentierte
Empfehlung: API-Task, wo möglich; Bridge, wo HTTP nicht darf oder keine Chain
existiert. **Spike:** Verfügbarkeit von `SQLSCRIPT_SYNC` (Built-in-Library)
im Open-SQL-Kontext des Tenants verifizieren — ohne Sleep keine Warte-Schleife
(Fallback: Chain in zwei Prozedur-Schritte teilen: Request → separater
Assert-Schritt mit `in_min_evaluated_after`).

### 6.4 `on_load`-Trigger (AP-5, additiv)

Unverändert aus dem Handover: für Objekte, deren Chains man nicht anfassen
kann, startet der Poller nach jedem neuen erfolgreichen Load einen Lauf. In
Kombination mit CLEAN-View-Konsum ergibt das ein Gating **ganz ohne
Pipeline-Änderung**: Load → automatischer Lauf → Verdict/Views aktuell →
Konsumenten lesen CLEAN.

---

## 7 — Lifecycle der materialisierten Objekte: Desired-State-Reconciler

Das Manifest-Muster (Monitoring-Share-Hub) wandert nach innen: Signal
berechnet aus den aktiven Contracts den **Soll-Zustand** seines Schemas und
gleicht ihn selbst ab.

**Registry (im Open-SQL-Schema, nur Signal schreibt):**

```sql
CREATE TABLE DQ_OBJECTS (
  NAME           NVARCHAR(128) PRIMARY KEY,    -- z. B. V_DQ_SALES__ORDERS_CLEAN
  KIND           NVARCHAR(16),                 -- view | table | procedure
  OBJECT_ID      NVARCHAR(256),                -- Prüfobjekt (NULL für globale Objekte)
  CONTRACT_ID    NVARCHAR(128),
  MANIFEST_HASH  NVARCHAR(64)  NOT NULL,       -- Hash über erzeugte DDL-Definition
  GENERATION     INTEGER       NOT NULL,
  STATUS         NVARCHAR(16)  NOT NULL,       -- active | invalidated | dropped
  CREATED_AT     TIMESTAMP, UPDATED_AT TIMESTAMP
);
```

**Reconcile-Zyklus** (bei Contract-Änderung, Deploy und periodisch):

1. **Soll berechnen:** deterministische DDL je Objekt (aus kompilierten
   Checks/Prädikaten + Inventar-Spalten), `manifest_hash` = Hash der DDL.
2. **Plan:** Diff Soll ↔ Registry ↔ tatsächliches Schema
   (`SYS.VIEWS`/`SYS.PROCEDURES`-Definitionen bzw. gespeicherter Hash) →
   `create / replace / invalidate / drop / drift`.
3. **Drift:** handgeänderte Signal-Objekte (Definition ≠ Hash) werden im
   Cockpit geflaggt und beim Apply überschrieben — Signals Schema ist
   generierter Boden, keine Bearbeitungsfläche.
4. **Apply:** idempotent (`CREATE OR REPLACE`, Guards); jede DDL-Aktion ist
   ein **Activity-Event** (Audit) mit Plan-Referenz.
5. **Verwaiste Objekte** (Contract weg, Enforcement zurückgestuft):
   **invalidate-then-drop** — weil Kunden-Flows z. B. `V_…_CLEAN` als Quelle
   referenzieren können, wird nie sofort gedroppt:
   - *Invalidate:* View wird durch eine Marker-Definition ersetzt, die **laut
     fehlschlägt** (z. B. Projektion mit `SIGNAL`-werfender Funktion bzw.
     ungültiger Verweis — Fehlermeldung nennt den Grund), Registry-Status
     `invalidated`, Episode/Notification an den Objekt-Owner. Bewusst kein
     stilles 0-Zeilen-Verhalten (Anti-Pattern §5.1).
   - *Drop:* nach Grace-Period (Setting, Default z. B. 14 Tage) endgültig,
     Registry `dropped`.
6. **Ausnahmen:** `DQ_Q_*`-Quarantäne-Tabellen (nur TTL, §5.2) und
   `DQ_RUN_REQUESTS`/`DQ_GATE_STATUS*`/`DQ_OBJECTS` selbst (globale
   Infrastruktur, versioniert über nummerierte Remote-Migrationen analog
   Store-Migrationen — nie per Reconciler gedroppt).

**Plan/Dry-Run im Cockpit:** der berechnete Plan ist vor dem Apply sichtbar
(analog Proposal-Flow); `ENFORCEMENT_MATERIALIZE_ENABLED` (Default `false`)
ist der globale Kill-Switch — ohne ihn rechnet Signal Pläne, wendet aber nie
an (reiner Manifest-Modus = heutiger externer Pfad bleibt möglich).

---

## 8 — Integrations-Rezepte (Kochbuch)

### R-A — Task Chain, natives Promotion-Gate (B2)

```
[Load → Staging]
→ [API-Task async: POST /api/objects/<id>/run?fail_on=block_and_quarantine]
→ [Promote Staging → Curated]          # läuft nur bei COMPLETED
```
Voraussetzungen: HTTP-Connection auf Signal (Host+Credentials, technischer
Principal `steward+`, S5 beachten: echte Auth, kein `noauth`).

### R-B — Task Chain, SQL-natives Gate (ohne HTTP)

```
[Load → Staging]
→ [Prozedur-Schritt: CALL "<SIGNAL_SCHEMA>"."P_DQ_GATE"('<obj>', 900, 10, 'block')]
→ [Transformation Flow liest das CLEAN-Artefakt (importiertes DQ_CLEAN_<OBJ> bzw. V_DQ_<OBJ>_CLEAN)]
→ [Promote]
```
Bridge-Latenz einkalkulieren; `fail_on='block'`, weil der Flow CLEAN
konsumiert — Quarantäne isoliert, blockiert aber nicht.

### R-C — Transformation Flow ohne Chain-Änderung

Flow-Quelle vom Rohobjekt auf das CLEAN-Artefakt umstellen (Variante A: importierte `DQ_CLEAN_<OBJ>`-Entität, per Sharing auch space-übergreifend); Lauf-Trigger via
`on_load` (§6.4). Kein Gate-Schritt — Schutzwirkung: Zeilen-Isolation ja,
harter Stopp nein. Für harten Stopp Chain um den Flow legen (R-A/R-B).

### R-D — Bestehende HANA-/SQLScript-Prozedur

```sql
CREATE OR REPLACE PROCEDURE KUNDE.LOAD_ORDERS AS
BEGIN
  CALL "<SIGNAL_SCHEMA>"."P_DQ_GATE"('SALES__ORDERS_STAGING', 900, 10,
                                     'block_and_quarantine');
  -- ab hier nur bei offenem Gate:
  INSERT INTO KUNDE.ORDERS_CURATED SELECT … FROM KUNDE.ORDERS_STAGING …;
END;
-- Variante ohne frischen Lauf (Verdict von on_load/Chain):
--   CALL "<SIGNAL_SCHEMA>"."P_DQ_ASSERT_GATE"('SALES__ORDERS_STAGING',
--        in_min_evaluated_after => :load_started_at);
```
Fehlerbehandlung optional per `EXIT HANDLER FOR SQL_ERROR_CODE 10052/10053`
(z. B. eigenes Protokoll + Re-Raise).

### R-E — Episodische Quarantäne mit Rückführung

```
Lauf → verdict=quarantine → Signal parkt Zeilen in DQ_Q_<OBJ> (Episode reconciled)
Steward prüft im Cockpit (PII-gegateter Drilldown) → Freigabe (released)
Kunden-Re-Load-Flow: liest V_DQ_<OBJ>_RELEASED → lädt ins Ziel
                     → CALL P_DQ_CONFIRM_REPROCESS(:episode)  → resolved
TTL-Ablauf ohne Freigabe → Housekeeping purgt, Episode resolved(expired)
```

### R-F — Nicht-DSP-Orchestrator (Airflow/Cron/CI)

CLI wie gehabt (`dq_check_runner.py`, Exit 0/1/3, `--no-enforce`) —
unverändert AP-2; die materialisierten Views/Tabellen stehen auch diesem Pfad
zur Verfügung, sofern die CLI gegen denselben Store/Tenant läuft.

---

## 9 — Sicherheits-Gates & Invarianten (Abgleich)

| Gate | Wirkung dieses Konzepts |
|---|---|
| **G1** | unverändert: Contracts bleiben SQL-frei; alle DDL/Prädikate erzeugt der Compiler/DDL-Generator |
| **G2** | verschärft beachten: generierte DDL enthält **nie** Schema-Literale — Quell-Schema via `bind_schema` `[SCHEMA-MAP]`, Signal-Schema via Setting (`DATASPHERE_SIGNAL_SCHEMA`), beides Laufzeit-Injektion |
| **G3** | Contract-Änderungen, die Prädikate/Views ändern, laufen durch den normalen Diff; Major-Bump-Pflicht unverändert. Reconciler `superseded`-Pfad greift bei Prädikatswechsel |
| **G6** | neue Zustände sind explizit: Episode-Lifecycle (inkl. `expired`), Request-Status, Registry-Status — nie stilles Auslassen |
| **G7** | DDL-**Generierung** ist frameworkfrei (neues Modul in `dq_core`), **Ausführung** (Schreib-Connection, Reconciler, Poller) lebt in `services/` |
| **G8** | Rohzeilen verlassen HANA nie; Quarantäne-Tabellen liegen in HANA; Cockpit-Drilldown nur über den gegateten Diagnostics-Pfad; TTL ist Pflicht |
| **S5** | unverändert; zusätzlich: API-Task-/Bridge-Aufrufe brauchen echte Auth bzw. `DEFINER`-Prozeduren ohne Direkt-Grants |
| **ADR-0002** | Amendment §2: read-only gegenüber Kundendaten, Schreiben nur im eigenen Schema; ein User, `DEFINER`-Türen, Grant-Modell |

Autonomie-Leitplanken (aus Review §5.4, hier bindend): jede DDL-Aktion und
jeder Outbound-Trigger ist auditiert (Activity-Event), alles Materialisierende
ist opt-in mit globalem Kill-Switch, Defaults sind aus.

---

## 10 — Implementierungs-Slice

Baut auf `Konzept_Enforcement_Modi_*` §4 auf (Layer 1–5 dort gelten
unverändert für Enforcement-Feld, Verdict, Store, CLI, Quarantäne-API/-UI).
Zusätzlich:

**Layer 1a — DDL-Generator (`packages/dq_core/enforce/`, frameworkfrei, G7)**
- `ddl.py`: deterministische Erzeugung von Split-View-, Verdict-, Prozedur-
  und Quarantäne-Tabellen-DDL aus kompilierten Checks (`_diagnostic_sql`-
  Prädikate) + Inventar-Spalten; `manifest_hash` (stabile Normalisierung).
- `plan.py`: Soll/Ist-Diff → Plan-Datenklassen (`create/replace/invalidate/
  drop/drift`). Reine Berechnung, keine Ausführung, keine Web-Imports.
- Tests: Golden-DDL-Fixtures je Garantie-Familie; Hash-Stabilität;
  OR-Vereinigung mehrerer Prädikate; Ausschluss nicht zeilenfähiger Familien.

**Layer 3a — Services (`services/api/`)**
- `enforcement/materializer.py`: Schreib-Connection (gleicher Space-User),
  Apply des Plans, Activity-Events, `ENFORCEMENT_MATERIALIZE_ENABLED`-Gate.
- Scheduler-Erweiterung: `DQ_RUN_REQUESTS`-Claim (Bridge, §6.3),
  `triggered_by="sql_bridge"`; Housekeeping-Tick (TTL-Purge, Grace-Drops).
- Lauf-Abschluss-Hook: Verdict-Upsert (§3), Episoden-Snapshot (§5.2).
- Settings (alle Default aus/leer): `DATASPHERE_SIGNAL_SCHEMA`,
  `ENFORCEMENT_MATERIALIZE_ENABLED`, `ENFORCEMENT_SQL_BRIDGE_ENABLED`,
  `QUARANTINE_DEFAULT_TTL_DAYS`, `RECONCILER_DROP_GRACE_DAYS`.

**Layer 4a — API**
- `routers/enforcement.py`: `GET /api/enforcement/plan` (Dry-Run),
  `POST /api/enforcement/apply` (`require_roles(owner, admin)`),
  Registry-/Drift-Ansicht; RFC-7807.
- `routers/quarantine.py` (aus Enforcement-Konzept) + `POST /{id}/confirm-
  reprocess`.

**Layer 5a — Frontend**
- Materialisierungs-Panel (Plan, Drift, Apply — rollen-gegated), Episoden mit
  Release-/Reprocess-Status, i18n in `de.ts`.

**Migrations-Disziplin:** Store-Migrationen nummeriert wie gehabt; die
**Remote-Infrastruktur-Objekte** (`DQ_GATE_STATUS`, `DQ_RUN_REQUESTS`,
`DQ_OBJECTS`) erhalten eine eigene, ebenfalls nummerierte Migrationsreihe
(`packages/dq_core/enforce/remote_migrations/`) — nie editieren, nur anhängen.

**Reihenfolge:** ① Enforcement-Achse (Layer 1–2 alt) → ② AP-1 API-Task →
③ Verdict-Tabelle + `P_DQ_ASSERT_GATE` (kleinster materialisierter Kern) →
④ Reconciler + Split-Views → ⑤ episodische Quarantäne → ⑥ SQL-Bridge →
⑦ Outbound-Trigger (R4). Spikes O5 (Grants/Flow-Quelle) und
`SQLSCRIPT_SYNC` vor ③ bzw. ⑥.

---

## 11 — Bewusst außerhalb des Scopes

- Schreiben außerhalb des Signal-Schemas — in jeder Form, dauerhaft.
- Rückführung freigegebener Zeilen in Kundenziele durch Signal (immer
  Kunden-Flow über die Release-View).
- Nachbau eines Task-Monitors (R5 bestätigt: verlinken, nicht spiegeln).
- HDLF/Data-Lake-Objekte ohne HANA-SQL-Oberfläche (ADR-0002 §6 unverändert).
- Automatisches Re-Schreiben von Kunden-Flows/Chains (Quellen-Umstellung auf
  CLEAN-Views ist manueller, dokumentierter Schritt).

## 12 — Offene Punkte & Risiken

| # | Punkt | Behandlung |
|---|---|---|
| O5 | **Rest-O5** (geschrumpft, 2026-07-11): Tabellen-Import aus dem Open-SQL-Schema (live auf hdbtable) + Cross-Space-Sharing sind am Tenant **bestätigt** — der Flow-/Sharing-Pfad ist entsperrt. Offen bleiben: (a) haben **Views** denselben Import-/Sharing-Pfad (nur Variante B §5.1)? (b) `EXECUTE`-Grant an fremde DB-User für `P_DQ_ASSERT_GATE` (nur Rezept R-D, wenn Kunden-Prozeduren unter anderer Identität laufen) | halber Spike-Tag; Capability-Probe im Connector |
| O6 | `SQLSCRIPT_SYNC:SLEEP_SECONDS` im Tenant verfügbar? | Spike vor Slice ⑥; Fallback: zweigeteilte Chain (Request-Schritt + Assert-Schritt) — alternativ Fallback direkt als Primärdesign beschließen |
| O7 | Performance der Split-Prädikate (`keys`/`referential`) je Lesen — **nur Variante B**; bei Variante A (materialisierte CLEAN-Tabelle) entfällt O7 | nur messen, falls B gewählt wird |
| O8 | Exakte API-Task-Statuscode-Erwartung | unverändert AP-1-Spike |
| O9 | Verhalten des Invalidate-Markers — welche Konstruktion schlägt in Flows zuverlässig laut fehl? Bei Variante A: **Leeren wäre stilles 0-Zeilen-Anti-Pattern (§5.1)** — Invalidate = Refresh-Stopp + Notification, nach Grace **Drop** der hdbtable (Import bricht laut). Zu verifizieren: bricht der Flow beim Drop wirklich laut? Marker-View-Frage bleibt für B | Teil des Rest-O5-Spikes |
| O10 | Datenschutz-Review der Data-Custody-Zone (TTL, Löschkonzept, Auftragsverarbeitung) | vor Slice ⑤ mit Governance klären |

## 13 — Verifikation (End-to-End, nach Umsetzung)

1. **Unit:** Golden-DDL je Familie; Plan-Diff-Matrix (create/replace/
   invalidate/drop/drift); Verdict-Upsert; Episoden-Idempotenz
   (gleiche Generation zweimal = No-Op); TTL-Purge explizit.
2. **Gate-Prozedur (Mock-HANA/Integrationstenant):** kein Verdict → 10050;
   veraltet → 10051; `block` → 10052; `quarantine` + Default → 10053;
   `quarantine` + `fail_on=block` → kommt zurück.
3. **Bridge:** Request → Poller claimt → Lauf → `P_DQ_GATE` kehrt zurück;
   Timeout → 10054 + Request `expired`; Doppel-Request → ein Lauf (F2).
4. **Chain-Rezepte R-A/R-B am Tenant:** grüner Lauf promotet; `block` stoppt
   die Chain; `quarantine` mit CLEAN-Konsum läuft weiter und öffnet Episode.
5. **Episodik:** Parken → Freigabe → Release-View → Confirm → `resolved`;
   Ablauf ohne Freigabe → `resolved(expired)`.
6. **Reconciler:** Contract entfernt → Objekt `invalidated` (Flow schlägt
   laut fehl), nach Grace gedroppt; Handänderung → Drift-Flag + Overwrite.
7. **Gates lokal:** G1/G2-Greps sauber (keine Schema-Literale in generierter
   DDL-Vorlage), G7 (`dq_core/enforce` ohne Web-Imports), G8
   (Drilldown nur gegated), `make test` + FE-Suite grün.
