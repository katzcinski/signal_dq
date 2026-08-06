# ADR-0005 — Scheduling: extern (Task-Chain/Cron) vs. intern (Store-backed Poller)

**Adressat:** Beratung, Plattform-Team, Entwicklung · **Stand:** 2026-06-24
**Status:** *Angenommen* (accepted) — **umgesetzt in `main`** (Option E: Migration `009_schedules`, `services/api/scheduler.py`, `PUT/GET/DELETE /api/objects/{id}/schedule`, `GET /api/schedules`, opt-in via `SCHEDULER_ENABLED`). Phase-2-Punkte im Backlog: `OPEN_TASKS.md` **N**.
**Zweck:** Festhalten, wie regelmäßige DQ-Läufe geplant werden — und warum Scheduling ein **pro-Objekt umschaltbares** Attribut wird (manuell / intern / extern), statt eine globale Betriebsentscheidung.

> Verwandte Dokumente: `Tooldokumentation.md` §7 (CLI), §10 (Deployment) · `ADR-0001` (Gates vs. Contracts, G7-Framework-Isolation).
> Aktive Phase-2-Backlog-Punkte sind seit 2026-07-04 in [`OPEN_TASKS.md`](OPEN_TASKS.md) §N konsolidiert.

---

## 0 — Kernaussage

Bisher triggert die API Läufe **nur ad hoc**; regelmäßige Läufe plant ein **externer** Scheduler über die CLI (`cli/dq_check_runner.py`, Tooldokumentation §7/§10). Das bleibt der Default und ist für Kunden mit eigenem Orchestrator (SAP Datasphere **Task Chains**, Airflow, k8s `CronJob`) der richtige Weg.

Diese ADR ergänzt — **additiv** — einen **optionalen, store-gestützten In-Process-Poller** und macht die Wahl **pro Objekt** sichtbar:

> **Scheduling ist ein Attribut des Objekts mit drei Zuständen: `manual` (kein Eintrag), `internal` (Signals Poller fährt die Kadenz), `external` (eine Task-Chain/Cron→CLI fährt sie; der Poller rührt das Objekt nie an, der Eintrag dokumentiert nur Intent und stempelt `last_run`).**

Engine und Contracts bleiben unangetastet (G7): die Scheduling-Logik lebt in `services/` und `cli/`, nie in `dq_core/`. Scheduling-Konfiguration ist **operativ**, nicht semantisch — sie steht daher **nicht** im Contract-YAML (G1), sondern in der Store-Tabelle `dq_schedules`.

---

## 1 — Kontext: Was Signal heute tut

| Baustein | Heute |
|---|---|
| API-Trigger | `POST /api/objects/{id}/run` → Hintergrund-Thread, F2-Doppellauf-Schutz via `try_begin_run` (partieller Unique-Index `idx_dq_runs_one_running`) |
| CLI | `cli/dq_check_runner.py` fährt die Engine ohne API — der dokumentierte Hook für Cron/Task-Chain |
| Deployment | Berater-lokal: 1 Worker · Kunde: ≥2 uvicorn-Worker; Run-Registry im Store schützt prozessübergreifend |
| Scheduling | „manuell/Cron" (lokal) bzw. „Cron/Task-Chain → CLI" (Kunde) — **extern** |

Die Lücke: kein in Signal sichtbarer, verwalteter Zeitplan; kein Cockpit-Schalter „dieses Objekt läuft alle N Minuten".

---

## 2 — Optionen (erwogen)

| # | Option | Pro | Contra |
|---|---|---|---|
| A | OS-Scheduler (cron/systemd) → CLI | null neuer Code, G7-konform | unsichtbar im Cockpit, kein Audit |
| B | Orchestrator/Task-Chain → CLI | Enterprise-Scheduling geschenkt; passt zu DSP | extern, Zustand außerhalb Signals |
| C | In-Process-Scheduler in der API (APScheduler/asyncio) | ein Deployable, Cockpit-sichtbar | **Multi-Worker-Gefahr**: Timer feuert je Worker; braucht Leader-Election |
| D | Dedizierter Single-Instance-Scheduler-Prozess | keine Duplikate per Konstruktion | ein weiteres Deployable |
| **E** | **Store-backed „due"-Queue + Claim** | korrekt unter ≥2 Workern *ohne* Leader-Election, Cockpit-sichtbar, durabel, auditiert | meiste Implementierung |

**Entscheidung: E**, weil es als einziges unter dem Kunden-Profil (≥2 Worker) ohne Zusatzmechanik korrekt ist — und weil es den vorhandenen F2-Primitiv (`try_begin_run`) wiederverwendet.

---

## 3 — Entscheidung (E im Detail)

### 3.1 Datenmodell — `dq_schedules` (Migration 009)

Spalten: `schedule_id`, `object_id`, **`mode`** (`internal|external`), `environment`, `execution_mode`, `interval_seconds`, `enabled`, `next_due_at`, `last_run_at`, `last_run_id`, `last_status`, Audit-Felder. Ein Schedule pro Objekt (deterministische ID `obj:<object_id>`) → der Objekt-Detail-Screen rendert **einen** Schalter.

### 3.2 Claim-Semantik (Kern)

Der Poller ruft `claim_due_schedules(now)`: SELECT der fälligen `mode='internal'`-Einträge, dann je Zeile ein **optimistisch geschütztes** `UPDATE … SET next_due_at=<advance> WHERE schedule_id=? AND next_due_at=<observed>`. Wer zuerst committet, gewinnt den Slot; der Konkurrent trifft mit seinem Guard nicht mehr und überspringt.

> **Korrektheitsgrenze ist nicht der Claim, sondern `try_begin_run`.** Selbst wenn zwei Worker rennen und beide starten, weist der partielle Unique-Index den zweiten Start als `already_running` ab — kein Doppellauf, nur ein verschenkter Wake-up. Der Claim ist reine Effizienz-Deduplizierung. **Keine Leader-Election nötig.**

### 3.3 Catch-up-Politik

`next_due_at` wird **vom vorherigen Slot** fortgeschrieben (kein Drift). Liegt der nächste Slot nach einem Ausfall noch in der Vergangenheit, springt er auf `now + interval` — **ein** Aufhol-Lauf, nie ein Backfill-Sturm.

### 3.4 Geteilter Ausführungspfad

`trigger_run` wurde in `objects.start_object_run(...)` zerlegt; HTTP-Route **und** Poller fahren über dieselbe Funktion → identische Compliance-/Incident-/Notification-/Baseline-Seiteneffekte und derselbe F2-Guard. `triggered_by="scheduler"` macht Scheduler-Läufe in `dq_runs` unterscheidbar.

### 3.5 Opt-in

`SCHEDULER_ENABLED` (Default **false**) + `SCHEDULER_TICK_SECONDS` (Default 30). Aus = dokumentiertes externes Modell unverändert. Jeder Worker startet seinen eigenen Poller; Claim + F2 halten das duplikatfrei.

### 3.6 API

`PUT /api/objects/{id}/schedule` (Upsert: mode/interval/environment/enabled), `GET …/schedule`, `DELETE …/schedule` (zurück zu manual), `GET /api/schedules` (Ops-Sicht). Berechtigung = Run-Trigger-Recht (steward+).

---

## 4 — Konsequenzen

- **Additiv & rückwärtskompatibel**: ohne `SCHEDULER_ENABLED` ändert sich nichts.
- **Extern bleibt erstklassig**: `mode='external'` dokumentiert Task-Chain-Steuerung im Cockpit, ohne dass der Poller eingreift.
- **G1/G7 gewahrt**: kein Scheduling im Contract, keine Scheduler-Logik in `dq_core`.
- **Offen (Phase 2)**: Cron-Ausdrücke statt fixem Intervall; Cockpit-UI für den Schalter; HANA-Store-Implementierung von `dq_schedules`; Missed-Run-Telemetrie.
