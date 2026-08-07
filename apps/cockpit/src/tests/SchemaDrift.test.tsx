import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { SchemaDriftObjectRow, SchemaEvolutionOut } from '@/types';

const data = vi.hoisted(() => ({
  overview: [] as SchemaDriftObjectRow[],
  overviewLoading: false,
  overviewError: false,
  overviewRefetch: vi.fn(),
  evolution: undefined as SchemaEvolutionOut | undefined,
  evolutionLoading: false,
  evolutionError: false,
}));

vi.mock('@/api/schemaDrift', () => ({
  useSchemaDriftOverview: () => ({
    data: data.overview,
    isLoading: data.overviewLoading,
    isError: data.overviewError,
    refetch: data.overviewRefetch,
  }),
  useSchemaEvolution: () => ({
    data: data.evolution,
    isLoading: data.evolutionLoading,
    isError: data.evolutionError,
    refetch: vi.fn(),
  }),
}));

import SchemaDrift from '@/pages/SchemaDrift';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
}

function row(over: Partial<SchemaDriftObjectRow> = {}): SchemaDriftObjectRow {
  return {
    object_name: 'DS_SALES_ORDERS',
    snapshots: 3,
    first_captured_at: '2026-07-01T06:00:00Z',
    last_captured_at: '2026-08-01T06:00:00Z',
    distinct_schemas: 2,
    findings: 1,
    breaking: 1,
    last_detected_at: '2026-08-01T06:00:00Z',
    last_incident_id: 3,
    column_count: 4,
    product: 'DS_SALES_ORDERS',
    kind: 'consumer_contract',
    contract_version: '2.0.0',
    lifecycle: 'active',
    ...over,
  };
}

function evolution(): SchemaEvolutionOut {
  return {
    object_name: 'DS_SALES_ORDERS',
    contract: { product: 'DS_SALES_ORDERS', version: '2.0.0', kind: 'consumer_contract', lifecycle: 'active' },
    snapshots: [
      { id: 1, captured_at: '2026-07-01T06:00:00Z', inventory_hash: 'h1', column_count: 4 },
      { id: 2, captured_at: '2026-08-01T06:00:00Z', inventory_hash: 'h2', column_count: 4 },
    ],
    steps: [{
      from_id: 1, to_id: 2,
      from_at: '2026-07-01T06:00:00Z', to_at: '2026-08-01T06:00:00Z',
      changes: [
        { category: 'column_added', column: 'NEW_COL', before: '', after: 'NEW_COL' },
        { category: 'column_removed', column: 'OLD_COL', before: 'OLD_COL', after: '' },
      ],
    }],
    drift_events: [{
      id: 9, object_name: 'DS_SALES_ORDERS', detected_at: '2026-08-01T06:00:00Z',
      category: 'column_removed', column_name: 'OLD_COL', before_value: 'OLD_COL',
      after_value: '', breaking: 1, contract_version: '2.0.0', incident_id: 3,
    }],
    latest_columns: [{ name: 'A' }, { name: 'B' }],
  };
}

function resetData() {
  data.overview = [row()];
  data.overviewLoading = false;
  data.overviewError = false;
  data.overviewRefetch.mockClear();
  data.evolution = evolution();
  data.evolutionLoading = false;
  data.evolutionError = false;
}

function renderPage(route = '/schema-drift') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/schema-drift" element={<><SchemaDrift /><LocationEcho /></>} />
        <Route path="/incidents" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SchemaDrift', () => {
  beforeEach(() => {
    resetData();
  });

  it('renders the overview with contract binding and breaking badge', () => {
    renderPage();

    expect(screen.getByText(t.schemaDrift.title)).toBeInTheDocument();
    expect(screen.getByText('DS_SALES_ORDERS')).toBeInTheDocument();
    expect(screen.getByText(/DS_SALES_ORDERS v2\.0\.0/)).toBeInTheDocument();
    expect(screen.getAllByText(t.drift.breakingBadge).length).toBeGreaterThan(0);
    expect(screen.getByText(t.schemaDrift.selectHint)).toBeInTheDocument();
  });

  it('drills into the evolution of a selected object', () => {
    renderPage();

    fireEvent.click(screen.getByText('DS_SALES_ORDERS'));

    expect(screen.getByText(t.schemaDrift.detailTitle.replace('{object}', 'DS_SALES_ORDERS'))).toBeInTheDocument();
    // Snapshot→Snapshot-Schritt: hinzugefügte/entfernte Spalten
    expect(screen.getAllByText('NEW_COL').length).toBeGreaterThan(0);
    expect(screen.getByText(t.drift.categories.column_added)).toBeInTheDocument();
    // Contract-Bruch: Drift-Event-Tabelle mit Incident-Referenz
    expect(screen.getByText(t.schemaDrift.eventsTitle)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /#3/ })).toBeInTheDocument();
  });

  it('deep-links a drift incident to the incidents inbox', () => {
    renderPage('/schema-drift?object=DS_SALES_ORDERS');

    fireEvent.click(screen.getByRole('button', { name: /#3/ }));

    expect(screen.getByTestId('location')).toHaveTextContent('/incidents');
    expect(screen.getByTestId('location')).toHaveTextContent('id=3');
  });

  it('shows the stable message when snapshots never changed', () => {
    data.evolution = { ...evolution(), steps: [], drift_events: [] };
    renderPage('/schema-drift?object=DS_SALES_ORDERS');

    expect(screen.getByText(t.schemaDrift.noSteps)).toBeInTheDocument();
    expect(screen.getByText(t.schemaDrift.noEvents)).toBeInTheDocument();
  });

  it('keeps the empty state visible without history', () => {
    data.overview = [];
    renderPage();

    expect(screen.getByText(t.schemaDrift.empty)).toBeInTheDocument();
  });

  it('shows a retry banner on overview errors', () => {
    data.overviewError = true;
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: t.common.retry }));
    expect(data.overviewRefetch).toHaveBeenCalledTimes(1);
  });
});
