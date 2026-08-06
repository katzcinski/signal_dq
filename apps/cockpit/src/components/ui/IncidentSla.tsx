import { t } from '@/i18n/de';
import type { Incident } from '@/types';

// Time-to-acknowledge / age SLA indicator (R4-1). Turns an incident's wait time
// into a glanceable urgency badge: an open incident that hasn't been
// acknowledged within its severity SLA pops amber, then red. Acknowledged /
// investigating incidents show how long they've been open; resolved incidents
// show the resolution time, always neutral.
//
// SLA budgets (minutes) tighten with severity — a critical breach left
// unacknowledged for an hour is a red flag; a warn can wait a day.
const SLA_MIN: Record<string, { warn: number; breach: number }> = {
  critical: { warn: 15, breach: 60 },
  fail: { warn: 60, breach: 240 },
  warn: { warn: 240, breach: 1440 },
};

function formatDuration(ms: number): string {
  const min = Math.max(0, Math.floor(ms / 60_000));
  if (min < 60) return `${min} Min.`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} Std.`;
  return `${Math.floor(h / 24)} Tg.`;
}

const LEVEL_COLOR: Record<string, string> = {
  neutral: 'var(--fg-3)',
  warn: 'var(--status-warn)',
  breach: 'var(--status-fail)',
};

export function IncidentSla({ incident }: { incident: Incident }) {
  const now = Date.now();
  const opened = new Date(incident.opened_at).getTime();

  let elapsedMs: number;
  let label: string;
  let urgencyEligible: boolean;

  if (incident.status === 'resolved' && incident.resolved_at) {
    elapsedMs = new Date(incident.resolved_at).getTime() - opened;
    label = t.incidents.slaResolvedAfter;
    urgencyEligible = false;
  } else {
    elapsedMs = now - opened;
    label = incident.status === 'open' ? t.incidents.slaUnacknowledged : t.incidents.slaOpenFor;
    urgencyEligible = true;
  }

  let level = 'neutral';
  if (urgencyEligible) {
    const th = SLA_MIN[incident.severity] ?? SLA_MIN.fail;
    const min = elapsedMs / 60_000;
    if (min >= th.breach) level = 'breach';
    else if (min >= th.warn) level = 'warn';
  }

  const duration = formatDuration(elapsedMs);
  const aria = `${label} ${duration}${level === 'breach' ? ` — ${t.incidents.slaBreached}` : ''}`;
  const color = LEVEL_COLOR[level];

  return (
    <span
      role="img"
      aria-label={aria}
      title={aria}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        fontSize: 11, fontFamily: 'var(--font-mono)', color,
        border: `1px solid ${level === 'neutral' ? 'var(--line-2)' : color}`,
        borderRadius: 'var(--r-md)', padding: '1px 7px',
        fontWeight: level === 'neutral' ? 400 : 600,
      }}
    >
      <span aria-hidden>⏱</span>{duration}
    </span>
  );
}
