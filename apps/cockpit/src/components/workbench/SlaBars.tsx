// SLA-Uptime-Balken (sichtbar wenn lifecycle = active).
import { useContractSla } from '@/api/contracts';
import { slaColor } from '@/components/ui/SlaWindowValue';
import { t } from '@/i18n/de';
import { monoStyle } from './shared';

export function SlaBars({ product }: { product: string }) {
  const { data } = useContractSla(product);
  if (!data) return null;
  const windows: ['7d' | '30d' | '90d', number | null][] = [
    ['7d', data.windows['7d']], ['30d', data.windows['30d']], ['90d', data.windows['90d']],
  ];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 200 }}>
      <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.workbench.slaTitle}</div>
      {windows.map(([label, pct]) => (
        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
          <span style={{ ...monoStyle, fontSize: 10, width: 28, color: 'var(--fg-3)' }}>{label}</span>
          <div style={{ flex: 1, height: 6, background: 'var(--bg-3)', borderRadius: 3, overflow: 'hidden' }}>
            {pct != null && (
              <div style={{
                width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%',
                background: slaColor(pct),
              }} />
            )}
          </div>
          <span style={{ ...monoStyle, fontSize: 10, width: 64, textAlign: 'right', color: 'var(--fg-2)' }}>
            {pct != null ? `${pct.toFixed(1)} %` : t.workbench.slaNoData}
          </span>
        </div>
      ))}
    </div>
  );
}
