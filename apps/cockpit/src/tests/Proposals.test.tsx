import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { Proposal } from '@/types';

const data = vi.hoisted(() => ({
  proposals: [] as Proposal[],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  actionMutate: vi.fn(),
}));

vi.mock('@/api/proposals', () => ({
  useProposals: () => ({
    data: data.proposals,
    isLoading: data.isLoading,
    isError: data.isError,
    refetch: data.refetch,
  }),
  useProposalAction: () => ({
    mutate: data.actionMutate,
  }),
}));

vi.mock('@/store/role', () => ({
  useRoleStore: (selector: (state: { role: string }) => unknown) => selector({ role: 'steward' }),
  canAcceptProposal: () => true,
}));

// BacktestBadge (V1) zieht sonst echtes react-query ohne Provider.
vi.mock('@/api/contracts', () => ({
  useExpectationBacktest: () => ({ data: undefined, isError: false }),
}));

import Proposals from '@/pages/Proposals';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function resetData() {
  data.proposals = [
    {
      id: 'open-gate',
      product: 'DS_GATE',
      check_name: 'gate_open_check',
      current_expect: '>= 10',
      proposed_expect: '>= 20',
      rationale: 'Gate proposal.',
      confidence: 0.93,
      status: 'open',
      kind: 'internal_gate',
      stats: { n: 10, min: 10, max: 30, mean: 20, p01: 10, p99: 30, stddev: 3 },
    },
    {
      id: 'open-contract',
      product: 'DS_CONTRACT',
      check_name: 'contract_open_check',
      current_expect: '<= 100',
      proposed_expect: '<= 80',
      rationale: 'Contract proposal.',
      confidence: 0.82,
      status: 'open',
      kind: 'consumer_contract',
    },
    {
      id: 'accepted',
      product: 'DS_REVIEWED',
      check_name: 'accepted_check',
      current_expect: '>= 1',
      proposed_expect: '>= 2',
      rationale: 'Accepted proposal.',
      confidence: 0.7,
      status: 'accepted',
      kind: 'internal_gate',
    },
    {
      id: 'rejected',
      product: 'DS_REVIEWED',
      check_name: 'rejected_check',
      current_expect: '>= 1',
      proposed_expect: '>= 3',
      rationale: 'Rejected proposal.',
      confidence: 0.6,
      status: 'rejected',
      kind: 'consumer_contract',
    },
    {
      id: 'snoozed',
      product: 'DS_REVIEWED',
      check_name: 'snoozed_check',
      current_expect: '<= 10',
      proposed_expect: '<= 9',
      rationale: 'Snoozed proposal.',
      confidence: 0.5,
      status: 'snoozed',
      kind: 'internal_gate',
    },
  ];
  data.isLoading = false;
  data.isError = false;
  data.refetch.mockClear();
  data.actionMutate.mockClear();
}

function renderProposals(route = '/proposals') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/proposals" element={<><Proposals /><LocationEcho /></>} />
        <Route path="/contracts" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Proposals', () => {
  beforeEach(() => {
    resetData();
  });

  it('hydrates groupBy from the URL', () => {
    renderProposals('/proposals?groupBy=kind');

    expect(screen.getByRole('button', { name: t.proposals.groupBy.kind })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText(t.proposals.kindLabel.internal_gate).length).toBeGreaterThan(0);
    expect(screen.getAllByText(t.proposals.kindLabel.contract).length).toBeGreaterThan(0);
  });

  it('syncs groupBy changes into the URL', () => {
    renderProposals();

    fireEvent.click(screen.getByRole('button', { name: t.proposals.groupBy.kind }));

    expect(screen.getByTestId('location')).toHaveTextContent('groupBy=kind');
  });

  it('defaults to open proposals only', () => {
    renderProposals();

    expect(screen.getByRole('button', { name: t.proposals.statusFilter.open })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('gate_open_check')).toBeInTheDocument();
    expect(screen.getByText('contract_open_check')).toBeInTheDocument();
    expect(screen.queryByText('accepted_check')).not.toBeInTheDocument();
    expect(screen.queryByText('rejected_check')).not.toBeInTheDocument();
  });

  it('filters reviewed proposals through the status chip and URL', () => {
    renderProposals();

    fireEvent.click(screen.getByRole('button', { name: t.proposals.statusFilter.reviewed }));

    expect(screen.getByTestId('location')).toHaveTextContent('status=reviewed');
    expect(screen.queryByText('gate_open_check')).not.toBeInTheDocument();
    expect(screen.queryByText('contract_open_check')).not.toBeInTheDocument();
    expect(screen.getByText('accepted_check')).toBeInTheDocument();
    expect(screen.getByText('rejected_check')).toBeInTheDocument();
    expect(screen.getByText('snoozed_check')).toBeInTheDocument();
  });

  it('filters to a single object via ?product= and clears it', () => {
    renderProposals('/proposals?product=DS_GATE');

    expect(screen.getByText('gate_open_check')).toBeInTheDocument();
    expect(screen.queryByText('contract_open_check')).not.toBeInTheDocument();

    // Aktiv-Filter-Chip nennt das Objekt und lässt sich einzeln löschen.
    fireEvent.click(screen.getByLabelText(new RegExp('DS_GATE')));
    expect(screen.getByTestId('location')).not.toHaveTextContent('product=DS_GATE');
    expect(screen.getByText('contract_open_check')).toBeInTheDocument();
  });

  it('uses skeleton cards while loading', () => {
    data.isLoading = true;
    renderProposals();

    expect(screen.queryByText(t.common.loading)).not.toBeInTheDocument();
    expect(screen.getAllByTestId('proposal-card-skeleton').length).toBeGreaterThan(0);
  });

  it('keeps open proposal affordances visible', () => {
    renderProposals();

    expect(screen.getByRole('button', { name: t.proposals.accept })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.proposals.reviewInContract })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: t.proposals.snooze })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: t.proposals.reject })).toHaveLength(2);
  });
});
