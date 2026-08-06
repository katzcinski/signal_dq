import { t } from '@/i18n/de';

// UX-Konsistenz §2.2: kompakter Lifecycle-Chip (Entwurf/Aktiv/Veraltet).
// Zuvor lokal in Products.tsx; jetzt geteilt, damit Listen (Products,
// Governance) denselben Chip statt je eigener Darstellungen nutzen.
export function LifecycleTag({ lifecycle }: { lifecycle: string }) {
  const color = lifecycle === 'active'
    ? 'var(--status-ok)'
    : lifecycle === 'deprecated'
      ? 'var(--status-stale)'
      : 'var(--fg-3)';
  return (
    <span style={{
      // color-mix statt Hex-Alpha-Suffix: an var(--…) angehängte Alpha-Nibbles
      // sind ungültiges CSS und wurden still verworfen (Chip ohne Tönung/Rahmen).
      background: `color-mix(in srgb, ${color} 10%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 33%, transparent)`,
      borderRadius: 'var(--r)',
      color,
      display: 'inline-flex',
      fontSize: 10,
      padding: '1px 6px',
      whiteSpace: 'nowrap',
    }}>
      {t.lifecycle[lifecycle] ?? lifecycle}
    </span>
  );
}
