export type ObjectDetailTab =
  | 'checks'
  | 'runs'
  | 'timeseries'
  | 'contract'
  | 'lineage'
  | 'schedule'
  | 'diff';

export type ObjectDetailGroup = 'quality' | 'history-ops' | 'structure-interface';

export type ObjectDetailTabTarget = {
  legacyTab: ObjectDetailTab;
  group: ObjectDetailGroup;
  anchor: ObjectDetailTab;
};

export type ObjectDetailGroupConfig = {
  id: ObjectDetailGroup;
  defaultTab: ObjectDetailTab;
  tabs: ObjectDetailTab[];
};

export const OBJECT_DETAIL_LEGACY_TABS: ObjectDetailTab[] = [
  'checks',
  'runs',
  'timeseries',
  'contract',
  'lineage',
  'schedule',
  'diff',
];

export const OBJECT_DETAIL_TAB_TARGETS: Record<ObjectDetailTab, ObjectDetailTabTarget> = {
  checks: { legacyTab: 'checks', group: 'quality', anchor: 'checks' },
  runs: { legacyTab: 'runs', group: 'history-ops', anchor: 'runs' },
  timeseries: { legacyTab: 'timeseries', group: 'history-ops', anchor: 'timeseries' },
  contract: { legacyTab: 'contract', group: 'structure-interface', anchor: 'contract' },
  lineage: { legacyTab: 'lineage', group: 'structure-interface', anchor: 'lineage' },
  schedule: { legacyTab: 'schedule', group: 'history-ops', anchor: 'schedule' },
  diff: { legacyTab: 'diff', group: 'history-ops', anchor: 'diff' },
};

export const OBJECT_DETAIL_GROUPS: ObjectDetailGroupConfig[] = [
  { id: 'quality', defaultTab: 'checks', tabs: ['checks'] },
  { id: 'structure-interface', defaultTab: 'contract', tabs: ['contract', 'lineage'] },
  { id: 'history-ops', defaultTab: 'runs', tabs: ['runs', 'timeseries', 'schedule', 'diff'] },
];

export function resolveObjectDetailTabTarget(tabKey: string | null | undefined): ObjectDetailTabTarget {
  if (tabKey && tabKey in OBJECT_DETAIL_TAB_TARGETS) {
    return OBJECT_DETAIL_TAB_TARGETS[tabKey as ObjectDetailTab];
  }
  return OBJECT_DETAIL_TAB_TARGETS.checks;
}

export function parseObjectDetailTab(tabKey: string | null | undefined): ObjectDetailTab {
  return resolveObjectDetailTabTarget(tabKey).legacyTab;
}
