// Gespeicherte Katalog-Ansichten: benannte Filter-Presets (Facetten + Suche),
// lokal je Nutzer (localStorage) — die Facetten selbst bleiben URL-synced,
// ein Preset setzt nur dieselben Parameter.
import { useState } from 'react';
import { FilterChip } from '@/components/ui/FilterChip';
import { t } from '@/i18n/de';

export interface SavedView {
  name: string;
  params: Record<string, string>;
}

const STORAGE_KEY = 'signal.catalog.views';

export function loadViews(storage: Pick<Storage, 'getItem'> = localStorage): SavedView[] {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (v): v is SavedView =>
        !!v && typeof v.name === 'string' && v.name.length > 0 &&
        typeof v.params === 'object' && v.params !== null,
    );
  } catch {
    return [];
  }
}

export function useSavedViews() {
  const [views, setViews] = useState<SavedView[]>(() => loadViews());

  const persist = (next: SavedView[]) => {
    setViews(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Storage voll/gesperrt — Ansicht lebt dann nur für diese Session.
    }
  };

  const save = (name: string, params: Record<string, string>) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    // Gleicher Name überschreibt (bewusstes Aktualisieren einer Ansicht).
    persist([...views.filter(v => v.name !== trimmed), { name: trimmed, params }]);
  };

  const remove = (name: string) => persist(views.filter(v => v.name !== name));

  return { views, save, remove };
}

export function SavedViewsBar({ current, hasActiveFilter, onApply }: {
  current: Record<string, string>;
  hasActiveFilter: boolean;
  onApply: (params: Record<string, string>) => void;
}) {
  const { views, save, remove } = useSavedViews();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');

  if (views.length === 0 && !hasActiveFilter) return null;

  const submit = () => {
    if (!name.trim()) return;
    save(name, current);
    setName('');
    setNaming(false);
  };

  return (
    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase' }}>
        {t.objects.savedViews}
      </span>
      {views.map(v => (
        <span key={v.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
          <FilterChip active={false} onClick={() => onApply(v.params)}>{v.name}</FilterChip>
          <button
            onClick={() => remove(v.name)}
            aria-label={t.objects.savedViewDelete.replace('{name}', v.name)}
            title={t.objects.savedViewDelete.replace('{name}', v.name)}
            style={{ background: 'none', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', fontSize: 12, padding: '0 2px' }}
          >
            ✕
          </button>
        </span>
      ))}
      {hasActiveFilter && !naming && (
        <button
          onClick={() => setNaming(true)}
          style={{
            background: 'none', border: '1px dashed var(--line-2)', borderRadius: 'var(--r-lg)',
            color: 'var(--fg-3)', cursor: 'pointer', fontSize: 12, padding: '4px 10px',
          }}
        >
          + {t.objects.savedViewSave}
        </button>
      )}
      {naming && (
        <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setNaming(false); }}
            placeholder={t.objects.savedViewNamePlaceholder}
            aria-label={t.objects.savedViewNamePlaceholder}
            style={{
              background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)',
              borderRadius: 'var(--r-md)', padding: '4px 8px', fontSize: 12, width: 160,
            }}
          />
          <button
            onClick={submit}
            disabled={!name.trim()}
            style={{
              background: 'var(--cont)', color: '#fff', border: 'none', borderRadius: 'var(--r-md)',
              padding: '4px 10px', fontSize: 12, cursor: 'pointer', opacity: name.trim() ? 1 : 0.5,
            }}
          >
            {t.common.confirm}
          </button>
        </span>
      )}
    </div>
  );
}
