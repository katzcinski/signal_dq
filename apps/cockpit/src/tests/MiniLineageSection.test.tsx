import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MiniLineageSection } from '@/components/object-detail/MiniLineageSection';
import type { LineageGraph } from '@/types';

const state = vi.hoisted(() => ({
  graph: { nodes: [], edges: [] } as LineageGraph,
  isLoading: false,
  scopes: [] as unknown[],
}));

vi.mock('@/api/lineage', () => ({
  useLineage: (scope: unknown) => {
    state.scopes.push(scope);
    return {
      data: state.graph,
      isLoading: state.isLoading,
    };
  },
}));

function renderMiniLineage() {
  return render(
    <MemoryRouter>
      <MiniLineageSection focusId="Sales_Orders_View" />
    </MemoryRouter>,
  );
}

describe('MiniLineageSection', () => {
  beforeEach(() => {
    state.graph = { nodes: [], edges: [] };
    state.isLoading = false;
    state.scopes = [];
  });

  it('renders a local skeleton while lineage is loading', () => {
    state.isLoading = true;

    renderMiniLineage();

    expect(screen.getByTestId('mini-lineage-skeleton')).toBeTruthy();
    expect(screen.queryByText('Lädt…')).toBeNull();
  });

  it('renders a real empty state when the one-hop graph has zero nodes', () => {
    state.graph = { nodes: [], edges: [] };

    renderMiniLineage();

    expect(screen.getByTestId('mini-lineage-sparse')).toBeTruthy();
    expect(screen.getByText('Keine Lineage-Knoten im aktuellen Extract')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Lineage Map/i })).toHaveAttribute(
      'href',
      '/lineage?focus=Sales_Orders_View',
    );
  });

  it('renders a focused sparse state for a single-node graph', () => {
    state.graph = {
      nodes: [{ id: 'Sales_Orders_View', label: 'Sales Orders', layer: 'consumption' }],
      edges: [],
    };

    renderMiniLineage();

    expect(screen.getByTestId('mini-lineage-sparse')).toBeTruthy();
    expect(screen.getByText('Nur dieses Objekt im aktuellen Ausschnitt')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Lineage Map/i })).toHaveAttribute(
      'href',
      '/lineage?focus=Sales_Orders_View',
    );
  });

  it('renders the normal mini DAG and full lineage link for connected graphs', () => {
    state.graph = {
      nodes: [
        { id: 'RAW_ORDERS', label: 'Raw Orders', layer: 'source' },
        { id: 'Sales_Orders_View', label: 'Sales Orders', layer: 'consumption' },
        { id: 'REVENUE_MART', label: 'Revenue Mart', layer: 'consumption' },
      ],
      edges: [
        { id: 'RAW_ORDERS->Sales_Orders_View', source: 'RAW_ORDERS', target: 'Sales_Orders_View' },
        { id: 'Sales_Orders_View->REVENUE_MART', source: 'Sales_Orders_View', target: 'REVENUE_MART' },
      ],
    };

    renderMiniLineage();

    expect(screen.getByTestId('mini-lineage-dag')).toBeTruthy();
    expect(state.scopes.at(-1)).toMatchObject({
      seeds: ['Sales_Orders_View'],
      depth: 20,
      enabled: true,
    });
    expect(screen.getByLabelText('Lineage: Sales_Orders_View')).toBeTruthy();
    expect(screen.queryByTestId('mini-lineage-sparse')).toBeNull();
    expect(screen.getByRole('link', { name: /Lineage Map/i })).toHaveAttribute(
      'href',
      '/lineage?focus=Sales_Orders_View',
    );
  });

  it('renders all reachable upstream and downstream object nodes', () => {
    state.graph = {
      nodes: [
        { id: 'RAW_STAGE', label: 'Raw Stage', layer: 'source' },
        { id: 'CURATED', label: 'Curated', layer: 'harmonization' },
        { id: 'COLUMN_ONLY', label: 'Column Only', layer: 'source' },
        { id: 'Sales_Orders_View', label: 'Sales Orders', layer: 'consumption' },
        { id: 'MART', label: 'Mart', layer: 'consumption' },
        { id: 'REPORT', label: 'Report', layer: 'consumption' },
      ],
      edges: [
        { id: 'RAW_STAGE->CURATED', source: 'RAW_STAGE', target: 'CURATED' },
        { id: 'CURATED->Sales_Orders_View', source: 'CURATED', target: 'Sales_Orders_View' },
        { id: 'Sales_Orders_View->MART', source: 'Sales_Orders_View', target: 'MART' },
        { id: 'MART->REPORT', source: 'MART', target: 'REPORT' },
      ],
      columnEdges: [
        {
          source: 'COLUMN_ONLY',
          sourceColumn: 'C1',
          target: 'Sales_Orders_View',
          targetColumn: 'C1',
          edgeType: 'direct',
        },
      ],
    };

    renderMiniLineage();

    expect(screen.getByTestId('mini-lineage-dag')).toBeTruthy();
    expect(screen.getByText('Raw Stage')).toBeTruthy();
    expect(screen.getByText('Curated')).toBeTruthy();
    expect(screen.getByText('Column Only')).toBeTruthy();
    expect(screen.getByText('Mart')).toBeTruthy();
    expect(screen.getByText('Report')).toBeTruthy();
  });
});
