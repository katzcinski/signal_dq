import { render, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { Table, type ColDef } from '@/components/ui/Table';

interface Row { id: string; n: number }
const rows: Row[] = [{ id: 'b', n: 3 }, { id: 'a', n: 1 }, { id: 'c', n: 2 }];
const columns: ColDef<Row>[] = [
  { key: 'id', header: 'ID', sortable: true, sortValue: r => r.id, render: r => r.id },
  { key: 'n', header: 'N', sortable: true, sortValue: r => r.n, render: r => String(r.n) },
];

function order(container: HTMLElement): string[] {
  return [...container.querySelectorAll('tbody tr')].map(tr => tr.querySelector('td')!.textContent!);
}

describe('Table sorting (R6-6)', () => {
  it('sorts ascending then descending then clears on repeated header clicks', () => {
    const { container, getByText } = render(<Table columns={columns} rows={rows} rowKey={r => r.id} />);
    expect(order(container)).toEqual(['b', 'a', 'c']); // original order

    fireEvent.click(getByText('ID'));
    expect(order(container)).toEqual(['a', 'b', 'c']); // asc

    fireEvent.click(getByText('ID'));
    expect(order(container)).toEqual(['c', 'b', 'a']); // desc

    fireEvent.click(getByText('ID'));
    expect(order(container)).toEqual(['b', 'a', 'c']); // cleared → original
  });

  it('renders the empty node when there are no rows', () => {
    const { getByText } = render(<Table columns={columns} rows={[]} rowKey={r => r.id} empty="Nothing here" />);
    expect(getByText('Nothing here')).toBeTruthy();
  });
});

// L5: ab virtualizeThreshold werden Zeilen gefenstert gerendert (Scroll-Spacer
// statt DOM-Knoten) — Regressions-Schutz für große Kataloge/Tenants.
describe('Table virtualization (L5)', () => {
  const many: Row[] = Array.from({ length: 250 }, (_, i) => ({
    id: `row-${String(i).padStart(3, '0')}`, n: i,
  }));

  // jsdom misst 0×0 — der Virtualizer liest offsetWidth/offsetHeight des
  // Scroll-Containers, also dort eine reale Viewport-Höhe vortäuschen.
  const offsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
  const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 400 });
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 });
  });

  afterEach(() => {
    if (offsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', offsetHeight);
    if (offsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', offsetWidth);
    vi.restoreAllMocks();
  });

  it('renders every row below the threshold', () => {
    const { container } = render(
      <Table columns={columns} rows={many.slice(0, 50)} rowKey={r => r.id} />,
    );
    expect(container.querySelectorAll('tbody tr')).toHaveLength(50);
  });

  it('windows the body above the threshold instead of rendering all rows', () => {
    const { container } = render(
      <Table columns={columns} rows={many} rowKey={r => r.id} virtualizeThreshold={80} />,
    );
    // Gefenstert: deutlich weniger <tr> als Datenzeilen (sichtbares Fenster +
    // Overscan + Spacer), niemals alle 250.
    const rendered = container.querySelectorAll('tbody tr').length;
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(250);
    // Scroll-Container mit begrenzter Höhe existiert.
    expect(container.querySelector('div[style*="overflow-y: auto"]')).toBeTruthy();
  });

  it('keeps sorting functional in the virtualized mode', () => {
    const { container, getByText } = render(
      <Table columns={columns} rows={many} rowKey={r => r.id} virtualizeThreshold={80} />,
    );
    fireEvent.click(getByText('N'));
    fireEvent.click(getByText('N')); // desc
    const first = container.querySelector('tbody tr td')?.textContent;
    expect(first).toBe('row-249');
  });
});
