import { t } from '@/i18n/de';

// Kanonische SLA-Schwellwerte (aus SlaBars gezogen, damit Workbench und
// Governance-Panel dieselben Farben verwenden): ≥ 99 % ok, ≥ 95 % warn, sonst fail.
export function slaColor(pct: number): string {
  return pct >= 99 ? 'var(--status-ok)' : pct >= 95 ? 'var(--status-warn)' : 'var(--status-fail)';
}

// Ein einzelner SLA-Fensterwert (%-compliant) als gefärbter Prozentwert;
// `null` → „keine Daten" (kein Compliance-Event im Fenster).
export function SlaWindowValue({ pct }: { pct: number | null }) {
  if (pct == null) {
    return (
      <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        {t.workbench.slaNoData}
      </span>
    );
  }
  return (
    <span style={{ color: slaColor(pct), fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500 }}>
      {pct.toFixed(1)} %
    </span>
  );
}
