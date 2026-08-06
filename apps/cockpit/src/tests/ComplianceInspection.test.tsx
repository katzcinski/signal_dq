import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Zwei-Ebenen-Inspektion auf der Governance-Fläche: der Objekt-Name öffnet das
// Quick-Checks-Popover, der Zeilenklick bleibt der Sprung ins Objektdetail. Die
// schweren Overlays werden durch Marker ersetzt — getestet wird die Verdrahtung.
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
vi.mock('@/components/ObjectPeek', () => ({
  ObjectPeek: ({ objectId }: { objectId: string }) => <div data-testid="object-peek">{objectId}</div>,
}));
vi.mock('@/components/ObjectChecksPopover', () => ({
  ObjectChecksPopover: ({ objectId }: { objectId: string }) => (
    <div data-testid="checks-popover">{objectId}</div>
  ),
}));

import Governance from '@/pages/Compliance';

const OBJECTS = [{ id: 'P1', name: 'OBJ_COVERED', space: 'SALES' }];
const CONTRACTS = [{ product: 'P1', kind: 'consumer_contract', lifecycle: 'active', version: '1.2.0' }];
const COVERAGE = { contract_coverage_pct: 50, with_active_contract: 1, objects_total: 1, contracts_breached: 0 };

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/compliance']}>
      <Routes>
        <Route path="/compliance" element={<><Governance /><LocationEcho /></>} />
        <Route path="/objects/:id" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Governance two-level inspection', () => {
  beforeEach(() => {
    state.objects = [...OBJECTS];
    state.contracts = [...CONTRACTS];
    state.coverage = { ...COVERAGE };
  });

  it('opens the quick-checks popover from the object name', () => {
    renderPage();

    expect(screen.queryByTestId('checks-popover')).toBeNull();
    fireEvent.click(screen.getByLabelText('Checks für OBJ_COVERED anzeigen'));
    expect(screen.getByTestId('checks-popover').textContent).toBe('P1');
    // Die Ebenen sind getrennt — das Betriebs-Panel bleibt geschlossen.
    expect(screen.queryByTestId('object-peek')).toBeNull();
  });

  it('still navigates to the object detail on row click', () => {
    renderPage();

    // Klick auf eine neutrale Zelle (nicht den Namen) löst den Zeilenklick aus.
    fireEvent.click(screen.getByText('SALES'));
    expect(screen.getByTestId('location')).toHaveTextContent('/objects/P1');
    expect(screen.queryByTestId('checks-popover')).toBeNull();
  });
});
