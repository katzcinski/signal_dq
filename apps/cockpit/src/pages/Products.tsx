import { useDeferredValue, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProducts } from '@/api/products';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { LifecycleTag } from '@/components/ui/LifecycleTag';
import { OwnershipTag } from '@/components/ui/OwnershipTag';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusPill } from '@/components/ui/StatusPill';
import { Table, type ColDef } from '@/components/ui/Table';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { t } from '@/i18n/de';
import type { ProductListItem } from '@/types';

function OwnerList({ owners }: { owners: string[] }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <OwnershipTag ownedBy="product" />
      {owners.map(owner => (
        <span key={owner} style={{ color: 'var(--fg-2)', fontSize: 12 }}>{owner}</span>
      ))}
    </div>
  );
}

export default function Products() {
  const { data: products = [], isLoading, isError, refetch } = useProducts();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParamState('q');
  const deferredSearch = useDeferredValue(search);

  const q = deferredSearch.trim().toLowerCase();
  const rows = useMemo(() => (
    q
      ? products.filter(p =>
          p.product.toLowerCase().includes(q) ||
          p.owners.some(owner => owner.toLowerCase().includes(q)),
        )
      : products
  ), [products, q]);

  const searchInput = (
    <input
      type="search"
      name="product-search"
      autoComplete="off"
      spellCheck={false}
      value={search}
      onChange={e => setSearch(e.target.value)}
      placeholder={t.products.search}
      aria-label={t.products.search}
      style={{
        background: 'var(--bg-2)', border: '1px solid var(--line-2)',
        color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12, minWidth: 220,
      }}
    />
  );

  const columns: ColDef<ProductListItem>[] = [
    {
      key: 'product',
      header: t.products.colProduct,
      mono: true,
      sortable: true,
      sortValue: row => row.product,
      render: row => row.product,
    },
    {
      key: 'owners',
      header: t.products.colOwners,
      sortable: true,
      sortValue: row => row.owners.join(','),
      render: row => <OwnerList owners={row.owners} />,
    },
    {
      key: 'health',
      header: t.products.colHealth,
      sortable: true,
      sortValue: row => row.own_health,
      render: row => <StatusPill status={row.own_health} size="sm" />,
    },
    {
      key: 'ports',
      header: t.products.colPorts,
      sortable: true,
      sortValue: row => row.port_count,
      render: row => <span style={{ color: 'var(--fg-2)', fontSize: 12 }}>{row.port_count}</span>,
    },
    {
      key: 'findings',
      header: t.products.colFindings,
      sortable: true,
      sortValue: row => row.finding_count,
      render: row => (
        <span style={{ color: row.finding_count > 0 ? 'var(--status-warn)' : 'var(--fg-3)', fontSize: 12 }}>
          {row.finding_count}
        </span>
      ),
    },
    {
      key: 'risk',
      header: t.products.colUpstreamRisk,
      sortable: true,
      sortValue: row => row.upstream_risk_count,
      render: row => (
        <span style={{ color: row.upstream_risk_count > 0 ? 'var(--status-warn)' : 'var(--fg-3)', fontSize: 12 }}>
          {row.upstream_risk_count}
        </span>
      ),
    },
    {
      key: 'lifecycle',
      header: t.products.colLifecycle,
      sortable: true,
      sortValue: row => row.lifecycle,
      render: row => <LifecycleTag lifecycle={row.lifecycle} />,
    },
  ];

  if (isLoading) {
    return (
      <div className="page-full">
        <PageHeader title={t.products.title} />
        <TableSkeleton columns={7} />
      </div>
    );
  }

  return (
    <div className="page-full">
      <PageHeader title={t.products.title} actions={searchInput} />
      {isError ? (
        <ErrorBanner onRetry={() => refetch()} />
      ) : (
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table
            columns={columns}
            rows={rows}
            rowKey={row => row.product}
            onRowClick={row => navigate(`/products/${encodeURIComponent(row.product)}`)}
            empty={t.products.empty}
          />
        </div>
      )}
    </div>
  );
}
