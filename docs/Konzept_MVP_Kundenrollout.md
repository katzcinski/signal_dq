# Konzept — MVP-Zuschnitt & Stufenrollout beim Kunden („Erster Wurf")

**Adressat:** Beratung, Plattform-Team, Entwicklung · **Stand:** 2026-08-25 · **Status:** Konzept (zur Umsetzung)

**Zweck:** Signal soll beim Kunden in Betrieb gehen, bevor der volle Funktionsumfang
getestet und abgenommen ist. Dieses Dokument schneidet den **ersten
auslieferbaren Funktionskern (Welle 0)**, definiert, **was abgeschaltet** startet,
und beschreibt den **Mechanismus**, mit dem die restlichen Module im Laufe der
Tests **ohne Re-Deployment** stufenweise freigeschaltet werden.

> Verwandte Dokumente: [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md)
> (Lite/Full-Prozess — Welle 0 ist der Lite-Pfad), [`Tooldokumentation.md`](Tooldokumentation.md)
> (implementierter Stand), [`OPEN_TASKS.md`](OPEN_TASKS.md) (Backlog; relevante
> Abhängigkeiten: C `HanaResultStore`, N Scheduling Phase 2, K O-Spikes).

---

## 0 — Kernaussage

**Ein Codestand, ein Deployment, vier Wellen.** Es gibt keinen „MVP-Branch" und
keine abgespeckte Distribution: Der Kunde bekommt den vollen Codestand; sichtbar
und aufrufbar ist nur, was die Konfiguration freischaltet. Freischalten heißt
Config-Änderung + Neustart — kein neuer Build, keine Migration des Vorgehens.

Der erste Wurf (Welle 0) ist der **kleinste geschlossene Wertkreislauf**:

```
Extrakt ──▶ Contract Lite ──▶ Kompilierte DQ-Checks ──▶ Run (HANA) ──▶ Ampel/Coverage
(Inventar)  (Checkliste,       (deterministisch,          (manuell/Cron)   (Cockpit)
             1 Klick certify)   read-only SQL)
```

Alles andere — Full-Governance, Alarmierung, Vorschlags-Miner, Quarantäne,
Healing, Enforcement — ist **nachgelagerte Reaktion oder Zeremonie** auf diesem
Kreislauf und startet abgeschaltet.

**Nicht verhandelbar:** Die Sicherheits-Gates (G1–G8, S5) und die PII-/
Diagnostics-Schalter sind **kein Teil des Stufenmodells**. Sie gelten in jeder
Welle unverändert scharf; das Modul-Gating ist eine Sichtbarkeits-/Prozess-Achse,
keine Sicherheitsachse.

---

## 1 — Scope-Entscheidung Welle 0 (der erste Wurf)

### 1.1 Was drin ist — und warum genau das

Die Frage „DQ-Checks + Data Contracts Lite — was noch?" beantwortet die
Wertschöpfungskette: Jedes Welle-0-Modul ist entweder **Voraussetzung** für
Checks/Contracts oder macht deren **Ergebnis sichtbar**. Was keins von beidem
tut, fliegt raus.

| # | Baustein | Begründung | Screens / API |
|---|---|---|---|
| 1 | **Extraktion Inventar + Lineage** | Ohne Objektliste kein Contract — der Seed speist sich aus dem Inventar | `POST /api/extract` · Extrakt-Alter im UI |
| 2 | **Data Contracts Lite** (`kind: internal_gate`) | Verbindlichkeit ohne Org-Change: Familien an/aus + Severity, „Speichern & aktivieren" (`certify`) | `/contracts` (nur Lite-Pane) · seed/validate/certify/compile |
| 3 | **DQ-Checks / Engine** (alle 7 Garantie-Familien) | Der Kern: `schema`, `keys`, `referential`, `not_null`, `completeness`, `freshness`, `volume` — deterministisch kompiliert, read-only | Runs via `POST /api/objects/{id}/run` + CLI |
| 4 | **Runs & Run-Detail** | Nachvollziehbarkeit jedes Laufs, Gating-Zustände sichtbar (G6) | `/runs/:id`, `/runs/compare` |
| 5 | **Cockpit-Statusgrid + Objektkatalog** | Das sichtbare Ergebnis: Status je Objekt × Familie, stale erkennbar | `/`, `/objects`, `/objects/:id` |
| 6 | **Coverage-/Lineage-Karte** (Objektebene) | Der Gesprächsanker beim Kunden: „dieses Objekt trägt heute null Garantien" | `/lineage` (`/coverage`) |
| 7 | **Compliance-Ampel** (lesend) | Wird die aktive Zusage gerade gehalten? `compliant/breached/unknown` entsteht ab dem ersten Lauf | `/compliance` |
| 8 | **Environments** (HANA-Verbindung) | Ohne echtes Environment keine echten Läufe; `ALLOW_MOCK_CONNECTION=false` beim Kunden | `/environments` |
| 9 | **Check-Library (API)** | Speist den Workbench-Builder; der eigene Screen `/library` ist optional | `/api/library` |
| 10 | **Auth + Settings-Basis** | OIDC beim Kunden (S5), Rollen `viewer/steward/owner/admin` | `/settings` (Admin) |
| 11 | **Incidents** (Breach-Episoden, lesend + Triage) | **Nachträglich in den Kern gezogen** — siehe Kasten unten | `/incidents`, `/api/incidents` |

Querschnitt, immer an (keine eigenen Module): SSE-Stream, Operations-/Progress-
Kanal (ADR-0007), Activity-Log, Metrics, RFC-7807-Fehler.

> **Warum Incidents doch in Welle 0 gehören.** Der erste Entwurf hatte sie in
> Welle 1 („Reaktionsschicht"). Der Code sagt etwas anderes: `pages/Cockpit.tsx`
> — der Welle-0-Hauptscreen — zieht `useIncidents()` für den AttentionPanel und
> die Incident-KPI. Eine Incident-Episode ist außerdem kein Zusatzworkflow,
> sondern die **Verdichtung der Breaches, die die Läufe ohnehin erzeugen**: kein
> externer Empfänger, keine zusätzliche Konfiguration, kein Schreibzugriff auf
> den Tenant. Was Welle 1 hinzufügt, ist die **Alarmierung** (Push an Kanäle),
> nicht der Datensatz. Incidents bleiben deshalb an, `notifications` nicht.

### 1.2 Was Welle 0 bewusst **nicht** enthält

| Abgeschaltet | Warum erst später | Welle |
|---|---|---|
| **Full-Modus** (SemVer, Approval, Breaking-Diff-UI, deprecate, ODCS/BDC-Export) | Braucht Ownership im Fachbereich; Lite liefert Verbindlichkeit ohne diese Zeremonie. Das G3-Sicherheitsnetz im `certify`-Pfad (409 bei Breaking auf zertifiziertem Stand) bleibt trotzdem aktiv | 2 |
| **Schedules** (interner Poller, Option E) | Welle 0 fährt Läufe manuell + extern per Cron/Task-Chain → CLI (ADR-0005). Der Poller ist ein Betriebsentscheid | 1 |
| **Notifications / Webhook / Digest** | Alarmierung setzt geklärte Empfänger + Allowlist voraus | 1 |
| **Profiling + Data-Diff** (Objekt-Profil, PK-Heuristik, `POST …/diff`) | Nützlich fürs Seeding, aber nicht Voraussetzung; Samples bleiben ohnehin PII-gegated | 1 |
| **Data-Load-Info** (Datasphere REST, Freshness-Zweitachse) | Braucht REST/OAuth-Anbindung an den Tenant; unabhängig vom Kernkreislauf | 1 |
| **Products** (Data-Product-Aggregat, ADR-0004) | Komposition über mehrere Objekte — erst sinnvoll, wenn Einzelobjekte stabil überwacht sind | 2 |
| **Proposals** (Miner, datengetriebene Vorschläge) | Baselines brauchen Lauf-Historie (Warm-up über N Läufe) | 2 |
| **Schema-Drift** (Contract vs. Quellstruktur, Shift-Left Tier 2; Screen + `…/drift`) | Eigenständiger Mehrwert, aber zweite Ausbaustufe. Der **Data-Diff** liegt technisch im Profiling-Router und kommt daher schon mit Welle 1 | 2 |
| **My Work** | Aggregiert Incidents/Proposals — ohne die beiden leer | 2 |
| **Quarantäne** | Aktiver Eingriff in den Datenfluss; Betriebsentscheid + TTL-Klärung | 3 |
| **Healing** (H1/H3-Workbench) | Schreibender Eingriff (Opt-in-Leiter); erst nach Vertrauensaufbau | 3 |
| **Enforcement** (Verdict-Materialisierung, Gate/Monitor, SQL-Bridge) | Schreibt in Signals Open-SQL-Schema; Kill-Switches existieren bereits, bleiben aus | 3 |
| **Monitoring-Hub** („make available for monitoring") | Braucht externes Reconcile-Skript + Hub-Space | 3 |
| **Inventory-Admin** (Meridian) | Beratungs-/Admin-Werkzeug, kein Kundenwert in W0 | optional |
| **Entropy-Integration** | Marktplatz unbestätigt (`entropy_marketplace_verified=false`) | — |

**Ausdrücklich NICHT abschaltbar** (Sicherheits-, keine Feature-Schalter):
Auth/AuthZ, S5-Bind-Policy, PII-Gate (G8), SQL-Freiheit (G1), Schema-Bindung
(G2), Gating-Sichtbarkeit (G6). Diese Liste gehört in den Code-Review-Check
jeder Gating-Änderung.

### 1.3 Personas & Prozess in Welle 0

Unverändert der Lite-Prozess aus `Betriebsmodi_Lite_und_Full.md` §3 (L1–L6):
Plattform/Beratung (`steward`/`owner`) extrahiert, seedet, setzt Lite-Garantien,
zertifiziert, löst Läufe aus; der Kunde konsumiert als `viewer` Ampel und
Coverage. Empfehlung unverändert: mit den **3–5 wichtigsten Konsum-Objekten**
starten, Coverage-Karte als Gesprächsanker.

---

## 2 — Freischalt-Mechanik: Modul-Gating (serverautoritativ)

Heute existieren bereits funktionale Kill-Switches (`scheduler_enabled`,
`enforcement_materialize_enabled`, `digest_enabled`, …, alle Default aus) — aber
**kein** Mechanismus, der Module als Ganzes aus API und UI nimmt. Der wird wie
folgt ergänzt. Prinzip identisch zur Rollen-Logik: **der Server ist autoritativ,
das Frontend spiegelt nur** (ein versteckter Nav-Eintrag ist ein Hinweis, kein
Gate).

### 2.1 Modulkatalog

Ein zentrales Registry-Modul `services/api/modules.py` definiert die Module und
die Wellen-Presets (eine Quelle, FE bekommt sie über die API):

```python
MODULES = {
    # Welle 0 — Kern, nicht gegatet: objects, runs, checks, extract, lineage,
    # contracts (Lite-Pfad), compliance, incidents, environments, library,
    # connector (Datasphere-Config für den Extrakt) + Querschnitt stream/
    # operations/activity/metrics
    "schedules":     1,   # routers/schedules.py (ohne Prefix: /api/schedules
                          # UND /api/objects/{id}/schedule)
    "notifications": 1,
    "profiling":     1,   # routers/profile.py — Profil UND Data-Diff
                          # (POST /api/objects/{id}/profile|diff)
    "data_loads":    1,   # routers/data_loads.py, Prefix /api/datasphere
    "contracts_full": 2,  # Full-Routen im geteilten contracts-Router
    "products":      2,
    "proposals":     2,
    "schema_drift":  2,   # routers/schema_drift.py UND
                          # GET /api/contracts/{product}/drift
    "my_work":       2,   # FE-only, kein eigener Router
    "quarantine":    3,
    "healing":       3,
    "enforcement":   3,   # umfasst monitoring (Hub/Reconcile-Endpunkte)
    "inventory_admin": None,  # optional, nur per modules_enabled_extra
    "integrations":    None,  # Entropy-Marktplatz — bleibt aus, solange
                              # entropy_marketplace_verified false ist
}
```

`None` = keiner Welle zugeordnet: nur über `modules_enabled_extra` erreichbar,
nie durch ein `rollout_wave`-Preset.

### 2.2 Konfiguration (`settings.py`)

```python
# Stufenrollout: Welle schaltet Modul-Presets frei; Overrides für Pilotierung.
rollout_wave: int = Field(default=0, ge=0, le=3)
modules_enabled_extra: list[str] = Field(default=[])   # einzeln vorziehen
modules_disabled: list[str] = Field(default=[])        # einzeln zurückhalten
```

Effektives Set = Kern ∪ {Module mit Welle ≤ `rollout_wave`} ∪ `extra` \ `disabled`.
Unbekannte Modulnamen ⇒ Startabbruch (fail-closed, kein Tippfehler-Silent-Pass).
Freischalten eines Moduls = `.env`-Änderung + Neustart. Interne Entwicklung und
CI fahren `ROLLOUT_WAVE=3`, damit die vollen Testsuiten unverändert laufen.

### 2.3 Serverseitiges Gate

Eine Dependency analog `require_roles(...)`:

```python
def require_module(name: str):        # services/api/deps.py
    def _dep() -> None:
        if name not in get_enabled_modules():
            raise HTTPException(404, f"Modul '{name}' ist nicht aktiviert.")
    return Depends(_dep)
```

- **Router-weite Module** (`proposals`, `schedules`, `quarantine`, `healing`,
  `enforcement`, `monitoring`, `products`, `schema_drift`, `notifications`,
  `profile`, `data_loads`): `require_module(...)` als
  Router-Dependency. Die Router bleiben **immer registriert** — das OpenAPI-Schema
  bleibt damit über alle Wellen stabil (kein G4-Drift, generierte FE-Typen
  unverändert); nur die Antwort ist 404 `problem+json`.
- **Contracts-Router (geteilt)**: Lite-Endpunkte (`GET`, `seed`, `validate`,
  `certify`, `compile`, `compiled`) sind Kern; Full-Endpunkte (`PUT` draft,
  `diff`, `version-diff`, `approve`, `deprecate`, `sla`, `export/odcs`,
  `export/bdc`) tragen `require_module("contracts_full")` pro Route.
  `GET /{product}/drift` liegt zwar im Contracts-Router, gehört aber zum Modul
  `schema_drift` — Gate nach Modul, nicht nach Router-Zugehörigkeit.
- **Kind-Beschränkung Welle 0/1**: Ohne `contracts_full` akzeptieren
  Schreibpfade nur `kind: internal_gate` (422 mit Verweis auf den Full-Rollout).
  Das ist konsistent mit ADR-0006 (Lite-Default folgt dem `kind`).
- 404 statt 403, damit „nicht aktiviert" nicht mit „keine Berechtigung"
  verwechselt wird; der `detail`-Text macht es explizit. Modul-Gate wirkt
  **zusätzlich** zu AuthN/AuthZ, ersetzt nie ein `require_roles`.

**G7-Wächter:** Das Gating lebt vollständig in `services/api/` und
`apps/cockpit/` — `packages/dq_core/` (`[ENGINE-FROZEN]`) wird nicht angefasst.

### 2.4 Feature-Endpoint & Frontend-Spiegel

- `GET /api/system/features` (authentifiziert, Kern): `{ wave, modules: [...] }`.
- FE: kleiner Query-Hook + Store (`useFeatures()`), analog `useRoleStore`.
  - `Sidebar.tsx`: Nav-Einträge filtern (`/schedules`, `/incidents`, `/quarantine`,
    `/healing`, `/enforcement`, `/proposals`, `/products`, `/schema-drift`,
    `/notifications`, `/my`, `/inventory-admin` nur bei aktivem Modul).
  - `App.tsx`: Routen deaktivierter Module rendern eine Seite
    „Modul nicht aktiviert" (i18n `de.ts`, mit Wellen-Hinweis) statt der Page —
    Deep-Links laufen nicht ins Leere und nicht in nackte 404-Fetches.
  - `ContractWorkbench`: ohne `contracts_full` kein Modus-Toggle, kein
    Approval-/Diff-Panel — nur der Lite-Pane (heute bereits der Default für
    `internal_gate`, ADR-0006).
- Der FE-Spiegel ist Komfort. Wer die API direkt anspricht, trifft das
  Server-Gate.

### 2.5 Abhängigkeits-Kontrakt der Kern-Screens

**Der eigentliche Aufwand liegt hier, nicht im Nav-Filter.** Mehrere
Welle-0-Screens ziehen heute Daten aus Modulen, die in Welle 0 aus sind. Ohne
Behandlung zeigt der Kunde auf einen Screen mit roten Fehlerbannern. Regel:

> Ein Kern-Screen rendert vollständig, wenn ein gegatetes Modul fehlt. Das
> abhängige Panel/Tab **entfällt still** — es erscheint kein Fehler, kein leerer
> Platzhalter, kein 404-Toast.

| Kern-Screen | Zugriff auf | Modul | Behandlung |
|---|---|---|---|
| `Cockpit.tsx` | `useIncidents()` (AttentionPanel, Incident-KPI) | `incidents` | entfällt — Incidents sind Kern (§1.1) |
| `ObjectDetail.tsx` | `ObjectProfilePanel`, `ObjectDiffPanel` | `profiling` | Panel + Tab `diff` weglassen |
| `ObjectDetail.tsx` | `SchedulePanel` | `schedules` | Panel + Tab `schedule` weglassen |
| `ObjectDetail.tsx` | `MinedProposalsCallout` | `proposals` | Callout weglassen |
| `ObjectDetail.tsx` | `useMonitoringConfig/Shares/RequestMonitoring` | `enforcement` | Monitoring-Aktion ausblenden |
| `ObjectDetail.tsx` | `useContractVersionDiff`, `ContractVersionDiffView` | `contracts_full` | Versions-Diff-Ansicht ausblenden |
| `ContractWorkbench` | `MinerSuggestions` | `proposals` | Vorschlagsblock weglassen |
| `ContractWorkbench` | `SchemaDriftBanner` (`…/drift`) | `schema_drift` | Banner weglassen |

`objectDetailTabs.ts` wird dafür von einer Konstanten zu einer Funktion über dem
Modulset (`objectDetailGroups(features)`), damit die Tab-Gruppen `history-ops`
und `structure-interface` nicht auf tote Tabs zeigen; die Deep-Link-Auflösung
(`resolveObjectDetailTabTarget`) fällt bei deaktiviertem Tab auf `checks` zurück.

### 2.6 Tests & CI

- `tests/api/test_module_gating.py`: (a) Welle 0 ⇒ gegatete Endpunkte 404,
  Kern-Endpunkte unverändert; (b) Welle 3 ⇒ alles erreichbar; (c) Overrides
  greifen; (d) unbekanntes Modul ⇒ Startfehler; (e) Full-Endpunkte des
  Contracts-Routers einzeln geprüft; (f) `certify`-G3-Netz auch in Welle 0.
- Vitest: `navForRole × features`-Matrix; „Modul nicht aktiviert"-Seite; **je
  ein Welle-0-Render von Cockpit, ObjectDetail und Workbench** mit leerem
  Modulset — kein Fehlerbanner, keine toten Tabs (§2.5).
- Bestehende Suiten laufen unter `ROLLOUT_WAVE=3` unverändert — das Gating darf
  keine bestehende Testerwartung ändern.

Geschätzter Umfang: Backend klein (1 Registry, 1 Dependency, ~11
Router-Annotationen + 8 Einzelrouten, 1 Endpoint). Der Schwerpunkt liegt im
Frontend — nicht der Nav-Filter, sondern die acht Panel-Guards aus §2.5 und die
modulabhängigen ObjectDetail-Tabs. Keine Migration, keine Engine-Änderung.

---

## 3 — Rollout-Plan: die vier Wellen

| Welle | Motto | Neu freigeschaltet | Vorbedingung für die Freischaltung |
|---|---|---|---|
| **0 — Messen & sichtbar machen** | „Was garantieren wir heute messbar?" | Kern (§1.1) | Deployment steht (§4), HANA-User read-only, 3–5 Objekte ausgewählt |
| **1 — Betrieb & Alarmierung** | Vom Klick zum Dauerlauf | `schedules`, `notifications`, `profiling`, `data_loads` | Scheduling-Entscheid (Cron/Task-Chain vs. interner Poller, ADR-0005); Webhook-Ziel + Allowlist; Empfänger geklärt |
| **2 — Governance & Full-Contracts** | Fachbereich übernimmt die Zusage | `contracts_full`, `products`, `proposals`, `schema_drift`, `my_work` | Ownership-Shift `platform → product` eingeleitet; Rollen im IdP gemappt (O4); genug Lauf-Historie für Baselines |
| **3 — Aktive Eingriffe** | Von Beobachtung zu Durchsetzung | `quarantine`, `healing`, `enforcement` (+ `monitoring`) | Expliziter Betriebsentscheid des Kunden; Signal-Schema im Tenant (ADR-0002-Amendment); TTL-/Retention-Klärung; die jeweiligen funktionalen Kill-Switches werden **zusätzlich** einzeln gesetzt |

Grundsätze:

- **Eine Welle pro Freischaltung, nie „alles auf einmal".** Zwischen den Wellen
  liegt jeweils eine Test-/Beobachtungsphase auf Kundendaten; einzelne Module
  lassen sich über `modules_enabled_extra` als Pilot vorziehen (z. B.
  `profiling` schon in Welle 0, wenn das Seeding an schwachen Inventardaten
  hängt).
- **Welle 3 hat doppelte Schlösser:** Modul-Gate (Sichtbarkeit) **und** die
  bestehenden funktionalen Kill-Switches (`enforcement_materialize_enabled`,
  `enforcement_sql_bridge_enabled`, `datasphere_allow_trigger`, …). Beide müssen
  bewusst gesetzt werden — das Modul-Gate ersetzt keinen davon.
- **Rückweg:** Jede Welle ist per Config reversibel (Modul wieder raus =
  wieder 404/ausgeblendet). Persistierte Daten (Runs, Incidents) bleiben liegen
  und tauchen bei Re-Aktivierung wieder auf — kein Datenverlust durch Toggling.

---

## 4 — Betriebsmodell Welle 0 beim Kunden

Entscheid nach `Betriebsmodi_Lite_und_Full.md` §8; für einen **Dauerbetrieb beim
Kunden** (und das ist der Sinn des ersten Wurfs) gilt:

| Aspekt | Welle-0-Setzung | Anmerkung |
|---|---|---|
| Deployment | **Container beim Kunden** | Berater-lokal (NoAuth/Loopback) bleibt das PoC-/Demo-Setup, nicht der Kundenbetrieb |
| Auth | `AUTH_MODE=oidc`, Kunden-IdP, Role-Mapping (`oidc_role_mapping`) | S5 erzwingt das ohnehin bei Nicht-Loopback-Bind; Mapping-Abstimmung ist Teil des Onboardings (O4) |
| Result-Store | `STORE_BACKEND=sqlite` + Volume/Backup | `HanaStore` ist Stub (`OPEN_TASKS` C2); SQLite reicht für die Pilotlast. HANA-Store ist Skalierungs-, kein Welle-0-Thema |
| DB-Zugriff | Technischer Space-User, **read-only** (ADR-0002) | Signal schreibt in Welle 0–2 nichts in den Tenant |
| Mock | `ALLOW_MOCK_CONNECTION=false` | Kein stiller Fail-Open (S-13) |
| Scheduling | Extern: Cron/Task-Chain → `cli/dq_check_runner.py` | Interner Poller erst mit Welle 1 (falls gewünscht) |
| PII/Diagnostics | `allow_local_diagnostics=false`, `allow_profile_samples=false` | Default beibehalten; Opt-in ist ein eigener, dokumentierter Entscheid |
| Rollout | `ROLLOUT_WAVE=0` | plus ggf. `MODULES_ENABLED_EXTRA` für Piloten |
| Contracts-Git | `git_remote` auf Kunden-Repo | `contracts/` bleibt Source of Truth, Author = Principal |

---

## 5 — Akzeptanzkriterien

**Gating-Baustein (Entwicklung, vor Auslieferung):**

1. Mit `ROLLOUT_WAVE=0` liefern alle gegateten Endpunkte 404 `problem+json`;
   Kern-Endpunkte und alle Gates/Suiten verhalten sich unverändert.
2. `GET /api/system/features` spiegelt exakt das effektive Modulset; Sidebar
   und Routen folgen ihm; Deep-Links auf deaktivierte Module zeigen die
   Hinweis-Seite.
3. Cockpit, ObjectDetail und Contract-Workbench rendern unter `ROLLOUT_WAVE=0`
   ohne Fehlerbanner und ohne toten Tab (§2.5) — mit Test belegt.
4. Contracts-Schreibpfade akzeptieren ohne `contracts_full` nur
   `internal_gate`; `certify` behält das G3-Sicherheitsnetz.
5. CI grün unter `ROLLOUT_WAVE=3` (Vollumfang) **und** ein dedizierter
   Welle-0-Gating-Testlauf.

**Welle 0 beim Kunden (erste 2–4 Wochen):**

1. Inventar/Lineage des Ziel-Space extrahiert, Extrakt-Alter < 7 Tage.
2. 3–5 Konsum-Objekte haben zertifizierte Lite-Contracts (≥ je 1 kompilierbare
   Garantie; Fokus `freshness`, `not_null`, `keys`, `schema closed`).
3. Regelmäßige Läufe (extern geplant) schreiben in den Result-Store; Cockpit-
   Ampel und Coverage-Karte sind für Kunden-`viewer` erreichbar und aktuell.
4. Mindestens ein realer Breach wurde über die Ampel erkannt und nachvollzogen
   (Run-Detail) — der Wertnachweis, der Welle 1 (Alarmierung) begründet.

---

## 6 — Risiken & offene Punkte

| Risiko / Punkt | Einordnung | Umgang |
|---|---|---|
| Kunde fragt in Welle 0 nach abgeschalteten Screens („was ist Quarantäne?") | Erwartungsmanagement | Hinweis-Seite nennt Welle + Zweck des Moduls; Rollout-Plan ist Teil des Kundenonboardings |
| SQLite unter Mehrbenutzer-/Dauerlast | mittel | Pilotlast ist klein (wenige Objekte, geplante Läufe); `HanaStore` (C2) parallel zur Welle 1/2 entwickeln |
| OIDC-/IdP-Abstimmung verzögert Deployment | häufig in der Praxis | Role-Mapping früh anfordern; bis dahin berater-lokal (Loopback) als Brücke, nie NoAuth im Netz (S5) |
| OpenAPI/G4: gegatete Routen erscheinen im Schema | akzeptiert | Bewusst so (stabile Typen über Wellen); 404-Semantik dokumentieren |
| **Kern-Screens hängen an gegateten Modulen** (Cockpit→Incidents, ObjectDetail→5 Module, Workbench→2) | **der Hauptaufwand**, beim ersten Entwurf übersehen | §2.5 als verbindlicher Kontrakt + Welle-0-Rendertests je Kern-Screen; Incidents in den Kern gezogen |
| Versuchung, Gates „mal eben" mit abzuschalten | rot | §1.2-Verbotsliste; Review-Checkliste: Modul-Gating berührt nie Auth/PII/G-Gates |
| Baselines (Proposals, `volume: rolling`) brauchen Warm-up | bekannt (`OPEN_TASKS` E/K-O2) | Welle-2-Vorbedingung „genug Lauf-Historie" ernst nehmen |

---

## 7 — Umsetzungsreihenfolge (Vorschlag)

Backlog-Verankerung: [`OPEN_TASKS.md`](OPEN_TASKS.md) Abschnitt **T** (T1–T5).

1. **T1** — `modules.py` (Registry + Wellen-Presets) + Settings-Erweiterung + Startvalidierung.
2. **T2** — `require_module` in `deps.py`; Router-Annotationen (router-weit + Contracts-Routen einzeln); Kind-Beschränkung im Contracts-Schreibpfad.
3. **T3a** — `GET /api/system/features` (+ Schema unter `services/api/schemas/`).
4. **T3b** — FE: `useFeatures`-Hook, Sidebar-Filter, „Modul nicht aktiviert"-Seite, `de.ts`-Strings — **und die Panel-Guards aus §2.5** (der größere Teil).
5. **T4** — Tests (`tests/api/test_module_gating.py`, Vitest-Matrix); CI-Lauf Welle 0 + Welle 3.
6. **T5** — Doku: ENV-Referenz in `Tooldokumentation.md` §6 ergänzen; Kunden-Runbook Welle 0 (Deployment-Checkliste aus §4).

Schritte 1–5 sind der auslieferbare Gating-Baustein; erst danach ist „Welle 0
beim Kunden" eine Konfiguration statt einer Absprache.
