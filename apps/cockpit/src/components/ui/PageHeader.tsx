import type { CSSProperties, ReactNode } from 'react';

// UX-Konsistenz §2.1: gemeinsamer Seitenkopf. Titelgröße, Zeilenhöhe und
// Abstände kamen zuvor pro Seite als Magic Numbers (18/20px, Margin 10/14/16/20);
// hier zentral über Tokens, damit alle Hauptseiten denselben Maßstab wie die
// Objekte-Referenz nutzen. Der rechte Slot nimmt Suche/Aktionen auf.
interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Rechtsbündiger Slot für Suche, Filter-Steuerung oder Aktionen. */
  actions?: ReactNode;
  titleId?: string;
  style?: CSSProperties;
}

export function PageHeader({ title, subtitle, actions, titleId, style }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: subtitle ? 'flex-start' : 'center',
        justifyContent: 'space-between',
        gap: 'var(--s3)',
        flexWrap: 'wrap',
        marginBottom: 'var(--s4)',
        ...style,
      }}
    >
      <div>
        <h1 id={titleId} style={{ fontSize: 'var(--fs-page-title)', fontWeight: 700, lineHeight: 'var(--lh-tight)', color: 'var(--fg)', margin: 0 }}>
          {title}
        </h1>
        {subtitle != null && (
          <p style={{ color: 'var(--fg-3)', fontSize: 'var(--fs-meta)', lineHeight: 'var(--lh-meta)', margin: 'var(--s1) 0 0' }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
          {actions}
        </div>
      )}
    </div>
  );
}
