// Pure clustering helpers for the Vorschläge page. No i18n/React here so the
// grouping logic stays unit-testable; the component applies the German labels.
import type { Proposal } from '@/types';
import { diffExpect } from './diff';

// Dimensions a steward can cluster proposals by. 'none' keeps the flat layout.
export type ClusterDimension = 'product' | 'kind' | 'confidence' | 'status' | 'direction' | 'none';

export interface ProposalCluster {
  key: string;             // stable, i18n-free group key (e.g. product name or 'high')
  proposals: Proposal[];   // group members, open first then by confidence desc
  count: number;
  openCount: number;
  avgConfidence: number;   // mean confidence across the group (0..1)
}

const CONFIDENCE_HIGH = 0.8;
const CONFIDENCE_MEDIUM = 0.5;

// Fixed display order for closed-domain dimensions; most actionable first.
const KIND_ORDER = ['internal_gate', 'contract'];
const CONFIDENCE_ORDER = ['high', 'medium', 'low'];
const STATUS_ORDER = ['open', 'snoozed', 'accepted', 'rejected'];
const DIRECTION_ORDER = ['tightened', 'loosened', 'changed'];

function confidenceBucket(value: number): string {
  if (value >= CONFIDENCE_HIGH) return 'high';
  if (value >= CONFIDENCE_MEDIUM) return 'medium';
  return 'low';
}

// Mirror the card's binary Gate/Contract semantics (consumer/provider → contract).
function kindBucket(kind: string): string {
  return kind === 'internal_gate' ? 'internal_gate' : 'contract';
}

function clusterKey(p: Proposal, dim: ClusterDimension): string {
  switch (dim) {
    case 'product': return p.product;
    case 'kind': return kindBucket(p.kind);
    case 'confidence': return confidenceBucket(p.confidence);
    case 'status': return p.status;
    case 'direction': return diffExpect(p.current_expect, p.proposed_expect).direction;
    case 'none': return '';
  }
}

// Open proposals bubble to the top of each cluster, then highest confidence first.
function byActionability(a: Proposal, b: Proposal): number {
  const aOpen = a.status === 'open' ? 0 : 1;
  const bOpen = b.status === 'open' ? 0 : 1;
  if (aOpen !== bOpen) return aOpen - bOpen;
  return b.confidence - a.confidence;
}

function clusterOrder(dim: ClusterDimension, a: ProposalCluster, b: ProposalCluster): number {
  const fixed: Record<string, string[]> = {
    kind: KIND_ORDER,
    confidence: CONFIDENCE_ORDER,
    status: STATUS_ORDER,
    direction: DIRECTION_ORDER,
  };
  const order = fixed[dim];
  if (order) {
    const ai = order.indexOf(a.key);
    const bi = order.indexOf(b.key);
    return (ai === -1 ? order.length : ai) - (bi === -1 ? order.length : bi);
  }
  // Free-domain dimensions (product): groups with open work first, then size,
  // then alphabetically for a stable, predictable layout.
  if (a.openCount !== b.openCount) return b.openCount - a.openCount;
  if (a.count !== b.count) return b.count - a.count;
  return a.key.localeCompare(b.key);
}

/**
 * Group proposals into ordered clusters along the chosen dimension. Returns a
 * single empty-key cluster when `dim === 'none'` so callers can treat the flat
 * case uniformly. Each cluster's members are pre-sorted by actionability.
 */
export function clusterProposals(proposals: Proposal[], dim: ClusterDimension): ProposalCluster[] {
  const buckets = new Map<string, Proposal[]>();
  for (const p of proposals) {
    const key = clusterKey(p, dim);
    const arr = buckets.get(key);
    if (arr) arr.push(p);
    else buckets.set(key, [p]);
  }

  const clusters: ProposalCluster[] = [];
  for (const [key, members] of buckets) {
    const sorted = [...members].sort(byActionability);
    const openCount = sorted.filter(p => p.status === 'open').length;
    const avgConfidence = sorted.reduce((s, p) => s + p.confidence, 0) / sorted.length;
    clusters.push({ key, proposals: sorted, count: sorted.length, openCount, avgConfidence });
  }

  clusters.sort((a, b) => clusterOrder(dim, a, b));
  return clusters;
}
