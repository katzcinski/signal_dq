import { type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStatusHeatmap } from '@/api/coverage';
import { Panel } from '@/components/ui/Panel';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { t } from '@/i18n/de';

// UX-N10: GitHub-contribution-style reliability heatmap — rows are objects,
// columns are days, each cell coloured by that day's worst run status. A day
// with no run renders neutral. At-a-glance: "which objects are flaky, and when?".

const CELL_COLOR: Record<string, string> = {
  pass: 'var(--status-ok)',
  warn: 'var(--status-warn)',
  fail: 'var(--status-fail)',
  critical: 'var(--status-crit)',
  error: 'var(--status-stale)',
};
const EMPTY = 'var(--bg-3)';
const CELL = 11;
const GAP = 2;

function fmtDay(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// onInspect (optional): der Objekt-Name öffnet dann das Quick-Checks-Popover
// ("dieses Objekt ist flaky — was schlägt gerade fehl?") statt zu navigieren.
// Die Heatmap zeigt *wann*, das Popover *was* — komplementär, ohne neues Chrome.
export function StatusHeatmap({ onInspect }: {
  onInspect?: (objectId: string, event: MouseEvent<HTMLElement>) => void;
}) {
  const { data, isLoading, isError, refetch } = useStatusHeatmap(30);
  const navigate = useNavigate();

  if (isError) return <ErrorBanner onRetry={() => refetch()} />;
  if (isLoading || !data) return null;
  if (data.datasets.length === 0) return null;

  const { days, datasets, matrix } = data;
  // Label only first/mid/last day to avoid clutter.
  const tickIdx = new Set([0, Math.floor(days.length / 2), days.length - 1]);

  return (
    <div>
      <Panel title={`${t.heatmap.title} (${days.length}${t.heatmap.daysShort})`}>
        <div style={{ overflowX: 'auto' }}>
          <div style={{ display: 'inline-block', minWidth: 'min-content' }}>
            {/* Day axis */}
            <div style={{ display: 'flex', gap: GAP, marginLeft: 150, marginBottom: 4 }}>
              {days.map((d, i) => (
                <span key={d} style={{ width: CELL, fontSize: 8, color: 'var(--fg-3)', textAlign: 'center', whiteSpace: 'nowrap' }}>
                  {tickIdx.has(i) ? fmtDay(d) : ''}
                </span>
              ))}
            </div>
            {datasets.map(ds => (
              <div key={ds} style={{ display: 'flex', alignItems: 'center', gap: GAP, marginBottom: GAP }}>
                <button
                  onClick={e => onInspect ? onInspect(ds, e) : navigate(`/objects/${encodeURIComponent(ds)}`)}
                  aria-label={onInspect ? t.peek.openChecksFor.replace('{name}', ds) : undefined}
                  title={ds}
                  style={{
                    width: 150, textAlign: 'right', paddingRight: 8, border: 'none', background: 'none',
                    color: 'var(--fg-2)', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0,
                  }}
                >
                  {ds}
                </button>
                {days.map(day => {
                  const status = matrix[ds]?.[day];
                  const bg = status ? (CELL_COLOR[status] ?? EMPTY) : EMPTY;
                  const label = status ? `${ds} · ${fmtDay(day)}: ${t.status[status] ?? status}` : `${ds} · ${fmtDay(day)}: ${t.heatmap.noRun}`;
                  return (
                    <span
                      key={day}
                      role="img"
                      aria-label={label}
                      title={label}
                      style={{ width: CELL, height: CELL, borderRadius: 2, background: bg, flexShrink: 0 }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', marginTop: 10, fontSize: 10, color: 'var(--fg-3)' }}>
          {(['pass', 'warn', 'fail', 'critical'] as const).map(s => (
            <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
              <span style={{ width: CELL, height: CELL, borderRadius: 2, background: CELL_COLOR[s] }} />
              {t.status[s] ?? s}
            </span>
          ))}
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
            <span style={{ width: CELL, height: CELL, borderRadius: 2, background: EMPTY }} />
            {t.heatmap.noRun}
          </span>
        </div>
      </Panel>
    </div>
  );
}
