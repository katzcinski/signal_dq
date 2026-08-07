# Konzept — Multi-Plattform-Executor für die Business Data Cloud

**Zweck:** Grundlegende Architektur, mit der Signal **alle Backends einer Business Data Cloud
(BDC)** prüfen kann — HANA-Spaces, HDLF-Container (Delta-Tabellen), SAP Databricks und natives
Databricks — aus *demselben* semantischen Contract heraus.
**Prämisse (gesetzt für dieses Dokument):** *die `datacontract-cli` (bzw. ein gleichwertiger
Executor) könnte HANA sprechen.* Diese Annahme dreht bewusst die in
[`Zusatz_ContractLifecycle_ORDBDCIntegration.md`](Zusatz_ContractLifecycle_ORDBDCIntegration.md)
§4 festgehaltene Lücke um (*„`datacontract test` unterstützt SAP HANA nicht … Executor bleibt
ausschließlich GX-on-HANA"*) und fragt: **was wäre dann die richtige Architektur?**
**Status:** Konzept-/Evaluierungsdokument. Keine gesetzten Entscheidungen; offene Punkte markiert.
**Datum:** 2026-06-20
**Scope:** Der **Executor-Layer** — Compiler-Output → Dialekt → Verbindung → Backend. Contract-Spec,
Cockpit, Result-Store, Lifecycle/ORD bleiben unangetastet (nur Erweiterungen, keine Brüche).

---

## 1 — Warum die HANA-Lücke der Dreh- und Angelpunkt ist

`datacontract test` spricht heute **Snowflake / BigQuery / Databricks / Postgres / S3 / Kafka** —
aber **nicht HANA**. In einer reinen-Databricks- oder reinen-Snowflake-Landschaft wäre die
Multi-Plattform-Prüfung also *bereits gelöst*. Der einzige Grund, warum man in der BDC heute **nicht**
einen einzigen Executor über die ganze Plattform legen kann, ist exakt das HANA-Loch — und HANA ist
in der BDC nicht das Randstück, sondern das **Zentrum** (HANA-Spaces, Foundation Data Products,
Replikation aus S/4).

Daraus folgt die Leitthese dieses Konzepts:

> **Sobald HANA „mitspricht", wird die Backend-Frage zu einer reinen Dialekt-/Connector-Frage.**
> Signal braucht dann *keinen* zweiten Executor pro Plattform, sondern **eine** Engine mit einer
> **pluggable Backend-Abstraktion** — und kann `datacontract-cli` als *portables Parität-Gate*
> daneben betreiben, statt es als Laufzeit-Executor zu adoptieren.

Die heutige Engine ist bereits **fast** plattformneutral: sie konsumiert einen generischen
PEP-249-Cursor (`query_helpers.py`) und kennt das Backend nur an wenigen, klar lokalisierbaren
Nähten. Wir müssen also nicht neu bauen, sondern **vier Nähte kapseln**.

---

## 2 — Die Plattform-Landschaft (vier Backend-Klassen)

| # | Backend | Physik | Zugriffsweg (SQL) | Identifier-Namespace |
|---|---------|--------|-------------------|----------------------|
| 1 | **HANA-Space** | HANA-Cloud-Spalten-Store | `hdbcli` (heute) | `"SCHEMA"."TABLE"` |
| 2 | **HDLF-Container** | Delta-Tabellen als Dateien im Object Store | **Route A:** HANA Data Lake *SQL-on-Files* / virtuelle Tabellen (SDA) → `hdbcli` · **Route B:** Spark/Databricks-Endpoint über das Delta | `"SCHEMA"."TABLE"` (A) bzw. `catalog.schema.table` (B) |
| 3 | **SAP Databricks** | Databricks in der BDC (managed) | `databricks-sql-connector` (SQL-Warehouse, Unity Catalog) | `catalog.schema.table` (3-teilig) |
| 4 | **Databricks nativ** | Kunden-eigenes Databricks | `databricks-sql-connector` | `catalog.schema.table` (3-teilig) |

**Architektonisch relevante Beobachtungen:**

- **HDLF hat zwei Executor-Routen.** Über HANA (SQL-on-Files / virtuelle Tabelle) reduziert sich
  HDLF auf den **HANA-Dialekt** mit kleinen Abweichungen — kein neuer Connector nötig. Über einen
  Databricks/Spark-Endpoint auf demselben Delta reduziert es sich auf den **Databricks-Dialekt**.
  Welche Route gilt, ist **Konfiguration pro Dataset/Environment**, keine neue Engine. Das ist der
  größte Hebel des Konzepts: *vier Backend-Klassen kollabieren auf zwei Dialekte.*
- **Databricks-`s3`-Pfad.** `datacontract test` erreicht Delta/Parquet im Object Store heute schon
  über seine `s3`/duckdb-Engine. Falls HDLF einen S3-kompatiblen Endpoint exponiert, ist HDLF für
  `datacontract-cli` potenziell **ohne** HANA-Engine prüfbar — geblockt nur durch den
  **HDLF-Permission-Gap** (Zusatz-Doc R7). Relevanter Backdoor-Pfad für das Parität-Gate (§6).
- **3-teiliger Namespace.** Databricks/Unity-Catalog adressiert `catalog.schema.table`; HANA nur
  `schema.table`. Die heutige `[SCHEMA-MAP]`-Laufzeitbindung (G2) muss zur **`[NAMESPACE-MAP]`**
  verallgemeinert werden (optionales `catalog`-Segment).
- **Delta-Freshness ≠ Business-Timestamp.** Auf Delta ist „Aktualität" oft die Commit-Zeit
  (`DESCRIBE HISTORY` / `_commit_timestamp`), nicht eine fachliche Spalte. Die Garantie bleibt
  semantisch gleich; die *Kompilierung* unterscheidet sich pro Dialekt (§4.3).

---

## 3 — Wo Signal heute an HANA gekoppelt ist (die vier Nähte)

Die gesamte Plattform-Kopplung sitzt an genau vier Stellen — alles andere (Contract-Spec,
Compiler-Struktur, Engine-Ablauf, Gating, Result-Store, PII-Gate, Determinismus-Hash) ist neutral.

| Naht | Datei | HANA-Spezifika |
|------|-------|----------------|
| **A — SQL-Templates** | `packages/dq_core/library/check_library.json` | `SECONDS_BETWEEN`, `LIKE_REGEXPR`, `APPROXIMATE_COUNT_DISTINCT`, `SYS.TABLE_COLUMNS`, `FROM DUMMY` |
| **B — Batch-/Timeout-Mechanik** | `engine/check_engine.py` (`_build_batch_sql` → `FROM DUMMY`; `_run_one_check` → `SET 'statementTimeout'`) | Batch-Skalar über `FROM DUMMY`; HANA-Session-Variable |
| **C — Connector** | `connect/db_connection.py` (`get_connection` → `hdbcli`) | nur `hdbcli`; HANA-`SET statementTimeout` |
| **D — Quoting & Katalog** | `connect/query_helpers.py` (`quote_identifier`, `qualified`, `get_columns`) | Double-Quote-2-teilig; `SYS.TABLE_COLUMNS`/`VIEW_COLUMNS` |

> Befund: **vier Dateien, ein Konzept.** Die Engine selbst (`run_checks`, Gating, Result-Bau,
> Expectation-Grammatik) ist bereits backend-agnostisch und bleibt **[ENGINE-FROZEN]**.

---

## 4 — Kern: die Backend-Abstraktion (`Dialect` + `Connector` + `Catalog`)

Wir führen **eine** Schnittstelle pro Naht ein und registrieren sie pro Backend-Klasse. Der
Compiler erzeugt weiterhin *semantische* Check-Definitionen; der **Dialekt** materialisiert sie zu
backend-spezifischem SQL. So bleibt **G1 (kein SQL im Contract)** absolut und **G7 (dq_core
frameworkfrei)** gewahrt.

### 4.1 — `Backend` als Registry-Eintrag

```python
# packages/dq_core/connect/backend.py  (Skizze, illustrativ)
class Backend(Protocol):
    id: str                       # "hana" | "databricks"
    dialect: Dialect              # Naht A + B + D (SQL-Materialisierung)
    def connect(self, env: dict) -> Connection: ...   # Naht C (PEP-249-Cursor)

BACKENDS: dict[str, Backend] = {}      # Registry; Default-Eintrag "hana" = heutiges Verhalten
```

Die heutige HANA-Implementierung wird **unverändert** als Default-Backend `"hana"` registriert —
Nullregression: bestehende Läufe verhalten sich bit-identisch.

### 4.2 — `Dialect` (Naht A + B + D)

Statt eines HANA-festen `sql_template`-Strings je Check trägt die Library eine **Capability** je
Check-Typ (`row_count`, `missing`, `duplicate`, `freshness`, …). Der Dialekt rendert die Capability:

```python
class Dialect(Protocol):
    def render(self, capability: str, dataset: str, params: dict) -> str: ...
    def quote_ident(self, name: str) -> str: ...          # "x" (HANA) vs `x` (Databricks)
    def qualify(self, ns: Namespace, table: str) -> str:  # 2- vs 3-teilig
    def batch(self, checks: list[CheckDef]) -> str:       # FROM DUMMY vs SELECT-ohne-FROM
    def set_timeout(self, cursor, ms: int) -> None:       # SET statementTimeout vs no-op/SET
    def column_catalog_sql(self, ns, table) -> str:       # SYS.* vs INFORMATION_SCHEMA / Unity
```

**Migrationspfad für die Library (Naht A):** `check_library.json` behält die HANA-`sql_template`
als *Default-Rendering des HANA-Dialekts* (kein Bruch); zusätzlich erhält jeder Check eine
**dialektneutrale Capability-ID**. Neue Dialekte überschreiben nur die Templates, die abweichen
(z. B. `freshness`, `schema`, `duplicate_approx`, `pattern_match`).

### 4.3 — Beispiel: dieselbe Garantie, drei Renderings

| Capability | HANA | Databricks / Spark-SQL | Bemerkung |
|------------|------|------------------------|-----------|
| `freshness` | `SECONDS_BETWEEN(MAX("c"), CURRENT_TIMESTAMP)` | `unix_timestamp(current_timestamp()) - unix_timestamp(max(\`c\`))` | identische Semantik (Sekunden), andere Funktion |
| `duplicate_approx` | `COUNT(*) - APPROXIMATE_COUNT_DISTINCT("c")` | `COUNT(*) - approx_count_distinct(\`c\`)` | — |
| `pattern_match` | `… NOT "c" LIKE_REGEXPR '<re>'` | `… NOT \`c\` RLIKE '<re>'` | — |
| `schema` (Existenz) | `SYS.TABLE_COLUMNS` | `INFORMATION_SCHEMA.COLUMNS` / Unity-Catalog | Katalog-Quelle pro Backend |
| Batch-Skalar | `SELECT … FROM DUMMY UNION ALL …` | `SELECT … UNION ALL …` (kein `FROM DUMMY`) | Naht B |

Die **Expectation-Grammatik** (`= 0`, `< 86400`, `BETWEEN …`) und damit der gesamte Pass/Fail-
Vergleich bleiben **dialektunabhängig** — Vergleich passiert in Python, nicht in SQL.

### 4.4 — `Connector` (Naht C)

`get_connection` wird zu einer Fabrik, die anhand `env["platform"]` den passenden Connector wählt:
`hana` → `hdbcli`; `databricks`/`hdlf-spark` → `databricks-sql-connector`. Beide liefern denselben
PEP-249-Cursor-Kontrakt, den `query_helpers`/Engine bereits voraussetzen — **keine Engine-Änderung**.
Das Fail-closed-Prinzip (S-13: fehlender Treiber = harter Fehler, kein stiller Mock) gilt pro Backend.

---

## 5 — Contract bleibt backend-agnostisch; Bindung erst zur Laufzeit

Kernprinzip **unverändert**: Der Contract trägt *Garantien*, **nie** SQL und **nie** ein Backend.
Die Backend-/Namespace-Wahl ist **Deployment-Konfiguration**, exakt analog zur heutigen
`[SCHEMA-MAP]`-Bindung (G2), die `'{schema}'` erst in `bind_schema()` auflöst.

**Erweiterung des Environment-Konzepts** (`services/api/deps.py::get_environment`,
`environments.yml`): ein Environment bekommt ein `platform`-Feld und optional ein `catalog`-Segment.

```yaml
# environments.yml  (erweitert — abwärtskompatibel: ohne 'platform' = "hana")
PROD_HANA_SALES:
  platform: hana
  host: …; port: 443; schema: SALES; password_ref: env:HANA_PW
PROD_HDLF_EVENTS:
  platform: hdlf-hana          # Route A: SQL-on-Files über HANA Data Lake
  host: …; schema: LAKE_EVENTS; password_ref: env:HDL_PW
PROD_DBX_FINANCE:
  platform: databricks          # SAP- oder natives Databricks (gleicher Connector)
  host: …; http_path: /sql/1.0/warehouses/…; catalog: finance; schema: gold
  token_ref: env:DBX_TOKEN
```

Damit ist **derselbe Contract** (`DS_SALES_ORDERS.yaml`) gegen HANA *und* gegen das Databricks-
Gold-Layer ausführbar — die Garantien sind identisch, nur die Bindung wechselt. Das ist die direkte
Umsetzung des „aus demselben Code, zwei Deployment-Ziele"-Prinzips des Repos, jetzt auf Backends.

---

## 6 — Capability-Matrix & sichtbare Degradierung (G6)

Nicht jedes Backend kann jede Garantie gleich gut. **Stillschweigend auslassen ist verboten** —
genau wie heute beim Stale-Gating (`state="skipped_stale"`). Wir führen analog
**`state="skipped_unsupported"`** ein: eine Garantie, die ein Backend nicht ausdrücken kann,
erscheint als explizites, statusneutrales Ergebnis im Cockpit — nie als falsches Grün.

| Garantie | HANA | Databricks/Delta | HDLF-via-HANA | Anmerkung |
|----------|:----:|:----------------:|:-------------:|-----------|
| row_count / missing / duplicate | ✓ | ✓ | ✓ | trivial portabel |
| completeness_pct / value_range / allowed_values | ✓ | ✓ | ✓ | ANSI-SQL |
| freshness | ✓ | ✓ (Business-Spalte) **oder** Delta-History | ✓ | Delta: ggf. Commit-Zeit statt Spalte |
| reference_integrity | ✓ | ✓ | ✓ (Join über Lake) | teuer; Gating greift |
| pattern_match | ✓ | ✓ (`RLIKE`) | ✓ | Regex-Dialekt |
| schema (Existenz/Drift) | SYS-Katalog | Unity/`INFORMATION_SCHEMA` | SYS | Katalogquelle backend-spezifisch |
| sap_bseg_balance / bkpf_orphan / fiscal | ✓ | ⚠ nur wenn ACDOCA repliziert | ✓ | SAP-Checks dort, wo SAP-Daten liegen |

Die Matrix wird **datengetrieben** aus der Dialekt-Registry abgeleitet (jeder Dialekt deklariert,
welche Capabilities er rendert), nicht hartkodiert — so bleibt sie mit neuen Backends konsistent.

---

## 7 — Verhältnis zu `datacontract-cli`: Enforcement vs. Parität

Die Prämisse (HANA-fähige CLI) verleitet dazu, `datacontract test` als *den* Executor zu adoptieren.
Die Empfehlung bleibt **differenziert** und respektiert die ADR aus dem Zusatz-Doc:

- **Signals native Engine = der Enforcement-Executor.** Nur sie hält die nicht verhandelbaren
  Invarianten: G1 (kein SQL im Contract), G6 (sichtbares Gating), G8 (PII-Gate an der Quelle),
  read-only, Determinismus-Hash, Stale-Gating, Result-Store-Semantik. Diese Eigenschaften müsste man
  in einem CLI-Wrapper sonst **nachbauen**.
- **`datacontract-cli` (mit HANA-Engine) = portables Parität-/CI-Gate.** Über den bereits
  empfohlenen **One-Way-Export YAML → ODCS** (Zusatz-Doc §5) entsteht ein `servers`-Block **pro
  Backend**. `datacontract test --server <name>` wird in CI gegen jedes Backend gefahren und
  dient als *unabhängige Zweitmeinung* + liefert `breaking`/`lint`/`changelog` gratis. Es ersetzt
  nicht den Laufzeit-Enforcer.

```yaml
# odcs-export.yaml (generiert) — multi-server, ein Contract
servers:
  hana_prod:  { type: hana,       host: …, schema: SALES }      # Prämisse: Engine existiert
  dbx_prod:   { type: databricks, catalog: finance, schema: gold, http_path: … }
  hdlf_prod:  { type: s3,         location: s3://…/events/, format: delta }
models: { … aus guarantees.schema abgeleitet … }
```

So bekommt man **beides**: einen invariantentreuen Enforcer (Signal) *und* die breite, gepflegte
Backend-Abdeckung der CLI als Cross-Check — ohne das „single executor"-Prinzip im Enforcement-Pfad
zu brechen.

---

## 8 — Routing: welcher Dataset liegt wo?

Die Zuordnung Dataset → Backend kommt aus zwei Quellen, die das Repo bereits führt:

1. **Environment-Auswahl** (heute schon pro Run gewählt, `routers/checks.py`): trägt künftig
   `platform`. Ein Run ist immer *ein* Environment = *ein* Backend.
2. **Inventory/Lineage** (`data/inventory.json`, `data/lineage.json`): wird um ein `platform`-/
   `space`-Attribut pro Objekt erweitert, damit das Cockpit die Plattform-Herkunft anzeigen und
   die **Coverage-Map pro Backend** aufschlüsseln kann (HANA-Spaces vs. HDLF vs. Databricks).

Ein **plattformübergreifender Run** (ein Contract, mehrere Backends, z. B. dieselbe Dimension in
HANA *und* gespiegelt in Databricks) ist die Iteration über mehrere Environments mit demselben
kompilierten `DatasetConfig` — kein Sonderpfad, nur eine Schleife im Orchestrator.

---

## 9 — Inventory & Lineage über Plattformen

Der Executor prüft Garantien; **Inventory und Lineage** liefern den Kontext (welche Objekte gibt es,
wer speist wen, Coverage-Map). Auch dieser Pfad ist heute Datasphere-spezifisch — aber er ist genau
wie die Engine an wenigen, kapselbaren Stellen gekoppelt, und die **nachgelagerten Builder sind
bereits pur/backend-agnostisch**.

### 9.1 — Wie der Status quo extrahiert (drei Stufen)

`services/api/extraction.py` + `packages/dq_core/lineage/`:

1. **Quellen-Beschaffung** (`_gather_objects`) — getiert: Datasphere-**CLI** (bevorzugt, volle CSN) →
   **Catalog-REST** (`datasphere_catalog.py`, headless Fallback) → lokaler Snapshot. Ergebnis ist
   eine **normalisierte Objektliste**: `{technicalName, objectType, status, businessName, sql,
   definition(CSN)}`.
2. **Pro-Objekt-Assembly** (`build_inventory_object`) — Spalten aus CSN-`elements`, SQL-
   Rekonstruktion, **Objekt-Lineage-Kanten** aus CSN-Query (`FROM`/`JOIN`) und CDS-Associations.
3. **Graph-Bau** (`build_lineage_graph` + `build_column_lineage`) — `{nodes, edges, adjacency,
   upstream}`; Column-Lineage aus CSN-`projectionLineage` **oder** — Phase-2-Pfad — aus rohem SQL
   via **sqlglot**.

> **Schlüssel:** Stufen 2+3 sind framework-frei und hängen nur an (a) Spalten und (b) Kanten.
> *Woher* die kommen, ist austauschbar — exakt wie die vier Executor-Nähte (§3).

### 9.2 — Abbildung auf Databricks (Unity Catalog)

Unity Catalog liefert dieselben Bausteine, an mehreren Stellen sogar reicher als der Datasphere-
Katalog:

| Signal-Stufe | Datasphere (Status quo) | Databricks-Analog |
|--------------|-------------------------|-------------------|
| Objektliste | Catalog-REST `list_objects` / CLI | `system.information_schema.tables` · UC-REST `/api/2.1/unity-catalog/tables` · `SHOW TABLES` |
| Spalten | CSN `elements` | `information_schema.columns` · `DESCRIBE TABLE EXTENDED` |
| Objekt-Definition (SQL) | CSN `query` / CLI `read_object` | `information_schema.views.view_definition` · `SHOW CREATE TABLE` |
| **Objekt-Lineage** | CSN `FROM`/`JOIN`-Parse | **Laufzeit:** `system.access.table_lineage` / Lineage-REST `/api/2.0/lineage-tracking/table-lineage` · **Statisch:** `view_definition` parsen |
| **Column-Lineage** | `projectionLineage` / sqlglot | **Laufzeit:** `system.access.column_lineage` · **Statisch:** vorhandener sqlglot-Parser (`dialect="databricks"`) |
| Layer/Role/Confidence | `NamingModel`-Heuristik | **derselbe** `NamingModel` — unverändert wiederverwendbar |
| Status/Freshness | Catalog `status` | `DESCRIBE DETAIL` (`lastModified`) · `DESCRIBE HISTORY` (Delta-Commits) |

### 9.3 — Der eine echte Unterschied: Lineage-Herkunft (ein Gewinn)

- **Datasphere** = *statische* Lineage aus dem deklarierten CSN-Modell (was modelliert wurde).
- **Unity Catalog** = *Laufzeit-Lineage*, automatisch aus der Query-History erfasst, table- **und**
  column-level. Autoritativer (was wirklich lief), deckt aber nur bereits ausgeführte Beziehungen ab.

**Empfehlung:** UC-Laufzeit-Lineage als **Primärquelle**; für Kaltstart/ungenutzte Views den
**statischen `view_definition`-Parse** als Ergänzung — und der nutzt den **vorhandenen sqlglot-Pfad**
(`_sql_column_parser`) mit `dialect="databricks"`. Keine zweite Lineage-Engine, nur eine andere Quelle
für dieselbe.

### 9.4 — Integration: `CatalogSource`-Abstraktion (parallel zur Backend-Registry)

Analog zu `Backend`/`Dialect` (§4) eine Quell-Abstraktion, gekeyt auf `platform`:

```python
# parallel zu extraction._gather_objects
class CatalogSource(Protocol):
    def gather_objects(self, scope) -> list[NormalizedObject]: ...
    # NormalizedObject = {technicalName, objectType, columns, sql,
    #                     lineageEdges?, columnEdges?, status}

SOURCES = {
    "datasphere": DatasphereCatalogSource(),   # heutige CLI+REST-Logik, unverändert
    "databricks": DatabricksCatalogSource(),   # UC-REST/system-tables + sqlglot
}
```

Zwei Andock-Strategien für `DatabricksCatalogSource`, **beide ohne Eingriff in die puren Builder**:

1. **Kanten direkt liefern** (empfohlen): UC hat die Lineage schon berechnet → in das
   `lineageEdges`/`columnEdges`-Format mappen. `build_lineage_graph` läuft **unverändert** (liest
   `obj["lineageEdges"]`).
2. **SQL liefern**: `view_definition` als `sql`-Feld durchreichen → `build_column_lineage` zieht die
   Column-Kanten via sqlglot selbst.

Tiering bleibt wie heute: UC-REST/system-tables bevorzugt → `INFORMATION_SCHEMA`/`SHOW`-Fallback →
File-Snapshot zuletzt. Der `space`-Begriff verallgemeinert sich auf `catalog.schema` (3-teiliger
Namespace, §10 Querschnitt).

### 9.5 — Caveats (ehrlich)

- **Read-only passt perfekt:** `information_schema` und `system.*` sind reine Metadaten — keine
  Nutzdaten, deckt sich mit Signals Posture.
- **UC-Lineage muss aktiviert sein** und braucht Grants (`SELECT` auf `system.access`); sonst bleibt
  nur der statische Parse-Pfad.
- **SAP- vs. natives Databricks:** identisches UC darunter, Unterschied nur Auth/Endpoint — derselbe
  `platform`-Subtyp wie beim Executor.
- **CSN-spezifische Felder** (Associations, `@ObjectModel`-Annotations) haben kein UC-Pendant und
  entfallen dort sauber — nichts wird erfunden, exakt wie schon beim REST-Fallback heute.

> **Fazit:** Inventory ist über UC quasi geschenkt (reicher als der Datasphere-Katalog), Lineage ist
> sogar besser (Laufzeit statt nur deklariert), und die puren Builder bleiben unangetastet. Benötigt
> wird **eine** `DatabricksCatalogSource`, die UC ins normalisierte Objekt-/Kantenformat übersetzt.

---

## 10 — Querschnitt: was pro Backend neu durchdacht werden muss

- **Read-only-Durchsetzung.** Heute Policy + Aggregat-only. Pro Backend zusätzlich technisch
  absichern: HANA Read-Role/`SET TRANSACTION READ ONLY`; Databricks SQL-Warehouse mit
  `SELECT`-only-Grants im Unity-Catalog. Read-only ist **Connector-Konfiguration**, nicht nur
  Konvention.
- **PII-Gate (G8).** `diagnostics`-Rohzeilen-Pfad (`_fetch_diagnostic_rows`) muss pro Dialekt das
  `LIMIT`-/`TOP`-Rewrite korrekt erzeugen (Databricks `LIMIT`, HANA `LIMIT` — kompatibel; trotzdem
  pro Dialekt testen). Das Gate bleibt **an der Quelle**.
- **Timeouts (Naht B).** HANA: `SET 'statementTimeout'`. Databricks: Warehouse-/Statement-Timeout
  über Connector-Option statt Session-`SET` — der Dialekt kapselt das (`set_timeout` ggf. no-op +
  Connector-seitiges Timeout).
- **Identifier-Sicherheit (S2).** Die dreistufige Verteidigung (Regex → Inventar-Existenz →
  Quote-Escaping) bleibt; nur das *Quote-Zeichen* wird dialektabhängig (`"` vs `` ` ``). Der
  `SAFE_IDENTIFIER`-Regex im Compiler bleibt unverändert die erste Verteidigungslinie.
- **Determinismus-Hash (A4).** Erweitert um die `backend.id` + Dialekt-Version, damit ein
  Backend-Wechsel als Re-Kompilierung sichtbar ist.

---

## 11 — Phasenplan (inkrementell, jede Phase eigenständig wertvoll)

| Phase | Inhalt | Risiko |
|------|--------|--------|
| **P0** | Nähte A–D refaktorieren in `Dialect`/`Backend`-Interface; HANA als Default-Backend registrieren. **Null Verhaltensänderung.** | niedrig — reine Kapselung, durch bestehende Tests abgesichert |
| **P1** | Databricks-Dialekt + Connector (`databricks-sql-connector`). Deckt **SAP Databricks _und_ natives Databricks** in einem ab. Capability-Matrix + `skipped_unsupported`. | mittel — neuer Treiber, 3-teiliger Namespace |
| **P2** | HDLF: zunächst **Route A** (SQL-on-Files über HANA Data Lake) = HANA-Dialekt mit kleinen Overrides; **Route B** (Databricks über Delta) fällt aus P1 ab. | mittel — HDLF-Auth/Permission-Gap (Zusatz R7) |
| **PE** | `CatalogSource`-Abstraktion + `DatabricksCatalogSource` (Inventory & Lineage aus Unity Catalog, §9). Unabhängig von P1 priorisierbar — liefert die Coverage-Map auch ohne Executor. | mittel — UC-Lineage-Grants, sqlglot-Dialekt |
| **P3** | ODCS-Multi-Server-Export + `datacontract test` als CI-Parität-Gate (Prämisse: HANA-Engine). Liefert zugleich das `breaking`-Gate (Zusatz §5). | abhängig von der Prämisse |
| **P4** | Cockpit: Coverage-Map & Status-Grid **pro Plattform**; Inventory/Lineage um `platform` erweitert (baut auf PE). | niedrig |

P0 ist die einzige Voraussetzung für den Executor-Pfad; **PE steht orthogonal** und kann zuerst
kommen (Discovery vor Enforcement). P1–P4 sind danach unabhängig priorisierbar.

---

## 12 — Offene Punkte / Risiken

> **[H]** hoch · **[M]** mittel · **[L]** später

- **[H] HDLF-Route-Entscheidung.** Route A (über HANA) vs. Route B (über Databricks/Delta) pro
  Dataset — Performance, Auth (HDLF-Permission-Gap, Zusatz R7) und Freshness-Semantik (Commit-Zeit
  vs. Spalte) klären, bevor P2 gesetzt wird.
- **[H] HANA-Engine in `datacontract-cli`.** Existiert nur per Prämisse. Realweg: eigener Beitrag
  (PyHDB/`hdbcli`-Engine upstream) oder Fork. Aufwand/Maintenance-Last bewerten — sonst bleibt P3
  Vision.
- **[M] 3-teiliger Namespace im Compiler.** `[SCHEMA-MAP]` → `[NAMESPACE-MAP]`: optionales
  `catalog`-Segment sauber durch `bind_schema`/Templates ziehen, ohne G2 zu verwässern.
- **[M] SAP- vs. native-Databricks-Unterschiede.** Gleicher Connector, aber Auth (SAP-IdP/OAuth vs.
  PAT-Token) und Unity-Catalog-Verfügbarkeit prüfen — evtl. zwei `platform`-Subtypen.
- **[M] Capability-Paritätstests.** Jeder Dialekt braucht einen Conformance-Test, der dieselbe
  Garantie gegen ein bekanntes Dataset prüft und identische Pass/Fail-Entscheidung liefert
  (Mock + Integration).
- **[L] Cross-Platform-Konsistenz-Check.** „Dimension in HANA == Spiegelung in Databricks?" als
  *neue* Garantie-Familie — über die heutige Single-Backend-Logik hinaus, eigenes Folgekonzept.

---

## 13 — Abgrenzung: Mehrwert gegenüber Databricks-nativer DQ

Ehrliche Selbstprüfung — *wann* ist Signal auf Databricks ein Gewinn und wann nicht? Die Antwort
hängt an **einer** Frage: **Ist Databricks die ganze Welt oder *ein* Backend von mehreren?**

### 13.1 — Wo Databricks-nativ gewinnt (und Signal **nicht** konkurrieren sollte)

| Native Funktion | Warum nativ überlegen |
|-----------------|------------------------|
| **DLT-Expectations** (`expect_or_drop`/`fail`) | **Enforcement zur Schreibzeit** — droppt/quarantänisiert schlechte Zeilen *während* der Ingestion. Signal ist read-only, post-hoc, out-of-band; es **verhindert nicht**, dass schlechte Daten landen. Fundamental andere Posture. |
| **Lakehouse Monitoring** | Profiling, Drift, statistische Metriken — purpose-built, ausgereifter als Signals Rolling-Baselines/Miner. |
| **Unity-Catalog-Lineage** | Laufzeit-Lineage (table+column) — reicher als jede Rekonstruktion; Signal *konsumiert* es (§9), baut es nicht nach. |
| **UC-Constraints** (NOT NULL, CHECK, PK/FK) | In-Engine, teils erzwungen. |
| Betrieb | Kein zweites Tool, keine externe Orchestrierung. |

Auf der reinen „prüft Bedingung X"-Ebene **überlappt Signal stark mit DLT/Monitoring — und verliert.**
Daraus folgt die Positionierung: **nicht als konkurrierender Executor danebenstellen.**

### 13.2 — Wo Signal Mehrwert hat (orthogonal, nicht technisch)

1. **Cross-Plattform-Single-Pane** — *das* Kernargument. DLT deckt nur die Databricks-Scheibe ab;
   **HANA hat kein DLT-Äquivalent, HDLF noch weniger**. Signal vereint HANA + HDLF + Databricks unter
   *einem* Contract, *einem* Cockpit, *einem* Compliance-Modell. Kein einzelnes natives Tool kann das.
2. **Contract als verhandeltes Artefakt mit Lifecycle** — DLT-Expectations sind *Code in der
   Pipeline*. Signals Contract ist eine SQL-freie, Git-versionierte *Vereinbarung* mit
   Draft/Active/Deprecated, SemVer/Breaking-Governance, Approval, Producer/Consumer-Split, ODCS/ORD-
   Export. Trennt *Vereinbarung* von *Implementierung*.
3. **Vendor-Neutralität / kein Lock-in** — derselbe Contract läuft gegen HANA *und* Databricks; bei
   Migration/Spiegelung bleibt er erhalten, native Checks müsste man neu bauen.
4. **Konsumenten-gerichtete Compliance-Ampel** — read-only Status mit SLA-Fenstern und Incident-
   Timeline für *Konsumenten*; Databricks-Monitoring ist primär Producer-/Plattform-gerichtet.
5. **No-SQL-Authoring + PII-Gate an der Quelle** — Stewards formulieren Garantien ohne SQL.

### 13.3 — Die reife Architektur: *darüber*, nicht *daneben*

> **Databricks-nativ = Ausführungs-Substrat (Enforcement, Monitoring, Lineage).
> Signal = Governance-/Aggregations-Plane darüber, die das Native *konsumiert* statt dupliziert.**

Konkret: Signal sammelt DLT-Expectation-Ergebnisse, UC-Lineage und Monitoring-Metriken **ein** und
hebt sie ins plattformübergreifende Contract-/Compliance-Modell — statt eigene Checks danebenzufahren.
Auf Databricks **delegiert** Signal die Ausführung; auf HANA (wo nichts Vergleichbares existiert)
**führt es selbst aus**. Das ist §7 konsequent zu Ende gedacht: native Engine als Enforcer dort, wo
sie stark ist; Signal als invariantentreue Klammer.

### 13.4 — Entscheidungs-Faustregel

| Situation | Empfehlung |
|-----------|------------|
| Nur Databricks, keine Cross-Team-Governance-Not | **Signal bringt wenig** — DLT + Lakehouse Monitoring, ggf. OSS `datacontract-cli` fürs CI-Gate. |
| Nur Databricks, aber echte Datenprodukt-Governance (Versionierung, Consumer-Verträge, Approval) | **Signal bringt die Vertrags-/Lifecycle-Ebene**, die Databricks nicht hat — Wert ohne Plattform-Vielfalt. |
| BDC heterogen (HANA + HDLF + Databricks) | **Signal differenziert und schwer ersetzbar** — Vereinheitlichung + HANA-Lücke kann kein natives Tool liefern. |

---

## 14 — Kernaussage

Signal muss für Multi-Plattform **nicht** seine Engine aufgeben und auch nicht pro Backend eine neue
bauen. Es muss **vier klar lokalisierte Nähte** hinter eine `Dialect`/`Backend`-Abstraktion ziehen
(P0), wonach **vier Backend-Klassen auf zwei Dialekte** (HANA, Databricks) kollabieren — HDLF wird je
nach Route einer der beiden. Der Contract bleibt SQL- und backend-frei; das Backend ist
Laufzeit-Bindung wie heute das Schema. `datacontract-cli` (mit HANA-Engine) ist dann das **portable
Parität-Gate** daneben, nicht der Enforcer. So bleibt jede Invariante (G1/G2/G6/G7/G8, read-only,
Determinismus) erhalten — und Signal prüft die **ganze** Business Data Cloud aus *einem* Contract.
</content>
</invoke>
