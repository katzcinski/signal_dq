import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ObjectDetail from '@/pages/ObjectDetail';
import type { CheckResult, ContractOut, ContractVersionDiff, ObjectSummary, RunListItem, RunSummary } from '@/types';

const mocks = vi.hoisted(() => ({
  triggerRun: vi.fn(),
  seedContract: vi.fn(),
  requestMonitoring: vi.fn(),
}));

const state = vi.hoisted(() => ({
  objectLoading: false,
  object: {
    id: 'Sales_Orders_View',
    name: 'Sales_Orders_View',
    schema_name: 'SALES',
    family: 'quality',
    layer: 'consumption',
    status: 'pass',
    family_status: { observability: 'pass', quality: 'pass' },
    contract_status: '',
    cov_flag: 'covered',
    check_count: 0,
    owned_by: 'platform',
    space: 'CORE',
  } as ObjectSummary,
  contract: undefined as ContractOut | undefined,
  versionDiff: undefined as ContractVersionDiff | undefined,
  runs: [] as RunListItem[],
  runDetail: undefined as RunSummary | undefined,
  monitoringEnabled: false,
  monitoringShares: [] as Array<{ object_id: string; status: string; view: string | null; error: string | null }>,
  requestMonitoringPending: false,
  seedContractPending: false,
  triggerPending: false,
}));

vi.mock('@/api/objects', () => ({
  useObject: () => ({
    data: state.objectLoading ? undefined : state.object,
    isLoading: state.objectLoading,
    isError: false,
    refetch: vi.fn(),
  }),
  useObjectRuns: () => ({ data: state.runs }),
  useTriggerRun: () => ({ mutate: mocks.triggerRun, isPending: state.triggerPending }),
  useCheckHistory: () => ({ data: [] }),
}));

vi.mock('@/api/contracts', () => ({
  useContract: () => ({ data: state.contract }),
  useContractVersionDiff: (_product: string, enabled = true) => ({
    data: enabled ? state.versionDiff : undefined,
    isLoading: false,
  }),
  useSeedContract: () => ({ mutate: mocks.seedContract, isPending: state.seedContractPending }),
}));

vi.mock('@/api/monitoring', () => ({
  useMonitoringConfig: () => ({ data: { enabled: state.monitoringEnabled, monitoring_space: 'MON' } }),
  useMonitoringShares: () => ({ data: state.monitoringShares }),
  useRequestMonitoring: () => ({ mutate: mocks.requestMonitoring, isPending: state.requestMonitoringPending }),
}));

vi.mock('@/api/runs', () => ({
  useRun: () => ({ data: state.runDetail }),
  useRunStream: () => ({ events: [] }),
}));

vi.mock('@/api/lineage', () => ({
  useLineage: () => ({
    data: {
      nodes: [{ id: 'Sales_Orders_View', label: 'Sales_Orders_View', layer: 'consumption' }],
      edges: [],
    },
    isLoading: false,
  }),
}));

vi.mock('@/components/SchedulePanel', () => ({
  SchedulePanel: ({ objectId }: { objectId: string }) => (
    <section>Schedule subsection for {objectId}</section>
  ),
}));

vi.mock('@/components/lineage/ColumnLineagePanel', () => ({
  ColumnLineagePanel: ({ objectId }: { objectId: string }) => (
    <section>Column lineage for {objectId}</section>
  ),
}));

vi.mock('@/components/MinedProposalsCallout', () => ({
  MinedProposalsCallout: () => null,
}));

function renderObjectDetail(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/objects/:id" element={<ObjectDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const failedResult: CheckResult = {
  name: 'row_count',
  sql: 'select 1',
  expect: '> 0',
  severity: 'fail',
  passed: false,
  actual_value: '0',
  duration_ms: 10,
  state: 'executed',
  kind: 'internal_gate',
};

const passedResult: CheckResult = {
  ...failedResult,
  name: 'freshness',
  passed: true,
  actual_value: '1',
};

const activeContract: ContractOut = {
  product: 'Sales_Orders_View',
  kind: 'provider_contract',
  dataset: 'Sales_Orders_View',
  owned_by: 'product',
  owners: ['team-data'],
  lifecycle: 'active',
  version: '1.2.0',
};

const finishedRun: RunListItem = {
  run_id: 'run-1',
  dataset: 'Sales_Orders_View',
  started_at: '2026-07-01T10:00:00Z',
  finished_at: '2026-07-01T10:01:00Z',
  overall_status: 'fail',
  total: 2,
  passed: 1,
  failed: 1,
  warnings: 0,
  run_state: 'finished',
  triggered_by: 'test',
};

beforeEach(() => {
  state.objectLoading = false;
  state.object.status = 'pass';
  state.contract = undefined;
  state.versionDiff = undefined;
  state.runs = [];
  state.runDetail = undefined;
  state.monitoringEnabled = false;
  state.monitoringShares = [];
  state.requestMonitoringPending = false;
  state.seedContractPending = false;
  state.triggerPending = false;
  mocks.triggerRun.mockClear();
  mocks.seedContract.mockClear();
  mocks.requestMonitoring.mockClear();
});

describe('ObjectDetail loading states', () => {
  it('shows local hero cards and the active section skeleton while the object loads', () => {
    state.objectLoading = true;

    renderObjectDetail('/objects/Sales_Orders_View?tab=lineage');

    expect(screen.getByTestId('object-hero-skeleton')).toBeTruthy();
    expect(screen.getAllByTestId('object-summary-card-skeleton')).toHaveLength(4);
    const nav = screen.getByLabelText('Objektbereiche');
    expect(nav).toHaveAttribute('data-active-group', 'structure-interface');
    expect(nav).toHaveAttribute('data-active-anchor', 'lineage');
    expect(screen.getByTestId('mini-lineage-skeleton')).toBeTruthy();
    expect(screen.getByTestId('column-lineage-skeleton')).toBeTruthy();
    expect(screen.queryByText('Lädt…')).toBeNull();
  });
});

describe('ObjectDetail legacy deep links', () => {
  it('opens ?tab=schedule in the history operations schedule subsection', () => {
    renderObjectDetail('/objects/Sales_Orders_View?tab=schedule');

    const nav = screen.getByLabelText('Objektbereiche');
    expect(nav).toHaveAttribute('data-active-group', 'history-ops');
    expect(nav).toHaveAttribute('data-active-anchor', 'schedule');
    expect(screen.getByRole('button', { name: 'Historie & Betrieb' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Zeitplan' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Schedule subsection for Sales_Orders_View')).toBeTruthy();
    expect(screen.queryByText('Run-ID')).toBeNull();
  });

  it('opens ?tab=lineage in the structure lineage subsection', () => {
    renderObjectDetail('/objects/Sales_Orders_View?tab=lineage');

    const nav = screen.getByLabelText('Objektbereiche');
    expect(nav).toHaveAttribute('data-active-group', 'structure-interface');
    expect(nav).toHaveAttribute('data-active-anchor', 'lineage');
    expect(screen.getByRole('button', { name: 'Struktur & Interface' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Lineage' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Column lineage for Sales_Orders_View')).toBeTruthy();
    expect(screen.getAllByText(/Lineage Map/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Contracts')).toBeNull();
  });
});

describe('ObjectDetail hero', () => {
  it('shows object identity, ownership, health, and empty summary states', () => {
    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getAllByText('Sales_Orders_View').length).toBeGreaterThan(0);
    expect(screen.getByText('Objektkontext')).toBeTruthy();
    expect(screen.getByText('Owner')).toBeTruthy();
    expect(screen.getByText('platform')).toBeTruthy();
    expect(screen.getByText('Aktuelle Health')).toBeTruthy();
    expect(screen.getByText('Kein Contract')).toBeTruthy();
    expect(screen.getByText('Deaktiviert')).toBeTruthy();
  });

  it('summarizes contract, latest run, failed checks, and active monitoring', () => {
    state.contract = activeContract;
    state.runs = [finishedRun];
    state.runDetail = {
      ...state.runs[0],
      schema_name: 'SALES',
      contract_version: '1.2.0',
      actor: 'test',
      results: [failedResult, passedResult],
    };
    state.monitoringEnabled = true;
    state.monitoringShares = [{
      object_id: 'Sales_Orders_View',
      status: 'provisioned',
      view: 'MON.Sales_Orders_View',
      error: null,
    }];

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByText('Teams: team-data')).toBeTruthy();
    expect(screen.getByText('Version 1.2.0 | product')).toBeTruthy();
    expect(screen.getByText('1/2 Checks bestanden')).toBeTruthy();
    expect(screen.getByText('1/2 Checks fehlgeschlagen')).toBeTruthy();
    expect(screen.getAllByText('Aktiv').length).toBeGreaterThan(0);
  });

  it('shows monitoring request and pending action states', () => {
    state.monitoringEnabled = true;
    state.requestMonitoringPending = true;
    state.seedContractPending = true;
    state.triggerPending = true;

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByText('Merke vor...')).toBeTruthy();
    expect(screen.getByText('Legt Checks an...')).toBeTruthy();
    const busyButtons = screen
      .getAllByRole('button')
      .filter(button => button.getAttribute('aria-busy') === 'true');
    expect(busyButtons).toHaveLength(3);
  });
});

describe('ObjectDetail attention band', () => {
  it('appears when the latest run has failed checks', () => {
    state.contract = activeContract;
    state.runs = [finishedRun];
    state.runDetail = {
      ...finishedRun,
      schema_name: 'SALES',
      contract_version: '1.2.0',
      actor: 'test',
      results: [failedResult, passedResult],
    };

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByLabelText('Aufmerksamkeitsband')).toBeTruthy();
    expect(screen.getByText('Checks fehlgeschlagen')).toBeTruthy();
    expect(screen.getByText('1 Check(s) im letzten Run sind fehlgeschlagen.')).toBeTruthy();
  });

  it('appears when the object has no contract', () => {
    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByLabelText('Aufmerksamkeitsband')).toBeTruthy();
    expect(screen.getByText('Contract fehlt')).toBeTruthy();
  });

  it('appears when monitoring is enabled but the object is not provisioned', () => {
    state.contract = activeContract;
    state.monitoringEnabled = true;

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByLabelText('Aufmerksamkeitsband')).toBeTruthy();
    expect(screen.getByText('Monitoring nicht vorgemerkt')).toBeTruthy();
  });

  it('appears when monitoring provisioning failed', () => {
    state.contract = activeContract;
    state.monitoringEnabled = true;
    state.monitoringShares = [{
      object_id: 'Sales_Orders_View',
      status: 'error',
      view: null,
      error: 'MON_VIEW konnte nicht erstellt werden',
    }];

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByLabelText('Aufmerksamkeitsband')).toBeTruthy();
    expect(screen.getByText('Monitoring-Fehler')).toBeTruthy();
    expect(screen.getAllByText('MON_VIEW konnte nicht erstellt werden').length).toBeGreaterThan(0);
  });

  it('appears when the contract version diff is breaking', () => {
    state.contract = activeContract;
    state.versionDiff = {
      available: true,
      from_version: '1.1.0',
      to_version: '1.2.0',
      breaking: true,
      entries: [{ kind: 'removed_column', path: 'guarantees.schema.columns', breaking: true }],
    };

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getByLabelText('Aufmerksamkeitsband')).toBeTruthy();
    expect(screen.getByText('Breaking Contract-Diff')).toBeTruthy();
  });

  it('does not appear from the hero health status alone', () => {
    state.object.status = 'fail';
    state.contract = activeContract;
    state.versionDiff = {
      available: true,
      from_version: '1.1.0',
      to_version: '1.2.0',
      breaking: false,
      entries: [],
    };

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getAllByText('Fehlgeschlagen').length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Aufmerksamkeitsband')).toBeNull();
  });

  it('collapses multiple triggers into one compact summary', () => {
    state.monitoringEnabled = true;
    state.runs = [finishedRun];
    state.runDetail = {
      ...finishedRun,
      schema_name: 'SALES',
      contract_version: '',
      actor: 'test',
      results: [failedResult],
    };

    renderObjectDetail('/objects/Sales_Orders_View');

    expect(screen.getAllByLabelText('Aufmerksamkeitsband')).toHaveLength(1);
    expect(screen.getByText('3 Punkte brauchen Aufmerksamkeit')).toBeTruthy();
    expect(screen.getByText('Checks fehlgeschlagen')).toBeTruthy();
    expect(screen.getByText('Contract fehlt')).toBeTruthy();
    expect(screen.getByText('Monitoring nicht vorgemerkt')).toBeTruthy();
  });
});
