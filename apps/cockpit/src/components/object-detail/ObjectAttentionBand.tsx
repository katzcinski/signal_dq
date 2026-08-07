import { Link } from 'react-router-dom';
import { t } from '@/i18n/de';

interface MonitoringEntry {
  status: string;
  error?: string | null;
}

interface AttentionItem {
  key: string;
  label: string;
  detail: string;
  tab: string;
}

interface ObjectAttentionBandProps {
  failedChecks: number;
  hasContract: boolean;
  monitoringEnabled: boolean;
  monitoringEntry?: MonitoringEntry;
  hasBreakingContractDiff: boolean;
}

function replaceAllTokens(template: string, values: Record<string, string>) {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.replace(`{${key}}`, value),
    template,
  );
}

export function ObjectAttentionBand({
  failedChecks,
  hasContract,
  monitoringEnabled,
  monitoringEntry,
  hasBreakingContractDiff,
}: ObjectAttentionBandProps) {
  const items: AttentionItem[] = [];

  if (failedChecks > 0) {
    items.push({
      key: 'failed-checks',
      label: t.objectDetail.attention.failedChecks,
      detail: replaceAllTokens(t.objectDetail.attention.failedChecksDetail, {
        count: String(failedChecks),
      }),
      tab: 'checks',
    });
  }

  if (!hasContract) {
    items.push({
      key: 'missing-contract',
      label: t.objectDetail.attention.missingContract,
      detail: t.objectDetail.attention.missingContractDetail,
      tab: 'contract',
    });
  }

  if (monitoringEnabled && !monitoringEntry) {
    items.push({
      key: 'monitoring-missing',
      label: t.objectDetail.attention.monitoringMissing,
      detail: t.objectDetail.attention.monitoringMissingDetail,
      tab: 'timeseries',
    });
  }

  if (monitoringEntry?.status === 'error') {
    items.push({
      key: 'monitoring-error',
      label: t.objectDetail.attention.monitoringError,
      detail: monitoringEntry.error ?? t.objectDetail.attention.monitoringErrorDetail,
      tab: 'timeseries',
    });
  }

  if (hasBreakingContractDiff) {
    items.push({
      key: 'breaking-diff',
      label: t.objectDetail.attention.breakingDiff,
      detail: t.objectDetail.attention.breakingDiffDetail,
      tab: 'contract',
    });
  }

  if (items.length === 0) return null;

  return (
    <section
      aria-label={t.objectDetail.attention.ariaLabel}
      style={{
        border: '1px solid color-mix(in srgb, var(--status-warn) 55%, var(--line))',
        borderRadius: 'var(--r-lg)',
        background: 'color-mix(in srgb, var(--status-warn) 9%, var(--bg-1))',
        padding: 'var(--s4)',
        marginBottom: 20,
        display: 'grid',
        gap: 'var(--s3)',
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 'var(--s3)',
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        <div>
          <div style={{
            color: 'var(--fg)',
            fontSize: 'var(--fs-body)',
            lineHeight: 'var(--lh-body)',
            fontWeight: 700,
          }}>
            {items.length === 1
              ? t.objectDetail.attention.singleTitle
              : replaceAllTokens(t.objectDetail.attention.multiTitle, { count: String(items.length) })}
          </div>
          <div style={{
            color: 'var(--fg-3)',
            fontSize: 'var(--fs-meta)',
            lineHeight: 'var(--lh-meta)',
            marginTop: 4,
          }}>
            {t.objectDetail.attention.hint}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 'var(--s2)' }}>
        {items.map(item => (
          <div
            key={item.key}
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) auto',
              gap: 'var(--s3)',
              alignItems: 'center',
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              background: 'var(--bg-1)',
              padding: 'var(--s3)',
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{
                color: 'var(--fg)',
                fontSize: 'var(--fs-meta)',
                lineHeight: 'var(--lh-meta)',
                fontWeight: 700,
              }}>
                {item.label}
              </div>
              <div style={{
                color: 'var(--fg-3)',
                fontSize: 'var(--fs-meta)',
                lineHeight: 'var(--lh-meta)',
                marginTop: 2,
                overflowWrap: 'anywhere',
              }}>
                {item.detail}
              </div>
            </div>
            <Link
              to={{ search: `?tab=${item.tab}` }}
              style={{
                color: 'var(--cont)',
                fontSize: 'var(--fs-meta)',
                lineHeight: 'var(--lh-meta)',
                whiteSpace: 'nowrap',
              }}
            >
              {t.objectDetail.attention.open}
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}
