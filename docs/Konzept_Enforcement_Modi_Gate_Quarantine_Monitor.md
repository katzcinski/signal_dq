# Konzept — Durchsetzungsmodi: Gate · Quarantäne · Monitoring

**Adressat:** Plattform-Team, Governance, Fachbereich · **Stand:** 2026-06-25
**Status:** **Umgesetzt** (2026-07, Slices ①–③ via [`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md)): `enforcement` auf CheckDef/Guarantee (Default `monitor`), `gate_verdict`-Rollup, Migration 016, `/api/quarantine`, CLI-Exit-Codes 0/1/3. Implementierter Stand: `Tooldokumentation.md` §3.8.
**Zweck:** Eine **dritte Zustands-Achse** einführen — *welche Aktion* ein
Breach auslöst (`gate | quarantine | monitor`) — orthogonal zu `severity`
(*wie schlimm*) und zum Lite/Full-Zeremonie-Pfad (*wie viel Prozess*).

> Verwandte Dokumente: `Betriebsmodi_Lite_und_Full.md` (Zeremonie-Achse) ·
> `ADR-0002_Datasphere-DB-Zugriff.md` (Read-only-Prinzip) ·
> `ADR-0005_Scheduling.md` (externes Scheduling → CLI) ·
> `HANDOVER.md` (Gates G1–G8).

---

## 0 — Kernaussage

Signal kennt heute zwei Achsen je Check: **`severity`** (`critical|fail|warn` —
wie schlimm ein Breach ist) und die **Lite/Full**-Zeremonie. Es fehlt die
**Durchsetzungs-Achse**: *was* bei einem Breach passieren soll.

| Modus | Bedeutung | Wirkung auf die Pipeline |
|---|---|---|
| **gate** | Breach **blockiert** die Weitergabe (harter Stopp) | Promotion wird gestoppt |
| **quarantine** | Breach **isoliert** das Objekt; gute Daten fließen weiter | Schlechte Zeilen/Partition werden geparkt |
| **monitor** | Breach wird **nur beobachtet** (Record, Trend, Alert) | Nie blockierend, nie isolierend |

Die Achse ist ein **eigenes Feld** (`enforcement_mode`), nicht eine Überladung
von `severity` — so bleiben die Konzepte kombinierbar: Ein `critical`-Check in
`monitor` blockiert nicht; ein `warn`-Check in `gate` ist ein weiches Signal.

**Default: `monitor`.** Eine Garantie ohne expliziten Modus beobachtet nur — die
Einführung der Achse kann keine heute grüne Pipeline in einen Überraschungs-
Stopp verwandeln. Teams entscheiden sich **bewusst** für `gate`/`quarantine`.

---

## 1 — Architektur-Leitplanke: Signal entscheidet, Datasphere handelt

> **Update 2026-07-10 — Prämisse gelockert.** Signal darf in seinem **eigenen
> Open-SQL-Schema** Objekte anlegen (Tabellen, Views, Prozeduren). Die in
> diesem Abschnitt beschriebene Auslagerung der Materialisierung an ein
> externes Reconcile-Skript ist damit nur noch der Fallback; Split-Views,
> Verdict-Tabellen, Gate-Prozeduren und episodische Quarantäne-Tabellen
> materialisiert Signal selbst. Siehe
> `Konzept_Datasphere_Integration_Gating_Quarantaene.md` (inkl.
> ADR-0002-Amendment). Die Enforcement-Achse (§0, §4) und die Verdict-Regel
> bleiben unverändert gültig.

Signal ist **read-only** gegenüber HANA/Datasphere (ADR-0002, Gate G2). Es kann
keine Zeilen physisch in eine Quarantäne-Tabelle verschieben. „Durchsetzung" ist
deshalb ein **Urteil, das Signal berechnet** und das ein externer Orchestrator
(Datasphere-Task-Chain / Cron / CLI) umsetzt.

```
ERKENNEN + ENTSCHEIDEN     (Signal — read-only)
  └─ Checks laufen → gate_verdict ∈ {proceed|quarantine|block} → Episode + Prädikat
AUF DATEN WIRKEN           (Task-Chain / Reconcile-Skript in Datasphere)
  └─ gut/schlecht trennen, schlechte parken, gute weiterleiten
ZURÜCKMELDEN               (Skript → Signal)
  └─ Status: N Zeilen quarantänisiert → Signal zeigt Episode + Count
FREIGEBEN                  (Mensch in Signal → nächster grüner Lauf löst auf)
```

### Das Prädikat existiert bereits

Jeder Quarantäne-Check kompiliert zu `SELECT COUNT(*) ... WHERE <bad>`. Die
Engine schreibt das bereits in die Diagnose-Form um (`_diagnostic_sql`,
`check_engine.py:364`). Damit ist die Trennregel kostenlos vorhanden:

```
gute Zeilen        = WHERE NOT (<bad>)
quarantänisierte   = WHERE <bad>
```

Signal braucht also nichts Neues, um die Quarantäne zu *beschreiben* — das
Prädikat des Checks ist die Splitregel. Es wird im Manifest veröffentlicht.

---

## 2 — Quarantäne-Flow in Datasphere × Signal

**A — typische Task-Chain**
```
[Load → Staging] → [Signal-Lauf] → Verzweigung nach Urteil
                                     ├ proceed    → in Consumer-View publizieren
                                     ├ quarantine → Split-Step, nur CLEAN publizieren
                                     └ block      → Chain stoppen, alarmieren
```

**B1 — View-basierter Split** (spiegelt den bestehenden Monitoring-Share-Hub,
`services/api/routers/monitoring.py`)
1. Signal berechnet `verdict=quarantine`, öffnet eine `dq_quarantine`-Episode.
2. Signal veröffentlicht ein **Quarantäne-Manifest** (Soll-Zustand): Zielobjekt,
   `WHERE <bad>`-Prädikat, Contract-Version.
3. Ein externes Reconcile-Skript materialisiert zwei Views aus Staging:
   - `V_<obj>` (Consumer) = `WHERE NOT(<bad>)` → gute Zeilen fließen weiter
   - `V_<obj>_QUARANTINE` = `WHERE <bad>` → isolierte Zeilen geparkt
4. Skript meldet Status zurück: `quarantined, row_count=N`.
5. Signal zeigt Episode + N am Objekt-Badge und auf der Quarantäne-Seite.

**B2 — Staging-Promotion-Gate** (ohne Zusatz-Views): Die Chain promotet
Staging→Curated nicht, solange `verdict=quarantine`. Einfacher, aber nur
objektgranular statt zeilenbasiert.

### Granularität — ehrliche Grenze
Zeilenbasierter Split (B1) setzt voraus, dass das Fehlerprädikat als Filter auf
dasselbe Objekt ausdrückbar ist. Das gilt für `not_null`, `completeness`,
`keys` (Duplikate), `referential` (Orphans). Für `freshness`/`volume`
(Objekt-Eigenschaften) gilt es **nicht** — die quarantänisieren objektgranular
(B2).

---

## 3 — Aufruf-Topologie: Scheduler → CLI vs. API

> **Update 2026-07-09 — Prämisse überholt.** SAP hat 2025 **API-Tasks** als
> Schritttyp in Task Chains eingeführt (POST/PUT über eine HTTP-Connection,
> synchron ≤ 60 s oder asynchron mit Status-Polling über den
> `Location`-Header). „Die Task-Chain ruft die Signal-API" **ist** damit ein
> vorhandener Schritttyp; das Verdict bleibt aus Chain-Sicht binär
> (COMPLETED/FAILED). Konsequenzen und empfohlener Async-Vertrag: siehe
> `REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md` §4.2/§4.3.
> Die folgenden Absätze beschreiben den Stand vor diesem Feature; Option A
> (CLI) bleibt für Nicht-DSP-Orchestratoren und Lite gültig.

Eine Datasphere-Task-Chain orchestriert Datasphere-Objekte; sie konnte
ursprünglich **nicht** nativ ein Shell-Kommando ausführen oder einen
ausgehenden HTTP-Call machen. Ein **externer Orchestrator** war deshalb der
Dirigent (ADR-0005: Scheduling ist extern, Cron/Task-Chain → CLI; die API
triggert nur ad hoc).

| | **Option A — CLI** (empfohlen) | **Option B — API** |
|---|---|---|
| Engine läuft | auf dem Runner | im Signal-Service |
| Verzweigungs-Signal | **Exit-Code** | `gate_verdict`-Feld (pollen) |
| Signal dauerhaft nötig | nein | ja (Container-Betrieb) |
| Ergebnis im Cockpit/Store | nur bei geteiltem `--db` | immer |
| Passt zu | Lite / Cron / CI / harter Gate | Full / Container-Deployment |

**Option A (empfohlen):**
```
scheduler:
  1. Datasphere-Load triggern
  2. python cli/dq_check_runner.py --schema ... --checks ...
  3. case $? in
       0) "promote"-Chain triggern ;;
       3) "quarantine/split"-Chain triggern ;;
       1) stoppen + alarmieren ;;
     esac
```

**Option B (Service-Modus):** `POST /api/objects/{id}/run` → `run_id`, dann
`GET /api/runs/{run_id}` pollen bis fertig, `gate_verdict` lesen, gleich
verzweigen.

Der **Split-Step selbst** (die `V_*`-Views bzw. Staging→Curated-Promotion) ist
in beiden Fällen ein normaler Datasphere-Bestandteil, getrieben vom gewählten
Zweig.

### Exit-Codes (Option A)
| Verdict | Exit-Code | Hinweis |
|---|---|---|
| `proceed` | `0` | Erfolg (Konvention) |
| `block` | `1` | generischer Fehler (Konvention) |
| `quarantine` | `3` | **bewusst nicht `2`** |

> `2` ist bereits belegt: `cli/dq_check_runner.py:39` (fehlendes `--host`) und
> argparse bei falschen Argumenten. Quarantäne darf damit nicht kollidieren.
> Ein `--no-enforce`-Flag soll Beobachtungsläufe unabhängig vom Urteil mit `0`
> beenden. Das Urteil gehört zusätzlich in die Text-/JSON-Ausgabe.

---

## 4 — Implementierungs-Slice (volle Vertikale, Default `monitor`)

> Gates bleiben scharf: **G1** (kein SQL im Contract), **G6** (Gating-States nie
> still auslassen), **G7** (`dq_core` frameworkfrei), **G8** (PII-Gate). **G2**
> ist nicht betroffen — es wird kein SQL erzeugt, nur ein Dataclass-Feld gesetzt.

**Layer 1 — Engine (`packages/dq_core/`, frameworkfrei)**
- `engine/models.py`: `VALID_ENFORCEMENT = {"gate","quarantine","monitor"}`;
  `enforcement` auf `CheckDef` + `CheckResult` (Default `monitor`);
  `gate_verdict` auf `RunSummary` (Default `proceed`).
- `engine/check_engine.py`: `enforcement` in `load_dataset_config` parsen
  (analog `severity`/`kind`, `:51-60`) und in `dataset_config_to_yaml` ausgeben;
  Feld in allen `CheckResult`-Konstruktoren durchreichen (inkl.
  `skipped_stale`); neue `_gate_verdict(results)` parallel zu `_overall_status`
  (`:473`); `summary.gate_verdict` in `run_checks` setzen.
- `contract/model.py`: `Guarantee.enforcement` + `Contract.enforcement_default`
  (Lite: ein Schalter fürs ganze Produkt).
- `contract/validator.py`: `_ENFORCEMENT`-Enum überall dort anhängen, wo
  `_SEVERITY` hängt (`:58-158`).
- `contract/compiler.py`: `_enforcement(g, default)` analog `_severity` (`:51`),
  `CheckDef.enforcement` setzen — nur Dataclass-Feld, SQL unberührt.

**Verdict-Regel** (state-bewusst, nur `executed`/`error` zählen):
```
block      wenn ein gefailter Check enforcement=gate       und severity∈{fail,critical}
quarantine sonst, wenn ein gefailter Check enforcement=quarantine und severity∈{fail,critical}
proceed    sonst   # monitor-Fails eskalieren das Urteil NIE
```

**Layer 2 — Store (`packages/dq_core/store/`)**
- Neue Migration `migrations/010_enforcement.sql` (vorhandene nie ändern):
  `enforcement_mode` an `dq_check_results`, `gate_verdict` an `dq_runs`, neue
  Tabelle `dq_quarantine` (modelliert nach `dq_incidents`,
  `004_incident_lifecycle.sql`).
- `sqlite_store.py`: `save_run` (`:99`) + `try_begin_run` (`:222`) um die neuen
  Spalten erweitern; `open_quarantine`/`list_quarantine`/`release_quarantine`
  analog zu `open_incident`/`list_incidents` (`:457-593`); Diagnose-Zeilen über
  den bestehenden `get_diagnostics`-Pfad (`:187`) — keine neue Rohzeilen-
  Erfassung, **G8 bleibt intakt**.

**Layer 3 — CLI (`cli/dq_check_runner.py`)**
- `gate_verdict` → Exit-Code (`0/1/3`, siehe §3); `--no-enforce`-Flag; Urteil in
  Text-/JSON-Ausgabe.

**Layer 4 — API (`services/api/`)**
- `routers/runs.py` (`:68`,`:98`): `gate_verdict` in Antwort + Schema.
- `routers/objects.py`: aktuelles Urteil/Quarantäne-Status je Objekt.
- Neuer `routers/quarantine.py` (Prefix `/api/quarantine`, nach
  `routers/incidents.py`): `GET /` Liste; `POST /{id}/release` mit
  `require_roles(steward, owner, admin)`; in `create_app()` registrieren
  (`main.py:106`); RFC-7807-Fehler (S-14). Kein neuer `/api/monitoring*`-Pfad
  (Namenskollision mit dem Monitoring-Share-Hub vermeiden).
- Lauf-Pfad ruft bei `verdict=quarantine` `open_quarantine` und routet über die
  bestehenden `dq_notification_rules` (Migration 005): `monitor`→Alert,
  `quarantine`/`gate`→Incident.

**Layer 5 — Frontend (`apps/cockpit/`)**
- `src/api/schema.d.ts` regenerieren (`npm run gen:api`).
- StatusGrid / `pages/Cockpit.tsx` + `ObjectDetail.tsx`: Enforcement-Badge +
  Urteils-Indikator (getrennt von der Pass/Fail-Ampel).
- Neue `pages/Quarantine.tsx` (nach `pages/Incidents.tsx`): Episoden-Liste,
  Drilldown in PII-gegatete Diagnose-Zeilen, „Freigeben"-Aktion (rollen-gegated);
  Lazy-Route in `App.tsx`.
- `pages/ContractWorkbench.tsx`: Enforcement-Auswahl je Garantie +
  `enforcement_default` auf Contract-Ebene (Lite: ein Schalter).
- `src/i18n/de.ts`: `gate`→„Sperren", `quarantine`→„Quarantäne",
  `monitor`→„Beobachten", Urteils-Labels, Freigabe-Aktion.

---

## 5 — Bewusst außerhalb des Scopes
- Physisches Schreiben von Zeilen in eine Datasphere-Quarantäne-View — Signal
  bleibt read-only; das ist Sache des externen Reconcile-Skripts (gleiches
  Muster wie der Monitoring-Share-Hub).
- Auto-Freigabe bei grünem Folgelauf — Start mit manueller Freigabe;
  Auto-Recovery kann später die Compliance-Auto-Recovery spiegeln.

---

## 6 — Verifikation (End-to-End)
1. **Unit:** `make test` — Verdict-Rollup-Matrix (gate/quarantine/monitor ×
   pass/fail/critical/warn × skipped_stale), Compiler-Propagation,
   Validator-Ablehnung; G5-Engine-Regression bleibt grün.
2. **CLI:** `python cli/dq_check_runner.py --schema MY --checks <fixture> --mock`
   — failender `gate`-Check → Exit `1`; auf `monitor` umgestellt → Exit `0`,
   `verdict=proceed` in der Summary.
3. **Store:** `SQLITE_DB=signal.db make seed`; failende `quarantine`-Garantie →
   `dq_runs.gate_verdict='quarantine'`, `dq_quarantine`-Zeile offen, Diagnose
   nur bei opt-in (G8).
4. **API:** `GET /api/runs/{id}` zeigt `gate_verdict`; `GET /api/quarantine`
   listet die Episode; `POST /api/quarantine/{id}/release` als `viewer` → 403,
   als `steward` → 200.
5. **Frontend:** Objekt zeigt Enforcement-Badge; Quarantäne-Seite listet/gibt
   frei; `npm run typecheck && npm run lint && npm run test -- --run` grün.
6. **Gates lokal:** G1-Grep sauber, G6 (übersprungene Checks behalten Modus,
   bleiben statusneutral), G7 (`dq_core` ohne Web-Framework), Coverage-Schwelle.
