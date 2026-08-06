import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SchedulePanel } from '@/components/SchedulePanel';

const upsert = vi.fn();
const remove = vi.fn();
const state = vi.hoisted(() => ({
  isLoading: false,
}));

vi.mock('@/api/schedules', () => ({
  useObjectSchedule: () => ({
    data: {
      schedule_id: 'obj:DS', object_id: 'DS', mode: 'internal', environment: '',
      execution_mode: 'auto', interval_seconds: 3600, enabled: true,
      next_due_at: new Date(Date.now() + 600_000).toISOString(), last_status: 'started',
    },
    isLoading: state.isLoading,
  }),
  useUpsertObjectSchedule: () => ({ mutate: upsert, isPending: false }),
  useDeleteObjectSchedule: () => ({ mutate: remove, isPending: false }),
}));

vi.mock('@/api/objects', () => ({
  useEnvironments: () => ({ data: { environments: [{ name: 'PROD', schema: 'CORE_DWH' }] } }),
}));

describe('SchedulePanel (per-object toggle)', () => {
  beforeEach(() => {
    state.isLoading = false;
    upsert.mockClear();
    remove.mockClear();
  });

  it('shows a local skeleton while the schedule loads', () => {
    state.isLoading = true;

    render(<SchedulePanel objectId="DS" />);

    expect(screen.getByTestId('schedule-skeleton')).toBeTruthy();
    expect(screen.queryByText('Lädt…')).toBeNull();
  });

  it('shows the three modes and saves the chosen one', () => {
    render(<SchedulePanel objectId="DS" />);

    // all three mode cards are present
    expect(screen.getByText('Intern')).toBeTruthy();
    expect(screen.getByText('Extern')).toBeTruthy();
    expect(screen.getByText('Manuell')).toBeTruthy();

    // saving the (internal) default upserts with the loaded cadence
    fireEvent.click(screen.getByText('Zeitplan speichern'));
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'internal', interval_seconds: 3600 }),
    );
  });

  it('switching to manual removes the schedule', () => {
    render(<SchedulePanel objectId="DS" />);
    fireEvent.click(screen.getByText('Manuell'));
    fireEvent.click(screen.getByText('Zeitplan entfernen'));
    expect(remove).toHaveBeenCalled();
  });
});
