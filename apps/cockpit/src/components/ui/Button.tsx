import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';

// UX-F6: shared Button primitive. Spacing/radius come from tokens, not memory.
// Variants encode intent (primary action, neutral, ghost, destructive); sizes
// keep padding consistent across screens.
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

const VARIANT: Record<Variant, CSSProperties> = {
  primary:   { background: 'var(--cont)', color: '#fff', border: '1px solid var(--cont)' },
  secondary: { background: 'var(--bg-2)', color: 'var(--fg-2)', border: '1px solid var(--line-2)' },
  ghost:     { background: 'none', color: 'var(--fg-3)', border: '1px solid var(--line-2)' },
  danger:    { background: 'none', color: 'var(--status-fail)', border: '1px solid var(--status-fail)' },
};

const SIZE: Record<Size, CSSProperties> = {
  sm: { padding: 'var(--s1) var(--s3)', fontSize: 11 },
  md: { padding: 'var(--s2) var(--s4)', fontSize: 12 },
};

// UX-F8: disabled reads via a tone-shift (muted surface + dim ink), not a pure
// opacity fade — recognizable without a tooltip (WCAG 1.4.3). Spread after the
// variant so it overrides its background/border/colour.
const DISABLED: CSSProperties = {
  background: 'var(--bg-2)',
  color: 'var(--fg-3)',
  border: '1px solid var(--line)',
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  pending?: boolean;
  pendingLabel?: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  style,
  disabled,
  pending = false,
  pendingLabel,
  children,
  ...rest
}: Props) {
  const isDisabled = disabled || pending;

  return (
    <button
      disabled={isDisabled}
      aria-busy={pending || undefined}
      style={{
        borderRadius: 'var(--r-md)',
        cursor: pending ? 'wait' : isDisabled ? 'not-allowed' : 'pointer',
        transition: 'filter var(--t), background var(--t), border-color var(--t), color var(--t)',
        ...VARIANT[variant],
        ...SIZE[size],
        ...(isDisabled ? DISABLED : null),
        ...style,
      }}
      {...rest}
    >
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
