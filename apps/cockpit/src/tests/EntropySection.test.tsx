import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// Entropy-Integrations-Panel in den Einstellungen: Modus (aus/dry-run/live),
// Konfig-Chips und der ehrliche „Validierung ausstehend"-Hinweis, solange der
// Marktplatz nicht gegenverifiziert ist.
const state = vi.hoisted(() => ({ cfg: {} as Record<string, unknown> }));

vi.mock('@/api/integrations', () => ({
  useEntropyConfig: () => ({ data: state.cfg, isLoading: false }),
}));
// Settings importiert weitere Hooks; hier neutral halten, damit nur EntropySection zählt.
vi.mock('@/api/environments', () => ({
  useAdminEnvironments: () => ({
    data: { environments: [], can_edit: false }, isLoading: false, isError: false, refetch: vi.fn(),
  }),
  useCreateEnvironment: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateEnvironment: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteEnvironment: () => ({ mutate: vi.fn(), isPending: false }),
  useStartConnectionTest: () => ({ mutate: vi.fn(), isPending: false }),
  useOperationStream: () => ({ data: undefined }),
}));

vi.mock('@/components/ConnectorPanel', () => ({ ConnectorPanel: () => null }));

import Settings from '@/pages/Settings';
import { t } from '@/i18n/de';

function setCfg(over: Record<string, unknown>) {
  state.cfg = {
    enabled: false, url_set: false, token_set: false, allowlist_count: 0,
    source_of_truth: 'signal', marketplace_verified: false, mode: 'off', ...over,
  };
}

describe('EntropySection', () => {
  it('shows dry-run mode and the pending-validation warning when unverified', () => {
    setCfg({ enabled: true, url_set: true, token_set: true, allowlist_count: 2,
      marketplace_verified: false, mode: 'dry_run' });
    render(<Settings />);
    expect(screen.getByText(t.entropy.title)).toBeInTheDocument();
    expect(screen.getByText(t.entropy.modeDryRun)).toBeInTheDocument();
    expect(screen.getByText(t.entropy.validationPending)).toBeInTheDocument();
    expect(screen.getByText(t.entropy.sotSignal)).toBeInTheDocument();
  });

  it('shows live mode without the warning when verified', () => {
    setCfg({ enabled: true, url_set: true, token_set: true, marketplace_verified: true, mode: 'live' });
    render(<Settings />);
    expect(screen.getByText(t.entropy.modeLive)).toBeInTheDocument();
    expect(screen.queryByText(t.entropy.validationPending)).not.toBeInTheDocument();
  });
});
