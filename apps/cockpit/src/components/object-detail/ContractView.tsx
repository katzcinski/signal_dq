import { t } from '@/i18n/de';
import type { ContractOut } from '@/types';

export function ContractView({ contract }: { contract: ContractOut }) {
  const guaranteeEntries = Object.entries(contract.guarantees ?? {}).filter(([, v]) => {
    if (!v) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === 'object') return Object.keys(v).length > 0;
    return true;
  });

  const lifecycleColor = contract.lifecycle === 'active'
    ? { bg: 'rgba(45,164,78,0.15)', fg: '#2da44e' }
    : { bg: 'var(--bg-2)', fg: 'var(--fg-3)' };

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
          v{contract.version}
        </span>
        <span style={{
          fontSize: 11,
          borderRadius: 'var(--r)',
          padding: '2px 8px',
          background: lifecycleColor.bg,
          color: lifecycleColor.fg,
          border: `1px solid ${lifecycleColor.fg}`,
        }}>
          {t.lifecycle[contract.lifecycle] ?? contract.lifecycle}
        </span>
        <span style={{ fontSize: 12, color: 'var(--fg-2)' }}>{contract.owned_by}</span>
        {contract.owners && contract.owners.length > 0 && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            {contract.owners.join(', ')}
          </span>
        )}
        {contract.compliance && (
          <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            {' '}
            {t.compliance[contract.compliance] ?? contract.compliance}
          </span>
        )}
      </div>

      {contract.description && (
        <p style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 16, lineHeight: 1.6 }}>
          {contract.description}
        </p>
      )}

      {guaranteeEntries.length === 0 ? (
        <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>Keine Garantien definiert.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {guaranteeEntries.map(([family, value]) => (
            <div key={family}>
              <div style={{
                fontSize: 11,
                color: 'var(--fg-3)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 4,
              }}>
                {t.workbench.families[family] ?? family}
              </div>
              <div style={{ background: 'var(--bg-2)', borderRadius: 'var(--r-md)', padding: 'var(--s2) var(--s3)' }}>
                <pre style={{
                  margin: 0,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--fg-2)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}>
                  {JSON.stringify(value, null, 2)}
                </pre>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
