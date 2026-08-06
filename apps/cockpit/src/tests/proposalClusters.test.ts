import { describe, it, expect } from 'vitest';
import { clusterProposals, type ClusterDimension } from '@/lib/proposalClusters';
import type { Proposal } from '@/types';

function mk(over: Partial<Proposal>): Proposal {
  return {
    id: Math.random().toString(36).slice(2),
    product: 'SALES.ORDERS',
    check_name: 'row_count',
    current_expect: '<= 10',
    proposed_expect: '<= 8',
    rationale: '',
    confidence: 0.9,
    status: 'open',
    kind: 'internal_gate',
    ...over,
  };
}

describe('clusterProposals', () => {
  it('groups by object (product) and orders groups with open work first', () => {
    const ps = [
      mk({ product: 'A', status: 'accepted' }),
      mk({ product: 'B', status: 'open' }),
      mk({ product: 'B', status: 'open' }),
    ];
    const clusters = clusterProposals(ps, 'product');
    expect(clusters.map(c => c.key)).toEqual(['B', 'A']); // B has open work → first
    expect(clusters[0].count).toBe(2);
    expect(clusters[0].openCount).toBe(2);
  });

  it('sorts members open-first then by confidence desc', () => {
    const ps = [
      mk({ id: 'lo', status: 'open', confidence: 0.5 }),
      mk({ id: 'done', status: 'accepted', confidence: 0.99 }),
      mk({ id: 'hi', status: 'open', confidence: 0.95 }),
    ];
    const [cluster] = clusterProposals(ps, 'product');
    expect(cluster.proposals.map(p => p.id)).toEqual(['hi', 'lo', 'done']);
  });

  it('buckets confidence into high/medium/low in fixed order', () => {
    const ps = [
      mk({ confidence: 0.3 }),
      mk({ confidence: 0.85 }),
      mk({ confidence: 0.6 }),
    ];
    const clusters = clusterProposals(ps, 'confidence');
    expect(clusters.map(c => c.key)).toEqual(['high', 'medium', 'low']);
  });

  it('collapses contract kinds into a binary Gate/Contract bucket', () => {
    const ps = [
      mk({ kind: 'consumer_contract' }),
      mk({ kind: 'provider_contract' }),
      mk({ kind: 'internal_gate' }),
    ];
    const clusters = clusterProposals(ps, 'kind');
    expect(clusters.map(c => c.key)).toEqual(['internal_gate', 'contract']);
    expect(clusters.find(c => c.key === 'contract')!.count).toBe(2);
  });

  it('groups by diff direction', () => {
    const ps = [
      mk({ current_expect: '<= 5', proposed_expect: '<= 8' }), // loosened
      mk({ current_expect: '<= 8', proposed_expect: '<= 4' }), // tightened
    ];
    const clusters = clusterProposals(ps, 'direction');
    expect(clusters.map(c => c.key)).toEqual(['tightened', 'loosened']); // tightened first
  });

  it('computes average confidence per cluster', () => {
    const ps = [mk({ confidence: 0.8 }), mk({ confidence: 0.6 })];
    const [cluster] = clusterProposals(ps, 'product');
    expect(cluster.avgConfidence).toBeCloseTo(0.7);
  });

  it('returns a single empty-key cluster for "none"', () => {
    const ps = [mk({ product: 'A' }), mk({ product: 'B' })];
    const clusters = clusterProposals(ps, 'none' as ClusterDimension);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].key).toBe('');
    expect(clusters[0].count).toBe(2);
  });
});
