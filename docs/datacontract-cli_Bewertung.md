# datacontract-cli vs. Signal — Bewertung & Entscheidungsgrundlage

> Begleitdokument zu [`datacontract-cli_Integration.md`](datacontract-cli_Integration.md)
> (Schaubild-/Feature-Landkarte). Dieses Dokument hält die **Bewertung** fest:
> Wo lohnt die CLI, wo nicht, und warum bleibt die Eigenentwicklung gerechtfertigt.
> Stand der Diskussion, nicht-bindend — als Argumentationsgrundlage.

---

## 0. Kernaussage (TL;DR)

- Die `datacontract-cli` ist für Signal eine **Beigabe in CI/Tooling auf dem
  ODCS-Export** — **kein** Ersatz für Engine, Store oder Cockpit.
- Ihr größter realer Nutzen ist die **Breaking-Change-Zweitmeinung** (läuft schon).
- Ihre „Check-Bibliothek" ist **nicht** das Kaufargument: sie hat keinen festen
  Check-Katalog und **kein SAP-HANA-Backend**.
- Signals Substanz liegt **nicht in der Engine**, sondern in **Governance (G1/G8),
  Runtime-Compliance/SLA, Cockpit, Observability, Lineage und SAP-Semantik** —
  alles Dinge, die ODCS/CLI konzeptionell gar nicht modellieren.
- **Nativ in Datasphere** geht die CLI nur in der **Databricks-Plane (BDC)** — dort
  über **zwei Delta-Pfade**: `type: databricks` (Unity/Hive Catalog, SQL-Warehouse)
  oder Object-Store + `format: delta` (DuckDB, ohne Cluster). Für HANA-Space-Objekte
  ist der native In-Chain-Check *kompiliertes SQL* = Signal-Engine (kein `type: hana`)
  (§8). Ein **Task-Chain-REST-Call** löst das *Trigger*-, nicht das
  *Ausführungs*-Problem — hinter der URL gehört Signals API, nicht die CLI (§9).
- Einen **HANA-Connector zu contributen** ist technisch machbar
  (`sqlalchemy-hana`), bringt aber Read-only/PII/G1 als Shim zurück und
  kommoditisiert nur den geringwertigsten Layer. Empfehlung: **Ökosystem-Play
  (Weg 2)** — contributen + als Advisory-Executor nutzen, Produktion bleibt
  Signal-Engine (§10).

---

## 1. Welche „Checks" bringt die CLI überhaupt mit?

Wichtig: Die CLI hat **keinen festen Check-Katalog** wie Signals
`check_library.json`. Sie kennt zwei Ebenen:

- **Ebene A — Schema-Validierung „gratis"** aus der Feld-Definition:
  Typ · `required` · `unique` · `primaryKey` · `enum` · `pattern` · `format`
  · `minLength`/`maxLength` · `minimum`/`maximum`. **Kein SQL.**
- **Ebene B — `quality:`-Sektion**: `type: library` (benannte Metrik wie
  `rowCount`/`nullValues` + Operator, `unit: percent` — **kein SQL**) oder
  `type: sql` (inline `query:` + Schwellwert — **Roh-SQL**). Backends u. a.
  Snowflake · BigQuery · Postgres · Databricks · DuckDB/Delta — **kein SAP HANA**.

> **Stand-Update (datacontract-cli v1.0.0, 2026-06):** Die Ausführungs-Engine
> wurde **von Soda Core auf ibis umgestellt** — `datacontract test` kompiliert
> Schema- und Quality-Checks in **ibis-Ausdrücke** (dialekt-korrektes SQL via
> `sqlglot`). **Rohe SodaCL-Custom-Checks (`type: custom`, `engine: soda`) werden
> nicht mehr ausgeführt** (nur Warnung); Empfehlung: `type: sql` **oder**
> `library`-Metrik. SodaCL/Great-Expectations sind damit nur noch **Export**-Ziele,
> nicht mehr der Laufzeitpfad. Die historischen „Soda/GX-Wrapper"-Aussagen unten
> sind in diesem Sinn zu lesen.

→ „Komplette Bibliothek an Checks" = realistisch **Schema-Validierung +
`library`-Metriken (begrenzter Katalog) + Roh-SQL als Escape-Hatch**. Ersetzt
Signals ~20 HANA-/SAP-Checks nicht und kann mangels HANA-Backend nicht gegen eure
Quelle laufen.

---

## 2. Signals Gegenstück: die eigene Check-Bibliothek

Quelle: `packages/dq_core/library/check_library.json` (~20 Checks, 5 Kategorien).

| Kategorie | Checks |
|---|---|
| Vollständigkeit | `row_count` · `missing` · `completeness_pct` |
| Konsistenz | `duplicate` · `duplicate_composite` · `duplicate_approx` · `invalid` · `value_range` · `allowed_values` · `pattern_match` · `string_length` · `reference_integrity` |
| Verteilung & Aggregate | `aggregate_range` |
| Aktualität & Sonstiges | `freshness` · `schema` · `custom_sql` |
| SAP / BDC | `sap_bseg_balance` · `sap_bkpf_orphan` · `sap_fiscal_completeness` · `sap_replication_lag` · `sap_key_plausibility` |

Die SAP/BDC- und HANA-Systemsicht-Checks (`SYS.TABLE_COLUMNS`,
`APPROXIMATE_COUNT_DISTINCT`, `LIKE_REGEXPR`, `SECONDS_BETWEEN`,
Input-Parameter `:<YEAR>`/`:<BUKRS>`) sind genau das, was die CLI **nicht** kann.

---

## 3. „SQL-freie Garantien" (Gate G1) — was das heißt

Im Contract steht **was** gelten soll, nie **wie** es abgefragt wird.

```yaml
guarantees:
  keys:
    - columns: [ORDER_ID]      # "ORDER_ID ist eindeutig"
      unique: true
  freshness:
    column: ORDER_DATE
    max_age: PT26H             # "nicht älter als 26 h"
```

Erst der **Compiler** (`compiler.py`) macht daraus deterministisch SQL — aus den
Templates der `check_library.json`. Es gibt **keinen Roh-SQL-Pfad** im Vertrag.

**Nutzen:** Sicherheit (keine SQL-Injection-Fläche im YAML, S2-Identifier-Schutz)
· fachliche Lesbarkeit · Portabilität (dieselbe Garantie → HANA-SQL *oder* ODCS)
· robuste Diffbarkeit (Bedeutungen statt SQL-Strings) · Governance.

---

## 4. Enthält ODCS SQL? — Ja, aber optional

Präzisierung: ODCS v3.1 **erlaubt** SQL, **erzwingt** es nicht.

| `quality.type` | Inhalt | SQL im Vertrag? |
|---|---|---|
| `library` | benannte Regel (rowCount, nullCount …) + Operator | nein (deklarativ) |
| `text` | Beschreibung | nein |
| `sql` | eingebettetes `query:` + Schwellwert | **ja** |
| `custom` | engine-spezifisch (Soda/GX) — **seit CLI v1.0.0 nicht mehr ausgeführt**, → `sql`/`library` migrieren | **ja** |

Zusätzlich viele **deklarative** Felder auf Property-Ebene (`required`, `unique`,
`primaryKey`, `pattern`, `min`/`max`, `enum`, `format`).

**Signals Haltung:** beim Export (`to_odcs()`) wird **bewusst nur der
deklarative + library-Pfad** genutzt — **nie** `type: sql`. Damit ist G1
**strenger als ODCS**: ODCS lässt dir die Wahl, Signal nimmt dir die SQL-Option
per Gate weg. Folge: ein *fremder* ODCS-Vertrag kann `type: sql`/`custom`
enthalten — euer eigener Export erzeugt das nie.

---

## 5. Kann Signal ODCS-Verträge importieren?

**Heute: nein.** Es gibt nur `to_odcs()` (Einweg-Export); kein `from_odcs()` und
kein Import-Endpoint.

Machbar wäre ein Importer, aber **verlustbehaftet** (umgekehrt zum Export, weil
ODCS die größere Menge ist):

- Deklarativer Teil mappt sauber zurück (`schema.properties`→`schema`,
  `required`→`not_null`, `primaryKey`→`keys`, `quality[rowCount]`→`volume`,
  `nullValues`→`completeness`, `latency`→`freshness`, `relationships`→`referential`,
  `pattern`/`enum`/`min`/`max`→entspr. Checks).
- **`type: sql`/`custom` lässt sich NICHT importieren** (G1, kein Roh-SQL-Pfad) —
  muss als „nicht übernommen" gemeldet, nicht still verworfen werden.
- Jeder Import muss durch `validate_contract` **und** Compile, sonst kein gültiger
  Signal-Contract.

**Wege:** (1) homegrown `from_odcs()` in `dq_core/contract/`, ~150 LOC,
frameworkfrei (G7) — empfohlen, falls Import gebraucht wird. (2) `datacontract
import --format odcs` bringt nichts Zusätzliches (erzeugt datacontract.com-YAML,
nicht euer kanonisches Schema — Mapper braucht ihr trotzdem). Der nützliche
CLI-`import` ist der aus *technischen* Quellen (SQL-DDL, Avro, Glue, BigQuery)
für einen Erst-Entwurf.

---

## 6. Build vs. Buy — auch wenn die CLI eine HANA-Engine hätte

Hypothese: Selbst *mit* HANA-Engine würde die CLi nur **`compiler` + `engine` +
`library`** abdecken (~20–30 % von Signal). **Nicht** ersetzt würden:

- **Runtime-Compliance & SLA** (`store/`, `compliance.py`) — ODCS modelliert keine
  Laufzeit-Resultate; die CLI ist zustandslos (run→pass/fail), kein Result-Store,
  keine `compliant/breached`-Transition, keine Incident-Timeline.
- **Cockpit** — Status-Grid, Coverage-Map, Workbench, Runs, Incidents, Proposals.
- **Observability / Proposal-Miner** (`obs/`) · **Lineage / CSN** (`lineage/`).
- **Lifecycle-Zeremonie** (Lite/Full, SemVer, Approval, Git-als-Wahrheit).
- **SAP/BDC-Semantik & ORD/CSN-Publishing** (`sap-bdc-connect-sdk`).

**Wo es ehrlicherweise knapp würde:** Für den reinen Ausführungs-Layer könnte man
„wrappen statt bauen" — *aber nur*, wenn die HANA-Engine read-only, PII-sicher und
HANA-SQL-nativ wäre. Realistisch (ibis-/`sqlglot`-basiert, generisch) ist sie das nicht:

1. Verlust der Kontrolle über HANA-Native-SQL (`APPROXIMATE_COUNT_DISTINCT`,
   `LIKE_REGEXPR`, `SYS`-Views, SAP-Input-Parameter).
2. **Kein PII-Gate (G8), keine Read-only-Garantie** — müsstet ihr um die CLI herum
   neu bauen und auditieren.
3. **G1 nicht durchsetzbar** — die CLI erlaubt `type: sql`/`custom`.
4. **G7** — Einbettung bräche „dq_core frameworkfrei".

→ Die Sicherheits-/Governance-Leitplanken baut ihr ohnehin selbst — und das ist
der eigentliche Aufwand, nicht das `COUNT(*)`-SQL.

**Fazit:** Voller Ersatz lohnt auch im Hypothese-Fall nicht. Die HANA-Engine ist
heute euer *Marketing*-Differenzierer („einzige mit HANA-Runner"), nicht euer
*substanzieller* — letzterer (Governance + Compliance + Cockpit + SAP-Kontext)
bliebe bestehen, selbst wenn die CLI HANA könnte. Ihr müsstet die *Erzählung*
anpassen, kaum die *Architektur*.

---

## 7. Empfehlung (Verdichtung)

| Einsatz der CLI | Urteil |
|---|---|
| `datacontract breaking` als CI-Zweitmeinung auf ODCS-Export | ✅ **nutzen** — läuft schon (`odcs-second-opinion`) |
| `datacontract lint` (ODCS-Spec-Konformität des Exports) | ◻️ sinnvoller Low-Cost-Ausbau |
| `export` (dbt/JSON-Schema/Avro/…) | ◻️ nur bei konkretem Konsumenten-Bedarf |
| `import` aus technischen Quellen (SQL/Avro/Glue) | ◻️ nützlich fürs Onboarding |
| `catalog` (statisches HTML) | ◻️ optional (Cockpit deckt internen Fall ab) |
| `test` als Check-Runner | ⛔ **nicht** — kein HANA, bricht G1/G8 |
| Engine/Store/Cockpit ersetzen | ⛔ **nicht** — Kern der Wertschöpfung |

---

## 8. Native Nutzung in Datasphere — zwei „Planes"

Frage: Kann die CLI nativ in Datasphere laufen, z. B. als Check am Ende von
Task Chains? Antwort hängt an **zwei** Constraints gleichzeitig:

1. **datacontract-cli hat keine HANA-Engine** (`test`: Snowflake/BigQuery/
   **Databricks**/Postgres/S3/Kafka — kein HANA).
2. **Task Chains haben keinen „beliebiges-Python/CLI"-Schritt** — sie
   orchestrieren nur Datasphere-Artefakte (Replication/Data/Transformation Flow,
   View-Persistierung, Intelligent Lookup, geschachtelte Chains).

→ „datacontract-cli nativ am Ende einer HANA-Task-Chain" ist im strengen Sinn
**nicht möglich**. Was nativ in der Chain läuft, ist *kompiliertes SQL* = Signals
Engine-Pfad, nicht die CLI. Es gibt zwei Ebenen, auf denen „nativ" je anderes heißt:

| | **HANA-Plane** (Objekte im HANA-Space als DP) | **Databricks-Plane** (BDC Data Products) |
|---|---|---|
| Daten liegen in | HANA Cloud (Datasphere-Space) | Databricks/Delta (BDC) |
| `datacontract test` nativ? | ⛔ nein (kein HANA-Backend, kein `type: hana`) | ✅ ja — **zwei Delta-Pfade** (s.u.) |
| „Check am Ende der Chain" | Transformation Flow / Prozedur mit kompiliertem SQL (**Signal-Engine**) | Databricks-Workflow-Task mit **`datacontract test`** |
| Orchestrierung | Task Chain nativ, oder Task-Chain-API + `dq_check_runner` | Databricks Workflow / Job |
| CLI-Rolle | nur statisch: `breaking`/`lint` + Export ODCS/CSN/ORD | Ausführung **+** statisch + Export |
| DQ-Status-Publishing | ORD-Labels/CSN (einseitig); Source of Truth = YAML | identisch |

**BDC-Sonderfall:** Weil BDC-Compute SAP Databricks ist, ist `datacontract test`
dort der **einzige** Ort, an dem die CLI als *Executor* nativ tragfähig ist —
ohne G1/G8 in der HANA-Welt zu verletzen.

**Delta-Connector — zwei Pfade (verifiziert gegen die datacontract-specification):**
Ein als **Delta** materialisiertes Data Product ist auf beiden Wegen testbar:

- **Pfad A — `type: databricks`** (Hive-/Unity-Catalog mit `catalog`/`schema`).
  Checks laufen als SQL auf einem Databricks **SQL-Warehouse/Compute**.
  Extra: `pip install datacontract-cli[databricks]` + laufendes Warehouse.
- **Pfad B — Object-Store + `format: delta`** (`type: s3`/`azure`/`gcs`/`local`).
  Liest die Delta-Files **direkt über DuckDB, ohne Databricks/Spark-Cluster** —
  leichtgewichtig. Extra: `pip install datacontract-cli[duckdb]`.

→ Egal ob das BDC-Produkt als Unity-Catalog-Tabelle (A) oder als Delta-Files im
Lakehouse-Objektspeicher (B) liegt: die CLI deckt beide Fälle ab. **HANA hat
keinen Connector** (`type: hana` existiert nicht), die HANA-Plane-Aussage oben
bleibt unberührt.

> **Vorbehalt — CLI vs. Eigenbau für Delta (vgl.
> [`datacontract-cli_Hypothese_VollerErsatz.md`](datacontract-cli_Hypothese_VollerErsatz.md)
> §6.6):** „CLI als Delta-Executor" ist nicht alternativlos. Sobald Signal
> Delta/HDLF *governt*, fallen read-only/PII/Gating **so oder so** an — und die
> *Plattform*-Garantien (Store/Compliance/Cockpit/G1-Authoring) werden ohnehin
> wiederverwendet, nicht neu gebaut. Damit schrumpft der CLI-Vorteil auf den
> mitgelieferten **Connector**; demgegenüber steht der Eigenbau-Weg (DuckDB/ibis-
> Adapter in `connect/` + `sqlglot`-Transpile der HANA-Templates), der die
> Guardrails **nativ** wiederverwendet und den Dual-Engine-Split auflöst. Welcher
> Weg billiger ist, ist eine Abwägung „gesparter Connector vs. Fremdprozess +
> Mapper + zweite Engine" — siehe §6.6 für die A/B-Gegenüberstellung.

> Offen (vgl. Zusatz-Doc R2/R7): wie Datasphere/BDC die ORD-Dokumente eines
> Data Products emittiert — und ob BDC-Produkte **überhaupt** als Delta
> materialisieren (dann greift Pfad A *oder* B) oder teils HANA-nativ bleiben
> (dann fallen sie auf die HANA-Plane zurück → kein CLI-Executor). Die
> Unterscheidung Unity-Catalog-Delta vs. Object-Store-Delta ist **kein** Blocker
> mehr, da beide abgedeckt sind.

---

## 9. Task Chain → REST → Engine (das saubere Trigger-Muster)

Einwand: Datasphere kann **ausgehende REST-Calls** in Task Chains auslösen — also
die CLI/Engine hinter einen Server-Endpoint legen. Das ist korrekt und die
**beste** native Anbindung, aber es trennt **zwei** Probleme, die man nicht
verwechseln darf:

- **Trigger-Problem** („wie wird der Check aufgerufen?") → vom REST-Call **gelöst**.
- **Ausführungs-Problem** („womit werden die HANA-Daten gelesen?") → vom REST-Call
  **nicht** gelöst.

**Was hinter der URL sitzen muss:**
- **Signals API/Engine** (FastAPI + `hdbcli`, read-only, PII-Gate, Store) → ✅
  funktioniert. Die Endpunkte existieren bereits: `POST /objects/{object_id}/run`,
  `POST /checks/{dataset}/dry-run`.
- **datacontract-cli auf einem Server** → ⛔ liest **trotzdem kein HANA**. Server
  ändert nichts am fehlenden Connector. (Nur in der Databricks-Plane tragfähig.)

→ Der REST-Trigger ist ein sauberer nativer Weg **für Signals Engine**, kein
Rettungsweg für die CLI als HANA-Executor.

**Zwei Design-Punkte für den REST-Schritt:**
1. **Sync vs. Async / Gating:** `/objects/{id}/run` liefert heute `202 Accepted`
   (fire-and-forget). Zum Gaten braucht die Chain entweder einen synchronen
   „run-and-wait"-Endpunkt (non-2xx bei `breached`) **oder** Trigger + Poll auf
   `GET /runs/{run_id}` bis terminal. Klären: kann der HTTP-Schritt auf den
   Response-Code verzweigen?
2. **Netz & Auth:** Service muss aus dem Datasphere-Netz erreichbar sein
   (Egress/BTP), Call braucht Token — passt zum fail-closed OIDC-Modus.

---

## 10. Build vs. Contribute — einen HANA-Connector beisteuern?

Überlegung: einen HANA-Connector + Engine zu datacontract-cli **contributen**.

**Technisch machbar, nicht von null:** Seit CLI v1.0.0 läuft `datacontract test`
nicht mehr über Soda Core, sondern über **ibis** (→ `sqlglot`). Der HANA-Connector
wäre damit realistisch ein **ibis-Backend für HANA** (statt eines
`soda-core-hana`-Adapters), gebaut auf **`sqlalchemy-hana` (SAP-maintained)** /
**`hdbcli`**. Heute existiert kein solches Backend (ibis kennt DuckDB/Snowflake/
BigQuery/Postgres/Spark …, kein HANA) — der Scope bleibt aber überschaubar.

**Aber die G-Gates kommen als Shim zurück** — ein generischer Connector ist
general-purpose:
1. **Read-only & PII-Gate (G8)** garantiert er **nicht** → musst du außenrum
   erzwingen (read-only Technical User, HANA-Privilegien). Der Teil der Engine,
   den du löschen wolltest, kehrt als Security-Schicht zurück.
2. **G1** ist mit der CLI nicht durchsetzbar (`type: sql`/`custom` erlaubt).
3. **HANA-native SQL & SAP-Checks** (BSEG-Balance, BKPF-Orphan, Fiscal
   Completeness, `SYS`-Views, Input-Parameter) haben **keine `library`-Metrik** →
   landen als `type: sql` → wieder SQL im Contract.

**Was auch dann bestehen bleibt:** ~70 % von Signal (Compliance/SLA-Store,
Cockpit, Observability, Lineage, Lifecycle, ORD/CSN). Die Contribution greift nur
den am stärksten kommoditisierten Ausführungs-Layer an.

**Strategischer Rahmen — „Commoditize your complement":** Liegt Signals Wert im
Produkt-Layer, macht eine OSS-Ausführungsschicht *darunter* den Markt größer —
gut, *solange du die Schicht darüber verkaufst*. Funktioniert aber nur, wenn du
Signal **tatsächlich auf die CLI neu aufsetzt** (sonst doppelt gebaut). Kehrseite:
du verschenkst den heutigen *Marketing*-Differenzierer („einzige mit HANA-Runner")
an den ganzen Markt — vertretbar, *wenn* der echte Moat das Produkt ist.

**Drei kohärente Wege:**

| Weg | Was du tust | Lohnt sich wenn … |
|---|---|---|
| **1 — All-in** | Connector contributen **und** Signal-Executor auf CLI umbauen | du auf den Standard wettest **und** Read-only/PII/G1 als Wrapper akzeptierst |
| **2 — Ökosystem-Play** | Connector contributen (Credibility, BDC-Reichweite, **Advisory-Executor**), Produktion bleibt Signal-Engine | du Cred + Optionalität willst, ohne Guardrails aufzugeben |
| **3 — Status quo** | nicht contributen, Differenzierer behalten | du den Aufwand scheust und den (flachen) Moat hältst |

**Empfehlung: Weg 2.** Connector als Ökosystem-/Credibility-Move beisteuern und in
Signal als **Advisory-Executor** nutzen (unabhängige Gegenprobe, analog zur
`breaking`-Zweitmeinung — Diskrepanz = Report, kein Produktionspfad).
Produktions-Checks gegen HANA bleiben auf Signals Engine, wo Read-only + PII-Gate
+ HANA-native SQL + SAP-Checks leben. Weg 1 lohnt nur, wenn ihr bereit seid,
G1/G8/Read-only als externen Shim zu führen — gemessen am Signal-Pitch ein
schlechter Tausch.

**Umsetzungshinweis:** Connector von Anfang an auf **read-only Technical User /
HANA-Read-only-Privilegien** auslegen und dokumentieren — dann für euren
Advisory-Einsatz brauchbar und für die Community sauber.

---

## 11. Anker-Referenzen

| Thema | Datei |
|---|---|
| Feature-Landkarte / Schaubild | `docs/datacontract-cli_Integration.md` |
| Contract-Beispiel | `contracts/DS_SALES_ORDERS.yaml` |
| Compiler (einziger SQL-Erzeuger, G1/G2/S2) | `packages/dq_core/contract/compiler.py` |
| Check-Bibliothek | `packages/dq_core/library/check_library.json` |
| ODCS-Export (Einweg-Brücke) | `packages/dq_core/contract/odcs_export.py` |
| Homegrown Breaking-Diff | `packages/dq_core/contract/diff.py` · `gate_g3.py` |
| CLI-Zweitmeinung (aktiv) | `.github/workflows/ci.yml` → `odcs-second-opinion` |
| Voranalyse / Begründung | `docs/REVIEW_Tool_v1_Befunde.md` |
