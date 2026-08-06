/**
 * Stateful Container des Schaltplan-Boards: lädt den Lineage-Graphen, baut das
 * Modell, lässt ELK layouten und verdrahtet Interaktion (Click-to-trace),
 * Filter (Suche / Layer / System), den View-Toggle und den Inspector.
 */
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useLineage } from '@/api/lineage';
import { useObjects } from '@/api/objects';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { t } from '@/i18n/de';
import { buildSchematicModel } from './model';
import { layoutSchematic, type SchematicLayout } from './layout';
import { traceCircuit, type CircuitTrace } from './trace';
import { SchematicBoard } from './SchematicBoard';
import { SchematicInspector, type InspectorSelection } from './SchematicInspector';
import { laneColor } from './theme';
import type { ObjectSummary } from '@/types';

const S = t.lineage.schematic;

const DEPTH_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: '1' },
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 20, label: S.depthAll },
];

export default function SchematicLineage() {
  const [focus, setFocus] = useSearchParamState('focus');
  const [seeds, setSeeds] = useState<string[]>(() => focus ? [focus] : []);
  const [depth, setDepth] = useState(2);
  const { data, isLoading } = useLineage({ seeds, depth, enabled: seeds.length > 0 });
  const { data: objects } = useObjects();
  // Per-Node-Expansion: Knoten-IDs, deren Spalten ausgeklappt sind. Default leer
  // → alles eingeklappt (Objekt-Ebene). Spalten-Lineage entsteht nur zwischen
  // zwei expandierten Knoten.
  const [columnsExpanded, setColumnsExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());
  const [hiddenSystems, setHiddenSystems] = useState<Set<string>>(new Set());
  const [selection, setSelection] = useState<InspectorSelection | null>(null);
  const [trace, setTrace] = useState<CircuitTrace | null>(null);
  const [layout, setLayout] = useState<SchematicLayout | null>(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const autoSelectedFocus = useRef('');

  const model = useMemo(
    () => buildSchematicModel(data?.nodes ?? [], data?.columnEdges ?? [], data?.edges ?? []),
    [data?.nodes, data?.columnEdges, data?.edges],
  );

  // ELK neu rechnen, wenn sich Modell oder Ansicht ändern. Filter/Selektion
  // ändern nur Dimming/Highlight — kein Relayout. Stale Ergebnisse verwerfen.
  const layoutToken = useRef(0);
  useEffect(() => {
    if (!model.chips.length) {
      setLayout(null);
      return;
    }
    const token = ++layoutToken.current;
    setLayoutBusy(true);
    layoutSchematic(model, columnsExpanded)
      .then(result => {
        if (token === layoutToken.current) setLayout(result);
      })
      .finally(() => {
        if (token === layoutToken.current) setLayoutBusy(false);
      });
  }, [model, columnsExpanded]);

  useEffect(() => {
    if (!focus) {
      autoSelectedFocus.current = '';
      return;
    }
    if (autoSelectedFocus.current === focus) return;
    setSeeds(prev => (prev.includes(focus) ? prev : [...prev, focus]));
  }, [focus]);

  useEffect(() => {
    if (!focus || autoSelectedFocus.current === focus) return;
    if (!model.chips.some(chip => chip.id === focus)) return;
    autoSelectedFocus.current = focus;
    setSelection({ node: focus });
    setTrace(null);
  }, [focus, model.chips]);

  const layers = useMemo(() => {
    const seen = new Map<string, { key: string; label: string; order: number; count: number }>();
    for (const c of model.chips) {
      const prev = seen.get(c.laneKey);
      if (prev) prev.count += 1;
      else seen.set(c.laneKey, { key: c.laneKey, label: c.layer, order: c.laneOrder, count: 1 });
    }
    return [...seen.values()].sort((a, b) => a.order - b.order);
  }, [model.chips]);

  const systems = useMemo(() => {
    const set = new Set<string>();
    for (const c of model.chips) if (c.system) set.add(c.system);
    return [...set].sort();
  }, [model.chips]);

  const dimmedChips = useMemo(() => {
    const dimmed = new Set<string>();
    const q = search.trim().toLowerCase();
    for (const c of model.chips) {
      const byLayer = hiddenLayers.has(c.laneKey);
      const bySystem = !!c.system && hiddenSystems.has(c.system);
      const bySearch =
        q.length > 0 &&
        !c.label.toLowerCase().includes(q) &&
        !c.pins.some(p => p.id.toLowerCase().includes(q));
      if (byLayer || bySystem || bySearch) dimmed.add(c.id);
    }
    return dimmed;
  }, [model.chips, search, hiddenLayers, hiddenSystems]);

  const selectPin = (node: string, pin: string) => {
    autoSelectedFocus.current = node;
    setFocus(node);
    setSelection({ node, pin });
    setTrace(traceCircuit(model, node, pin));
  };
  const selectChip = (node: string) => {
    autoSelectedFocus.current = node;
    setFocus(node);
    setSelection({ node });
    setTrace(null);
  };
  const clearSelection = () => {
    setSelection(null);
    setTrace(null);
  };

  const toggleSet = (setter: typeof setHiddenLayers, key: string) =>
    setter(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Spalten eines Knotens ein-/ausklappen. Beim Einklappen eines Knotens, der
  // gerade einen getracten Pin hält, den Trace verwerfen (er wäre nicht mehr
  // sichtbar).
  const toggleColumns = (id: string) => {
    setColumnsExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    if (columnsExpanded.has(id) && selection?.node === id && selection.pin) clearSelection();
  };
  const collapseAll = () => {
    setColumnsExpanded(new Set());
    if (selection?.pin) clearSelection();
  };

  const seedOptions = objects ?? [];
  const seedName = (id: string) => seedOptions.find(o => o.id === id)?.name ?? id;
  const addSeed = (id: string) => {
    setSeeds(prev => (prev.includes(id) ? prev : [...prev, id]));
    setFocus(id);
  };
  const removeSeed = (id: string) => {
    setSeeds(prev => prev.filter(s => s !== id));
    if (focus === id) setFocus('');
    clearSelection();
  };
  const hasSeeds = seeds.length > 0;

  return (
    <div style={page}>
      <div style={toolbar}>
        <span style={titleStyle}>{t.lineage.title}</span>

        {/* Seed-Auswahl: nur das Umfeld dieser Objekte wird geladen. Vor der
            ersten Wahl übernimmt das die Empty-State-Karte. */}
        {hasSeeds && (
          <>
            <div style={seedBar}>
              {seeds.map(id => (
                <span key={id} style={seedChip}>
                  {seedName(id)}
                  <button
                    type="button"
                    style={seedChipX}
                    aria-label={S.removeSeed}
                    onClick={() => removeSeed(id)}
                  >
                    ×
                  </button>
                </span>
              ))}
              <SeedSearch options={seedOptions} selected={seeds} onAdd={addSeed} />
            </div>

            <div style={toggle} aria-label={S.depthLabel}>
              {DEPTH_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  style={toggleBtn(depth === opt.value)}
                  onClick={() => setDepth(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <input
              style={searchInput}
              name="lineage-search"
              autoComplete="off"
              spellCheck={false}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={S.searchPlaceholder}
              aria-label={S.searchPlaceholder}
            />
            {columnsExpanded.size > 0 && (
              <button type="button" style={chip(true)} onClick={collapseAll}>
                {S.collapseAll}
              </button>
            )}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {systems.map(sys => {
                const active = !hiddenSystems.has(sys);
                return (
                  <button
                    key={sys}
                    type="button"
                    style={chip(active)}
                    onClick={() => toggleSet(setHiddenSystems, sys)}
                  >
                    {sys}
                  </button>
                );
              })}
            </div>
            {trace && (
              <button type="button" style={chip(true)} onClick={clearSelection}>
                {S.clearTrace}
              </button>
            )}
          </>
        )}
      </div>

      <div style={body}>
        <aside style={sidebar}>
          <h4 style={sideHeading}>{S.layers}</h4>
          {layers.map(l => {
            const active = !hiddenLayers.has(l.key);
            return (
              <button
                key={l.key}
                type="button"
                style={layerRow(active)}
                onClick={() => toggleSet(setHiddenLayers, l.key)}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: laneColor(l.order) }} />
                <span style={{ flex: 1, textAlign: 'left' }}>{l.label}</span>
                <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>{l.count}</span>
              </button>
            );
          })}
        </aside>

        <main style={canvas}>
          {!hasSeeds ? (
            <div style={seedEmptyWrap}>
              <div style={seedEmptyCard}>
                <h3 style={seedEmptyTitle}>{S.seedEmptyTitle}</h3>
                <p style={seedEmptyHint}>{S.seedEmptyHint}</p>
                <SeedSearch options={seedOptions} selected={seeds} onAdd={addSeed} autoFocus />
              </div>
            </div>
          ) : isLoading || layoutBusy ? (
            <div style={hint}>{S.loading}</div>
          ) : !layout || !model.chips.length ? (
            <div style={hint}>{S.empty}</div>
          ) : (
            <SchematicBoard
              layout={layout}
              tracePins={trace?.pins}
              traceEdges={trace?.edges}
              dimmedChips={dimmedChips}
              selectedChip={selection && !selection.pin ? selection.node : null}
              selectedPin={selection?.pin ? { node: selection.node, pin: selection.pin } : null}
              onSelectChip={selectChip}
              onSelectPin={selectPin}
              onToggleColumns={toggleColumns}
              onBackground={clearSelection}
              fitKey={seeds.join('|')}
            />
          )}
        </main>

        <aside style={inspector}>
          <SchematicInspector model={model} selection={selection} />
        </aside>
      </div>
    </div>
  );
}

/** Suchfeld mit Dropdown, um Seed-Objekte hinzuzufügen. */
function SeedSearch({
  options,
  selected,
  onAdd,
  autoFocus,
}: {
  options: ObjectSummary[];
  selected: string[];
  onAdd: (id: string) => void;
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);

  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const chosen = new Set(selected);
    const next: ObjectSummary[] = [];
    for (const option of options) {
      if (chosen.has(option.id)) continue;
      if (
        needle &&
        !option.name.toLowerCase().includes(needle) &&
        !option.id.toLowerCase().includes(needle)
      ) continue;
      next.push(option);
      if (next.length === 8) break;
    }
    return next;
  }, [options, selected, q]);

  const pick = (id: string) => {
    onAdd(id);
    setQ('');
    setOpen(false);
  };

  return (
    <div style={seedSearchWrap}>
      <input
        style={seedSearchInput}
        name="lineage-seed-search"
        autoComplete="off"
        spellCheck={false}
        value={q}
        autoFocus={autoFocus}
        onChange={e => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        placeholder={S.seedSearchPlaceholder}
        aria-label={S.seedSearchPlaceholder}
      />
      {open && (
        <ul style={seedDropdown}>
          {matches.length === 0 ? (
            <li style={seedNoMatch}>{S.noObjects}</li>
          ) : (
            matches.map(o => (
              <li key={o.id}>
                <button
                  type="button"
                  style={seedOption}
                  // onMouseDown feuert vor dem Input-blur, sonst schließt das Dropdown zuerst.
                  onMouseDown={e => {
                    e.preventDefault();
                    pick(o.id);
                  }}
                >
                  <span style={seedOptionName}>{o.name}</span>
                  <span style={seedOptionMeta}>{o.layer}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

// ---- styles ----
const page: CSSProperties = { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 };
const toolbar: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderBottom: '1px solid var(--line)',
  flexWrap: 'wrap', flexShrink: 0,
};
const titleStyle: CSSProperties = { fontSize: 15, fontWeight: 600, color: 'var(--fg)' };
const searchInput: CSSProperties = {
  flex: 1, minWidth: 160, maxWidth: 320, background: 'var(--bg-1)', border: '1px solid var(--line)',
  borderRadius: 'var(--r-md)', color: 'var(--fg)', fontSize: 13, padding: '8px 11px',
};
const toggle: CSSProperties = {
  display: 'flex', background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden',
};
const toggleBtn = (active: boolean): CSSProperties => ({
  background: active ? 'var(--cont)' : 'transparent', color: active ? '#fff' : 'var(--fg-2)',
  border: 'none', fontSize: 12, fontWeight: 600, padding: '7px 12px', cursor: 'pointer',
});
const chip = (active: boolean): CSSProperties => ({
  fontSize: 11.5, fontWeight: 500, padding: '6px 10px', borderRadius: 'var(--r-full)',
  border: `1px solid ${active ? 'var(--cont)' : 'var(--line)'}`,
  color: active ? 'var(--fg)' : 'var(--fg-3)',
  background: active ? 'color-mix(in srgb, var(--cont) 12%, transparent)' : 'var(--bg-1)', cursor: 'pointer',
});
const body: CSSProperties = { display: 'flex', flex: 1, minHeight: 0 };
const sidebar: CSSProperties = {
  width: 210, borderRight: '1px solid var(--line)', padding: '14px 12px', overflowY: 'auto', flexShrink: 0,
};
const sideHeading: CSSProperties = {
  fontSize: 11, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-3)', margin: '0 0 10px', fontWeight: 600,
};
const layerRow = (active: boolean): CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 'var(--s2)', width: '100%', padding: '6px 4px', borderRadius: 'var(--r)',
  fontSize: 12.5, cursor: 'pointer', color: active ? 'var(--fg-2)' : 'var(--fg-3)', background: 'transparent',
  border: 'none', opacity: active ? 1 : 0.5,
});
// Pan/Zoom übernimmt das Navigieren — daher kein Scroll-Overflow mehr.
const canvas: CSSProperties = { flex: 1, overflow: 'hidden', background: 'var(--bg-1)', position: 'relative' };
const inspector: CSSProperties = {
  width: 320, borderLeft: '1px solid var(--line)', padding: 'var(--s4)', overflowY: 'auto', flexShrink: 0,
};

// ---- Seed-Auswahl ----
const seedBar: CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' };
const seedChip: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600,
  padding: '5px 6px 5px 10px', borderRadius: 'var(--r-full)', color: 'var(--fg)',
  border: '1px solid var(--cont)', background: 'color-mix(in srgb, var(--cont) 16%, transparent)',
};
const seedChipX: CSSProperties = {
  display: 'grid', placeItems: 'center', width: 16, height: 16, borderRadius: 'var(--r-full)',
  border: 'none', background: 'transparent', color: 'var(--fg-2)', cursor: 'pointer', fontSize: 14, lineHeight: 1,
};
const seedSearchWrap: CSSProperties = { position: 'relative' };
const seedSearchInput: CSSProperties = {
  minWidth: 180, background: 'var(--bg-1)', border: '1px dashed var(--line-2)', borderRadius: 'var(--r-md)',
  color: 'var(--fg)', fontSize: 13, padding: '7px 11px',
};
const seedDropdown: CSSProperties = {
  position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 20, minWidth: 240, maxWidth: 320,
  margin: 0, padding: 4, listStyle: 'none', background: 'var(--bg-2)', border: '1px solid var(--line-2)',
  borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-2)', maxHeight: 280, overflowY: 'auto',
};
const seedOption: CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, width: '100%',
  padding: '7px 9px', borderRadius: 'var(--r)', border: 'none', background: 'transparent',
  color: 'var(--fg)', fontSize: 13, cursor: 'pointer', textAlign: 'left',
};
const seedOptionName: CSSProperties = { fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const seedOptionMeta: CSSProperties = { color: 'var(--fg-3)', fontSize: 11, flexShrink: 0 };
const seedNoMatch: CSSProperties = { padding: '8px 9px', color: 'var(--fg-3)', fontSize: 12.5 };
const seedEmptyWrap: CSSProperties = { display: 'grid', placeItems: 'center', height: '100%', padding: 24 };
const seedEmptyCard: CSSProperties = {
  maxWidth: 440, width: '100%', textAlign: 'center', background: 'var(--bg-2)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: '28px 28px 32px',
  boxShadow: 'var(--shadow-1)',
};
const seedEmptyTitle: CSSProperties = { margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--fg)' };
const seedEmptyHint: CSSProperties = { margin: '0 0 18px', fontSize: 13, lineHeight: 1.5, color: 'var(--fg-2)' };
const hint: CSSProperties = { color: 'var(--fg-3)', fontSize: 13, padding: 40, textAlign: 'center' };
