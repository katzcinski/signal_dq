import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { IncidentDetail } from '@/types';

const data = vi.hoisted(() => ({
  useIncidentsCalls: [] as Array<[string | undefined, string | undefined, string | undefined]>,
  incidents: [
    {
      id: 1,
      product: 'DS_CONTRACT',
      run_id: 'run-1',
      severity: 'fail',
      status: 'open',
      owner: 'team-a',
      title: 'Open contract breach',
      failed_checks: ['row_count'],
      opened_at: '2026-07-02T08:00:00Z',
      resolved_at: null,
      contract_version: '1.0.0',
      kind: 'consumer_contract',
      events: [],
      impacted_objects: [],
    },
    {
      id: 2,
      product: 'DS_GATE',
      run_id: 'run-2',
      severity: 'critical',
      status: 'acknowledged',
      owner: 'team-b',
      title: 'Internal latency signal',
      failed_checks: ['freshness'],
      opened_at: '2026-07-02T07:00:00Z',
      resolved_at: null,
      contract_version: '',
      kind: 'internal_gate',
      events: [],
      impacted_objects: [],
    },
    {
      id: 3,
      product: 'DS_GATE_2',
      run_id: 'run-3',
      severity: 'warn',
      status: 'open',
      owner: '',
      title: 'Open gate signal',
      failed_checks: ['volume'],
      opened_at: '2026-07-02T06:00:00Z',
      resolved_at: null,
      contract_version: '',
      kind: 'internal_gate',
      events: [],
      impacted_objects: [],
    },
    {
      id: 4,
      product: 'DS_DONE',
      run_id: 'run-4',
      severity: 'fail',
      status: 'resolved',
      owner: 'team-c',
      title: 'Resolved breach',
      failed_checks: [],
      opened_at: '2026-07-01T08:00:00Z',
      resolved_at: '2026-07-01T09:00:00Z',
      contract_version: '1.0.0',
      kind: 'provider_contract',
      events: [],
      impacted_objects: [],
    },
  ] as IncidentDetail[],
  transition: vi.fn(),
}));

vi.mock('@/api/incidents', () => ({
  useIncidents: (status?: string, severity?: string, kind?: string) => {
    data.useIncidentsCalls.push([status, severity, kind]);

    return {
      data: data.incidents.filter(incident => {
        if (severity && incident.severity !== severity) return false;
        if (kind && incident.kind !== kind) return false;
        return true;
      }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  },
  useIncident: (id: number | null) => ({
    data: data.incidents.find(incident => incident.id === id),
    isLoading: false,
  }),
  useIncidentTransition: () => ({ mutate: data.transition, isPending: false }),
  useFailedChecks: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
}));

import Incidents from '@/pages/Incidents';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderIncidents(route = '/incidents') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/incidents" element={<><Incidents /><LocationEcho /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

function lastUseIncidentsCall() {
  return data.useIncidentsCalls[data.useIncidentsCalls.length - 1];
}

describe('Incidents page', () => {
  beforeEach(() => {
    data.useIncidentsCalls.length = 0;
    data.transition.mockReset();
  });

  it('fetches incidents without a server status and filters the default open tab client-side', () => {
    renderIncidents();

    expect(lastUseIncidentsCall()).toEqual([undefined, undefined, undefined]);
    expect(screen.getByText('Open contract breach')).toBeInTheDocument();
    expect(screen.getByText('Open gate signal')).toBeInTheDocument();
    expect(screen.queryByText('Internal latency signal')).not.toBeInTheDocument();
    expect(screen.queryByText('Resolved breach')).not.toBeInTheDocument();
  });

  it('filters the acknowledged tab client-side without passing status to the API', () => {
    renderIncidents('/incidents?status=acknowledged');

    expect(lastUseIncidentsCall()).toEqual([undefined, undefined, undefined]);
    expect(screen.getByText('Internal latency signal')).toBeInTheDocument();
    expect(screen.queryByText('Open contract breach')).not.toBeInTheDocument();
    expect(screen.queryByText('Open gate signal')).not.toBeInTheDocument();
    expect(screen.queryByText('Resolved breach')).not.toBeInTheDocument();
  });

  it('passes only the internal gate kind to the incidents API', () => {
    renderIncidents('/incidents?kind=internal_gate');

    expect(lastUseIncidentsCall()).toEqual([undefined, undefined, 'internal_gate']);
    expect(screen.getByText('Open gate signal')).toBeInTheDocument();
    expect(screen.queryByText('Open contract breach')).not.toBeInTheDocument();
  });

  it('keeps the contract kind filter client-side', () => {
    renderIncidents('/incidents?kind=contract');

    expect(lastUseIncidentsCall()).toEqual([undefined, undefined, undefined]);
    expect(screen.getByText('Open contract breach')).toBeInTheDocument();
    expect(screen.queryByText('Open gate signal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.open} (1)` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.resolved} (1)` })).toBeInTheDocument();
  });

  it('shows all non-resolved incidents on the active tab', () => {
    renderIncidents('/incidents?status=active');

    expect(screen.getByText('Open contract breach')).toBeInTheDocument();
    expect(screen.getByText('Internal latency signal')).toBeInTheDocument();
    expect(screen.getByText('Open gate signal')).toBeInTheDocument();
    expect(screen.queryByText('Resolved breach')).not.toBeInTheDocument();
    // Tab-Zähler = offen + bestätigt + in Arbeit (3 von 4).
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.active} (3)` })).toBeInTheDocument();
  });

  it('restricts the list to assigned incidents via ?assigned=1', () => {
    renderIncidents('/incidents?status=active&assigned=1');

    // team-a / team-b tragen einen Owner, DS_GATE_2 nicht.
    expect(screen.getByText('Open contract breach')).toBeInTheDocument();
    expect(screen.getByText('Internal latency signal')).toBeInTheDocument();
    expect(screen.queryByText('Open gate signal')).not.toBeInTheDocument();
    // Zähler folgt dem Assigned-Filter (2 zugewiesene offene).
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.active} (2)` })).toBeInTheDocument();
  });

  it('toggles the assigned filter through the URL and clears it', () => {
    renderIncidents('/incidents?status=active');

    fireEvent.click(screen.getByRole('button', { name: t.incidents.filterAssigned }));
    expect(screen.getByTestId('location')).toHaveTextContent('assigned=1');
    expect(screen.queryByText('Open gate signal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(new RegExp(t.incidents.filterAssigned)));
    expect(screen.getByTestId('location')).not.toHaveTextContent('assigned=1');
    expect(screen.getByText('Open gate signal')).toBeInTheDocument();
  });

  it('opens the drawer from a shared ?id= deep link', () => {
    renderIncidents('/incidents?status=acknowledged&kind=internal_gate&id=2');

    expect(screen.getByRole('dialog', { name: 'Internal latency signal' })).toBeInTheDocument();
    expect(screen.getAllByText('DS_GATE').length).toBeGreaterThan(0);
    expect(screen.getAllByText(t.incidents.kindGate).length).toBeGreaterThan(0);
  });

  it('opens the drawer for an id hidden by the active filters', () => {
    renderIncidents('/incidents?kind=internal_gate&id=1');

    expect(lastUseIncidentsCall()).toEqual([undefined, undefined, 'internal_gate']);
    expect(screen.queryByRole('button', { name: /Open contract breach/ })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Open contract breach' })).toBeInTheDocument();
  });

  it('writes and clears the selected incident id through the URL', () => {
    renderIncidents();

    fireEvent.click(screen.getByText('Open contract breach'));
    expect(screen.getByTestId('location')).toHaveTextContent('id=1');
    expect(screen.getByRole('dialog', { name: 'Open contract breach' })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(t.common.close));
    expect(screen.getByTestId('location')).not.toHaveTextContent('id=1');
  });

  it('follows a resolved incident to the resolved tab so the drawer does not go stale', () => {
    // Der Übergangs-Mock ruft den onSuccess-Callback auf, damit followTransition greift.
    data.transition.mockImplementation((_body: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    renderIncidents('/incidents?status=open&id=1');

    expect(screen.getByRole('dialog', { name: 'Open contract breach' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.incidents.resolve }));
    // Der Bestätigen-Button im Notiz-Panel (t.common.confirm kollidiert mit dem
    // Acknowledge-Label) — über das Notiz-Feld eindeutig eingrenzen.
    const notePanel = screen.getByPlaceholderText(t.incidents.notePlaceholder).closest('div') as HTMLElement;
    fireEvent.click(within(notePanel).getByRole('button', { name: t.common.confirm }));

    // Tab folgt dem Incident (status=resolved), id bleibt erhalten → Drawer bleibt konsistent.
    expect(screen.getByTestId('location')).toHaveTextContent('status=resolved');
    expect(screen.getByTestId('location')).toHaveTextContent('id=1');
  });

  it('does not jump tabs when an acknowledge keeps the incident on the active tab', () => {
    data.transition.mockImplementation((_body: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    renderIncidents('/incidents?status=active&id=1');

    fireEvent.click(screen.getByRole('button', { name: t.incidents.acknowledge }));
    const notePanel = screen.getByPlaceholderText(t.incidents.notePlaceholder).closest('div') as HTMLElement;
    fireEvent.click(within(notePanel).getByRole('button', { name: t.common.confirm }));

    // acknowledged bleibt im „Aktiv"-Tab sichtbar → kein unnötiger Tab-Wechsel.
    expect(screen.getByTestId('location')).toHaveTextContent('status=active');
    expect(screen.getByTestId('location')).not.toHaveTextContent('status=acknowledged');
  });

  it('shows status counts beside the tabs', () => {
    renderIncidents();

    expect(screen.getByRole('button', { name: `${t.incidents.tabs.open} (2)` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.acknowledged} (1)` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${t.incidents.tabs.resolved} (1)` })).toBeInTheDocument();
  });

  it('syncs kind and severity chips into the URL and clears active filters individually', () => {
    renderIncidents();

    fireEvent.click(screen.getByRole('button', { name: t.incidents.kindGate }));
    expect(screen.getByTestId('location')).toHaveTextContent('kind=internal_gate');
    expect(screen.queryByText('Open contract breach')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.status.critical }));
    expect(screen.getByTestId('location')).toHaveTextContent('severity=critical');

    fireEvent.click(screen.getByRole('button', { name: `${t.incidents.tabs.acknowledged} (1)` }));
    expect(screen.getByTestId('location')).toHaveTextContent('status=acknowledged');
    expect(screen.getByText('Internal latency signal')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(new RegExp(t.status.critical)));
    expect(screen.getByTestId('location')).not.toHaveTextContent('severity=critical');
  });
});
