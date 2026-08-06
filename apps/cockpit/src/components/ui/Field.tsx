import type { CSSProperties, InputHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react';

// UX-F6: shared form-control primitives. One control style (bg/border/radius/
// padding from tokens) and one labelled-field wrapper, so screens stop
// re-declaring the same input styling inline.
export const controlStyle: CSSProperties = {
  background: 'var(--bg-2)',
  border: '1px solid var(--line-2)',
  borderRadius: 'var(--r-md)',
  padding: 'var(--s1) var(--s2)',
  color: 'var(--fg)',
  fontSize: 12,
};

export function Input({ style, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input style={{ ...controlStyle, ...style }} {...rest} />;
}

export function Select({ style, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select style={{ ...controlStyle, ...style }} {...rest}>{children}</select>;
}

interface FieldProps {
  label: string;
  hint?: string;
  children: ReactNode;
  style?: CSSProperties;
}

export function Field({ label, hint, children, style }: FieldProps) {
  return (
    <label style={{ display: 'block', ...style }}>
      <span style={{ fontSize: 10, color: 'var(--fg-3)', display: 'block', marginBottom: 'var(--s1)' }}>
        {label}
      </span>
      {children}
      {hint && <span style={{ fontSize: 10, color: 'var(--fg-3)', display: 'block', marginTop: 'var(--s1)' }}>{hint}</span>}
    </label>
  );
}
