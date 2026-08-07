import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Governance: KPI-Zeile (Coverage/Aktiv/Ohne Contract/Verletzt), Objekt-Tabelle
// mit zusammengeführter Contract-Spalte (Lifecycle-Chip + Version bzw.
// Gap-Chip), Suche + „Nur ohne Contract"-Filter, Zeilenklick → Objektdetail.
const state = vi.hoisted(() => ({
  objects: [] as unknown[],
  contracts: [] as unknown[],
  coverage: {} as Record<string, unknown>,
}));

vi.mock('@/api/objects', () => ({
  useObjects: () => ({ data: state.objects, isLoading: false, isError: false, refetch: vi.fn() }),
}));
vi.mock('@/api/contracts', () => ({
  useContracts: () => ({ data: state.contracts, isLoading: false, isError: false, refetch: vi.fn() }),
  // Das SLA-Panel hält je aktiver Zeile einen eigenen Hook — hier neutral gemockt.
  useContractSla: () => ({ data: undefined }),
}));
vi.mock('@/api/coverage', () => ({
  useCoverageSummary: () => ({ data: state.coverage }),
}));

import Governance from '@/pages/Compliance';

const OBJECTS = [
  { id: 'P1', name: 'OBJ_COVERED', space: 'SALES' },
  { id: 'P2', name: 'OBJ_BARE', space: 'FINANCE' },
];
const CONTRACTS = [
  { product: 'P1', kind: 'consumer_contract', lifecycle: 'active', version: '1.2.0' },
  // internal_gate zählt nicht als Boundary-Contract → P2 bleibt ungebunden.
  { product: 'P2', kind: 'internal_gate', lifecycle: 'active', version: '1.0.0' },
];
const COVERAGE = { contract_coverage_pct: 50, with_active_contract: 1, objects_total: 2, contracts_breached: 3, unvalidated_30d: [] as string[] };

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
}

function renderPage(route = '/compliance') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/compliance" element={<><Governance /><LocationEcho /></>} />
        <Route path="/objects/:id" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

// Klickbare Zeilen tragen role="button" (Tastatur-A11y der Table), daher
// über die .tbl-row-Klasse statt über getAllByRole('row') selektieren. Auf die
// Objektstatus-Tabelle (die erste der Seite) einschränken, da das SLA-Panel
// darunter ebenfalls `.tbl-row`-Zeilen rendert.
function objectColumnTexts(): string[] {
  const objectTable = document.querySelector('table')!;
  return Array.from(objectTable.querySelectorAll('tbody tr.tbl-row'))
    .map(row => row.querySelector('td')?.textContent ?? '');
}

describe('Governance', () => {
  beforeEach(() => {
    state.objects = [...OBJECTS];
    state.contracts = [...CONTRACTS];
    state.coverage = { ...COVERAGE };
  });

  it('shows coverage, uncovered and breached KPIs', () => {
    renderPage();

    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('1/2 mit aktivem Contract')).toBeInTheDocument();
    const uncoveredKpi = screen.getByText('Ohne Contract', { selector: 'div' }).parentElement!;
    expect(within(uncoveredKpi).getByText('1')).toBeInTheDocument();
    const breachedKpi = screen.getByText('Verletzte Contracts').parentElement!;
    expect(within(breachedKpi).getByText('3')).toBeInTheDocument();
  });

  it('merges binding and lifecycle into one contract column', () => {
    renderPage();

    const covered = within(screen.getByText('OBJ_COVERED').closest('tr')!);
    expect(covered.getByText('Aktiv')).toBeInTheDocument();
    expect(covered.getByText('v1.2.0')).toBeInTheDocument();

    // internal_gate bindet nicht → Gap-Chip statt Lifecycle.
    const bare = within(screen.getByText('OBJ_BARE').closest('tr')!);
    expect(bare.getByText('Ohne Contract')).toBeInTheDocument();
    expect(bare.queryByText('Aktiv')).not.toBeInTheDocument();
  });

  it('sorts by governance maturity via the contract column', () => {
    renderPage();

    fireEvent.click(screen.getByText('Contract', { selector: 'th' }));
    expect(objectColumnTexts()).toEqual(['OBJ_BARE', 'OBJ_COVERED']); // aufsteigend: ungebunden zuerst

    fireEvent.click(screen.getByText('Contract', { selector: 'th' }));
    expect(objectColumnTexts()).toEqual(['OBJ_COVERED', 'OBJ_BARE']);
  });

  it('filters to uncovered objects and by search text', () => {
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Nur ohne Contract' }));
    expect(objectColumnTexts()).toEqual(['OBJ_BARE']);
    fireEvent.click(screen.getByRole('button', { name: 'Nur ohne Contract' }));

    const search = screen.getByRole('searchbox', { name: 'Objekt oder Space filtern…' });
    fireEvent.change(search, { target: { value: 'sales' } });
    expect(objectColumnTexts()).toEqual(['OBJ_COVERED']);

    fireEvent.change(search, { target: { value: 'nix' } });
    expect(screen.getByText('Keine Treffer für den Filter')).toBeInTheDocument();
  });

  it('filters by space via the select', () => {
    renderPage();

    const spaceSelect = screen.getByRole('combobox', { name: 'Nach Space filtern' });
    fireEvent.change(spaceSelect, { target: { value: 'FINANCE' } });
    expect(objectColumnTexts()).toEqual(['OBJ_BARE']);
  });

  it('links to the contract workbench when no contract is active', () => {
    state.contracts = [{ product: 'P2', kind: 'internal_gate', lifecycle: 'active', version: '1.0.0' }];
    renderPage();
    expect(screen.getByRole('link', { name: /Ersten Contract anlegen/ })).toHaveAttribute('href', '/contracts');
  });

  it('navigates to the object detail on row click', () => {
    renderPage();

    fireEvent.click(screen.getByText('OBJ_COVERED').closest('tr')!);
    expect(screen.getByTestId('location')).toHaveTextContent('/objects/P1');
  });

  it('shows the hint banner when no boundary contract is active', () => {
    state.contracts = [{ product: 'P2', kind: 'internal_gate', lifecycle: 'active', version: '1.0.0' }];
    renderPage();
    expect(screen.getByText(/Noch keine aktiven Contracts/)).toBeInTheDocument();
  });

  it('surfaces stale objects via KPI, chip and filter', () => {
    state.coverage = { ...COVERAGE, unvalidated_30d: ['P2'] };
    renderPage();

    // KPI zeigt die Zahl der überfälligen Objekte.
    const staleKpi = screen.getByText('Unvalidiert >30d', { selector: 'div' }).parentElement!;
    expect(within(staleKpi).getByText('1')).toBeInTheDocument();

    // Der Marker sitzt auf der betroffenen Zeile.
    const bare = within(screen.getByText('OBJ_BARE').closest('tr')!);
    expect(bare.getByText('Unvalidiert')).toBeInTheDocument();

    // KPI-Klick ist ein Deep-Link auf den Filter — der Modus lebt in der URL.
    fireEvent.click(within(staleKpi).getByText('1'));
    expect(objectColumnTexts()).toEqual(['OBJ_BARE']);
    expect(screen.getByTestId('location')).toHaveTextContent('mode=stale');
  });

  it('hydrates the filter mode from the URL (?mode=stale)', () => {
    state.coverage = { ...COVERAGE, unvalidated_30d: ['P2'] };
    renderPage('/compliance?mode=stale');

    // Deep-Link (z. B. vom Cockpit-KPI „>30d unvalidiert") reproduziert den Filter.
    expect(objectColumnTexts()).toEqual(['OBJ_BARE']);
  });

  it('renders the estate lifecycle distribution', () => {
    renderPage();
    // P1 aktiv gebunden, P2 ungebunden → 1 aktiv, 1 ohne Contract.
    expect(
      screen.getByRole('img', { name: /Aktiv: 1.*Entwurf: 0.*Veraltet: 0.*Ohne Contract: 1/ }),
    ).toBeInTheDocument();
  });

  it('drills into breached objects from the KPI', () => {
    state.contracts = [
      { product: 'P1', kind: 'consumer_contract', lifecycle: 'active', version: '1.2.0', compliance: 'breached' },
      { product: 'P2', kind: 'consumer_contract', lifecycle: 'active', version: '1.0.0', compliance: 'ok' },
    ];
    renderPage();

    const covered = within(screen.getByText('OBJ_COVERED').closest('tr')!);
    expect(covered.getByText('Verletzt')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Nur verletzt' }));
    expect(objectColumnTexts()).toEqual(['OBJ_COVERED']);
  });
});
