import { Spark } from './Spark';

interface Props {
  label: string;
  value: string | number;
  delta?: string;
  /** true → grün, false → rot, undefined → neutrale Zusatzinfo. */
  deltaPositive?: boolean;
  sparkData?: number[];
  sparkColor?: string;
  accent?: string;
  /** Macht die Kachel klickbar (Deep-Link auf die gefilterte Ansicht). */
  onClick?: () => void;
}

export function Kpi({ label, value, delta, deltaPositive, sparkData, sparkColor, accent = 'var(--qual)', onClick }: Props) {
  const deltaColor = deltaPositive === undefined
    ? 'var(--fg-3)'
    : deltaPositive ? 'var(--status-ok)' : 'var(--status-fail)';
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={onClick ? 'kpi-link' : undefined}
      style={{
        background: 'var(--bg-1)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)', padding: 'var(--s4) var(--s5)',
        borderBottom: `2px solid ${accent}`,
        display: 'flex', flexDirection: 'column', gap: 'var(--s2)',
        minWidth: 0, textAlign: 'left', color: 'inherit', font: 'inherit',
      }}
    >
      <div style={{
        fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 'var(--s2)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 27, fontWeight: 700, color: 'var(--fg)', lineHeight: 1, whiteSpace: 'nowrap' }}>{value}</span>
        {sparkData && <Spark data={sparkData} color={sparkColor ?? accent} />}
        {!sparkData && onClick && <span aria-hidden style={{ color: 'var(--fg-3)', fontSize: 13, lineHeight: 1 }}>→</span>}
      </div>
      {/* Delta auf eigener Zeile — bricht nicht mehr in die Wertzeile um. */}
      {delta && (
        <div style={{ fontSize: 12, lineHeight: 'var(--lh-meta)', color: deltaColor }}>
          {delta}
        </div>
      )}
    </Tag>
  );
}
