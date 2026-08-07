import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';

// UX-F6: shared surface primitive. The bg/border/radius and the padding scale
// live here instead of being re-typed as inline styles on every screen.
type Pad = 'none' | 'sm' | 'md' | 'lg';

const PAD: Record<Pad, string | number> = {
  none: 0,
  sm: 'var(--s3)',
  md: 'var(--s4)',
  lg: 'var(--s5)',
};

interface Props extends HTMLAttributes<HTMLDivElement> {
  pad?: Pad;
  /** Left accent bar colour (e.g. a family token). */
  accent?: string;
  children: ReactNode;
}

export function Card({ pad = 'md', accent, style, children, ...rest }: Props) {
  const base: CSSProperties = {
    background: 'var(--bg-1)',
    border: '1px solid var(--line)',
    borderLeft: accent ? `3px solid ${accent}` : undefined,
    borderRadius: 'var(--r-lg)',
    padding: PAD[pad],
  };
  return <div style={{ ...base, ...style }} {...rest}>{children}</div>;
}
