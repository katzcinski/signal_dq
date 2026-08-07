import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { HealingEpisodeDetail, HealingOverview, HealingPatch } from '@/types';

const h = vi.hoisted(() => ({
  overview: undefined as HealingOverview | undefined,
  detail: undefined as HealingEpisodeDetail | undefined,
  createCorrection: vi.fn(),
  recheck: vi.fn(),
  createPatch: vi.fn(),
  revokePatch: vi.fn(),
  role: 'steward' as string,
}));

vi.mock('@/api/healing', () => ({
  useHealingOverview: () => ({
    data: h.overview, isLoading: false, isError: false, refetch: vi.fn(),
  }),
  useHealingEpisode: () => ({
    data: h.detail, isLoading: false, isError: false, refetch: vi.fn(),
  }),
  useCreateCorrection: () => ({ mutate: h.createCorrection, isPending: false }),
  useRecheckEpisode: () => ({ mutate: h.recheck, isPending: false }),
  useCreatePatch: () => ({ mutate: h.createPatch, isPending: false }),
  useRevokePatch: () => ({ mutate: h.revokePatch, isPending: false }),
}));

vi.mock('@/store/role', () => ({
  useRoleStore: (selector: (s: { role: string }) => unknown) => selector({ role: h.role }),
}));

import Healing from '@/pages/Healing';

function patch(over: Partial<HealingPatch> = {}): HealingPatch {
  return {
    id: 'p-1', object_id: 'DS_SALES_ORDERS', keys: { ID: '42' }, values: { AMOUNT: '100' },
    reason: 'Quellfehler', actor: 'owner', created_at: '2026-08-01T10:00:00Z',
    valid_until: null, status: 'active', revoked_at: null, revoked_by: '',
    applied: false, apply_error: '', ...over,
  };
}

function overview(over: Partial<HealingOverview> = {}): HealingOverview {
  return {
    materialization_enabled: false,
    signal_schema: '',
    episodes: [{
      episode_id: 7, object_id: 'DS_SALES_ORDERS', status: 'open', row_count: 12,
      failed_checks: ['amount_not_null'], opened_at: '2026-08-01T08:00:00Z',
      corrections: 1, kind: 'consumer_contract', four_eyes: true,
    }],
    patches: [patch()],
    patches_total: 1,
    corrections_total: 1,
    ...over,
  };
}

function detail(over: Partial<HealingEpisodeDetail> = {}): HealingEpisodeDetail {
  return {
    episode: { id: 7 } as HealingEpisodeDetail['episode'],
    object_id: 'DS_SALES_ORDERS',
    kind: 'consumer_contract',
    four_eyes: true,
    columns: ['ID', 'AMOUNT', 'CURRENCY'],
    key_columns: ['ID'],
    row_capable: true,
    predicates: [{ check: 'amount_not_null', type: 'missing' }],
    skipped: [],
    remaining_bad_rows: 3,
    release_ready: false,
    corrections: [{
      id: 1, object_id: 'DS_SALES_ORDERS', episode_id: 7, row_key: { ID: '42' },
      column_name: 'AMOUNT', before_value: null, after_value: '100',
      reason: 'Tippfehler', actor: 'anna', created_at: '2026-08-01T09:00:00Z',
      applied: false, apply_error: '',
    }],
    correction_actors: ['anna'],
    ...over,
  };
}

function renderPage(route = '/healing') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Healing />
    </MemoryRouter>,
  );
}

describe('Healing-Workbench', () => {
  beforeEach(() => {
    h.overview = overview();
    h.detail = detail();
    h.role = 'steward';
    h.createCorrection.mockClear();
    h.recheck.mockClear();
    h.createPatch.mockClear();
    h.revokePatch.mockClear();
  });

  it('lists healable episodes and flags the four-eyes rule', () => {
    renderPage();
    expect(screen.getByText(t.healing.title)).toBeInTheDocument();
    expect(screen.getByText('DS_SALES_ORDERS')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText(/Vier-Augen/)).toBeInTheDocument();
  });

  it('warns when materialization is off', () => {
    renderPage();
    expect(screen.getByText(t.healing.materializationOff)).toBeInTheDocument();
  });

  it('shows remaining violating rows and blocks release readiness', () => {
    renderPage('/healing?episode=7');
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(t.healing.releaseBlocked)).toBeInTheDocument();
  });

  it('reports release readiness once the predicate is satisfied', () => {
    h.detail = detail({ remaining_bad_rows: 0, release_ready: true });
    renderPage('/healing?episode=7');
    expect(screen.getByText(t.healing.releaseReady)).toBeInTheDocument();
  });

  it('submits a correction with the row key and target column', () => {
    renderPage('/healing?episode=7');

    fireEvent.change(screen.getByLabelText(t.healing.keyValue), { target: { value: '42' } });
    fireEvent.change(screen.getByLabelText(t.healing.column), { target: { value: 'AMOUNT' } });
    fireEvent.change(screen.getByLabelText(t.healing.newValue), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText(t.healing.reason), { target: { value: 'Tippfehler' } });
    fireEvent.click(screen.getByText(t.healing.submitCorrection));

    expect(h.createCorrection).toHaveBeenCalledTimes(1);
    expect(h.createCorrection.mock.calls[0][0]).toEqual({
      keys: { ID: '42' }, column: 'AMOUNT', new_value: '100', reason: 'Tippfehler',
    });
  });

  it('keeps the correction form disabled until key and value are given', () => {
    renderPage('/healing?episode=7');
    expect(screen.getByText(t.healing.submitCorrection).closest('button')).toBeDisabled();
  });

  it('explains episodes without a row-level predicate', () => {
    h.detail = detail({ row_capable: false, remaining_bad_rows: null });
    renderPage('/healing?episode=7');
    expect(screen.getByText(t.healing.notRowCapable)).toBeInTheDocument();
    // Ohne Zeilenfähigkeit kein Korrekturformular
    expect(screen.queryByText(t.healing.submitCorrection)).not.toBeInTheDocument();
  });

  it('triggers a recheck', () => {
    renderPage('/healing?episode=7');
    fireEvent.click(screen.getByText(t.healing.recheck));
    expect(h.recheck).toHaveBeenCalledTimes(1);
  });

  it('hides the patch form from stewards but shows the patches', () => {
    renderPage('/healing?tab=patches');
    expect(screen.getByText(t.healing.patchOwnerOnly)).toBeInTheDocument();
    expect(screen.queryByText(t.healing.submitPatch)).not.toBeInTheDocument();
    expect(screen.getAllByText('DS_SALES_ORDERS').length).toBeGreaterThan(0);
  });

  it('lets an owner create and revoke patches', () => {
    h.role = 'owner';
    renderPage('/healing?tab=patches');

    fireEvent.change(screen.getByLabelText(t.healing.patchObject), { target: { value: 'DS_SALES_ORDERS' } });
    fireEvent.change(screen.getByLabelText(t.healing.keyColumn), { target: { value: 'ID' } });
    fireEvent.change(screen.getByLabelText(t.healing.keyValue), { target: { value: '42' } });
    fireEvent.change(screen.getByLabelText(t.healing.column), { target: { value: 'AMOUNT' } });
    fireEvent.change(screen.getByLabelText(t.healing.newValue), { target: { value: '100' } });
    fireEvent.click(screen.getByText(t.healing.submitPatch));

    expect(h.createPatch).toHaveBeenCalledTimes(1);
    expect(h.createPatch.mock.calls[0][0]).toMatchObject({
      object_id: 'DS_SALES_ORDERS', keys: { ID: '42' }, values: { AMOUNT: '100' },
    });

    fireEvent.click(screen.getByText(t.healing.revoke));
    expect(h.revokePatch).toHaveBeenCalledWith('p-1');
  });

  it('marks unprojected entries as audit-only', () => {
    renderPage('/healing?tab=patches');
    expect(screen.getAllByText(t.healing.appliedNo).length).toBeGreaterThan(0);
  });

  it('does not offer revoke for a revoked patch', () => {
    h.role = 'owner';
    h.overview = overview({ patches: [patch({ status: 'revoked' })] });
    renderPage('/healing?tab=patches');
    expect(screen.queryByText(t.healing.revoke)).not.toBeInTheDocument();
  });
});
