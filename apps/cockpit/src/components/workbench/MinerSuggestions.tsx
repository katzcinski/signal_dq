// Inline-Miner-Vorschläge (P6): datengetriebene Garantie-Vorschläge für diesen
// Contract. „Übernehmen" trägt den vorgeschlagenen Schwellwert in den Entwurf ein
// (client-seitig); gespeichert wird anschließend über den normalen Freigabepfad
// (G1 → Kompilieren → G3). Kein Server-Write hier.
import { toast } from 'sonner';
import { useProposals } from '@/api/proposals';
import { Button } from '@/components/ui/Button';
import { t } from '@/i18n/de';
import { cardStyle, monoStyle } from './shared';
import type { ContractGuarantees, Proposal } from '@/types';

// Übersetzt den vorgeschlagenen Erwartungswert in den passenden Garantie-Parameter.
// Nur die numerischen Miner-Ausgaben (Volume/Completeness/Freshness) sind
// automatisch übernehmbar; sonst null (→ Hinweis „manuell anpassen").
export function applyProposalToGuarantees(g: ContractGuarantees, p: Proposal): ContractGuarantees | null {
  const num = parseFloat((p.proposed_expect.match(/-?\d[\d.]*/) ?? [''])[0]);
  if (Number.isNaN(num)) return null;

  if (p.check_name === 'volume_min_rows') {
    return { ...g, volume: { ...(g.volume ?? {}), min_rows: Math.round(num), severity: g.volume?.severity ?? 'warn' } };
  }
  if (p.check_name.startsWith('freshness_')) {
    if (!g.freshness) return null;
    const hours = Math.max(1, Math.round(num / 3600));
    return { ...g, freshness: { ...g.freshness, max_age: `PT${hours}H` } };
  }
  if (p.check_name.startsWith('completeness_')) {
    const col = p.check_name.slice('completeness_'.length);
    if (!g.completeness?.some(r => r.column === col)) return null;
    const minPct = Math.max(0, Math.min(100, 100 - num));  // expect ist „<= max_null_pct"
    return { ...g, completeness: g.completeness.map(r => r.column === col ? { ...r, min_pct: minPct } : r) };
  }
  return null;
}

export function MinerSuggestions({ product, guarantees, onApply }: {
  product: string;
  guarantees: ContractGuarantees;
  onApply: (g: ContractGuarantees) => void;
}) {
  const { data: proposals = [] } = useProposals();
  const relevant = proposals.filter(p => p.product === product && p.status === 'open');
  if (relevant.length === 0) return null;

  return (
    <div style={{ ...cardStyle, borderLeft: '3px solid var(--cont)', display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
        <span aria-hidden>⚡</span>
        <span style={{ fontWeight: 600, fontSize: 13 }}>{t.workbench.miner.title}</span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>({relevant.length})</span>
      </div>
      {relevant.map(p => {
        const pct = p.confidence <= 1 ? Math.round(p.confidence * 100) : Math.round(p.confidence);
        return (
          <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', flexWrap: 'wrap', padding: 'var(--s1) 0', borderTop: '1px solid var(--line)' }}>
            <span style={{ ...monoStyle, fontSize: 11, color: 'var(--fg-2)' }}>{p.check_name}</span>
            <span style={{ ...monoStyle, fontSize: 11 }}>
              <span style={{ color: 'var(--fg-3)' }}>{p.current_expect || '∅'}</span>
              {' → '}
              <span style={{ color: 'var(--status-ok)' }}>{p.proposed_expect}</span>
            </span>
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.workbench.miner.confidence} {pct}%</span>
            <div style={{ flex: 1 }} />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const next = applyProposalToGuarantees(guarantees, p);
                if (next) {
                  onApply(next);
                  toast.success(t.workbench.miner.applied);
                } else {
                  toast(t.workbench.miner.notMappable);
                }
              }}
            >
              {t.workbench.miner.apply}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
