import { describe, expect, it } from 'vitest';
import {
  OBJECT_DETAIL_GROUPS,
  OBJECT_DETAIL_LEGACY_TABS,
  OBJECT_DETAIL_TAB_TARGETS,
  resolveObjectDetailTabTarget,
  type ObjectDetailTab,
  type ObjectDetailTabTarget,
} from '@/pages/objectDetailTabs';

const expectedTargets: Record<ObjectDetailTab, ObjectDetailTabTarget> = {
  checks: { legacyTab: 'checks', group: 'quality', anchor: 'checks' },
  runs: { legacyTab: 'runs', group: 'history-ops', anchor: 'runs' },
  timeseries: { legacyTab: 'timeseries', group: 'history-ops', anchor: 'timeseries' },
  schedule: { legacyTab: 'schedule', group: 'history-ops', anchor: 'schedule' },
  diff: { legacyTab: 'diff', group: 'history-ops', anchor: 'diff' },
  contract: { legacyTab: 'contract', group: 'structure-interface', anchor: 'contract' },
  lineage: { legacyTab: 'lineage', group: 'structure-interface', anchor: 'lineage' },
};

function targetFromUrl(url: string) {
  return resolveObjectDetailTabTarget(new URL(url, 'https://signal.local').searchParams.get('tab'));
}

describe('ObjectDetail tab compatibility', () => {
  it('keeps every legacy ?tab= key accepted with its grouped target', () => {
    for (const tab of OBJECT_DETAIL_LEGACY_TABS) {
      expect(targetFromUrl(`/objects/Sales_Orders_View?tab=${tab}`)).toEqual(expectedTargets[tab]);
    }
  });

  it('exports the same mapping as the resolver uses', () => {
    expect(OBJECT_DETAIL_TAB_TARGETS).toEqual(expectedTargets);
  });

  it('defines grouped navigation defaults without changing legacy anchors', () => {
    expect(OBJECT_DETAIL_GROUPS).toEqual([
      { id: 'quality', defaultTab: 'checks', tabs: ['checks'] },
      { id: 'structure-interface', defaultTab: 'contract', tabs: ['contract', 'lineage'] },
      { id: 'history-ops', defaultTab: 'runs', tabs: ['runs', 'timeseries', 'schedule', 'diff'] },
    ]);
  });

  it('uses checks as the fallback for missing or unknown tab keys', () => {
    expect(targetFromUrl('/objects/Sales_Orders_View')).toBe(OBJECT_DETAIL_TAB_TARGETS.checks);
    expect(targetFromUrl('/objects/Sales_Orders_View?tab=unknown')).toBe(OBJECT_DETAIL_TAB_TARGETS.checks);
  });
});
