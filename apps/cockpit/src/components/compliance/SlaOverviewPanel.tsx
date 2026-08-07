// SLA-Übersichts-Panel der Compliance-Seite: je aktivem Boundary-Contract eine
// Zeile mit aktuellem Compliance-Status und den 7/30/90-Tage-Fenstern.
//
// Datenweg (Option A aus docs/HANDOVER_SLA_Panel.md): kein Aggregat-Endpoint —
// jede Zeile hält ihren eigenen `useContractSla`-Hook; react-query
// parallelisiert und cacht die Einzelabrufe. Die Zeilenkomponente kapselt die
// Datenquelle, ein späterer Umstieg auf einen Aggregat-Endpoint tauscht nur sie.
import type { CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { useContractSla } from '@/api/contracts';
import { Panel } from '@/components/ui/Panel';
import { StatusPill } from '@/components/ui/StatusPill';
import { SlaWindowValue } from '@/components/ui/SlaWindowValue';
import { t } from '@/i18n/de';
import type { Contract } from '@/types';

const thStyle: CSSProperties = {
  padding: 'var(--row-pad-y) var(--row-pad-x)', textAlign: 'left',
  fontSize: 10, fontWeight: 600, color: 'var(--fg-3)',
  textTransform: 'uppercase', letterSpacing: '0.06em',
  borderBottom: '1px solid var(--line)', whiteSpace: 'nowrap',
};
const tdStyle: CSSProperties = {
  padding: 'var(--row-pad-y) var(--row-pad-x)', fontSize: 12, whiteSpace: 'nowrap',
};

// Eine Contract-Zeile mit eigenem SLA-Hook. `current` als kanonischer
// StatusPill (compliant/breached/unknown), drei Fensterwerte via SlaWindowValue.
function SlaRow({ product, onOpen }: { product: string; onOpen: (product: string) => void }) {
  const { data } = useContractSla(product);
  const windows = data?.windows;
  return (
    <tr
      className="tbl-row"
      role="button"
      tabIndex={0}
      onClick={() => onOpen(product)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(product);
        }
      }}
      style={{ borderBottom: '1px solid var(--line)', cursor: 'pointer' }}
    >
      <td style={{ ...tdStyle, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>{product}</td>
      <td style={tdStyle}>
        {data ? (
          <StatusPill status={data.current} size="sm" label={t.compliance[data.current] ?? data.current} />
        ) : (
          <span style={{ color: 'var(--fg-3)' }}>{t.workbench.slaNoData}</span>
        )}
      </td>
      <td style={tdStyle}><SlaWindowValue pct={windows?.['7d'] ?? null} /></td>
      <td style={tdStyle}><SlaWindowValue pct={windows?.['30d'] ?? null} /></td>
      <td style={tdStyle}><SlaWindowValue pct={windows?.['90d'] ?? null} /></td>
    </tr>
  );
}

// Nur aktive Contracts (der Titel sagt es). Stabile Sortierung nach Produktname —
// worst-window-first ist unter Option A nicht möglich, da die Fensterwerte erst
// pro Zeile geladen werden und dem Panel nicht vorliegen.
export function SlaOverviewPanel({ contracts }: { contracts: Contract[] }) {
  const navigate = useNavigate();
  const rows = [...contracts].sort((a, b) => a.product.localeCompare(b.product));
  return (
    <Panel title={t.governance.slaTitle} family="contract">
      {rows.length === 0 ? (
        <div style={{ padding: 'var(--s4)', textAlign: 'center', color: 'var(--fg-3)', fontSize: 12 }}>
          {t.governance.slaEmpty}
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>{t.governance.slaProduct}</th>
                <th style={thStyle}>{t.governance.slaCurrent}</th>
                <th style={thStyle}>{t.governance.sla7d}</th>
                <th style={thStyle}>{t.governance.sla30d}</th>
                <th style={thStyle}>{t.governance.sla90d}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <SlaRow key={c.product} product={c.product} onOpen={p => navigate(`/objects/${p}`)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
