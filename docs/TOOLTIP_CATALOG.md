# Tooltip-Katalog für Signal Cockpit

**Status:** Vorschlag, aus Code und Doku abgeleitet  
**Ziel:** Eine kuratierte Sammlung möglicher Tooltip-Texte für Hover- und Fokus-Zustände im Cockpit. Die Texte sind als UX-Copy gedacht, nicht als bereits implementierte Funktion.

## Annahmen

- Die UI-Sprache bleibt Deutsch, weil `apps/cockpit/src/i18n/de.ts` die aktuelle Produktcopy führt.
- Tooltips erklären vor allem Fachbegriffe, Konsequenzen und deaktivierte Aktionen. Sie ersetzen keine sichtbaren Labels.
- Bestehende native `title`-Attribute können kurzfristig weitergenutzt werden; für neue Tooltips sollte ein echtes Tooltip-Primitive später auch Fokus, Touch und `aria-describedby` unterstützen.
- "Hover up" bedeutet: Tooltip öffnet bevorzugt oberhalb des Auslösers, fällt bei Platzmangel aber seitlich oder nach unten zurück.

## Quellen

- `CONTEXT.md`: zentrale Begriffe wie Data Product, Data Contract, Internal Gate, boundary, kind, Freshness, Load-Lag und Reconciliation.
- `docs/Konzept_DQ_Cockpit_UIUX.md`: Rollenmodell, objektzentrierte IA, Farbsemantik, Mono-Konvention und UI-Regeln.
- `docs/Betriebsmodi_Lite_und_Full.md`: Lite/Full-Prozess, Lifecycle, Compliance, Coverage und Gates.
- `docs/ADR-0001_Quality-Gates_vs_Contracts.md`: Trennung interner Quality Gates von Contracts.
- `apps/cockpit/src/i18n/de.ts`: vorhandene Labels, Status-Hints und erste `lineage.tooltips`.
- `packages/dq_core/library/check_library.json`: Check-Hilfetexte, Parameter-Hints und Beispiele.

## Copy-Regeln

- Kurz halten: 1 Satz, maximal 140 Zeichen für häufige UI-Elemente.
- Konsequenz nennen: "was bedeutet das für Compliance, SLA, Lauf oder Schreibrecht?"
- Keine Architekturromane im Tooltip. Längere Erklärungen gehören in Drawer, Empty-State oder Doku.
- Keine rein farbbasierten Erklärungen. Status immer mit Begriff oder Wirkung erklären.
- Für Artefakte (`run_id`, Objekt, Spalte, Expectation) technische Namen sichtbar lassen und nur die Bedeutung erklären.

## Grundbegriffe

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `tooltips.product` | "Data Product" Label, Produktkopf | Ein Data Product umfasst die Pipeline über alle Layer in einer Ownership, nicht nur ein einzelnes Objekt. |
| `tooltips.contract` | "Contract" Badge/Tab | Ein Contract beschreibt nur die konsumierbaren Grenzen eines Data Products und ist governance-relevant. |
| `tooltips.internalGate` | "Gate" Badge, interne Checks | Internes Quality Gate: Engineering-Signal ohne Gegenpartei, SemVer oder Governance-Compliance. |
| `tooltips.outputPort` | Output-Port Badge | Konsumierbare Produktgrenze; hier wird eine Zusage für andere Parteien verbindlich. |
| `tooltips.boundary` | Boundary/Art Filter | Klassifiziert, ob eine Garantie intern ist oder an einer Inbound-/Outbound-Grenze wirkt. |
| `tooltips.kind` | YAML-/Workbench-Art | On-disk Art des Artefakts: `internal_gate`, `consumer_contract` oder `provider_contract`. |
| `tooltips.freshness` | Freshness-Familie | Fachliche Frische: neuester Business-Zeitpunkt darf nicht älter als die Zusage sein. |
| `tooltips.loadLag` | Load-Lag-Signal | Technische Liveness der Pipeline; grüne Load-Lag heißt nicht automatisch frische Business-Daten. |
| `tooltips.reconciliation` | Reconciliation-Finding | Vergleicht Produkt-Intent mit Lineage-Realität und meldet Deltas wie Boundary-Leaks. |

## Rollen und Schreibrechte

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `role.tooltips.viewer` | Rollenmenü: Viewer | Lesen und prüfen; Schreibaktionen bleiben sichtbar, aber deaktiviert. |
| `role.tooltips.steward` | Rollenmenü: Steward | Darf Runs starten und platform-owned Gates oder Contracts pflegen. |
| `role.tooltips.owner` | Rollenmenü: Owner | Darf platform- und product-owned Artefakte in seinem Scope ändern. |
| `role.tooltips.admin` | Rollenmenü: Admin | Vollzugriff für Betrieb, Policy und Notfallkorrekturen. |
| `role.tooltips.readOnly` | Read-only Banner | Du siehst dieselbe Oberfläche; der Server blockiert Schreibaktionen für diese Rolle. |
| `role.tooltips.noWriteAction` | Deaktivierte Aktion | Keine Schreibberechtigung in dieser Rolle oder für diese Ownership. |
| `role.tooltips.ownerLockPlatform` | Ownership-Tag "Platform" | Platform-owned: Änderung liegt beim Plattform-/Beratungsteam. |
| `role.tooltips.ownerLockProduct` | Ownership-Tag "Produkt" | Product-owned: Änderung erfordert Product Owner oder passenden Owner-Scope. |

## Status, Compliance und Gating

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `status.tooltips.pass` | StatusPill `pass` | Letzter ausgeführter Check hat die Erwartung erfüllt. |
| `status.tooltips.warn` | StatusPill `warn` | Erwartung verletzt, aber als Warnung eingestuft; prüfen, bevor daraus ein Breach wird. |
| `status.tooltips.fail` | StatusPill `fail` | Erwartung verletzt; je nach Artefakt wird daraus ein Incident oder Compliance-Breach. |
| `status.tooltips.critical` | StatusPill `critical` | Kritische Verletzung; priorisiert triagieren und Downstream-Wirkung prüfen. |
| `stateHint.skipped_stale` | StatePill | Check übersprungen: Datenstand veraltet; kein Pass/Fail-Ergebnis. |
| `stateHint.skipped_dependency` | StatePill | Check übersprungen: vorausgesetzter Gate-Check ist nicht grün. |
| `stateHint.downgraded` | StatePill | Schweregrad wurde durch Gating reduziert; Ergebnis ist sichtbar, aber nicht voll gewichtet. |
| `stateHint.error` | StatePill | Technischer Ausführungsfehler; kein fachliches Pass/Fail-Ergebnis. |
| `compliance.tooltips.compliant` | Compliance-Pill | Aktive Contract-Zusagen wurden im letzten relevanten Lauf eingehalten. |
| `compliance.tooltips.breached` | Compliance-Pill | Mindestens eine verbindliche Contract-Zusage ist verletzt und governance-relevant. |
| `compliance.tooltips.unknown` | Compliance-Pill | Noch kein belastbarer Lauf für diese aktive Zusage vorhanden. |

## Coverage und Lineage

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `lineage.tooltips.covered` | Coverage-Flag `covered` | Aktives Gate oder Contract vorhanden, Checks laufen und der letzte Status ist grün. |
| `lineage.tooltips.partial` | Coverage-Flag `partial` | Gate oder Contract vorhanden, aber Checks fehlen, liefen noch nicht oder sind nicht grün. |
| `lineage.tooltips.gap` | Coverage-Flag `gap` | Kein aktives Gate und kein aktiver Contract für dieses Objekt. |
| `lineage.tooltips.outOfScope` | Coverage-Flag `out_of_scope` | Externes oder unaufgelöstes Objekt; keine Signal-Coverage erwartet. |
| `lineage.tooltips.gateSignal` | Gate-Signal Marker | Interner DQ-Check: operatives Engineering-Signal ohne Governance-Compliance-Folge. |
| `lineage.tooltips.governanceBreach` | Governance-Breach Marker | Verbindlicher Contract-Check: Verletzung wirkt auf Compliance, SLA und Incident-Routing. |
| `lineage.tooltips.extractAge` | Extrakt-Alter | Alter des Inventar-/Lineage-Snapshots; veraltete Extrakte können Coverage verzerren. |
| `lineage.tooltips.promote` | "Als Contract festschreiben" | Kopiert interne Gate-Garantien in einen Boundary-Contract-Entwurf. |
| `lineage.tooltips.focusPath` | Root-Cause/Focus-Modus | Hebt Upstream- und Downstream-Pfade um das ausgewählte Objekt hervor. |

## Workbench und Lifecycle

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `workbench.tooltips.tabInternal` | Tab "Interne DQ-Checks" | Gates sichern interne Qualität und können ohne Approval-Zeremonie geändert werden. |
| `workbench.tooltips.tabContract` | Tab "Contracts" | Contracts sind verbindliche Zusagen an Konsumenten oder Quellen. |
| `workbench.tooltips.noSql` | "Kein SQL" Hinweis | Garantien bleiben semantisch; ausführbares SQL entsteht erst im Compiler. |
| `workbench.tooltips.liteMode` | Modus "Lite" | Schneller Einstieg: gleiche Gates, aber ohne SemVer- und Approval-Zeremonie. |
| `workbench.tooltips.fullMode` | Modus "Full" | Governter Pfad mit Versionierung, Approval und Breaking-Schutz. |
| `workbench.tooltips.draft` | Lifecycle Step Draft | Entwurf ist editierbar und noch nicht verbindlich aktiv. |
| `workbench.tooltips.active` | Lifecycle Step Active | Aktive Version erzeugt Checks und zählt für Compliance und Coverage. |
| `workbench.tooltips.deprecated` | Lifecycle Step Deprecated | Historisch sichtbar, aber nicht mehr für neue Runs maßgeblich. |
| `workbench.tooltips.breaking` | Breaking Chip | Diese Änderung verengt oder entfernt Zusagen und erfordert im Full-Modus einen Major-Bump. |
| `workbench.tooltips.breakingGate` | Breaking-Hinweis bei Gate | An einem internen Gate informativ; verbindlich wird es erst nach Promotion zum Contract. |
| `workbench.tooltips.release` | "Neue Version freigeben" | Aktiviert den Contract verbindlich und schreibt genau eine nachvollziehbare Version. |
| `workbench.tooltips.deprecate` | "Außer Betrieb nehmen" | Stoppt neue Nutzung des Contracts; Historie und alte Läufe bleiben sichtbar. |
| `workbench.tooltips.revert` | Revert-Aktion | Setzt generierte Checks auf die vorige Git-Version zurück. Handgepflegte Konflikte bleiben geschützt. |
| `workbench.tooltips.bdcExport` | BDC-/ODCS-Export | Exportiert nur Boundary-Contracts für Kataloge; interne Gates bleiben intern. |

## Garantie-Familien

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `workbench.familyTooltips.schema` | Garantie "Schema" | Erwartete Spalten und optional geschlossener Vertrag über die Struktur. |
| `workbench.familyTooltips.keys` | Garantie "Keys" | Schlüssel müssen eindeutig sein; Duplikate brechen strukturelle Verlässlichkeit. |
| `workbench.familyTooltips.referential` | Garantie "Referentielle Integrität" | Fact-Zeilen müssen auf gültige Parent-/Dimensionseinträge verweisen. |
| `workbench.familyTooltips.freshness` | Garantie "Freshness" | Business-Zeitstempel darf nur innerhalb des zugesagten Alters liegen. |
| `workbench.familyTooltips.volume` | Garantie "Volume" | Zeilenanzahl muss Mindestwert oder Baseline-Korridor erfüllen. |
| `workbench.familyTooltips.completeness` | Garantie "Vollständigkeit" | NULL-Quote einer Spalte darf die definierte Grenze nicht überschreiten. |
| `workbench.familyTooltips.notNull` | Garantie "Not-Null" | Pflichtspalte darf keine NULL-Werte enthalten. |

## Check Library und Builder

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `library.tooltips.familyObservability` | Familie "observability" | Misst Ankunft, Volumen und technische Verlässlichkeit der Daten. |
| `library.tooltips.familyQuality` | Familie "quality" | Prüft fachliche Korrektheit, Vollständigkeit und Konsistenz. |
| `library.tooltips.gatingStandard` | Gating `standard` | Läuft regulär und zählt direkt in den Check-Status. |
| `library.tooltips.gatingGate` | Gating `gate` | Billiger Vorcheck, der teurere oder abhängige Checks stoppen kann. |
| `library.tooltips.gatingExpensive` | Gating `expensive` | Teurer Check; sollte durch vorgelagerte Gates geschützt werden. |
| `library.tooltips.expect` | Expectation-Feld | Erwartung an den numerischen Ist-Wert, z. B. `= 0`, `> 0` oder `BETWEEN`. |
| `library.tooltips.severity` | Severity-Auswahl | Steuert, ob eine Verletzung Warnung, Fail oder kritischer Breach wird. |
| `library.tooltips.paramIdentifier` | Parameter Typ `identifier` | Objekt-, Spalten- oder Tabellennamen werden validiert und sicher quoted. |
| `library.tooltips.paramValueList` | Parameter Typ `value_list` | Jeder Eintrag wird einzeln escaped und als erlaubte Wertemenge gebunden. |
| `library.tooltips.paramRegex` | Parameter Typ `regex` | HANA-kompatibles Muster für Formatprüfungen, z. B. Codes oder IDs. |
| `library.tooltips.sqlPreview` | SQL-Vorschau | Generiertes, read-only SQL aus semantischer Garantie und Laufzeit-Schema. |

## Objekte, Runs und Zeitreihen

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `objects.tooltips.status` | Objektstatus-Spalte | Rollup des letzten relevanten Laufstatus über Observability und Quality. |
| `objects.tooltips.checkCount` | Checks-Spalte | Anzahl kompilierter Checks, die für dieses Objekt verfügbar sind. |
| `objects.tooltips.lastRun` | Letzter Lauf | Zeitpunkt des letzten gespeicherten Runs; Details öffnen den Run-Kontext. |
| `objectDetail.tooltips.run` | "Run starten" | Führt Checks gegen die konfigurierte Umgebung aus und speichert Ergebnisse. |
| `objectDetail.tooltips.profile` | "Profiling" | Berechnet Spaltenstatistiken; Samples bleiben hinter dem PII-Gate. |
| `objectDetail.tooltips.createChecks` | "Checks anlegen" | Öffnet oder seeded den Workbench-Entwurf für dieses Objekt. |
| `objectDetail.tooltips.trend` | Sparkline in Check-Tabelle | Verlauf des numerischen Ist-Werts aus den letzten Läufen. |
| `timeseries.tooltips.expectedBand` | Erwartetes Band | Baseline-Korridor aus historischen Läufen; Ausreißer markieren Drift. |
| `timeseries.tooltips.anomaly` | Anomalie-Marker | Datenpunkt außerhalb des erwarteten Bands oder mit auffälligem Delta. |
| `runDetail.tooltips.downloadCsv` | CSV-Download | Exportiert die sichtbaren Check-Ergebnisse dieses Runs. |
| `compare.tooltips.regression` | Run-Vergleich | Zeigt Checks, die zwischen zwei Läufen neu rot wurden oder sich erholt haben. |

## Incidents, Proposals und Alerting

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `incidents.tooltips.kindContract` | Incident-Art "Contract-Breach" | Verletzung einer verbindlichen Contract-Zusage mit Compliance- und SLA-Wirkung. |
| `incidents.tooltips.kindGate` | Incident-Art "Engineering-Signal" | Internes Gate ist auffällig; relevant für Teams, nicht für Governance-Compliance. |
| `incidents.tooltips.acknowledge` | "Bestätigen" | Markiert, dass der Incident gesehen wurde; löst ihn noch nicht. |
| `incidents.tooltips.investigate` | "In Arbeit nehmen" | Signalisiert aktive Analyse und hält die Timeline nachvollziehbar. |
| `incidents.tooltips.resolve` | "Lösen" | Schließt den Incident fachlich; Folge-Runs belegen die Erholung. |
| `incidents.tooltips.rootCause` | "Root Cause in Lineage" | Öffnet die Lineage mit Fokus auf mögliche Upstream-Ursachen. |
| `incidents.tooltips.sla` | SLA-Wartezeit | Zeit seit Öffnung oder Bestätigung; überschrittene Fenster werden hervorgehoben. |
| `proposals.tooltips.confidence` | Konfidenz-Bar | Statistische Sicherheit des Vorschlags aus historischen Runs und Warm-up. |
| `proposals.tooltips.acceptGate` | Vorschlag übernehmen | Übernimmt die neue Erwartung in ein internes Gate. |
| `proposals.tooltips.reviewContract` | "Im Contract prüfen" | Boundary-Vorschläge laufen durch den Contract-Workflow statt Auto-Apply. |
| `proposals.tooltips.snooze` | Snooze | Blendet den Vorschlag vorerst aus, ohne ihn fachlich abzulehnen. |
| `notifications.tooltips.mute` | Mute-Fenster | Unterdrückt Benachrichtigungen im Wartungsfenster, ohne Ergebnisse zu löschen. |
| `notifications.tooltips.routingRule` | Routing-Regel | Leitet Incidents nach Severity, Space, Produkt oder Owner an einen Kanal. |

## Governance und Policy

| i18n-Key-Vorschlag | Auslöser | Tooltip-Text |
|---|---|---|
| `governance.tooltips.g1` | Gate G1 Policy | Contracts enthalten keine SQL-Fragmente; nur semantische Garantien sind erlaubt. |
| `governance.tooltips.g2` | Gate G2 Policy | Schema wird erst zur Laufzeit gebunden, nicht im Compiler hartcodiert. |
| `governance.tooltips.g3` | Gate G3 Policy | Breaking Changes an Contracts brauchen einen Major-Version-Sprung. |
| `governance.tooltips.g6` | Gate G6 Policy | Übersprungene oder gegatete Checks dürfen nie wie bestanden aussehen. |
| `governance.tooltips.g8` | Gate G8 Policy | Rohdaten verlassen HANA nur mit expliziter PII-Freigabe und Projektion. |
| `governance.tooltips.contractsBreached` | Breached KPI | Anzahl aktiver Boundary-Contracts mit aktuell verletzter Compliance. |
| `governance.tooltips.activeContracts` | Aktive Contracts KPI | Nur aktive Boundary-Contracts zählen für Governance und SLA. |

## Implementierungsnotizen

- Bestehende Keys nicht doppeln: `stateHint.*` und `lineage.tooltips.*` können direkt als Startpunkt dienen.
- Für Check-Builder-Parameter zuerst `CheckTemplateParam.hint` aus `check_library.json` verwenden; nur wiederkehrende Konzepte zentralisieren.
- Für deaktivierte Buttons `title` kurzfristig beibehalten, später durch `Tooltip` + `aria-describedby` ersetzen.
- Tooltip-Triggers sollten auch per Tastatur erreichbar sein: Icon-Button mit `aria-label`, sichtbarer Fokus, Escape schließt.
- Keine Tooltips auf rein dekorativen Farben oder Spines; dort reichen sichtbare Labels, Legende und `aria-label`.
- Für mobile/touch später alternative Offenlegung vorsehen: Info-Icon oder Long-press allein reicht nicht.

## Mögliche erste Umsetzung

1. `apps/cockpit/src/i18n/de.ts` um einen Top-Level-Block `tooltips` erweitern und vorhandene `lineage.tooltips`/`stateHint` unverändert lassen.
2. Kleines `Tooltip`-Primitive bauen, das `children`, `content`, `placement="top"` und `aria-describedby` unterstützt.
3. Zuerst die Stellen mit hoher Entscheidungslast anbinden: deaktivierte Schreibaktionen, Gate-vs-Contract-Badges, Coverage-Flags, Breaking-Diff, Gating-States.
4. Danach Check-Builder-Parameter und Zeitreihen ergänzen.
