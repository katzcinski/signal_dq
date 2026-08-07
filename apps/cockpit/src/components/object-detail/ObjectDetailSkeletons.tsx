import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { t } from '@/i18n/de';
import type { ObjectDetailTab } from '@/pages/objectDetailTabs';

export function ObjectSummaryCardSkeleton() {
  return (
    <div className="object-summary-card" data-testid="object-summary-card-skeleton">
      <Skeleton width={86} height={10} />
      <div style={{ marginTop: 12 }}>
        <Skeleton width={112} height={22} />
      </div>
      <div style={{ marginTop: 10 }}>
        <Skeleton width="72%" height={10} />
      </div>
    </div>
  );
}

export function ObjectHeroSkeleton() {
  return (
    <section
      className="object-detail-hero object-detail-section"
      aria-label={t.objectDetail.loading.hero}
      data-testid="object-hero-skeleton"
    >
      <div className="object-detail-hero-head">
        <div style={{ minWidth: 0 }}>
          <Skeleton width={88} height={28} radius={6} style={{ marginBottom: 12 }} />
          <div className="object-detail-title-row">
            <Skeleton width="min(420px, 82vw)" height={30} />
            <Skeleton width={76} height={22} radius={999} />
            <Skeleton width={58} height={22} radius={999} />
          </div>
          <div className="object-detail-meta" style={{ marginTop: 10 }}>
            <Skeleton width={96} height={11} />
            <Skeleton width={56} height={11} />
            <Skeleton width={72} height={11} />
            <Skeleton width={90} height={11} />
          </div>
          <div className="object-detail-facts" style={{ marginTop: 16 }}>
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index}>
                <Skeleton width={62} height={10} />
                <div style={{ marginTop: 8 }}>
                  <Skeleton width={index === 0 ? 130 : 76} height={14} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="object-detail-actions">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} width={index === 3 ? 96 : 118} height={32} radius={6} />
          ))}
        </div>
      </div>

      <div className="object-detail-summary-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <ObjectSummaryCardSkeleton key={index} />
        ))}
      </div>
    </section>
  );
}

export function MiniLineageSkeleton() {
  return (
    <div
      className="object-detail-local-skeleton"
      aria-label={t.objectDetail.loading.lineage}
      data-testid="mini-lineage-skeleton"
    >
      <Skeleton width={132} height={12} />
      <div className="object-detail-lineage-skeleton">
        <Skeleton width={144} height={34} radius={6} />
        <Skeleton width={90} height={2} />
        <Skeleton width={144} height={34} radius={6} />
        <Skeleton width={90} height={2} />
        <Skeleton width={144} height={34} radius={6} />
      </div>
      <Skeleton width={118} height={12} style={{ justifySelf: 'end' }} />
    </div>
  );
}

export function TimeseriesSkeleton() {
  return (
    <div
      className="object-detail-local-skeleton"
      aria-label={t.objectDetail.loading.timeseries}
      data-testid="timeseries-skeleton"
    >
      <div className="object-detail-inline-skeleton-row">
        <Skeleton width={62} height={12} />
        <Skeleton width={166} height={28} radius={6} />
      </div>
      <Skeleton width="100%" height={180} radius={8} />
      <Skeleton width="100%" height={180} radius={8} />
    </div>
  );
}

export function ScheduleSkeleton() {
  return (
    <div
      className="object-detail-local-skeleton object-detail-schedule-skeleton"
      aria-label={t.objectDetail.loading.schedule}
      data-testid="schedule-skeleton"
    >
      <Skeleton width="62%" height={42} radius={8} />
      <div className="object-detail-schedule-mode-skeleton">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} width="100%" height={74} radius={8} />
        ))}
      </div>
      <Skeleton width={132} height={32} radius={6} />
    </div>
  );
}

export function ColumnLineageSkeleton() {
  return (
    <div
      className="object-detail-local-skeleton"
      aria-label={t.objectDetail.loading.columnLineage}
      data-testid="column-lineage-skeleton"
    >
      <Skeleton width={140} height={18} />
      <Skeleton width={280} height={34} radius={6} />
      <div className="object-detail-column-lineage-skeleton">
        <Skeleton width="100%" height={72} radius={8} />
        <Skeleton width="100%" height={72} radius={8} />
        <Skeleton width="100%" height={72} radius={8} />
      </div>
      <TableSkeleton columns={5} rows={3} />
    </div>
  );
}

export function ObjectDetailSectionSkeleton({ tab }: { tab: ObjectDetailTab }) {
  if (tab === 'checks') {
    return <TableSkeleton columns={6} rows={6} />;
  }
  if (tab === 'runs') {
    return <TableSkeleton columns={5} rows={6} />;
  }
  if (tab === 'timeseries') {
    return <TimeseriesSkeleton />;
  }
  if (tab === 'lineage') {
    return (
      <div className="object-detail-section-stack" data-testid="object-detail-section-skeleton">
        <MiniLineageSkeleton />
        <ColumnLineageSkeleton />
      </div>
    );
  }
  if (tab === 'schedule') {
    return <ScheduleSkeleton />;
  }

  return (
    <div
      className="object-detail-local-skeleton"
      aria-label={t.objectDetail.loading.section}
      data-testid="object-detail-section-skeleton"
    >
      <Skeleton width="42%" height={18} />
      <Skeleton width="100%" height={120} radius={8} />
      <Skeleton width="86%" height={14} />
    </div>
  );
}
