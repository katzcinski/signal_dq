// Check-Builder (nur interne Gates): bibliotheks-instanziierte Engineering-Checks
// ohne Garantie-Äquivalent (Wertebereiche, Regex, erlaubte Werte …).
import { useMemo } from 'react';
import { useLibrary } from '@/api/library';
import { t } from '@/i18n/de';
import {
  cardStyle, monoStyle, selectStyle, fieldLabel,
  RemoveRowButton, SeveritySelect, CheckParamInput, isBuilderEligible,
} from './shared';
import type { CheckDef as LibraryCheck, GateCheck } from '@/types';

interface CheckBuilderProps {
  checks: GateCheck[];
  onChange: (checks: GateCheck[]) => void;
  columnOptions: string[];
}

export function CheckBuilder({ checks, onChange, columnOptions }: CheckBuilderProps) {
  const { data: library } = useLibrary();
  const templates = useMemo(() => (library?.checks ?? []).filter(isBuilderEligible), [library]);
  const byId = useMemo(() => new Map(templates.map(c => [c.id, c])), [templates]);
  const grouped = useMemo(() => {
    const m = new Map<string, LibraryCheck[]>();
    for (const c of templates) {
      const arr = m.get(c.category);
      if (arr) arr.push(c); else m.set(c.category, [c]);
    }
    return [...m.entries()];
  }, [templates]);

  const addCheck = (id: string) => {
    const tpl = byId.get(id);
    if (!tpl) return;
    const params: Record<string, string | string[]> = {};
    for (const p of tpl.params) params[p.token] = p.type === 'value_list' ? [] : '';
    onChange([...checks, { id, params, expect: tpl.default_expect, severity: tpl.default_severity }]);
  };
  const updateCheck = (i: number, patch: Partial<GateCheck>) =>
    onChange(checks.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{t.workbench.checks.title}</span>
        <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.workbench.checks.subtitle}</span>
      </div>

      {checks.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.workbench.checks.empty}</div>
      )}

      {checks.map((chk, i) => {
        const tpl = byId.get(chk.id);
        return (
          <div key={i} style={{ ...cardStyle, padding: 0, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderBottom: tpl ? '1px solid var(--line)' : 'none' }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{tpl?.label ?? chk.id}</span>
              <span style={{ ...monoStyle, fontSize: 10, color: 'var(--fg-3)' }}>{chk.id}</span>
              <div style={{ flex: 1 }} />
              <RemoveRowButton onClick={() => onChange(checks.filter((_, j) => j !== i))} />
            </div>
            {tpl && (
              <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{tpl.help}</div>
                {tpl.params.map(p => (
                  <div key={p.token} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ ...fieldLabel, minWidth: 96 }} title={p.hint}>{p.label}</span>
                    <CheckParamInput
                      param={p}
                      value={chk.params[p.token] ?? (p.type === 'value_list' ? [] : '')}
                      columnOptions={columnOptions}
                      onChange={v => updateCheck(i, { params: { ...chk.params, [p.token]: v } })}
                    />
                  </div>
                ))}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ ...fieldLabel, minWidth: 96 }}>{t.workbench.checks.expect}</span>
                  <input
                    value={chk.expect}
                    onChange={e => updateCheck(i, { expect: e.target.value })}
                    aria-label={t.workbench.checks.expect}
                    style={{ ...selectStyle, ...monoStyle, width: 160 }}
                  />
                  {tpl.unit && <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{tpl.unit}</span>}
                  <SeveritySelect value={chk.severity} onChange={s => updateCheck(i, { severity: s })} />
                </div>
              </div>
            )}
          </div>
        );
      })}

      <select
        value=""
        onChange={e => { if (e.target.value) addCheck(e.target.value); }}
        aria-label={t.workbench.checks.add}
        style={{ ...selectStyle, alignSelf: 'flex-start', minWidth: 230 }}
      >
        <option value="">{t.workbench.checks.add}</option>
        {grouped.map(([cat, items]) => (
          <optgroup key={cat} label={cat}>
            {items.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
