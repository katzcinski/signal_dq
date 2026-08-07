import { t } from '@/i18n/de';
import type { OverallStatus } from '@/types';

const STATUS_COLOR: Record<string, string> = {
  pass:    'var(--status-ok)',
  ok:      'var(--status-ok)',
  compliant: 'var(--status-ok)',
  warn:    'var(--status-warn)',
  fail:    'var(--status-fail)',
  breached:'var(--status-fail)',
  critical:'var(--status-crit)',
  unknown: 'var(--status-unknown)',
  stale:   'var(--status-stale)',
};

interface Props {
  status: OverallStatus | string;
  size?: 'sm' | 'md';
  /** Overrides the default `t.status[status]` label — for statuses whose copy
   *  lives outside the status dictionary (e.g. compliance breach, freshness). */
  label?: string;
}

export function StatusPill({ status, size = 'md', label }: Props) {
  const color = STATUS_COLOR[status] ?? STATUS_COLOR.unknown;
  const pad = size === 'sm' ? '1px 6px' : '2px 8px';
  const fs  = size === 'sm' ? '10px' : '11px';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: `${color}22`, border: `1px solid ${color}55`,
      color, borderRadius: 'var(--r)', padding: pad, fontSize: fs,
      fontWeight: 500, letterSpacing: '0.02em', whiteSpace: 'nowrap',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label ?? (t.status as Record<string, string>)[status] ?? status}
    </span>
  );
}
