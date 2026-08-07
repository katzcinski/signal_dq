# Review — Implementierungsplan DQ-Cockpit v0.1

**Kritische Durchsicht: offene Flanken · SAP-BDC-Einbettung · Kundennutzen · Architektur · UI/UX · Security**

2026-06-09 · Gegenstand: `IMPLEMENTATION_PLAN_DQ_Cockpit.md` v0.1
Befund-Klassifikation: **[B] Blocker** (vor Start des betroffenen AP lösen) · **[N] Nachschärfen** (in Plan v0.2 einarbeiten) · **[A] Akzeptiert** (bewusster Trade-off, nur dokumentieren).

-----

## 1 — Offene Flanken im Plan

**F1 [B] — Das Git-Schreibmodell widerspricht sich selbst.** AP2 sagt „die API committet direkt, ein Commit je Approve”; G3 sagt „Breaking-Gate als CI auf Contract-PRs”. Wenn die API direkt auf `main` schreibt, läuft nie ein PR-Gate. Dazu ungelöst: Concurrency (zwei Stewards approven gleichzeitig → Race auf dem Working Tree), Repo-Heimat (lokal im Container = weg beim Restart; Remote = Push-Credentials, Push-Reject-Handling), Author-Mapping (Commit muss den Principal tragen, sonst Audit-Lücke). **Fix:** Diff-/Breaking-Prüfung läuft *zweimal mit demselben `dq_core`-Code* — API-seitig blockierend vor jedem Commit, CI-seitig als Netz für manuelle Git-Edits. Schreibzugriff serialisiert (ein Writer-Lock bzw. Commit-Queue), Remote-Repo als Wahrheit, Author = Principal.

**F2 [B] — In-Memory-Run-Registry bricht beim Kunden-Deployment.** Multi-User heißt realistisch Gunicorn/uvicorn mit >1 Worker — dann sieht der SSE-Endpunkt die Registry des anderen Workers nicht. **Fix:** Run-Zustand in den Result-Store (die `dq_runs`-Tabelle existiert; Status `running` + Progress-Zeilen), SSE liest daraus, Polling-Endpunkt als Fallback. Nebeneffekt: löst auch die Kollision API-Run ↔ CLI-Cron-Run auf demselben Dataset (Store-seitiges „läuft bereits”-Flag).

**F3 [B] — Run und Contract-Version sind nicht verknüpft.** Schema v2 führt `state` und Stats ein, aber `dq_runs` weiß nicht, gegen *welche* Contract-Version/-Hash es lief. Ohne das ist „Certify” (compliant/breached je Version) nicht beweisbar und der Breach-Webhook nicht zuordenbar. **Fix:** `dq_runs.contract_version` + `contract_hash` + `actor` (Erweiterung des vorhandenen `triggered_by`).

**F4 [N] — `breached`-Semantik ist unspezifiziert.** Wann kippt ein Contract auf breached (erster critical-Fail? N Läufe in Folge?) und wann zurück (erster Pass? manuell)? Das ist die Kernsemantik der Zertifizierung und derzeit ein Wort im Plan. **Fix:** Transition-Regel v1 festlegen: breached bei ≥1 nicht bestandenem Check mit Severity ≥ `fail` der aktiven Version; Auto-Recovery bei vollständig grünem Folgelauf; beides als Events im Store, nicht nur als Zustand.

**F5 [N] — Aktualität von `inventory.json`/`lineage.json` ist ungesteuert.** Seed, Coverage Map und Schema-Drift hängen an Batch-Extrakten; der Plan hat weder Extraktions-Job/-Endpunkt noch Anzeige des Extrakt-Alters. Eine Coverage Map auf drei Wochen altem Extrakt ist eine falsche Karte. **Fix:** `POST /api/extract` (ruft die bestehende Analyzer-Kette), Extrakt-Timestamp prominent in Map und Seed-Dialog, Staleness-Warnung ab Schwellwert.

**F6 [N] — Environment-/Mehrkunden-Konzept fehlt.** Eine `DbConfig` aus ENV modelliert genau einen Tenant. Real: ein Berater ↔ mehrere Kunden; ein Kunde ↔ DEV/PROD. Verknüpft mit der `schema_ref`-Frage (→ A2). **Fix:** Environments-Konfiguration (Name → Host/Schema-Mapping) ab AP0; Contracts bleiben environment-frei.

**F7 [N] — Kein Rollback-Pfad nach fehlerhaftem Compile.** Compile committet, der nächste Lauf zeigt: generierter Check wirft SQL-Fehler (fail-closed greift, gut) — aber der Operator-Weg zurück (Revert auf vorherige `checks.yml` aus dem UI) ist nicht definiert. **Fix:** „Revert auf Vorversion”-Aktion in der Compile-Ansicht = Git-Revert + Hinweis im Dashboard.

**F8 [A] — Aufwand ist optimistisch.** 44–69 PT netto für Editor + Compiler + Graph-Viz + Auth-Abstraktion + zwei Stores. Mit den Deltas aus diesem Review, Edge-Cases, Doku und Stabilisierung realistisch **60–95 PT brutto**. Bewusst so kommunizieren — die Netto-Zahl taugt nicht als Angebotsbasis.

-----

## 2 — Einbettung in SAP BDC

Wettbewerbs- und Integrationslage (Stand Juni 2026, web-verifiziert; Quellen-Güte markiert):

- **SAP positioniert BDC als Governance-Schicht, nicht als Check-Engine.** Sapphire 2026: HANA Cloud und MDG sind Kernkomponenten von BDC; der „Knowledge Core” führt aktive Metadaten inkl. „data quality and trust signals” (SAP Architecture Center — offiziell, aber deskriptiv formuliert: Signale *informieren* Nutzung, kein Enforcement-Mechanismus beschrieben).
- **Datasphere-nativ:** Der Data-Validation-Rahmen (Modell-Validierungen, referenzielle Integrität) existiert, ist aber metadatennah und **manuell auszuführen** (SAP Community, bestätigt 2024/2025) — genau die Lücke, die Community-Teams mit Eigenbauten füllen (AI-assisted DQ Screening, SAP Community 09/2025). Das bestätigt: die Lücke ist real *und* andere bauen bereits hinein.
- **Vendor-Blogs (SAVIC, 04/2026)** behaupten ML-Profiling + „AI-suggested remediation rules” in Datasphere — Beratungs-SEO ohne SAP-Roadmap-Beleg; nicht als Fakt behandeln, aber als Richtungssignal: SAP bewegt sich auf dieses Feld zu.
- **Dritthersteller:** Collibra DQ & Observability mit Pushdown für HANA/Datasphere ist der reale kommerzielle Wettbewerber im Konzernsegment (ML-generierte Regeln, Pushdown-Ausführung).

**Befunde:**

**B1 [N] — Positionierung muss die Konkurrenzlage explizit beantworten.** Gegen Datasphere-nativ gewinnt das Cockpit klar (kontinuierlich vs. manuell, Contract + Gating + Feedback vs. Einzelvalidierung). Gegen Collibra **nicht antreten**: wo eine Governance-Suite gesetzt ist, ist das Cockpit das falsche Angebot — Zielsegment ist der Datasphere-Mittelstand/T&M-Kunde ohne Suite-Budget. Diese Abgrenzung gehört in den Pitch, sonst entscheidet der Kunde sie selbst.

**B2 [N] — Die strategische Antwort auf BDC-„Quality Signals” ist: Zulieferer werden, nicht Konkurrent.** Wenn der BDC-Catalog Qualitätssignale anzeigt, soll das Cockpit deren *Produzent* sein. Das ist exakt E1 („BDC beschreibt — das Cockpit erzwingt”), aber v1 hat den Export-Hook nur „vorgesehen” — damit ist die BDC-Story im Vertrieb leer. **Fix:** Minimaler einseitiger Export ab M2 (generierte CSN-Annotations-Datei + ORD-Custom-Label-Fragment als Artefakt, manuell deploybar). Kostet 2–3 PT, macht die Demo BDC-anschlussfähig, ohne R1/R2 vorzugreifen.

**B3 [A] — HANA-only-Executor (E2) begrenzt den prüfbaren Scope bei BDC-first-Kunden.** Object-Store-/Delta-Produkte sind erst nach Provisionierung in eine HANA-Repräsentation prüfbar. Bewusste Entscheidung (kein Engine-Fork) — aber als expliziter Satz in jede Kundenpräsentation, bevor der Kunde es als Lücke entdeckt. HDLF-CLI-Gap bleibt als bekanntes Risiko bestehen.

**B4 [N] — Data Product Studio (GA H1 2026) erzeugt Authoring-Erwartung beim Product Owner.** „Warum nicht im SAP-Standard pflegen?” wird kommen. Antwort existiert (DPS kennt keine durchsetzbaren Garantien), aber der Plan sollte die `product_owner`-Variante als *Import-Pfad* vorsehen (DPS-Definition → Contract-Draft-Seed) statt nur als alternative UI „später” — das nimmt dem Einwand die Spitze.

-----

## 3 — Wertung: Nutzen für den Kunden

**N1 — Der Wertschwerpunkt liegt in AP1 + 7.1, nicht im Contract-Stack.** Das akute, universelle Kundenproblem ist „Lauf fehlgeschlagen / Tabelle halbiert / niemand hat’s gemerkt” — das lösen Dashboard + Observability. Der volle Contract-Lifecycle (SemVer, Breaking-Diff, Approval-Zeremonie) setzt Rollen voraus (Steward, Product Owner), die im Datasphere-Mittelstand oft nicht existieren. Risiko: 10–15 PT Workbench für eine Persona ohne Besetzung. **Fix:** Workbench bekommt einen **Lite-Modus** — Contract als geführte Checkliste (Garantien an/aus, Severity), ohne Versions-/Approval-Pflicht; der volle Lifecycle ist zuschaltbar. Gleicher Unterbau, zwei Reifegrade.

**N2 — Die „Warum nicht SAC + DQ-Views?”-Frage braucht eine Tabelle, keinen Absatz.** Die eigene Integrationsmuster-Doku sagt: DQ-as-View + SAC deckt 80 % nativ. Differenzierung je Modul explizit machen:

|Fähigkeit                                      |SAC + DQ-Views  |Datasphere-Validations|Cockpit       |
|-----------------------------------------------|----------------|----------------------|--------------|
|Kontinuierliches Monitoring + Historie je Check|◐ (selbst bauen)|✗ (manuell)           |✓             |
|Gating (stale-skip, Key-vor-FK)                |✗               |✗                     |✓             |
|Generierung aus Metadaten/Contract             |✗ (Handpflege)  |✗                     |✓             |
|Feedback-Loop (Proposals aus Baselines)        |✗               |✗                     |✓             |
|Governance (Versionen, Breaking, Approval)     |✗               |✗                     |✓ (Voll-Modus)|

**N3 [N] — Das Betriebsmodell ist unbeantwortet und vertriebsrelevant.** „Lokal beim Berater” = kein Dauerbetrieb, Kunde abhängig vom Laptop; „Container beim Kunden” = der Kunde braucht jemanden für Updates, Secrets, IdP. Beides ist verkaufbar, aber es muss *vor* M2 entschieden und bepreist sein (Betreibervertrag vs. Übergabe). Derzeit fällt es zwischen die Deployment-Optionen.

**N4 — Exit-Argument aktiv verkaufen.** Contracts = YAML in Git, Checks = YAML, Ergebnisse = HANA-Tabelle, SAC liest weiter die Released Views: der Kunde behält bei Cockpit-Wegfall alles Lauffähige. Das ist gegen jede Suite ein echtes Argument und steht bisher nirgends.

**Nutzen-Wertung je Baustein:**

|Baustein                |Kundennutzen                           |Bedingung                      |
|------------------------|---------------------------------------|-------------------------------|
|AP1 Dashboard           |hoch, sofort, jede Kundengröße         |—                              |
|7.1 Observability       |hoch (das akute Problem)               |O2-Spike (Metadaten-Zugriff)   |
|AP3 Builder             |hoch (Pflegeaufwand ↓)                 |Contract Lite reicht als Quelle|
|AP2 Workbench Voll-Modus|hoch nur bei Governance-Reife          |Rollen beim Kunden besetzt     |
|7.2 Miner               |mittel–hoch, Differenzierer            |Datenhistorie ≥ Warm-up        |
|AP4 Coverage Map        |mittel operativ, hoch im Vertrieb/Audit|aktueller Extrakt (F5)         |

-----

## 4 — Architektur

**A1 [B] — Modellfehler: `status: breached` gehört nicht ins versionierte YAML.** Breached ist abgeleiteter *Runtime*-Zustand — im Git-Artefakt erzeugt er entweder einen Commit pro Statuswechsel (Historie verschmutzt) oder ist per Definition veraltet. **Fix:** Feld splitten. `lifecycle: draft | active | deprecated` (Governance-Zustand, im YAML, ändert sich nur durch Menschen) · `compliance: compliant | breached | unknown` (abgeleitet aus `dq_object_status` + F4-Regel, lebt ausschließlich im Store/Rollup, wird im UI gejoint angezeigt).

**A2 [N] — `schema_ref` zur Laufzeit binden, nicht zur Compile-Zeit.** Compile-Zeit-Auflösung macht `checks.yml` environment-spezifisch (Datei je Umgebung, Drift-Quelle). Die Bausteine für die bessere Lösung existieren bereits: `check_library`-Templates nutzen das `{schema}`-Token, der Runner hat `--db-schema`. **Fix:** Contract environment-frei, kompilierte Checks mit `{schema}`-Platzhalter, Bindung über die Environments-Konfiguration (F6) beim Run. G2 („kein hardcodiertes CENTRAL”) wird damit strukturell erzwungen statt nur getestet.

**A3 [N] — Git ist keine Query-Datenbank.** `GET /api/contracts` mit Filtern (lifecycle, owned_by, Produkt-Suche) erfordert sonst Working-Tree-Scans pro Request. **Fix:** Read-Index in SQLite (Contract-Metadaten, invalidiert per HEAD-Hash) — 0,5 PT, erspart spätere Performance-Flickerei.

**A4 [N] — Determinismus-Hash muss die Library einschließen.** „Gleiche Contract-Version ⇒ byte-identische checks.yml” bricht bei jedem Template-Fix in `check_library.json`. **Fix:** Library bekommt eigene Version (Feld existiert: `"version": 1`); Header-Hash = f(Contract-Hash, Library-Version); Library-Änderung ⇒ Recompile-Hinweis im UI.

**A5 [N] — Registry in den Store, SSE optional.** Folge aus F2; zusätzlich UX-relevant: SSE über Corporate-Proxies ist fragil, mobil erst recht. Polling auf `GET /api/runs/{id}` als gleichwertiger Pfad, SSE als Progressive Enhancement.

**A6 [A] — Pydantic-Spiegelung der Engine-Dataclasses = Doppelpflege.** Akzeptiert (hält die Engine API-frei), aber mit Drift-Schutz: Snapshot-Test, der Dataclass-Felder gegen Schema-Felder vergleicht.

-----

## 5 — UI/UX

**U1 [B] — Farbkollision: Grün ist doppelt belegt.** Familienfarbe Quality = Grün *und* Status pass = Grün — ein StatusGrid mit grüner Quality-Spalte voller grüner Pass-Badges ist unlesbar, im Fehlerfall sogar irreführend. **Fix als Design-Token-Regel:** Familien werden über Form/Icon/Spaltenposition codiert (Label + Icon, monochrom), die Ampel (grün/gelb/rot/grau) ist **exklusiv** für Status reserviert. Familienfarben bleiben für Diagramme/Dokumente, wo kein Statuskontext ist.

**U2 [N] — Der Garantie-Editor braucht einen Inventar-Picker — fehlt in AP2.** Referential-Garantien (FK → Parent-Objekt/-Spalten) per Freitext sind Tippfehler-Hölle und unterlaufen die S2-Validierung nutzerseitig. **Fix:** Autocomplete gegen den Inventar-Snapshot (Objekt- und Spaltenebene) als eigener Baustein in AP2 (+1–2 PT) inkl. Read-Endpunkt `GET /api/inventory`.

**U3 [N] — Responsive-Festlegung fehlt.** Status prüfen und Proposals approven sind klassische Mobile-Momente; Editor und Coverage Map sind Desktop-Arbeit. **Fix:** Dashboard, Objekt-Detail, Proposal-Inbox, Approve-Aktion = mobile-tauglich; Editor, Compile-Diff, Map = Desktop-only mit sauberem Hinweis statt kaputtem Layout.

**U4 [N] — Erststart-Erlebnis entscheidet die Demo.** Leerer Tenant: kein Extrakt, kein Contract, kein Run → drei leere Screens. **Fix:** geführter Onboarding-Flow (1 Extrakt einspielen/triggern → 2 Seed für ein Objekt → 3 Dry-Run → 4 Dashboard zeigt erstes Ergebnis) als expliziter Pfad, nicht nur Empty-State-Texte.

**U5 [A] — Sprache: de-only in v1**, alle Strings zentral (ein Modul), damit i18n nachrüstbar bleibt ohne Treasure Hunt.

-----

## 6 — Security

**S1 [B] — `dq_diagnostics` ist ein Datenleck-Kanal und kollidiert mit der eigenen Datenschutz-Doku.** `CheckResult.diagnostic_rows` persistiert Rohzeilen verletzter Datensätze — im Lokal-Modus landen damit potenziell personenbezogene Produktivdaten in einer SQLite auf dem Berater-Laptop. Die eigene Integrationsmuster-Doku fordert für Reject-Daten dieselben DAC-Regeln wie für Originale. **Fix:** Diagnostics default **aus**; Aktivierung nur je Check mit Spalten-Allowlist; Retention-TTL im Store; im Lokal-Modus zusätzliche explizite Freigabe (ENV-Flag). Auch im Sinne von E6 (nur Skalare verlassen HANA) konsequent.

**S2 [B] — Identifier-Injection im Compiler.** Spalten-/Objektnamen aus dem Contract werden in `sql_template`-Tokens interpoliert — Quoting allein schützt nicht (eingebettete `"` im Namen). Bedrohung: kompromittiertes Contract-Repo oder böswilliger Editor-Input. **Fix (dreifach):** Identifier-Regex-Policy (`^[A-Za-z_][A-Za-z0-9_]*$`, v1-Einschränkung dokumentieren), Existenzprüfung gegen den Inventar-Snapshot (Spalte muss es geben), Quote-Escaping als letzte Schicht. Klarstellung im Sicherheitsmodell: freies SQL existiert weiterhin in handgepflegten Suiten (`custom_sql`) — **die tatsächliche Grenze ist der DB-User**, nicht der Parser.

**S3 [N] — `owned_by` ohne Owner-Zuordnung ist Dekoration.** Rollenmodell prüft *was* jemand ist, nicht *wofür*. Darf jeder Steward jeden Contract approven? **Fix:** `owners: [sub|Gruppe]` im Contract (Governance-Daten, gehören ins YAML) + Autorisierungsregel: Schreiben/Approven = Rolle × Mitgliedschaft.

**S4 [N] — DB-User-Härtung.** Technischer User strikt: SELECT auf Prüf-Schemata + INSERT/UPDATE nur auf `dq_results_lt`-Schema; nie ein Space-Admin. TLS: prüfen, ob `db_connection.py` `encrypt=true` + Zertifikatsvalidierung setzt — falls nein, nachrüsten (Pflicht). Secrets beim Kunden aus Secret-Store/Mounted File, Rotationszuständigkeit benennen.

**S5 [N] — NoAuth muss fail-closed sein.** Fehlkonfiguration (AUTH_MODE vergessen) darf nicht einen Admin-Principal ins Kundennetz stellen. **Fix:** Default-Bind `127.0.0.1`; Bind auf `0.0.0.0` nur wenn AUTH_MODE explizit gesetzt — sonst Startabbruch mit klarer Meldung.

**S6 [N] — Webhook = SSRF-Fläche.** Konfigurierbarer POST aus dem Service heraus: URL-Allowlist (Host-Pattern), kein Redirect-Follow, Timeout, keine internen IP-Ranges.

**S7 [N] — Audit-Spur vervollständigen.** Git deckt Contracts (mit F1-Author-Mapping); Runs/Compiles/Proposals brauchen den Principal: `triggered_by` existiert bereits → um `actor` erweitern (deckt sich mit F3).

**S8 [A] — Frontend-Basics:** CSP setzen, `dangerouslySetInnerHTML` verboten (Check-Namen/Beschreibungen/YAML sind Nutzereingaben, auch in Cytoscape-Labels), Lint-Regel dazu.

-----

## 7 — Konsequenz: Delta-Liste für Plan v0.2

|#  |Änderung                                                                                                                |Trifft |Aufwand Δ             |
|---|------------------------------------------------------------------------------------------------------------------------|-------|----------------------|
|D1 |Git-Schreibmodell: serverseitiges Breaking-Gate vor Commit + Writer-Serialisierung + Remote-Repo + Author=Principal (F1)|AP0/AP2|+1 PT                 |
|D2 |Run-Registry in den Store, SSE optional + Polling-Fallback (F2/A5)                                                      |AP0/AP1|±0 (Umverteilung)     |
|D3 |Schema v2 erweitert: `contract_version`, `contract_hash`, `actor` in `dq_runs` (F3/S7)                                  |AP0    |+0,5 PT               |
|D4 |`lifecycle`/`compliance`-Split + breached-Transition-Regel (A1/F4)                                                      |AP2    |+0,5 PT               |
|D5 |Environments-Konfiguration + Laufzeit-Schema-Bindung via `{schema}` (F6/A2)                                             |AP0/AP3|+1 PT                 |
|D6 |Extrakt-Job + Timestamp-Anzeige + Staleness-Warnung (F5)                                                                |AP0/AP4|+1 PT                 |
|D7 |Inventar-Picker + `GET /api/inventory` (U2/S2)                                                                          |AP2    |+1–2 PT               |
|D8 |Workbench-Lite-Modus (N1)                                                                                               |AP2    |+1–2 PT               |
|D9 |Diagnostics: default off, Allowlist, TTL, Lokal-Freigabe (S1)                                                           |AP0/AP1|+1 PT                 |
|D10|Identifier-Validator im Compiler (S2)                                                                                   |AP3    |+0,5 PT               |
|D11|CSN/ORD-Minimal-Export als Artefakt ab M2 (B2)                                                                          |neu    |+2–3 PT               |
|D12|Token-Regel Familien≠Ampel (U1) + Onboarding-Flow (U4) + Responsive-Matrix (U3)                                         |AP0/AP1|+1–2 PT               |
|D13|NoAuth fail-closed, TLS-Check, Webhook-Allowlist, Owner-ACL (S3–S6)                                                     |AP0/7.3|+1–1,5 PT             |
|D14|Betriebsmodell-Entscheidung als expliziter Meilenstein-Vorläufer vor M2 (N3)                                            |Plan   |Entscheidung, kein Bau|

Summe Δ ≈ **+12–16 PT** → realistische Gesamtspanne **60–95 PT brutto** (deckt sich mit F8).

**Gesamturteil:** Plan-Grundgerüst (dq_core/FastAPI/React, AP-Reihenfolge, Gates) hält der Prüfung stand — kein struktureller Umbau nötig. Die Blocker (F1–F3, A1, U1, S1, S2) sind sämtlich vor oder in AP0/AP2 lösbar und ändern keine gesetzte Konzept-Entscheidung (E1–E6 bleiben unberührt). Die zwei strategischen Nachschärfungen sind nicht technisch: Workbench-Lite für die Persona-Realität (N1) und der Minimal-Export, der die BDC-Story von „vorgesehen” auf „zeigbar” hebt (B2).