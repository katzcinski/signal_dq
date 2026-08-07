# Übergabemodelle & Lizenz — Dienstleistung vs. Softwareüberlassung

**Zweck:** Entscheidungsgrundlage dafür, *wie* Signal an einen Kunden übergeben wird —
und ab wann aus einem **Beratungs-Delivery** eine **Softwareüberlassung** wird, mit den
rechtlichen/kommerziellen Pflichten, die das auslöst. Gesprächsgrundlage für Justiziar
+ Steuerberater.
**Status:** Strategie-/Entscheidungsdokument. **Kein Rechtsrat** — die konkrete
Vertrags-, Lizenz- und Steuergestaltung gehört vor qualifizierte Beratung.
**Datum:** 2026-06-23
**Kontext:** Signal wird als **Beratungs-Delivery-Tool** eingesetzt (nicht als
lizenziertes Produkt). Dieses Dokument hält fest, wie das so bleibt — oder bewusst
nicht.

---

## 1 — Die eigentliche Schwelle

Technisch ist Signal **immer** Software (auch im Lite-/Berater-Modus). Geschäftlich
zählt eine andere Unterscheidung:

> **Erbringst du eine Dienstleistung, oder überlässt du Software?**

Die Schwelle ist **nicht** der Code, sondern die **Betriebs-Autonomie**: In dem
Moment, in dem der Kunde eine **eigenständig betreibbare Signal-Instanz** in der Hand
hält und sie **ohne dich** fährt, kippst du von Dienstleistung in
**Softwareüberlassung**. Man rutscht da nicht „aus Versehen” hinein — man entscheidet
es (oder versäumt, es zu entscheiden).

---

## 2 — Was den Besitzer wechselt (sauber vs. heikel)

| Was übergeben wird | Einordnung |
|---|---|
| **Artefakte** — `contracts/*.yaml`, `products/*.yaml`, CI-Config, Cron-/Runner-Skripte | **Eindeutig Dienstleistungs-Output.** Gehört dem Kunden ohnehin (Git = Wahrheit). Kein „Produkt”. |
| **Lauffähige Instanz** — Cockpit + Engine, die der Kunde selbst startet/betreibt | **Softwareüberlassung.** Genau dieser Schritt löst die Pflichten in §4 aus. |

Der Artefakt-Teil ist immer unproblematisch. Die Frage stellt sich **nur** an der
lauffähigen Instanz.

---

## 3 — Die drei Übergabemodelle

| Modell | „Software” überlassen? | Wann passend |
|---|---|---|
| **A) Managed Service** — *du* betreibst es (Kunden-Tenant oder dein Hosting) | **Nein** — keine Überlassung, reine Dienstleistung | Wiederkehrender Betrieb gewünscht; Entropy-Posture sauber halten |
| **B) Kunde betreibt, aus *seiner* Quelle/Infra deployed** — du konfigurierst, lieferst **kein** fertiges Binary/Bundle | **Graubereich** — primär Dienstleistung, aber §4-Punkte müssen geregelt sein | Kunde will Autonomie, du willst kein Produktgeschäft |
| **C) Software lizenzieren** — explizit als Produkt | **Ja** — volles Produkt | Nur als *bewusste* Geschäftsmodell-Entscheidung |

**Empfehlung (Delivery-Modell, saubere Entropy-Beziehung):** **A** wann immer möglich,
sonst **B** mit vollständig geregelter §4-Checkliste. **C** nur, wenn man bewusst ins
Produktgeschäft will — nicht als Nebenprodukt einer netten Übergabe.

Technischer Anker: Der Umschalter Lite→Kunde ist reine Konfiguration
(`services/api/settings.py`): `store_backend=hana`, `auth_mode=oidc`, `bind_host`
non-loopback **nur mit** Auth (S5), `allow_mock_connection=false` (S-13),
`environments.yml` mit Secret-Referenzen. Bei **A** läuft das in deiner/der
betreuten Umgebung; bei **B/C** in der des Kunden.

---

## 3a — Variante A1: Managed Service mit Betriebs-Split (+ Hybrid-Executor)

Die in der Praxis häufigste Ausprägung von **Modell A**: *Ihr* betreibt Signal,
*der Kunde* betreibt die Lösung **fachlich**. Der Trick ist, dass „betreiben” zwei
Dinge meint — und die Trennung ist genau der `owned_by`-Split, den Signal ohnehin
vorsieht.

| „Betrieb” | Wer | Was konkret |
|---|---|---|
| **Technischer Betrieb** (Hosting/Ops) | **Beratung** | Deployment, Updates/Patches, `store_backend=hana`, OIDC, Secrets, Scheduler-Anbindung, Store |
| **Fachlicher Betrieb** (Governance/Inhalt) | **Kunde** | Contracts authoren/pflegen (Workbench), Garantien als *seine* Zusage, auf Incidents/Ampel reagieren, Cockpit nutzen |

Der Kunde loggt sich per **OIDC** in das gehostete Cockpit ein (Rollen
`viewer\|steward\|owner\|admin`) und macht seine Governance-Arbeit; die Beratung
hält die Plattform am Laufen. Multi-Tenant möglich: ein Hosting, je Kunde ein
Tenant (OIDC + eigene `environments.yml`).

**Einordnung:** Bleibt **Dienstleistung** — es wird *keine* betreibbare Instanz
überlassen, sondern selbst betrieben und nur fachlicher Zugang gegeben. Die
Softwareüberlassungs-Schwelle (§1) wird gar nicht erreicht.

### Zwei Hürden, die A1 entscheiden (Prüfpunkte)

1. **Konnektivität & Security zur produktiven HANA — meist *der* Knackpunkt.**
   Läuft Signal bei der Beratung, muss der Executor von dort die **produktive
   HANA/Datasphere des Kunden lesen**. Das Security-Team muss einem extern
   gehosteten System Zugriff auf produktive ERP-Daten erlauben.
   - *Argumente:* lesend, PII-Gate (G8), Rohzeilen verlassen HANA nie ohne Freigabe,
     Ergebnisse getrennt.
   - *Technisch:* VPN / Private Link / IP-Allowlisted-Tunnel.
   - **Hybrid-Executor (Standard-Fallback):** der framework-freie Runner
     (`cli/dq_check_runner.py`) läuft **im Netz des Kunden** nahe der HANA, nur die
     **Ergebnisse** fließen in das gehostete Cockpit/Store. HANA-Zugriff bleibt in
     der Kundenzone — oft genau das, was die Security durchwinkt.
2. **Datenresidenz der Ergebnisse.** Hostet die Beratung, liegt der Result-Store
   (DQ-Resultate, ggf. Diagnose-Zeilen) bei ihr. Die Data-Governance des Kunden
   verlangt evtl. Verbleib *im* Kunden-Tenant → klären, ob Store bei der Beratung
   zulässig ist, sonst Hybrid (Store/Runner in Kundenzone).

> **Leitsatz A1:** Die Frage ist nie „können wir hosten”, sondern „lässt die
> Security des Kunden den HANA-Zugriff von außen zu”. Fällt die Antwort „nein”, ist
> der Hybrid-Executor die Standard-Antwort.

**Kommerziell:** wiederkehrendes Managed-Service-Entgelt (Betrieb) + Rollout-/
Härtungs-Engagements obendrauf — hebt die Marge des Tools, ohne ins Lizenzgeschäft
zu kippen.

---

## 4 — Checkliste: vor einer Selbstbetriebs-Übergabe (B/C) zu regeln

1. **Lizenz / Nutzungsrechte.** Nutzungsrecht an Signals eigenem Code einräumen.
   Vorab klären: **Wem gehört Signal-IP?** (Teile aus früheren Kundenprojekten können
   *geteiltes* IP sein.)
2. **OSS-Durchreichung + SAP-Stolperstein.** Signal hängt an GX, FastAPI, `hdbcli`
   u. a. → deren Lizenzen werden mitgeliefert. **`hdbcli` ist der proprietäre
   SAP-HANA-Client und darf nicht einfach redistribuiert werden.** Sauber: der Kunde
   zieht den Treiber unter *seiner* SAP-Lizenz (als Datasphere-Kunde vorhanden) —
   **nicht** im Bundle mitliefern.
3. **Gewährleistung / Haftung — der scharfe Punkt.** Software läuft **lesend gegen
   produktive ERP-Daten**, und der Kunde *vertraut* der grünen Ampel. Risiken: falscher
   Check, übersehener Breach, Last auf der Quelle. → **Haftungs-Cap** + explizite
   „as-is / keine Eignungszusage”-Klausel.
4. **Support / Wartung.** Selbstbetrieb erzeugt Erwartung auf Patches, Security-Fixes,
   Updates = **Produkt-Support-Pflicht**. Entweder bezahlt zusagen oder explizit
   ausschließen.
5. **Entropy-Kanalkonflikt.** Im Delivery-Modell **nicht** vorhanden. Als
   *überlassene/lizenzierte* Software rückt Signal näher an „Produkt” → potenziell
   Wettbewerber in Entropys Wahrnehmung. Die „Backend hinter eurem Schaufenster”-Story
   verträgt das nur bei bewusst kleinem Zuschnitt.
6. **Steuer / Bilanz.** Softwareüberlassung vs. Dienstleistung wird unterschiedlich
   behandelt (USt, ggf. grenzüberschreitend Quellensteuer). Früh mit Steuerberater
   klären.

---

## 5 — Kernsatz

> Signal wird nicht „aus Versehen” zur Software. Es wird zur **überlassenen Software
> in dem Moment, in dem du die Betriebs-Autonomie mitgibst.** Entscheide aktiv, ob du
> das willst (Modell A/B/C), statt hineinzurutschen — und papere bei B/C die
> §4-Checkliste *vor* der Übergabe.

---

## 6 — Anker-Referenzen

| Baustein | Datei / Stelle |
|---|---|
| Lite↔Kunde-Umschalter (Modi) | `services/api/settings.py` (`store_backend`, `auth_mode`, `bind_host`, `allow_mock_connection`) |
| Secret-Referenzen / Connection-Config | `services/api/routers/environments.py`; `environments.yml` |
| SAP-Client-Abhängigkeit (`hdbcli`) | `packages/dq_core/pyproject.toml` → optional-dependency `hana` |
| Read-only / PII-Posture (Haftungs-Argument) | `README.md` §Sicherheits-Leitplanken (G8) |
| Betriebsmodi Lite/Full | `docs/Betriebsmodi_Lite_und_Full.md` |
| Entropy-Kanalkonflikt-Kontext | `docs/Zusatz_EntropyData_Integration_und_Defensibility.md` §4, §6d |
