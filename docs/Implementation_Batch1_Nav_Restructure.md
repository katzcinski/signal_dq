# Batch 1 — Navigation Restructure & Health-Screen Scope

> **Goal**: Restructure the sidebar into DQ-Block + Govern-Block with divider,
> rename Governance → Compliance, scope Health dashboard to Engineering-Health.
>
> **No backend changes.** All API endpoints and response shapes stay identical.
> This batch is pure frontend (React + i18n + routing + tests).

---

## Pre-conditions

- Branch from `main` (commit `248a02f` or later).
- All existing tests must pass before starting (`npm run test` in `apps/cockpit`).

---

## File 1 — `apps/cockpit/src/i18n/de.ts`

### 1a. Rename nav labels

```ts
// OLD (lines 4, 10)
cockpit: 'Cockpit',
governance: 'Governance',

// NEW
cockpit: 'Health',
governance: 'Compliance',
```

### 1b. Add `nav.compliance` alias (same value, for forward-compat)

```ts
// After governance line, add:
compliance: 'Compliance',
```

### 1c. Rename cockpit section header

```ts
// OLD (line 95–96)
cockpit: {
  title: 'DQ Cockpit',
  subtitle: 'SAP Datasphere — Data Quality & Observability',

// NEW
cockpit: {
  title: 'Health',
  subtitle: 'Engineering Health — Internal Gates & Observability',
```

### 1d. Change KPI label from "Contract-Abdeckung" to "Check-Abdeckung"

```ts
// OLD (line 99)
kpiCoverage: 'Contract-Abdeckung',

// NEW
kpiCoverage: 'Check-Abdeckung',
```

### 1e. Change coverage delta text

```ts
// OLD (line 101)
coverageOf: 'mit aktivem Contract',

// NEW
coverageOf: 'mit ≥1 Check',
```

### 1f. Rename governance section title

```ts
// OLD (line 518)
governance: {
  title: 'Governance',

// NEW
governance: {
  title: 'Compliance',
```

### 1g. Rename breadcrumb

```ts
// OLD (line 41)
breadcrumb: {
  home: 'Cockpit',

// NEW
breadcrumb: {
  home: 'Health',
```

---

## File 2 — `apps/cockpit/src/components/layout/Sidebar.tsx`

### 2a. Add `'compliance'` to `IconKey` union

```ts
// OLD (line 9)
type IconKey = 'my' | 'cockpit' | 'objects' | 'contracts' | 'lineage'
  | 'incidents' | 'proposals' | 'governance' | 'library'
  | 'notifications' | 'inventoryAdmin';

// NEW
type IconKey = 'my' | 'cockpit' | 'objects' | 'contracts' | 'lineage'
  | 'incidents' | 'proposals' | 'governance' | 'compliance' | 'library'
  | 'notifications' | 'inventoryAdmin';
```

### 2b. Add `compliance` icon to the `Icon` switch (reuse shield glyph)

```tsx
// After the 'governance' case (line 25), add:
case 'compliance': return <svg {...common}><path d="M12 3 4 6v5c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6Z" /><path d="M9 12l2 2 4-4" /></svg>;
```

> Uses the governance shield + a checkmark inside to visually distinguish.

### 2c. Add `'divider'` variant to `NavItem` and replace flat `BASE` with two-block structure

Replace the `NavItem` interface + `BASE` array (lines 32–47) with:

```tsx
interface NavItem { to: string; label: string; icon: IconKey; }
type SidebarEntry = NavItem | 'divider';

const MY_WORK: NavItem = { to: '/my', label: t.nav.myWork, icon: 'my' };
const INVENTORY_ADMIN: NavItem = { to: '/inventory-admin', label: t.nav.inventoryAdmin, icon: 'inventoryAdmin' };

const DQ_BLOCK: NavItem[] = [
  { to: '/',           label: t.nav.cockpit,    icon: 'cockpit' },
  { to: '/objects',    label: t.nav.objects,     icon: 'objects' },
  { to: '/lineage',    label: t.nav.lineage,     icon: 'lineage' },
  { to: '/incidents',  label: t.nav.incidents,   icon: 'incidents' },
  { to: '/proposals',  label: t.nav.proposals,   icon: 'proposals' },
  { to: '/library',    label: t.nav.library,     icon: 'library' },
];

const GOVERN_BLOCK: NavItem[] = [
  { to: '/contracts',  label: t.nav.contracts,   icon: 'contracts' },
  { to: '/compliance', label: t.nav.compliance,  icon: 'compliance' },
];

const UTILITY: NavItem[] = [
  { to: '/notifications', label: t.nav.notifications, icon: 'notifications' },
];

function navForRole(role: Role): SidebarEntry[] {
  const base: SidebarEntry[] = [
    ...DQ_BLOCK,
    'divider',
    ...GOVERN_BLOCK,
    'divider',
    ...UTILITY,
  ];
  if (role === 'admin') return [...base, INVENTORY_ADMIN];
  if (role === 'steward' || role === 'owner') return [MY_WORK, ...base];
  return base;
}
```

### 2d. Render the divider in the `<nav>` map

Replace the `nav.map(...)` block (lines 78–96) with:

```tsx
<nav style={{ flex: 1, padding: '8px 0' }}>
  {nav.map((entry, idx) => {
    if (entry === 'divider') {
      return (
        <div
          key={`div-${idx}`}
          style={{
            height: 1,
            background: 'var(--line)',
            margin: '6px 12px',
          }}
        />
      );
    }
    const { to, label, icon } = entry;
    return (
      <NavLink
        key={to} to={to} end={to === '/'}
        title={label}
        aria-label={label}
        style={({ isActive }) => ({
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '8px 12px', margin: '1px 6px', borderRadius: 5,
          justifyContent: collapsed ? 'center' : 'flex-start',
          color: isActive ? 'var(--fg)' : 'var(--fg-2)',
          background: isActive ? 'var(--bg-2)' : 'transparent',
          fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden',
          transition: 'color var(--t), background var(--t)',
        })}
      >
        <span style={{ display: 'inline-flex', flexShrink: 0 }}><Icon name={icon} /></span>
        {!collapsed && <span>{label}</span>}
      </NavLink>
    );
  })}
</nav>
```

---

## File 3 — `apps/cockpit/src/App.tsx`

### 3a. Add lazy import for Compliance page

```ts
// OLD (line 17)
const Governance = lazy(() => import('./pages/Governance'));

// NEW
const Compliance = lazy(() => import('./pages/Compliance'));
```

### 3b. Replace `/governance` route, add `/compliance` + redirect

```tsx
// OLD (line 49)
<Route path="/governance"  element={<Governance />} />

// NEW
<Route path="/compliance"  element={<Compliance />} />
<Route path="/governance"  element={<Navigate to="/compliance" replace />} />
```

> Import `Navigate` from `react-router-dom` (add to line 2 import).

---

## File 4 — `apps/cockpit/src/pages/Governance.tsx` → `Compliance.tsx`

### 4a. Rename the file

```
git mv apps/cockpit/src/pages/Governance.tsx apps/cockpit/src/pages/Compliance.tsx
```

### 4b. Rename the default export

```ts
// OLD (line 9)
export default function Governance() {

// NEW
export default function Compliance() {
```

No other content changes in this batch. The Compliance page keeps its existing
G1-policy and lifecycle panels — enrichment with SLA-breach list happens in
Batch 2 after `kind`-aware backend endpoints exist.

---

## File 5 — `apps/cockpit/src/store/role.ts`

### 5a. Update ROLE_META hints

```ts
// OLD (lines 20–23)
viewer:  { label: 'Viewer',         hint: 'Nur-Lese-Zugriff auf alle Ansichten.',               home: '/' },
steward: { label: 'Steward',        hint: 'Pflegt Platform-Contracts, bearbeitet Incidents.',    home: '/my' },
owner:   { label: 'Product-Owner',  hint: 'Schreibrecht auf eigene Produkt-Contracts.',          home: '/my' },
admin:   { label: 'Platform-Admin', hint: 'Vollzugriff auf alle Objekte und Aktionen.',          home: '/' },

// NEW
viewer:  { label: 'Viewer',         hint: 'Nur-Lese-Zugriff auf Health, Objekte und Compliance.', home: '/' },
steward: { label: 'Steward',        hint: 'Pflegt Internal Gates, bearbeitet Incidents und Contracts.', home: '/my' },
owner:   { label: 'Product-Owner',  hint: 'Gates und Contracts für eigene Produkte.',              home: '/my' },
admin:   { label: 'Platform-Admin', hint: 'Vollzugriff auf alle Objekte und Aktionen.',            home: '/' },
```

> Home routes stay the same (viewer→`/`, steward→`/my`, owner→`/my`, admin→`/`).
> Platform Owner home stays `/my` per grill decision (Q14-b). Changing it to
> `/lineage` is deferred to when the Coverage Map has the dimension switcher.

---

## File 6 — `apps/cockpit/src/pages/Cockpit.tsx`

### 6a. Replace Coverage KPI — use `with_checks` instead of `contract_coverage_pct`

The API already returns `with_checks` in the `CoverageSummary` type. Replace
the third KPI tile (lines 174–179):

```tsx
// OLD
<Kpi
  label={t.cockpit.kpiCoverage}
  value={`${coverage?.contract_coverage_pct ?? 0}%`}
  delta={coverage ? `${coverage.with_active_contract}/${coverage.objects_total} ${t.cockpit.coverageOf}` : undefined}
  accent="var(--cont)"
/>

// NEW
<Kpi
  label={t.cockpit.kpiCoverage}
  value={coverage ? `${Math.round((coverage.with_checks / Math.max(coverage.objects_total, 1)) * 100)}%` : '0%'}
  delta={coverage ? `${coverage.with_checks}/${coverage.objects_total} ${t.cockpit.coverageOf}` : undefined}
  accent="var(--cont)"
/>
```

### 6b. Remove SLA-Overview panel from Health page

The SLA panel (lines 229–242) belongs to Compliance, not Engineering-Health.
Delete the entire block:

```tsx
// DELETE lines 229–242 (the activeContracts.length > 0 && ... panel)
```

Also remove the now-unused imports and variables:

```ts
// Remove from imports (line 15):
import { useContracts, useContractSla } from '@/api/contracts';

// Remove from component body (line 110):
const contractsQuery = useContracts();
// Remove (line 113):
const { data: contracts = [] } = contractsQuery;
// Remove (line 114):
const activeContracts = contracts.filter(c => c.lifecycle === 'active');
```

And delete the `SlaBar` and `SlaRow` helper components (lines 66–93) — they are
no longer used on this page. (They will be reused in Compliance.tsx in Batch 2.)

### 6c. Update page title/subtitle

Already handled via i18n changes in File 1 (§1c). No code changes here — the
component reads from `t.cockpit.title` / `t.cockpit.subtitle`.

---

## File 7 — `apps/cockpit/src/tests/role.test.ts`

### 7a. Update ROLE_META assertion for new hint text

```ts
// The home routes don't change, so the existing ROLE_META test (lines 65–72)
// stays valid as-is. No changes needed.
```

### 7b. Add nav structure assertion (new describe block)

Create a new test that imports the sidebar nav helpers and validates the
two-block structure. If the `navForRole` function is not directly exported,
add `export` to it in `Sidebar.tsx` and test here. Otherwise, test at the
integration level via a rendering test.

**Minimal approach** — add to `role.test.ts`:

```ts
describe('ROLE_META homes', () => {
  it('viewer lands on Health (/)', () => {
    expect(ROLE_META.viewer.home).toBe('/');
  });
  it('steward lands on My Work (/my)', () => {
    expect(ROLE_META.steward.home).toBe('/my');
  });
  it('owner lands on My Work (/my)', () => {
    expect(ROLE_META.owner.home).toBe('/my');
  });
  it('admin lands on Health (/)', () => {
    expect(ROLE_META.admin.home).toBe('/');
  });
});
```

> This overlaps with the existing `ROLE_META` test but is more explicit. You can
> merge them or keep both — the existing test already passes.

---

## Execution order

These files have no circular dependencies. Apply them in any order, but
logically:

1. **i18n** (de.ts) — labels referenced by everything else
2. **Sidebar** — navigation structure
3. **App.tsx** — routing (depends on Compliance.tsx existing)
4. **Governance → Compliance** — file rename + export rename
5. **role.ts** — hint text updates
6. **Cockpit.tsx** — KPI + SLA panel removal
7. **Tests** — validate

---

## Acceptance criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| A1 | Sidebar shows two blocks separated by a 1px divider line | Visual: open app, inspect sidebar |
| A2 | DQ-Block order: Health, Objects, Lineage, Incidents, Proposals, Library | Visual: sidebar top section |
| A3 | Govern-Block order: Contracts, Compliance | Visual: sidebar below first divider |
| A4 | Utility block: Alerting (Notifications) | Visual: sidebar below second divider |
| A5 | Steward/Owner see "Meine Arbeit" above the DQ block | Switch role to steward, check sidebar |
| A6 | Admin sees Inventory at the bottom | Switch role to admin, check sidebar |
| A7 | `/governance` redirects to `/compliance` | Navigate to `/governance` in browser |
| A8 | Health page title says "Health" (not "DQ Cockpit") | Visual: open `/` |
| A9 | 3rd KPI shows "Check-Abdeckung" with `with_checks/objects_total` | Visual: Health page |
| A10 | SLA panel no longer appears on Health page | Visual: scroll Health page |
| A11 | Compliance page renders at `/compliance` | Navigate to `/compliance` |
| A12 | All existing tests pass (`npm run test`) | CLI |
| A13 | No TypeScript errors (`npm run typecheck` or `tsc --noEmit`) | CLI |
| A14 | Role-switch still works and lands on correct home route | Click role switcher in UI |

---

## Out of scope (later batches)

- `kind`-aware backend endpoints (ADR-0001 model changes)
- Segment-Control "Internal | Contract | All" on Object-Detail Checks tab
- Coverage-Map dimension switcher
- Promotion-Flow UI
- Compliance page enrichment (SLA-breach list, contract-compliance-Ampel)
- Dual-Run awareness in Runs page
- My Work kind-awareness (gate vs contract items)
