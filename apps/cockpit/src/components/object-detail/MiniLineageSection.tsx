import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useLineage } from '@/api/lineage';
import { t } from '@/i18n/de';
import { MiniLineageSkeleton } from './ObjectDetailSkeletons';
import type { LineageGraph, LineageNode } from '@/types';

const BOX_W = 144;
const BOX_H = 34;
const H_GAP = 56;
const V_GAP = 10;
const MINI_LINEAGE_DEPTH = 20;

function colH(count: number): number {
  return Math.max(1, count) * (BOX_H + V_GAP) - V_GAP;
}

function boxY(svgH: number, idx: number, total: number): number {
  const totalH = colH(total);
  return (svgH - totalH) / 2 + idx * (BOX_H + V_GAP);
}

function truncate(s: string, max = 17): string {
  return s.length > max ? s.slice(0, max - 1) + '...' : s;
}

interface ObjectEdge {
  id: string;
  source: string;
  target: string;
}

interface LayoutNode {
  id: string;
  x: number;
  y: number;
}

function objectEdges(graph: LineageGraph): ObjectEdge[] {
  const seen = new Set<string>();
  const out: ObjectEdge[] = [];
  const add = (source?: string, target?: string, id?: string) => {
    if (!source || !target || source === target) return;
    const key = `${source}->${target}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ id: id || key, source, target });
  };
  for (const edge of graph.edges) add(edge.source, edge.target, edge.id);
  for (const edge of graph.columnEdges ?? []) add(edge.source, edge.target);
  return out;
}

function distancesFrom(seed: string, edges: ObjectEdge[], reverse = false): Map<string, number> {
  const adj = new Map<string, string[]>();
  for (const edge of edges) {
    const from = reverse ? edge.target : edge.source;
    const to = reverse ? edge.source : edge.target;
    const next = adj.get(from);
    if (next) next.push(to);
    else adj.set(from, [to]);
  }

  const distances = new Map<string, number>();
  const queue: Array<{ id: string; depth: number }> = [{ id: seed, depth: 0 }];
  distances.set(seed, 0);
  for (let i = 0; i < queue.length; i += 1) {
    const { id, depth } = queue[i];
    for (const next of adj.get(id) ?? []) {
      if (distances.has(next)) continue;
      distances.set(next, depth + 1);
      queue.push({ id: next, depth: depth + 1 });
    }
  }
  distances.delete(seed);
  return distances;
}

function groupsByDistance(ids: string[], distances: Map<string, number>, descending = false): string[][] {
  const grouped = new Map<number, string[]>();
  for (const id of ids) {
    const depth = distances.get(id);
    if (!depth) continue;
    const group = grouped.get(depth);
    if (group) group.push(id);
    else grouped.set(depth, [id]);
  }
  const depths = [...grouped.keys()].sort((a, b) => (descending ? b - a : a - b));
  return depths.map(depth => grouped.get(depth)!.sort());
}

function FullLineageLink({ focusId }: { focusId: string }) {
  return (
    <Link
      to={`/lineage?focus=${encodeURIComponent(focusId)}`}
      style={{ color: 'var(--cont)', fontSize: 11 }}
    >
      {t.objectDetail.lineageOpenFull}
    </Link>
  );
}

function SparseState({
  focusId,
  title,
  detail,
}: {
  focusId: string;
  title: string;
  detail: string;
}) {
  return (
    <div
      data-testid="mini-lineage-sparse"
      style={{
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        background: 'var(--bg-2)',
        padding: 'var(--s5)',
        display: 'grid',
        gap: 'var(--s3)',
      }}
    >
      <div>
        <div style={{
          color: 'var(--fg)',
          fontSize: 'var(--fs-body)',
          lineHeight: 'var(--lh-body)',
          fontWeight: 700,
        }}>
          {title}
        </div>
        <div style={{
          color: 'var(--fg-3)',
          fontSize: 'var(--fs-meta)',
          lineHeight: 'var(--lh-meta)',
          marginTop: 4,
        }}>
          {detail}
        </div>
      </div>
      <div>
        <FullLineageLink focusId={focusId} />
      </div>
    </div>
  );
}

export function MiniLineageSection({ focusId }: { focusId: string }) {
  const { data: graph, isLoading } = useLineage({ seeds: [focusId], depth: MINI_LINEAGE_DEPTH, enabled: !!focusId });
  const navigate = useNavigate();
  const lineage = useMemo(() => {
    const nodeMap = new Map((graph?.nodes ?? []).map(n => [n.id, n]));
    if (!graph) {
      return { nodeMap, focusNode: undefined, edges: [], upstreamGroups: [], downstreamGroups: [] };
    }
    const edges = objectEdges(graph);
    const upstreamDistances = distancesFrom(focusId, edges, true);
    const downstreamDistances = distancesFrom(focusId, edges);
    const upstreamIds = [...upstreamDistances.keys()].filter(id => nodeMap.has(id));
    const downstreamIds = [...downstreamDistances.keys()].filter(id => nodeMap.has(id));
    const upstreamGroups = groupsByDistance(upstreamIds, upstreamDistances, true);
    const downstreamGroups = groupsByDistance(downstreamIds, downstreamDistances);
    return {
      nodeMap,
      focusNode: nodeMap.get(focusId),
      edges,
      upstreamGroups,
      downstreamGroups,
    };
  }, [focusId, graph]);

  if (isLoading) {
    return <MiniLineageSkeleton />;
  }

  if (!graph || graph.nodes.length === 0) {
    return (
      <SparseState
        focusId={focusId}
        title={t.objectDetail.lineageEmptyTitle}
        detail={t.objectDetail.lineageEmptyDetail}
      />
    );
  }

  if (lineage.upstreamGroups.length === 0 && lineage.downstreamGroups.length === 0) {
    return (
      <SparseState
        focusId={focusId}
        title={t.objectDetail.lineageFocusedTitle}
        detail={t.objectDetail.lineageFocusedDetail}
      />
    );
  }

  const groups = [...lineage.upstreamGroups, [focusId], ...lineage.downstreamGroups];
  const columnXs = groups.map((_, idx) => idx * (BOX_W + H_GAP));
  const svgH = Math.max(...groups.map(group => colH(group.length)), BOX_H) + 20;
  const svgW = groups.length * BOX_W + (groups.length - 1) * H_GAP;
  const layoutNodes = new Map<string, LayoutNode>();
  groups.forEach((group, groupIdx) => {
    group.forEach((id, idx) => {
      layoutNodes.set(id, {
        id,
        x: columnXs[groupIdx],
        y: boxY(svgH, idx, group.length),
      });
    });
  });
  const visibleEdges = lineage.edges.filter(edge => layoutNodes.has(edge.source) && layoutNodes.has(edge.target));
  const focusLayout = layoutNodes.get(focusId)!;
  const focusX = focusLayout.x;
  const focusY = (svgH - BOX_H) / 2;

  const curve = (x1: number, y1: number, x2: number, y2: number) => {
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`;
  };

  return (
    <div data-testid="mini-lineage-dag">
      <svg
        width={svgW}
        height={svgH}
        style={{ display: 'block', maxWidth: '100%', overflow: 'visible' }}
        aria-label={`Lineage: ${focusId}`}
      >
        <defs>
          <marker id="mini-dag-arr" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <polygon points="0 0, 7 3.5, 0 7" fill="var(--fg-3)" opacity={0.5} />
          </marker>
        </defs>

        {visibleEdges.map(edge => {
          const source = layoutNodes.get(edge.source)!;
          const target = layoutNodes.get(edge.target)!;
          return (
            <path
              key={edge.id}
              d={curve(source.x + BOX_W, source.y + BOX_H / 2, target.x, target.y + BOX_H / 2)}
              stroke="var(--line-2)"
              strokeWidth={1.5}
              fill="none"
              markerEnd="url(#mini-dag-arr)"
            />
          );
        })}

        <g transform={`translate(${focusX},${focusY})`}>
          <rect width={BOX_W} height={BOX_H} rx={4} fill="var(--cont)" />
          <text x={BOX_W / 2} y={BOX_H / 2 + 4} textAnchor="middle" fontSize={10} fontFamily="var(--font-mono)" fill="#fff" fontWeight="bold">
            {truncate(lineage.focusNode?.label ?? focusId)}
          </text>
        </g>

        {[...layoutNodes.values()].filter(node => node.id !== focusId).map(node => (
          <LineageObjectNode
            key={node.id}
            node={node}
            lineageNode={lineage.nodeMap.get(node.id)}
            navigate={navigate}
          />
        ))}
      </svg>

      <div style={{ marginTop: 10, textAlign: 'right' }}>
        <FullLineageLink focusId={focusId} />
      </div>
    </div>
  );
}

function LineageObjectNode({
  node,
  lineageNode,
  navigate,
}: {
  node: LayoutNode;
  lineageNode?: LineageNode;
  navigate: ReturnType<typeof useNavigate>;
}) {
  return (
    <g
      transform={`translate(${node.x},${node.y})`}
      style={{ cursor: 'pointer' }}
      onClick={() => navigate(`/objects/${node.id}`)}
    >
      <rect width={BOX_W} height={BOX_H} rx={4} fill="var(--bg-2)" stroke="var(--line)" strokeWidth={1} />
      <text x={BOX_W / 2} y={BOX_H / 2 + 4} textAnchor="middle" fontSize={10} fontFamily="var(--font-mono)" fill="var(--fg-2)">
        {truncate(lineageNode?.label ?? node.id)}
      </text>
    </g>
  );
}
