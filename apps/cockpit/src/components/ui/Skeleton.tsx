// R6-3: skeleton loaders that mirror the real layout, so loading reads as
// "content arriving here" rather than a bare spinner.

export function Skeleton({ width = '100%', height = 14, radius = 4, style }: {
  width?: number | string; height?: number | string; radius?: number; style?: React.CSSProperties;
}) {
  return <div className="skeleton" style={{ width, height, borderRadius: radius, ...style }} />;
}

export function KpiSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${count}, 1fr)`, gap: 'var(--s4)', marginBottom: 24 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s4) var(--s5)', borderLeft: '3px solid var(--line-2)' }}>
          <Skeleton width={80} height={10} />
          <div style={{ marginTop: 12 }}><Skeleton width={60} height={26} /></div>
        </div>
      ))}
    </div>
  );
}

// Mirrors the generic Table: a header row plus N body rows across `columns` cells.
export function TableSkeleton({ columns = 5, rows = 8 }: { columns?: number; rows?: number }) {
  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: 'var(--s4)', padding: 'var(--row-pad-y) var(--row-pad-x)', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
        {Array.from({ length: columns }).map((_, i) => <Skeleton key={i} width={i === 0 ? 140 : 70} height={9} />)}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} style={{ display: 'flex', gap: 'var(--s4)', padding: 'var(--row-pad-y) var(--row-pad-x)', borderBottom: '1px solid var(--line)' }}>
          {Array.from({ length: columns }).map((_, c) => <Skeleton key={c} width={c === 0 ? 160 : 60} height={12} />)}
        </div>
      ))}
    </div>
  );
}
