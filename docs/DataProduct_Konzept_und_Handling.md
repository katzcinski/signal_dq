# Datenprodukte in Signal — Konzept, Definition und Workflow

**Zielgruppe:** Beratung, Produktteams, Plattform-Entwicklung · **Stand:** 2026-06-28
**Quellen:** ADR-0001, ADR-0003, ADR-0004, Tooldokumentation.md, Betriebsmodi_Lite_und_Full.md

---

## 1. Grundbegriffe — was ein Datenprodukt ist (und was nicht)

### 1.1 Datenprodukt

Ein **Datenprodukt** ist in Signal *das Ganze*: die Menge aller Objekte in einer einzigen Ownership
über alle Layer hinweg (Raw → Integrated Core → Business Core → Serving). Es ist ein
**Eigentums-Aggregat**, kein einzelnes Dataset.

```
 ┌─────────────────────────────────────────────────────────┐
 │  Datenprodukt "sales_overview"  (Owner: team-sales)     │
 │                                                         │
 │  [RAW]            [CORE]          [SERVING]             │
 │  SRC_ORDERS   →   INT_ORDERS  →   DS_REVENUE_SUMMARY  ──│──▶ Consumer-Team
 │  SRC_PRODUCTS →   INT_PRODUCTS    (Output-Port)         │
 │                                                         │
 │  ← interieur (abgeleitet aus Lineage) →  ← Port →      │
 └─────────────────────────────────────────────────────────┘
```

**Kritische Abgrenzung:** Ein Datenprodukt ist *nicht* dasselbe wie ein Dataset oder ein Contract.

| Begriff | Was es beschreibt |
|---|---|
| **Datenprodukt** | Das Ganze — alle Objekte einer Ownership inkl. Interieur |
| **Contract** | Nur die Ränder — die Qualitätszusage an einem Output-Port |
| **Dataset** | Einzelnes technisches Objekt in Datasphere/HANA |
| **Guarantee** | Eine semantische Qualitätseigenschaft im Contract (kein SQL) |
| **Check** | Die vom Compiler erzeugte, ausführbare SQL-Prüfung |

### 1.2 Wichtigster Grundsatz: Contracts beschreiben Ränder, nicht Objekte

> *„Ein Data Contract ist nur der Rand des Datenprodukts — das Versprechen an der
> Konsumgrenze. Das Innere des Produkts ist interne Angelegenheit."*
>
> — ADR-0001, §10

---

## 2. Das Datenprodukt-Manifest

Ein Datenprodukt wird durch ein **dünnes Manifest-YAML** unter `products/<name>.yaml`
deklariert. Das Manifest listet **nur die Ränder und die Owner-Hülle** — das Interieur
wird aus der Lineage abgeleitet.

### 2.1 Schema

```yaml
product: sales_overview                    # Technischer Bezeichner (SQL-safe)
owners: [team-sales]                       # Owner-Hülle — wirkt als Walk-Stopp-Bedingung

output_ports:                              # 1:N Output-Ports; pro Port ein Contract
  - dataset: DS_REVENUE_SUMMARY            # Verweist auf contracts/DS_REVENUE_SUMMARY.yaml

inbound:                                   # Nur bei echter Fremd-Abhängigkeit deklarieren
  - depends_on: { product: kunde, version: "1.2.0" }

# interieur: NICHT gelistet — wird automatisch aus der Lineage abgeleitet
```

### 2.2 Felder im Detail

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `product` | ja | Technischer Name (SQL-Identifier-Pattern `^[A-Za-z_][A-Za-z0-9_]*$`) |
| `owners` | ja | Owner-Set (Team-IDs); wirkt als Stopp-Bedingung im Lineage-Walk |
| `output_ports` | ja | Liste der Output-Ports; jeder Port referenziert einen Contract |
| `inbound` | nein | Nur wenn ein anderes Team Quelle besitzt (Fall B, geketteter Contract) |

### 2.3 Was das Manifest nicht enthält

- **Kein Interieur-Listing** — interne Core-/Raw-Objekte werden nie aufgezählt
- **Keine Version am Produkt** — SemVer lebt pro Output-Port-Contract, nicht am Produkt
- **Kein Lifecycle-Feld** — Lifecycle wird aus den Port-Contracts abgeleitet:
  - mind. ein Port `active` → Produkt `active`
  - alle Ports `deprecated` → Produkt `deprecated`
  - nur `draft`-Ports → Produkt `draft`

---

## 3. Contracts — die Qualitätszusagen an den Rändern

### 3.1 Was ein Contract ist

Ein **Contract** ist ein semantisches Qualitätsversprechen in reinem YAML — **kein SQL**.
Er beschreibt *was* garantiert wird (Strukturen, Frische, Vollständigkeit, Mengen),
nie *wie* die Prüfung technisch implementiert ist. Der Compiler übersetzt das einmalig in SQL.

```yaml
product: DS_REVENUE_SUMMARY
kind: consumer_contract            # Governance-Contract (nicht internes Gate)
dataset: DS_REVENUE_SUMMARY
owned_by: product
lifecycle: active
version: "1.0.0"
owners: [team-sales]

guarantees:
  schema:
    columns: [REGION, PERIOD, REVENUE, CURRENCY, UPDATED_AT]
    mode: closed                   # keine weiteren Spalten erlaubt
  keys:
    - columns: [REGION, PERIOD]
      unique: true
      severity: critical
  not_null:
    - columns: [REGION, PERIOD, REVENUE]
      severity: fail
  volume:
    min_rows: 1000
    severity: warn
  freshness:
    column: UPDATED_AT
    max_age: PT26H                 # ISO-8601-Dauer: 26 Stunden
    severity: warn
```

### 3.2 Contract-Kinds

| Kind | Bedeutung | Governance-Zeremonie |
|---|---|---|
| `internal_gate` | Interne Qualitätsprüfung, keine externe Partei | Keine (kein SemVer, kein Approval) |
| `consumer_contract` | Versprechen des Produzenten an den Konsumenten | Vollständig (SemVer, Approval, G3) |
| `provider_contract` | Absicherung eines eingehenden Feeds | Vollständig |

Nur `consumer_contract` und `provider_contract` haben eine ODCS-Exportoption; `internal_gate`
ist immer projektinterner Governance-Artefakt.

### 3.3 Guarantee-Typen

| Guarantee | Was wird geprüft | Beispiel |
|---|---|---|
| `schema` | Spaltenliste (open/closed mode) | `columns: [A, B], mode: closed` |
| `keys` | Eindeutigkeit | `columns: [ORDER_ID], unique: true` |
| `referential` | Fremdschlüssel-Integrität | `fk: [CUST_ID], parent: CUSTOMERS` |
| `freshness` | Datenstaleness (Zeitstempel-Spalte) | `column: TS, max_age: PT26H` |
| `volume` | Zeilenanzahl-Grenzen | `min_rows: 1000, baseline: rolling` |
| `completeness` | NULL-Anteil | `column: CUST_ID, min_pct: 99.5` |
| `not_null` | Kein NULL erlaubt | `columns: [ORDER_ID, DATE]` |
| `checks[]` | Bibliotheks-Check direkt | `id: invalid, params: {...}, expect: < 10` |

**Gate G1** — kein Guarantee-Feld darf SQL-Syntax enthalten; der Validator blockiert
Schlüsselwörter (`SELECT`, `;`, `--`, `UNION` etc.) in allen nicht-Freitext-Feldern.

### 3.4 Contract-Lifecycle

```
            PUT /{product}
                 │
                 ▼
           ┌──────────┐
           │  DRAFT   │◄────── Jede PUT-Operation resettet auf draft
           └──────────┘
                 │
        POST /{product}/diff        ← Vergleich gegen .active.yml (Gate G3)
                 │
        POST /{product}/approve     ← Gate G3: Breaking Change → Major-Bump nötig
                 │
                 ▼
           ┌──────────┐
           │  ACTIVE  │ ─── .active.yml wird geschrieben (Git-Commit)
           └──────────┘
                 │
       POST /{product}/deprecate
                 │
                 ▼
          ┌────────────┐
          │ DEPRECATED │
          └────────────┘
```

Im **Lite-Modus** überspringt `POST /{product}/certify` alle Zwischenschritte:
seed → validate → compile → approve in einem Aufruf.

---

## 4. Vom Contract zur ausführbaren Prüfung — Compilation

### 4.1 Was der Compiler tut

Der Compiler (`packages/dq_core/contract/compiler.py`) übersetzt semantische Guarantees
deterministisch in SQL-Templates aus der Check-Bibliothek (`check_library.json`, v6, 20+ Checks).

```
Contract-YAML
    │
    ├─ validate_contract()  ──── G1: Kein SQL in Guarantees
    │
    ├─ compile_contract()
    │       │
    │       ├─ Identifier-Prüfung (S2, 3-stufig)
    │       │       ├─ Regex: ^[A-Za-z_][A-Za-z0-9_]*$
    │       │       ├─ Inventar-Abgleich (optional)
    │       │       └─ Quote-Escaping-Defense
    │       │
    │       └─ Template-Bindung: Guarantee → Check-Library → SQL-Template
    │               {schema} bleibt Platzhalter bis zur Laufzeit (Gate G2)
    │
    └─ DatasetConfig mit checks: list[CheckDef]
            └─ compiler_hash (SHA256, 16 hex) — Reproduzierbarkeits-Nachweis
```

### 4.2 Beispiel: guarantee → check

**Guarantee im Contract:**
```yaml
guarantees:
  freshness:
    column: UPDATED_AT
    max_age: PT26H
    severity: warn
```

**Kompiliertes SQL-Template:**
```sql
SELECT
  CASE
    WHEN MAX("UPDATED_AT") IS NULL THEN 1
    WHEN SECONDS_BETWEEN(MAX("UPDATED_AT"), CURRENT_TIMESTAMP) > 93600 THEN 1
    ELSE 0
  END AS result
FROM "{schema}"."DS_REVENUE_SUMMARY"
```

`{schema}` wird erst zur Laufzeit durch `bind_schema(schema_name)` ersetzt — **Gate G2**
verhindert hartcodierte Schema-Namen in Packages und Services.

### 4.3 Determinism Hash

Jede Compilation wird mit einem reproduzierbaren Hash gestempelt:

```python
compiler_hash = sha256(f"{contract_hash}:{library_version}")[:16]
```

Derselbe Contract + dieselbe Library-Version → immer derselbe Hash → auditierbare,
deterministische Compilation.

---

## 5. Interieur: abgeleitetes Innenleben des Datenprodukts

### 5.1 Der Owner-gegatete Upstream-Walk

Das Interieur eines Datenprodukts wird **nicht deklariert**, sondern aus der Lineage
rückwärts abgeleitet, ausgehend vom Output-Port:

```
Output-Port (DS_REVENUE_SUMMARY)
        │
        ▲ rückwärts durch Lineage-Graph
        │
   ┌────┴────┐
   │         │
INT_ORDERS  INT_PRODUCTS       ← interieur (interne Gates)
   │         │
   ▲         ▲
SRC_ORDERS  SRC_PRODUCTS      ← Stopp: externer Source-Knoten

Walk stoppt bei:
  (a) Output-Port eines ANDEREN Owner-Sets → Inbound-Dependency
  (b) Externer Source-Knoten (S4:*, ext)   → Inbound-Source-Kandidat
  (c) Bereits besuchtem Knoten
```

### 5.2 Intent vs. Reality — Reconciliation-Befunde

| Befund | Bedeutung | Konsequenz |
|---|---|---|
| **Boundary-Leak** | Fremdes Team konsumiert intern, kein Port deklariert | → Port/Contract anlegen |
| **Over-Declaration** | Port deklariert, kein grenzüberschreitender Konsum | → Tier-0-Verdacht |
| **Contested-Interior** | Zwei Produkte beanspruchen dasselbe Interieur-Objekt | → Foundation-Product-Kandidat |
| **Orphan-Interior** | Objekt speist Port, kein Produkt beansprucht es | → Manifest erweitern |
| **Dangling-Port** | Port im Manifest, kein Objekt/Contract | → Drift |

---

## 6. Betriebsmodi: Lite vs. Full

| Dimension | Lite | Full |
|---|---|---|
| Contract-Kind | `internal_gate` oder einfacher Consumer-Contract | `consumer_contract` / `provider_contract` |
| SemVer | Nicht erzwungen | Pflicht (G3) |
| Approval | Kein separater Schritt | `POST /approve` mit G3-Prüfung |
| Certify-Shortcut | `POST /certify` (alles in einem) | — |
| Breaking Change | Keine Blockade | Blockiert ohne Major-Bump |
| ODCS-Export | Optional | Empfohlen |
| Zielgruppe | Schnelle interne Gates | Produkt-zu-Produkt-Verträge, externe Consumer |

Die Wahl des Modus ist **orthogonal zur Speichertechnologie** (HANA, HDLF) und zum Tier.

---

## 7. Konvergenz mit Data Product Studio (BDC)

> **Stand und Einschränkung:** Die genaue API des Data Product Studio und die technischen
> Details der ORD-Emission sind zum Zeitpunkt dieser Dokumentation nicht vollständig
> spezifiziert (Verifikationspunkte V2/V5 aus ADR-0003 offen). Die folgenden Ausführungen
> basieren auf ADR-0003 (2026-06-22) und ADR-0004 (2026-06-22). Annahmen über die
> technische Struktur von Studio-Produkten sind explizit gekennzeichnet.

### 7.1 Was sich *nicht* ändert — die Konzept-Ebene

Signals Konzept-Ebene ist **speicher-agnostisch**. Folgendes gilt für Studio-Produkte
identisch wie für klassische Datasphere-Objekte:

- `boundary`-Klassifikation (internal/inbound/outbound)
- Tiering-Modell (Tier 0/1/2 × Lite/Full)
- Das Manifest-Modell (dünner Deklarationsrahmen, Interieur aus Lineage)
- Compliance-Ampel und Incident-System

### 7.2 Was sich ändert — die Enforcement-Ebene

Signals einziger Executor ist **GX-on-HANA** (`hdbcli`, read-only). Jeder Check ist ein
SQL-Template gegen `"{schema}"."{dataset}"`. Damit gilt:

> **Signal enforced an der SQL-erreichbaren Oberfläche eines Datenprodukts.**

#### Entscheidungsbaum

```
Studio-Datenprodukt (Custom, BDC)
        │
        ▼
 Output-Port spricht SQL?
  (HANA-View / SQL-on-Files / ODBC)
        │
   JA ─┘    NEIN ─────────────────────────────────────┐
   │                                                   │
   ▼                                           SQL-erreichbare
Direktes Enforcement                           Repräsentation?
GX-on-HANA gegen schema.object                         │
                                              JA ──────┘   NEIN
                                              │               │
                                     Transitives         Out-of-scope
                                     Enforcement         für Executor
                                     an SQL-Repr.        (kein 2. Executor!)
        │                                    │
        ▼                                    ▼
   boundary?                            boundary?
  outbound → Outbound-Contract        (unveränderte Governance)
  internal → Internes Quality Gate
```

#### Die drei Fälle

| Fall | Produkt-Typ | Signal-Enforcement | Governance |
|---|---|---|---|
| **A — Happy Path** | HANA-Space-Produkt oder HDLF mit SQL-on-Files-View | Direkt, 20 Checks ohne Änderung | Vollständig |
| **B — Transitiv** | HDLF ohne SQL-Sicht, aber SQL-erreichbare Upstream-Repräsentation | An der SQL-Repräsentation | Vollständig (Deklaration ≠ Enforcement) |
| **C — Out-of-scope** | Reines Delta Share / Object Store ohne SQL-Oberfläche | **Nicht prüfbar** — kein zweiter Executor | Governance bleibt, `monitored: false` |

### 7.3 Technische Struktur eines Studio-Produkts

*Annahme (nicht verifiziert, V2 offen):* Ein Custom Data Product aus dem Studio ist ein
Fluss mehrerer Objekte, die nach folgendem Muster aufgebaut sein dürften:

```
 Input                  Transformation(en)              Output
 (inbound)              (Interieur)                    (output port)
 SAP-Standard-      →   join / clean / aggregate   →   SALES.ORDERS_CURATED
 produkt oder           Zwischen-Files / -Views         (SQL-on-Files-View
 HDLF-Roh-File                                          oder HANA-View)
 [type: unknown]        [type: transformation-flow]     [type: views]
```

Das Manifest für dieses Produkt würde lauten:

```yaml
product: sales_orders_curated
owners: [team-fin]
output_ports:
  - dataset: ORDERS_CURATED              # SQL-on-Files-View: SALES.ORDERS_CURATED
inbound:
  - depends_on: { product: kunde, version: "1.2.0" }
# Transformation-Zwischenschritte: von Lineage abgeleitet, nicht gelistet
```

### 7.4 HDLF-spezifische Besonderheiten

| Aspekt | Verhalten |
|---|---|
| **Adressierung** | `"{schema}"."{view}"` über SQL-on-Files-View — identisch zu HANA (V1 gelöst) |
| **Schema/Closed-Mode** | Über View-Spalten unverändert — aber `SYS.TABLE_COLUMNS` muss durch `SYS.VIEW_COLUMNS` ergänzt werden (G-8, jetzt gefixt) |
| **Freshness** | Erwartet eine Datum-Spalte; bei Files ggf. Lade-/Partitionsspalte nötig (V3a offen) |
| **Volume/row_count** | `COUNT(*)` via Virtual Table — korrekt, aber ggf. teuer (Full-Scan bei Parquet) |
| **Discovery** | HDLF-/SQL-on-Files-Objekte müssen im Inventar erfasst sein (V5 offen) |

### 7.5 ORD/ODCS als einseitige Derivate

Das Studio emittiert ORD-Descriptoren; Signal erzeugt ODCS-Exports. In beiden Fällen gilt:

- Das **Contract-YAML** bleibt einzige Source of Truth
- ORD und ODCS sind **Derivate**, nicht ko-authored Quellen
- Ein Produkt mit mehreren physischen Ports (Delta Share **und** SQL-on-Files) hat pro
  *governter Grenze* **einen** Outbound-Contract (Transport-Äquivalenz)

### 7.6 Faustregeln

1. **SQL-Output-Port = überwachbar.** Das ehrliche Kunden-Framing: Tier-2-Produkte sollten
   immer einen SQL-Port bekommen.
2. **Delta Share ist kein SQL-Endpoint.** Direkt nicht prüfbar; transitiv enforcen oder
   ehrlich als `monitored: false` führen.
3. **Derive überall, enforce nur an SQL.** Der ganze Fluss wird aus der Lineage abgeleitet;
   gecheckt wird nur, wo ein Objekt SQL spricht.
4. **Kein zweiter Executor.** Object-Store-/Spark-Enforcement wird abgelehnt (G7, single executor).
5. **Out-of-scope ≠ out-of-scope für Governance.** Ein Delta-Share-Output ist nicht prüfbar,
   aber das stärkste Discovery-Signal — deklariert, entdeckt, `monitored: false`.

---

## 8. Sicherheitsgates

| Gate | Invariante | Wo erzwungen |
|---|---|---|
| **G1** | Kein SQL in Contracts — nur semantische Guarantees | `validator.py` (JSON-Schema + SQL-Keyword-Scan) |
| **G2** | Schema nie hardcodiert — immer `{schema}`-Platzhalter | `compiler.py`, CI grep auf `"CENTRAL"` |
| **G3** | Breaking Change erfordert Major-Bump | `contracts.py` POST `/approve` |
| **G6** | Alle CheckResult.states definiert und persistiert | `engine/models.py` + Store |
| **G7** | `dq_core` ist framework-frei (kein FastAPI/Flask) | CI import-check |
| **G8** | PII-Gate — Rohdaten verlassen HANA nie ohne Opt-in | Store, `_allow_diagnostics` |
| **S2** | Identifier-Safety: 3-stufige Verteidigung | Regex → Inventar-Check → Quote-Escaping |
| **S5** | Fail-closed bind — `AUTH_MODE=noauth` nur auf Loopback | `main.py`, `assert_bind_policy` |

---

## 9. API-Referenz (Contract-Endpoints)

| Method | Endpoint | Aktion |
|---|---|---|
| `GET` | `/api/contracts` | Alle Contracts (mit Lifecycle-Filter) |
| `GET` | `/api/contracts/{product}` | Contract inkl. Guarantees |
| `PUT` | `/api/contracts/{product}` | Contract speichern (setzt lifecycle=draft) |
| `POST` | `/api/contracts/{product}/seed` | Draft aus Inventar-Snapshot generieren |
| `POST` | `/api/contracts/{product}/diff` | Gegen .active.yml vergleichen (G3 vorab) |
| `POST` | `/api/contracts/{product}/approve` | Certifizieren (G3-Check, schreibt .active.yml) |
| `POST` | `/api/contracts/{product}/compile` | Guarantees → Checks-YAML kompilieren |
| `POST` | `/api/contracts/{product}/certify` | Lite: seed+validate+compile+approve in einem |
| `POST` | `/api/contracts/{product}/promote` | internal_gate → consumer_contract (Draft) |
| `POST` | `/api/contracts/{product}/deprecate` | Aktiven Contract zurückziehen |
| `GET` | `/api/contracts/{product}/export/odcs` | ODCS 3.1 Export |
| `POST` | `/api/contracts/{product}/export/bdc` | CSN/ORD-Fragmente für BDC generieren |
| `GET` | `/api/contracts/{product}/sla` | SLA-Compliance über 7d/30d/90d |

---

## 10. Kompletter Workflow — Ende zu Ende

```
1. INVENTAR-SNAPSHOT
   data/inventory.json  ←── Datasphere Catalog REST API (OAuth2)
   data/lineage.json    ←── build_lineage_graph()

2. SEED (optional)
   POST /api/contracts/{product}/seed
   → Draft-YAML aus Inventar-Spalten generieren

3. EDIT
   PUT /api/contracts/{product}
   → Guarantees in YAML editieren (Contract Workbench im Cockpit)
   → Validator (G1) läuft sofort

4. DIFF (Full-Modus)
   POST /api/contracts/{product}/diff
   → Vergleich gegen .active.yml, Breaking-Change-Klassifikation

5. APPROVE (Full-Modus) / CERTIFY (Lite-Modus)
   POST /api/contracts/{product}/approve
   → Gate G3: Breaking Change? → Major-Bump nötig
   → Schreibt contracts/{product}.active.yml
   → Git-Commit mit Caller als Author

6. COMPILE
   POST /api/contracts/{product}/compile
   → Guarantees → DatasetConfig → CheckDef-Liste
   → Schreibt checks/{product}/checks.yaml (mit compiler_hash)

7. EXECUTION (CLI oder API)
   python cli/dq_check_runner.py --schema {SCHEMA} --checks checks/{product}/checks.yaml
   → bind_schema({SCHEMA})  [Gate G2]
   → Checks gegen HANA ausführen
   → Ergebnisse in Result-Store (SQLite/HANA)

8. COMPLIANCE & INCIDENTS
   → Compliance-Ampel im Cockpit (grün/gelb/rot)
   → Incidents bei State-Wechsel (executed → fail, skipped_stale, etc.)
   → Rolling Baseline + Proposal Miner für neue Guarantees
```

---

## Verwandte Dokumente

- `ADR-0001_Quality-Gates_vs_Contracts.md` — boundary-Diskriminator, Tiering
- `ADR-0006_Editor-Modus_aus_Kind.md` — Lite/Full-Modalität
- `ADR-0003_BDC-Datasphere-DataProductStudio.md` — Studio-Integration, HDLF, SQL-Port
- `ADR-0004_DataProduct-als-Komposition.md` — Manifest-Modell, Intent vs. Reality
- `Betriebsmodi_Lite_und_Full.md` — Prozess-Zeremonie
- `Tooldokumentation.md` — Architektur-Referenz
- `Zusatz_ContractLifecycle_ORDBDCIntegration.md` — ORD/ODCS-Seam, offene Punkte
