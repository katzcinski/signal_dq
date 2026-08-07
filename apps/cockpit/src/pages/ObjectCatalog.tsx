import { useDeferredValue, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useObjects } from '@/api/objects';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { useObjectInspection } from '@/hooks/useObjectInspection';
import { Table, type ColDef } from '@/components/ui/Table';
import { StatusPill } from '@/components/ui/StatusPill';
import { CovFlag } from '@/components/ui/CovFlag';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { FilterChip, ActiveFilterChip } from '@/components/ui/FilterChip';
import { SavedViewsBar } from '@/components/SavedViewsBar';
import { t } from '@/i18n/de';
import type { ObjectSummary } from '@/types';

const FAMILIES = ['observability', 'quality', 'contract'] as const;
const STATUSES = ['pass', 'warn', 'fail', 'critical', 'unknown'] as const;

export default function ObjectCatalog() {
  const { data: objects = [], isLoading, isError, refetch } = useObjects();
  const [spaceFilter, setSpaceFilter] = useSearchParamState('space');
  const [textFilter, setTextFilter] = useSearchParamState('q');
  const [familyFilter, setFamilyFilter] = useSearchParamState('family');
  const [statusFilter, setStatusFilter] = useSearchParamState('dqstatus');
  // Absicht aus dem „+ Zeitplan"-Button (Schedules): den Nutzer nicht kommentarlos
  // auf dem Katalog absetzen, sondern erklären, dass ein Zeitplan pro Objekt im
  // Reiter „Zeitplan" scharfgeschaltet wird.
  const [intent, setIntent] = useSearchParamState('intent');
  const { openChecks, openPeek, overlays } = useObjectInspection();
  const navigate = useNavigate();
  const deferredTextFilter = useDeferredValue(textFilter);

  const spaces = useMemo(() => [...new Set(objects.map(o => o.space))].sort(), [objects]);
  const q = deferredTextFilter.trim().toLowerCase();
  const rows = useMemo(() => objects.filter(o => {
    if (spaceFilter && o.space !== spaceFilter) return false;
    if (familyFilter && o.family !== familyFilter) return false;
    if (statusFilter && o.status !== statusFilter) return false;
    if (q && !o.name.toLowerCase().includes(q) && !o.space.toLowerCase().includes(q) && !(o.owned_by ?? '').toLowerCase().includes(q)) return false;
    return true;
  }), [objects, spaceFilter, familyFilter, statusFilter, q]);

  const columns = useMemo<ColDef<ObjectSummary>[]>(() => [
    {
      key: 'name', header: t.objects.colName, mono: true, sortable: true, sortValue: o => o.name,
      render: o => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
          <span style={{
            width: 3, height: 16, borderRadius: 2, flexShrink: 0,
            background: o.family === 'observability' ? 'var(--obs)'
              : o.family === 'quality' ? 'var(--qual)' : 'var(--cont)',
          }} />
          {/* R6-1: the name navigates to the full page; the rest of the row peeks. */}
          <button
            onClick={e => { e.stopPropagation(); navigate(`/objects/${o.id}`); }}
            style={{ background: 'none', border: 'none', padding: 0, color: 'var(--fg)', cursor: 'pointer', font: 'inherit' }}
          >
            {o.name}
          </button>
        </div>
      ),
    },
    { key: 'family', header: t.objects.colFamily, sortable: true, sortValue: o => o.family, render: o => <span style={{ color: 'var(--fg-2)', fontSize: 12 }}>{o.family}</span> },
    { key: 'layer', header: t.objects.colLayer, sortable: true, sortValue: o => o.layer, render: o => <span style={{ color: 'var(--fg-2)', fontSize: 12 }}>{o.layer}</span> },
    { key: 'space', header: t.objects.colSpace, mono: true, sortable: true, sortValue: o => o.space, render: o => o.space },
    {
      key: 'status', header: t.objects.colStatus,
      render: o => <StatusPill status={o.status ?? 'unknown'} size="sm" />,
    },
    {
      key: 'coverage', header: t.objects.colCov,
      render: o => <CovFlag flag={o.cov_flag ?? 'gap'} />,
    },
    {
      key: 'checks', header: t.objects.colChecks, sortable: true, sortValue: o => o.check_count ?? 0,
      render: o => (
        <button
          type="button"
          aria-label={t.peek.openChecksFor.replace('{name}', o.name)}
          onClick={event => openChecks(o.id, event)}
          onKeyDown={event => event.stopPropagation()}
          style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--line-2)',
            borderRadius: 'var(--r-md)',
            color: 'var(--fg-2)',
            cursor: 'pointer',
            fontSize: 12,
            minWidth: 32,
            padding: '2px 8px',
          }}
        >
          {o.check_count ?? '-'}
        </button>
      ),
    },
    { key: 'owned_by', header: t.objects.colOwner, sortable: true, sortValue: o => o.owned_by, render: o => <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{o.owned_by}</span> },
    {
      key: 'last_run', header: t.objects.colLastRun, mono: true, sortable: true, sortValue: o => o.last_run ?? '',
      render: o => <span style={{ fontSize: 11 }}>{o.last_run ? new Date(o.last_run).toLocaleString() : '—'}</span>,
    },
  ], [navigate, openChecks]);

  const searchInput = (
    <input
      type="search"
      name="object-search"
      autoComplete="off"
      spellCheck={false}
      value={textFilter}
      onChange={e => setTextFilter(e.target.value)}
      placeholder={t.objects.searchPlaceholder}
      style={{
        background: 'var(--bg-2)', border: '1px solid var(--line-2)',
        color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12, minWidth: 220,
      }}
    />
  );

  if (isLoading) return (
    <div className="page-full">
      <PageHeader title={t.objects.title} />
      <TableSkeleton columns={9} />
    </div>
  );

  const hasActiveFilter = !!(textFilter || familyFilter || statusFilter || spaceFilter);

  return (
    <div className="page-full">
      <PageHeader title={t.objects.title} actions={searchInput} />
      {intent === 'schedule' && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--s3)',
          background: 'color-mix(in srgb, var(--cont) 10%, var(--bg-2))',
          border: '1px solid color-mix(in srgb, var(--cont) 40%, var(--line))',
          borderRadius: 'var(--r-lg)', padding: '10px 14px', marginBottom: 12,
        }}>
          <span style={{ color: 'var(--fg-2)', fontSize: 12.5, lineHeight: 1.5 }}>{t.schedules.catalogHint}</span>
          <button
            onClick={() => setIntent('')}
            aria-label={t.common.close}
            style={{ background: 'none', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0, flexShrink: 0 }}
          >
            ✕
          </button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <FilterChip active={familyFilter === ''} onClick={() => setFamilyFilter('')}>{t.objects.allFamilies}</FilterChip>
        {FAMILIES.map(f => (
          <FilterChip key={f} active={familyFilter === f} onClick={() => setFamilyFilter(familyFilter === f ? '' : f)}>
            {t.workbench.families[f] ?? f}
          </FilterChip>
        ))}
        <div style={{ width: 1, height: 16, background: 'var(--line-2)', margin: '0 4px' }} />
        <FilterChip active={statusFilter === ''} onClick={() => setStatusFilter('')}>{t.common.all}</FilterChip>
        {STATUSES.map(s => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(statusFilter === s ? '' : s)}>
            {t.status[s] ?? s}
          </FilterChip>
        ))}
        <div style={{ marginLeft: 'auto' }}>
          <select
            value={spaceFilter}
            onChange={e => setSpaceFilter(e.target.value)}
            aria-label={t.objects.colSpace}
            style={{
              background: 'var(--bg-2)', border: '1px solid var(--line-2)',
              color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12,
            }}
          >
            <option value="">{t.objects.allSpaces}</option>
            {spaces.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <SavedViewsBar
        current={{ q: textFilter, family: familyFilter, dqstatus: statusFilter, space: spaceFilter }}
        hasActiveFilter={hasActiveFilter}
        onApply={params => {
          setTextFilter(params.q ?? '');
          setFamilyFilter(params.family ?? '');
          setStatusFilter(params.dqstatus ?? '');
          setSpaceFilter(params.space ?? '');
        }}
      />
      {hasActiveFilter && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10, alignItems: 'center' }}>
          {textFilter && <ActiveFilterChip label={`"${textFilter}"`} onClear={() => setTextFilter('')} />}
          {familyFilter && <ActiveFilterChip label={t.workbench.families[familyFilter] ?? familyFilter} onClear={() => setFamilyFilter('')} />}
          {statusFilter && <ActiveFilterChip label={t.status[statusFilter] ?? statusFilter} onClear={() => setStatusFilter('')} />}
          {spaceFilter && <ActiveFilterChip label={spaceFilter} onClear={() => setSpaceFilter('')} />}
        </div>
      )}
      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {!isError && (
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table
            columns={columns}
            rows={rows}
            rowKey={o => o.id}
            onRowClick={o => openPeek(o.id)}
            empty={t.objects.empty}
          />
        </div>
      )}
      {overlays}
    </div>
  );
}
