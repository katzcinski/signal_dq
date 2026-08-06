import { t } from '@/i18n/de';
import type { Schedule } from '@/types';

/** Human cadence label for an interval in seconds. Uses i18n presets where they
 *  match, else falls back to a coarse minutes/hours/days phrasing. */
export function cadenceLabel(seconds: number): string {
  if (!seconds) return '—';
  const preset = t.schedules.intervalPresets[String(seconds)];
  if (preset) return preset;
  if (seconds % 86400 === 0) return `alle ${seconds / 86400} Tage`;
  if (seconds % 3600 === 0) return `alle ${seconds / 3600} Std`;
  if (seconds % 60 === 0) return `alle ${seconds / 60} Min`;
  return `${seconds}s`;
}

function compactDelta(ms: number): string {
  const s = Math.round(Math.abs(ms) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

export interface NextRun {
  kind: 'ok' | 'overdue' | 'external' | 'paused';
  label: string;
}

/** What to show in the "next run" column/field for a schedule. */
export function nextRunInfo(s: Schedule, now: number = Date.now()): NextRun {
  if (s.mode === 'external') return { kind: 'external', label: t.schedules.nextExternal };
  if (!s.enabled) return { kind: 'paused', label: t.schedules.nextPaused };
  const due = new Date(s.next_due_at).getTime();
  if (Number.isNaN(due)) return { kind: 'ok', label: '—' };
  const delta = due - now;
  if (delta <= 0) return { kind: 'overdue', label: t.schedules.overdue.replace('{ago}', compactDelta(delta)) };
  return { kind: 'ok', label: `in ${compactDelta(delta)}` };
}
