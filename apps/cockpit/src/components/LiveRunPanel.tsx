import { useState } from 'react';
import { useRunStream } from '@/api/runs';
import { t } from '@/i18n/de';

interface Props {
  runId: string;
  dataset: string;
  running: boolean;
}

// Collapsible bottom bar showing live progress lines of an in-flight run,
// streamed over SSE (/api/stream) while the run is running, with a polling
// fallback when the stream is unavailable.
export function LiveRunPanel({ runId, dataset, running }: Props) {
  const [open, setOpen] = useState(true);
  const { events } = useRunStream(runId, running);

  if (!running) return null;

  return (
    <div style={{
      position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 20,
      background: 'var(--bg-1)', borderTop: '1px solid var(--line)',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 'var(--s2)',
          background: 'none', border: 'none', padding: 'var(--s2) var(--s4)',
          color: 'var(--fg-2)', fontSize: 12, cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--status-warn)', flexShrink: 0 }} />
        <span>{t.liveRun}</span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>{dataset}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{runId.slice(0, 12)}…</span>
        <span style={{ marginLeft: 'auto', color: 'var(--fg-3)' }}>{open ? '▾' : '▴'}</span>
      </button>
      {open && (
        <div style={{
          maxHeight: 160, overflowY: 'auto', padding: '0 var(--s4) var(--s3)',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)',
        }}>
          {events.length === 0 ? (
            <div style={{ color: 'var(--fg-3)' }}>{t.common.loading}</div>
          ) : events.map((e, i) => (
            <div key={`${e.ts}-${i}`}>
              <span style={{ color: 'var(--fg-3)' }}>{e.ts}</span> {e.line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
