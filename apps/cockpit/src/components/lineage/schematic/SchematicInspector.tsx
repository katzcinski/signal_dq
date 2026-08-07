/**
 * Rechter Inspector des Schaltplan-Boards: Objekt-Detail oder — bei getracter
 * Spalte — Column-Detail inkl. Transformations-Expression als Codeblock,
 * Reichweite, DQ-Status und Contract-Binding. Präsentational, leitet alles aus
 * dem Modell ab.
 */
import { t } from '@/i18n/de';
import type { CSSProperties, ReactNode } from 'react';
import type { SchematicChip, SchematicModel } from './model';
import { dqStatusColor } from './theme';

const S = t.lineage.schematic;

export interface InspectorSelection {
  node: string;
  pin?: string;
}

export function SchematicInspector({
  model,
  selection,
}: {
  model: SchematicModel;
  selection: InspectorSelection | null;
}) {
  if (!selection) {
    return <div style={emptyStyle}>{S.inspectorEmpty}</div>;
  }
  const chip = model.chips.find(c => c.id === selection.node);
  if (!chip) return <div style={emptyStyle}>{S.inspectorEmpty}</div>;

  return selection.pin
    ? <ColumnDetail model={model} chip={chip} pin={selection.pin} />
    : <ObjectDetail model={model} chip={chip} />;
}

function ObjectDetail({ model, chip }: { model: SchematicModel; chip: SchematicChip }) {
  const upstream = new Set(model.edges.filter(e => e.toNode === chip.id).map(e => e.fromNode));
  const downstream = new Set(model.edges.filter(e => e.fromNode === chip.id).map(e => e.toNode));

  return (
    <div>
      <div style={eyebrow}>{`${chip.layer}${chip.system ? ` · ${chip.system}` : ''}`}</div>
      <div style={titleStyle}>{chip.label}</div>
      <DqBadge status={chip.dqStatus} />
      <ContractBadges chip={chip} />

      <Section label={S.object}>
        <Row k={S.layer} v={chip.layer} />
        {chip.system && <Row k={S.system} v={chip.system} />}
        {chip.space && <Row k={S.space} v={chip.space} />}
        <Row k={S.columns} v={String(chip.pins.length)} />
      </Section>

      <Section label={S.lineage}>
        <Row k={S.upstreamObjects} v={String(upstream.size)} />
        <Row k={S.downstreamObjects} v={String(downstream.size)} />
      </Section>
    </div>
  );
}

function ColumnDetail({ model, chip, pin }: { model: SchematicModel; chip: SchematicChip; pin: string }) {
  const pinMeta = chip.pins.find(p => p.id === pin);
  const incoming = model.edges.filter(e => e.toNode === chip.id && e.toPin === pin);
  const outgoing = model.edges.filter(e => e.fromNode === chip.id && e.fromPin === pin);

  return (
    <div>
      <div style={eyebrow}>{chip.label}</div>
      <div style={titleStyle}>{pin}</div>
      {pinMeta?.dataType && <div style={subStyle}>{pinMeta.dataType}</div>}

      {incoming.length > 0 && (
        <Section label={S.transformation}>
          {incoming.map(e => (
            <div key={e.id}>
              <Row k={e.kind === 'derived' ? S.derived : S.directFrom} v={`${e.fromNode}.${e.fromPin}`} />
              {e.kind === 'derived' && e.expression && <pre style={codeBlock}>{e.expression}</pre>}
            </div>
          ))}
        </Section>
      )}

      <Section label={S.reach}>
        <Row k={S.directUpstream} v={String(incoming.length)} />
        <Row k={S.directDownstream} v={String(outgoing.length)} />
      </Section>

      {chip.dqStatus && (
        <Section label={S.qualityChecks}>
          <DqBadge status={chip.dqStatus} />
        </Section>
      )}

      {(chip.hasContract || chip.hasBoundaryContract) && (
        <Section label={S.contractBinding}>
          <ContractBadges chip={chip} />
        </Section>
      )}
    </div>
  );
}

// ---- kleine Bausteine ----

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={sectionStyle}>
      <div style={sectionLabel}>{label}</div>
      {children}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={rowStyle}>
      <span>{k}</span>
      <strong style={{ color: 'var(--fg)', fontWeight: 500, textAlign: 'right' }}>{v}</strong>
    </div>
  );
}

function DqBadge({ status }: { status?: string }) {
  if (!status) return null;
  const label =
    status === 'pass' ? S.dqPass
    : status === 'warn' ? S.dqWarn
    : status === 'fail' || status === 'critical' ? S.dqFail
    : S.dqUnknown;
  return (
    <span style={{ ...badge, color: dqStatusColor(status), background: 'var(--bg-3)' }}>
      <span style={{ ...dot, background: dqStatusColor(status) }} />
      {label}
    </span>
  );
}

function ContractBadges({ chip }: { chip: SchematicChip }) {
  if (!chip.hasContract && !chip.hasBoundaryContract) return null;
  return (
    <span style={{ ...badge, color: 'var(--cont)', background: 'var(--bg-3)' }}>
      <span style={{ ...dot, background: 'var(--cont)' }} />
      {chip.hasBoundaryContract ? S.boundaryContract : S.contractBound}
    </span>
  );
}

const emptyStyle: CSSProperties = {
  color: 'var(--fg-3)', fontSize: 13, lineHeight: 1.6, marginTop: 48, textAlign: 'center', padding: '0 var(--s3)',
};
const eyebrow: CSSProperties = {
  fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600,
};
const titleStyle: CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 14.5, fontWeight: 600, color: 'var(--fg)', margin: '3px 0 8px', wordBreak: 'break-all',
};
const subStyle: CSSProperties = { fontSize: 12, color: 'var(--fg-2)', marginBottom: 10, fontFamily: 'var(--font-mono)' };
const sectionStyle: CSSProperties = { marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--line)' };
const sectionLabel: CSSProperties = {
  fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: 6,
};
const rowStyle: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: 'var(--fg-2)', marginBottom: 6, gap: 'var(--s2)',
};
const codeBlock: CSSProperties = {
  background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '10px 11px',
  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--qual)', lineHeight: 1.5, whiteSpace: 'pre-wrap',
  wordBreak: 'break-word', margin: '4px 0 0',
};
const badge: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, padding: '3px 8px',
  borderRadius: 'var(--r-full)', marginRight: 6, marginBottom: 6,
};
const dot: CSSProperties = { width: 6, height: 6, borderRadius: '50%' };
