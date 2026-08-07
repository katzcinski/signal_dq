import { lazy, Suspense, type CSSProperties } from 'react';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { t } from '@/i18n/de';

const SchematicLineage = lazy(() => import('@/components/lineage/schematic/SchematicLineage'));
const LegacyLineageMap = lazy(() => import('./LegacyLineageMap'));

type Renderer = 'schematic' | 'legacy';

export default function LineagePage() {
  const [renderer, setRenderer] = useSearchParamState('renderer', 'schematic');
  const current: Renderer = renderer === 'legacy' ? 'legacy' : 'schematic';

  return (
    <div style={page}>
      <div style={toolbar}>
        <div role="group" aria-label={t.lineage.rendererLabel} style={toggle}>
          <button
            type="button"
            style={toggleButton(current === 'schematic', false)}
            onClick={() => setRenderer('schematic')}
          >
            {t.lineage.rendererSchematic}
          </button>
          <button
            type="button"
            style={toggleButton(current === 'legacy', true)}
            onClick={() => setRenderer('legacy')}
          >
            {t.lineage.rendererLegacy}
          </button>
        </div>
      </div>

      <div style={content}>
        <Suspense fallback={<div style={fallback}>{t.common.loading}</div>}>
          {current === 'legacy' ? <LegacyLineageMap /> : <SchematicLineage />}
        </Suspense>
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
  justifyContent: 'flex-end',
  flexShrink: 0,
  marginBottom: 'var(--s3)',
};

const toggle: CSSProperties = {
  display: 'inline-flex',
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-md)',
  overflow: 'hidden',
  background: 'var(--bg-1)',
};

const toggleButton = (active: boolean, last: boolean): CSSProperties => ({
  border: 'none',
  borderRight: last ? 'none' : '1px solid var(--line)',
  background: active ? 'var(--cont)' : 'transparent',
  color: active ? '#fff' : 'var(--fg-2)',
  fontSize: 12,
  fontWeight: 600,
  minWidth: 92,
  padding: '7px 12px',
});

const content: CSSProperties = {
  flex: 1,
  minHeight: 0,
};

const fallback: CSSProperties = {
  color: 'var(--fg-3)',
  padding: 40,
  textAlign: 'center',
};
