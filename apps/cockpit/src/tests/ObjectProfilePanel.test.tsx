import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ObjectProfilePanel } from '@/components/ObjectProfilePanel';
import { useRoleStore } from '@/store/role';
import type { ObjectProfileResult, OperationStatus } from '@/types';

const apiMock = vi.hoisted(() => ({
  mutate: vi.fn(),
  state: {
    operation: null as OperationStatus<ObjectProfileResult> | null,
    isPending: false,
    isError: false,
    error: null as unknown,
  },
}));

vi.mock('@/api/objects', () => ({
  useEnvironments: () => ({
    data: { environments: [{ name: 'prod', schema: 'CORE_DWH' }] },
    isLoading: false,
  }),
  useObjectProfile: () => ({
    mutate: apiMock.mutate,
    data: null,
    isPending: apiMock.state.isPending,
    isError: apiMock.state.isError,
    error: apiMock.state.error,
  }),
}));

vi.mock('@/api/operations', () => ({
  useOperation: () => ({ data: apiMock.state.operation }),
  useOperationStream: () => ({ data: apiMock.state.operation }),
}));

const profileResult: ObjectProfileResult = {
  schema: 'CORE_DWH',
  table: 'DS_SALES_ORDERS',
  row_count: 100,
  column_count: 2,
  columns: [
    {
      column: 'ORDER_ID',
      data_type: 'NVARCHAR',
      total: 100,
      nulls: 0,
      null_pct: 0,
      distinct: 100,
      uniqueness_pct: 100,
      pk_candidate: true,
      empty_pct: 0,
    },
    {
      column: 'NET_AMOUNT',
      data_type: 'DECIMAL',
      total: 100,
      nulls: 1,
      null_pct: 1,
      distinct: 80,
      uniqueness_pct: 80,
      pk_candidate: false,
      avg: 42.5,
    },
  ],
  pk_candidates: {
    single: ['ORDER_ID'],
    ranked_single: [{
      column: 'ORDER_ID',
      exact: true,
      uniqueness_pct: 100,
      rank_reason: 'Distinct = row count, no NULLs',
      final_score: 98,
      technical_score: 100,
      business_score: 95,
    }],
    ranked_composite: [{
      columns: ['ORDER_ID', 'NET_AMOUNT'],
      exact: false,
      uniqueness_pct: 100,
      rank_reason: '100.00% unique',
      final_score: 72,
      technical_score: 80,
      business_score: 60,
    }],
  },
  issues: [{ column: 'NET_AMOUNT', type: 'completeness', detail: '1.0% NULLs' }],
  scores: { overall_key_confidence: 91 },
};

describe('ObjectProfilePanel', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mutate.mockReset();
    apiMock.state.operation = {
      op_id: 'op-1',
      kind: 'profile',
      state: 'finished',
      started_at: null,
      finished_at: null,
      result: profileResult,
      error: null,
      progress: [],
    };
    apiMock.state.isPending = false;
    apiMock.state.isError = false;
    apiMock.state.error = null;
    useRoleStore.setState({ role: 'steward' });
  });

  it('renders profile stats and key candidates', () => {
    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    expect(screen.getByText('Rows')).toBeTruthy();
    expect(screen.getAllByText('100').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ORDER_ID').length).toBeGreaterThan(0);
    expect(screen.getAllByText('NET_AMOUNT').length).toBeGreaterThan(0);
    expect(screen.getByText('Single-column key candidates')).toBeTruthy();
    expect(screen.getByText('Composite key candidates')).toBeTruthy();
  });

  it('posts the selected environment and composite flag', async () => {
    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    const button = screen.getByRole('button', { name: 'Run profile' });
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);

    expect(apiMock.mutate).toHaveBeenCalledWith({
      environment: 'prod',
      include_composite: true,
      include_samples: false,
      sample_limit: 20,
    }, expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it('requests sample rows only after the PII gate checkbox is enabled', async () => {
    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    fireEvent.click(screen.getByLabelText('Sample rows [PII-GATE]'));
    const button = screen.getByRole('button', { name: 'Run profile' });
    await waitFor(() => expect(button).not.toBeDisabled());
    fireEvent.click(button);

    expect(apiMock.mutate).toHaveBeenCalledWith({
      environment: 'prod',
      include_composite: true,
      include_samples: true,
      sample_limit: 20,
    }, expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it('renders PII-gated sample rows when the server returns them', () => {
    apiMock.state.operation = {
      ...apiMock.state.operation!,
      result: {
        ...profileResult,
        sample_rows: {
          enabled: true,
          columns: ['ORDER_ID', 'AMOUNT'],
          rows: [{ ORDER_ID: 'SO-1', AMOUNT: 1234.5 }],
        },
      },
    };

    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    expect(screen.getAllByText('Sample rows [PII-GATE]').length).toBe(2);
    expect(screen.getByText('SO-1')).toBeTruthy();
    expect(screen.getByText('1234.50')).toBeTruthy();
  });

  it('disables profiling for viewer role', () => {
    useRoleStore.setState({ role: 'viewer' });
    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    expect(screen.getByRole('button', { name: 'Run profile' })).toBeDisabled();
    expect(screen.getByText('Steward role or higher required.')).toBeTruthy();
  });

  it('shows server authorization errors', () => {
    apiMock.state.operation = null;
    apiMock.state.isError = true;
    apiMock.state.error = { response: { status: 403, data: { detail: 'Profiling requires steward role or higher.' } } };

    render(<ObjectProfilePanel objectId="DS_SALES_ORDERS" onClose={() => undefined} />);

    expect(screen.getByText('Profiling requires steward role or higher.')).toBeTruthy();
  });
});
