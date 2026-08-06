import type { CheckState, Severity } from '@/types';
import { StatusPill } from './StatusPill';
import { Tooltip } from './Tooltip';
import { t } from '@/i18n/de';

// G6: gating states must render as neutral state pills, never as pass/fail.
type GatedState = Exclude<CheckState, 'executed'>;

const GLYPH: Record<GatedState, string> = {
  skipped_stale: '⏸',
  skipped_dependency: '⏸',
  downgraded: '↓',
  error: '⚠',
};

interface Props {
  state: GatedState;
  size?: 'sm' | 'md';
}

export function StatePill({ state, size = 'md' }: Props) {
  const pad = size === 'sm' ? '1px 6px' : '2px 8px';
  const fs  = size === 'sm' ? '10px' : '11px';
  const label = t.status[state] ?? state;
  const hint = t.stateHint[state] ?? label;
  return (
    <Tooltip content={hint}>
      <span aria-label={hint} style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        background: 'transparent',
        borderWidth: 1, borderStyle: 'dashed', borderColor: 'var(--fg-3)',
        color: 'var(--fg-3)', borderRadius: 'var(--r)', padding: pad, fontSize: fs,
        fontWeight: 500, letterSpacing: '0.02em', whiteSpace: 'nowrap',
      }}>
        <span aria-hidden>{GLYPH[state]}</span>
        {label}
      </span>
    </Tooltip>
  );
}

// Shared status cell for check-result tables: shows the neutral StatePill for
// any non-executed gating state, otherwise the pass/fail StatusPill.
export function CheckStatusCell({ state, passed, severity }: {
  state?: CheckState;
  passed: boolean;
  severity: Severity;
}) {
  if (state && state !== 'executed') return <StatePill state={state} size="sm" />;
  return <StatusPill status={passed ? 'pass' : severity} size="sm" />;
}
