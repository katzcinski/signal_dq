import { Link } from 'react-router-dom';

// UX-F7: breadcrumbs for deep paths (Objekt → Run → Lineage) so location is
// always legible, instead of relying on a single back-button. The last crumb is
// the current page (no link); earlier crumbs navigate up the hierarchy.
export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" style={{ marginBottom: 12 }}>
      <ol style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6, listStyle: 'none', padding: 0, margin: 0 }}>
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {c.to && !last ? (
                <Link to={c.to} style={{ fontSize: 12, color: 'var(--fg-3)' }}>{c.label}</Link>
              ) : (
                <span aria-current={last ? 'page' : undefined} style={{ fontSize: 12, color: last ? 'var(--fg-2)' : 'var(--fg-3)', fontWeight: last ? 600 : 400 }}>
                  {c.label}
                </span>
              )}
              {!last && <span aria-hidden style={{ color: 'var(--fg-3)', fontSize: 11 }}>/</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
