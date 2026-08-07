import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { Incident, ObjectSummary, Proposal } from '@/types';

type MyWorkObject = Pick<ObjectSummary, 'id' | 'name' | 'status'>;

const data = vi.hoisted(() => ({
  objects: [] as MyWorkObject[],
  incidents: [] as Incident[],
  proposals: [] as Proposal[],
  objectsLoading: false,
  incidentsLoading: false,
  proposalsLoading: false,
  objectsError: false,
  incidentsError: false,
  proposalsError: false,
  objectsRefetch: vi.fn(),
  incidentsRefetch: vi.fn(),
  proposalsRefetch: vi.fn(),
}));

vi.mock('@/api/objects', () => ({
  useObjects: () => ({
    data: data.objects,
    isLoading: data.objectsLoading,
    isError: data.objectsError,
    refetch: data.objectsRefetch,
  }),
}));

vi.mock('@/api/incidents', () => ({
  useIncidents: () => ({
    data: data.incidents,
    isLoading: data.incidentsLoading,
    isError: data.incidentsError,
    refetch: data.incidentsRefetch,
  }),
}));

vi.mock('@/api/proposals', () => ({
  useProposals: () => ({
    data: data.proposals,
    isLoading: data.proposalsLoading,
    isError: data.proposalsError,
    refetch: data.proposalsRefetch,
  }),
}));

import MyWork from '@/pages/MyWork';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}{location.search}</div>;
}

function resetData() {
  data.objects = [
    { id: 'DS_OK', name: 'DS_OK', status: 'pass' },
    { id: 'DS_BAD', name: 'DS_BAD', status: 'fail' },
  ];
  data.incidents = [
    {
      id: 11,
      product: 'DS_CONTRACT',
      run_id: 'run-11',
      severity: 'critical',
      status: 'open',
      owner: 'team-a',
      title: 'Critical contract breach',
      failed_checks: ['row_count'],
      opened_at: '2026-07-02T08:00:00Z',
      resolved_at: null,
      contract_version: '1.0.0',
      kind: 'consumer_contract',
    },
    {
      id: 12,
      product: 'DS_CONTRACT_2',
      run_id: 'run-12',
      severity: 'fail',
      status: 'acknowledged',
      owner: '',
      title: 'Acknowledged contract breach',
      failed_checks: ['freshness'],
      opened_at: '2026-07-02T07:00:00Z',
      resolved_at: null,
      contract_version: '1.0.0',
      kind: 'provider_contract',
    },
    {
      id: 13,
      product: 'DS_GATE',
      run_id: 'run-13',
      severity: 'warn',
      status: 'open',
      owner: 'platform',
      title: 'Engineering gate signal',
      failed_checks: ['volume'],
      opened_at: '2026-07-02T06:00:00Z',
      resolved_at: null,
      contract_version: '',
      kind: 'internal_gate',
    },
    {
      id: 14,
      product: 'DS_DONE',
      run_id: 'run-14',
      severity: 'critical',
      status: 'resolved',
      owner: 'team-a',
      title: 'Resolved incident',
      failed_checks: [],
      opened_at: '2026-07-01T06:00:00Z',
      resolved_at: '2026-07-01T07:00:00Z',
      contract_version: '1.0.0',
      kind: 'consumer_contract',
    },
  ];
  data.proposals = [
    {
      id: 'proposal-open',
      product: 'DS_CONTRACT',
      check_name: 'row_count_min',
      current_expect: '>= 10',
      proposed_expect: '>= 20',
      rationale: 'Observed stable minimum.',
      confidence: 0.91,
      status: 'open',
      kind: 'internal_gate',
    },
    {
      id: 'proposal-reviewed',
      product: 'DS_CONTRACT',
      check_name: 'freshness_reviewed',
      current_expect: '<= 10',
      proposed_expect: '<= 20',
      rationale: 'Already reviewed.',
      confidence: 0.5,
      status: 'accepted',
      kind: 'consumer_contract',
    },
  ];
  data.objectsLoading = false;
  data.incidentsLoading = false;
  data.proposalsLoading = false;
  data.objectsError = false;
  data.incidentsError = false;
  data.proposalsError = false;
  data.objectsRefetch.mockClear();
  data.incidentsRefetch.mockClear();
  data.proposalsRefetch.mockClear();
}

function renderMyWork(route = '/my') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/my" element={<><MyWork /><LocationEcho /></>} />
        <Route path="/incidents" element={<LocationEcho />} />
        <Route path="/proposals" element={<LocationEcho />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('MyWork', () => {
  beforeEach(() => {
    resetData();
  });

  it('renders attention summary counts', () => {
    renderMyWork();

    const summary = screen.getByLabelText(t.myWork.attentionAriaLabel);
    expect(within(summary).getByRole('button', { name: new RegExp(`1.*${t.myWork.attentionCriticalAssigned}`) })).toBeInTheDocument();
    expect(within(summary).getByRole('button', { name: new RegExp(`2.*${t.myWork.attentionContractBreaches}`) })).toBeInTheDocument();
    expect(within(summary).getByRole('button', { name: new RegExp(`1.*${t.myWork.attentionEngineeringSignals}`) })).toBeInTheDocument();
    expect(within(summary).getByRole('button', { name: new RegExp(`1.*${t.myWork.attentionOpenProposals}`) })).toBeInTheDocument();
  });

  it('navigates incident rows to an id deep link', () => {
    renderMyWork();

    fireEvent.click(screen.getAllByText('Critical contract breach')[0]);

    expect(screen.getByTestId('location')).toHaveTextContent('/incidents');
    expect(screen.getByTestId('location')).toHaveTextContent('status=open');
    expect(screen.getByTestId('location')).toHaveTextContent('kind=contract');
    expect(screen.getByTestId('location')).toHaveTextContent('id=11');
  });

  it('links attention tiles to filters that match their counts', () => {
    renderMyWork();

    const summary = screen.getByLabelText(t.myWork.attentionAriaLabel);
    // Kritisch zugewiesen zählt über alle offenen Status + Owner → active + severity + assigned.
    fireEvent.click(within(summary).getByRole('button', { name: new RegExp(t.myWork.attentionCriticalAssigned) }));
    const loc = screen.getByTestId('location');
    expect(loc).toHaveTextContent('status=active');
    expect(loc).toHaveTextContent('severity=critical');
    expect(loc).toHaveTextContent('assigned=1');
  });

  it('deep-links proposal rows to the object-scoped proposals view', () => {
    renderMyWork();

    fireEvent.click(screen.getByText('row_count_min'));
    const loc = screen.getByTestId('location');
    expect(loc).toHaveTextContent('/proposals');
    expect(loc).toHaveTextContent('status=open');
    expect(loc).toHaveTextContent('product=DS_CONTRACT');
  });

  it('shows a retry banner for object query errors', () => {
    data.objectsError = true;
    renderMyWork();

    expect(screen.getByText(t.common.error)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.common.retry }));

    expect(data.objectsRefetch).toHaveBeenCalledTimes(1);
  });

  it('keeps empty states visible', () => {
    data.incidents = [];
    data.proposals = [];
    renderMyWork();

    expect(screen.getByText(t.myWork.noAssigned)).toBeInTheDocument();
    expect(screen.getAllByText(t.myWork.noOpenIncidents)).toHaveLength(2);
    expect(screen.getByText(t.myWork.noProposals)).toBeInTheDocument();
  });
});
