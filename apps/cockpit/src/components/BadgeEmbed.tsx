import { toast } from 'sonner';
import { t } from '@/i18n/de';

// Embeddable read-only compliance badge (R4-5). The backend serves an SVG at
// /api/badge/{product}; this surfaces it with a live preview and copyable
// Markdown / HTML / URL snippets for SAC, Confluence or a README.
//
// The snippet uses an absolute URL off the current origin. When the cockpit is
// served from the same origin as the API (the standard deployment), this is the
// correct embeddable link; in split-origin setups, point it at the API origin.
export function BadgeEmbed({ product }: { product: string }) {
  const relUrl = `/api/badge/${encodeURIComponent(product)}`;
  const absUrl = `${window.location.origin}${relUrl}`;
  const markdown = `![DQ ${product}](${absUrl})`;
  const html = `<img src="${absUrl}" alt="DQ ${product}" />`;

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).then(
      () => toast.success(t.badge.copied),
      () => toast.error(t.badge.copyError),
    );
  };

  const btn: React.CSSProperties = {
    background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg-2)',
    borderRadius: 'var(--r-md)', padding: '5px 12px', fontSize: 12, cursor: 'pointer',
  };

  return (
    <div style={{ marginTop: 16, padding: 'var(--s4)', background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)' }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{t.badge.title}</div>
      <p style={{ color: 'var(--fg-3)', fontSize: 12, margin: '4px 0 12px' }}>{t.badge.hint}</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)', flexWrap: 'wrap' }}>
        <span style={{ color: 'var(--fg-3)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.badge.preview}</span>
        <img src={relUrl} alt={`DQ ${product}`} style={{ height: 20 }} />
        <div style={{ flex: 1 }} />
        <button style={btn} onClick={() => copy(markdown)}>{t.badge.copyMarkdown}</button>
        <button style={btn} onClick={() => copy(html)}>{t.badge.copyHtml}</button>
        <button style={btn} onClick={() => copy(absUrl)}>{t.badge.copyUrl}</button>
      </div>
    </div>
  );
}
