import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ObjectDiffPanel } from '@/components/ObjectDiffPanel';
import type { ObjectDiffResult } from '@/types';

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  data: undefined as ObjectDiffResult | undefined,
  isError: false,
}));

vi.mock('@/api/objects', () => ({
  useObjectDiff: () => ({ mutate: state.mutate, data: state.data, isPending: false, isError: state.isError }),
}));

const distResult: ObjectDiffResult = {
  object_id: 'DS_SALES_ORDERS', mode: 'distribution',
  base: { snapshot_id: 1, captured_at: '', environment: '' },
  head: { snapshot_id: 2, captured_at: '', environment: '' },
  distribution: {
    row_count: { base: 1000, head: 900, delta: -100, pct_delta: -10 },
    column_count: { base: 2, head: 2, delta: 0 },
    columns: [{ column: 'AMT', metrics: { null_pct: { base: 0.1, head: 5, delta: 4.9 } }, changed: true }],
    added_columns: [], removed_columns: [], changed_columns: ['AMT'],
  },
};

describe('ObjectDiffPanel', () => {
  it('triggers a diff computation on demand', () => {
    state.data = undefined; state.isError = false;
    render(<ObjectDiffPanel objectId="DS_SALES_ORDERS" />);
    fireEvent.click(screen.getByText(/Diff berechnen/i));
    expect(state.mutate).toHaveBeenCalledWith({ mode: 'distribution' });
  });

  it('shows the needTwo hint when the diff errors', () => {
    state.data = undefined; state.isError = true;
    render(<ObjectDiffPanel objectId="DS_SALES_ORDERS" />);
    expect(screen.getByText(/zwei Profil-Snapshots/i)).toBeTruthy();
  });

  it('renders distribution deltas for changed columns', () => {
    state.isError = false; state.data = distResult;
    render(<ObjectDiffPanel objectId="DS_SALES_ORDERS" />);
    expect(screen.getByText('AMT')).toBeTruthy();
    expect(screen.getByText(/NULL-%/)).toBeTruthy();
  });
});
