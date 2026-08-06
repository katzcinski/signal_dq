// Beobachtete Realität je Garantie (P6): letzter Messwert, Sparkline und
// PASS/FAIL — gespeist aus GET /contracts/{id}/observed. Sitzt im Kopf des
// Garantie-Kanalzugs neben der Severity.
import { Spark } from '@/components/ui/Spark';
import { t } from '@/i18n/de';
import type { ObservedGuarantee } from '@/types';

export function ObservedSlot({ observed }: { observed?: ObservedGuarantee }) {
  if (!observed || observed.state === 'unknown') return null;
  // Repräsentativer Check: der erste mit Historie (sonst der erste).
  const check = observed.checks.find(c => c.points.length > 0) ?? observed.checks[0];
  if (!check) return null;
  const series = check.points
    .map(p => p.value)
    .filter((v): v is number => v != null);
  const ok = observed.state === 'pass';
  const color = ok ? 'var(--status-ok)' : 'var(--status-fail)';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)' }}>
      {series.length >= 2 && (
        <div style={{ width: 64, height: 22 }} aria-hidden>
          <Spark data={series} color={color} width={64} height={22} />
        </div>
      )}
      <div style={{ textAlign: 'right', lineHeight: 1.15 }}>
        <div style={{ fontSize: 9, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.workbench.observed.last}</div>
        <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>{check.last_value ?? '—'}</div>
      </div>
      <span style={{
        fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', color,
        padding: '2px 7px', borderRadius: 'var(--r)',
        background: `color-mix(in srgb, ${color} 14%, transparent)`, border: `1px solid ${color}`,
      }}>
        {ok ? t.workbench.observed.pass : t.workbench.observed.fail}
      </span>
    </div>
  );
}
