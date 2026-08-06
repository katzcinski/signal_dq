import { useSchemaDrift } from '@/api/contracts';
import { Table, type ColDef } from '@/components/ui/Table';
import { t } from '@/i18n/de';
import type { SchemaDriftFinding } from '@/types';

// Shift-Left (§A.6): zeigt im Contract-Editor, ob die Quelle vom Schema-
// Versprechen abweicht. Read-only — Persistenz/Incident laufen beim Extrakt.
export function SchemaDriftBanner({ product, enabled = true }: { product: string; enabled?: boolean }) {
  const { data } = useSchemaDrift(product, enabled);
  if (!data || !data.object_found) return null;
  const { findings, summary } = data;
  if (findings.length === 0) return null;

  const breaking = summary.has_breaking;
  const accent = breaking ? 'var(--status-fail)' : 'var(--status-warn)';
  const isContract = data.kind === 'consumer_contract' || data.kind === 'provider_contract';

  const columns: ColDef<SchemaDriftFinding>[] = [
    {
      key: 'category', header: t.drift.colCategory,
      render: f => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          {f.breaking && (
            <span style={{
              fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.05em',
              color: 'var(--status-fail)', border: '1px solid var(--status-fail)',
              borderRadius: 'var(--r)', padding: '1px 5px',
            }}>{t.drift.breakingBadge}</span>
          )}
          {t.drift.categories[f.category] ?? f.category}
        </span>
      ),
    },
    { key: 'column', header: t.drift.colColumn, mono: true, render: f => f.column },
    { key: 'before', header: t.drift.colPromised, mono: true, render: f => f.before || '—' },
    { key: 'after', header: t.drift.colActual, mono: true, render: f => f.after || '—' },
  ];

  const summaryText = t.drift.summary
    .replace('{total}', String(summary.total))
    .replace('{breaking}', String(summary.breaking));

  return (
    <div style={{
      background: `color-mix(in srgb, ${accent} 8%, transparent)`,
      border: `1px solid ${accent}`, borderLeft: `3px solid ${accent}`,
      borderRadius: 'var(--r-lg)', padding: 'var(--s4)',
      display: 'flex', flexDirection: 'column', gap: 'var(--s3)',
    }}>
      <div>
        <div style={{ fontWeight: 600, fontSize: 13, color: accent }}>
          {breaking ? t.drift.breakingTitle : t.drift.cleanTitle}
        </div>
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{summaryText}</div>
        {breaking && isContract && (
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 4 }}>{t.drift.majorHint}</div>
        )}
      </div>
      <Table columns={columns} rows={findings} rowKey={f => `${f.category}:${f.column}`} />
    </div>
  );
}
