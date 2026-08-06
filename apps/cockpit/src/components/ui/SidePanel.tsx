import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { t } from '@/i18n/de';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

interface Props {
  title: ReactNode;
  onClose: () => void;
  width?: number;
  footer?: ReactNode;
  children: ReactNode;
}

export function SidePanel({ title, onClose, width = 460, footer, children }: Props) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const id = window.setTimeout(() => closeRef.current?.focus(), 0);

    return () => {
      window.clearTimeout(id);
      const previous = previousFocusRef.current;
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const onDialogKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;

    const focusable = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
      .filter(node => node.offsetParent !== null || node === closeRef.current);
    if (focusable.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 55, background: 'rgba(0,0,0,0.46)' }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={onDialogKeyDown}
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width,
          maxWidth: '92vw',
          background: 'var(--bg-1)',
          borderLeft: '1px solid var(--line)',
          boxShadow: '-10px 0 30px rgba(0,0,0,0.36)',
          display: 'flex',
          flexDirection: 'column',
          overscrollBehavior: 'contain',
        }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--s3)',
          padding: '14px 18px',
          borderBottom: '1px solid var(--line)',
        }}
        >
          <div id={titleId} style={{ fontSize: 14, fontWeight: 700, minWidth: 0 }}>
            {title}
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label={t.common.close}
            style={{
              width: 30,
              height: 30,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'var(--bg-2)',
              border: '1px solid var(--line-2)',
              color: 'var(--fg-2)',
              borderRadius: 'var(--r-md)',
              fontSize: 13,
              fontWeight: 700,
              lineHeight: 1,
            }}
          >
            x
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>{children}</div>
        {footer && <div style={{ borderTop: '1px solid var(--line)', padding: '12px 18px' }}>{footer}</div>}
      </div>
    </div>
  );
}
