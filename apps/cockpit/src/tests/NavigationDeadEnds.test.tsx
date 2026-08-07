import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Sackgassen-Guard: 404-Catch-all + „nicht gefunden"-Ausgänge + verlinkte
// Findings + Show-more für Upstream-Risk. Deckt die vier Dead-Ends ab, aus denen
// man vorher nur über die Sidebar herauskam.

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

const state = vi.hoisted(() => ({
  product: undefined as unknown,
}));

vi.mock('@/api/products', () => ({
  useProduct: () => ({
    data: state.product,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

import ProductDetail from '@/pages/ProductDetail';
import NotFound from '@/pages/NotFound';

function baseProduct(overrides: Record<string, unknown> = {}) {
  return {
    product: 'sales_product',
    owners: ['team-sales'],
    lifecycle: 'active',
    own_health: 'pass',
    ports: [],
    interior: [],
    inbound_sources: [],
    upstream_risk: [],
    findings: [],
    subgraph: { nodes: [], edges: [] },
    ...overrides,
  };
}

function renderProduct() {
  render(
    <MemoryRouter initialEntries={['/products/sales_product']}>
      <Routes>
        <Route path="/products/:name" element={<ProductDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('404 catch-all page', () => {
  it('shows the requested path and an exit link home', () => {
    render(
      <MemoryRouter initialEntries={['/does/not/exist']}>
        <Routes>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Seite nicht gefunden')).toBeTruthy();
    expect(screen.getByText(/\/does\/not\/exist/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Zur Übersicht' }).getAttribute('href')).toBe('/');
    expect(screen.getByRole('link', { name: 'Zu den Objekten' }).getAttribute('href')).toBe('/objects');
  });
});

describe('ProductDetail dead-end fixes', () => {
  beforeEach(() => {
    state.product = undefined;
  });

  it('offers a way back when the product is not found', () => {
    state.product = undefined;
    renderProduct();

    expect(screen.getByText('Nicht gefunden')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Zu den Produkten' }).getAttribute('href')).toBe('/products');
    expect(screen.getByRole('link', { name: 'Zur Übersicht' }).getAttribute('href')).toBe('/');
  });

  it('opens the quick-checks popover from a finding object', () => {
    state.product = baseProduct({
      findings: [
        { finding_type: 'boundary_leak', scope: 'interior', object_id: 'DS_LEAK', detail: 'leaks upstream' },
      ],
    });
    renderProduct();

    expect(screen.queryByTestId('checks-popover')).toBeNull();
    fireEvent.click(screen.getByLabelText('Checks für DS_LEAK anzeigen'));
    expect(screen.getByTestId('checks-popover').textContent).toBe('DS_LEAK');
  });

  it('reveals hidden upstream-risk entries behind a show-more toggle', () => {
    state.product = baseProduct({
      upstream_risk: Array.from({ length: 6 }, (_, i) => ({
        product: `up_${i}`,
        pinned_version: '1.0.0',
        current_version: '1.1.0',
        compliance: null,
        upstream_breach: false,
        version_drift: true,
      })),
    });
    renderProduct();

    // Nur die ersten vier sind sichtbar, der Rest steckt hinter dem Toggle.
    expect(screen.getByText('up_3')).toBeTruthy();
    expect(screen.queryByText('up_4')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Alle 6 anzeigen' }));
    expect(screen.getByText('up_4')).toBeTruthy();
    expect(screen.getByText('up_5')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Weniger anzeigen' }));
    expect(screen.queryByText('up_4')).toBeNull();
  });
});
