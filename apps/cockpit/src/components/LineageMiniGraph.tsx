import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import type Cytoscape from 'cytoscape';
import { lineageNodeLabel } from '@/lib/lineage';
import type { LineageGraph, LineageNode } from '@/types';

let dagreRegistered = false;

function registerDagre(CytoscapeFactory: typeof Cytoscape, dagre: unknown) {
  if (dagreRegistered) return;
  CytoscapeFactory.use(dagre as Parameters<typeof CytoscapeFactory.use>[0]);
  dagreRegistered = true;
}

interface LineageMiniGraphProps {
  subgraph: LineageGraph;
}

interface ThemeTokens {
  bg1: string;
  bg2: string;
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

function resolveTheme(): ThemeTokens {
  const styles = getComputedStyle(document.documentElement);
  const cssVar = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
  return {
    bg1: cssVar('--bg-1', '#11151B'),
    bg2: cssVar('--bg-2', '#1A1F27'),
    fg: cssVar('--fg', '#E7EBF2'),
    fg2: cssVar('--fg-2', '#AAB3C2'),
    fg3: cssVar('--fg-3', '#5E6877'),
    line: cssVar('--line', '#27303A'),
    line2: cssVar('--line-2', '#313945'),
    cont: cssVar('--cont', '#5E83E6'),
    obs: cssVar('--obs', '#F59E0B'),
    qual: cssVar('--qual', '#00D4AA'),
    statusOk: cssVar('--status-ok', '#2da44e'),
    statusWarn: cssVar('--status-warn', '#d97706'),
    statusFail: cssVar('--status-fail', '#c44444'),
    fontMono: cssVar('--font-mono', "'JetBrains Mono', monospace"),
  };
}

function coverageColor(node: LineageNode, theme: ThemeTokens): string {
  const flag = String(node.coverage_flag ?? '').toLowerCase();
  if (flag === 'covered' || flag === '●') return theme.statusOk;
  if (flag === 'partial' || flag === '◐') return theme.statusWarn;
  if (flag === 'gap' || flag === '△') return theme.statusFail;
  return '';
}

function nodeColor(node: LineageNode, theme: ThemeTokens): string {
  const coverage = coverageColor(node, theme);
  if (coverage) return coverage;
  const role = String(node.role ?? '').toLowerCase();
  if (role.includes('source')) return theme.obs;
  if (role.includes('core') || role.includes('transformation')) return theme.qual;
  if (role.includes('consumption') || role.includes('fact') || role.includes('dimension')) return theme.cont;
  return theme.line2;
}

function SparseLineageState({ node }: { node: LineageNode }) {
  const navigate = useNavigate();
  const label = lineageNodeLabel(node);
  const meta = [node.layer, node.role].filter(Boolean).join(' · ');
  return (
    <div
      data-testid="lineage-mini-graph-sparse"
      style={{
        alignItems: 'stretch',
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--cont) 8%, var(--bg-1)), var(--bg-1))',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--s4)',
        minHeight: 220,
        padding: 'var(--s5)',
        textAlign: 'left',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--s3)', flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: 'var(--fg-3)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Upstream context
          </div>
          <div style={{ color: 'var(--fg)', fontSize: 16, fontWeight: 700, marginTop: 4 }}>
            No upstream objects in the current extract
          </div>
        </div>
        <span style={{
          border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-full)',
          background: 'var(--bg-2)',
          color: 'var(--fg-2)',
          fontSize: 11,
          padding: '2px 8px',
          whiteSpace: 'nowrap',
        }}
        >
          Single-node view
        </span>
      </div>

      <button
        onClick={() => navigate(`/objects/${encodeURIComponent(node.id)}`)}
        style={{
          alignItems: 'flex-start',
          background: 'var(--bg-2)',
          border: '1px solid color-mix(in srgb, var(--cont) 40%, var(--line))',
          borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-1)',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          padding: '14px 16px',
          textAlign: 'left',
        }}
      >
        <div style={{ color: 'var(--fg)', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700 }}>
          {label}
        </div>
        {meta && (
          <div style={{ color: 'var(--fg-3)', fontSize: 11 }}>
            {meta}
          </div>
        )}
        <span style={{ color: 'var(--cont)', fontSize: 11, fontWeight: 600, marginTop: 2 }}>
          Open object detail
        </span>
      </button>
      <div style={{ color: 'var(--fg-2)', fontSize: 12, lineHeight: 1.6, maxWidth: 460 }}>
        This preview currently resolves to one mapped object, so it stays focused on that object instead of drawing an empty
        lineage board.
      </div>
    </div>
  );
}

export function LineageMiniGraph({ subgraph }: LineageMiniGraphProps) {
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const sparse = subgraph.nodes.length <= 1 || subgraph.edges.length === 0;
  const graphHeight = Math.max(280, Math.min(420, 220 + subgraph.nodes.length * 28));

  useEffect(() => {
    if (!ref.current || subgraph.nodes.length === 0 || sparse) return undefined;

    let cancelled = false;
    let cy: Cytoscape.Core | null = null;
    let ro: ResizeObserver | null = null;
    const container = ref.current;

    const init = async () => {
      const [{ default: CytoscapeFactory }, { default: dagre }] = await Promise.all([
        import('cytoscape'),
        import('cytoscape-dagre'),
      ]);
      if (cancelled || !container) return;
      registerDagre(CytoscapeFactory, dagre);

      const theme = resolveTheme();
      cy = CytoscapeFactory({
        container,
        elements: {
          nodes: subgraph.nodes.map(node => ({
            data: {
              ...node,
              id: node.id,
              label: lineageNodeLabel(node),
              color: nodeColor(node, theme),
            },
          })),
          edges: subgraph.edges.map((edge, index) => ({
            data: {
              ...edge,
              id: edge.id || `${edge.source}->${edge.target}:${index}`,
              source: edge.source,
              target: edge.target,
            },
          })),
        },
        style: [
          {
            selector: 'node',
            style: {
              'label': 'data(label)',
              'shape': 'roundrectangle',
              'background-color': theme.bg2,
              'border-color': 'data(color)',
              'border-width': 2,
              'color': theme.fg,
              'font-family': theme.fontMono,
              'font-size': 10,
              'font-weight': 600,
              'height': 34,
              'padding': 10,
              'text-halign': 'center',
              'text-valign': 'center',
              'text-max-width': '150px',
              'text-wrap': 'ellipsis',
              'width': 'label',
            } as Record<string, unknown>,
          },
          {
            selector: 'edge',
            style: {
              'arrow-scale': 0.7,
              'curve-style': 'bezier',
              'line-color': theme.line2,
              'line-opacity': 0.9,
              'target-arrow-color': theme.line2,
              'target-arrow-shape': 'triangle',
              'width': 1.6,
            } as Record<string, unknown>,
          },
          {
            selector: 'node:selected',
            style: {
              'background-color': theme.cont,
              'border-color': theme.fg2,
            } as Record<string, unknown>,
          },
        ],
        layout: { name: 'preset' },
        maxZoom: 2.2,
        minZoom: 0.25,
        userPanningEnabled: true,
        userZoomingEnabled: true,
        wheelSensitivity: 0.2,
      });

      cy.on('tap', 'node', event => {
        const id = String(event.target.id());
        if (id) navigate(`/objects/${encodeURIComponent(id)}`);
      });

      cy.layout({
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 42,
        rankSep: 88,
        fit: true,
        padding: 30,
      } as Cytoscape.LayoutOptions).run();

      window.setTimeout(() => {
        if (!cy?.destroyed()) cy?.fit(undefined, 30);
      }, 0);

      if (typeof ResizeObserver !== 'undefined') {
        ro = new ResizeObserver(() => {
          cy?.resize();
          cy?.fit(undefined, 30);
        });
        ro.observe(container);
      }
    };

    void init();

    return () => {
      cancelled = true;
      ro?.disconnect();
      cy?.destroy();
    };
  }, [navigate, sparse, subgraph]);

  if (subgraph.nodes.length === 0) {
    return (
      <div style={{ color: 'var(--fg-3)', fontSize: 12, padding: 'var(--s6)', textAlign: 'center' }}>
        No lineage nodes.
      </div>
    );
  }

  if (sparse) {
    return <SparseLineageState node={subgraph.nodes[0]} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
      <div style={{ color: 'var(--fg-3)', fontSize: 11 }}>
        {subgraph.nodes.length} nodes · {subgraph.edges.length} edges
      </div>
      <div
        ref={ref}
        data-testid="lineage-mini-graph"
        style={{
          background:
            'radial-gradient(circle at top left, color-mix(in srgb, var(--cont) 10%, transparent), transparent 52%), var(--bg-1)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-lg)',
          height: graphHeight,
          minHeight: 280,
          overflow: 'hidden',
          width: '100%',
        }}
      />
    </div>
  );
}
