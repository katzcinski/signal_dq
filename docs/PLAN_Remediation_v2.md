# PLAN — Remediation & Ausbau v2 · DQ & Observability Cockpit

> **Nachtrag 2026-06-22:** Dieser Plan (R0–R6) ist umgesetzt und damit
> **historisch**. Die anschließende Feature-Arbeit (UI/UX-Ausbau UX-N1–N15 sowie
> der `kind`-Diskriminator, Batches 1–6 / ADR-0001/0002) liegt außerhalb der
> R-Sequenz. Der maßgebliche, aktuelle Stand steht in
> [`Tooldokumentation.md`](Tooldokumentation.md); offene Punkte in
> [`OPEN_TASKS.md`](OPEN_TASKS.md) und [`REVIEW_Tool_v2_Status.md`](REVIEW_Tool_v2_Status.md).

> **Status 2026-06-12:** R0–R6 implementiert.
> R0/R1 vollständig; R2 bis auf HANA-Store-Implementierung (O6, bewusst Stub);
> R3 inkl. Gating-Produktion, StatusGrid, ContractEditor-Neubau, Onboarding, URL-Sync, i18n der
> angefassten Screens; R4 Incidents/SLA/Coverage/Badge/Webhook-Kontext; R5 ODCS-3.1-Export
> (validiert gegen offizielles Bitol-Schema) + Advisory-CI; R6-Politur (Peek-Drilldown,
> Sparkline-Zellen, Skeletons, Toasts, Cmd-K, Virtualisierung, Density-Toggle,
> Lineage-Swimlanes) komplett. Volle i18n-Abdeckung der Restscreens (Proposals, Governance,
> Workbench-Reste) nachgezogen — kein Sprachmix mehr. F2-Kern (Run-Status +
> Progress store-getrieben, über Worker-Grenzen identisch) jetzt durch
> Integrationstest belegt (`tests/unit/test_multi_worker_f2.py`: zwei Store-
> Instanzen auf einer DB + realer SSE-Generator). **Offen:** Spaltenebene
> Lineage (O3, blockiert durch `columnEdges`-Parser-Defekt im Analyzer),
> optionaler Playwright-E2E-Smoke obendrauf (Browser-Ebene, kein
> Korrektheitsrisiko mehr).

**Stand:** 2026-06-10 · **Grundlage:** `REVIEW_Tool_v1_Befunde.md` (Befund-IDs S-x/L-x/FE-x werden referenziert) + Marktabgleich § 7.
**Modus:** sequentiell wie HANDOVER; jeder Schritt mit Acceptance, kein Merge bei rotem Gate. Boundary-Tags und Goldene Regeln des HANDOVER gelten unverändert weiter.

> **Leitidee:** Erst die Lüge aus dem System nehmen (Dinge, die fertig aussehen, aber nicht funktionieren), dann die Sicherheitslinie schließen, dann Workflow-Wahrheit herstellen, erst danach Produktreife und Markt-Table-Stakes. Kein neues Feature, solange R0/R1 offen sind.

## Übersicht & Sequenz

| WS | Inhalt | hängt ab von | Aufwand (PT) | Meilenstein |
|----|--------|--------------|--------------|-------------|
| R0 | Stop-the-line: Compiler-Neubau, Injection-Schließung, Crash-/Glob-Fixes, G4-Pipeline | — | 8–11 | **M-R0: M2-Pfad existiert wieder** |
| R1 | Security-Linie: OIDC, Authz flächendeckend, PII-Gate komplett, SSE-Ersatz, Bind, CSP | R0 | 7–10 | **M-R1: Kunden-Deployment vertretbar** |
| R2 | Workflow-Wahrheit: Git-Modell, Run↔Contract, Compliance-Events, Run-Registry, HANA-Pfad | R0 | 8–12 | — |
| R3 | Frontend-Konformität: G6-Pipeline, StatusGrid, ContractEditor, Onboarding, i18n, A11y | R0 (G4) | 10–14 | **M-R3: Konzept-UI eingelöst** |
| R4 | Table Stakes: Incidents, Notifications, SLA-über-Zeit, Coverage-Metriken, Badge | R2, R3 | 8–12 | — |
| R5 | Interop: ODCS-3.1-Export, CLI-Zweitmeinung, BDC/ORD-Alignment | R0 | 3–5 | — |
| R6 | UI-Modernisierung: Carbon-Encoding, Side-Panel, Sparkline-Zellen, Cmd-K, Density | R3 | 5–8 | **M-R6: v1-Demo-Reife** |

**Brutto ≈ 49–72 PT.** R1 und R2 sind nach R0 parallelisierbar (verschiedene Dateien); R5 jederzeit nach R0 einschiebbar (klein, hoher Demo-Wert).

---

## R0 — Stop-the-line (nichts anderes vorher)

**R0-1 Compiler-Neubau auf §1.5-Garantien-Format** `[DETERMINISM]` `[SCHEMA-MAP]` `[CONTRACT-SQL-FREE]` *(Befund § 1, S-3, S-4, L-1, L-2)*
`compiler.py` komplett gegen das interne Format schreiben; die ODCS-Lesart wird **gelöscht** (ODCS kommt als *Export* in R5 zurück, nie als zweites internes Schema):
- Input: validiertes Contract-Dict (§1.5). Je Garantie-Familie ein Mapping auf `check_library`-Template → `CheckDef`. **Kein `type: sql`-Pfad mehr — ersatzlos** (G1 absolut; der `owned_by: product`-Sonderfall war die Hintertür S-3).
- `_bind()` ersetzt durch dreistufige Identifier-Verteidigung (S2 wörtlich aus HANDOVER): (1) Regex `^[A-Za-z_][A-Za-z0-9_]*$` auf **jeden** Identifier (Spalten, Dataset, Parent, auch listen-wertige Garantien), (2) Existenzprüfung gegen Inventar-Snapshot, (3) Quote-Escaping (`"` → `""`) als Defense-in-depth. `<REGEX>`-Werte: Quoting für SQL-Literal (`'` → `''`) + Längen-/Komplexitätslimit (L-11 ReDoS).
- `{schema}`-Platzhalter bleibt **wörtlich im Output** (`FROM "{schema}"."<DATASET>"`); Bindung ausschließlich zur Laufzeit durch Engine/Runner. `schema_override` aus der Compile-API entfernen.
- Header im erzeugten `checks.yml`: `# contract_hash: …` `# library_version: …` `# compiler_hash: sha256(contract_hash + library_version)` — Hash *in der Datei*, nicht nur in der Response (L-1/A4).
- Merge existing-wins unverändert übernehmen, jetzt erreichbar.
*Acceptance:* `compile_contract(load("contracts/DS_SALES_ORDERS.yaml"))` liefert ≥6 Checks; Injection-Fixtures (`A" OR 1=1 --` in `keys[].columns`, `; DROP` in `<REGEX>`) ⇒ ValueError; zweimal kompilieren = byte-identisch **bei nicht-leerem Output** (Determinismus-Test bekommt eine `assert len(checks) > 0`-Wache — nie wieder vakuum); Output enthält literal `{schema}`.

**R0-2 Validator-Neubau: jsonschema + echte Lint-Stufe** *(S-4, S-5, L-9)*
- Formales jsonschema für §1.5 (Garantie-Familien, Severities, SemVer, Lifecycle-Enum, `additionalProperties: false`). Identifier-Regex als `pattern` auf **allen** Spalten-/Namensfeldern inkl. listen-wertiger Garantien.
- G1-Lint danach: Reject auf `sql:`-Key irgendwo + Quote-/Semikolon-/Kommentar-Muster in *Identifier-Feldern* (nicht in `description` — behebt den False-Positive, an dem der eigene Contract scheitert).
- `schema:`-Key im Contract wird **verboten** (A2); `max_age_hours` → ISO-8601 `max_age` normalisieren (eine Schreibweise, behebt L-3-Blindstelle); ausgelieferte `contracts/*.yaml` migrieren.
*Acceptance:* beide Repo-Contracts validieren grün; SQL-Schmuggel-Fixtures rot; `schema:`-Key rot.

**R0-3 Glob-/Naming-Vereinheitlichung** *(L-7, S-11)*
Eine Utility `contract_path(product)` mit Identifier-Regex-Prüfung auf `product`/`dataset` (auch als Pfad-Schutz), Endung kanonisch `.yaml`, alle Globs `*.y*ml`. Betrifft `checks.py:39`, `lineage.py:32`, `proposals.py:79`.
*Acceptance:* Dry-Run + Coverage-Join + Proposal-Accept funktionieren mit den ausgelieferten `.yaml`-Contracts; `product="../x"` und `product="X.active"` ⇒ 422.

**R0-4 CLI + Phantom-Importe reparieren** *(L-6)*
`dq_check_runner.py` auf reale API (`run_checks`, `ResultStore`) umstellen; Phantom-Importe in `checks.py` (DBConnection/CheckEngine) ersetzen; das tote `simple_yaml`-Fallback in `check_engine.py` entfernen. Bare `except:`-Maskierungen durch gezielte Exceptions ersetzen. Smoke-Test: CLI gegen SQLite + MockConnection läuft durch.

**R0-5 G4-Pipeline: openapi-typescript** *(FE-Drift-Trio)*
`openapi-typescript` als devDependency, `npm run gen:api` gegen `/api/openapi.json`, generierte `src/api/schema.d.ts` eingecheckt, CI-Step `gen + git diff --exit-code`. Handgeschriebene Typen in `src/types/index.ts` durch Importe ersetzen — das fixiert Incidents- (`id`/`expected`), Proposals- (`pending`→`open`) und RunState- (`failed`→`error`) Drift strukturell. Vorher BE aufräumen: **eine** Schema-Familie (die ungenutzte `schemas/{contracts,runs,objects}.py`-Schicht löschen), Incidents bekommen eine stabile `id`.
*Acceptance:* CI bricht bei absichtlicher BE-Schema-Änderung ohne FE-Regeneration.

**R0-6 FE-Sofortfixes** *(FE-Bugs 1, 4–7)*
Hooks-Crash (`useRun` über die frühen Returns heben); Polling-Fallback als Basis-Pfad (`refetchInterval` solange `run_state==='running'`); Cytoscape-Farben via `getComputedStyle` zu Hex auflösen; Positions-Cache nur Positionen, Key = Hash der Node-IDs; CSV-Export escapen (`"`-Verdopplung, `'`-Präfix für `=+-@`).

**R0-7 CI-Gates nachziehen** *(§ 4 des Reviews)*
- **G1-on-files:** CI-Job validiert `contracts/*.yaml` mit dem R0-2-Validator.
- **G3-on-PRs:** CI-Job, der bei PRs mit Contract-Änderungen `dq_core.contract.diff` gegen den Merge-Base laufen lässt; breaking ohne Major-Sprung ⇒ fail.
- **G4:** siehe R0-5. — **A6-Drift-Test:** Snapshot-Test Dataclass-Felder ↔ Pydantic-Felder (der in `schemas/__init__.py` behauptete Test wird real).
- Determinismus-Test mit Nicht-leer-Wache (R0-1).

*Meilenstein M-R0:* Roundtrip Contract→Compile→Dry-Run→Status läuft mit `DS_SALES_ORDERS.yaml` lokal durch; alle 8 Gates + A6 real in CI; Injection-Fixtures rot.

---

## R1 — Security-Linie

**R1-1 OIDC real** `[AUTHZ]` *(S-1)*
JWKS-basierte Validierung (python-jose/joserfc): Signatur, `iss`, `aud`, `exp/nbf`, Algorithmus-Pinning (`RS256`/`ES256`, **kein** `none`/HS-Downgrade), JWKS-Cache mit TTL + Kid-Rollover. Claims→Rollen-Mapping aus ENV (`OIDC_ROLE_CLAIM`, Mapping-Tabelle). `provider.py`-501 entfernen. Integrationstest mit selbst-signiertem Token-Fixture (gültig/abgelaufen/falsche aud/None-Alg ⇒ 401).

**R1-2 Authz flächendeckend + korrekt** `[AUTHZ]` *(S-2, S-6)*
- `can_write_contract` entscheidet anhand des **bestehenden** Contracts (Platte/Index), nicht des Bodys; bei Neuanlage anhand Default-Policy. PUT nur bei `lifecycle=draft`; `lifecycle` aus `ContractIn` entfernen (Lifecycle-Übergänge nur über approve/deprecate).
- Dependency `require_write(product)` auf: PUT, seed, compile, approve, deprecate, revert, proposals/accept|reject, objects/run (Letzteres `steward+`).
- `grp:`-ACLs: echtes Gruppen-Mapping aus OIDC-Claims (Platzhalter raus); bis dahin `grp:`-Einträge **fail-closed** (matchen niemanden) statt jeden.
*Acceptance:* Endpoint-Matrix-Test: jede mutierende Route × jede Rolle ⇒ erwartetes 200/403; Body-Manipulationstest aus S-2 ⇒ 403.

**R1-3 PII-Gate komplettieren** `[PII-GATE]` *(S-8)*
`CheckDef.diagnostics: {enabled: bool, columns: [..]}` (Engine-Dataclass-Erweiterung ist additiv, kein [ENGINE-FROZEN]-Bruch); Engine holt Diagnostik-Zeilen **nur wenn enabled** (Suppression an der Quelle, nicht erst am Store) und projiziert auf die Allowlist vor Rückgabe; SSE/Progress-Pfad transportiert nie Rohzeilen. TTL-Cleanup (`DIAGNOSTICS_TTL_DAYS`) beim Store-Open. `deps.py` reicht die Konfiguration durch.
*Acceptance:* G8-Test erweitert: enabled+Allowlist ⇒ nur erlaubte Spalten, im Store **und** im SSE-Event-Strom; TTL-Test löscht abgelaufene Zeilen.

**R1-4 SSE-Ersatz: Store-getriebenes Streaming** *(S-9)*
Globale Queue löschen. SSE-Generator pollt `dq_run_progress` (Cursor = letzte gesehene Zeilen-ID) mit kurzem Sleep async — damit identische Wahrheit für SSE und Polling, multi-worker-fest (F2/A5), kein Busy-Loop, kein Shared-State. Event-Shapes mit dem FE vertraglich fixieren (kommt via G4-OpenAPI-Beschreibung der Event-Typen): `progress | run_started | check_result | run_finished | run_error`.

**R1-5 Bind fail-closed real** *(S-7)*
Prüfung auf den tatsächlichen Socket statt String: Startup-Check normalisiert `BIND_HOST` (`ipaddress`-Modul: unspecified/any ⇒ abort bei noauth), und `make dev-backend` ruft uvicorn **mit** `--host $(BIND_HOST)` aus den Settings auf. Test: `AUTH_MODE=noauth` + `BIND_HOST=::` ⇒ Startabbruch.

**R1-6 Webhook verdrahten + härten** *(S-10, L-4-Haken)*
Aufruf beim Compliance-Übergang →`breached` (R2-3 liefert das Event); Härtung: Scheme-Allowlist `https`, DNS-Pinning (aufgelöste IP für die Connection verwenden — TOCTOU zu), Retry mit Backoff, Payload: product, contract_version, run_id, failed_checks.

**R1-7 FE-Security-Floor** *(FE-Tabelle § 2)*
Fonts self-hosten (`@fontsource/dm-sans`, `@fontsource/jetbrains-mono`); danach CSP (`default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'` minimieren) als Meta + Server-Header in FastAPI-Static-Serving; ESLint-Config real (`react/no-danger: error`, hooks-Regeln — hätte den R0-6-Crash gefangen) + CI-Step.

**R1-8 Fehlerformat & Fail-Closed-Verbindungen** *(S-13, S-14)*
RFC-7807-Handler für `HTTPException` **und** Catch-all (generische Message extern, Details ins Log); `MockConnection`-Fallback nur bei explizitem `ALLOW_MOCK_CONNECTION=true`, sonst harter Fehler; `secret_ref` in `environments.yml` (Auflösung über ENV/Datei, nie Klartext-Passwort im YAML).

*Meilenstein M-R1:* Pen-Test-Checkliste des Reviews (S-1…S-14) vollständig geschlossen oder bewusst akzeptiert; OIDC-Deployment mit 2 Workern im Integrationstest grün.

---

## R2 — Workflow-Wahrheit

**R2-1 Git-Schreibmodell nach WS2-3** *(S-12)*
Datei-basiertes Prozess-Lock (`fcntl`/lockfile) um die Commit-Sektion; Commits via `git -C … -c user.name=… -c user.email=…` (keine Shared-Config-Mutation); explizite Pfad-Staging (nie `index.commit()` mit Fremd-Staging); Breaking-Prüfung (derselbe `diff`-Code wie G3) **blockierend vor** jedem Commit; Push auf `GIT_REMOTE` mit Reject→409+Rebase-Hinweis; Fehler nie verschluckt (Approve schlägt sichtbar fehl, wenn der Commit fehlschlägt). `contract_index` nach Commit aktualisieren und `GET /api/contracts` **aus dem Index** bedienen (A3).
*Acceptance:* 2-Worker-Test: 20 parallele Approves ⇒ 20 saubere Einzelcommits, keine Fremddateien; simulierter Push-Reject ⇒ 409.

**R2-2 Run↔Contract-Verknüpfung (F3)** *(L-4)*
Beim Run-Start aktive Contract-Version+Hash des Datasets ermitteln und in `dq_runs.contract_version/contract_hash/actor` schreiben; `compute_compliance` wertet nur Runs der aktiven Version.

**R2-3 Compliance als Event-Log** *(L-4)*
Neue Tabelle `dq_compliance_events(product, from_state, to_state, run_id, at)` via Migration 003; `dq_compliance` wird zur materialisierten Sicht des letzten Events; `since` = Zeitstempel des letzten **Übergangs**. Übergang →`breached` feuert R1-6-Webhook und (R4-1) Incident-Erzeugung.

**R2-4 Run-Registry korrekt** *(L-5)*
Partieller Unique-Index `(dataset, environment) WHERE run_state='running'` (SQLite: `CREATE UNIQUE INDEX … WHERE`), Insert-or-fail statt check-then-act; Stale-Running-Reaper (Runs > Timeout ⇒ `error`). `POST /api/runs {dataset, environment, execution_mode}` wie WS1-2 spezifiziert (der Objekt-Shortcut bleibt als Convenience).

**R2-5 Echter Ausführungspfad** `[SCHEMA-MAP]` *(L-5, S-13)*
Run-Trigger nimmt `environment`; `get_environment()` liefert Host/Port/Schema/secret_ref; Engine bekommt die Schema-Bindung zur Laufzeit (hier wird `{schema}` aus R0-1 gebunden — der einzige Ort). MockConnection nur noch via Flag (R1-8).

**R2-6 Store-Vervollständigung** *(L-8, L-10)*
`HanaStore`-Methoden auf `ResultStoreProtocol` umbenennen + Protocol-Konformitätstest (instanziieren, `isinstance`-Check via `runtime_checkable`); `get_store()` respektiert `STORE_BACKEND` (hana ⇒ NotImplementedError mit klarer Meldung statt stillem SQLite); Migrations-Runner: Statement-Splitting durch sqlparse oder `--`-Marker ersetzen. Endpunkt `GET /api/objects/{name}/checks/{c}/history` (Sparkline-Quelle) + `GET /api/runs/{id}/results|/diagnostics` + Pagination (`limit/offset`, Default 50, Max 500) auf allen Listen.

**R2-7 Seed korrekt** *(L-9)*
`_key_gap` raus; Seed erzeugt echte `keys:`-Garantie aus deklarierten Keys, und wo keine existieren, den konkreten Pflichtvorschlag (Heuristik: ID-Spalten-Kandidaten aus Inventar, für `Sales_Orders_View` deterministisch `[OrderID, ItemNo]`) mit `severity: critical` und Kommentar-Flag `proposed: true`; kein `schema:` im Output (R0-2 verbietet es).

**R2-8 Proposals persistent** *(API § 4)*
Miner schreibt in die existierende `dq_proposals`-Tabelle; `GET /api/proposals?status=`; accept ⇒ Draft-Amendment über den normalen PUT/Approve-Weg (mit R1-2-Authz), reject/snooze persistieren Status statt Fake-Response. `baselines.py` an den Run-Abschluss anbinden (Warm-up-Zähler dekrementieren, Bounds aktualisieren) — sonst bleibt WS5-1 toter Code.

---

## R3 — Frontend-Konformität (Konzept einlösen)

**R3-1 G6-Pipeline end-to-end** *(FE 1.1; Backend-Hälfte: Gating)*
- Engine/Runner: Gating-Logik produziert real `skipped_stale` (Staleness aus Extrakt-Alter/Freshness-Check) und `skipped_dependency` (günstige Checks gaten teure — Konzept § 2); bis dahin mindestens: `state` wird durch alle Schichten gereicht.
- FE: `StatePill` (neutral grau, gestrichelte Border, Glyph + Label aus `de.ts`, Tooltip mit Grund) rendert **immer wenn `state !== 'executed'`** — vor jeder Status-Ableitung aus `passed`. Einsatzorte: ObjectDetail-CheckTable, RunDetail, Dry-Run-Panel, Incidents.
- Vitest-Test analog `CovFlag.test.tsx`: `skipped_stale`-Fixture darf weder Pass- noch Fail-Styling tragen (G6 als FE-Test).

**R3-2 StatusGrid = Objekt × Familie** *(FE 1.3)*
Datenmodell-Fix zuerst: `family` ist Attribut von **Checks**, nicht Objekten; `GET /api/objects` liefert je Objekt eine Familien-Status-Map (`{observability: …, quality: …}`). Grid-Zeile = Objekt, Spalten = Familien, Zelle = StatusPill + Mini-Sparkline; Zellklick → Side-Panel (R6-2), Objektklick → Detailseite. Filter Space/Layer/Severity/Familie URL-synchron (R3-6).

**R3-3 ContractEditor-Neubau (U2)** *(FE 1.2)*
Linke Liste = **Contracts** aus `GET /api/contracts` (lifecycle/owner-Spalten); Editor = Karten je Garantie-Familie (Toggle + Severity-Select + warn→block-Schalter), Felder als Combobox gegen `GET /api/inventory` (kein Freitext für Spalten/Parents); rechts read-only YAML-Vorschau (CodeMirror) + **BreakingDiffPanel** (ruft den existierenden `POST /diff` vor Enable des Approve-Buttons — Grafana-Prinzip: Friction ∝ Risiko); ApprovalBar als sichtbare Statusmaschine (draft→review→active mit Begründung). **Lite-Modus**: gleiche Karten, reduziert auf An/Aus+Severity, ohne Versions-/Approval-Pflicht. Client-seitige G1-Regex löschen (Server ist autoritativ).

**R3-4 Onboarding & Empty States (U4)** *(FE 1.4)*
`/` bei leerem Tenant: 4-Schritte-Stepper (Extract → Seed → Dry-Run → erstes Ergebnis) mit Live-Buttons auf die existierenden Endpunkte; jede Liste bekommt NN/g-konforme Empty States (Status + Erklärung + nächste Aktion — bei Objekten ohne Garantien: Miner-Vorschläge anbieten). Fehler ≠ leer: `isError` ⇒ Banner + Retry, **nie** „all checks passing" bei API-Ausfall.

**R3-5 LiveRunPanel + Run-UX** *(FE 1.5)*
RunTriggerDialog (Dataset+Environment+Modus, gegen R2-4-Endpunkt); LiveRunPanel als persistente Bottom-Bar, gespeist aus `sseStore` (endlich konsumiert) mit Polling-Basis (R0-6); ActualValueSparkline gegen R2-6-History-Endpunkt; DiagnosticsDrawer (nur wenn aktiviert, R1-3); Extrakt-Alter + Staleness-Warnung, sobald `GET /api/lineage` `extract_age` liefert (BE-Feld ergänzen — FE wartet schon darauf).

**R3-6 Querschnitte** *(FE § 2)*
`useSearchParamState`-Hook → alle Filter URL-synchron (macht auch den `/contracts?compile=`-Deep-Link aus der Map funktionsfähig); i18n real: alle Strings nach `de.ts`, toten `Nav.tsx` löschen, Sprachmix beseitigen; Status-Vokabular harmonisieren (`error` statt `unknown`, `failed`→`error`, Map-Badges einheitlich `✓/◐/⚠/○`, Route `/coverage`); Token-Konsolidierung: Tailwind-Palette auf CSS-Vars mappen (eine Quelle), Inline-Style-Doubletten in Komponenten ziehen; U1-Lecks fixen (Proposals: `--status-ok` statt Familien-Grün; Stepper/ConfidenceBar: neutrale Skala).

**R3-7 A11y-Floor** *(FE § 5, Carbon-Regel)*
Status-Encoding ≥3-von-4 (Farbe + Form/Glyph + Text): StatusDot bekommt Form-Varianten (●▲◆) + `aria-label`; klickbare `div`s → `<button>`/`<Link>` mit `:focus-visible`; CommandPalette: Pfeiltasten/Enter, `role="dialog"`, Fokus-Falle (oder `cmdk` adoptieren); Kontrast-Pass über Pills (WCAG ≥4.5:1); `prefers-reduced-motion`; Responsive-Guards via `matchMedia`-Hook (LineageMap, ContractWorkbench mit Desktop-Hinweis nach U3).

---

## R4 — Markt-Table-Stakes (Review § 7.2)

**R4-1 Incident-Lifecycle**
Migration 004: `dq_incidents(id, product, run_id, check_name, severity, status: open|acknowledged|investigating|resolved, owner, opened_at, resolved_at)` + `dq_incident_events` (Timeline: wer, was, wann — ISO-8601). Erzeugung beim Compliance-Übergang →breached (ein Incident je product+breach-Episode, nicht je Check-Fail — Sifflet-Gruppierungs-Lektion). API: list/get/transition/assign; FE: Incidents-Seite wird Inbox (Severity-sortiert, Status-Filter, Detail-Drawer mit Timeline, Acknowledge/Assign/Resolve-Aktionen, „Root-Cause in Lineage"-Link mit Upstream-Highlight).

**R4-2 Notification-Routing**
Webhook (R1-6) erweitert um Kanal-Konfiguration je Contract (`owners` → Routing); Slack/Teams-kompatible Payload (Blocks/AdaptiveCard) mit Status, Trend-Kontext und Deep-Link; Digest-Option (täglich) vs. sofort je Severity.

**R4-3 SLA-Compliance über Zeit**
Store-Query über `dq_compliance_events`: %-compliant je Contract über 7/30/90-Tage-Fenster; `GET /api/contracts/{p}/sla`; FE: Uptime-Balken (Status-Page-Pattern) im ContractDetail und als Spalte in der Contract-Liste.

**R4-4 Coverage-Metriken**
`GET /api/coverage/summary`: % Objekte mit aktivem Contract, % Spalten mit Garantien, Objekte ohne Lauf >30 Tage (GX-Vorbild). FE: KPI-Reihe auf `/coverage` über der Map; ⚠-Liste „unvalidiert" mit Workbench-Link.

**R4-5 Status-Badge/Tile**
`GET /api/badge/{product}` (SVG + JSON, read-only, optional token-geschützt) für Einbettung in SAC/Confluence — dbt-Health-Tile-Analogon mit minimalem Aufwand.

---

## R5 — Interop & BDC (klein, hoher strategischer Wert)

**R5-1 ODCS-3.1-Export**
`dq_core/contract/odcs_export.py`: deterministisches Mapping §1.5 → ODCS 3.1 (schema→properties mit `required`/`unique`/`primaryKey`, keys/referential→constraints+relationships, freshness/volume→`slaProperties`+library-Checks, completeness→nullCount; Rest→`customProperties`; lifecycle→`status`). `GET /api/contracts/{p}/export/odcs`. **Compliance bleibt draußen** (A1-konform, ODCS-konform).
*Acceptance:* Export validiert gegen das offizielle ODCS-3.1-JSON-Schema (Fixture im Repo).

**R5-2 CI-Zweitmeinung Breaking-Diff**
Optionaler CI-Job: `datacontract breaking <base-export> <head-export>` auf Contract-PRs neben G3 — Diskrepanzen zwischen homegrown diff.py und CLI als Report (erfüllt O1/Stufe 2 ohne diff.py zu ersetzen). Vorher L-3 schließen: Type-Narrowing (sobald Schema-Garantie Typen trägt — jsonschema aus R0-2 erweitern), `mode: closed`+Spalte, Severity-Eskalation.

**R5-3 BDC-Export-Alignment (WS5-4)**
CSN-Interop- + ORD-Fragment-Generierung gegen die aktuellen Spezifikationen (csn-interop-specification, ORD-Spec) prüfen; Compliance-Status als ORD-`labels`/Custom-Taxonomie; Roadmap-Notiz: `sap-bdc-connect-sdk`-Publishing, sobald Kundenfall da (einseitig, E1 bleibt).

---

## R6 — UI-Modernisierung (nach R3, Demo-Politur)

1. **Side-Panel-Drilldown** (Polaris-Muster): Grid-Zelle/Tabellenzeile → Peek-Panel mit Check-Historie + Aktionen; Full-Page nur Objekt/Contract/Run.
2. **Sparkline-Zellen**: Wert + Delta + 14-Punkte-Sparkline, konsistente Achsen je Spalte (StatusGrid, Contract-SLA-Spalte).
3. **Skeleton-Loader** statt „Loading…" (KPI-Tiles, Tabellenzeilen aus ColDef-Breiten, Map-Canvas).
4. **Toasts + optimistische Updates** (Proposal-Aktionen, Contract-Save mit Rollback).
5. **Cmd-K-Ausbau**: Aktionen („Run checks on …", „Open contract …"), Recents, `cmdk`-Basis.
6. **Virtualisierte Tabelle** (`@tanstack/react-virtual` im generischen `Table`) + Spaltensortierung — Ziel >500 Objekte.
7. **Density-Toggle** (compact/comfortable) auf Token-Basis.
8. **Lineage-Map**: Layer-Swimlanes, Root-Cause-Modus (`predecessors()` highlighten), Legende, Form-Redundanz der Coverage-Badges (Carbon).
9. ~~Horizon-Anmutung~~ — **Entscheidung 2026-06-10: kein Fiori-Alignment.** Die UI bleibt bei der eigenen modernen Dark-Token-Palette (Linear/Grafana-Richtung); konsolidiert wird nur die Doppelung Tailwind-Palette ↔ CSS-Vars (eine Quelle). WCAG-Kontrast und Carbon-Redundanz-Regel (Punkt 8) gelten unabhängig davon.

---

## Teststrategie-Erweiterung

- **Injection-Fixture-Suite** (R0): YAML-Fixtures mit allen bekannten Schmuggel-Vektoren (listen-wertige Spalten, REGEX, product-Namen) — läuft als Teil von G1.
- **Authz-Matrix-Test** (R1): parametrisiert Route × Rolle.
- **Multi-Worker-Integrationstest** (R1/R2): 2 uvicorn-Worker, paralleler Run-Trigger + Approve (F2-Acceptance des HANDOVER endlich real).
- **G6-FE-Test** (R3-1) + Playwright-Smoke für M-R0-Roundtrip und Onboarding-Flow.
- **ODCS-Schema-Validierung** (R5-1) als Unit-Test.

## Definition of Done (Remediation)

- Alle Review-Befunde S-1…S-14, L-1…L-11, FE-CRITICAL/HIGH geschlossen oder mit begründetem Accept im Review-Doc vermerkt.
- HANDOVER-DoD wieder in Kraft: M2-Roundtrip mit `Sales_Orders_View`-Pflichtfall (⚠ → Garantie → Compile → Run → ✓) demonstrierbar, **diesmal mit nicht-leerem Compiler-Output**.
- CI: G1–G8 + A6 + ESLint + G6-FE-Test grün; Determinismus-Test mit Nicht-leer-Wache.
- Kein toter Code mehr aus der Phantom-Schicht (CLI, zweite Schema-Familie, `Nav.tsx`, ungenutzte Tabellen sind angebunden oder gelöscht).
