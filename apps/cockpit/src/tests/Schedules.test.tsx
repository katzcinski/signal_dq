import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Schedules from '@/pages/Schedules';
import type { Schedule } from '@/types';

const past = new Date(Date.now() - 60_000).toISOString();
const future = new Date(Date.now() + 3_600_000).toISOString();

const rows: Schedule[] = [
  { schedule_id: 'obj:ORDER_ITEMS', object_id: 'ORDER_ITEMS', mode: 'internal', environment: 'PROD',
    execution_mode: 'auto', interval_seconds: 900, enabled: true, next_due_at: past, last_status: 'started' },
  { schedule_id: 'obj:FX_RATES', object_id: 'FX_RATES', mode: 'external', environment: 'PROD',
    execution_mode: 'auto', interval_seconds: 0, enabled: true, next_due_at: future, last_status: 'started' },
];

vi.mock('@/api/schedules', () => ({
  useSchedules: () => ({ data: rows, isLoading: false, isError: false, refetch: vi.fn() }),
  useRunObjectNow: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateScheduleRow: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/api/objects', () => ({
  useObjects: () => ({ data: [
    { id: 'ORDER_ITEMS', space: 'SALES', layer: 'core' },
    { id: 'FX_RATES', space: 'FINANCE', layer: 'raw' },
  ] }),
}));

describe('Schedules overview', () => {
  it('renders rows, mode badges and an overdue countdown', () => {
    render(<MemoryRouter><Schedules /></MemoryRouter>);

    expect(screen.getByText('ORDER_ITEMS')).toBeTruthy();
    expect(screen.getByText('FX_RATES')).toBeTruthy();
    // internal vs external split is surfaced (badge text)
    expect(screen.getAllByText('intern').length).toBeGreaterThan(0);
    expect(screen.getAllByText('extern').length).toBeGreaterThan(0);
    // the past-due internal schedule reads as overdue (subtitle + row cell)
    expect(screen.getAllByText(/überfällig/).length).toBeGreaterThan(0);
    // the external schedule shows no internal cadence
    expect(screen.getByText('— extern')).toBeTruthy();
  });
});
