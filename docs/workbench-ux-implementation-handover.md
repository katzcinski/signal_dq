# Handover — Workbench Freigabe-UX cleanup

**For:** Codex (implementing agent, no prior context)
**Scope:** Frontend-only. No backend, no API, no migration.
**Files in play:** `apps/cockpit/src/pages/ContractWorkbench.tsx`, `apps/cockpit/src/i18n/de.ts` (and any other locale files under `apps/cockpit/src/i18n/`).

---

## 1. Goal in one sentence

Remove the lite/full **mode toggle** from the contract editor and replace the two competing action buttons (`Genehmigen` / `Speichern & aktivieren`) with **one primary action whose label and ceremony are derived from the contract's state** — never chosen by the user.

**Locked decision (do not reopen):** progressive disclosure only. There is **no** mode toggle and **no** "advanced mode" switch. The versioning/breaking-diff UI is always available behind a collapsible disclosure, but it is never a separate workflow.

---

## 2. Why (the problem being fixed)

In the current editor toolbar, two buttons look like actions but are actually layout toggles:
- `Schnell zertifizieren` (i18n key `workbench.liteMode`) — just switches the editor into lite layout.
- `Freigabe-Workflow` (`workbench.fullMode`) — switches into full layout.

Each layout then exposes a *differently named* real action that produces the **same end state** (draft → active):
- Lite layout → `Speichern & aktivieren` (`workbench.certify`, calls the `certify` endpoint).
- Full layout → `Entwurf speichern` then `Genehmigen` (`workbench.approve`, calls the `approve` endpoint).

For an `internal_gate` the two paths are identical in effect. Result: users don't know which to click, take unnecessary roundtrips (save-then-approve), and the verbs overlap (`zertifizieren` / `genehmigen` / `aktivieren` / `freigeben` / `hochstufen`).

**Important:** the backend already separates `certify` and `approve` endpoints, and the FE already auto-computes lite-vs-full via `kindDefaultLite` / `lockedToFull`. This task removes the *user-facing override toggle* and unifies the verbs. It does **not** rewrite the lifecycle.

---

## 3. Current code map (verify before editing — line numbers are approximate anchors)

`apps/cockpit/src/pages/ContractWorkbench.tsx`:
- `EditorPane` component starts ~L1182. Hooks used: `usePutContract`, `useCertifyContract`, `useApproveContract`, `useDeprecateContract`, `useDiffContract` (~L1190–1194).
- Mode-selection logic ~L1210–1218:
  - `kindDefaultLite` = `contract?.kind === 'internal_gate' || !contract`
  - `lockedToFull` = `draftKind !== 'internal_gate' && contract?.certified === true`
  - `lite` = `lockedToFull ? false : liteOverride ?? kindDefaultLite`
  - `handleSetLite(...)` — toggle setter.
- Breaking-gate (G3) derivation ~L1259–1274: `hasBreaking`, `activeVersion`, `ceremonyRequired`, `ceremonyBreaking`, `breakingBlocked`, `canApproveDraft`. **Keep this logic** — it decides whether the consequential path is required.
- `saveButton` ~L1312–1321.
- `promoteButton` ~L1325–1334 (only shown for `internal_gate`, label `workbench.promote`).
- **Lite layout block** ~L1346–1386 — returns early. Contains the `fullMode` toggle button (~L1356) and the single `certify` button (~L1373–1383).
- **Full layout block** ~L1389 onward — ApprovalBar with `liteMode` toggle (~L1401), `promoteButton`, `saveButton`, `approve` button (~L1405–1414), `deprecate` button (~L1415–1424), confirm dialog (~L1432–1440), and the right-hand column with YAML preview + `BreakingDiffPanel` (~L1456–1476).

`apps/cockpit/src/i18n/de.ts` — `workbench:` block starts ~L174. Relevant keys: `promote`, `promoting`, `promoteHint`, `liteMode`, `fullMode`, `saveDraft`, `saving`, `saved`, `saveError`, `certify`, `certifying`, `certified`, `liteHint`, `approve`, `approving`, `approveConfirm`, `deprecate`, `deprecating`, `gateChangeHint`.

---

## 4. Target behavior — action follows state

Compute a single primary action in `EditorPane` from existing state (`contract.kind`, `contract.lifecycle`, whether an `.active.yml` baseline exists / `contract.certified`, and `breakingBlocked`). One editor layout only.

| Object & state | Primary button label | Endpoint called | Ceremony |
|---|---|---|---|
| `internal_gate`, any change | **Aktiv schalten** | `certify` | one click |
| contract, `lifecycle==='draft'`, never been live | **Aktiv schalten** | `certify` | one click |
| contract, already live (has active baseline), changed | **Neue Version freigeben (vX.Y.Z)** | `approve` | version + breaking-diff disclosure + confirm dialog; respect `breakingBlocked` (disable + `breakingBlocked` tooltip) |
| `lifecycle==='active'` | **Außer Betrieb nehmen** | `deprecate` | confirm |
| `internal_gate` → contract | **Als Contract festschreiben** (in a `⋯` overflow menu, secondary) | `promote` | existing promote flow |

Supporting controls become progressive disclosure:
- YAML preview + `BreakingDiffPanel` move behind a collapsible **"Versionierung & Diff anzeigen"** disclosure (e.g. a `<details>` or a local `useState` show/hide). Always available, never blocking.
- "Save draft" becomes a quiet secondary button (label "Als Entwurf sichern"), **off** the critical path — it is for parking/handing off work, not a prerequisite for activation.

---

## 5. Step-by-step tasks

1. **Delete the mode machinery** in `EditorPane`: remove `liteOverride`/`onSetLiteOverride` props, `lockedToFull`, `lite`, `handleSetLite`, and the `kindDefaultLite`-driven branch. Also remove `liteOverride` plumbing from the parent `ContractWorkbench` (the `?lite=0|1` URL param and any state that fed `onSetLiteOverride`). Grep for `lite`, `liteOverride`, `lockedToFull`, `fullMode`, `liteMode` to find all call sites.
2. **Collapse to one layout.** Keep the full-layout structure (ApprovalBar + editor grid). Delete the early-return lite block (~L1346–1386). The guarantee editor / check builder must still render once.
3. **Derive the primary action.** Add a small helper that returns `{ label, onClick, disabled, title, variant }` from state per the table in §4. Render exactly one primary button. Reuse existing mutations (`certify`, `approve`, `deprecate`) and the existing confirm dialog for the `approve` path. Keep `breakingBlocked` gating intact.
4. **Move `promote`** into a `⋯` overflow menu (or a clearly secondary button), relabel via new i18n key (see §6). Only render for `internal_gate` and `lifecycle !== 'deprecated'`.
5. **Progressive disclosure** for YAML preview + `BreakingDiffPanel`. Default collapsed for the one-click paths; default expanded (or auto-expand) for the "Neue Version freigeben" path so the diff is visible before a consequential release.
6. **Demote save-draft** to a quiet secondary ("Als Entwurf sichern").
7. **Pending-proposal banner (tracked in `OPEN_TASKS.md` §M4; optional inside this frontend-only cleanup).** When a contract was downgraded to `draft` by an accepted proposal, show an inline banner in the editor: "Übernommener Vorschlag wartet auf Freigabe → Prüfen & freigeben", wired to the same release action. If detecting "downgraded-by-proposal" requires backend signal not present, defer to M4 — do not invent an endpoint.
8. **i18n** — see §6.
9. **Verify** — see §7.

---

## 6. i18n changes (`de.ts` and every other locale file under `i18n/`)

Add:
- `activate: 'Aktiv schalten'`, `activating: 'Aktiviert…'`
- `release: 'Neue Version freigeben'` (the version is interpolated at call site, e.g. ``${t.workbench.release} (v${version})``)
- `releasing: 'Wird freigegeben…'`
- `saveDraftSecondary: 'Als Entwurf sichern'`
- `promote: 'Als Contract festschreiben'` (repurpose existing key; also fix the stray English "Promote to Contract" inside `gateChangeHint`)
- `showVersioning: 'Versionierung & Diff anzeigen'`

Remove / stop referencing (delete keys only after confirming no other component imports them — grep first):
- `liteMode`, `fullMode`, `liteHint`, `certify` (as a button verb), `approve` (as a button verb), `approving`/`certifying` (replace with `activating`/`releasing`).

Keep as **state labels only** (not verbs): `certified` / `Aktiv`. Keep `deprecate`/`deprecating`, `saved`/`saving`/`saveError`, `approveConfirm` (reuse for the release confirm dialog), `breakingBlocked`, `promoteHint`, `gateChangeHint`.

Apply the same key set to all locale files so the build doesn't break on a missing key — find them with a glob over `apps/cockpit/src/i18n/`.

---

## 7. Verification

- `cd apps/cockpit` and run the project's typecheck + lint (check `package.json` scripts — likely `tsc --noEmit` / `eslint`). The build must be green with no dangling references to removed keys/props.
- Run the cockpit dev server and check, in the contract workbench, for each case in §4:
  - internal gate → single **Aktiv schalten**, no diff/version clutter on the critical path.
  - new draft contract → single **Aktiv schalten**.
  - already-active contract with an edit → **Neue Version freigeben (vX.Y.Z)**, diff visible, confirm dialog, blocked when `breakingBlocked`.
  - active contract → **Außer Betrieb nehmen**.
  - gate → **Als Contract festschreiben** present in the `⋯` menu.
- Confirm no toggle button (`Schnell zertifizieren` / `Freigabe-Workflow`) appears anywhere.

---

## 8. Do NOT

- Do not touch backend endpoints. `certify` and `approve` both stay; only the FE choice of which to call changes.
- Do not change the G3 breaking-change guard semantics.
- Do not add a mode toggle or "advanced mode" switch back in any form.
- Do not invent new backend signals for the proposal banner — gate that on existing data or defer.

---

## 9. Reference

Full conceptual write-up with before/after mockup: `docs/workbench-ux-proposal.html`.
