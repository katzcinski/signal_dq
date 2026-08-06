import { type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import type { ObjectSummary } from '@/types';

// Replaces the (redundant) overall health gauge: the trend already shows the
// current pass-rate, so this slot answers the question the trend can't —
// *which* objects need attention right now. Ranked worst-first, each row drills
// straight into the object detail. DQ-first and actionable.

const SEVERITY_RANK: Record<string, number> = { critical: 0, fail: 1, warn: 2 };

// Ursache in Worten: die auffälligen Familien mit ihrem Status-Label.
function findingText(o: ObjectSummary): string {
  const parts: string[] = [];
  const fams = [
    [t.cockpit.colObservability, o.family_status?.observability],
    [t.cockpit.colQuality, o.family_status?.quality],
  ] as const;
  for (const [label, status] of fams) {
    if (status && status in SEVERITY_RANK) {
      parts.push(`${label}: ${t.status[status as keyof typeof t.status] ?? status}`);
    }
  }
  if (parts.length === 0) return t.status[o.status as keyof typeof t.status] ?? o.status;
  return parts.join(' · ');
}

function severityDot(status: string): React.CSSProperties {
  const critical = status === 'critical';
  const color = critical ? 'var(--status-crit)'
    : status === 'fail' ? 'var(--status-fail)' : 'var(--status-warn)';
  return {
    width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: color,
    boxShadow: critical ? `0 0 5px ${color}` : undefined,
  };
}

// onInspect (optional): öffnet die Zwei-Ebenen-Inspektion (Quick-Checks-Popover)
// statt direkt in die Vollansicht zu springen. Ohne den Prop bleibt das alte
// Verhalten — die Komponente ist eigenständig nutzbar.
export function AttentionPanel({ objects, onInspect }: {
  objects: ObjectSummary[];
  onInspect?: (objectId: string, event: MouseEvent<HTMLElement>) => void;
}) {
  const navigate = useNavigate();
  const ranked = objects
    .filter(o => o.status in SEVERITY_RANK)
    .sort((a, b) => (SEVERITY_RANK[a.status] ?? 9) - (SEVERITY_RANK[b.status] ?? 9))
    .slice(0, 6);

  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)',
      borderLeft: `3px solid ${ranked.length ? 'var(--status-fail)' : 'var(--qual)'}`,
      borderRadius: 'var(--r-lg)', overflow: 'hidden', flex: 1, display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--s2)',
        padding: '10px 14px', borderBottom: '1px solid var(--line)',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {t.cockpit.attentionTitle}
        </span>
        {ranked.length > 0 && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{ranked.length}</span>
        )}
      </div>

      <div style={{ padding: '4px 14px 8px', flex: 1 }}>
        {ranked.length === 0 ? (
          <p style={{ color: 'var(--fg-3)', fontSize: 12, padding: 'var(--s5) 0', textAlign: 'center' }}>
            {t.cockpit.attentionEmpty}
          </p>
        ) : ranked.map((o, i) => (
          <button
            key={o.id}
            aria-label={onInspect ? t.peek.openChecksFor.replace('{name}', o.name) : undefined}
            onClick={e => onInspect ? onInspect(o.id, e) : navigate(`/objects/${o.id}`)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
              padding: '8px 0', background: 'none', border: 'none',
              borderTop: i === 0 ? 'none' : '1px solid var(--line)', borderRadius: 0,
              color: 'var(--fg)', cursor: 'pointer',
            }}
          >
            <span aria-hidden style={severityDot(o.status)} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, whiteSpace: 'nowrap' }}>
              {o.name}
            </span>
            <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {findingText(o)}
            </span>
            {o.last_run && (
              <span title={absoluteTime(o.last_run)} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
                {relativeTime(o.last_run)}
              </span>
            )}
            <span aria-hidden style={{ color: 'var(--fg-3)', fontSize: 11 }}>→</span>
          </button>
        ))}
      </div>
    </div>
  );
}
