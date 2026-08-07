import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';

const data = vi.hoisted(() => ({
  plan: {
    enabled: false,
    signal_schema: 'SIGNAL_SQL',
    bridge_enabled: false,
    objects: [
      { name: 'DQ_GATE_STATUS', kind: 'table', manifest_hash: 'abc123', replaceable: false, ddl: 'CREATE TABLE …' },
      { name: 'P_DQ_ASSERT_GATE', kind: 'procedure', manifest_hash: 'def456', replaceable: true, ddl: 'CREATE OR REPLACE …' },
    ],
    split_artifacts: [
      {
        object_id: 'DS_SALES_ORDERS',
        source: '"CORE_DWH"."DS_SALES_ORDERS"',
        clean_table: 'DQ_CLEAN_DS_SALES_ORDERS',
        quarantine_table: 'DQ_Q_DS_SALES_ORDERS',
        released_view: 'V_DQ_RELEASED_DS_SALES_ORDERS',
        manifest_hash: 'aaa',
        predicates: [{ check: 'A_not_null', type: 'missing', condition: '"A" IS NULL' }],
        skipped: [{ check: 'fresh_TS', type: 'freshness', reason: 'Objekt-Eigenschaft — wirkt über das Objekt-Gate (B2)' }],
      },
    ],
  },
  capabilities: [
    { key: 'sqlscript_sync', status: 'unavailable', detail: 'library not found', environment: 'dev', checked_at: '2026-07-11T10:00:00Z' },
    { key: 'flow_view_import', status: 'manual', detail: 'Data Builder prüfen', environment: '', checked_at: '' },
  ],
  apply: vi.fn(),
  probe: vi.fn(),
}));

vi.mock('@/api/enforcement', () => ({
  useEnforcementPlan: () => ({ data: data.plan, isLoading: false, isError: false, refetch: vi.fn() }),
  useCapabilities: () => ({ data: { capabilities: data.capabilities } }),
  useEnforcementApply: () => ({ mutate: data.apply, isPending: false }),
  useCapabilityProbe: () => ({ mutate: data.probe, isPending: false }),
}));

vi.mock('@/api/objects', () => ({
  useEnvironments: () => ({ data: { environments: [{ name: 'dev', schema: 'X' }] } }),
}));

import Enforcement from '@/pages/Enforcement';
import { useRoleStore } from '@/store/role';

function renderPage() {
  render(<MemoryRouter><Enforcement /></MemoryRouter>);
}

describe('Enforcement panel', () => {
  beforeEach(() => {
    data.apply.mockReset();
    data.probe.mockReset();
    useRoleStore.setState({ role: 'owner' });
  });

  it('shows kill-switch state, schema and infrastructure objects', () => {
    renderPage();
    expect(screen.getByText(t.enforcementPanel.disabled)).toBeInTheDocument();
    expect(screen.getByText(/SIGNAL_SQL/)).toBeInTheDocument();
    expect(screen.getByText('DQ_GATE_STATUS')).toBeInTheDocument();
    expect(screen.getByText(t.enforcementPanel.stateful)).toBeInTheDocument();
  });

  it('lists capabilities with status badges', () => {
    renderPage();
    expect(screen.getByText('sqlscript_sync')).toBeInTheDocument();
    expect(screen.getByText(t.enforcementPanel.capStatus.unavailable)).toBeInTheDocument();
    expect(screen.getByText(t.enforcementPanel.capStatus.manual)).toBeInTheDocument();
  });

  it('expands a split artifact to show predicates and explicit skips (G6)', () => {
    renderPage();
    fireEvent.click(screen.getByText('DS_SALES_ORDERS'));
    expect(screen.getByText(/"A" IS NULL/)).toBeInTheDocument();
    expect(screen.getByText(/Objekt-Eigenschaft/)).toBeInTheDocument();
  });

  it('probe runs with a selected environment; apply stays blocked while opt-in is off', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(t.enforcementPanel.environment), { target: { value: 'dev' } });
    fireEvent.click(screen.getByRole('button', { name: t.enforcementPanel.runProbe }));
    expect(data.probe).toHaveBeenCalledWith('dev');
    // Kill-Switch aus ⇒ Apply bleibt deaktiviert (fail-closed Spiegel des Servers)
    expect(screen.getByRole('button', { name: t.enforcementPanel.applyPlan })).toBeDisabled();
    expect(data.apply).not.toHaveBeenCalled();
  });

  it('viewer sees the panel read-only', () => {
    useRoleStore.setState({ role: 'viewer' });
    renderPage();
    expect(screen.getByRole('button', { name: t.enforcementPanel.runProbe })).toBeDisabled();
  });
});
