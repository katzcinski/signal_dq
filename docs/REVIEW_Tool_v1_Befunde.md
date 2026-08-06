# REVIEW — DQ & Observability Cockpit · Kritischer Tool-Review v1

**Stand:** 2026-06-10 · **Scope:** Gesamtes Repo (Backend `packages/dq_core` + `services/api`, Frontend `apps/cockpit`, CLI, CI, Contracts) geprüft gegen `HANDOVER.md`, `Konzept_DQ_Cockpit_UIUX.md`, `Konzept_DQ_Observability_Cockpit.md`, `REVIEW_Implementierungsplan.md` sowie gegen den Marktstand 2025/2026 (Standards, Tools, UI/UX — Quellen in § 7).
**Methodik:** Vollständige Code-Lektüre, empirische Verifikation der kritischen Befunde (Compiler-Crash, Injection-Strings, Validator-Bypass reproduziert), Testlauf (`python -m pytest tests/` → **93 passed**), CI-Workflow-Abgleich.

> **Gesamturteil:** Das Fundament (Engine, Expectation-Grammatik, SQLite-Store, Migrations, G7-Gate) ist solide und getestet. Darüber liegt jedoch eine Schicht, die *fertig aussieht, aber nicht funktioniert*: Der Compiler spricht ein anderes Contract-Format als der Rest des Systems — damit existiert der M2-Kernpfad (Contract → Compile → Run → Status) **nicht**. Drei der acht CI-Gates sind nicht implementiert, zwei nur dem Buchstaben nach. Die grüne Testsuite täuscht: Flaggschiff-Tests (Determinismus) sind vakuum (vergleichen zwei leere Outputs). Im Frontend sind G6 (Gating sichtbar), U2 (Picker statt Freitext), U4 (Onboarding) und U5 (i18n) verletzt; es gibt einen garantierten React-Crash und drei FE/BE-Typ-Drift-Bugs, deren Ursache das fehlende G4 (openapi-typescript) ist.

---

## 1 / Leitbefund: Zwei inkompatible Contract-Schemata

`validator.py`, `diff.py`, `seed.py`, alle API-Router und die ausgelieferten `contracts/*.yaml` verwenden das HANDOVER-§1.5-Format (`guarantees:`-Block). **`compiler.py` ist gegen ODCS v3 geschrieben** (`servers[]`, `schema: [{properties: …}]`, `slaProperties`). Empirisch verifiziert:

- `compile_contract(load("contracts/DS_SALES_ORDERS.yaml"))` → `AttributeError` (compiler.py:217 indiziert `odcs["schema"][0]`, der Contract hat `schema: CORE_DWH` als String) ⇒ `POST /api/contracts/{p}/compile` und `/api/checks/{ds}/dry-run` liefern **500 für jeden ausgelieferten Contract**.
- Für §1.5-Contracts ohne `schema:`-Key liefert der Compiler stillschweigend `dataset=''`, **0 Checks** — `guarantees:` wird nie gelesen.

**Konsequenz:** M2-Acceptance (Sales_Orders_View-Pflichtfall ⚠→✓) ist unerreichbar. Alles stromabwärts des Compilers (Existing-wins-Merge, Revert, CompilePreview im FE) ist Dekoration. Pikant: ODCS ist zwar die *richtige* Interop-Richtung (§ 7.1), aber als **Export-Format**, nicht als heimliches zweites internes Schema.

---

## 2 / Security-Befunde (Backend)

| # | Sev | Befund | Beleg |
|---|-----|--------|-------|
| S-1 | **CRITICAL** | **JWT-Validierung deaktiviert:** `jwt.decode(..., options={"verify_signature": False})` — keine Signatur-, Issuer-, Audience-, Algorithmus-Prüfung. Aktuell nur deshalb kein Live-Bypass, weil `provider.py:61` für `oidc` 501 wirft — d. h. der einzige funktionierende Auth-Modus ist NoAuth-Admin; das Kunden-Deployment (OIDC, ≥2 Worker) existiert nicht. | `services/api/auth/oidc.py:18-22` |
| S-2 | **CRITICAL** | **PUT-Authz entscheidet anhand des Angreifer-Bodys:** `can_write_contract(data.get("owned_by"), data.get("owners"))` prüft den *Request-Body*, nicht den bestehenden Contract auf Platte. Jeder Principal kann jeden Contract überschreiben (inkl. `lifecycle: active` direkt im Body — Approve-/Diff-Gate komplett umgangen). „PUT nur bei lifecycle=draft" wird ignoriert. | `services/api/routers/contracts.py:119` |
| S-3 | **CRITICAL** | **Roh-SQL-Hintertür im Compiler (G1-Bruch):** `type: sql`-Regeln werden bei `owned_by: product` wörtlich zu `CheckDef(sql=rule["query"])`. Verifiziert: `SELECT 1 FROM users; DROP TABLE x` wird emittiert. Compile/Dry-Run laden Contracts **ohne Re-Validierung** von Platte (contracts.py:306-312, checks.py:39-60) — der Git-/Seed-Pfad schleust SQL an G1 vorbei zur Engine. `[CONTRACT-SQL-FREE]` greift nur auf einem von drei Ingestion-Pfaden. | `packages/dq_core/contract/compiler.py:185-189` |
| S-4 | **CRITICAL** | **Identifier-Injection — S2 im Compiler nicht implementiert:** `_bind()` macht naives `str.replace()` ohne Regex-Check, ohne Inventar-Existenzprüfung, ohne Quote-Escaping (alle drei HANDOVER-Verteidigungslinien fehlen). Verifizierter Output: `SELECT COUNT(*) FROM "S"."T" ; --" WHERE "A" OR 1=1 --" IS NULL`. Der Validator prüft Spaltennamen nur bei **dict-wertigen** Garantien — `keys`, `completeness`, `referential` (listen-wertig) werden **gar nicht** geprüft: Spaltenname `A" OR 1=1 --` passiert `validate_contract` mit null Fehlern. Auch `<REGEX>` wird unescaped in ein SQL-Literal interpoliert. | `compiler.py:76-87`, `validator.py:67-77` |
| S-5 | HIGH | **G1-Validator ist eine schwache Keyword-Denylist:** `UNION`, `MERGE`, `EXEC`, `;`, Kommentar-Token fehlen; gleichzeitig False-Positive auf Prosa — der **eigene** `DS_SALES_ORDERS.yaml` fällt durch (`"harmonised from RAW_SALES"` matcht `\bFROM\b\s+\w`). Keine jsonschema-Validierung (WS2-1 fordert sie); unbekannte Garantie-Typen/Severities passieren frei. | `validator.py:8-16` |
| S-6 | HIGH | **Mutierende Endpunkte ohne `can_write_contract`:** `seed` (überschreibt beliebige Contracts), `compile` (ohne `lifecycle=active`-Vorbedingung), `proposals/accept` (**jeder Viewer kann aktive Contracts auf `draft` degradieren**, proposals.py:99), `checks/revert`, `objects/run`. Zudem `provider.py:33-36`: `grp:`-Owner-Einträge matcht ein Platzhalter, der *jeden* Steward/Owner akzeptiert — Gruppen-ACLs (S3) sind dekorativ. | `contracts.py:139,290`, `proposals.py:48-113`, `checks.py:138-195` |
| S-7 | HIGH | **S5-Fail-Closed-Bind ist kosmetisch:** nur Literal-Match `"0.0.0.0"`; `::`, `0:0:0:0:0:0:0:0`, und der Realfall `uvicorn --host 0.0.0.0` (das eigene `make dev-backend` umgeht `BIND_HOST` vollständig) exponieren den Admin-Principal ins Netz. Geprüft wird eine Einstellung, nicht der tatsächliche Bind. | `services/api/main.py:25`, `Makefile` |
| S-8 | HIGH | **PII-Gate (S1) halb gebaut:** Per-Check-`diagnostics: {enabled, columns[]}` existiert nicht (`CheckDef` hat kein Feld); Allowlist ist ein globales Konstruktor-Arg, das `deps.py:25-28` nicht einmal übergibt → mit `ALLOW_LOCAL_DIAGNOSTICS=true` werden **alle Spalten aller Checks** ungefiltert persistiert. `DIAGNOSTICS_TTL_DAYS` wird nirgends gelesen (keine Retention). Engine holt weiter eifrig bis 100 Rohzeilen je Fail (check_engine.py:257-290) — PII transitiert Prozessspeicher und SSE-Pfad; nur der finale Store-Write ist gegated. Was existiert (Store-seitig default-off + Allowlist), ist korrekt getestet. | `engine/models.py:11-22`, `deps.py:25-28` |
| S-9 | HIGH | **SSE: globale Shared-Queue mit Busy-Loop:** ein `SimpleQueue` für alle Consumer; ein Subscriber, der ein fremdes `run_id`-Event zurücklegt, re-`get`t es sofort — CPU-Spin, klaut Events nondeterministisch, belegt Threadpool (sync-Generator). DoS-fähig bei jeder Parallelnutzung; bei ≥2 Workern (Modul-Level-Queue) konstruktiv kaputt (F2/A5 verletzt). | `services/api/sse.py:22-28` |
| S-10 | MED | **Webhook (S6): gute Funktion, nie aufgerufen.** `fire_webhook_async` hat null Call-Sites; der Breach-Übergang (objects.py:234-243) feuert nie. Im toten Code zusätzlich: DNS-Auflösung für den Private-IP-Check getrennt von der Connection → TOCTOU/DNS-Rebinding; `http:` nicht verboten. | `services/api/webhook.py` |
| S-11 | MED | **`product`/`dataset` als Pfad-/Identifier ungeprüft:** Dateipfade aus Pfadparametern ohne `^[A-Za-z_][A-Za-z0-9_]*$`; Kollision mit der `.active.yml`-Konvention möglich (`X.active`). | `contracts.py:24-35`, `checks.py:145` |
| S-12 | MED | **git_repo.py ist nicht das WS2-3-Schreibmodell:** Thread-Lock statt Prozess-Lock (nutzlos bei ≥2 Workern); mutiert die geteilte Repo-Config je Request; `index.commit()` committet mitgestagtes Fremdmaterial; kein Push, kein 409-Rebase-Pfad; Breaking-Check vor Commit fehlt (der Kommentar dazu steht vor einem sha256-Aufruf); Commit in `approve` ist `try/except: pass`-verschluckt — „genau ein Commit je Approve" ist Fiktion. `contract_index` wird geschrieben, aber nie gelesen (`GET /api/contracts` scannt den Working Tree — exakt was A3 verbietet). | `services/api/git_repo.py:30-58`, `contracts.py:244-254` |
| S-13 | MED | **Secrets im Klartext + Fail-Open:** `user`/`password` direkt aus `environments.yml` (WS0-7 fordert `secret_ref`); `get_connection` fällt bei ImportError stumm auf `MockConnection` zurück — Prod-Fehlkonfiguration ⇒ fake-grüne Checks. TLS-Defaults selbst sind gut (encrypt + validate cert). | `checks.py:72-78`, `connect/db_connection.py:62-63` |
| S-14 | LOW | **RFC-7807 nur im ungünstigsten Fall:** Catch-all gibt `str(exc)` (Interna-Leak) ohne `application/problem+json`; `HTTPException`s (Mehrheit) liefern plain `{"detail"}`. | `main.py:48-58` |

### Security-Befunde (Frontend)

| Sev | Befund | Beleg |
|-----|--------|-------|
| HIGH | **Keine CSP** — weder Meta-Tag noch Server-Header (WS0-8/S8). Fonts von `fonts.googleapis.com` (Third-Party-Laufzeitabhängigkeit, DSGVO-relevant für SAP-Kunden, blockiert jede strikte CSP). | `index.html:7-12` |
| MED | **ESLint existiert nicht** — keine Config im Repo; `npm run lint` kann nicht laufen; das S8-Lint-Verbot von `dangerouslySetInnerHTML` ist fiktiv (Code selbst derzeit sauber). | `apps/cockpit/` |
| MED | **CSV-Formula-Injection im Export:** naive String-Konkatenation; `"` bricht die Datei, `=`,`+`,`-`,`@`-Präfixe werden in Excel als Formeln ausgeführt. | `RunDetail.tsx:28-38` |

---

## 3 / Logik-Befunde

| # | Sev | Befund | Beleg |
|---|-----|--------|-------|
| L-1 | **CRITICAL** | **Determinismus-Test vakuum:** Der Test PUTtet einen §1.5-Contract; der ODCS-Compiler ignoriert `guarantees` und kompiliert **0 Checks** — verglichen werden zwei identische leere YAMLs. Der Hash (Library-Version korrekt eingefaltet) steht nur in der JSON-Response, **nie im `checks.yml`-Header** → A4-Rückverfolgbarkeit unmöglich. | `tests/api/test_compiler_determinism.py`, `contracts.py:314-319` |
| L-2 | HIGH | **G2 funktional verletzt:** `replace("{schema}", schema)` mit `schema_override=""` ⇒ Output `FROM ""."TABLE"` — der Platzhalter, von dem Laufzeitbindung (A2) lebt, wird zerstört statt erhalten. Gleichzeitig hartkodieren die ausgelieferten Contracts `schema: CORE_DWH`/`ANALYTICS` (A2: „Contracts bleiben environment-frei"). Das CI-Grep auf `CENTRAL` passiert — Buchstabe erfüllt, Geist verletzt. | `compiler.py:80`, `contracts/*.yaml` |
| L-3 | HIGH | **diff.py verfehlt geforderte Breaking-Klassen:** kein Type-Narrowing (explizit gefordert); Freshness parst nur ISO-8601 `max_age`, die Contracts nutzen `max_age_hours: 26` → Verschärfung unsichtbar; `mode: closed`+neue Spalte, Severity-Eskalation, entfernte Completeness: unklassifiziert. (Key-Change und `min_pct`-Anhebung: korrekt.) | `diff.py:115-127` |
| L-4 | HIGH | **Compliance halb korrekt:** Regel v1 stimmt und ist getestet, aber `set_compliance` ist `INSERT OR REPLACE`, das `since` bei **jedem** Lauf neu schreibt — „Übergänge als Events" (WS2-5) nicht erfüllt, keine Historie, kein Breach→Webhook-Haken. `contract_version` am Run ist **immer leer** (F3-Spalten existieren, werden nie befüllt) → Compliance je Version unbeweisbar. | `sqlite_store.py:150-158`, `objects.py:241` |
| L-5 | HIGH | **Run-Registry: Race + Mock-Execution:** Check-then-act nur auf `runs[0]`; zwei parallele POSTs starten beide. Der Run nutzt **unconditionally `MockConnection()`** — die API kann nie gegen HANA prüfen; `environment`/`execution_mode` (WS1-2) existieren nicht. | `objects.py:183-185, 220` |
| L-6 | HIGH | **CLI tot:** importiert `CheckEngine`/`SQLiteStore` — beide Klassen existieren nicht (real: `run_checks()`/`ResultStore`). Jeder Aufruf crasht mit ImportError. Dieselben Phantom-Importe in `checks.py:65,98` — der Dry-Run-„executed"-Zweig kann nie laufen (maskiert durch bare `except`). Kein Test deckt es. | `cli/dq_check_runner.py:23,41,49` |
| L-7 | HIGH | **`.yml`-vs-`.yaml`-Globs nullen Features stumm aus:** Contracts sind `.yaml`; `checks.py:39` globbt `*.yml` → Dry-Run 404 für jeden realen Contract; `lineage.py:32` → Coverage-Join findet keine Contracts, **jede Node rendert als Lücke ▲**; `proposals.py:79` → Accept 404. | div. |
| L-8 | MED | **HANA-Store: Stub mit falschen Methodennamen** (`get_run_detail` vs. Protocol `get_run` usw.) — könnte das Protocol selbst implementiert nie erfüllen; `STORE_BACKEND=hana` wird akzeptiert, `get_store()` baut bedingungslos SQLite. Migration-Runner für SQLite ist solide (idempotent, getestet); HANA-Dialektvariante fehlt; naives `split(";")` bricht bei künftigen Trigger-/String-Literal-Migrationen. | `hana_store.py`, `deps.py:21-29` |
| L-9 | MED | **Seed verfehlt den einzigen Pflichtfall:** statt konkretem Key-Vorschlag (`OrderID,ItemNo`) ein schema-fremdes `_key_gap`-Pseudofeld mit Freitext, das Validator nicht kennt und Compiler ignoriert. Seed schreibt zudem `schema:` in den Contract (A2-Bruch) und erzeugt damit exakt die String-Form, an der der Compiler crasht (§ 1). | `seed.py:33-37,53` |
| L-10 | MED | **Sparkline-Daten unerreichbar:** `get_check_history` existiert im Store, aber `GET /api/objects/{name}/checks/{c}/history` (WS1-2) fehlt. Polling-Pfad selbst ist solide (Progress persistiert, lesbar). | `runs.py` |
| L-11 | LOW | Engine-Details: `± `-Form verlangt entgegen eigener Fehlermeldung ASCII `+/-`; `MATCHES` führt Nutzer-Regex aus (ReDoS); `check_engine.py:12-16` importiert ein nirgends existierendes `simple_yaml`-Fallback-Modul. | `expectation.py:25` |

---

## 4 / CI-Gates: Soll vs. Ist

| Gate | Soll | Ist | Urteil |
|------|------|-----|--------|
| G1 | jsonschema + Lint auf `contracts/*.yml` in CI | nur Unit-Tests der Funktion; **Contract-Dateien werden in CI nie gelintet** — Beweis: der eigene `DS_SALES_ORDERS.yaml` fällt unbemerkt durch seinen eigenen Validator | **FAIL** |
| G2 | kein hartkodiertes Schema | Grep vorhanden; verfehlt die Platzhalter-Zerstörung (L-2) und die `schema:`-Keys in den Contracts | partial |
| G3 | Breaking⇒Major als CI-Gate auf Contract-PRs | nur serverseitig in `approve`; **kein CI-Job difft Contract-PRs** | **FAIL** |
| G4 | openapi-typescript + `git diff --exit-code` | nur `tsc --noEmit`; keine Generierung — Folge: drei gelieferte Drift-Bugs (§ 5) | **FAIL** |
| G5 | Engine-Suite grün | läuft | pass |
| G6 | `skipped_stale` nie still | CI-Grep + Verhaltentests existieren; aber nichts in der Engine **produziert** je `skipped_stale` (keine Gating-Logik), und das FE rendert `state` nirgends (§ 5) | partial |
| G7 | Framework-Isolation | AST-basierter Check — das beste Gate der acht | pass |
| G8 | PII-Verhaltenstest | Verhaltentests vorhanden und laufen | pass (de facto) |

Zusätzlich fehlt der in `schemas/__init__.py:1` *behauptete* A6-Drift-Test (Dataclass↔Pydantic) vollständig. Es existieren **zwei parallel driftende Schema-Familien** (`schemas/{contracts,runs,objects}.py` ungenutzt neben `schemas/*_schemas.py`).

---

## 5 / Frontend-Befunde (UI/UX/Workflow)

### Hard-Fails gegen die eigenen Regeln

| Regel | Urteil | Beleg |
|-------|--------|-------|
| **G6** (skipped ≠ pass) | **FAIL** — `StatusPill status={c.passed ? 'pass' : c.severity}`; das Feld `state` wird nie konsultiert. Ein `skipped_stale` rendert als rotes *fail* (oder grünes *pass*). `skipped_dependency`/`downgraded` kommen im FE **nirgends** vor. Das i18n-Label existiert, ist aber verwaist. | `ObjectDetail.tsx:52`, `RunDetail.tsx:21`, `ContractWorkbench.tsx:187` |
| **U2** (Picker, kein Freitext) | **FAIL** — ContractEditor ist ein **rohes JSON-Textarea**; kein Formular je Garantie-Familie, kein Inventar-Autocomplete (`GET /api/inventory` wird nie aufgerufen), keine read-only YAML-Vorschau. Lite-Modus (N1/D8): fehlt komplett. | `ContractWorkbench.tsx:308-318` |
| **U4** (Onboarding) | **FAIL** — kein Extract→Seed→Dry-Run→Ergebnis-Wizard; leerer Tenant zeigt „No observability objects" ohne Call-to-Action; `/api/extract` und `/seed` FE-seitig ungenutzt. | `Cockpit.tsx:45` |
| **U5** (i18n zentral) | **FAIL** — `de.ts` wird nur vom **toten** `Nav.tsx` importiert; alle Live-Screens hartkodieren Englisch, mit deutschen Fragmenten gemischt („Contract öffnen →" neben „Search objects…"). | `Sidebar.tsx:4-11`, `LineageMap.tsx:78` |
| **U1** (Statusfarben exklusiv) | mostly pass, mit Lecks: `Proposals` nutzt Familien-Grün als „gut/accept"; `LifecycleStepper`/`ConfidenceBar` nutzen Status-Ampel für Nicht-Status; `StatusDot` ist farb-einzig ohne Label. | `Proposals.tsx:50,81`, `LifecycleStepper.tsx:20,28` |
| **U3** (responsive) | partial — nur LineageMap guarded Desktop, via einmaligem `window.innerWidth` ohne Listener; ContractWorkbench (Editor!) hat keinen Desktop-Hinweis. | `LineageMap.tsx:102` |
| **S8** (CSP/Lint) | FAIL (siehe § 2 FE-Tabelle) | |

### Bugs

1. **CRITICAL — Rules-of-Hooks-Crash:** frühe `return`s vor `useRun(...)` — der Loading→Loaded-Übergang ändert die Hook-Anzahl, React wirft. Die Objektdetail-Seite crasht im Normalbetrieb. `ObjectDetail.tsx:24-28`
2. **HIGH — Typ-Drift Incidents:** BE liefert `expect_expr`/`error_message`/`state`, kein `id`; FE erwartet `id`/`expected` → „Expected"-Spalte immer leer, `rowKey=undefined` für jede Zeile, `state` verworfen. `incidents.py:36-48` vs `types/index.ts:156-165`
3. **HIGH — Proposals dead-on-arrival:** BE-Status `open`, FE filtert `pending` → alle offenen Proposals landen unter „Reviewed", Accept/Reject-Buttons rendern nie. `Proposals.tsx:98`
4. **HIGH — SSE-Event-Shape-Mismatch:** FE erwartet `check_result`/`run_finished{summary}`; BE sendet `progress`/`run_started`/`run_finished{overall_status}`/`run_error`. Zudem liest **keine Komponente** den `sseStore` — Live-Run ist funktionslose Verrohrung; kein Polling-Fallback nach 202. `types/index.ts:191-194` vs `sse.py:51`
5. **MED — Cytoscape versteht kein `var()`:** Canvas-Renderer kann CSS-Variablen nicht auflösen — die Coverage-Farbcodierung der Map rendert mutmaßlich gar nicht. `LineageMap.tsx:175-199`
6. **MED — Positions-Cache vergiftet Live-Daten:** Cache-Key = Node-*Anzahl*; Restore via `cy.json({elements})` ersetzt auch `coverage_flag`/`dq_status` durch sessionStorage-Schnappschüsse — eine reparierte Node zeigt den alten Status. `LineageMap.tsx:30,214`
7. **MED — `RunState`-Drift:** FE `'failed'` vs BE/Migration `'error'`.
8. Dazu: Fehler rendern als leere Zustände (API-Ausfall = „all checks passing" — für ein *Monitoring*-Tool gefährlich); URL-State-Sync fehlt fast überall (WS1-3 fordert ihn); StatusGrid existiert nicht — stattdessen partitioniert `Cockpit.tsx` Objekte in Entweder-oder-Familien-Buckets (`family` als Objekt-Attribut modelliert) — ein Objekt kann nie Obs- **und** Quality-Status nebeneinander zeigen, das ist eine strukturelle Fehllesung der Architektur.

### A11y & Konsistenz

- Status farb-einzig (`StatusDot` ohne `aria-label`/Form-Redundanz); klickbare `div`s statt Buttons (nicht tastaturerreichbar); CommandPalette ohne Pfeiltasten/Enter/Fokus-Falle (Konzept §5.8 fordert es explizit); Kontrast der 10–11px-Pills auf Alpha-Hintergründen unter WCAG; kein `prefers-reduced-motion`.
- Status-Vokabular inkonsistent: Engine `pass|warn|fail|critical|error`, FE ersetzt `error` durch `unknown`; Map-Badges `●◐▲○` (Konzept) vs HANDOVER `✓/◐/⚠/○`; Route `/lineage` vs spec `/coverage`.
- **Zwei parallele Token-Systeme:** tailwind.config definiert Familienfarben (`#22c55e`), die Live-Komponenten nutzen ausschließlich Inline-Styles mit CSS-Vars (`#3FB07A`) — Tailwind wird de facto nur vom toten `Nav.tsx` benutzt.
- Tote Schicht: `Nav.tsx`, `useRuns`, `useLibrary`, `useCompileContract`, devtools-Dependency, `Kpi.sparkData`, hartkodierter `steward`-Chip und hartkodierter Lifecycle-Stepper (Fake-Daten in Governance).

---

## 6 / Was solide ist (behalten, nicht anfassen)

- **Expectation-Grammatik + Engine-Kern**: sauber, kein eval, verankerte Regexes, gut getestet.
- **SQLite-Store + Migration-Runner**: Idempotenz real getestet; Schema v2 vollständig angelegt.
- **Store-seitiges PII-Default-off + Allowlist** inkl. Verhaltenstests.
- **Compliance-Regel v1** (Funktion korrekt, getestet) — nur die Event-Persistenz fehlt.
- **Webhook-SSRF-Funktion** (Allowlist, Private-IP-Block, no-redirect, Timeout) — muss nur aufgerufen und gegen DNS-Rebinding gehärtet werden.
- **G7-AST-Gate**, **Polling-Progress-Design**, TLS-Defaults der DB-Connection.
- FE: Token-Basis in `index.css`, Shell/Routing, CompilePreview-Ansatz mit Determinismus-Hash, `CovFlag`-Test als Muster für G6-FE-Tests.

---

## 7 / Marktabgleich 2025/2026 (Quellen)

### 7.1 Standards — Konsequenz für uns

- **ODCS v3.1.0** (Bitol / LF AI & Data, Dez 2025) ist *der* Standard; die datacontract.com-Spec wurde **mit ODCS 3.1 deprecated**, die `datacontract-cli` nutzt ODCS als Default. v3.1 bringt Relationships (FK-Semantik!), executable SLAs, strengere Validierung. Unsere Garantie-Familien mappen fast 1:1: schema→`schema.properties`, keys/referential→constraints+relationships, freshness/volume→`slaProperties`+library-Checks, completeness→nullCount/completeness; Proprietäres→`customProperties`. Lifecycle (draft/active/deprecated)→ODCS `status`; **Compliance bleibt bewusst draußen** (ODCS modelliert keine Laufzeit-Resultate — bestätigt unsere A1-Trennung).
  https://bitol.io/bitol-announces-odcs-v3-1-0-stronger-smarter-and-stricter/ · https://github.com/bitol-io/open-data-contract-standard · https://datacontract.com/ · https://cli.datacontract.com/
- **`datacontract breaking`** (CLI) kann als CI-Zweitmeinung gegen unseren ODCS-Export laufen (O1/Stufe 2 quasi geschenkt). Kein Tool am Markt (inkl. datacontract-cli) hat einen **SAP-HANA-Runner** — das ist unser echtes Differenzierungsmerkmal.
- **SAP BDC Connect GA (Okt 2025):** ORD+CSN ist der *verpflichtende* Publishing-Pfad für Data Products in BDC (`sap-bdc-connect-sdk`, PyPI) — validiert WS5-4 voll. Aber: **kein standardisiertes ORD/CSN-Feld für DQ-Resultate** — Praxis: Compliance als ORD-Labels/Custom-Taxonomie + Katalog-Quality-Score, volle Garantien parallel als ODCS.
  https://help.sap.com/docs/business-data-cloud/sap-business-data-cloud-connect/appendix-describing-data-product-with-ord-and-csn-metadata · https://github.com/open-resource-discovery/specification · https://github.com/SAP/csn-interop-specification · https://pypi.org/project/sap-bdc-connect-sdk/

### 7.2 Tool-Landschaft — Table Stakes, die uns fehlen

Soda 4.0 (OSS-Contracts-Engine, ODCS-Input), Great Expectations Cloud (Coverage Metrics, ExpectAI), dbt (Health Tiles), Monte Carlo (Incident-Lifecycle, Data-Product-SLAs), Elementary, Sifflet (Alert-Gruppierung), Metaplane (→Datadog, Apr 2025), Anomalo, Bigeye (SLA-Store), OpenMetadata 1.10 (volle ODCS-3.1-Im-/Export):

1. **Incident-Lifecycle** — ein Breach erzeugt überall ein persistentes Incident-Objekt (Status triage/investigating/resolved, Owner, Severity, Aktions-Timeline), nicht nur eine rote Zelle. Uns fehlt es vollständig (unsere „Incidents"-Seite ist eine Live-Abfrage fehlgeschlagener Checks).
2. **Notification-Routing** (Slack/Teams/Mail mit Chart-Kontext inline; Ownership-Routing aus Contract-`team`) — bei uns: ein nie aufgerufener Webhook.
3. **SLA-Compliance über Zeitfenster** (Uptime-%-Stil je Contract) statt nur Letzter-Lauf-Zustand (Bigeye SLA-Store, MC Data-Product-Dashboards).
4. **Coverage-Metriken** (% Objekte/Spalten mit Garantien; Objekte >30 Tage unvalidiert — GX Cloud als Vorbild). Unsere Coverage-Map zeigt Platzierung, nicht Quoten.
5. **Status-Embedding für Konsumenten** (dbt-Health-Tile/Badge-API für SAC/BI).
6. Unser **Proposal-Miner** ist exakt der Markttrend 2025 (GX ExpectAI, Soda AI, Sifflet Sentinel) — Differenzierung: deterministisch/erklärbar statt ML-Blackbox. Baselines: Rolling-Stats/MAD entspricht Elementary/GX-Niveau; Feedback-Tuning (Soda-Daumen-Pattern) einplanen.
  https://soda.io/blog/introducing-soda-4.0 · https://docs.greatexpectations.io/docs/cloud/overview/gx_cloud_overview/ · https://docs.getdbt.com/docs/explore/data-tile · https://docs.datahub.com/docs/managed-datahub/observe/data-contract · https://www.datadoghq.com/about/latest-news/press-releases/datadog-metaplane-aquistion/

### 7.3 UI/UX-Stand der Technik

- **Status-Encoding:** IBM Carbon verlangt **≥3 von 4 Elementen** (Farbe, Icon/Form, Text, Kontext) je Statusindikator — direkt anwendbar auf StatusGrid und Cytoscape-Map (Formen-Set Kreis/Dreieck/Raute für CVD). WCAG: ≥4.5:1 Text, ≥3:1 UI-Grafik. https://carbondesignsystem.com/patterns/status-indicator-pattern/
- **Drilldown-Muster:** Tabelle/Grid + **Side-Panel-Peek**, Full-Page nur für tiefe Entitäten (Shopify Polaris resource-index). Zelle→SidePanel mit Check-Historie; Objekt→Seite. https://polaris-react.shopify.com/patterns/resource-index-layout
- **Tabellenzellen:** aktueller Wert + Delta-Indikator + Sparkline (7–30 Punkte, konsistente Achsen). https://www.smashingmagazine.com/2025/09/ux-strategies-real-time-dashboards/
- **Grafana Saga** (Referenz-Designsystem Observability): „UI-Friction soll der Schwere der Aktion entsprechen" — billig zu acknowledgen, bewusst einen Breaking-Approve zu bestätigen; Grafana 12 „observability as code"/Git Sync spiegelt unser Contracts-in-Git. https://grafana.com/developers/saga/foundations/design-principles/
- **Empty States:** NN/g — Status kommunizieren, lehren, nächste Aktion anbieten; Ideal bei uns: „Keine Garantien → hier sind 3 geminte Vorschläge" (Miner als Onboarding). https://www.nngroup.com/articles/empty-state-interface-design/
- **Layout:** NN/g F-Pattern — KPIs oben, Trends Mitte, Tabellen unten; präattentive Attribute, damit Breaches ohne Lesen poppen. https://www.nngroup.com/articles/dashboards-preattentive/
- **SAP-Kontext:** Fiori **Horizon** (Morning/Evening, WCAG 2.2) ist das Theme der Zielumgebung — mindestens die semantische Farb-Logik übernehmen, damit das Cockpit neben Datasphere/SAC nativ wirkt. https://experience.sap.com/fiori-design-web/evening-horizon/
- Erwartete Patterns: Command-K (vorhanden, aber ohne Tastatur-Nav), Density-Toggle, Skeleton-Loader, Toasts + optimistische Updates, virtualisierte Tabellen (>500 Objekte It-Ziel), dark-token-getrieben (Basis vorhanden).

---

## 8 / Priorisierte Zusammenfassung

**Sofort (Sicherheit/Integrität):** S-1…S-4 (Auth-Bypass-Pfade, SQL-Hintertür, Identifier-Injection), Compiler-Format (§ 1), FE-Crash (Hooks), L-7 (Glob-Bugs nullen Lineage-Coverage und Dry-Run aus).
**Danach (Workflow-Wahrheit):** Git-Schreibmodell, Run↔Contract-Verknüpfung, Compliance-Events, SSE-Ersatz, G1/G3/G4-Gates real, G6 end-to-end (Engine produziert states → FE rendert sie).
**Dann (Produktreife):** Incident-Lifecycle, Notifications, SLA-über-Zeit, Coverage-Metriken, ContractEditor-Neubau, Onboarding, ODCS-Export, A11y/Encoding nach Carbon-Regel.

Der detaillierte, sequenzierte Plan steht in `PLAN_Remediation_v2.md`.
