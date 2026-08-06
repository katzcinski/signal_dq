import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { BacktestOut, ContractPutBody } from '@/types';

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  data: undefined as BacktestOut | undefined,
  isPending: false,
  isError: false,
  queryData: undefined as BacktestOut | undefined,
  queryError: false,
}));

vi.mock('@/api/contracts', () => ({
  useBacktestContract: () => ({
    mutate: state.mutate,
    data: state.data,
    isPending: state.isPending,
    isError: state.isError,
  }),
  useExpectationBacktest: () => ({
    data: state.queryData,
    isError: state.queryError,
  }),
}));

import { BacktestPanel } from '@/components/workbench/BacktestPanel';
import { BacktestBadge } from '@/components/BacktestBadge';

const DRAFT: ContractPutBody = {
  product: 'DS_SALES_ORDERS', dataset: 'DS_SALES_ORDERS',
  version: '1.0.0', kind: 'internal_gate', lifecycle: 'draft',
  guarantees: { volume: { min_rows: 1000 } },
} as unknown as ContractPutBody;

function result(over: Partial<BacktestOut> = {}): BacktestOut {
  return {
    product: 'DS_SALES_ORDERS', dataset: 'DS_SALES_ORDERS',
    window_days: [30, 90],
    checks: [{
      check_name: 'volume_min_rows', expect: '>= 1000', type: 'row_count', severity: 'fail',
      points: 12, evaluated: 12, skipped: 0, breaches: 3, breach_rate: 0.25,
      first_breach_at: '2026-06-01T06:00:00Z', last_breach_at: '2026-08-01T06:00:00Z',
      sample: [],
      windows: [
        { days: 30, points: 5, breaches: 1 },
        { days: 90, points: 12, breaches: 3 },
      ],
    }],
    checks_total: 1,
    checks_with_history: 1,
    summary_windows: [
      { days: 30, breaches: 1, checks_firing: 1 },
      { days: 90, breaches: 3, checks_firing: 1 },
    ],
    ...over,
  };
}

function resetState() {
  state.mutate.mockClear();
  state.data = undefined;
  state.isPending = false;
  state.isError = false;
  state.queryData = undefined;
  state.queryError = false;
}

describe('BacktestPanel', () => {
  beforeEach(resetState);

  it('triggers the backtest with the current draft', () => {
    render(<BacktestPanel product="DS_SALES_ORDERS" draft={DRAFT} />);

    fireEvent.click(screen.getByRole('button', { name: t.backtest.run }));
    expect(state.mutate).toHaveBeenCalledWith(DRAFT);
  });

  it('renders per-check breach counts and the firing summary', () => {
    state.data = result();
    render(<BacktestPanel product="DS_SALES_ORDERS" draft={DRAFT} />);

    expect(screen.getByText('volume_min_rows')).toBeInTheDocument();
    expect(screen.getByText('>= 1000')).toBeInTheDocument();
    // 90d-Fenster: 3 Verstöße, Zusammenfassung nennt sie
    expect(screen.getByText(/3 Verstöße in 90 Tagen/)).toBeInTheDocument();
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('shows the calm summary when nothing would have fired', () => {
    const clean = result();
    clean.checks[0] = {
      ...clean.checks[0], breaches: 0, breach_rate: 0,
      first_breach_at: null, last_breach_at: null,
      windows: [{ days: 30, points: 5, breaches: 0 }, { days: 90, points: 12, breaches: 0 }],
    };
    clean.summary_windows = [
      { days: 30, breaches: 0, checks_firing: 0 },
      { days: 90, breaches: 0, checks_firing: 0 },
    ];
    state.data = clean;
    render(<BacktestPanel product="DS_SALES_ORDERS" draft={DRAFT} />);

    expect(screen.getByText(t.backtest.summaryClean.replace('{days}', '90'))).toBeInTheDocument();
  });

  it('hints when there is no history yet', () => {
    state.data = result({ checks_with_history: 0 });
    render(<BacktestPanel product="DS_SALES_ORDERS" draft={DRAFT} />);

    expect(screen.getByText(t.backtest.noHistory)).toBeInTheDocument();
  });
});

describe('BacktestBadge', () => {
  beforeEach(resetState);

  it('shows the would-have-fired count for the proposed expectation', () => {
    state.queryData = result();
    render(<BacktestBadge product="DS_SALES_ORDERS" checkName="volume_min_rows" expect=">= 1000" />);

    expect(screen.getByText(
      t.backtest.badge.replace('{n}', '3').replace('{days}', '90'),
    )).toBeInTheDocument();
  });

  it('renders the no-data badge without history and nothing on error', () => {
    state.queryData = result({
      checks: [{ ...result().checks[0], points: 0 }],
      checks_with_history: 0,
    });
    render(<BacktestBadge product="DS_SALES_ORDERS" checkName="volume_min_rows" expect=">= 1000" />);
    expect(screen.getByText(t.backtest.badgeNoData)).toBeInTheDocument();

    state.queryError = true;
    state.queryData = undefined;
    const { container } = render(
      <BacktestBadge product="DS_SALES_ORDERS" checkName="volume_min_rows" expect=">= 1000" />,
    );
    expect(container.firstChild).toBeNull();
  });
});
