import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import type Cytoscape from 'cytoscape';
import { useLineage } from '@/api/lineage';
import { useObjects } from '@/api/objects';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { deriveLane, lineageNodeLabel } from '@/lib/lineage';
import { t } from '@/i18n/de';
import type { LineageEdge, LineageNode, ObjectSummary } from '@/types';

let dagreRegistered = false;

function registerDagre(CytoscapeFactory: typeof Cytoscape, dagre: unknown) {
  if (dagreRegistered) return;
  CytoscapeFactory.use(dagre as Parameters<typeof CytoscapeFactory.use>[0]);
  dagreRegistered = true;
}

interface ThemeTokens {
  bg1: string;
  bg2: string;
  bg3: string;
  fg: string;
  fg2: string;
  fg3: string;
  line: string;
  line2: string;
  cont: string;
  obs: string;
  qual: string;
  statusOk: string;
  statusWarn: string;
  statusFail: string;
  fontMono: string;
}

type CoverageKey = 'covered' | 'partial' | 'gap' | 'out_of_scope';

interface ContextMenuState {
  nodeId: string;
  x: number;
  y: number;
}

const LEGACY_DEPTH = 2;
const CONTEXT_MENU_WIDTH = 190;

const COVERAGE_OPTIONS: Array<{ key: CoverageKey; label: string }> = [
  { key: 'covered', label: t.lineage.covered },
  { key: 'partial', label: t.lineage.partial },
  { key: 'gap', label: t.lineage.gap },
  { key: 'out_of_scope', label: t.lineage.outOfScope },
];

function resolveTheme(): ThemeTokens {
  const styles = getComputedStyle(document.documentElement);
  const cssVar = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
  return {
    bg1: cssVar('--bg-1', '#11151b'),
    bg2: cssVar('--bg-2', '#1a1f27'),
    bg3: cssVar('--bg-3', '#222c3e'),
    fg: cssVar('--fg', '#e7ebf2'),
    fg2: cssVar('--fg-2', '#aab3c2'),
    fg3: cssVar('--fg-3', '#5e6877'),
    line: cssVar('--line', '#27303a'),
    line2: cssVar('--line-2', '#313945'),
    cont: cssVar('--cont', '#5e83e6'),
    obs: cssVar('--obs', '#f59e0b'),
    qual: cssVar('--qual', '#00d4aa'),
    statusOk: cssVar('--status-ok', '#2da44e'),
    statusWarn: cssVar('--status-warn', '#d97706'),
    statusFail: cssVar('--status-fail', '#c44444'),
    fontMono: cssVar('--font-mono', "'JetBrains Mono', monospace"),
  };
}

function useThemeVersion(): number {
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return undefined;
    const observer = new MutationObserver(() => setVersion(v => v + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'data-density'],
    });
    return () => observer.disconnect();
  }, []);

  return version;
}

function coverageKey(flag: unknown): CoverageKey {
  const value = String(flag ?? '').toLowerCase();
  if (value === 'covered' || value === '\u25cf') return 'covered';
  if (value === 'partial' || value === '\u25d0') return 'partial';
  if (value === 'gap' || value === '\u25b2' || value === '\u25b3') return 'gap';
  return 'out_of_scope';
}

function coverageColor(key: CoverageKey, theme: ThemeTokens): string {
  switch (key) {
    case 'covered': return theme.statusOk;
    case 'partial': return theme.statusWarn;
    case 'gap': return theme.statusFail;
    default: return theme.fg3;
  }
}

function familyColor(node: LineageNode, theme: ThemeTokens): string {
  switch (node.family) {
    case 'observability': return theme.obs;
    case 'quality': return theme.qual;
    case 'contract': return theme.cont;
    default: return coverageColor(coverageKey(node.coverage_flag), theme);
  }
}

function edgeKind(edge: Pick<LineageEdge, 'type' | 'edgeType'>): string {
  return edge.type || edge.edgeType || 'lineage';
}

function edgeColor(kind: string, theme: ThemeTokens): string {
  switch (kind) {
    case 'computed': return theme.statusWarn;
    case 'passthrough': return theme.fg3;
    case 'direct': return theme.statusOk;
    default: return theme.line2;
  }
}

function statusColor(status: string | undefined, theme: ThemeTokens): string {
  switch (status) {
    case 'pass': return theme.statusOk;
    case 'warn': return theme.statusWarn;
    case 'fail':
    case 'critical': return theme.statusFail;
    default: return theme.fg3;
  }
}

function isInsideViewport(cy: Cytoscape.Core, node: Cytoscape.CollectionReturnValue): boolean {
  const box = node.renderedBoundingBox({ includeLabels: true });
  const margin = 28;
  return (
    box.x1 >= margin &&
    box.y1 >= margin &&
    box.x2 <= cy.width() - margin &&
    box.y2 <= cy.height() - margin
  );
}

function shouldReduceMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

function contextMenuPoint(event: Cytoscape.EventObject, container: HTMLDivElement) {
  const rendered = event.renderedPosition;
  const rect = container.getBoundingClientRect();
  const original = event.originalEvent as MouseEvent | TouchEvent | undefined;
  const clientPoint =
    original && 'clientX' in original
      ? { x: original.clientX - rect.left, y: original.clientY - rect.top }
      : null;
  const raw = rendered ?? clientPoint ?? { x: 12, y: 12 };
  return {
    x: Math.max(8, Math.min(raw.x, Math.max(8, container.clientWidth - CONTEXT_MENU_WIDTH - 8))),
    y: Math.max(8, Math.min(raw.y, Math.max(8, container.clientHeight - 128))),
  };
}

function filterNodes(
  nodes: LineageNode[],
  layerFilter: string,
  coverageFilter: string,
  search: string,
) {
  const q = search.trim().toLowerCase();
  return nodes.filter(node => {
    const lane = deriveLane(node);
    if (layerFilter && lane.key !== layerFilter) return false;
    if (coverageFilter && coverageKey(node.coverage_flag) !== coverageFilter) return false;
    if (!q) return true;
    const label = lineageNodeLabel(node).toLowerCase();
    return label.includes(q) || node.id.toLowerCase().includes(q) || lane.label.toLowerCase().includes(q);
  });
}

interface SelectionPanelProps {
  node: LineageNode;
  onClose: () => void;
  onOpenObject: (id: string) => void;
}

function SelectionPanel({ node, onClose, onOpenObject }: SelectionPanelProps) {
  const lane = deriveLane(node);
  const key = coverageKey(node.coverage_flag);
  const coverage = COVERAGE_OPTIONS.find(option => option.key === key)?.label ?? t.lineage.outOfScope;

  return (
    <aside style={selectionPanel}>
      <div style={selectionHeader}>
        <strong style={{ fontSize: 14 }}>{lineageNodeLabel(node)}</strong>
        <button type="button" onClick={onClose} style={iconButton} aria-label={t.common.close}>
          x
        </button>
      </div>
      <dl style={metaList}>
        <Meta label={t.lineage.layerLabel} value={lane.label} />
        <Meta label={t.lineage.dqStatus} value={node.dq_status ?? '-'} />
        <Meta label="Coverage" value={coverage} />
        {node.family && <Meta label={t.lineage.family} value={node.family} />}
        {node.space && <Meta label="Space" value={node.space} />}
        {node.last_run && <Meta label={t.lineage.lastRun} value={node.last_run} />}
      </dl>
      <button type="button" onClick={() => onOpenObject(node.id)} style={primaryButton}>
        {t.lineage.openObject}
      </button>
    </aside>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div style={metaRow}>
      <dt style={metaLabel}>{label}</dt>
      <dd style={metaValue}>{value}</dd>
    </div>
  );
}

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
  const selectedIds = useMemo(() => new Set(selected), [selected]);

  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const next: ObjectSummary[] = [];
    for (const option of options) {
      if (selectedIds.has(option.id)) continue;
      if (
        needle &&
        !option.name.toLowerCase().includes(needle) &&
        !option.id.toLowerCase().includes(needle)
      ) continue;
      next.push(option);
      if (next.length === 8) break;
    }
    return next;
  }, [options, q, selectedIds]);

  const pick = (id: string) => {
    onAdd(id);
    setQ('');
    setOpen(false);
  };

  return (
    <div style={seedSearchWrap}>
      <input
        style={seedSearchInput}
        name="lineage-legacy-seed-search"
        autoComplete="off"
        spellCheck={false}
        value={q}
        autoFocus={autoFocus}
        onChange={event => {
          setQ(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        placeholder={t.lineage.schematic.seedSearchPlaceholder}
        aria-label={t.lineage.schematic.seedSearchPlaceholder}
      />
      {open && (
        <ul style={seedDropdown}>
          {matches.length === 0 ? (
            <li style={seedNoMatch}>{t.lineage.schematic.noObjects}</li>
          ) : (
            matches.map(option => (
              <li key={option.id}>
                <button
                  type="button"
                  style={seedOption}
                  onMouseDown={event => {
                    event.preventDefault();
                    pick(option.id);
                  }}
                >
                  <span style={seedOptionName}>{option.name}</span>
                  <span style={seedOptionMeta}>{option.layer}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function NodeContextMenu({
  node,
  x,
  y,
  onInspect,
  onOpenObject,
  onLoadScope,
}: {
  node: LineageNode;
  x: number;
  y: number;
  onInspect: () => void;
  onOpenObject: () => void;
  onLoadScope: () => void;
}) {
  return (
    <div role="menu" aria-label={t.lineage.contextMenuLabel} style={contextMenu(x, y)}>
      <div style={contextMenuTitle}>{lineageNodeLabel(node)}</div>
      <button type="button" role="menuitem" style={contextMenuItem} onClick={onInspect}>
        {t.lineage.contextInspect}
      </button>
      <button type="button" role="menuitem" style={contextMenuItem} onClick={onLoadScope}>
        {t.lineage.contextLoadScope}
      </button>
      <button type="button" role="menuitem" style={contextMenuItem} onClick={onOpenObject}>
        {t.lineage.openObject}
      </button>
    </div>
  );
}

export default function LegacyLineageMap() {
  const navigate = useNavigate();
  const [layerFilter, setLayerFilter] = useSearchParamState('layer');
  const [coverageFilter, setCoverageFilter] = useSearchParamState('status');
  const [search, setSearch] = useSearchParamState('search');
  const [focus, setFocus] = useSearchParamState('focus');
  const [seedIds, setSeedIds] = useState<string[]>(() => (focus ? [focus] : []));
  const hasSeeds = seedIds.length > 0;
  const { data, isLoading, isError } = useLineage({
    seeds: seedIds,
    depth: LEGACY_DEPTH,
    enabled: hasSeeds,
  });
  const { data: objects } = useObjects();
  const cyRef = useRef<HTMLDivElement>(null);
  const cyInstance = useRef<Cytoscape.Core | null>(null);
  const [graphReady, setGraphReady] = useState(0);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [contextMenuState, setContextMenuState] = useState<ContextMenuState | null>(null);
  const themeVersion = useThemeVersion();

  const seedOptions = objects ?? [];
  const seedName = (id: string) => seedOptions.find(option => option.id === id)?.name ?? id;
  const addSeed = (id: string) => {
    setSeedIds(prev => (prev.includes(id) ? prev : [...prev, id]));
    setFocus(id);
  };
  const removeSeed = (id: string) => {
    setSeedIds(prev => prev.filter(seed => seed !== id));
    if (focus === id) setFocus('');
    setContextMenuState(null);
  };
  const loadSingleSeed = (id: string) => {
    setSeedIds([id]);
    setFocus(id);
    setContextMenuState(null);
  };

  const layers = useMemo(() => {
    const byKey = new Map<string, { key: string; label: string; order: number }>();
    for (const node of data?.nodes ?? []) {
      const lane = deriveLane(node);
      if (!byKey.has(lane.key)) byKey.set(lane.key, { key: lane.key, label: lane.label, order: lane.order });
    }
    return [...byKey.values()].sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
  }, [data?.nodes]);

  const visibleNodes = useMemo(
    () => filterNodes(data?.nodes ?? [], layerFilter, coverageFilter, search),
    [coverageFilter, data?.nodes, layerFilter, search],
  );

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map(node => node.id)), [visibleNodes]);

  const visibleEdges = useMemo(
    () => (data?.edges ?? []).filter(edge => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)),
    [data?.edges, visibleNodeIds],
  );

  const selectedNode = useMemo(
    () => (data?.nodes ?? []).find(node => node.id === focus) ?? null,
    [data?.nodes, focus],
  );

  const contextNode = useMemo(
    () => (data?.nodes ?? []).find(node => node.id === contextMenuState?.nodeId) ?? null,
    [contextMenuState?.nodeId, data?.nodes],
  );

  useEffect(() => {
    if (!cyRef.current || visibleNodes.length === 0) return undefined;

    let cancelled = false;
    let cy: Cytoscape.Core | null = null;
    let ro: ResizeObserver | null = null;
    const container = cyRef.current;

    const init = async () => {
      const [{ default: CytoscapeFactory }, { default: dagre }] = await Promise.all([
        import('cytoscape'),
        import('cytoscape-dagre'),
      ]);
      if (cancelled) return;

      registerDagre(CytoscapeFactory, dagre);
      const theme = resolveTheme();

      try {
        cy = CytoscapeFactory({
          container,
          elements: {
            nodes: visibleNodes.map(node => {
              const lane = deriveLane(node);
              return {
                data: {
                  id: node.id,
                  label: lineageNodeLabel(node),
                  layer: lane.label,
                  accent: familyColor(node, theme),
                  coverage: coverageColor(coverageKey(node.coverage_flag), theme),
                  status: statusColor(node.dq_status, theme),
                },
              };
            }),
            edges: visibleEdges.map((edge, index) => {
              const kind = edgeKind(edge);
              return {
                data: {
                  id: edge.id || `${edge.source}->${edge.target}:${index}`,
                  source: edge.source,
                  target: edge.target,
                  kind,
                  color: edgeColor(kind, theme),
                },
              };
            }),
          },
          style: [
            {
              selector: 'node',
              style: {
                'shape': 'roundrectangle',
                'width': 152,
                'height': 46,
                'background-color': theme.bg2,
                'border-color': 'data(accent)',
                'border-width': 2,
                'label': 'data(label)',
                'color': theme.fg,
                'font-family': theme.fontMono,
                'font-size': 10,
                'font-weight': 600,
                'text-max-width': 128,
                'text-overflow-wrap': 'anywhere',
                'text-valign': 'center',
                'text-halign': 'center',
                'overlay-opacity': 0,
              } as Record<string, unknown>,
            },
            {
              selector: 'node:selected, .is-focused',
              style: {
                'border-color': theme.cont,
                'border-width': 3,
                'background-color': theme.bg3,
              } as Record<string, unknown>,
            },
            {
              selector: 'edge',
              style: {
                'curve-style': 'bezier',
                'line-color': 'data(color)',
                'target-arrow-color': 'data(color)',
                'target-arrow-shape': 'triangle',
                'arrow-scale': 0.7,
                'width': 1.8,
                'opacity': 0.86,
              } as Record<string, unknown>,
            },
          ],
          layout: { name: 'preset' },
          minZoom: 0.2,
          maxZoom: 2.8,
          userPanningEnabled: true,
          userZoomingEnabled: true,
          wheelSensitivity: 0.2,
        });
      } catch (err) {
        setGraphError(err instanceof Error ? err.message : String(err));
        return;
      }

      cy.on('tap', 'node', event => {
        const id = String(event.target.id());
        setFocus(id);
        setContextMenuState(null);
      });
      cy.on('tap', event => {
        if (event.target === cy) {
          setFocus('');
          setContextMenuState(null);
        }
      });
      cy.on('cxttap', 'node', event => {
        event.originalEvent?.preventDefault();
        const id = String(event.target.id());
        setFocus(id);
        setContextMenuState({ nodeId: id, ...contextMenuPoint(event, container) });
      });
      cy.on('dbltap', 'node', event => {
        const id = String(event.target.id());
        if (id) navigate(`/objects/${encodeURIComponent(id)}`);
      });

      cy.layout({
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 58,
        rankSep: 116,
        fit: true,
        padding: 42,
      } as Cytoscape.LayoutOptions).run();

      cyInstance.current = cy;
      setGraphReady(value => value + 1);

      if (typeof ResizeObserver !== 'undefined') {
        ro = new ResizeObserver(() => {
          cy?.resize();
        });
        ro.observe(container);
      }
    };

    void init();

    return () => {
      cancelled = true;
      ro?.disconnect();
      cy?.destroy();
      if (cyInstance.current === cy) cyInstance.current = null;
    };
  }, [navigate, setFocus, themeVersion, visibleEdges, visibleNodes]);

  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    cy.elements().removeClass('is-focused');
    if (!focus) return;
    const node = cy.getElementById(focus);
    if (node.empty()) return;
    node.addClass('is-focused');
    cy.nodes(':selected').unselect();
    node.select();
    if (!isInsideViewport(cy, node)) {
      if (shouldReduceMotion()) {
        cy.center(node);
      } else {
        cy.animate({ center: { eles: node } }, { duration: 180, easing: 'ease-out' });
      }
    }
  }, [focus, graphReady]);

  return (
    <div style={page}>
      <div style={toolbar}>
        {hasSeeds && (
          <div style={seedBar}>
            {seedIds.map(id => (
              <span key={id} style={seedChip}>
                {seedName(id)}
                <button
                  type="button"
                  style={seedChipX}
                  aria-label={t.lineage.schematic.removeSeed}
                  onClick={() => removeSeed(id)}
                >
                  x
                </button>
              </span>
            ))}
            <SeedSearch options={seedOptions} selected={seedIds} onAdd={addSeed} />
          </div>
        )}
        {hasSeeds && data && (
          <>
            <select
              value={layerFilter}
              onChange={event => setLayerFilter(event.target.value)}
              aria-label={t.lineage.layerLabel}
              style={control}
            >
              <option value="">{t.lineage.allLayers}</option>
              {layers.map(layer => (
                <option key={layer.key} value={layer.key}>{layer.label}</option>
              ))}
            </select>
            <select
              value={coverageFilter}
              onChange={event => setCoverageFilter(event.target.value)}
              aria-label={t.lineage.allCoverage}
              style={control}
            >
              <option value="">{t.lineage.allCoverage}</option>
              {COVERAGE_OPTIONS.map(option => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>
            <input
              value={search}
              onChange={event => setSearch(event.target.value)}
              aria-label={t.lineage.searchPlaceholder}
              placeholder={t.lineage.searchPlaceholder}
              style={{ ...control, minWidth: 220 }}
            />
            <span style={countPill}>{visibleNodes.length} / {data.nodes.length}</span>
            {data.extract_age != null && (
              <span style={{ ...countPill, color: data.stale ? 'var(--status-warn)' : 'var(--fg-3)' }}>
                {t.lineage.extractAge}: {data.extract_age}
              </span>
            )}
          </>
        )}
      </div>

      <div style={canvasShell}>
        {!hasSeeds ? (
          <div style={seedEmptyWrap}>
            <div style={seedEmptyCard}>
              <h3 style={seedEmptyTitle}>{t.lineage.schematic.seedEmptyTitle}</h3>
              <p style={seedEmptyHint}>{t.lineage.schematic.seedEmptyHint}</p>
              <SeedSearch options={seedOptions} selected={seedIds} onAdd={addSeed} autoFocus />
            </div>
          </div>
        ) : isError ? (
          <div style={messageError}>Backend nicht erreichbar - bitte Backend starten und Seite neu laden.</div>
        ) : isLoading || !data ? (
          <div style={message}>{t.common.loading}</div>
        ) : data.nodes.length === 0 ? (
          <div style={message}>{t.lineage.schematic.empty}</div>
        ) : graphError ? (
          <div style={messageError}>Graph-Fehler: {graphError}</div>
        ) : visibleNodes.length === 0 ? (
          <div style={message}>{t.common.noData}</div>
        ) : (
          <div
            ref={cyRef}
            data-testid="legacy-lineage-map"
            style={canvas}
            onContextMenu={event => event.preventDefault()}
          />
        )}
        {selectedNode && (
          <SelectionPanel
            node={selectedNode}
            onClose={() => setFocus('')}
            onOpenObject={id => navigate(`/objects/${encodeURIComponent(id)}`)}
          />
        )}
        {contextMenuState && contextNode && (
          <NodeContextMenu
            node={contextNode}
            x={contextMenuState.x}
            y={contextMenuState.y}
            onInspect={() => {
              setFocus(contextNode.id);
              setContextMenuState(null);
            }}
            onLoadScope={() => loadSingleSeed(contextNode.id)}
            onOpenObject={() => navigate(`/objects/${encodeURIComponent(contextNode.id)}`)}
          />
        )}
      </div>
    </div>
  );
}

const page: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  minHeight: 0,
};

const toolbar: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--s2)',
  flexWrap: 'wrap',
  flexShrink: 0,
  marginBottom: 'var(--s3)',
};

const control: CSSProperties = {
  background: 'var(--bg-1)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-md)',
  color: 'var(--fg)',
  fontSize: 12,
  padding: '7px 10px',
};

const countPill: CSSProperties = {
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-full)',
  color: 'var(--fg-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  padding: '4px 9px',
};

const seedBar: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexWrap: 'wrap',
};

const seedChip: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  fontSize: 12,
  fontWeight: 600,
  padding: '5px 6px 5px 10px',
  borderRadius: 'var(--r-full)',
  color: 'var(--fg)',
  border: '1px solid var(--cont)',
  background: 'color-mix(in srgb, var(--cont) 16%, transparent)',
};

const seedChipX: CSSProperties = {
  display: 'grid',
  placeItems: 'center',
  width: 16,
  height: 16,
  borderRadius: 'var(--r-full)',
  border: 'none',
  background: 'transparent',
  color: 'var(--fg-2)',
  cursor: 'pointer',
  fontSize: 14,
  lineHeight: 1,
};

const seedSearchWrap: CSSProperties = {
  position: 'relative',
};

const seedSearchInput: CSSProperties = {
  minWidth: 180,
  background: 'var(--bg-1)',
  border: '1px dashed var(--line-2)',
  borderRadius: 'var(--r-md)',
  color: 'var(--fg)',
  fontSize: 13,
  padding: '7px 11px',
};

const seedDropdown: CSSProperties = {
  position: 'absolute',
  top: 'calc(100% + 4px)',
  left: 0,
  zIndex: 20,
  minWidth: 240,
  maxWidth: 320,
  margin: 0,
  padding: 4,
  listStyle: 'none',
  background: 'var(--bg-2)',
  border: '1px solid var(--line-2)',
  borderRadius: 'var(--r-md)',
  boxShadow: 'var(--shadow-2)',
  maxHeight: 280,
  overflowY: 'auto',
};

const seedOption: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  width: '100%',
  padding: '7px 9px',
  borderRadius: 'var(--r)',
  border: 'none',
  background: 'transparent',
  color: 'var(--fg)',
  fontSize: 13,
  cursor: 'pointer',
  textAlign: 'left',
};

const seedOptionName: CSSProperties = {
  fontFamily: 'var(--font-mono)',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const seedOptionMeta: CSSProperties = {
  color: 'var(--fg-3)',
  fontSize: 11,
  flexShrink: 0,
};

const seedNoMatch: CSSProperties = {
  padding: '8px 9px',
  color: 'var(--fg-3)',
  fontSize: 12.5,
};

const seedEmptyWrap: CSSProperties = {
  display: 'grid',
  placeItems: 'center',
  height: '100%',
  padding: 24,
};

const seedEmptyCard: CSSProperties = {
  maxWidth: 440,
  width: '100%',
  textAlign: 'center',
  background: 'var(--bg-2)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-lg)',
  padding: '28px 28px 32px',
  boxShadow: 'var(--shadow-1)',
};

const seedEmptyTitle: CSSProperties = {
  margin: '0 0 8px',
  fontSize: 16,
  fontWeight: 600,
  color: 'var(--fg)',
};

const seedEmptyHint: CSSProperties = {
  margin: '0 0 18px',
  fontSize: 13,
  lineHeight: 1.5,
  color: 'var(--fg-2)',
};

const canvasShell: CSSProperties = {
  position: 'relative',
  flex: 1,
  minHeight: 0,
  overflow: 'hidden',
  background: 'var(--bg-1)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-lg)',
};

const canvas: CSSProperties = {
  width: '100%',
  height: '100%',
};

const selectionPanel: CSSProperties = {
  position: 'absolute',
  top: 0,
  right: 0,
  width: 300,
  maxWidth: 'min(300px, 100%)',
  height: '100%',
  overflowY: 'auto',
  background: 'var(--bg-1)',
  borderLeft: '1px solid var(--line)',
  padding: 'var(--s4)',
  boxShadow: 'var(--shadow-2)',
};

const selectionHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 'var(--s3)',
  marginBottom: 'var(--s4)',
};

const iconButton: CSSProperties = {
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-md)',
  background: 'var(--bg-2)',
  color: 'var(--fg-2)',
  width: 26,
  height: 26,
};

const metaList: CSSProperties = {
  display: 'grid',
  gap: 'var(--s2)',
  marginBottom: 'var(--s4)',
};

const metaRow: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 'var(--s3)',
  borderBottom: '1px solid var(--line)',
  paddingBottom: 'var(--s2)',
};

const metaLabel: CSSProperties = {
  color: 'var(--fg-3)',
  fontSize: 11,
};

const metaValue: CSSProperties = {
  color: 'var(--fg)',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  textAlign: 'right',
  overflowWrap: 'anywhere',
};

const primaryButton: CSSProperties = {
  width: '100%',
  border: '1px solid var(--cont)',
  borderRadius: 'var(--r-md)',
  background: 'var(--cont)',
  color: '#fff',
  fontSize: 12,
  fontWeight: 700,
  padding: '8px 12px',
};

const contextMenu = (x: number, y: number): CSSProperties => ({
  position: 'absolute',
  left: x,
  top: y,
  zIndex: 30,
  width: CONTEXT_MENU_WIDTH,
  padding: 4,
  background: 'var(--bg-2)',
  border: '1px solid var(--line-2)',
  borderRadius: 'var(--r-md)',
  boxShadow: 'var(--shadow-2)',
});

const contextMenuTitle: CSSProperties = {
  color: 'var(--fg-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  overflow: 'hidden',
  padding: '6px 8px',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const contextMenuItem: CSSProperties = {
  width: '100%',
  border: 'none',
  borderRadius: 'var(--r)',
  background: 'transparent',
  color: 'var(--fg)',
  cursor: 'pointer',
  display: 'block',
  fontSize: 12,
  padding: '7px 8px',
  textAlign: 'left',
};

const message: CSSProperties = {
  color: 'var(--fg-3)',
  padding: 40,
  textAlign: 'center',
};

const messageError: CSSProperties = {
  color: 'var(--status-fail)',
  padding: 40,
  textAlign: 'center',
};
