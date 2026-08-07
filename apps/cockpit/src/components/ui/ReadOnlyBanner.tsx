import { t } from '@/i18n/de';

// UX-F1: read-only is *marked*, not hidden. When the active role can't write on
// a screen, this banner sits above the actions so the mental model stays the
// same for every role — the affordances are visible but disabled, with a reason.
export function ReadOnlyBanner({ hint }: { hint?: string }) {
  return (
    <div
      role="status"
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'var(--bg-2)', border: '1px solid var(--line-2)',
        borderLeft: '3px solid var(--obs)', borderRadius: 'var(--r-md)',
        padding: 'var(--s2) var(--s3)', marginBottom: 16,
      }}
    >
      <span aria-hidden style={{ color: 'var(--obs)' }}>🔒</span>
      <span style={{ fontSize: 12, color: 'var(--fg)', fontWeight: 600 }}>{t.role.readOnlyBanner}</span>
      <span style={{ fontSize: 12, color: 'var(--fg-2)' }}>{hint ?? t.role.readOnlyHint}</span>
    </div>
  );
}
