import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Cockpit from '@/pages/Cockpit';

// Zwei-Ebenen-Inspektion auf der Cockpit-Übersicht: die Checks-Zelle öffnet das
// Quick-Checks-Popover, der Zeilenklick das rechte Betriebs-Panel (ObjectPeek).
// Die schweren Kinder werden durch Marker ersetzt — getestet wird die Verdrahtung.

const OBJECT = {
  id: 'obj1',
  name: 'MY_TABLE',
  schema_name: 'S',
  family: 'quality',
  layer: 'reporting',
  status: 'fail',
  family_status: { observability: 'pass', quality: 'fail' },
  contract_status: '',
  cov_flag: 'gap',
  check_count: 7,
  owned_by: 'team',
  last_run: null,
  space: 'SALES',
};

vi.mock('@/api/objects', () => ({
  useObjects: () => ({
    data: [OBJECT],
    isLoading: false,
    isError: false,
    isSuccess: true,
    refetch: vi.fn(),
    dataUpdatedAt: 0,
  }),
}));
vi.mock('@/api/incidents', () => ({
  useIncidents: () => ({ data: [], isError: false, isSuccess: true, refetch: vi.fn() }),
}));
vi.mock('@/api/activity', () => ({ useActivity: () => ({ data: [], isSuccess: true }) }));
vi.mock('@/api/coverage', () => ({
  useCoverageSummary: () => ({
    data: {
      unvalidated_30d: [],
      contract_coverage_pct: 0,
      with_active_contract: 0,
      objects_total: 0,
      gates_failing: 0,
    },
    isSuccess: true,
  }),
}));
vi.mock('@/api/contracts', () => ({
  useContracts: () => ({ data: [] }),
  useContractSla: () => ({ data: undefined }),
}));

vi.mock('@/components/DqHealthTrend', () => ({ DqHealthTrend: () => null }));
vi.mock('@/components/AttentionPanel', () => ({ AttentionPanel: () => null }));
vi.mock('@/components/StatusHeatmap', () => ({ StatusHeatmap: () => null }));
vi.mock('@/components/ObjectPeek', () => ({
  ObjectPeek: ({ objectId }: { objectId: string }) => <div data-testid="object-peek">{objectId}</div>,
}));
vi.mock('@/components/ObjectChecksPopover', () => ({
  ObjectChecksPopover: ({ objectId }: { objectId: string }) => (
    <div data-testid="checks-popover">{objectId}</div>
  ),
}));

function renderCockpit() {
  render(
    <MemoryRouter>
      <Cockpit />
    </MemoryRouter>,
  );
}

describe('Cockpit two-level inspection', () => {
  it('renders the object in the status grid with a checks trigger', () => {
    renderCockpit();
    expect(screen.getByText('MY_TABLE')).toBeTruthy();
    expect(screen.getByLabelText('Checks für MY_TABLE anzeigen')).toBeTruthy();
  });

  it('opens the quick-checks popover from the checks cell', () => {
    renderCockpit();
    expect(screen.queryByTestId('checks-popover')).toBeNull();
    fireEvent.click(screen.getByLabelText('Checks für MY_TABLE anzeigen'));
    expect(screen.getByTestId('checks-popover').textContent).toBe('obj1');
    // Das Betriebs-Panel bleibt geschlossen — die Ebenen sind getrennt.
    expect(screen.queryByTestId('object-peek')).toBeNull();
  });

  it('opens the operations panel on row click', () => {
    renderCockpit();
    expect(screen.queryByTestId('object-peek')).toBeNull();
    // Klick auf eine neutrale Zelle (nicht Name/Checks) löst den Zeilenklick aus.
    fireEvent.click(screen.getByText('SALES'));
    expect(screen.getByTestId('object-peek').textContent).toBe('obj1');
    expect(screen.queryByTestId('checks-popover')).toBeNull();
  });
});
