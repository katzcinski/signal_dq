# Evaluation — Neue Features, Workflows & UI-Verbesserungen · 2026-08

**Stand:** 2026-08-03 · **Zweck:** Bewertung *neuer* Feature-Kandidaten,
State-of-the-Art-Workflows und UI-Verbesserungen — als Ergänzung zu
[`OPEN_TASKS.md`](OPEN_TASKS.md) (konsolidierter Backlog) und
[`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md)
(Feature-Gap-Synthese 2026-06). Dieses Dokument wiederholt den Backlog **nicht**;
wo ein Vorschlag an einen bestehenden Punkt andockt, ist die ID referenziert.

**Bewertungsfilter** (wie in der Marktanalyse): Vereinbarkeit mit den Gates —
lesender HANA-Zugriff, SQL-freie Contracts (G1), Laufzeit-Schema-Bindung (G2),
frameworkfreie Engine (G7), PII-Gate (G8).

---

## 1 / Ausgangslage — was sich seit der Marktanalyse geschlossen hat

Die vier Tier-1-Lücken der Marktanalyse (saisonale Anomalie-Baselines,
Segmentierung, Incident-RCA/Blast-Radius, Alert-Clustering) sind über
Observability-Intelligence v1 geliefert; ebenso die Enforcement-Achse
`gate | quarantine | monitor` (Slices ①–③), ODCS-Import/ODPS-Export und der
Schema-Drift-**Datenpfad** (Persistenz, API, Banner). Signal ist damit auf der
Intelligenz-Schicht nicht mehr im Rückstand — die verbleibenden Lücken liegen in
drei Feldern:

1. **Reichweite nach außen** — Ergebnisse verlassen das Cockpit kaum
   (kein teilbarer Report, kein Digest, keine Agenten-/CI-Schnittstelle).
2. **Vertrauensbildung vor der Aktivierung** — Garantien werden aktiviert, ohne
   zu wissen, wie oft sie historisch gefeuert hätten.
3. **UI-Restpolitur** — wenige, klar umrissene Screens/Interaktionen.

---

## 2 / Neue Feature-Kandidaten (nicht im Backlog)

### V1 — Garantie-Backtesting („Was hätte gefeuert?") · **Empfehlung: bauen** `[M]`

**Markt:** Bigeye/Anomalo lassen Schwellwerte gegen die Historie simulieren,
bevor ein Monitor scharf geschaltet wird — das wirksamste Mittel gegen
Alert-Fatigue *vor* dem ersten Alert.

**Signal heute:** Proposal-Miner schlägt Garantien datengetrieben vor, Dry-Run
prüft Kompilierbarkeit — aber niemand sieht vor der Aktivierung, wie oft eine
Garantie in den letzten 30/90 Tagen verletzt gewesen wäre.

**Zuschnitt:** Reine Auswertung bereits persistierter Daten (`dq_baselines`,
Zeitreihen, Run-Historie) — kein neuer HANA-Zugriff, kein Engine-Eingriff (G7).
Backend: `POST /api/contracts/{p}/backtest` (Garantie-Entwurf → simulierte
Breach-Punkte je Zeitfenster). Frontend: Overlay im bestehenden
Threshold-/Anomalie-Chart der Workbench + Badge „hätte N× in 90 d gefeuert" am
Proposal (stärkt zugleich die Accept-Entscheidung aus **M4**).

**Wert:** hoch · **Aufwand:** mittel (~3–4 PT) · **Risiko:** gering.

### V2 — KI-Copilot: NL→Garantie + deutschsprachige Incident-Erklärung · **Empfehlung: bauen, eng geschnitten** `[M]`

Marktanalyse §2.3 — bislang ohne Backlog-ID, daher hier konkretisiert. Zwei
getrennt lieferbare Scheiben:

- **(a) Incident-Erklärer:** Persistierte Incident-Daten (RCA-Korrelation,
  Impact-Snapshot, Baseline-Kontext — alles schon im Store) → deutsche
  Erklärung in 3–5 Sätzen im Incident-Drawer. Nur Aggregate, keine Rohzeilen
  (G8 bleibt scharf). Kleinste Scheibe, sichtbarster Effekt.
- **(b) NL→Garantie in der Workbench:** LLM emittiert ausschließlich
  Garantie-YAML; `validate_contract` + Compiler bleiben die einzige SQL-Quelle
  (G1 unverletzt). Ein abgelehnter Vorschlag ist ein Validierungsfehler, kein
  Sicherheitsproblem.

Architektur: eigener Service-Baustein unter `services/api/` (LLM-Client hinter
Settings/ENV, Fail-closed ohne Key), **nichts** davon in `dq_core`. Der
deutschsprachige Erklärer ist gegen Monte Carlo/Anomalo ein echter
Differenziator — die Codebasis ist German-first.

**Wert:** hoch (Demo-Hebel) · **Aufwand:** (a) ~2 PT, (b) ~4–5 PT · **Risiko:**
gering, da rein additiv.

### V3 — MCP-Server: Signal als Werkzeug für KI-Assistenten · **Empfehlung: evaluieren → kleine Scheibe** `[M/L]`

2026-Standard: Datenplattformen exponieren einen MCP-Server, damit
Organisations-Assistenten (Claude & Co.) Qualitätsstatus abfragen können —
„Ist `SALES_ORDERS` heute vertrauenswürdig?" direkt im Chat des Konsumenten.

**Zuschnitt:** Read-only-Tools über die bestehende API (Objekt-Status,
Incidents, Lineage-Impact, Contract-Lookup, Compliance) — kein neuer Datenpfad,
Auth über das bestehende Rollenmodell (Token ↦ `viewer`). Schreiben bleibt
ausgeschlossen. Passt zu Signals Lesend-Positionierung; sinnvoll erst, wenn ein
Kunde/Interessent Assistenten im Einsatz hat — daher kleine Scheibe hinter
Feature-Flag.

**Wert:** mittel heute, strategisch steigend · **Aufwand:** ~2–3 PT · **Risiko:** gering.

### V4 — Qualitäts-Digest (täglich/wöchentlich) · **Empfehlung: mit A1 bündeln** `[M]`

`notify.py` kennt heute nur ereignisgetriebene Webhooks (Slack/Teams/generisch);
es gibt keinen periodischen Rollup („5 neue Incidents, 2 SLA-Verletzungen,
Health-Trend ↓"). Ein Digest über den vorhandenen Scheduler
(`schedules.py`-Muster) + Notification-Routing ist der halbe Weg zu **A1**
(teilbarer Report) — dieselbe Aggregation, zwei Ausspielungen (Webhook-Karte
und Report-Snapshot). E-Mail als neuer Target-Typ (SMTP via Settings) gehört in
dieselbe Scheibe.

**Wert:** mittel/hoch (Management-Sichtbarkeit) · **Aufwand:** ~2–3 PT zusätzlich
zu A1 · **Risiko:** gering.

### V5 — Verify-API für Consumer-CI („Contract-Check vor Deploy") · **Empfehlung: dokumentieren, dann dünn bauen** `[L/M]`

Der CLI-Runner liefert bereits Gate-Exit-Codes (0/1/3) und
`GET /api/runs/{id}/status` existiert als Task-Vertrag. Was fehlt, ist der
konsumentenseitige Workflow: Ein Downstream-Team fragt in seiner CI „ist der
Contract meines Upstreams aktuell erfüllt?" (`GET /api/contracts/{p}/verdict`,
read-only, viewer-Token) und bricht den eigenen Deploy ab, wenn nicht.
Erst als Rezept dokumentieren (GitHub-Action-Beispiel gegen die bestehende
API), Endpoint-Zuschnitt danach — Shift-Left auf der Consumer-Seite, komplementär
zum Producer-seitigen G3.

### V6 — Incident-Postmortem light · **Empfehlung: beobachten** `[L]`

Status-Transitionen tragen bereits `note` + Owner. Was fehlt: strukturierte
Auflösungs-Kategorie (`root_cause: upstream | schema | load | data | false_positive`)
und deren Auswertung (False-Positive-Quote je Garantie → Rückkopplung in
Threshold-Tuning/Backtesting V1). Kleine Migration + zwei Felder im
Incident-Drawer. Erst sinnvoll, wenn reale Incident-Volumina da sind.

---

## 3 / Workflows — State of the Art, Einordnung

| Workflow (Markt) | Einordnung für Signal |
|---|---|
| Monitors-as-Code (Soda/GX) | ✅ vorhanden — Contracts in Git, API schreibt über Git-Writer zurück |
| Shift-Left Producer-Gate | ✅ G3 in CI; Consumer-Seite = **V5** |
| Backtesting vor Aktivierung | ◻ = **V1** |
| Incident-Triage mit RCA/Impact | ✅ Obs-Intelligence v1 |
| Periodische Reports/Digests | ◻ = **V4** + Backlog **A1** |
| Agenten-/LLM-Zugriff (MCP) | ◻ = **V3** |
| On-Call-Integration (PagerDuty/Opsgenie) | dünn: neuer Webhook-Target-Typ im bestehenden Routing genügt; kein eigenes Konzept nötig |
| Data-Diff in CI (Datafold) | teilweise über Backlog **I2** (counts-only Validator); nicht separat verfolgen |

---

## 4 / UI-Verbesserungen (konkret, klein geschnitten)

1. **A2 zuerst — Schema-Drift-Screen.** Der günstigste offene Punkt im ganzen
   Backlog: Datenpfad, API, FE-Binding und Tests existieren; es fehlt nur die
   Page (lazy Route + `de.ts` + vitest). ~1 PT für einen kompletten Screen.
2. **Backtesting-Overlay in der Workbench** (Teil von V1) — nutzt die
   vorhandenen Chart-Primitives (Threshold-/Anomalie-Band).
3. **Gespeicherte Ansichten im Objektkatalog.** Facetten-Filter sind
   URL-synced; benannte Presets („Meine Finance-Objekte, nur rot") als
   localStorage-Scheibe + optional per Store, angezeigt in „My Work".
4. **Command-Palette um Aktionen erweitern.** Heute Navigation/Suche; Aktionen
   wie „Run auslösen", „Incident quittieren", „Contract öffnen" machen sie zum
   Power-User-Werkzeug (Rollen-Guards wiederverwenden).
5. **Tabellen-Virtualisierung ab ~500 Zeilen** (Backlog **L5**) — vor dem
   ersten großen Tenant messen, nicht danach.
6. **en-Locale** (Backlog **L2**): nur relevant, falls Nicht-DACH-Prospects
   real werden; Struktur (`i18n/de.ts`) ist vorbereitet, Aufwand liegt im
   Übersetzen, nicht im Code.
7. **Lineage Phase 3** (Backlog **O1–O5**) bleibt die richtige Sammelstelle für
   Graph-UX — hier bewusst nichts Neues obendrauf.

---

## 5 / Priorisierte Empfehlung

Unverändert gilt die Reihenfolge aus `OPEN_TASKS.md` für die
**Fundament-Spur**: M1/M2/M3/M6 (Workflow-/CI-Wahrheit) → C2 (`HanaStore`).
Die hier evaluierten Punkte bilden eine parallele **Produkt-Spur** (klein,
additiv, demo-wirksam):

1. **A2 Schema-Drift-Screen** — 1 PT, schließt einen Backlog-Punkt vollständig.
2. **V1 Backtesting** — größter Vertrauens-/Anti-Fatigue-Hebel, rein auf
   Store-Daten.
3. **V2a Incident-Erklärer (deutsch)** — kleinste KI-Scheibe, größter
   Demo-Effekt; V2b (NL→Garantie) danach.
4. **A1 + V4 als ein Paket** — Report-Snapshot + Digest + E-Mail-Target aus
   einer Aggregation.
5. **V3 MCP-Server** — kleine Flag-Scheibe, sobald Kundenkontext Assistenten
   nutzt; **V5/V6** dahinter.

Nicht verfolgen (bestätigt): Connector-Breite, Cost/FinOps-Observability,
LLM-Korpus-Observability (Marktanalyse §4) — Positionierung bleibt
Datasphere/HANA, lesend, deterministisch.
