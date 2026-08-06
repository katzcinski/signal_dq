import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Products from '@/pages/Products';

vi.mock('@/api/products', () => ({
  useProducts: () => ({
    data: [{
      product: 'sales_product',
      owners: ['team-sales'],
      port_count: 2,
      own_health: 'pass',
      upstream_risk_count: 0,
      finding_count: 0,
      lifecycle: 'active',
    }],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

describe('Products', () => {
  it('renders product names and health pills', () => {
    render(
      <MemoryRouter>
        <Products />
      </MemoryRouter>,
    );

    expect(screen.getByText('sales_product')).toBeTruthy();
    expect(screen.getByText('Bestanden')).toBeTruthy();
  });
});
