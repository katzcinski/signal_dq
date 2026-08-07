# Konzept: Shift-Left-Schema-Drift & Data-Diff v1 (Tier-2-Features)

**Stand:** 2026-06-29 · **Status:** **Backend umgesetzt** (2026-07: Migrationen `014_schema_snapshots`/`015_profile_snapshots`, `GET /api/contracts/{p}/drift`, `POST /api/objects/{id}/diff`, `value_delta` in `/api/runs/compare`); offen ist nur der Schema-Drift-Screen (`OPEN_TASKS.md` **A2**) · **Bezug:**
[`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md) (Tier 2,
§2.1 & §2.2), [`Tooldokumentation.md`](Tooldokumentation.md) (implementierter Stand)

Technischer Entwurf für zwei Tier-2-Lücken:

- **A — Shift-Left-Schema-Drift-Detection** (Marktanalyse §2.1): erkennt, wenn die *Quelle*
  vom Contract-Versprechen abweicht — der Contract-Monitoring-Teil von „Shift-Left".
- **B — Data-Diff / Environment- & Versions-Vergleich** (Marktanalyse §2.2): Wert- und
  Verteilungs-Diff statt nur Status-Diff.

> **Leitplanke (wie Tier 1):** Engine bleibt `[ENGINE-FROZEN]`/frameworkfrei (G7). Contracts
> SQL-frei (G1), Schema laufzeit-gebunden (G2). HANA ausschließlich **lesend**; Signal schreibt
> **nie** nach Datasphere. Rohzeilen nur per PII-Gate/Allowlist (G8). Neue Store-Objekte nur über
> nummerierte Migrationen — nächste freie Nummer hier: **`014`** (Tier-1-Konzept belegt 010–013).

---

# Teil A — Shift-Left-Schema-Drift-Detection (§2.1)

## A.1 Problem

Zwei Lücken zwischen „was wir versprochen haben" und „was die Quelle tatsächlich tut":

1. **G3 schützt nur das Contract-Repo.** Das Breaking-Gate difft Änderungen an *unseren*
   Contract-Dateien gegen die Merge-Base. Ändert der **Producer** seine Datasphere-/HANA-Struktur,
   merkt G3 nichts — die Quelle driftet still vom Versprechen weg.
2. **Die `schema`-Garantie prüft zur Laufzeit nur die Spaltenzahl.** Der Compiler bildet
   `guarantees.schema` auf einen `schema_columns`-Check ab, dessen Expectation `= N` bzw. `>= N`
   ist (`compiler.py`, Z. 219–227). Eine **umbenannte** Spalte bei gleicher Anzahl, ein
   **Typwechsel** oder eine **Nullability-Änderung** rutschen durch.

Gable & Co. fangen so etwas im Producer-Code ab. Signal kann keine Producer-Repos lesen — aber
es extrahiert bereits das **materialisierte** Quellschema (`data/inventory.json`,
`schemaVersion 6`, je Objekt `columns[].{name,type,key,nullable}`). Damit lässt sich der
Drift gegen das Versprechen erkennen.

## A.2 Design — Drift-Detektor als framework-freier Analyzer

Neuer Analyzer **`packages/dq_core/contract/schema_drift.py`** (Teil von `dq_core`, also
G7-frameworkfrei; Konsument: API + CLI). Reine Metadaten-Diffs — **kein** SQL gegen HANA,
nur das vom Extrakt gelieferte Inventar gegen die `schema`-Garantie des aktiven Contracts.

**Diff-Kategorien (je contractetem Objekt):**

| Kategorie | Bedeutung | `closed` mode | `open` mode |
|---|---|---|---|
| `column_added` | Spalte in Quelle, nicht im Contract | **breaking** | info |
| `column_removed` | Contract-Spalte fehlt in Quelle | **breaking** | **breaking** |
| `type_changed` | Quelltyp ≠ deklarierter Typ¹ | breaking (bei inkompat.) | breaking |
| `nullable_relaxed` | NOT NULL → nullable | breaking | breaking |
| `key_changed` | Key-Flag-Set verschoben | breaking | breaking |

¹ Setzt die optionale Typ-Deklaration im Contract voraus (siehe A.5) — heute trägt das
Contract-Schema keine Typen; bis dahin bleibt `type_changed` deaktiviert.

**Severity/Konsequenz folgt `kind`** (wie die Compliance-Trennung in 007):
- `consumer_contract`/`provider_contract` + breaking → **Contract-Breach-Incident**
  (Compliance-Ampel), analog zu einem fehlgeschlagenen Contract-Check.
- `internal_gate` + breaking → **Engineering-Signal-Incident** (kein SLA/Ampel-Effekt).

## A.3 Zwei Auslösepunkte

1. **Beim Extrakt** (`POST /api/extract`): Nach Inventar-Refresh läuft der Drift-Detektor
   über **alle** aktiven Contracts → ein Drift-Report + ggf. Incidents. So wird Drift entdeckt,
   bevor ein Lauf überhaupt startet (echtes Shift-Left, Producer-seitig getriggert).
2. **Als Pre-Flight im Lauf** (Runner): Ein billiger Schema-Drift-Check **gatet** die teuren
   Inhalts-Checks — dasselbe Prinzip wie „günstige Checks gaten teure" und `skipped_stale`
   (G6). Driftet das Schema breaking, werden abhängige Checks als `skipped_dependency`
   markiert (Zustand existiert bereits in `engine/models.py`) statt rot/grün zu rauschen.

## A.4 Datenmodell — Migration `014_schema_snapshots.sql`

Snapshot je Objekt × Extrakt (für Drift-über-Zeit, idempotent neu ableitbar):

```sql
CREATE TABLE IF NOT EXISTS dq_schema_snapshots (
  id INTEGER PRIMARY KEY,
  object_name TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  columns_json TEXT NOT NULL,          -- [{name,type,key,nullable}] aus inventory.json
  inventory_hash TEXT NOT NULL         -- Schnell-Vergleich gleich/ungleich
);
CREATE INDEX IF NOT EXISTS ix_schema_snap ON dq_schema_snapshots(object_name, captured_at);

CREATE TABLE IF NOT EXISTS dq_schema_drift (
  id INTEGER PRIMARY KEY,
  object_name TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  category TEXT NOT NULL,              -- column_added | column_removed | type_changed | ...
  column_name TEXT,
  before_value TEXT,
  after_value TEXT,
  breaking INTEGER NOT NULL,
  contract_version TEXT,
  incident_id TEXT                     -- gesetzt, wenn ein Incident eröffnet wurde
);
```

Der Drift wird gegen die **`schema`-Garantie des aktiven Contracts** (nicht gegen den
vorigen Snapshot) bewertet — das Versprechen ist die Referenz. Snapshots dienen der Historie
und der „seit wann"-Aussage.

## A.5 Contract-Schema (additiv, SQL-frei) — optionale Typ-Deklaration

Damit `type_changed`/`nullable_relaxed` scharf werden, erhält die `schema`-Garantie eine
optionale, **rein deklarative** Typ-/Nullability-Spezifikation (kein SQL → G1 unberührt):

```yaml
schema:
  columns: [ORDER_ID, CUSTOMER_ID, NET_AMOUNT]    # Kurzform bleibt gültig
  mode: closed
  types:                                          # optional, additiv
    ORDER_ID:     { type: integer, nullable: false, key: true }
    NET_AMOUNT:   { type: decimal, nullable: false }
```

Dies operationalisiert den in der Tooldokumentation (§3.2) als „später Contract-Garantie"
vorgemerkten `type_conformance`-Pfad — der Drift-Detektor ist das Vehikel, das deklarierte
Typen einführt. Validator (`contract/validator.py`): `types` optional, Enum-geprüfte Typen,
Spalten müssen Teilmenge von `columns` sein.

## A.6 API & UI

- `GET /api/contracts/{product}/drift` → aktueller Drift-Report (Kategorien, breaking-Flag,
  „seit Snapshot X").
- Extrakt-Response (`/api/extract`) trägt eine Drift-Zusammenfassung je betroffenem Objekt.
- Contract-Workbench (`/contracts`): Banner „Quelle weicht vom Versprechen ab" mit Diff-Tabelle;
  Quick-Action „Contract anpassen" (öffnet Editor) bzw. (bei `*_contract`) Hinweis auf nötigen
  Major-Bump (G3). Strings nach `i18n/de.ts`.
- Incident-Inbox: neuer Incident-Anlass „Schema-Drift" (kind-getrennt wie Compliance vs. Engineering).

## A.7 Gate-Konformität

- **G1:** Drift nutzt Inventar-Metadaten + deklarative Typen — kein SQL im Contract.
- **G2:** keine Schema-Literale; Objektbindung über Inventar/Environment.
- **G6:** breaking Drift → abhängige Checks `skipped_dependency`, nie still ausgelassen.
- **G7:** Analyzer in `dq_core`, frameworkfrei. Engine unberührt.
- **Read-only:** nur Inventar-Lesen; keine Datasphere-Schreibvorgänge.

---

# Teil B — Data-Diff / Environment- & Versions-Vergleich (§2.2)

## B.1 Problem

`GET /api/runs/compare` difft heute **nur Check-Status** (regressed/recovered/added/removed,
`runs.py` Z. 106–143). Es fehlt der **Wert-/Verteilungs-Diff**: „Row-Count fiel von 1,2 M auf
0,9 M", „Null-Quote in `NET_AMOUNT` stieg von 0,1 % auf 4 %", „dev vs. prod weicht ab".
Datafold-Stil „was änderte sich zwischen zwei Zuständen" ist nicht abgedeckt.

## B.2 Design — drei Diff-Modi, alle lesend, abgestuft nach Kosten/PII

| Modus | Quelle | Kosten | PII-Risiko |
|---|---|---|---|
| **B-1 Value-Diff** | `dq_check_results.actual_value` zweier Runs | trivial (Store-Query) | keins (Aggregate) |
| **B-2 Distribution-Diff** | Profiler-Stats zweier Snapshots/Environments | mittel (HANA-Aggregate) | keins (nur Aggregate; Samples bleiben gegated) |
| **B-3 Key-Reconciliation** | Key-Set-Kardinalität zweier Datasets/Environments | mittel (GROUP BY/COUNT) | gering (nur Key-Mengenarithmetik, keine Rohzeilen) |

**Bewusst nicht in v1:** vollständiger zeilenweiser Row-Diff (Datafold „rows"). Das bräuchte
entweder Rohzeilen (G8) oder Per-Zeilen-Hashes über Nicht-PII-Spalten. Als **opt-in mit
Allowlist** (analog `ALLOW_LOCAL_DIAGNOSTICS`/`PROFILE_SAMPLE_COLUMNS`) später nachrüstbar;
in v1 bleibt es bei Aggregat-/Verteilungs-Diff + Key-Reconciliation.

### B-1 — Value-Diff (Sofort-Gewinn, reine Store-Schicht)

`compare_runs` wird um `value_delta` je Check erweitert: `base.actual_value`,
`head.actual_value`, `abs_delta`, `pct_delta`. Keine neue Erfassung, kein HANA-Zugriff — die
Werte liegen bereits in `dq_check_results`. Direkt nutzbar im bestehenden Run-Compare-Screen.

### B-2 — Distribution-Diff (Profiler-Wiederverwendung)

Der vorhandene Profiler (`profile/profiler.py`, `profile_table`) liefert je Spalte
count/null%/distinct/min/max. Für den Diff werden zwei Profil-Snapshots desselben logischen
Datasets verglichen — **zwei Zeitpunkte** (Versions-/Deploy-Diff) **oder zwei Environments**
(dev vs. prod, Bindung über `environments.yml`-Schema, G2). Pro Spalte: Δ null%, Δ distinct,
Δ min/max, sowie ein einfacher **Verteilungs-Abstand** (PSI/Population-Stability-Index über
gröbere Bins, falls Histogramme vorliegen — sonst Kennzahl-Deltas).

### B-3 — Key-Reconciliation (Cross-Environment)

Für denselben deklarierten Key (`guarantees.keys.columns`) je Environment lesend:
`COUNT(*)`, `COUNT(DISTINCT key)` und — über zwei gegen dasselbe HANA erreichbare Schemata —
Key-Set-Differenzen via `EXCEPT`/`NOT IN` **nur auf Key-Spalten** (Kardinalität, keine
Attributwerte). Ergebnis: „nur in base: N Keys, nur in head: M Keys, gemeinsam: K". Das ist
der reconciliation-nahe Anteil ohne Rohzeilen-Leak (vgl. Marktanalyse §2.4: volle
Reconciliation bleibt separater Pfad).

## B.3 Datenmodell — Migration `015_profile_snapshots.sql`

Damit B-2/B-3 zwei Zeitpunkte vergleichen können, werden Profil-Läufe als Snapshots abgelegt
(heute ist `POST /objects/{id}/profile` flüchtig):

```sql
CREATE TABLE IF NOT EXISTS dq_profile_snapshots (
  id INTEGER PRIMARY KEY,
  object_name TEXT NOT NULL,
  environment TEXT,                  -- NULL = Default/Mock
  captured_at TEXT NOT NULL,
  stats_json TEXT NOT NULL           -- Aggregat-Profil (keine Sample-Rows, G8)
);
CREATE INDEX IF NOT EXISTS ix_profile_snap ON dq_profile_snapshots(object_name, environment, captured_at);
```

B-1 braucht **keine** Migration (liest `dq_check_results`).

## B.4 API & UI

- **B-1:** `GET /api/runs/compare` zusätzliches Feld `value_delta` je `changes[]`-Eintrag
  (rückwärtskompatibel additiv).
- **B-2/B-3:** `POST /api/objects/{id}/diff` mit Body
  `{base: {run|snapshot|env}, head: {…}, mode: distribution|keys}` →
  `{columns:[{name, base_stats, head_stats, deltas, psi?}], keys?:{only_base, only_head, common}}`.
  Schreib-frei, aber HANA-lesend → `[AUTHZ]` (steward+, wie `environments/{name}/test`).
- **UI Run-Vergleich** (`/runs/compare`): neue Spalte „Wert (vorher → nachher, Δ%)" mit
  Richtungspfeil/Glyph (Status-Encoding ≥3-von-4, Carbon).
- **UI Objekt-Detail** (`/objects/:id`): „Diff"-Drawer — Environment-A-vs-B-Auswahl,
  Verteilungs-Heatmap (Spalte × Δ), Key-Reconciliation-Kachel. Strings in `i18n/de.ts`.

## B.5 Gate-Konformität

- **G1/G2:** Diff-SQL nur im Compiler/Profiler erzeugt, `{schema}` laufzeit-gebunden.
- **G8:** ausschließlich Aggregate/Verteilungen/Key-Kardinalität; Sample-Rows bleiben hinter
  `ALLOW_PROFILE_SAMPLES`/Allowlist. Zeilenweiser Diff explizit out-of-scope für v1.
- **G7:** Profiler/Diff-Logik in `dq_core`; Engine unberührt.
- **Read-only:** kein Datasphere-Write.

---

## C / Umsetzungsreihenfolge & Aufwand

```
①  B-1 Value-Diff            ── reine Store-Erweiterung, keine Migration ── Sofort-Gewinn
②  A  Schema-Drift           ── Inventar-Diff vorhanden; größter Governance-Nutzen
③  B-2 Distribution-Diff     ── Profiler-Snapshots; baut Verteilungs-Historie auf
④  B-3 Key-Reconciliation    ── Cross-Env; setzt Multi-Environment-Bindung voraus
```

| Feature | Migration | Engine berührt? | Neue Contract-Keys | Hauptaufwand |
|---|---|---|---|---|
| A Schema-Drift | `014` | nein | `schema.types` (optional) | `contract/schema_drift.py`, extract, runner-gate, UI |
| B-1 Value-Diff | — | nein | — | `runs.py` compare-Erweiterung, UI |
| B-2 Distribution-Diff | `015` | nein | — | profiler-Snapshots, `/objects/{id}/diff`, UI |
| B-3 Key-Reconciliation | — | nein | — | compiler (Key-Set-SQL), `/objects/{id}/diff`, UI |

## D / Tests (mirror CI: tests/unit + tests/api)

- **A:** `tests/unit` — alle Drift-Kategorien (added/removed/type/nullable/key) gegen
  `closed`/`open`, kind-abhängige Severity, Pre-Flight-Gating → `skipped_dependency` (G6);
  `tests/api` — `/contracts/{product}/drift`, Incident-Anlage kind-getrennt.
- **B-1:** `tests/api` — `value_delta` im compare-Response, Division-durch-0/None-Robustheit.
- **B-2:** `tests/unit` — Distribution-Delta/PSI-Berechnung, keine Sample-Rows im Snapshot (G8);
  `tests/api` — `/objects/{id}/diff` zwei Snapshots & zwei Environments.
- **B-3:** `tests/unit` — Key-Set-Arithmetik (only_base/only_head/common), S2 auf Key-Identifier.
- Alle: bestehende Engine-Suite (G5) bleibt **unverändert grün** — Beweis für `[ENGINE-FROZEN]`.
