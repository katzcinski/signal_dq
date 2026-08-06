import { Link } from 'react-router-dom';
import { t } from '@/i18n/de';

export interface NotFoundAction {
  label: string;
  to: string;
  primary?: boolean;
}

interface Props {
  code?: string;
  title?: string;
  message?: string;
  actions?: NotFoundAction[];
}

// Sackgassen-Guard: einheitlicher „nicht gefunden"-Zustand mit Ausweg. Statt
// eines nackten Grautexts (aus dem man nur über die Sidebar herauskäme) zeigt er
// Titel, Erklärung und mindestens einen Weg zurück in die Hierarchie — sowohl für
// die 404-Catch-all-Route als auch für leere Detail-Ansichten (Objekt/Run/Produkt).
export function NotFoundState({ code = '404', title, message, actions }: Props) {
  const links = actions ?? [{ label: t.notFound.home, to: '/', primary: true }];
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        gap: 'var(--s3)',
        maxWidth: 460,
        margin: '0 auto',
        padding: 'var(--s6) var(--s5)',
      }}
    >
      <span className="mono-label" style={{ color: 'var(--fg-3)', letterSpacing: '0.08em' }}>
        {code}
      </span>
      <h1 style={{ fontSize: 'var(--fs-h2)', fontWeight: 700, color: 'var(--fg)', margin: 0 }}>
        {title ?? t.notFound.title}
      </h1>
      <p style={{ color: 'var(--fg-3)', fontSize: 13, lineHeight: 1.6, margin: 0 }}>
        {message ?? t.notFound.message}
      </p>
      <div
        style={{
          display: 'flex',
          gap: 'var(--s2)',
          flexWrap: 'wrap',
          justifyContent: 'center',
          marginTop: 'var(--s2)',
        }}
      >
        {links.map(action => (
          <Link
            key={action.to}
            to={action.to}
            style={{
              borderRadius: 'var(--r-md)',
              padding: 'var(--s2) var(--s4)',
              fontSize: 12,
              textDecoration: 'none',
              border: `1px solid ${action.primary ? 'var(--cont)' : 'var(--line-2)'}`,
              background: action.primary ? 'var(--cont)' : 'var(--bg-2)',
              color: action.primary ? '#fff' : 'var(--fg-2)',
            }}
          >
            {action.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
