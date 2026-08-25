# Betriebsmodi — Lite & Full · Prozess, Personas, Tooling

**Adressat:** Beratung, Plattform-Team, Fachbereich, Governance · **Stand:** 2026-06-15
**Zweck:** Wie das DQ- & Observability-Cockpit zwei Reifegrade von Data-Product-Verbindlichkeit bedient — den **Lite-Einstieg** (Verbindlichkeit ohne Org-Change) und den **Voll-Modus** (governte Data Products mit Versionierung & Approval) — auf demselben technischen Unterbau.

> Verwandte Dokumente: `ADR-0006_Editor-Modus_aus_Kind.md` (Modus-Default folgt dem `kind`; Override kontrolliert) · `HANDOVER.md` (technischer Implementierungsplan, Workstreams, Gates) · `Konzept_DQ_Observability_Cockpit.md` (fachliches Konzept) · `Konzept_MVP_Kundenrollout.md` (**welche Module beim Kunden wann freigeschaltet werden** — Lite ist der Funktionskern der Welle 0, Full folgt in Welle 2).

---

## 0 — Kernaussage

Beide Modi teilen **einen** Unterbau: dieselben Garantie-Familien, denselben Compiler, dieselbe Engine, dieselbe Result-Store-/Compliance-Mechanik. Der Unterschied liegt **allein in der Prozess-Zeremonie**. Der Editor-Default folgt dem `kind`: `internal_gate` startet in **Lite**, `consumer_contract`/`provider_contract` starten im **Full**-Workflow. Ein expliziter URL-Override bleibt moeglich, ausser bei bereits zertifizierten Contracts: dort entfaellt der Wechsel zur schnellen Zertifizierung.

| | **Lite** | **Full** |
|---|---|---|
| Leitfrage | „Was garantieren wir heute messbar?" | „Welche versionierte Zusage trägt das Produkt verbindlich?" |
| Contract-Erstellung | Geführte Checkliste: Garantie **an/aus** + eine Severity je Familie | Feingranulare Regeln, Inventar-Picker je Spalte |
| Lifecycle | Direkt `active` (ein Klick: Speichern & aktivieren) | `draft → active → deprecated` |
| Versionierung | Keine SemVer-Pflicht | SemVer; **Breaking ⇒ Major** (Gate G3) |
| Freigabe | Keine Approval-Zeremonie | **Approval** durch berechtigte Rolle, genau 1 Commit |
| Ownership | typ. `owned_by: platform` (Plattform/Beratung) | typ. `owned_by: product` (Fachbereich) |
| Breaking-Diff | Greift erst bei bereits zertifizierten Produkten | Immer, blockierend (Server **und** CI) |
| Konsumenten-Sicht | Status, Compliance-Ampel, Coverage `✓` | identisch + SLA-Fenster, Versionshistorie |
| Gates G1/G2/G6/G8 | **unverändert scharf** | **unverändert scharf** |

**Gemeinsam:** Garantien sind rein semantisch — **niemals SQL** (Gate G1). Der Server ist autoritativ; das Frontend spiegelt nur.

---

## 1 — Personas

### 1.1 Technische Rollen (im Tool, `[AUTHZ]`)

Quelle: `services/api/auth/provider.py` · Schreibrecht = `Rolle × owned_by × owners`.

| Rolle | Lesen | Run auslösen | Lite-Certify | Full-Approve | Schreibrecht-Regel |
|---|---|---|---|---|---|
| `viewer` | ✅ | ❌ | ❌ | ❌ | nie schreiben |
| `steward` | ✅ | ✅ | ✅ bei `platform` | ✅ bei `platform` | platform-owned Contracts |
| `owner` | ✅ | ✅ | ✅ | ✅ | platform **und** product-owned |
| `admin` | ✅ | ✅ | ✅ | ✅ | alles |

Zusätzlich: `owners: ["grp:…", "<sub>"]` im Contract erlauben Einzel-/Gruppen-ACLs (IdP-Claim, fail-closed).

### 1.2 Fachliche Personas (Engagement)

| Persona | Typische Rolle | Heimat-Modus | Verantwortung |
|---|---|---|---|
| **Plattform-/Beratungsteam** | `steward`/`owner` | **Lite** zuerst | Objekte extrahieren, Lite-Garantien aufsetzen, erste Verbindlichkeit herstellen |
| **Data Product Owner** (Fachbereich) | `owner` | **Full** | Übernimmt Ownership, versioniert Zusagen, genehmigt Änderungen |
| **Konsument** (SAC-Report, Downstream-Modell, Data Scientist) | `viewer` | beide | Liest Compliance-Ampel/SLA; meldet Bedarf |
| **Governance/Daten-Office** | `steward`/`admin` | beide | Coverage-Lücken, Breaking-Policy, Betriebsmodell |

> Der **Übergang Lite → Full** ist genau der Moment, in dem ein Objekt von `owned_by: platform` auf `owned_by: product` wechselt — der Fachbereich übernimmt die Zusage, die die Plattform vorgespurt hat.

---

## 2 — Gemeinsamer Unterbau

### 2.1 Garantie-Familien (Contract-Schema v1, `[CONTRACT-SQL-FREE]`)

| Familie | Bedeutung | Kompiliert zu Check | Verbindlichkeits-Dimension |
|---|---|---|---|
| `schema` | erwartete Spalten, `mode: closed/open` | Spaltenanzahl/-existenz | **Struktur** |
| `keys` | Unique-Schlüssel | Duplikat-Check `= 0` | **Struktur** |
| `referential` | FK-Integrität gegen Parent | Orphan-Check `= 0` | **Struktur** |
| `not_null` | Pflichtspalten | Missing-Check `= 0` | **Qualität** |
| `completeness` | min. Füllgrad je Spalte (`min_pct`) | NULL-Quote `<= x%` | **Qualität** |
| `freshness` | max. Alter (`max_age`, ISO-8601) | Alter `< n s` | **Performance/Verlässlichkeit** |
| `volume` | Mindestzeilen / Rolling-Bounds | Row-Count `>= n` | **Performance/Verlässlichkeit** |

`volume.baseline: rolling` ist Observability-Konfiguration (Baselines), kein kompilierbarer Check.

### 2.2 Drei Zustands-Achsen (bewusst getrennt)

- **Lifecycle** (im YAML): `draft | active | deprecated` — wo der Contract im Erstellungsprozess steht.
- **Compliance** (nur im Store, nie im YAML): `compliant | breached | unknown` — ob die aktive Zusage gerade gehalten wird. Kippt auf `breached` bei ≥1 nicht bestandenem Check ≥ `fail`; Auto-Recovery bei grünem Folgelauf.
- **Coverage** (abgeleitet): `covered | partial | gap | out_of_scope` — ob ein Objekt überhaupt eine zertifizierte, kompilierte Zusage trägt.

### 2.3 Gates (CI + serverseitig, gelten in **beiden** Modi)

| Gate | Inhalt |
|---|---|
| G1 | Kein SQL im Contract |
| G2 | Kein hartkodiertes Schema im Compiler (`{schema}` erst zur Laufzeit gebunden) |
| G3 | Breaking ⇒ Major-Sprung *(Lite: nur für bereits zertifizierte Produkte)* |
| G5 | Engine-Regression-Schutz |
| G6 | Gating sichtbar (`skipped_stale` nie wie `pass`) |
| G7 | `dq_core` frameworkfrei |
| G8 | PII-Gate (keine Rohzeile ohne Allowlist) |

---

## 3 — Prozess Lite (Verbindlichkeit ohne Zeremonie)

**Ziel:** In Tagen — nicht Wochen — messbare Zusagen an Konsumenten liefern, *bevor* der Fachbereich Ownership übernimmt.

```
Extrakt ──▶ Seed ──▶ Lite-Garantien ──▶ Speichern & aktivieren ──▶ Run ──▶ Cockpit
 (F5)      (WS2-2)   (Checkliste)        (1 Klick: certify)         (HANA)   (Ampel)
```

| # | Schritt | Persona | Tooling / Endpoint | Ergebnis |
|---|---|---|---|---|
| L1 | **Inventar/Lineage extrahieren** | Plattform `steward` | `POST /api/extract` · Screen `/objects`, `/coverage` | Objektliste, Extrakt-Alter sichtbar |
| L2 | **Draft seeden** | Plattform | `POST /api/contracts/{p}/seed` · Workbench `/contracts` | Garantie-Vorschläge aus Inventar (kein leeres Blatt) |
| L3 | **Lite-Garantien setzen** | Plattform | Workbench **Lite-Modus**: Familien an/aus + Severity | Fokus: `freshness`, `not_null`, `keys`, `schema closed` |
| L4 | **Speichern & aktivieren** | Plattform `steward`/`owner` | **`POST /api/contracts/{p}/certify`** (Button „Speichern & aktivieren") | Contract `active`, Checks kompiliert, Compliance `unknown` |
| L5 | **Lauf auslösen** | Plattform | `POST /api/objects/{id}/run` (oder CLI/Cron) | Persistenter Run gegen Datasphere |
| L6 | **Konsument sieht Ampel** | `viewer` | Cockpit `/`, Coverage `/coverage`, Objekt `/objects/:id` | Status grün/rot, Coverage `✓`, Compliance-Ampel |

**Was Lite bewusst auslässt:** SemVer, Approval-Dialog, Breaking-Diff-Pflicht (außer der Schutz für bereits zertifizierte Produkte, s. u.). **Was Lite trotzdem erzwingt:** G1 (kein SQL), ≥1 kompilierbare Garantie (sonst Ablehnung), Schreibrecht.

**Sicherheitsnetz im Lite-Pfad** (`certify`): Existiert bereits eine zertifizierte Version (`.active.yml`-Snapshot) und der Change ist **breaking** ohne Major-Sprung → **409, Verweis auf Voll-Modus** (G3 bleibt intakt). Greenfield-Adoption bleibt reibungslos; ein governtes Produkt lässt sich über Lite nicht aushebeln.

---

## 4 — Prozess Full (governte Data Products)

**Ziel:** Versionierte, vom Fachbereich verantwortete Zusagen mit nachvollziehbarem Änderungspfad.

```
Seed/Edit ─▶ Diff ─▶ Approve ─▶ Compile ─▶ Run ─▶ Cockpit + SLA
 (draft)   (breaking?) (active, 1 Commit) (checks.yml) (HANA)  (Ampel + Historie)
```

| # | Schritt | Persona | Tooling / Endpoint | Gate |
|---|---|---|---|---|
| F1 | **Draft anlegen/bearbeiten** | Owner | `PUT /api/contracts/{p}` (immer Draft) · Workbench **Voll-Modus**, Inventar-Picker | G1 |
| F2 | **Breaking-Diff prüfen** | Owner/Steward | `POST /api/contracts/{p}/diff`, `GET …/version-diff` · `BreakingDiffPanel` | G3-Vorschau |
| F3 | **Genehmigen** | berechtigte Rolle | `POST /api/contracts/{p}/approve` · `ApprovalBar` | **G3 blockierend** + 1 Commit (Author = Principal) |
| F4 | **Kompilieren** | Owner/Steward | `POST /api/contracts/{p}/compile` (nur `active`) · `CompilePreview` | G2, Determinismus |
| F5 | **Dry-Run (optional)** | Steward+ | `POST /api/checks/{ds}/dry-run` · `DryRunPanel` | nicht persistiert |
| F6 | **Lauf & Compliance** | Steward+ | `POST /api/objects/{id}/run` | G6 (Gating sichtbar) |
| F7 | **SLA & Historie** | viewer/Owner | `GET /api/contracts/{p}/sla` · `SlaBars`, Run-Compare `/runs/compare` | — |
| F8 | **Veralten** | Owner | `POST /api/contracts/{p}/deprecate` | — |
| F9 | **Revert (Notfall)** | Steward+ | `POST /api/checks/{ds}/revert` (Git) | F7-Wiederherstellung |

Zusätzliche Voll-Modus-Werkzeuge: **Proposal-Inbox** (`/proposals`, datengetriebene Garantie-Vorschläge aus dem Miner), **Incidents** (`/incidents`, Breach-Episoden mit Timeline), **BDC/ODCS-Export** (`…/export/bdc`, `…/export/odcs`).

---

## 5 — Übergang Lite → Full (Reifegrad-Pfad)

Der Wechsel ist **kein Rebuild** — gleicher Unterbau, nur mehr Zeremonie und ein Ownership-Shift.

| Auslöser | Aktion | Persona |
|---|---|---|
| Fachbereich erkennt Wert (Ampel zieht Pull) | `owned_by: platform → product` setzen | Governance + Owner |
| Zusage soll versioniert/verbindlich werden | In der Workbench **Voll-Modus** zuschalten (Toggle), SemVer pflegen; bei `consumer_contract`/`provider_contract` ist das der Default | Owner |
| Erste governte Änderung | regulärer `draft → diff → approve`-Pfad | Owner |
| Breaking-Schutz | Ab jetzt greift G3 bei jeder Änderung blockierend | System |

> **Hinweis (ADR-0006):** Der Editor-**Default**-Modus folgt dem `kind` (Gate → Schnell zertifizieren, Contract → Freigabe-Workflow); der Toggle bleibt als Override. Auf einem **bereits zertifizierten** Contract entfällt der Schnell-Override — jede weitere Änderung läuft über die Freigabe (G3-Schutz bleibt serverautoritativ).

**Empfehlung:** Lite für die 3–5 wichtigsten Konsum-Objekte starten; die sichtbare Coverage-Map als Gesprächsanker nutzen („dieses Objekt, von dem ihr lebt, trägt heute null Garantien"), um Ownership organisch auszulösen.

---

## 6 — Tooling-Referenz (Screens × Modus)

| Screen / Route | Lite | Full | Zweck |
|---|---|---|---|
| `/` Cockpit (StatusGrid) | ✅ | ✅ | Status je Objekt × Familie, stale sichtbar (G6) |
| `/objects`, `/objects/:id` | ✅ | ✅ | Katalog, Detail, Checks, Sparkline, Run-Trigger |
| `/coverage` (Lineage) | ✅ | ✅ | Coverage `✓/◐/⚠/○` je Objekt, Pfad in die Workbench |
| `/contracts` Workbench | ✅ Lite-Pane | ✅ Voll-Pane | Garantie-Editor; Default aus `kind`; Toggle zwischen den Modi, solange ein zertifizierter Contract nicht auf Full festliegt |
| `/runs/:id`, `/runs/compare` | ✅ | ✅ | Lauf-Detail, Versions-/Lauf-Vergleich |
| `/incidents` | (ab Compliance) | ✅ | Breach-Episoden mit Timeline |
| `/proposals` | — | ✅ | Datengetriebene Garantie-Vorschläge (Miner) |
| `/governance`, `/library` | ✅ | ✅ | ACLs, Check-Bibliothek |

**Persistierte Artefakte:** `contracts/<product>.yaml` (Git) · `contracts/<product>.active.yml` (zertifizierter Snapshot, G3-Basis) · `checks/<product>/checks.yml` (kompiliert, mit Determinismus-Header) · Result-Store (SQLite lokal / `dq_results_lt` in HANA).

---

## 7 — Verantwortlichkeiten (RACI, verdichtet)

| Aktivität | Plattform/Beratung | Product Owner | Konsument | Governance |
|---|---|---|---|---|
| Extrakt & Seed | **R/A** | C | I | I |
| Lite-Garantien & Certify | **R/A** | C | I | C |
| Ownership-Übernahme | C | **A** | I | **R** |
| Full-Approval & Versionierung | C | **R/A** | I | C |
| Breaking-Policy / Gates | C | C | — | **R/A** |
| Ampel/SLA konsumieren | I | I | **R** | I |
| Betriebsmodell & Deployment | **R** | C | — | **A** |

---

## 8 — Entscheidungs-Gate: Betriebsmodell (vor dem Skalieren)

Unabhängig vom Modus zu klären (HANDOVER N3):

- **Berater-lokal** — SQLite, NoAuth, `127.0.0.1`, kein Dauerbetrieb. Ideal für die **Lite-/PoC-Phase**.
- **Container beim Kunden** — OIDC, HANA-Result-Store, ≥2 Worker, Updates/Secrets/IdP-Zuständigkeit. Voraussetzung für **Full im Regelbetrieb**.

Beide laufen aus **demselben Code** (Auth-/Store-Abstraktion, kein Code-Zweig). Scheduling ist extern (Cron/Task-Chain → CLI); die API triggert nur ad hoc.

### Offene Punkte mit Modus-Bezug

| Punkt | Betrifft | Vorgehen |
|---|---|---|
| Observability-Baselines (Rolling Volume) | Full (und Lite-`volume:rolling`) | Warm-up über N Läufe; Fallback `LOAD_TS` + Row-Count, bis Katalog-Lastmetadaten geklärt (O2) |
| Scheduling regelmäßiger Läufe | beide | Cron/Task-Chain ruft CLI — für Dauer-Verbindlichkeit nötig |
| Spaltenebene in Coverage | beide | Objektebene liefert sofort; Spaltenebene nach Parser-Fix (O3) |
