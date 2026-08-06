import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { AdminEnvironmentsResponse } from '@/types';

const h = vi.hoisted(() => ({ cfg: { current: null as AdminEnvironmentsResponse | null } }));

// Mock the API layer so the page renders without react-query/axios.
vi.mock('@/api/environments', () => {
  const noopMut = () => ({ mutate: () => {}, isPending: false });
  return {
    useAdminEnvironments: () => ({ data: h.cfg.current, isLoading: false, isError: false, refetch: () => {} }),
    useCreateEnvironment: noopMut,
    useUpdateEnvironment: noopMut,
    useDeleteEnvironment: noopMut,
    useStartConnectionTest: () => ({ mutate: () => {}, isPending: false }),
    useOperation: () => ({ data: null }),
    useOperationStream: () => ({ data: null }),
  };
});

// The Datasphere connector panel has its own react-query data flow; stub it so
// these HANA-connection tests stay focused and need no QueryClientProvider.
vi.mock('@/components/ConnectorPanel', () => ({
  ConnectorPanel: () => null,
}));

// The Entropy integration section fetches its config via react-query; stub it so
// these HANA-connection tests need no QueryClientProvider.
vi.mock('@/api/integrations', () => ({
  useEntropyConfig: () => ({
    data: {
      enabled: false, url_set: false, token_set: false, allowlist_count: 0,
      source_of_truth: 'signal', marketplace_verified: false, mode: 'off',
    },
    isLoading: false,
  }),
}));

import Settings from '@/pages/Settings';

const baseConfig = (overrides: Partial<AdminEnvironmentsResponse> = {}): AdminEnvironmentsResponse => ({
  environments: [
    {
      name: 'prod', host: 'hana.example.invalid', port: 30015, user: 'SIGNAL_RO',
      schema: 'CORE', password_ref: 'env:HANA_PW_PROD', password_set: true,
      encrypt: true, validate_cert: true,
    },
  ],
  can_edit: true,
  ...overrides,
});

describe('Settings page — HANA connections', () => {
  it('lists a connection target with its non-secret details and the secret status', () => {
    h.cfg.current = baseConfig();
    render(<Settings />);
    expect(screen.getByText('prod')).toBeInTheDocument();
    expect(screen.getByText('SIGNAL_RO@hana.example.invalid:30015')).toBeInTheDocument();
    expect(screen.getByText(t.settings.passwordSet)).toBeInTheDocument();
    // Admin gets the add affordance and the per-row test button.
    expect(screen.getByText(t.settings.addEnvironment)).toBeInTheDocument();
    expect(screen.getByText(t.settings.test)).toBeInTheDocument();
  });

  it('flags a missing secret', () => {
    h.cfg.current = baseConfig({
      environments: [{
        name: 'dev', host: 'h', port: 443, user: 'u', schema: '',
        password_ref: '', password_set: false, encrypt: true, validate_cert: true,
      }],
    });
    render(<Settings />);
    expect(screen.getByText(t.settings.passwordMissing)).toBeInTheDocument();
  });

  it('shows the read-only banner and hides write affordances for non-admins', () => {
    h.cfg.current = baseConfig({ can_edit: false });
    render(<Settings />);
    expect(screen.getByText(t.role.readOnlyBanner)).toBeInTheDocument();
    expect(screen.queryByText(t.settings.addEnvironment)).not.toBeInTheDocument();
    expect(screen.queryByText(t.settings.edit)).not.toBeInTheDocument();
  });
});
