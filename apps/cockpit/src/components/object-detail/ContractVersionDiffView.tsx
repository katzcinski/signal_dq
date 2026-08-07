import { useContractVersionDiff } from '@/api/contracts';
import { t } from '@/i18n/de';

function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function ContractVersionDiffView({ product, enabled }: { product: string; enabled: boolean }) {
  const { data: diff, isLoading } = useContractVersionDiff(product, enabled);
  if (isLoading || !diff) return null;

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {t.diff.versionTitle}
        </span>
        {diff.available && diff.from_version && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
            {t.diff.fromTo.replace('{from}', `v${diff.from_version}`).replace('{to}', `v${diff.to_version}`)}
          </span>
        )}
        {diff.available && diff.entries.length > 0 && (
          <span style={{
            fontSize: 10,
            borderRadius: 'var(--r)',
            padding: '2px 8px',
            background: diff.breaking ? 'rgba(196,68,68,0.15)' : 'rgba(45,164,78,0.15)',
            color: diff.breaking ? 'var(--status-fail)' : 'var(--status-ok)',
            border: `1px solid ${diff.breaking ? 'var(--status-fail)' : 'var(--status-ok)'}`,
          }}>
            {diff.breaking ? t.diff.breaking : t.diff.nonBreaking}
          </span>
        )}
      </div>

      {!diff.available ? (
        <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.diff.noBaseline}</p>
      ) : diff.entries.length === 0 ? (
        <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.diff.noChanges}</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
          {diff.entries.map((e, i) => (
            <div key={`${e.path}-${i}`} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
              borderLeft: `3px solid ${e.breaking ? 'var(--status-fail)' : 'var(--status-warn)'}`,
              background: 'var(--bg-2)',
              borderRadius: 'var(--r-md)',
              padding: 'var(--s2) var(--s3)',
            }}>
              <span style={{ fontSize: 12, color: 'var(--fg)', fontWeight: 500 }}>
                {t.diff.kinds[e.kind] ?? e.kind}
              </span>
              <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>{e.path}</span>
              <div style={{ flex: 1 }} />
              <code style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--fg-3)' }}>{fmtVal(e.old)}</code>
              <span style={{ color: 'var(--fg-3)' }}>-&gt;</span>
              <code style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: e.breaking ? 'var(--status-fail)' : 'var(--fg-2)' }}>{fmtVal(e.new)}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
