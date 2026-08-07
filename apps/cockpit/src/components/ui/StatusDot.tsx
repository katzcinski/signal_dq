import type { OverallStatus } from '@/types';
import { t } from '@/i18n/de';

const STATUS_COLOR: Record<string, string> = {
  pass:    'var(--status-ok)',
  warn:    'var(--status-warn)',
  fail:    'var(--status-fail)',
  critical:'var(--status-crit)',
  unknown: 'var(--status-unknown)',
  stale:   'var(--status-stale)',
};

interface Props { status: OverallStatus | string; size?: number }

export function StatusDot({ status, size = 8 }: Props) {
  const color = STATUS_COLOR[status] ?? STATUS_COLOR.unknown;
  const label = t.status[status] ?? status;
  return (
    <span
      role="img"
      aria-label={label}
      style={{
        display: 'inline-block', width: size, height: size,
        borderRadius: '50%', background: color, flexShrink: 0,
      }}
      title={label}
    />
  );
}
