import type { ReactNode } from 'react';

interface ObjectSummaryCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}

export function ObjectSummaryCard({ label, value, hint, tone = 'var(--cont)' }: ObjectSummaryCardProps) {
  return (
    <div className="object-summary-card">
      <div style={{
        color: 'var(--fg-3)',
        fontSize: 'var(--fs-eyebrow)',
        lineHeight: 'var(--lh-meta)',
        textTransform: 'uppercase',
        letterSpacing: 0,
        marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{
        color: tone,
        fontSize: 'var(--fs-h2)',
        lineHeight: 'var(--lh-tight)',
        fontWeight: 700,
        minHeight: 22,
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--s2)',
        flexWrap: 'wrap',
      }}>
        {value}
      </div>
      {hint && (
        <div style={{
          color: 'var(--fg-3)',
          fontSize: 'var(--fs-meta)',
          lineHeight: 'var(--lh-meta)',
          marginTop: 8,
        }}>
          {hint}
        </div>
      )}
    </div>
  );
}
