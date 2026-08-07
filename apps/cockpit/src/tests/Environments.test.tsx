import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Environments from '@/pages/Environments';
import { useRoleStore } from '@/store/role';
import { t } from '@/i18n/de';
import type { EnvironmentsResponse } from '@/types';

const h = vi.hoisted(() => ({
  data: {
    current: {
      environments: [{
        name: 'prod',
        schema: 'CORE',
        host: '***.example.com',
        secret_status: true,
      }],
    } as EnvironmentsResponse,
  },
  start: vi.fn(),
}));

vi.mock('@/api/objects', () => ({
  useEnvironments: () => ({
    data: h.data.current,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/api/environments', () => ({
  useStartConnectionTest: () => ({ mutate: h.start, isPending: false }),
  useOperationStream: () => ({ data: null }),
}));

describe('Environments page', () => {
  beforeEach(() => {
    h.start.mockReset();
    useRoleStore.setState({ role: 'steward' });
  });

  it('lists safe connection metadata and starts a test for stewards', () => {
    render(<Environments />);

    expect(screen.getByText('prod')).toBeInTheDocument();
    expect(screen.getByText('***.example.com')).toBeInTheDocument();

    fireEvent.click(screen.getByText(t.settings.test));
    expect(h.start).toHaveBeenCalledWith('prod', expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it('keeps viewers read-only', () => {
    useRoleStore.setState({ role: 'viewer' });
    render(<Environments />);

    expect(screen.getByText(t.role.readOnlyBanner)).toBeInTheDocument();
    expect(screen.getByText(t.settings.test)).toBeDisabled();
  });
});
