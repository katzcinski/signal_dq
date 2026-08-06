import { t } from '@/i18n/de';
import {
  OBJECT_DETAIL_GROUPS,
  type ObjectDetailGroup,
  type ObjectDetailTab,
} from '@/pages/objectDetailTabs';

interface ObjectDetailNavigationProps {
  activeGroup: ObjectDetailGroup;
  activeTab: ObjectDetailTab;
  onSelectTab: (tab: ObjectDetailTab) => void;
}

export function ObjectDetailNavigation({
  activeGroup,
  activeTab,
  onSelectTab,
}: ObjectDetailNavigationProps) {
  const activeGroupConfig = OBJECT_DETAIL_GROUPS.find(group => group.id === activeGroup) ?? OBJECT_DETAIL_GROUPS[0];

  return (
    <nav
      aria-label={t.objectDetail.navigationLabel}
      data-active-group={activeGroup}
      data-active-anchor={activeTab}
      style={{
        display: 'grid',
        gap: 'var(--s2)',
        borderBottom: '1px solid var(--line)',
        marginBottom: 20,
        paddingBottom: 'var(--s2)',
      }}
    >
      <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap' }}>
        {OBJECT_DETAIL_GROUPS.map(group => {
          const active = activeGroup === group.id;
          return (
            <button
              key={group.id}
              type="button"
              aria-pressed={active}
              onClick={() => onSelectTab(group.defaultTab)}
              style={{
                border: `1px solid ${active ? 'var(--cont)' : 'var(--line)'}`,
                borderRadius: 'var(--r-md)',
                background: active ? 'color-mix(in srgb, var(--cont) 12%, var(--bg-1))' : 'var(--bg-1)',
                color: active ? 'var(--fg)' : 'var(--fg-3)',
                cursor: 'pointer',
                fontSize: 'var(--fs-meta)',
                fontWeight: active ? 700 : 500,
                lineHeight: 'var(--lh-meta)',
                padding: 'var(--s2) var(--s4)',
              }}
            >
              {t.objectDetail.groups[group.id]}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', gap: 'var(--s1)', flexWrap: 'wrap' }}>
        {activeGroupConfig.tabs.map(tab => {
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              type="button"
              aria-pressed={active}
              onClick={() => onSelectTab(tab)}
              style={{
                border: 'none',
                borderBottom: `2px solid ${active ? 'var(--cont)' : 'transparent'}`,
                background: 'none',
                color: active ? 'var(--fg)' : 'var(--fg-3)',
                cursor: 'pointer',
                fontSize: 13,
                padding: 'var(--s2) var(--s3)',
              }}
            >
              {t.objectDetail.tabs[tab] ?? tab}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
