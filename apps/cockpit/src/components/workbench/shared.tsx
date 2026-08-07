// Geteilte Bausteine der Contract-Workbench. Zuvor lagen Stil-Tokens, reine
// Helfer und die kleinen Formular-Atome inline in der 1666-Zeilen-Seite
// ContractWorkbench.tsx; hier zentral, damit die Editor-Bausteine (GuaranteeEditor,
// CheckBuilder, CompilePanel, …) sauber ausgelagert und einzeln testbar sind.
import { useState, type CSSProperties, type ReactNode } from 'react';
import type { AxiosError } from 'axios';
import { Combobox } from '@/components/ui/Combobox';
import { Tooltip } from '@/components/ui/Tooltip';
import { Button } from '@/components/ui/Button';
import { t } from '@/i18n/de';
import type {
  ArtifactKind, Contract, ContractPutBody, ContractOut,
  CheckDef as LibraryCheck, CheckTemplateParam, Severity, InventoryDataset, EnforcementMode,
} from '@/types';

// ─── Shared style tokens ─────────────────────────────────────────────────────
export const cardStyle: CSSProperties = {
  background: 'var(--bg-1)', border: '1px solid var(--line)',
  borderRadius: 'var(--r-lg)', padding: 'var(--s4)',
};
export const monoStyle: CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 12,
};
export const selectStyle: CSSProperties = {
  background: 'var(--bg-2)', border: '1px solid var(--line-2)',
  color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: 'var(--s1) var(--s2)', fontSize: 12,
};
export const fieldLabel: CSSProperties = { fontSize: 11, color: 'var(--fg-3)' };

export const SEVERITIES: Severity[] = ['warn', 'fail', 'critical'];

// ─── Frame split by kind ─────────────────────────────────────────────────────
// Two visible frames on one tool: internal DQ gates (no ceremony) and boundary
// contracts (versioned, governed). `internal_gate` ⇒ internal; everything else
// is a boundary contract. The editor/compiler engine is shared — only chrome and
// ceremony differ — so this is an IA split, not two separate workbenches.
export type Section = 'internal' | 'contract';
export const sectionOfKind = (kind: ArtifactKind | undefined): Section =>
  kind === 'internal_gate' ? 'internal' : 'contract';

export const complianceStatus = (c: ContractOut): string =>
  c.compliance === 'compliant' ? 'pass' : c.compliance === 'breached' ? 'fail' : 'unknown';

// ─── Pure helpers ────────────────────────────────────────────────────────────

export const datasetName = (d: InventoryDataset): string =>
  String(d.technicalName ?? d.name ?? d.id ?? '');

export const majorOf = (version: string | undefined): number => {
  const n = parseInt(String(version ?? '0').replace(/^v/i, '').split('.')[0], 10);
  return Number.isFinite(n) ? n : 0;
};

export const maxAgeToHours = (maxAge: string | undefined): number => {
  if (!maxAge) return 24;
  const h = /^PT(\d+(?:\.\d+)?)H$/i.exec(maxAge);
  if (h) return Number(h[1]);
  const d = /^P(\d+)D$/i.exec(maxAge);
  if (d) return Number(d[1]) * 24;
  return 24;
};

export const hoursToMaxAge = (hours: number): string => `PT${Math.max(1, Math.round(hours))}H`;

// PUT body has NO lifecycle field — the server forces draft.
export const toPutBody = (c: Contract | ContractPutBody): ContractPutBody => ({
  product: c.product,
  kind: c.kind ?? 'internal_gate',
  dataset: c.dataset,
  owned_by: c.owned_by,
  owners: c.owners,
  version: c.version,
  description: c.description,
  guarantees: c.guarantees ?? {},
  observability: c.observability ?? {},
  checks: c.checks ?? [],
});

// RFC-7807: detail.errors list (defensive against shape variants).
export function extractValidationErrors(e: unknown): string[] {
  const data = (e as AxiosError<Record<string, unknown>>)?.response?.data;
  if (!data) return [];
  const detail = data.detail ?? data;
  const raw = Array.isArray(detail) ? detail
    : (detail && typeof detail === 'object' && 'errors' in detail) ? (detail as { errors: unknown }).errors
    : typeof detail === 'string' ? [detail]
    : [];
  if (!Array.isArray(raw)) return [String(raw)];
  return raw.map(item => {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') {
      const o = item as Record<string, unknown>;
      const loc = Array.isArray(o.loc) ? o.loc.join('.') : o.path ?? '';
      const msg = o.msg ?? o.message ?? JSON.stringify(item);
      return loc ? `${loc}: ${msg}` : String(msg);
    }
    return String(item);
  });
}

// Iteration 1: author the engineering checks that have no guarantee equivalent
// (ranges, regex, allowed sets, …). Guarantee-covered templates are excluded so
// nothing can be authored twice; custom_sql and raw-SQL-expression (`expr`)
// params are deferred — no GUI path yet (HANDOVER §5).
export const GUARANTEE_COVERED_IDS = new Set([
  'schema', 'duplicate', 'duplicate_composite', 'reference_integrity',
  'freshness', 'row_count', 'completeness_pct', 'missing',
]);

export const isBuilderEligible = (c: LibraryCheck): boolean =>
  !!c.sql_template
  && c.id !== 'custom_sql'
  && !GUARANTEE_COVERED_IDS.has(c.id)
  && c.params.every(p => p.type !== 'expr');

// ─── Small form atoms ────────────────────────────────────────────────────────

export function FrameTag({ internal }: { internal: boolean }) {
  return (
    <Tooltip content={internal ? t.workbench.frameInternalHint : t.workbench.frameContractHint}>
      <span style={{
        fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--r)',
        background: internal ? 'var(--qual)22' : 'var(--cont)22',
        border: `1px solid ${internal ? 'var(--qual)' : 'var(--cont)'}`,
        color: internal ? 'var(--qual)' : 'var(--cont)',
        whiteSpace: 'nowrap',
      }}>
        {internal ? t.workbench.frameInternal : t.workbench.frameContract}
      </span>
    </Tooltip>
  );
}

// Durchsetzungsmodus je Garantie (gate|quarantine|monitor); leer = Contract-
// Default (enforcement_default, sonst monitor). FE spiegelt, Server erzwingt.
export function EnforcementSelect({ value, onChange }: {
  value: EnforcementMode | undefined;
  onChange: (m: EnforcementMode | undefined) => void;
}) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange((e.target.value || undefined) as EnforcementMode | undefined)}
      aria-label={t.workbench.fields.enforcement}
      title={t.workbench.fields.enforcementHint}
      style={selectStyle}
    >
      <option value="">{t.workbench.fields.enforcementDefault}</option>
      <option value="monitor">{t.quarantine.enforcementLabel.monitor}</option>
      <option value="quarantine">{t.quarantine.enforcementLabel.quarantine}</option>
      <option value="gate">{t.quarantine.enforcementLabel.gate}</option>
    </select>
  );
}

export function SeveritySelect({ value, onChange }: { value: Severity | undefined; onChange: (s: Severity) => void }) {
  return (
    <select
      value={value ?? 'warn'}
      onChange={e => onChange(e.target.value as Severity)}
      aria-label={t.common.severity}
      style={selectStyle}
    >
      {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

// Multi-column picker: chips + combobox (NO free text — picker only).
export function ColumnsPicker({ value, onChange, options }: {
  value: string[];
  onChange: (cols: string[]) => void;
  options: string[];
}) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      {value.map(col => (
        <span key={col} style={{
          display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)',
          background: 'var(--bg-3)', border: '1px solid var(--line-2)', borderRadius: 'var(--r)',
          padding: '2px 6px', ...monoStyle, fontSize: 11,
        }}>
          {col}
          <button
            onClick={() => onChange(value.filter(c => c !== col))}
            aria-label={`${t.common.remove}: ${col}`}
            style={{ background: 'none', border: 'none', color: 'var(--fg-3)', padding: 0, fontSize: 12, cursor: 'pointer' }}
          >
            ×
          </button>
        </span>
      ))}
      <Combobox
        options={options.filter(o => !value.includes(o))}
        value=""
        onChange={c => onChange([...value, c])}
        placeholder={t.workbench.fields.pickColumn}
        width={170}
      />
    </div>
  );
}

// Garantie-„Kanalzug": Kopf mit Toggle + Familie, optionaler Kopf-Slot
// (Severity, beobachtete Realität) und aufklappbarer Parameter-Bereich.
export function GuaranteeCard({ familyKey, enabled, onToggle, headerExtra, accent, children }: {
  familyKey: string;
  enabled: boolean;
  onToggle: (on: boolean) => void;
  headerExtra?: ReactNode;
  accent?: string;
  children?: ReactNode;
}) {
  return (
    <div style={{
      ...cardStyle, padding: 0, overflow: 'hidden',
      borderLeft: enabled && accent ? `3px solid ${accent}` : cardStyle.border as string,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
        borderBottom: enabled && children ? '1px solid var(--line)' : 'none',
      }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => onToggle(e.target.checked)}
            aria-label={`${t.workbench.families[familyKey]} ${t.workbench.enabled}`}
          />
          {t.workbench.families[familyKey] ?? familyKey}
        </label>
        <span style={{ ...monoStyle, fontSize: 10, color: 'var(--fg-3)' }}>guarantees.{familyKey}</span>
        <div style={{ flex: 1 }} />
        {enabled && headerExtra}
      </div>
      {enabled && children && <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>{children}</div>}
    </div>
  );
}

export function RemoveRowButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={t.common.remove}
      style={{ background: 'none', border: '1px solid var(--line-2)', color: 'var(--fg-3)', borderRadius: 'var(--r)', padding: '2px 8px', fontSize: 11, cursor: 'pointer' }}
    >
      ×
    </button>
  );
}

export function AddRowButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick} style={{ alignSelf: 'flex-start' }}>
      + {t.workbench.fields.addEntry}
    </Button>
  );
}

// Free-text multi-value input for value_list params (chips + type-and-Enter).
export function ValueListInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [entry, setEntry] = useState('');
  const commit = () => {
    const v = entry.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setEntry('');
  };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      {value.map(v => (
        <span key={v} style={{
          display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)',
          background: 'var(--bg-3)', border: '1px solid var(--line-2)', borderRadius: 'var(--r)',
          padding: '2px 6px', ...monoStyle, fontSize: 11,
        }}>
          {v}
          <button
            onClick={() => onChange(value.filter(x => x !== v))}
            aria-label={`${t.common.remove}: ${v}`}
            style={{ background: 'none', border: 'none', color: 'var(--fg-3)', padding: 0, fontSize: 12, cursor: 'pointer' }}
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={entry}
        onChange={e => setEntry(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
        onBlur={commit}
        placeholder={t.workbench.checks.addValue}
        style={{ ...selectStyle, width: 120 }}
      />
    </div>
  );
}

// One param input, chosen by the library param `type`.
export function CheckParamInput({ param, value, columnOptions, onChange }: {
  param: CheckTemplateParam;
  value: string | string[];
  columnOptions: string[];
  onChange: (v: string | string[]) => void;
}) {
  if (param.type === 'identifier') {
    return (
      <Combobox
        options={columnOptions}
        value={typeof value === 'string' ? value : ''}
        onChange={onChange}
        placeholder={t.workbench.fields.pickColumn}
        width={180}
      />
    );
  }
  if (param.type === 'value_list') {
    return <ValueListInput value={Array.isArray(value) ? value : []} onChange={onChange} />;
  }
  return (
    <input
      type={param.type === 'number' ? 'number' : 'text'}
      value={typeof value === 'string' ? value : ''}
      onChange={e => onChange(e.target.value)}
      placeholder={param.hint}
      aria-label={param.label}
      style={{ ...selectStyle, ...monoStyle, width: param.type === 'number' ? 110 : 200 }}
    />
  );
}

export function ConflictList({ conflicts }: { conflicts: string[] }) {
  if (!conflicts.length) return null;
  return (
    <div style={{ background: 'var(--status-warn)22', border: '1px solid var(--status-warn)', borderRadius: 'var(--r-md)', padding: '10px 14px', marginTop: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--status-warn)', marginBottom: 4 }}>
        {conflicts.length} {t.workbench.compile.conflicts}
      </div>
      {conflicts.map(name => (
        <div key={name} style={{ ...monoStyle, color: 'var(--fg-2)', fontSize: 11 }}>• {name}</div>
      ))}
    </div>
  );
}
