import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ColumnLineagePanel } from '@/components/lineage/ColumnLineagePanel';

const state = vi.hoisted(() => ({
  isLoading: false,
}));

vi.mock('@/api/lineage', () => ({
  useColumnLineage: () => ({
    data: {
      object: 'DEMO_BUS_01',
      columns: {
        BUS_COL_03: {
          upstream: [{ object: 'DEMO_BUS_05', column: 'BUS_COL_03', edgeType: 'computed', expression: 'SUM(b5.BUS_COL_03)' }],
          downstream: [{ object: 'DEMO_BUS_02', column: 'BUS_COL_03', edgeType: 'computed' }],
        },
        BUS_COL_01: { upstream: [], downstream: [] },
      },
    },
    isLoading: state.isLoading,
  }),
  useColumnImpact: (_obj: string, column: string | undefined) => ({
    data: column === 'BUS_COL_03' ? {
      object: 'DEMO_BUS_01',
      column: 'BUS_COL_03',
      impacted: [
        { object: 'DEMO_BUS_02', column: 'BUS_COL_03', edgeType: 'computed', depth: 1,
          ownedBy: 'product', owners: ['team-c'], coverageFlag: '▲', dqStatus: 'unknown' },
      ],
      totalImpacted: 1,
      maxDepth: 1,
      truncated: false,
    } : { object: 'DEMO_BUS_01', column, impacted: [], totalImpacted: 0, maxDepth: 0, truncated: false },
  }),
}));

describe('ColumnLineagePanel', () => {
  beforeEach(() => {
    state.isLoading = false;
  });

  it('shows a local skeleton while column lineage loads', () => {
    state.isLoading = true;

    render(<ColumnLineagePanel objectId="DEMO_BUS_01" />);

    expect(screen.getByTestId('column-lineage-skeleton')).toBeTruthy();
    expect(screen.queryByText('Lade Spalten-Lineage…')).toBeNull();
  });

  it('renders upstream/downstream and the impact list for the first column', () => {
    render(<ColumnLineagePanel objectId="DEMO_BUS_01" />);
    // upstream + downstream sources rendered
    expect(screen.getByText('DEMO_BUS_05')).toBeTruthy();
    expect(screen.getAllByText('DEMO_BUS_02').length).toBeGreaterThan(0);
    // impact row with ownership
    expect(screen.getByText('product')).toBeTruthy();
    expect(screen.getAllByText(/berechnet/i).length).toBeGreaterThan(0);
  });

  it('shows the empty impact state for a column with no downstream', () => {
    render(<ColumnLineagePanel objectId="DEMO_BUS_01" />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'BUS_COL_01' } });
    expect(screen.getByText(/Keine Downstream-Consumer betroffen/i)).toBeTruthy();
  });
});
