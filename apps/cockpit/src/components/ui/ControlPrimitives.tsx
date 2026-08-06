import { useEffect, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode, type SelectHTMLAttributes } from 'react';
import { Button } from '@/components/ui/Button';

const controlShell: CSSProperties = {
  minHeight: 32,
  borderRadius: 'var(--r-md)',
  border: '1px solid var(--line-2)',
  background: 'color-mix(in srgb, var(--bg-2) 86%, var(--bg-3))',
  color: 'var(--fg-2)',
  boxShadow: 'var(--shadow-1)',
};

interface ToolbarButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

export function ToolbarButton({ active, children, style, type = 'button', ...rest }: ToolbarButtonProps) {
  return (
    <button
      type={type}
      aria-pressed={active ?? undefined}
      style={{
        ...controlShell,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--s2)',
        padding: '0 var(--s3)',
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: 'nowrap',
        ...(active ? {
          borderColor: 'var(--signal-line)',
          color: 'var(--signal-bright)',
          background: 'color-mix(in srgb, var(--signal) 10%, var(--bg-2))',
        } : null),
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

interface IconButtonProps extends Omit<ToolbarButtonProps, 'aria-label'> {
  label: string;
}

export function IconButton({ label, children, style, ...rest }: IconButtonProps) {
  return (
    <ToolbarButton
      aria-label={label}
      title={label}
      style={{ width: 32, minWidth: 32, padding: 0, ...style }}
      {...rest}
    >
      {children}
    </ToolbarButton>
  );
}

interface ControlSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'prefix'> {
  label: string;
  prefix?: ReactNode;
  tone?: 'neutral' | 'accent';
  shellStyle?: CSSProperties;
}

export function ControlSelect({
  label,
  prefix,
  tone = 'neutral',
  shellStyle,
  style,
  children,
  ...rest
}: ControlSelectProps) {
  const accent = tone === 'accent';

  return (
    <label
      style={{
        ...controlShell,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--s2)',
        padding: '0 var(--s2)',
        ...shellStyle,
      }}
    >
      <span className="sr-only">{label}</span>
      {prefix}
      <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', minWidth: 0 }}>
        <select
          aria-label={label}
          style={{
            appearance: 'none',
            WebkitAppearance: 'none',
            border: 0,
            background: 'transparent',
            color: accent ? 'var(--cont)' : 'var(--fg-2)',
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: accent ? 700 : 600,
            minHeight: 30,
            maxWidth: 160,
            padding: '0 18px 0 0',
            ...style,
          }}
          {...rest}
        >
          {children}
        </select>
        <svg
          aria-hidden="true"
          focusable="false"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ position: 'absolute', right: 1, pointerEvents: 'none', color: accent ? 'var(--cont)' : 'var(--fg-3)' }}
        >
          <path d="m7 10 5 5 5-5" />
        </svg>
      </span>
    </label>
  );
}

interface ConfirmDeleteButtonProps {
  label: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
}

export function ConfirmDeleteButton({
  label,
  confirmLabel,
  cancelLabel,
  onConfirm,
  disabled,
}: ConfirmDeleteButtonProps) {
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (disabled) setConfirming(false);
  }, [disabled]);

  if (!confirming) {
    return (
      <Button variant="ghost" size="sm" disabled={disabled} onClick={() => setConfirming(true)}>
        {label}
      </Button>
    );
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)', flexShrink: 0 }}>
      <Button
        variant="danger"
        size="sm"
        disabled={disabled}
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
        autoFocus
      >
        {confirmLabel}
      </Button>
      <Button variant="ghost" size="sm" disabled={disabled} onClick={() => setConfirming(false)}>
        {cancelLabel}
      </Button>
    </span>
  );
}
