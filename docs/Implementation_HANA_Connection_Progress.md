# Implementation Plan — Realer HANA-Connection-Pfad + Connection-UI + Progress

**Adressat:** Entwicklung · **Stand:** 2026-06-26 · **Modus:** sequentiell wie HANDOVER, jeder Schritt mit Acceptance, kein Merge bei rotem Gate.
**Zweck:** Den hdbcli-Verbindungspfad **nachweisbar lauffähig** machen, eine **Connection-/Environment-Oberfläche mit Test-Funktion** bereitstellen und **überall, wo eine hdbcli-Connection geöffnet wird** (Run, Dry-Run/Preview, Profiling/Validation, Connection-Test) einen **Live-Progress** anzeigen.

> Verwandt: [`Tooldokumentation.md`](Tooldokumentation.md) §6/§10 (ENV, Deployment) · [`REVIEW_Tool_v2_Status.md`](REVIEW_Tool_v2_Status.md) (Verification-only: realer HANA-Pfad, O6) · [`HANDOVER.md`](HANDOVER.md) §5 (O6 HanaResultStore).

---

## 0 — Geltende Invarianten (NICHT verletzen)

- **G7 Framework-Isolation.** `dq_core` importiert nie FastAPI/sqlite-API-spezifisches aus dem Service. Progress wird in `dq_core` ausschließlich über den **vorhandenen `on_progress(line)`-Callback** emittiert; das Persistieren bleibt in `services/api` bzw. hinter dem Store-Protocol.
- **G2/[SCHEMA-MAP].** `{schema}` wird weiterhin nur zur Laufzeit gebunden (in den Öffnungsstellen), nie im Contract.
- **S-13 fail-closed.** Kein stiller Mock-Fallback; Treiber-/Auth-/Konfigfehler sichtbar als 502/503 mit sicherer Meldung (keine Interna).
- **S-1/Secrets.** Credentials kommen über `password_ref` → `secrets.get_secret`; die UI sieht **nie** ein Passwort, nur einen `secret_status` (bool) und den Referenz-Namen.
- **G4.** Jede API-Form-Änderung ⇒ `openapi-typescript` neu generieren, `git diff --exit-code`.

## 1 — Ist-Zustand (verifiziert 2026-06-26)

| Stelle | Datei | Connection | Progress |
|---|---|---|---|
| Run | `services/api/routers/objects.py:373` (`_run_thread`) | `get_connection(on_progress=callback)` ✅ | ✅ store-Protocol + SSE (op_id-basiert) |
| Dry-Run / Preview | `services/api/routers/checks.py:18` | `get_connection(...)`, **synchron** | ❌ keiner |
| Profiling / Validation | `services/api/routers/profile.py:105` | `get_connection(...)`, **synchron** | ❌ keiner |
| Connection-Test | — | existiert nicht | — |

- **Connection-Helper:** `packages/dq_core/connect/db_connection.py` — ✅ vollständig (Retry, `statementTimeout`, `encrypt`+`sslValidateCertificate`, fail-closed). `on_progress`-Callback bereits integriert (Verbinde/Verbunden/Retry-Zeilen). `DbConnection`/`DbCursor` als `runtime_checkable Protocol` definiert (Z. 25–42). `check_connection()` vollständig implementiert (Z. 169–277).
- **Progress-Kanal:** `services/api/sse.py` — ✅ generalisiert: `make_progress_callback(op_id, store)` schreibt via `store.append_progress` (kein raw sqlite3); `sse_generator(store, stream_id)` liest via `store.get_progress`/`get_operation`, unterstützt beliebige `op_id` (nicht nur `run_id`). Endpoints `GET /api/operations/{op_id}/events` + `GET /api/operations/{op_id}` vorhanden.
- **Store-Protocol:** `dq_core/store/base.py` — ✅ alle Operation-Methoden definiert (`append_progress`, `get_progress`, `begin_operation`, `finish_operation`, `get_operation`). `sqlite_store.py` vollständig implementiert. Migration `008_operations.sql` existiert (inkl. `009_schedules.sql`).
- **Environments:** `deps.get_environment(name)` ✅ (host/port/schema + `password_ref`→`secrets.get_secret`). `GET /api/environments` in `routers/environments.py` — kein `secret_status`, kein maskierter `host`, **kein** Test-/Status-Endpoint.
- **Result-Store HANA:** `packages/dq_core/store/hana_store.py` = Stub (alle Methoden `raise NotImplementedError`); `deps.get_store()` wirft `RuntimeError` bei `STORE_BACKEND=hana`. `RESULTS_ENVIRONMENT` fehlt in `settings.py`.
- **Frontend:** `store/sseStore.ts` (EventSource auf globalem `/api/stream`, nicht parametrisiert), `api/runs.ts::useRunStream`, `components/LiveRunPanel.tsx` vorhanden. Kein `useOperationStream`, kein `OperationProgress.tsx`, kein Connections-Screen, kein Progress in Dry-Run/Profile.

## 2 — Zielbild

1. **Ein generischer Operation-/Progress-Kanal** (`op_id`) über das **Store-Protocol** statt rohem sqlite3 — nutzbar von Run, Dry-Run, Profile, Connection-Test; HANA-tauglich.
2. **`get_connection` emittiert Phasen** über den `on_progress`-Callback: „Verbinde mit host:port…", „Verbunden (HANA <version>)", „transienter Fehler, Versuch n…".
3. **Connection-Test** als eigener Endpoint + UI mit Live-Progress und Status-Badge (ok / Latenz / Server-Version / Schema sichtbar / Fehler).
4. **Dry-Run & Profile asynchron** wie der Run (sofort `op_id`, Hintergrund-Thread, Live-Progress, Ergebnis am Ende des Streams + Poll-Endpoint).
5. **`HanaResultStore` (O6)** implementiert, damit der **Full-Deployment-Pfad** (HANA-Result-Store) lauffähig ist — inkl. Progress-Persistenz über das Protocol.
6. **Verifikations-Harness**, das den realen hdbcli-Pfad gegen eine echte HANA ausführt (env-gated), sodass er reproduzierbar nachgewiesen ist.

## 3 — Vorab zu treffende Entscheidungen

| # | Entscheidung | Empfehlung |
|---|---|---|
| D1 | Dry-Run/Profile **async** (op_id + Stream) **oder** sync mit unbestimmtem Spinner? | **Async** — nur so gibt es echten Progress „überall wo eine Connection öffnet". Kostet G4-Regen + FE-Umbau, ist aber die Anforderung. |
| D2 | Herkunft + Ziel der **Result-Store-Connection** bei `STORE_BACKEND=hana` | **Ins Open SQL Schema des Datasphere-DB-Users schreiben** (der User hat dort DDL/DML — die Migrationen legen die wenigen Result-Tabellen selbst an). Vorteil: die Ergebnisse sind danach **in Datasphere weiterverarbeitbar** (Loop geschlossen — Quality-KPIs als DSP-Quelle für SAC/Modelle). Schema-Name kommt aus dem Environment (kein hartkodiertes `dq_results_lt`). Optional kann **derselbe** Datasphere-DB-User auch lesen (Space-exponierte Prüf-Objekte via „Enable read access"), wodurch Lese- und Schreib-Connection zu **einem** User kollabieren — abhängig von den Grants im Space (S-4). |
| D3 | Environments **in der UI editierbar** oder read-only + Test? | **Read-only + Test** in v1 (Anlage via `environments.yml`/Secret-Store, Governance-Akt). UI-Editor (ohne Secret-Eingabe) als späteres Opt-in. |
| D4 | **HANA-Testumgebung** für Verifikation | Klären: HANA Cloud Trial / `hanaexpress`-Container / Kunden-Sandbox. Ohne sie bleibt WS F „skipped" (env-gated), aber der Code ist fertig. |

---

## WS A — Connection-Layer: Test + Progress ✅ Erledigt

**A1 `ConnectionProtocol` + `check_connection`** `dq_core/connect/db_connection.py`
- `DbConnection`/`DbCursor` als `runtime_checkable Protocol` ✅ (Z. 25–42)
- `check_connection(host, port, user, password, schema, *, on_progress=None) -> dict` ✅ (Z. 169–277): `SELECT 1 FROM DUMMY` + `SELECT VERSION FROM M_DATABASE`, Schema-Sichtbarkeit, sichere Fehlermeldungen (S-14)

**A2 `get_connection` instrumentieren** ✅
- `on_progress: ProgressCallback | None` integriert (Z. 110): Verbinde-/Verbunden-/Retry-Zeilen vor/nach `dbapi.connect`; kein `services/`-Import (G7)

*Acceptance A: erfüllt.* Unit-Tests prüfen `check_connection` mit hdbcli-Double; `MockConnection` erfüllt das Protocol.

---

## WS B — Generischer Operation-/Progress-Kanal (store-getrieben) ✅ Erledigt

**B1 Migration 008** `packages/dq_core/store/migrations/008_operations.sql` ✅
- `dq_operations` + `dq_progress`-Tabellen vorhanden (aktuell neueste Migration: `009_schedules.sql`). HANA-Dialektvariante fehlt noch (→ WS E1).

**B2 Store-Protocol erweitern** ✅
- `dq_core/store/base.py`: alle 5 Methoden im Protocol (Z. 30–44)
- `sqlite_store.py`: vollständig implementiert (Z. 241–306)
- Roher `sqlite3`-Zugriff aus `sse.py` entfernt — Progress läuft über das Protocol (G7 eingehalten)

**B3 SSE generalisieren** ✅ `services/api/sse.py`
- `sse_generator(store, stream_id)` liest via `store.get_progress`/`get_operation`; Terminalzustand aus `dq_runs` oder `dq_operations`
- `make_progress_callback(op_id, store)` nutzt `store.append_progress`
- Endpoints vorhanden: `/api/stream?run_id=` (Rückwärtskompat) + `GET /api/operations/{op_id}/events` + `GET /api/operations/{op_id}`

*Acceptance B: erfüllt.*

---

## WS C — Öffnungsstellen instrumentieren (Run · Dry-Run · Profile · Test)

Gemeinsames Muster (wie der bestehende Run): Endpoint legt `op_id` an (`begin_operation`), startet Hintergrund-Thread, gibt sofort `202 {op_id}` zurück; der Thread bindet `{schema}`, öffnet die Connection **mit `on_progress=make_progress_callback(op_id, store)`**, führt aus, schreibt `finish_operation`.

**C1 Run** ✅ Erledigt — `objects.py:_run_thread` (Z. 373–398) übergibt bereits `on_progress=callback` an `get_connection`; Connection-Phasen erscheinen im Stream.

**C2 Dry-Run / Preview** `routers/checks.py` (aktuell synchron, Z. 18–137)
- `POST /checks/{dataset}/dry-run` → `202 {op_id}` (statt synchronem Ergebnis). Thread: validate (G1) → compile → `get_connection(on_progress=…)` → `run_checks(..., on_progress=callback, results_db=None)` → `finish_operation(op_id, "finished", result_json=<summary>)`. Der `compile_only`-Pfad (kein Environment) bleibt **synchron** (kein Connection-Open, kein Progress nötig).
- Per-Check-Progress kommt **gratis** aus dem vorhandenen `on_progress` von `run_checks`.

**C3 Profiling / Validation** `routers/profile.py` (aktuell synchron, Z. 105–197)
- `POST /objects/{id}/profile` → `202 {op_id}`. Thread: `get_connection(on_progress=…)` → Progress je Phase: „Profiliere Spalten…", „PK-Kandidaten (composite)…", „Sample Rows [PII-GATE]…" → `finish_operation` mit dem Profil-Result. `profile_table`/`analyze_composite_candidates` bekommen einen optionalen `on_progress`-Parameter (additiv) für „Spalte k/n".

**C4 Connection-Test** `routers/environments.py` (dort leben bereits alle anderen Environment-Endpoints)
- `POST /api/environments/{name}/test` → `202 {op_id}`. Thread: `get_environment(name)` → `check_connection(..., on_progress=…)` → `finish_operation` mit `{ok, latency_ms, server_version, schema_visible}`. `[AUTHZ]`: steward+.
- `GET /api/environments` zusätzlich `secret_status` (aus `secrets.secret_status(password_ref)`) + `host` maskiert (`***.example.com`) — nie Passwort.

*Acceptance C:* Jeder der vier Endpoints liefert `202 {op_id}`; der Stream zeigt mindestens „Verbinde…"→„Verbunden"→fachliche Schritte→Terminal; Dry-Run-/Profile-Ergebnis ist am Stream-Ende und über den Poll-Endpoint abrufbar; ohne Environment bleibt Dry-Run `compile_only` synchron.

---

## WS D — Frontend: Operation-Progress + Connections-Screen

**D1 Generischer Stream-Hook + Komponente** `apps/cockpit/src`
- `store/sseStore.ts` → generalisieren auf beliebige `op_id` (heute nur `/api/stream` global); neuer `useOperationStream(opId)` (EventSource `/api/operations/{opId}/events`, Polling-Fallback wie `useRunStream`).
- `components/OperationProgress.tsx` — schlanke **Progressbar/Stepper** (Phasenliste + Determinate-Balken, sobald „k/n" geparst wird; sonst indeterminate) + Live-Log-Auszug. Wiederverwendbar in Dialogen.

**D2 Connections-Screen** `pages/Connections.tsx` + Route `/connections` (oder Panel in `Governance`)
- Liste der Environments (`name`, `schema`, maskierter `host`, `secret_status`-Badge). Pro Zeile **„Verbindung testen"** → `POST …/test`, `OperationProgress`, danach Status-Badge: ✅ ok · Latenz `xx ms` · `HANA <version>` · Schema sichtbar — oder ❌ mit sicherer Fehlermeldung.
- i18n nach `i18n/de.ts`; Status-Encoding ≥3-von-4 (Farbe+Form+Label, Carbon). `[AUTHZ]`: Test sichtbar nur steward+.

**D3 Progress in die bestehenden Dialoge einhängen**
- `RunTriggerDialog`/`LiveRunPanel`: auf `useOperationStream` umstellen (Run ist eine Operation), Connection-Phasen erscheinen jetzt mit.
- `ContractWorkbench` DryRunPanel: `useDryRunChecks` liefert künftig `op_id` → `OperationProgress` während des Laufs, Ergebnis aus dem Terminal-Event.
- `ObjectProfilePanel`: `useProfileObject` → `op_id` → `OperationProgress` (Verbinden + Profiling-Phasen), Ergebnis am Ende.

**D4 G4** `npm run gen:api` (neue/aenderte Endpoints) + `git diff --exit-code`; TS strict grün.

*Acceptance D:* Ein Steward testet eine Verbindung und sieht live „Verbinde…→Verbunden (HANA …)→OK 42 ms"; Dry-Run und Profiling zeigen jeweils einen Fortschrittsbalken inkl. der Connection-Phase; Viewer sieht keine Test-/Run-Aktion.

---

## WS E — HanaResultStore (O6) → Open SQL Schema *(parallel; nötig für Full-Deployment)*

**Ziel (D2):** in das **Open SQL Schema des Datasphere-DB-Users** schreiben. Dort hat der User DDL/DML — die Migrationen legen die wenigen Result-Tabellen selbst an. Der Schema-Name wird zur Laufzeit aus dem Environment gebunden (`[SCHEMA-MAP]`, kein hartkodiertes `dq_results_lt`). Folge: die Ergebnis-Tabellen können als Quelle zurück in einen Datasphere-Space übernommen und dort weiterverarbeitet werden (geschlossener Loop — Quality-KPIs als DSP-Quelle für SAC/Modelle).

**E1 HANA-Dialekt-Migrationen** `store/migrations/hana/NNN_*.sql` (oder Dialekt-Schalter im Runner)
- SQLite-Spezifika übersetzen (`INTEGER PRIMARY KEY AUTOINCREMENT` → HANA-Identity/Sequence, `TEXT`→`NVARCHAR`, partieller Unique-Index für Run-Guard → HANA-Äquivalent).
- `CREATE TABLE` **qualifiziert auf das Open-SQL-Schema** (Name aus dem Environment, `currentSchema`); Idempotenz wie bei SQLite über den Migration-Runner (`schema_migrations` im selben Schema).

**E2 `HanaStore`** `store/hana_store.py` — alle `ResultStoreProtocol`-Methoden via hdbcli implementieren (inkl. `append_progress`/`get_progress`/`*_operation` aus WS B, `try_begin_run`/Run-Guard, `get_sla`, Heatmap/Trend/Series). Connection + Ziel-Schema aus dem Datasphere-DB-User-Environment (D2).

**E3 `deps.get_store()`** baut bei `STORE_BACKEND=hana` den `HanaStore` (Connection + Open-SQL-Schema auflösen) statt zu werfen. Zusätzlich: `RESULTS_ENVIRONMENT`-Eintrag in `services/api/settings.py` ergänzen (noch nicht vorhanden).

**E4 Re-Consumption (Doku, kein Code):** Damit die Result-Tabellen in Datasphere konsumierbar sind, muss der Space das Open SQL Schema als Quelle hinzufügen / die Tabellen importieren — ein Deployment-/Konfig-Schritt. In `Tooldokumentation.md` §10 festhalten.

*Acceptance E:* `ResultStoreProtocol`-Konformitätstest (`runtime_checkable`, `isinstance`) für `HanaStore`; die bestehende Store-Test-Suite läuft env-gated (`HANA_SMOKE=1`) auch gegen das Open SQL Schema grün; `STORE_BACKEND=hana` legt die Tabellen im konfigurierten Schema an und startet ohne Fehler; die Result-Tabellen sind aus dem Space heraus lesbar (manuell verifiziert).

---

## WS F — Verifikation, DB-User-Härtung, Doku

**F1 Smoke-Harness** `tests/integration/test_hana_smoke.py` + `make hana-smoke`
- Mit `HANA_SMOKE=1` + Env-Vars: `check_connection` grün; ein Mini-Contract Compile→Dry-Run→Run gegen echte HANA; Multi-Worker-Run (2 uvicorn) gegen denselben (HANA-)Store. Ohne Flag: `pytest.skip` (CI bleibt grün).
- Reproduzierbares Ziel dokumentieren (HANA Cloud Trial / `hanaexpress`-Container).

**F2 DB-User-Härtung (S-4)** in `Tooldokumentation.md` §9/§10 festhalten: Lese-Zugriff nur `SELECT` auf die Space-exponierten Prüf-Objekte; Schreib-Zugriff der Result-Store-User **auf sein eigenes Open SQL Schema** (DDL/DML dort, sonst nichts); nie Space-Admin. Ob ein **einziger** Datasphere-DB-User beides abdeckt (lesen via „Enable read access", schreiben ins eigene Open-Schema) oder zwei getrennte User — abhängig von den Space-Grants; beide Varianten dokumentieren. TLS bereits `encrypt`+Cert (verifiziert).

**F3 Doku nachziehen:** `Tooldokumentation.md` §5 (neue Operation-/Test-Endpoints), §6 (`RESULTS_ENVIRONMENT`-ENV), §8 (Connections-Screen, Progress in Dry-Run/Profile); `REVIEW_Tool_v2_Status.md` (HANA-Pfad/O6 von „verification-only/open" auf „done" ziehen, sobald F1/E grün).

**F4 `scripts/generate_environments.py` + `DatasphereClient.list_db_users()`**
- Neue Methode `list_db_users(space_id) -> list[dict]` in `services/api/datasphere.py`: `GET /api/v1/dwc/catalog/spaces/{id}/dbUsers` via bestehendem `_get()` — liefert `user_name` + Open-SQL-Schema-Name (`<SPACE>#<CUSTOM>`).
- Script `scripts/generate_environments.py`: nutzt die vorhandenen `DATASPHERE_BASE_URL/CLIENT_ID/CLIENT_SECRET/TOKEN_URL` aus `.env` (keine neuen Env-Variablen). Ohne Argumente: interaktive Auswahl aus `list_spaces()` + `list_db_users()`; mit `--space`/`--db-user` direkt. Schreibt `environments.yml` mit host/port/user/schema vorausgefüllt; `password_ref: "<bitte eintragen>"` bleibt Platzhalter — kein Passwort wird verarbeitet (S-1).

```bash
python scripts/generate_environments.py --space DQ_SIGNAL --db-user DQ_SVC
# → environments.yml mit schema: DQ_SIGNAL#DQ_SVC, password_ref: "<bitte eintragen>"
```

*Acceptance F4:* generierte YAML ist direkt von `deps.get_environment()` ladbar; ohne Argumente läuft interaktive Auswahl durch; kein Secret erscheint in Output oder Log.

**F5 `FileSecretResolver` + `PUT /api/admin/environments/{name}/secret`** ✅ Erledigt
- `services/api/secrets.py`: `_var_name_from_ref()`, `FileSecretResolver` (liest `secrets.local.yml` frisch je Aufruf), `ChainedSecretResolver` (Env-Var hat Vorrang), `write_secret(ref, value, path)` (atomar, logt nie den Wert), `init_resolver(secrets_file)`.
- `services/api/settings.py`: `secrets_file: str = Field(default="secrets.local.yml")`.
- `services/api/main.py`: `init_resolver(settings.secrets_file)` in `create_app()`.
- `services/api/routers/environments.py`: `PUT /{name}/secret` (admin+, 204) — schreibt via `write_secret` in `secrets.local.yml`; `plain:`-Referenzen werden mit 422 abgelehnt.
- `.gitignore`: `secrets.local.yml` eingetragen.
- Frontend (→ D2): Passwort-Feld im Connections-Screen, das `PUT /api/admin/environments/{name}/secret` aufruft; danach `password_set`-Badge neu laden.

*Flow:* `generate_environments.py` → `environments.yml` mit `password_ref: env:HANA_PW_DQ_SVC` → Connections-UI zeigt Environment vorausgefüllt mit `password_set: false` → Admin gibt Passwort ein → `PUT …/secret` → `secrets.local.yml` (gitignored) → `secret_status: true`.

---

## WS G — Quarantäne / Reject-Store *(optional, nach E; durch In-HANA-Store erst sinnvoll)*

**Idee:** zeilen-genaue Verstöße in eine Quarantäne-Tabelle **im selben Open SQL Schema** schreiben — per `INSERT … SELECT` **direkt in HANA**, sodass die Rohzeilen den App-Prozess **nie** berühren (E6 strikt eingehalten, stärker als der heutige `dq_diagnostics`-Pfad). Die Tabelle ist aus dem Space zurück-konsumierbar → Reject-/Remediation-Dashboards in SAC.

- **Nur zeilen-identifizierbare Familien:** `not_null`, `completeness`, `keys`/Duplikate, `referential` (Orphans), `matches`/Regex, `cross_field`. **Nicht** `volume.min_rows`/`freshness`/`volume_anomaly` (keine Einzelzeilen).
- **Compiler erweitern** (`dq_core/contract/compiler.py`): neben dem Aggregat-Check optional einen **Quarantäne-`SELECT`** mit demselben Verletzungs-Prädikat emittieren, projiziert auf **PK + Allowlist-Spalten**, mit `LIMIT N`. Opt-in je Garantie: `quarantine: { enabled, columns[], limit }`, **default off**.
- **Tabelle** (Migration, HANA + SQLite): `dq_quarantine(id, run_id, dataset, check_name, captured_at, row_key, payload_json)` — `payload_json` nur Allowlist-Spalten. TTL-Cleanup wie `DIAGNOSTICS_TTL_DAYS`.
- **PII-Disziplin = `dq_diagnostics`:** default-off, Spalten-Allowlist, TTL, restriktiver Zugriff. Verhältnis zu `dq_diagnostics` entscheiden (ablösen vs. zweite Stufe).
- **Ausführung:** im Run-/Dry-Run-Thread nach einem fehlgeschlagenen, quarantäne-fähigen Check ein `INSERT … SELECT` ins Open-Schema absetzen (Progress-Zeile „Quarantäne: N Zeilen erfasst").

*Acceptance G:* fehlschlagender `not_null`-Check mit `quarantine.enabled` schreibt **nur** Key+Allowlist-Spalten per `INSERT … SELECT`; der App-Prozess sieht **keine** Rohzeile; `volume`/`freshness` erzeugen **keine** Quarantäne; TTL löscht abgelaufene Zeilen; ohne `enabled` bleibt die Tabelle leer.

*Aufwand:* 2–3 PT (Compiler-Paar-Query + Migration + Ausführungs-Hook + Tests).

---

## Sequenz & Aufwand

| WS | Inhalt | hängt ab von | Aufwand (PT) | Status |
|----|--------|--------------|--------------|--------|
| A | Connection-Test + `on_progress`-Instrumentierung | — | ~~1–1,5~~ | ✅ Erledigt |
| B | Operation-/Progress-Kanal (Migration 008, Store-Protocol, SSE generalisieren) | A | ~~2–3~~ | ✅ Erledigt |
| C1 | Run mit Connection-Phasen | B | ~~0,5~~ | ✅ Erledigt |
| C2–C4 | Dry-Run/Profile async + Connection-Test-Endpoint | B | 1,5–2 | ✅ Erledigt |
| D | FE: `useOperationStream`, `OperationProgress`, Connections-Screen, Dialoge | C | 3–4 | ⬜ offen |
| E | `HanaResultStore` (O6) + HANA-Migrationen + `RESULTS_ENVIRONMENT` | B (Protocol) | 4–6 | ⬜ offen |
| F1–F3 | Smoke-Harness, DB-User-Härtung, Doku, `generate_environments.py` | C–E | 2–2,5 | ⬜ offen |
| F5 | `FileSecretResolver` + `PUT …/secret` + `secrets.local.yml` | — | ~~1~~ | ✅ Erledigt |
| G | Quarantäne/Reject-Store (optional) | E | 2–3 | ⬜ optional |

**Verbleibend ≈ 7,5–10,5 PT** (ohne WS G; mit Quarantäne +2–3 PT). WS A, B, C1–C4 sind abgeschlossen — rund 6–7 PT bereits investiert. Kritischer Pfad D; E läuft parallel.

## Definition of Done

- `check_connection` + Connection-Test-UI zeigen live Verbinden→Verbunden→Status; Fehlerfälle sicher (keine Interna).
- **Jede** hdbcli-Öffnungsstelle (Run, Dry-Run/Preview, Profiling/Validation, Test) streamt Progress über den **store-getriebenen** Kanal; SQLite **und** HANA-Store tauglich.
- Realer hdbcli-Pfad reproduzierbar nachgewiesen (`make hana-smoke`, env-gated), Multi-Worker grün.
- `STORE_BACKEND=hana` lauffähig (E) oder bewusst als Folge-Batch markiert.
- Gates G1/G2/G4/G6/G7/G8 grün; OpenAPI-Typen regeneriert.

## Bewusst NICHT in diesem Plan
- UI-Editor zum Anlegen von Environments inkl. Secret-Eingabe (Anlage bleibt `environments.yml`/Secret-Store, D3).
- Vault-Resolver (Interface steht in `secrets.py`, Implementierung später).
- Connection-Pooling/Persistente Sessions (jede Operation öffnet/schließt; Pooling erst bei Lastbedarf).
- Object-Store-/HDLF-Executor (E2-Carve-out, B3 des Reviews bleibt).
