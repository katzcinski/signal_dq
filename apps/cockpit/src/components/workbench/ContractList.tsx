// Linke Liste: Contracts + „Neu aus Inventar" (seedet ein internes Gate).
import { useState } from 'react';
import { useSeedContract } from '@/api/contracts';
import { StatusDot } from '@/components/ui/StatusDot';
import { Button } from '@/components/ui/Button';
import { t } from '@/i18n/de';
import {
  monoStyle, datasetName, sectionOfKind, complianceStatus, type Section,
} from './shared';
import type { ContractOut, InventoryDataset } from '@/types';

function SectionTabs({ section, onChange }: { section: Section; onChange: (s: Section) => void }) {
  const tab = (key: Section, label: string) => (
    <button
      onClick={() => onChange(key)}
      style={{
        flex: 1, padding: 'var(--s2) var(--s2)', fontSize: 12, cursor: 'pointer', background: 'none',
        border: 'none', borderBottom: section === key ? '2px solid var(--cont)' : '2px solid transparent',
        color: section === key ? 'var(--fg)' : 'var(--fg-3)', fontWeight: section === key ? 600 : 400,
      }}
    >
      {label}
    </button>
  );
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--line)' }}>
      {tab('internal', t.workbench.tabInternal)}
      {tab('contract', t.workbench.tabContract)}
    </div>
  );
}

export function ContractList({ contracts, inventory, selected, onSelect, section, onSectionChange }: {
  contracts: ContractOut[];
  inventory: InventoryDataset[];
  selected: string;
  onSelect: (product: string) => void;
  section: Section;
  onSectionChange: (s: Section) => void;
}) {
  const [search, setSearch] = useState('');
  const seed = useSeedContract();
  const [seedingId, setSeedingId] = useState('');

  const inSection = contracts.filter(c => sectionOfKind(c.kind) === section);
  const q = search.trim().toLowerCase();
  const filtered = q
    ? inSection.filter(c => c.product.toLowerCase().includes(q) || c.dataset.toLowerCase().includes(q))
    : inSection;

  // "Neu aus Inventar" seeds an internal gate (the seed default kind), so it only
  // belongs in the internal frame; the contract frame is reached via promotion.
  const contractKeys = new Set(contracts.flatMap(c => [c.product, c.dataset]));
  const uncovered = section === 'internal'
    ? inventory.filter(d => {
        const id = String(d.id ?? datasetName(d));
        return id && !contractKeys.has(id) && !contractKeys.has(datasetName(d));
      })
    : [];

  return (
    <div style={{ width: 280, borderRight: '1px solid var(--line)', overflowY: 'auto', flexShrink: 0 }}>
      <SectionTabs section={section} onChange={onSectionChange} />
      <div style={{ padding: 10, borderBottom: '1px solid var(--line)' }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t.workbench.searchContracts}
          aria-label={t.workbench.searchContracts}
          style={{
            width: '100%', background: 'var(--bg-2)', border: '1px solid var(--line-2)',
            color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12, outline: 'none',
          }}
        />
      </div>

      {filtered.length === 0 && (
        <div style={{ padding: 14, fontSize: 12, color: 'var(--fg-3)' }}>
          {section === 'internal' ? t.workbench.emptyInternal : t.workbench.emptyContract}
        </div>
      )}
      {filtered.map(c => (
        <button
          key={c.product}
          onClick={() => onSelect(c.product)}
          style={{
            display: 'block', width: '100%', textAlign: 'left',
            padding: '10px 14px', cursor: 'pointer',
            background: selected === c.product ? 'var(--bg-2)' : 'transparent',
            border: 'none', borderBottom: '1px solid var(--line)', color: 'var(--fg)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
            <span style={{ ...monoStyle, color: 'var(--fg)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.product}</span>
            <span style={{
              fontSize: 10, padding: '1px 6px', borderRadius: 3,
              background: 'var(--bg-3)', border: '1px solid var(--line-2)', color: 'var(--fg-2)',
            }}>
              {t.lifecycle[c.lifecycle] ?? c.lifecycle}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', marginTop: 4 }}>
            <span style={{ ...monoStyle, fontSize: 10, color: 'var(--fg-3)' }}>v{String(c.version).replace(/^v/i, '')}</span>
            <span style={{ fontSize: 10, color: 'var(--fg-3)' }}>{c.owned_by}</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)', marginLeft: 'auto', fontSize: 10, color: 'var(--fg-3)' }}>
              <StatusDot status={complianceStatus(c)} size={6} />
              {t.compliance[c.compliance ?? 'unknown'] ?? t.compliance.unknown}
            </span>
          </div>
        </button>
      ))}

      {/* Neu aus Inventar */}
      {uncovered.length > 0 && (
        <div>
          <div style={{ padding: '10px 14px 4px', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t.workbench.newFromInventory}
          </div>
          {uncovered.map(d => {
            const id = String(d.id ?? datasetName(d));
            return (
              <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', padding: '6px 14px', borderBottom: '1px solid var(--line)' }}>
                <span style={{ ...monoStyle, fontSize: 11, color: 'var(--fg-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {datasetName(d)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  pending={seed.isPending && seedingId === id}
                  pendingLabel={t.workbench.seeding}
                  onClick={() => {
                    setSeedingId(id);
                    seed.mutate(id, { onSuccess: () => onSelect(id) });
                  }}
                >
                  {t.workbench.seed}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
