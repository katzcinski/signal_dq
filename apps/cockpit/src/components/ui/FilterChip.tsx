import type { ReactNode } from 'react';
import { t } from '@/i18n/de';

// UX-Konsistenz §2.2: gemeinsame Filter-Chip-Primitiven. Der identische
// `chipBtn`-Stil war in ObjectCatalog, CheckLibrary und Incidents handkopiert;
// die entfernbaren Aktiv-Filter-Chips existierten nur lokal im Objekt-Katalog.
// Hier zentral, damit jede Liste dieselbe Toolbar wie die Objekte-Referenz nutzt.

// Toggle-Chip: an/aus-Filter (z. B. Familie, Status). `active` treibt die Tönung.
export function FilterChip({
  active,
  onClick,
  children,
  ...rest
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
} & Pick<React.ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'title'>) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: '4px 10px',
        borderRadius: 'var(--r-full)',
        border: active ? '1px solid var(--cont)' : '1px solid var(--line-2)',
        background: active ? 'var(--cont)' : 'var(--bg-2)',
        color: active ? '#fff' : 'var(--fg-3)',
        fontSize: 11,
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

// Aktiv-Filter-Chip: zeigt einen gesetzten Filter mit Einzel-Clear (×).
export function ActiveFilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--s1)',
        padding: '2px 6px 2px 8px',
        borderRadius: 'var(--r-full)',
        background: 'var(--cont)',
        color: '#fff',
        fontSize: 11,
      }}
    >
      {label}
      <button
        onClick={onClear}
        aria-label={`${t.objects.clearFilters}: ${label}`}
        style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 0, fontSize: 14, lineHeight: 1 }}
      >
        ×
      </button>
    </span>
  );
}
