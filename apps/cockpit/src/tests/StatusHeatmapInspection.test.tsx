import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { StatusHeatmap } from '@/components/StatusHeatmap';

vi.mock('@/api/coverage', () => ({
  useStatusHeatmap: () => ({
    data: {
      days: ['2026-07-01', '2026-07-02'],
      datasets: ['SALES.ORDERS'],
      matrix: { 'SALES.ORDERS': { '2026-07-01': 'fail', '2026-07-02': 'pass' } },
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

describe('StatusHeatmap inspection wiring', () => {
  it('routes the object label to onInspect when provided', () => {
    const onInspect = vi.fn();
    render(
      <MemoryRouter>
        <StatusHeatmap onInspect={onInspect} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText('Checks für SALES.ORDERS anzeigen'));
    expect(onInspect).toHaveBeenCalledTimes(1);
    expect(onInspect.mock.calls[0][0]).toBe('SALES.ORDERS');
  });
});
