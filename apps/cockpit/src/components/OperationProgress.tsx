import type { OperationStatus } from '@/types';

interface Props<T = unknown> {
  operation?: OperationStatus<T> | null;
}

function tone(state?: OperationStatus['state']) {
  if (state === 'finished') return 'var(--status-pass)';
  if (state === 'error') return 'var(--status-fail)';
  return 'var(--status-warn)';
}

export function OperationProgress<T = unknown>({ operation }: Props<T>) {
  if (!operation) return null;

  const lines = (operation.progress ?? []).filter(line => !line.line.startsWith('@@progress '));
  const color = tone(operation.state);

  return (
    <div style={{
      border: `1px solid ${color}`,
      borderRadius: 'var(--r-md)',
      background: `color-mix(in srgb, ${color} 8%, transparent)`,
      padding: 'var(--s3)',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--s2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 600, color }}>
          {operation.kind} · {operation.state}
        </span>
      </div>
      {operation.state === 'running' && (
        <div style={{ height: 3, overflow: 'hidden', borderRadius: 2, background: 'var(--bg-3)' }}>
          <div style={{ height: '100%', width: '45%', background: color }} />
        </div>
      )}
      <div style={{
        maxHeight: 120,
        overflowY: 'auto',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--fg-2)',
      }}>
        {lines.length === 0 ? (
          <div style={{ color: 'var(--fg-3)' }}>Waiting for progress...</div>
        ) : lines.slice(-8).map((line, idx) => (
          <div key={`${line.ts}-${idx}`}>
            <span style={{ color: 'var(--fg-3)' }}>{line.ts}</span> {line.line}
          </div>
        ))}
      </div>
      {operation.error && (
        <div style={{ color: 'var(--status-fail)', fontSize: 12 }}>{operation.error}</div>
      )}
    </div>
  );
}
