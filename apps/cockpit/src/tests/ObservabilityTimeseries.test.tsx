import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ObservabilityTimeseries } from '@/components/ObservabilityTimeseries';

vi.mock('@/api/objects', () => ({
  useObjectTimeseries: () => ({
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  }),
}));

describe('ObservabilityTimeseries loading state', () => {
  it('shows a local skeleton while the time series loads', () => {
    render(<ObservabilityTimeseries objectId="DS" enabled />);

    expect(screen.getByTestId('timeseries-skeleton')).toBeTruthy();
    expect(screen.queryByText('Lädt…')).toBeNull();
  });
});
