import { t } from '@/i18n/de';
import { Tooltip } from './Tooltip';

// UX-F1: dual-ownership at a glance. A small lock + family-neutral tag marking
// whether an object/contract is platform- or product-owned. Not an auth gate -
// it explains *why* a write may be blocked for the current role.
export function OwnershipTag({ ownedBy }: { ownedBy: string | undefined }) {
  const isPlatform = ownedBy === 'platform';
  const label = isPlatform ? t.role.ownedPlatform : t.role.ownedProduct;
  const color = isPlatform ? 'var(--cont)' : 'var(--obs)';
  const hint = isPlatform ? t.role.tooltips.ownerLockPlatform : t.role.tooltips.ownerLockProduct;

  return (
    <Tooltip content={hint}>
      <span
        aria-label={`${t.role.ownerLock}: ${label}. ${hint}`}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)',
          fontSize: 10, color, border: `1px solid ${color}55`,
          background: `${color}1A`, borderRadius: 'var(--r)', padding: '1px 6px',
          whiteSpace: 'nowrap',
        }}
      >
        <span aria-hidden>{'\u{1F512}'}</span>{label}
      </span>
    </Tooltip>
  );
}
