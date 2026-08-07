import type { Lifecycle } from '@/types';
import { t } from '@/i18n/de';

const STEPS: Lifecycle[] = ['draft', 'active', 'deprecated'];
const STEP_LABELS: Record<Lifecycle, string> = {
  draft:      t.lifecycle.draft,
  active:     t.lifecycle.active,
  deprecated: t.lifecycle.deprecated,
};

interface Props { current: Lifecycle }

export function LifecycleStepper({ current }: Props) {
  const idx = STEPS.indexOf(current);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      {STEPS.map((step, i) => {
        const done    = i < idx;
        const active  = i === idx;
        const locked  = i > idx;
        const color   = active ? 'var(--cont)' : done ? 'var(--status-ok)' : 'var(--fg-3)';
        return (
          <div key={step} style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--s1)',
            }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: active ? 'var(--cont)' : done ? 'var(--status-ok)' : 'var(--bg-3)',
                border: `2px solid ${color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, color: active || done ? '#fff' : 'var(--fg-3)',
              }}>
                {locked ? '🔒' : done ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: 10, color, whiteSpace: 'nowrap' }}>{STEP_LABELS[step]}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{
                width: 48, height: 2, margin: '0 4px',
                background: done ? 'var(--status-ok)' : 'var(--line-2)',
                marginBottom: 16,
              }} />
            )}
          </div>
        );
      })}
    </div>
  );
}
