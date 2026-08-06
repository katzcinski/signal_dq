# datacontract-cli im Signal-Workflow — Feature-Landkarte fürs Schaubild

> Zweck: Vorlage, um ein **Schaubild** zu zeichnen, das zeigt, *wo* die
> `datacontract-cli` an Signals nativen Pfad andockt — und wo bewusst **nicht**.
> Leitsatz aus `docs/REVIEW_Tool_v1_Befunde.md`: die CLI ist eine **Beigabe
> in CI/Tooling auf dem ODCS-Export**, niemals ein zweiter Check-Runner.
> Signals Alleinstellungsmerkmal — der **lesende SAP-HANA-Runner** — bleibt
> unberührt; die CLI kann gar nicht gegen HANA laufen.

---

## 1. Der native Signal-Pfad (Ist-Zustand, ohne CLI)

Das ist die Achse, um die herum das Schaubild gebaut wird. Jeder Kasten ist ein
realer Baustein im Repo.

```
contracts/*.yaml          packages/dq_core/                                      services/  apps/
─────────────────         ──────────────────────────────────────────────────    ─────────  ─────
                                                                                  
┌───────────────┐  G1  ┌───────────┐  G1   ┌───────────┐      ┌──────────────┐   ┌───────┐  ┌─────────┐
│ Contract YAML │─────▶│ validator │──────▶│ compiler  │─────▶│ check_engine │──▶│ store │─▶│ Cockpit │
│ (semantisch,  │ json │ .py       │ guar- │ .py       │ Check│ .py          │   │ sqlite│  │ React   │
│  SQL-frei)    │schema│           │ antees│  +library/│ Def  │ liest HANA   │   │ /hana │  │ (Grid,  │
│               │      │           │  →SQL │ check_lib │ (SQL)│ NUR LESEND   │   │       │  │  SLA …) │
└───────────────┘      └───────────┘       │ .json     │      └──────────────┘   └───────┘  └─────────┘
                                           └───────────┘             │              │  ▲
   Garantie-Familien:                       SQL-Templates            │ PII-Gate(G8) │  │ Compliance/
   schema·keys·not_null·                     (~20 Checks)            │ Rohzeilen    │  │ SLA-Events
   completeness·volume·                                              │ nur mit      │  │ (NIE im YAML)
   freshness·referential                                             │ Freigabe     │  │
                                                                                       
            ┌───────────────────────────────────────────────────────────────────────────────┐
   GATES    │ G1 kein SQL im Contract · G2 Schema erst zur Laufzeit · G3 Breaking⇒Major-Bump  │
   (CI)     │ G5 Engine-Regression · G6 Gating sichtbar · G7 dq_core frameworkfrei · G8 PII   │
            └───────────────────────────────────────────────────────────────────────────────┘
```

**Kernaussage fürs Bild:** Von der Garantie bis zum Resultat gibt es **keinen
Roh-SQL-Pfad**. `compiler.py` ist der einzige Ort, an dem SQL entsteht, und zwar
ausschließlich aus `check_library.json`. Das ist Signals Substanz — und der
Grund, warum die CLI **nicht** in diese Achse gehört.

---

## 2. Wo die datacontract-cli andockt — die Touchpoints

Die CLI hängt sich **seitlich** an genau einer Stelle ein: dem **ODCS-Export**
(`packages/dq_core/contract/odcs_export.py`, `to_odcs()`). Dieser Export ist die
verlustfreie Brücke zum Standard (ODCS v3.1, Bitol / LF AI & Data). Alles, was
die CLI tut, beginnt an diesem Artefakt — nie an der Live-Engine.

```
                                  ┌──────────────────────────────────────────────┐
                                  │           datacontract-cli (extern)           │
                                  │            läuft in CI / lokal,               │
                                  │            NIE in dq_core (G7)                 │
                                  └──────────────────────────────────────────────┘
                                        ▲          ▲          ▲          ▲
                                        │ breaking │ lint     │ export   │ import
                                        │ changelog│          │          │
                                        │          │          │          │
   contracts/*.yaml                     │          │          │          │
        │                               │          │          │          ▼
        ▼                          ┌─────────────────────┐         (Reverse: aus
   ┌───────────┐   to_odcs()       │   *.odcs.yaml       │          bestehendem
   │ validator │ ────────────────▶ │  (ODCS v3.1,        │          SQL/Avro/dbt/
   │ compiler  │   Einweg-Export   │   Einweg-Artefakt)  │          Glue → Contract)
   │  …native  │                   └─────────────────────┘
   │  Achse    │                          │
   └───────────┘                          ▼  export-Ziele
                                   dbt · JSON Schema · Avro · Protobuf ·
                                   SQL-DDL · SodaCL · Great Expectations ·
                                   pydantic · SQLAlchemy · HTML-Katalog …
```

**Schaubild-Hinweis:** Die CLI-Box gehört **außerhalb** des `dq_core`-Rahmens
(G7 verbietet Framework-/Tool-Importe in der Engine) und berührt nur das
`*.odcs.yaml`-Artefakt, nicht die Pfeile zwischen compiler → engine → store.

---

## 3. Feature-für-Feature — Detail für die Legende

Jede Zeile ist ein eigener Pfeil/Knoten im Schaubild. Spalte „Status" zeigt, ob
es bei euch schon existiert.

| # | CLI-Feature | Was es tut | Andockpunkt im Workflow | Nutzen für Signal | Status |
|---|---|---|---|---|---|
| F1 | **`datacontract breaking`** | Vergleicht zwei Contract-Versionen, klassifiziert Breaking vs. non-breaking | CI-Job auf `*.odcs.yaml` (base vs. head) | **Zweitmeinung** zu eurem homegrown `gate_g3.py` / `diff.py` (Stufe 1) | ✅ **schon verdrahtet** — Job `odcs-second-opinion` in `ci.yml`, advisory/non-blocking |
| F2 | **`datacontract changelog`** | Erzeugt menschenlesbaren Änderungsbericht zwischen Versionen | CI / Release, auf `*.odcs.yaml` | Automatischer Changelog für Konsumenten beim Versionssprung | ◻️ optional, leicht aus F1-Job ableitbar |
| F3 | **`datacontract lint`** | Validiert die YAML **formal gegen die ODCS-Spec** | CI, direkt nach `to_odcs()` | Garantiert, dass euer Export spec-konform bleibt (Schema-Drift im Export erkennen) | ◻️ ergänzt eure native `validator.py` (die das *kanonische* Schema prüft, nicht ODCS) |
| F4 | **`datacontract export`** | Generiert Artefakte aus dem Contract: dbt, JSON Schema, Avro, Protobuf, SQL-DDL, SodaCL, Great-Expectations-Suite, pydantic, SQLAlchemy, RDF, GraphQL … | On-demand, auf `*.odcs.yaml` | Ein Contract → viele Downstream-Formate, ohne Handarbeit | ◻️ ihr exportiert heute nur ODCS selbst |
| F5 | **`datacontract import`** | **Reverse-Engineering**: erzeugt einen Contract aus bestehendem SQL-DDL, Avro, JSON Schema, dbt, AWS Glue, BigQuery, ODCS … | Onboarding neuer Datasets | Schneller Erst-Entwurf eines Contracts aus vorhandenen Strukturen | ◻️ habt ihr nicht; spart Tipparbeit beim Onboarding |
| F6 | **`datacontract catalog`** | Statischer **HTML-Katalog** aller Contracts | Build-Artefakt / GitHub Pages | Verteilbarer Katalog „außerhalb" des Cockpits (z. B. für Konsumenten ohne Zugang) | ◻️ Cockpit deckt internen Fall ab |
| F7 | **`datacontract test`** | Führt Quality-Checks aus — seit **v1.0.0 via ibis→`sqlglot`** (nicht mehr Soda Core; SodaCL/GX nur Export); Backends u. a. Databricks und Delta (`type: databricks` via `[databricks]`, oder Object-Store + `format: delta` via `[duckdb]`) | — für HANA bewusst **nicht** genutzt; tragfähig nur in der BDC/Databricks-Plane | ⛔ **kein HANA-Backend** (kein `type: hana`/ibis-HANA); `type: sql` bringt Roh-SQL in den Contract → G1. Signals HANA-Runner ist hier überlegen. Delta/Databricks ✅ siehe Bewertung §8 | ⛔ **nicht für HANA** · ✅ nur BDC/Delta |

**Legende fürs Bild:** ✅ = bereits aktiv · ◻️ = sinnvoller Ausbau · ⛔ = bewusst ausgeschlossen.

---

## 4. Was sind „die Checks" der CLI? (für die Detail-Box)

Wichtig fürs Schaubild: Die CLI hat **keinen festen Check-Katalog** wie eure
`check_library.json`. Sie kennt zwei Ebenen:

```
┌─ Ebene A: Schema-Validierung "für umsonst" ──────────────────────────────┐
│  direkt aus der Feld-Definition, ohne SQL:                               │
│  Typ · required(not-null) · unique · primaryKey · enum · pattern(regex)  │
│  · format(email/uuid/…) · minLength/maxLength · minimum/maximum          │
│  ≈ deckt Signals Familien: schema·keys·not_null·allowed_values·          │
│    pattern_match·string_length·value_range                              │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Ebene B: quality:-Sektion ──────────────────────────────────────────────┐
│  type: library  →  benannte Metrik (rowCount, nullValues …)  KEIN SQL   │
│  type: sql      →  inline query: + Schwellwert               ROH-SQL     │
│  (type: custom/sodacl: seit CLI v1.0.0 NICHT mehr ausgeführt → migrieren)│
│  Engine seit v1.0.0: ibis → sqlglot (nicht mehr Soda Core);             │
│    SodaCL/GX nur noch Export-Ziele                                      │
│  Backends: Snowflake·BigQuery·Postgres·Databricks·DuckDB/Delta·S3       │
│  ⚠ KEIN SAP HANA · ⚠ type:sql bringt Roh-SQL in den Contract → Bruch G1 │
└──────────────────────────────────────────────────────────────────────────┘
```

Fazit für die Legende: Die „komplette Bibliothek an Checks" ist realistisch
**Schema-Validierung + `library`-Metriken (begrenzt) + Roh-SQL als Escape-Hatch**
(Engine seit v1.0.0: ibis/`sqlglot`). Das ersetzt Signals HANA-spezifische Checks
(inkl. SAP-Spezialitäten BSEG-Balance, BKPF-Orphan, Fiscal Completeness,
Replication Lag) **nicht** — und kann mangels HANA-Backend ohnehin nicht gegen
eure Quelle laufen.

---

## 5. Signals eigene Check-Bibliothek (Gegenstück zur CLI, fürs Bild)

Quelle: `packages/dq_core/library/check_library.json` (~20 Checks, 5 Kategorien).
Diese Box gehört als **Kontrast** neben Ebene A/B der CLI:

| Kategorie | Checks |
|---|---|
| **Vollständigkeit** | `row_count` · `missing` · `completeness_pct` |
| **Konsistenz** | `duplicate` · `duplicate_composite` · `duplicate_approx` · `invalid` · `value_range` · `allowed_values` · `pattern_match` · `string_length` · `reference_integrity` |
| **Verteilung & Aggregate** | `aggregate_range` |
| **Aktualität & Sonstiges** | `freshness` · `schema` (change) · `custom_sql` |
| **SAP / BDC** | `sap_bseg_balance` · `sap_bkpf_orphan` · `sap_fiscal_completeness` · `sap_replication_lag` · `sap_key_plausibility` |

Die SAP/BDC- und HANA-Systemsicht-Checks (`SYS.TABLE_COLUMNS`,
`APPROXIMATE_COUNT_DISTINCT`, `LIKE_REGEXPR`, `SECONDS_BETWEEN`) sind genau das,
was die CLI **nicht** kann — der Differenzierungs-Kern.

---

## 6. Empfohlene Schaubild-Aufteilung (drei Zonen)

Vorschlag, wie du die Flächen visuell trennst:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ZONE 1 — SIGNAL NATIVE (die Wertschöpfung, geschlossener Kreis)             │
│  Contract YAML → validator → compiler(+check_library) → engine(HANA, lesend) │
│  → store → API → Cockpit       [Gates G1–G8 als Rahmen]                      │
└─────────────────────────────────────────────────────────────────────────────┘
                              │ to_odcs()  (Einweg)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ZONE 2 — INTEROP-ARTEFAKT:  *.odcs.yaml  (ODCS v3.1, der Übergabepunkt)      │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ZONE 3 — datacontract-cli (extern, CI/Tooling — NICHT in dq_core, G7)       │
│  ✅ breaking (aktiv)  ◻️ changelog · lint · export · import · catalog         │
│  ⛔ test gegen HANA (kein type:hana · bricht G1)                              │
│  ✅ test nur BDC/Delta: type:databricks ODER object-store + format:delta      │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Zone 1** kräftig/zentral zeichnen — das ist das Produkt.
- **Zone 2** als schmale Brücke (ein Artefakt, ein Pfeil) — verlustfrei, einweg.
- **Zone 3** abgesetzt, gestrichelter Rahmen = „extern/optional"; den `test`-Knoten
  durchgestrichen oder rot als bewusst ausgeschlossen markieren.

---

## 7. Anker-Referenzen (für Fußnoten im Schaubild)

| Baustein | Datei |
|---|---|
| Contract-Beispiel | `contracts/DS_SALES_ORDERS.yaml` |
| Validator (G1) | `packages/dq_core/contract/validator.py` |
| Compiler (einziger SQL-Erzeuger) | `packages/dq_core/contract/compiler.py` |
| Check-Bibliothek | `packages/dq_core/library/check_library.json` |
| ODCS-Export (Brücke) | `packages/dq_core/contract/odcs_export.py` → `to_odcs()` |
| Homegrown Breaking-Diff | `packages/dq_core/contract/diff.py` · `gate_g3.py` |
| CLI-Zweitmeinung (aktiv) | `.github/workflows/ci.yml` → Job `odcs-second-opinion` |
| Voranalyse / Begründung | `docs/REVIEW_Tool_v1_Befunde.md` (§ ODCS / datacontract-cli) |
