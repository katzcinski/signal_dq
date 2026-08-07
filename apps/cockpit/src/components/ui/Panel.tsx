import type { Family } from '@/types';
import type { ReactNode } from 'react';

const FAMILY_COLOR: Record<Family, string> = {
  observability: 'var(--obs)',
  quality:       'var(--qual)',
  contract:      'var(--cont)',
};

interface Props {
  title: string;
  family?: Family;
  actions?: ReactNode;
  children: ReactNode;
}

export function Panel({ title, family, actions, children }: Props) {
  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)',
      ...(family ? { borderLeft: `3px solid ${FAMILY_COLOR[family]}` } : {}),
      borderRadius: 'var(--r-lg)', overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: 'var(--s2) var(--s4)', borderBottom: '1px solid var(--line)',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', letterSpacing: '0.01em' }}>
          {title}
        </span>
        {actions && <div>{actions}</div>}
      </div>
      <div style={{ padding: 'var(--s3) var(--s4)' }}>{children}</div>
    </div>
  );
}
