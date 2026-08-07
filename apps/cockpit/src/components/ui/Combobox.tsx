import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  width?: number | string;
}

/**
 * Filter-as-you-type dropdown over a fixed option set. No free text:
 * the committed value can only ever be one of `options` - typing merely
 * filters; blur/Escape reverts the input to the last committed value.
 */
export function Combobox({ options, value, onChange, placeholder, ariaLabel, width = 200 }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value);
  const [activeIndex, setActiveIndex] = useState(0);
  const [listboxStyle, setListboxStyle] = useState<React.CSSProperties | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setText(value); }, [value]);

  const filtered = options.filter(o => o.toLowerCase().includes(text.toLowerCase()));
  const clamped = Math.min(activeIndex, Math.max(filtered.length - 1, 0));

  const commit = (option: string) => {
    onChange(option);
    setText(option);
    setOpen(false);
  };

  const revert = () => {
    setText(value);
    setOpen(false);
  };

  const updateListboxPosition = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;

    const rect = root.getBoundingClientRect();
    const gutter = 8;
    const gap = 2;
    const maxMenuHeight = 200;
    const minMenuHeight = 80;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const menuWidth = Math.min(rect.width, Math.max(0, viewportWidth - gutter * 2));
    const left = Math.min(
      Math.max(rect.left, gutter),
      Math.max(gutter, viewportWidth - menuWidth - gutter),
    );
    const roomBelow = Math.max(0, viewportHeight - rect.bottom - gutter - gap);
    const roomAbove = Math.max(0, rect.top - gutter - gap);
    const openUp = roomBelow < minMenuHeight && roomAbove > roomBelow;
    const availableHeight = openUp ? roomAbove : roomBelow;
    const menuHeight = Math.min(maxMenuHeight, Math.max(minMenuHeight, availableHeight));
    const top = openUp
      ? Math.max(gutter, rect.top - gap - menuHeight)
      : Math.min(rect.bottom + gap, Math.max(gutter, viewportHeight - gutter - menuHeight));

    setListboxStyle({ position: 'fixed', top, left, width: menuWidth, maxHeight: menuHeight });
  }, []);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      const inRoot = rootRef.current?.contains(target);
      const inListbox = listboxRef.current?.contains(target);
      if (!inRoot && !inListbox) revert();
    };
    if (open) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, value]);

  useEffect(() => {
    if (!open) {
      setListboxStyle(null);
      return;
    }

    updateListboxPosition();
    window.addEventListener('resize', updateListboxPosition);
    window.addEventListener('scroll', updateListboxPosition, true);
    return () => {
      window.removeEventListener('resize', updateListboxPosition);
      window.removeEventListener('scroll', updateListboxPosition, true);
    };
  }, [open, updateListboxPosition]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && filtered[clamped]) commit(filtered[clamped]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      revert();
    }
  };

  return (
    <div ref={rootRef} style={{ position: 'relative', width }}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={open ? `${id}-listbox` : undefined}
        aria-activedescendant={open && filtered[clamped] ? `${id}-option-${clamped}` : undefined}
        aria-autocomplete="list"
        aria-label={ariaLabel ?? placeholder}
        autoComplete="off"
        spellCheck={false}
        value={text}
        placeholder={placeholder}
        onChange={e => { setText(e.target.value); setOpen(true); setActiveIndex(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        style={{
          width: '100%', background: 'var(--bg-2)', border: '1px solid var(--line-2)',
          color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12,
          fontFamily: 'var(--font-mono)',
        }}
      />
      {open && listboxStyle && createPortal(
        <div
          id={`${id}-listbox`}
          ref={listboxRef}
          role="listbox"
          style={{
            ...listboxStyle, zIndex: 10000,
            background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
            overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}
        >
          {filtered.length === 0 ? (
            <div style={{ padding: '6px 10px', fontSize: 11, color: 'var(--fg-3)' }}>-</div>
          ) : filtered.slice(0, 50).map((o, i) => (
            <button
              id={`${id}-option-${i}`}
              key={o}
              type="button"
              role="option"
              aria-selected={o === value}
              tabIndex={-1}
              // mousedown beats the input blur/doc-click handler
              onMouseDown={e => { e.preventDefault(); commit(o); }}
              onMouseEnter={() => setActiveIndex(i)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                background: i === clamped ? 'var(--bg-3)' : 'none', border: 'none',
                color: 'var(--fg)', padding: '5px 10px', fontSize: 12,
                fontFamily: 'var(--font-mono)', cursor: 'pointer',
              }}
            >
              {o}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
