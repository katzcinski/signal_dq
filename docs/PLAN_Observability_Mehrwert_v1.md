# PLAN — Observability-Mehrwert für Signal (v1)

**Stand:** 2026-06-25 · **Status:** teilweise umgesetzt (2026-07: robuster MAD-z-Score in `obs/baselines.py` + Migration 010; Incident-Impact-Snapshot via Migration 015 — offen bleibt Task-Log-Freshness, siehe `OPEN_TASKS.md` **E**)
**Quelle:** Abgleich der Referenzarchitektur *„Data Quality Observability für
SAP Datasphere & HANA Cloud" (v0.1)* gegen den implementierten Signal-Stand.

Dieses Dokument hält **nur die drei Punkte** fest, die echten, noch nicht
vorhandenen Mehrwert liefern und auf Bausteinen aufsetzen, die Signal bereits
besitzt — aber noch nicht verbindet. Bewusst **nicht** enthalten ist alles, was
Signal schon abdeckt (Result-Store, Check-Registry/Library, Pushdown-SQL,
Incident-Dedup/Lifecycle, Notification-Routing Slack/Teams/Webhook, Scheduling,
Task-Chain-Trigger, Catalog/Lineage-OData) — das nachzubauen wäre Doppelarbeit.

> Reihenfolge nach Hebel: **(1) MAD-z-Score** (klein, sofort robuster) →
> **(3) Freshness via Task-Log** (schließt blinde Objekte) →
> **(2) Lineage-Impact am Alert** (höchste Sichtbarkeit, größter Eingriff).

---

## Punkt 1 — Robuster MAD-z-Score in der Anomalie-Bewertung

### Befund
`packages/dq_core/obs/baselines.py` **berechnet bereits** `median` und `mad`
(Median Absolute Deviation) und persistiert sie in `dq_baselines`. Die
Bewertung läuft aber über `compute_bounds()`, das `mean ± σ·stddev` nutzt —
also die klassische, ausreißeranfällige Standardabweichung. Der in §6 der
Referenzarchitektur beschriebene robuste z-Score
(`0.6745·(x − median)/mad`) ist damit „halb vorhanden": die Eingangsgrößen
liegen vor, nur die Bewertungsformel fehlt.

### Vorschlag
- In `obs/baselines.py` eine robuste Bewertung ergänzen, z. B.
  `robust_zscore(value, baseline)` → `0.6745·(value − median)/mad` mit
  Sonderfall `mad == 0` (keine Streuung ⇒ exakte Abweichung wertet als FAIL,
  sonst PASS), analog `evaluate()` aus §6.
- Schwellen aus dem Konzept übernehmen: `|z| > k` ⇒ FAIL, `|z| > 0.7·k` ⇒ WARN
  (Default `k = 3.5`). `compute_bounds()` bleibt für rückwärtskompatible
  Bound-Anzeige erhalten, ist aber nicht mehr alleinige Verdikt-Quelle.
- `median` mit in `dq_baselines` aufnehmen, falls nicht schon vorhanden (aktuell
  werden `mean_v`, `stddev_v`, `p01`, `p99`, `mad` gespeichert — `median` ist
  für den robusten z-Score nötig). → **neue numerierte Migration**, bestehende
  nicht ändern.
- Lernphase respektieren: `WARMUP_N` (aktuell 5) bleibt Gate; vor genügend
  Historie kein FAIL-Verdikt, nur Beobachtung.

### Betroffene Stellen
- `packages/dq_core/obs/baselines.py` (Engine, **G7 framework-frei halten**).
- ggf. `services/api/routers/objects.py` (~Z. 415–430), wo `BaselineManager`
  schon aufgerufen wird — Bewertungspfad anbinden.
- Neue Migration `packages/dq_core/store/migrations/010_*.sql` für `median`.
- Tests: `tests/unit/` (z-Score-Grenzfälle, `mad == 0`, Lernphase).

### Aufwand / Risiko
**Klein.** Reine Engine-Erweiterung, kein API-Schema-Bruch. Risiko gering, da
additiv und durch Warmup-Gate abgesichert.

---

## Punkt 2 — Lineage-Impact am Incident / Alert

### Befund
Signal besitzt den vollständigen Lineage-Graphen (`packages/dq_core/lineage/`,
Coverage-Map, `lineage`-Router) und persistente Incidents mit Timeline
(Migration 004) sowie ownership-geroutetes Alerting (`services/api/notify.py`,
Slack/Teams/Webhook). **Nicht verbunden:** Beim Öffnen eines Incidents bzw.
beim Versand der Benachrichtigung werden die **betroffenen Downstream-Objekte
nicht ermittelt**. Der Alert sagt heute „View X hat einen Breach", nicht
„… betrifft 3 nachgelagerte Analytic Models / SAC-Stories" (Impact-Analyse,
§8 der Referenz). Der Graph ist da, nur der Join zur Incident-Zeit fehlt.

### Vorschlag
- Eine Downstream-Auflösung bereitstellen: ausgehend vom betroffenen
  `object_name` die Lineage-Kanten transitiv folgen und die Menge der
  nachgelagerten Objekte (mit Typ, z. B. Analytic Model / View) bestimmen.
  Identitäts-Join ist mapping-frei (`node.id == technicalName == product`).
- Beim `open_incident` den Impact als strukturiertes Feld am Incident ablegen
  (z. B. `impacted_objects` JSON) und in der Event-Timeline referenzieren.
- In `notify.py` den Impact in die Payloads aufnehmen: Slack/Teams als lesbare
  Zeile („Betrifft: …"), generischer Webhook als maschinen-routbares Array.
- Severity-Eskalation optional: viele/kritische Downstream-Objekte können die
  effektive Dringlichkeit anheben (Konzept-Mapping CRITICAL → Downstream-Stopp)
  — als Folge-Ausbaustufe, nicht Teil der ersten Iteration.

### Betroffene Stellen
- `packages/dq_core/lineage/` — Downstream-Traversierung (Engine, **G7**).
- `services/api/routers/objects.py` (Incident-Erzeugung, ~Z. 445 ff.).
- `services/api/notify.py` (Payload-Anreicherung; **SSRF-Guards in
  `webhook.fire_webhook` unverändert lassen**).
- Migration für `impacted_objects` am Incident (**neue** Migration).
- Frontend optional: Impact in der Incident-Detailansicht (`src/pages/`,
  Strings in `i18n/de.ts`) — separater Schritt.
- Tests: `tests/unit/` (Traversierung, Zyklen-/Dedup-Schutz),
  `tests/api/` (Incident enthält Impact, Notify-Payload).

### Aufwand / Risiko
**Mittel.** Größter funktionaler Nutzen, aber berührt Engine, API, Store und
optional Frontend. Risiko: Lineage-Tiefe/Zyklen — Traversierung muss
Tiefenlimit + Dedup haben (vgl. `_dedupe_lineage_edges`).

---

## Punkt 3 — Freshness-Fallback über Task-Log

### Befund
Der `freshness`-Check (`check_library.json`) braucht eine fachliche
Zeitstempelspalte (`SECONDS_BETWEEN(MAX(<col>), CURRENT_TIMESTAMP)`). Objekte
**ohne** fachlichen `load_ts` sind damit für Freshness blind. Gleichzeitig
existiert mit `services/api/datasphere.py` (`get_task_chain_runs`) und dem
`data_loads`-Router bereits ein Client, der den **letzten erfolgreichen Lauf**
der vorgelagerten Task Chain / Replication Flow liefert (§2/§5.5 der Referenz:
„fällt Freshness auf die Task-Log-API zurück"). Beide Bausteine sind da, die
Brücke fehlt.

### Vorschlag
- Eine Freshness-Quelle „Task-Log" als Alternative zur Spalten-basierten
  Messung: Wenn am Objekt kein Zeitstempel-Check definierbar ist, Freshness aus
  dem `finished_at` des letzten erfolgreichen Task-Chain-/Replication-Laufs
  ableiten (Stunden seit Lauf) und als regulären Metrikwert historisieren — so
  greift dieselbe Baseline-/Anomalie-Mechanik wie bei Spalten-Freshness.
- Konfiguration am Check/Objekt: `freshness_source = column | task_log`
  (Default `column`, Fallback `task_log` nur wo gewählt). Keine stille
  Umschaltung — explizite Wahl, konsistent mit „no silent fallbacks".
- **Pushdown-Invariante wahren:** der Task-Log-Pfad ist eine OData-Abfrage über
  den bestehenden Client, kein SQL gegen Kundendaten — bleibt lesend und
  verlässt die Plattform nicht.

### Betroffene Stellen
- `services/api/datasphere.py` / `routers/data_loads.py` — Bereitstellung des
  „letzter erfolgreicher Lauf"-Zeitpunkts pro Objekt.
- Anbindung im Run-Pfad (`routers/objects.py`), damit der Wert als
  Metrik/`CheckResult` in den Store fließt (Zustände gem. **G6** vollständig).
- Engine bleibt unberührt, falls der Wert als normaler Metrikwert eingespeist
  wird (kein neuer Expectation-Operator nötig → **G1/G7** unangetastet).
- Frontend: Freshness-Quelle sichtbar machen (`i18n/de.ts`).
- Tests: `tests/api/` (Fallback liefert Wert, Default unverändert).

### Aufwand / Risiko
**Mittel.** Hauptrisiko sind die bekannten OData-/CLI-Limits (siehe „Offene
Punkte" der Referenz, HDLF File Spaces). Realistisch zuerst für Objekte mit
sauber abfragbarer Task-Chain-Historie; alles andere bleibt explizit
„keine Freshness-Quelle" statt zu raten.

---

## Gate-Checkliste (für die spätere Umsetzung)

| Gate | Beachten bei |
|---|---|
| **G1** SQL nur im Compiler | Punkt 3: Task-Log über OData, kein Contract-SQL. |
| **G2** Schema-Bind zur Laufzeit | Keine Schema-Literale in neuen SQL-/Bind-Pfaden. |
| **G6** Gating-Zustände vollständig | Punkt 3: neuer Freshness-Wert führt sauber zu `executed`/`skipped_*`. |
| **G7** `dq_core` framework-frei | Punkte 1 & 2: Engine-/Lineage-Code importiert kein FastAPI. |
| **G8** PII-Gate | Punkt 1: nur Aggregat-Metriken (wie `miner.py`), keine Rohzeilen. |
| Store-Migrationen | Punkte 1 & 2 brauchen **neue** numerierte Migrationen; geshippte nie ändern. |

## Bewusst nicht in diesem Plan (geringer/kein Mehrwert)

- **Saison-/Wochentags-Baseline** — sinnvoll, aber erst ab ≥ 8 Wochen Historie
  und nach Punkt 1; als Folgeausbau vorgemerkt.
- **Schema-Drift-Snapshots mit Klassifikation** — überschneidet sich teils mit
  `schema`/`type_conformance`/`column_count` + `gate_g3`; eigener Plan, falls
  physische Drift zwischen Contract-Versionen separat sichtbar werden soll.
- **DQ_STATUS-Propagation nach SAC** — SAP-spezifisch und schwer; eigener
  Integrationspfad, nicht Teil dieses Mehrwert-Schnitts.

## Offene Entscheidungen

1. **Punkt 1:** `k`-Faktor und WARN/FAIL-Schwellen global oder pro Check-Typ
   konfigurierbar?
2. **Punkt 2:** Impact-Traversierung voll-transitiv oder auf N Ebenen begrenzt?
   Severity-Eskalation durch Downstream-Anzahl in v1 oder später?
3. **Punkt 3:** Pro-Objekt-Konfiguration der Freshness-Quelle im Contract
   (Observability-Sektion) oder nur als Store-/Schedule-Einstellung?
