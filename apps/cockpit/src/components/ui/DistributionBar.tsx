// Schlanker gestapelter Anteilsbalken + Legende: zeigt die Verteilung eines
// Bestands über wenige Kategorien als eine Zeile. Anders als eine einzelne
// Prozent-KPI macht der Balken Momentum sichtbar (z. B. Entwürfe in Arbeit,
// veraltete Reste), ohne ein Chart-Framework zu bemühen.

export interface DistributionSegment {
  key: string;
  label: string;
  count: number;
  color: string;
}

export function DistributionBar({ segments, ariaLabel }: { segments: DistributionSegment[]; ariaLabel?: string }) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
      <div
        role="img"
        aria-label={ariaLabel ?? segments.map(s => `${s.label}: ${s.count}`).join(', ')}
        style={{
          display: 'flex', height: 8, borderRadius: 'var(--r-full)',
          overflow: 'hidden', background: 'var(--bg-3)',
        }}
      >
        {total > 0 && segments.filter(s => s.count > 0).map(s => (
          <div
            key={s.key}
            title={`${s.label}: ${s.count}`}
            style={{ width: `${(100 * s.count) / total}%`, background: s.color }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--s2) var(--s4)' }}>
        {segments.map(s => (
          <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 11, color: 'var(--fg-3)' }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            {s.label}
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-2)', fontWeight: 600 }}>{s.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
