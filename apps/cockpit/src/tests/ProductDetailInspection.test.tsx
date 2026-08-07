import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// Zwei-Ebenen-Inspektion auf der Produkt-Detailseite: Port- und Interior-Objekte
// öffnen das Quick-Checks-Popover statt den Produkt-Kontext direkt zu verlassen.
vi.mock('@/components/LineageMiniGraph', () => ({
  LineageMiniGraph: () => <div>Mini graph</div>,
}));
vi.mock('@/components/ObjectPeek', () => ({
  ObjectPeek: ({ objectId }: { objectId: string }) => <div data-testid="object-peek">{objectId}</div>,
}));
vi.mock('@/components/ObjectChecksPopover', () => ({
  ObjectChecksPopover: ({ objectId }: { objectId: string }) => (
    <div data-testid="checks-popover">{objectId}</div>
  ),
}));

vi.mock('@/api/products', () => ({
  useProduct: () => ({
    data: {
      product: 'sales_product',
      owners: ['team-sales'],
      lifecycle: 'active',
      own_health: 'pass',
      ports: [{
        dataset: 'DS_PRODUCT',
        kind: 'provider_contract',
        lifecycle: 'active',
        compliance: 'compliant',
        version: '1.0.0',
      }],
      interior: [{ id: 'INT_OBJ', layer: 'transform', role: 'stage', coverage_flag: 'covered' }],
      inbound_dependencies: [],
      inbound_sources: [],
      upstream_risk: [],
      findings: [],
      subgraph: { nodes: [], edges: [] },
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

import ProductDetail from '@/pages/ProductDetail';

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/products/sales_product']}>
      <Routes>
        <Route path="/products/:name" element={<ProductDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProductDetail two-level inspection', () => {
  it('opens the quick-checks popover from a published port', () => {
    renderPage();

    expect(screen.queryByTestId('checks-popover')).toBeNull();
    fireEvent.click(screen.getByLabelText('Checks für DS_PRODUCT anzeigen'));
    expect(screen.getByTestId('checks-popover').textContent).toBe('DS_PRODUCT');
    expect(screen.queryByTestId('object-peek')).toBeNull();
  });

  it('opens the quick-checks popover from an interior object', () => {
    renderPage();

    fireEvent.click(screen.getByLabelText('Checks für INT_OBJ anzeigen'));
    expect(screen.getByTestId('checks-popover').textContent).toBe('INT_OBJ');
  });
});
