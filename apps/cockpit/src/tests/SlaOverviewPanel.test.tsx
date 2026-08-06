import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// SLA-Übersichts-Panel: je aktivem Boundary-Contract eine Zeile mit aktuellem
// Compliance-Status (StatusPill) und den 7/30/90-Tage-Fenstern, Zeilenklick →
// Objektdetail, Leerzustand ohne aktive Contracts.
const slaByProduct = vi.hoisted(() => ({} as Record<string, unknown>));

vi.mock('@/api/contracts', () => ({
  // Die Zeile ruft useContractSla(product); wir liefern je Produkt einen Datensatz.
  useContractSla: (product: string) => ({ data: slaByProduct[product] }),
}));

import { SlaOverviewPanel } from '@/components/compliance/SlaOverviewPanel';
import type { Contract } from '@/types';

const contract = (over: Partial<Contract>): Contract =>
  ({ product: 'P', kind: 'consumer_contract', lifecycle: 'active', version: '1.0.0', ...over }) as Contract;

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPanel(contracts: Contract[]) {
  render(
    <MemoryRouter initialEntries={['/compliance']}>
      <Routes>
        <Route path="/compliance" element={<><SlaOverviewPanel contracts={contracts} /><LocationEcho /></>} />
        <Route path="/objects/:id" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SlaOverviewPanel', () => {
  beforeEach(() => {
    for (const k of Object.keys(slaByProduct)) delete slaByProduct[k];
  });

  it('renders one row per contract with status and window percentages', () => {
    slaByProduct.SALES_ORDERS = { product: 'SALES_ORDERS', kind: 'consumer_contract', current: 'compliant', windows: { '7d': 99.8, '30d': 99.1, '90d': 98.4 } };
    slaByProduct.FIN_LEDGER = { product: 'FIN_LEDGER', kind: 'consumer_contract', current: 'breached', windows: { '7d': 94.2, '30d': 96.0, '90d': 97.3 } };
    renderPanel([contract({ product: 'SALES_ORDERS' }), contract({ product: 'FIN_LEDGER' })]);

    const sales = within(screen.getByText('SALES_ORDERS').closest('tr')!);
    expect(sales.getByText('Konform')).toBeInTheDocument();
    expect(sales.getByText('99.8 %')).toBeInTheDocument();
    expect(sales.getByText('99.1 %')).toBeInTheDocument();
    expect(sales.getByText('98.4 %')).toBeInTheDocument();

    const fin = within(screen.getByText('FIN_LEDGER').closest('tr')!);
    expect(fin.getByText('Verletzt')).toBeInTheDocument();
    expect(fin.getByText('94.2 %')).toBeInTheDocument();
  });

  it('sorts rows by product name for stability', () => {
    slaByProduct.SALES_ORDERS = { current: 'compliant', windows: { '7d': null, '30d': null, '90d': null } };
    slaByProduct.FIN_LEDGER = { current: 'compliant', windows: { '7d': null, '30d': null, '90d': null } };
    renderPanel([contract({ product: 'SALES_ORDERS' }), contract({ product: 'FIN_LEDGER' })]);

    const products = Array.from(document.querySelectorAll('tbody tr td:first-child')).map(td => td.textContent);
    expect(products).toEqual(['FIN_LEDGER', 'SALES_ORDERS']);
  });

  it('shows "keine Daten" when a window has no compliance events', () => {
    slaByProduct.SALES_ORDERS = { current: 'unknown', windows: { '7d': null, '30d': 99.1, '90d': null } };
    renderPanel([contract({ product: 'SALES_ORDERS' })]);

    const row = within(screen.getByText('SALES_ORDERS').closest('tr')!);
    expect(row.getAllByText('keine Daten').length).toBe(2);
    expect(row.getByText('99.1 %')).toBeInTheDocument();
  });

  it('navigates to the object detail on row click', () => {
    slaByProduct.SALES_ORDERS = { current: 'compliant', windows: { '7d': 99.8, '30d': 99.1, '90d': 98.4 } };
    renderPanel([contract({ product: 'SALES_ORDERS' })]);

    fireEvent.click(screen.getByText('SALES_ORDERS').closest('tr')!);
    expect(screen.getByTestId('location')).toHaveTextContent('/objects/SALES_ORDERS');
  });

  it('shows the empty state when there are no active contracts', () => {
    renderPanel([]);
    expect(screen.getByText('Keine aktiven Contracts')).toBeInTheDocument();
  });
});
