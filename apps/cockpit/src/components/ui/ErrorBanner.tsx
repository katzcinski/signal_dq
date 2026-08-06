import { t } from '@/i18n/de';

interface Props {
  message?: string;
  onRetry?: () => void;
}

// Red-tinted error panel — rendered whenever a query failed, so an API outage
// is never mistaken for an empty (all-good) state.
export function ErrorBanner({ message, onRetry }: Props) {
  return (
    <div style={{
      background: 'rgba(229, 72, 77, 0.08)', border: '1px solid var(--status-crit)',
      borderRadius: 'var(--r-md)', padding: '10px 14px', marginBottom: 16,
      display: 'flex', alignItems: 'center', gap: 'var(--s3)',
    }}>
      <span style={{ color: 'var(--status-crit)', fontSize: 12 }}>{message ?? t.common.error}</span>
      <div style={{ flex: 1 }} />
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            background: 'none', border: '1px solid var(--status-crit)', color: 'var(--status-crit)',
            borderRadius: 'var(--r-md)', padding: 'var(--s1) var(--s3)', fontSize: 12, cursor: 'pointer',
          }}
        >
          {t.common.retry}
        </button>
      )}
    </div>
  );
}
