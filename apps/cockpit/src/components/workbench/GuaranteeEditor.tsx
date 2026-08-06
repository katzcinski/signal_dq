// Garantien-Editor: eine Karte je Familie (kanonisches §1.5-Schema). Rein
// semantisch — kein SQL; der Server validiert verbindlich (G1).
import type { ReactNode } from 'react';
import { Combobox } from '@/components/ui/Combobox';
import { t } from '@/i18n/de';
import {
  GuaranteeCard, SeveritySelect, EnforcementSelect, ColumnsPicker, RemoveRowButton, AddRowButton,
  fieldLabel, selectStyle, monoStyle, maxAgeToHours, hoursToMaxAge,
} from './shared';
import type {
  ContractGuarantees, GuaranteeKey, GuaranteeReferential,
  GuaranteeCompleteness, GuaranteeNotNull,
} from '@/types';

// Familien-Akzent (linker Rand der Kanalzüge): Observability warm, Quality teal.
const FAMILY_ACCENT: Record<string, string> = {
  freshness: 'var(--obs)', volume: 'var(--obs)',
  schema: 'var(--qual)', keys: 'var(--qual)', referential: 'var(--qual)',
  completeness: 'var(--qual)', not_null: 'var(--qual)',
};

interface GuaranteeEditorProps {
  guarantees: ContractGuarantees;
  onChange: (g: ContractGuarantees) => void;
  columnOptions: string[];
  datasetOptions: string[];
  columnsOfDataset: (name: string) => string[];
  // Beobachtete Realität je Familie (letzter Messwert, Sparkline, PASS/FAIL) —
  // von der Workbench eingespeist, sobald der observed-Endpoint geladen ist.
  observed?: (familyKey: string) => ReactNode;
}

export function GuaranteeEditor({ guarantees, onChange, columnOptions, datasetOptions, columnsOfDataset, observed }: GuaranteeEditorProps) {
  const g = guarantees;
  const set = (patch: Partial<ContractGuarantees>) => onChange({ ...g, ...patch });
  const unset = (key: keyof ContractGuarantees) => {
    const next = { ...g };
    delete next[key];
    onChange(next);
  };
  // Kopf-Slot: beobachtete Realität links, Severity rechts.
  const header = (familyKey: string, severity?: ReactNode): ReactNode => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)' }}>
      {observed?.(familyKey)}
      {severity}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* schema */}
      <GuaranteeCard
        familyKey="schema"
        accent={FAMILY_ACCENT.schema}
        enabled={!!g.schema}
        onToggle={on => on ? set({ schema: { columns: [], mode: 'closed', severity: 'fail' } }) : unset('schema')}
        headerExtra={g.schema && header('schema', <><SeveritySelect value={g.schema.severity} onChange={s => set({ schema: { ...g.schema!, severity: s } })} /><EnforcementSelect value={g.schema.enforcement} onChange={m => set({ schema: { ...g.schema!, enforcement: m } })} /></>)}
      >
        {g.schema && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={fieldLabel}>{t.workbench.fields.mode}</span>
              <select
                value={g.schema.mode}
                onChange={e => set({ schema: { ...g.schema!, mode: e.target.value as 'closed' | 'open' } })}
                aria-label={t.workbench.fields.mode}
                style={selectStyle}
              >
                <option value="closed">closed</option>
                <option value="open">open</option>
              </select>
            </div>
            <div>
              <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.columns}</div>
              <ColumnsPicker
                value={g.schema.columns}
                onChange={cols => set({ schema: { ...g.schema!, columns: cols } })}
                options={columnOptions}
              />
            </div>
          </>
        )}
      </GuaranteeCard>

      {/* keys */}
      <GuaranteeCard
        familyKey="keys"
        accent={FAMILY_ACCENT.keys}
        enabled={!!g.keys}
        onToggle={on => on ? set({ keys: [{ columns: [], unique: true, severity: 'critical' }] }) : unset('keys')}
        headerExtra={g.keys && header('keys')}
      >
        {g.keys && (
          <>
            {g.keys.map((key: GuaranteeKey, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap', borderBottom: i < g.keys!.length - 1 ? '1px solid var(--line)' : 'none', paddingBottom: 8 }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>
                    {t.workbench.fields.columns}
                    {key.proposed && (
                      <span style={{
                        marginLeft: 8, background: 'var(--cont)22', border: '1px solid var(--cont)55',
                        color: 'var(--cont)', borderRadius: 3, padding: '1px 5px', fontSize: 10, fontWeight: 600,
                      }}>
                        {t.workbench.proposalChip}
                      </span>
                    )}
                  </div>
                  <ColumnsPicker
                    value={key.columns}
                    onChange={cols => set({ keys: g.keys!.map((k, j) => j === i ? { ...k, columns: cols } : k) })}
                    options={columnOptions}
                  />
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginTop: 18 }}>
                  <input
                    type="checkbox"
                    checked={key.unique}
                    onChange={e => set({ keys: g.keys!.map((k, j) => j === i ? { ...k, unique: e.target.checked } : k) })}
                  />
                  {t.workbench.fields.unique}
                </label>
                <div style={{ marginTop: 14 }}>
                  <SeveritySelect value={key.severity} onChange={s => set({ keys: g.keys!.map((k, j) => j === i ? { ...k, severity: s } : k) })} />
                  <EnforcementSelect value={key.enforcement} onChange={m => set({ keys: g.keys!.map((k, j) => j === i ? { ...k, enforcement: m } : k) })} />
                </div>
                <div style={{ marginTop: 14 }}>
                  <RemoveRowButton onClick={() => {
                    const next = g.keys!.filter((_, j) => j !== i);
                    next.length ? set({ keys: next }) : unset('keys');
                  }} />
                </div>
              </div>
            ))}
            <AddRowButton onClick={() => set({ keys: [...g.keys!, { columns: [], unique: true, severity: 'critical' }] })} />
          </>
        )}
      </GuaranteeCard>

      {/* referential */}
      <GuaranteeCard
        familyKey="referential"
        accent={FAMILY_ACCENT.referential}
        enabled={!!g.referential}
        onToggle={on => on ? set({ referential: [{ fk: [], parent: '', parent_key: [], severity: 'fail' }] }) : unset('referential')}
        headerExtra={g.referential && header('referential')}
      >
        {g.referential && (
          <>
            {g.referential.map((ref: GuaranteeReferential, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap', borderBottom: i < g.referential!.length - 1 ? '1px solid var(--line)' : 'none', paddingBottom: 8 }}>
                <div>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.fk}</div>
                  <Combobox
                    options={columnOptions}
                    value={ref.fk[0] ?? ''}
                    onChange={c => set({ referential: g.referential!.map((r, j) => j === i ? { ...r, fk: [c] } : r) })}
                    placeholder={t.workbench.fields.pickColumn}
                    width={160}
                  />
                </div>
                <div>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.parent}</div>
                  <Combobox
                    options={datasetOptions}
                    value={ref.parent}
                    onChange={p => set({ referential: g.referential!.map((r, j) => j === i ? { ...r, parent: p, parent_key: [] } : r) })}
                    placeholder={t.workbench.fields.pickDataset}
                    width={180}
                  />
                </div>
                <div>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.parentKey}</div>
                  <Combobox
                    options={columnsOfDataset(ref.parent)}
                    value={ref.parent_key[0] ?? ''}
                    onChange={c => set({ referential: g.referential!.map((r, j) => j === i ? { ...r, parent_key: [c] } : r) })}
                    placeholder={t.workbench.fields.pickColumn}
                    width={160}
                  />
                </div>
                <SeveritySelect value={ref.severity} onChange={s => set({ referential: g.referential!.map((r, j) => j === i ? { ...r, severity: s } : r) })} />
                <EnforcementSelect value={ref.enforcement} onChange={m => set({ referential: g.referential!.map((r, j) => j === i ? { ...r, enforcement: m } : r) })} />
                <RemoveRowButton onClick={() => {
                  const next = g.referential!.filter((_, j) => j !== i);
                  next.length ? set({ referential: next }) : unset('referential');
                }} />
              </div>
            ))}
            <AddRowButton onClick={() => set({ referential: [...g.referential!, { fk: [], parent: '', parent_key: [], severity: 'fail' }] })} />
          </>
        )}
      </GuaranteeCard>

      {/* freshness */}
      <GuaranteeCard
        familyKey="freshness"
        accent={FAMILY_ACCENT.freshness}
        enabled={!!g.freshness}
        onToggle={on => on ? set({ freshness: { column: '', max_age: 'PT24H', severity: 'warn' } }) : unset('freshness')}
        headerExtra={g.freshness && header('freshness', <><SeveritySelect value={g.freshness.severity} onChange={s => set({ freshness: { ...g.freshness!, severity: s } })} /><EnforcementSelect value={g.freshness.enforcement} onChange={m => set({ freshness: { ...g.freshness!, enforcement: m } })} /></>)}
      >
        {g.freshness && (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--s3)', flexWrap: 'wrap' }}>
            <div>
              <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.column}</div>
              <Combobox
                options={columnOptions}
                value={g.freshness.column}
                onChange={c => set({ freshness: { ...g.freshness!, column: c } })}
                placeholder={t.workbench.fields.pickColumn}
                width={180}
              />
            </div>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)', fontSize: 11, color: 'var(--fg-3)' }}>
              {t.workbench.fields.maxAgeHours}
              <input
                type="number"
                min={1}
                value={maxAgeToHours(g.freshness.max_age)}
                onChange={e => set({ freshness: { ...g.freshness!, max_age: hoursToMaxAge(Number(e.target.value)) } })}
                style={{ ...selectStyle, width: 90 }}
              />
            </label>
            <span style={{ ...monoStyle, fontSize: 11, color: 'var(--fg-3)' }}>{g.freshness.max_age}</span>
          </div>
        )}
      </GuaranteeCard>

      {/* volume */}
      <GuaranteeCard
        familyKey="volume"
        accent={FAMILY_ACCENT.volume}
        enabled={!!g.volume}
        onToggle={on => on ? set({ volume: { min_rows: 1, severity: 'warn' } }) : unset('volume')}
        headerExtra={g.volume && header('volume', <><SeveritySelect value={g.volume.severity} onChange={s => set({ volume: { ...g.volume!, severity: s } })} /><EnforcementSelect value={g.volume.enforcement} onChange={m => set({ volume: { ...g.volume!, enforcement: m } })} /></>)}
      >
        {g.volume && (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)', fontSize: 11, color: 'var(--fg-3)' }}>
              {t.workbench.fields.minRows}
              <input
                type="number"
                min={0}
                value={g.volume.min_rows ?? ''}
                onChange={e => {
                  const v = e.target.value;
                  const next = { ...g.volume! };
                  if (v === '') delete next.min_rows; else next.min_rows = Number(v);
                  set({ volume: next });
                }}
                style={{ ...selectStyle, width: 100 }}
              />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={g.volume.baseline === 'rolling'}
                onChange={e => {
                  const next = { ...g.volume! };
                  if (e.target.checked) next.baseline = 'rolling'; else delete next.baseline;
                  set({ volume: next });
                }}
              />
              {t.workbench.fields.baseline}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={g.volume.bounds === 'auto'}
                onChange={e => {
                  const next = { ...g.volume! };
                  if (e.target.checked) next.bounds = 'auto'; else delete next.bounds;
                  set({ volume: next });
                }}
              />
              {t.workbench.fields.bounds}
            </label>
          </div>
        )}
      </GuaranteeCard>

      {/* completeness */}
      <GuaranteeCard
        familyKey="completeness"
        accent={FAMILY_ACCENT.completeness}
        enabled={!!g.completeness}
        onToggle={on => on ? set({ completeness: [{ column: '', min_pct: 95, severity: 'warn' }] }) : unset('completeness')}
        headerExtra={g.completeness && header('completeness')}
      >
        {g.completeness && (
          <>
            {g.completeness.map((row: GuaranteeCompleteness, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.column}</div>
                  <Combobox
                    options={columnOptions}
                    value={row.column}
                    onChange={c => set({ completeness: g.completeness!.map((r, j) => j === i ? { ...r, column: c } : r) })}
                    placeholder={t.workbench.fields.pickColumn}
                    width={180}
                  />
                </div>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)', fontSize: 11, color: 'var(--fg-3)' }}>
                  {t.workbench.fields.minPct}
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={row.min_pct}
                    onChange={e => set({ completeness: g.completeness!.map((r, j) => j === i ? { ...r, min_pct: Number(e.target.value) } : r) })}
                    style={{ ...selectStyle, width: 80 }}
                  />
                </label>
                <SeveritySelect value={row.severity} onChange={s => set({ completeness: g.completeness!.map((r, j) => j === i ? { ...r, severity: s } : r) })} />
                <EnforcementSelect value={row.enforcement} onChange={m => set({ completeness: g.completeness!.map((r, j) => j === i ? { ...r, enforcement: m } : r) })} />
                <RemoveRowButton onClick={() => {
                  const next = g.completeness!.filter((_, j) => j !== i);
                  next.length ? set({ completeness: next }) : unset('completeness');
                }} />
              </div>
            ))}
            <AddRowButton onClick={() => set({ completeness: [...g.completeness!, { column: '', min_pct: 95, severity: 'warn' }] })} />
          </>
        )}
      </GuaranteeCard>

      {/* not_null */}
      <GuaranteeCard
        familyKey="not_null"
        accent={FAMILY_ACCENT.not_null}
        enabled={!!g.not_null}
        onToggle={on => on ? set({ not_null: [{ columns: [], severity: 'fail' }] }) : unset('not_null')}
        headerExtra={g.not_null && header('not_null')}
      >
        {g.not_null && (
          <>
            {g.not_null.map((row: GuaranteeNotNull, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div style={{ ...fieldLabel, marginBottom: 4 }}>{t.workbench.fields.columns}</div>
                  <ColumnsPicker
                    value={row.columns}
                    onChange={cols => set({ not_null: g.not_null!.map((r, j) => j === i ? { ...r, columns: cols } : r) })}
                    options={columnOptions}
                  />
                </div>
                <div style={{ marginTop: 14 }}>
                  <SeveritySelect value={row.severity} onChange={s => set({ not_null: g.not_null!.map((r, j) => j === i ? { ...r, severity: s } : r) })} />
                </div>
                <div style={{ marginTop: 14 }}>
                  <EnforcementSelect value={row.enforcement} onChange={m => set({ not_null: g.not_null!.map((r, j) => j === i ? { ...r, enforcement: m } : r) })} />
                </div>
                <div style={{ marginTop: 14 }}>
                  <RemoveRowButton onClick={() => {
                    const next = g.not_null!.filter((_, j) => j !== i);
                    next.length ? set({ not_null: next }) : unset('not_null');
                  }} />
                </div>
              </div>
            ))}
            <AddRowButton onClick={() => set({ not_null: [...g.not_null!, { columns: [], severity: 'fail' }] })} />
          </>
        )}
      </GuaranteeCard>
    </div>
  );
}
