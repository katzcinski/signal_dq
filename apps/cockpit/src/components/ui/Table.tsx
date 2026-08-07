import { useMemo, useRef, useState, type CSSProperties, type ReactNode, type KeyboardEvent } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

export interface ColDef<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  mono?: boolean;
  width?: string | number;
  // R6-6: sortable columns provide a comparable value (render returns a node).
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
}

interface Props<T> {
  columns: ColDef<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  // Above this many rows the body is virtualized (windowed) for performance.
  virtualizeThreshold?: number;
  maxHeight?: number;
  // Optional per-row style (e.g. severity tint); merged into the <tr> style.
  rowStyle?: (row: T) => CSSProperties | undefined;
}

type SortState = { key: string; dir: 'asc' | 'desc' } | null;

const ROW_HEIGHT = 34;

export function Table<T>({
  columns, rows, rowKey, onRowClick, empty = 'Keine Daten',
  virtualizeThreshold = 80, maxHeight = 560, rowStyle,
}: Props<T>) {
  const [sort, setSort] = useState<SortState>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find(c => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const accessor = col.sortValue;
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = accessor(a), vb = accessor(b);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }, [rows, sort, columns]);

  const toggleSort = (key: string) =>
    setSort(prev => prev?.key === key
      ? (prev.dir === 'asc' ? { key, dir: 'desc' } : null)
      : { key, dir: 'asc' });

  const handleKeyDown = (e: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (onRowClick && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onRowClick(row);
    }
  };

  const virtualize = sortedRows.length > virtualizeThreshold;

  const head = (
    <thead>
      <tr style={{ background: 'var(--bg-2)', position: 'sticky', top: 0, zIndex: 1 }}>
        {columns.map(c => {
          const active = sort?.key === c.key;
          return (
            <th
              key={c.key}
              onClick={c.sortable ? () => toggleSort(c.key) : undefined}
              aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
              style={{
                padding: 'var(--row-pad-y) var(--row-pad-x)', textAlign: 'left',
                fontSize: 10, fontWeight: 600, color: active ? 'var(--fg-2)' : 'var(--fg-3)',
                textTransform: 'uppercase', letterSpacing: '0.06em',
                borderBottom: '1px solid var(--line)', width: c.width,
                // UX-F9: subtle edge so the stuck header separates from rows scrolling under it.
                boxShadow: '0 1px 0 var(--line-2)',
                cursor: c.sortable ? 'pointer' : 'default', userSelect: 'none', whiteSpace: 'nowrap',
              }}
            >
              {c.header}{c.sortable && <span style={{ marginLeft: 4 }}>{active ? (sort!.dir === 'asc' ? '↑' : '↓') : '↕'}</span>}
            </th>
          );
        })}
      </tr>
    </thead>
  );

  const renderRow = (row: T) => (
    <tr
      key={rowKey(row)}
      // UX-F9: hover + :focus-within handled in CSS (.tbl-row), not JS.
      className="tbl-row"
      onClick={() => onRowClick?.(row)}
      // A11y: clickable rows are keyboard-operable (Enter/Space).
      role={onRowClick ? 'button' : undefined}
      tabIndex={onRowClick ? 0 : undefined}
      onKeyDown={onRowClick ? e => handleKeyDown(e, row) : undefined}
      style={{
        borderBottom: '1px solid var(--line)',
        cursor: onRowClick ? 'pointer' : undefined,
        ...rowStyle?.(row),
      }}
    >
      {columns.map(c => (
        <td key={c.key} style={{
          padding: 'var(--row-pad-y) var(--row-pad-x)',
          fontSize: c.mono ? 12 : 'var(--cell-fs)',
          fontFamily: c.mono ? 'var(--font-mono)' : undefined,
          color: c.mono ? 'var(--fg-2)' : 'var(--fg)',
        }}>
          {c.render(row)}
        </td>
      ))}
    </tr>
  );

  if (sortedRows.length === 0) {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          {head}
          <tbody>
            <tr><td colSpan={columns.length} style={{ padding: 'var(--s6) var(--s3)', textAlign: 'center', color: 'var(--fg-3)' }}>{empty}</td></tr>
          </tbody>
        </table>
      </div>
    );
  }

  if (!virtualize) {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          {head}
          <tbody>{sortedRows.map(renderRow)}</tbody>
        </table>
      </div>
    );
  }

  return <VirtualTable rows={sortedRows} colCount={columns.length} head={head} renderRow={renderRow} maxHeight={maxHeight} />;
}

function VirtualTable<T>({ rows, colCount, head, renderRow, maxHeight }: {
  rows: T[]; colCount: number; head: ReactNode; renderRow: (r: T) => ReactNode; maxHeight: number;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  const items = virtualizer.getVirtualItems();
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;

  return (
    <div ref={parentRef} style={{ maxHeight, overflowY: 'auto', overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        {head}
        <tbody>
          {padTop > 0 && <tr style={{ height: padTop }}><td colSpan={colCount} /></tr>}
          {items.map(vi => renderRow(rows[vi.index]))}
          {padBottom > 0 && <tr style={{ height: padBottom }}><td colSpan={colCount} /></tr>}
        </tbody>
      </table>
    </div>
  );
}
