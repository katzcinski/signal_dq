import type { ReactNode } from 'react';

// UX-F6: shared uppercase section header (title + optional count + actions).
// Centralises the recurring "label-caps + spacing" pattern used across pages.
interface Props {
  title: string;
  count?: number;
  actions?: ReactNode;
  hint?: string;
}

export function SectionHeader({ title, count, actions, hint }: Props) {
  return (
    <div style={{ marginBottom: 'var(--s3)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s3)' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {title}{count != null ? ` (${count})` : ''}
        </span>
        {actions}
      </div>
      {hint && <p style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 'var(--s1)' }}>{hint}</p>}
    </div>
  );
}
