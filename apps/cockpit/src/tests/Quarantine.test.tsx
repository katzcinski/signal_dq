import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { QuarantineEpisodeDetail } from '@/types';

const data = vi.hoisted(() => ({
  episodes: [
    {
      id: 1,
      product: 'DS_SALES_ORDERS',
      run_id: 'run-1',
      status: 'open',
      failed_checks: ['A_not_null'],
      contract_version: '1.0.0',
      manifest_hash: 'abc',
      generation: 2,
      row_count: 42,
      opened_at: '2026-07-09T08:00:00Z',
      released_at: null,
      released_by: '',
      resolved_at: null,
      resolve_reason: '',
      events: [
        { id: 1, at: '2026-07-09T08:00:00Z', actor: 'system', action: 'opened', note: 'Quarantäne-Verdict in Run run-1' },
      ],
    },
    {
      id: 2,
      product: 'DS_RELEASED',
      run_id: 'run-2',
      status: 'released',
      failed_checks: ['B_not_null'],
      contract_version: '1.0.0',
      manifest_hash: 'def',
      generation: 1,
      row_count: null,
      opened_at: '2026-07-08T08:00:00Z',
      released_at: '2026-07-09T09:00:00Z',
      released_by: 'steward-1',
      resolved_at: null,
      resolve_reason: '',
      events: [],
    },
    {
      id: 3,
      product: 'DS_DONE',
      run_id: 'run-3',
      status: 'resolved',
      failed_checks: [],
      contract_version: '1.0.0',
      manifest_hash: 'ghi',
      generation: 1,
      row_count: 7,
      opened_at: '2026-07-01T08:00:00Z',
      released_at: '2026-07-02T08:00:00Z',
      released_by: 'steward-1',
      resolved_at: '2026-07-03T08:00:00Z',
      resolve_reason: 'reprocessed',
      events: [],
    },
  ] as QuarantineEpisodeDetail[],
  release: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock('@/api/quarantine', () => ({
  useQuarantineEpisodes: () => ({
    data: data.episodes,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useQuarantineEpisode: (id: number | null) => ({
    data: data.episodes.find(e => e.id === id),
    isLoading: false,
  }),
  useQuarantineRelease: () => ({ mutate: data.release, isPending: false }),
  useQuarantineConfirmReprocess: () => ({ mutate: data.confirm, isPending: false }),
}));

import Quarantine from '@/pages/Quarantine';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderQuarantine(route = '/quarantine') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/quarantine" element={<><Quarantine /><LocationEcho /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Quarantine page', () => {
  beforeEach(() => {
    data.release.mockReset();
    data.confirm.mockReset();
  });

  it('lists active (non-terminal) episodes on the default tab', () => {
    renderQuarantine();
    expect(screen.getByText('DS_SALES_ORDERS')).toBeInTheDocument();
    expect(screen.getByText('DS_RELEASED')).toBeInTheDocument();
    expect(screen.queryByText('DS_DONE')).not.toBeInTheDocument();
  });

  it('filters by status tab from the URL', () => {
    renderQuarantine('/quarantine?status=resolved');
    expect(screen.getByText('DS_DONE')).toBeInTheDocument();
    expect(screen.queryByText('DS_SALES_ORDERS')).not.toBeInTheDocument();
  });

  it('drills into an episode and releases it with a note', () => {
    renderQuarantine('/quarantine?id=1');
    // Drawer zeigt Episode + verletzte Garantien
    expect(screen.getByText('- A_not_null')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.quarantine.release }));
    // Freigabe-Hinweis (harte Grenze: Rückführung macht der Kunden-Flow)
    expect(screen.getByText(t.quarantine.releaseHint)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: t.common.confirm }));

    expect(data.release).toHaveBeenCalledTimes(1);
    expect(data.release.mock.calls[0][0]).toEqual({ note: undefined });
  });

  it('offers reprocess confirmation only for released episodes', () => {
    renderQuarantine('/quarantine?id=2');
    expect(screen.getByRole('button', { name: t.quarantine.confirmReprocess })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.quarantine.release })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.quarantine.confirmReprocess }));
    fireEvent.click(screen.getByRole('button', { name: t.common.confirm }));
    expect(data.confirm).toHaveBeenCalledTimes(1);
  });

  it('shows the episode timeline', () => {
    renderQuarantine('/quarantine?id=1');
    expect(screen.getByText('system')).toBeInTheDocument();
    expect(screen.getByText('opened')).toBeInTheDocument();
  });
});
