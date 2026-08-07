// Breaking-Diff gegen die aktive Version. Zeigt Änderungen und den G3-Hinweis
// (Ceremony / Blocking) — nur Darstellung, die Gate-Logik lebt im EditorPane.
import { t } from '@/i18n/de';
import { cardStyle, monoStyle } from './shared';
import type { DiffEntry } from '@/types';

export function BreakingDiffPanel({ entries, pending, isError, blocking, ceremonyRequired }: {
  entries: DiffEntry[];
  pending: boolean;
  isError: boolean;
  blocking: boolean;
  ceremonyRequired: boolean;
}) {
  const isBreaking = (e: DiffEntry) => e.breaking === true || /breaking/i.test(e.kind);
  const hasBreaking = entries.some(isBreaking);
  return (
    <div style={cardStyle}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>{t.workbench.diffTitle}</div>
      {!ceremonyRequired && (
        <div style={{
          marginBottom: 10, padding: 'var(--s2) var(--s3)', borderRadius: 'var(--r-md)',
          background: 'var(--bg-2)', border: '1px solid var(--line)',
          color: 'var(--fg-2)', fontSize: 12,
        }}>
          <div style={{ fontWeight: 600 }}>{t.workbench.gateNoCeremony}</div>
          <div style={{ marginTop: 3, color: 'var(--fg-3)' }}>{t.workbench.gateChangeHint}</div>
        </div>
      )}
      {pending && <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.workbench.diffPending}</div>}
      {isError && <div style={{ fontSize: 12, color: 'var(--status-fail)' }}>{t.workbench.diffError}</div>}
      {!pending && !isError && entries.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.workbench.diffEmpty}</div>
      )}
      {entries.map((e, i) => (
        <div key={i} style={{
          display: 'flex', gap: 'var(--s2)', alignItems: 'baseline', padding: 'var(--s1) 0',
          borderBottom: '1px solid var(--line)', fontSize: 12, flexWrap: 'wrap',
        }}>
          <span style={{
            color: isBreaking(e) ? 'var(--status-crit)' : 'var(--fg-2)',
            fontWeight: isBreaking(e) ? 700 : 400, minWidth: 110,
          }}>
            {isBreaking(e) && '⛔ '}{e.kind}
          </span>
          <span style={{ ...monoStyle, fontSize: 11, color: 'var(--fg-3)' }}>{e.path}</span>
          {(e.old !== undefined || e.new !== undefined) && (
            <span style={{ ...monoStyle, fontSize: 11 }}>
              <span style={{ color: 'var(--status-fail)' }}>{e.old !== undefined ? JSON.stringify(e.old) : '∅'}</span>
              {' → '}
              <span style={{ color: 'var(--status-ok)' }}>{e.new !== undefined ? JSON.stringify(e.new) : '∅'}</span>
            </span>
          )}
        </div>
      ))}
      {!ceremonyRequired && hasBreaking && (
        <div style={{
          marginTop: 10, padding: 'var(--s2) var(--s3)', borderRadius: 'var(--r-md)',
          background: 'var(--status-warn)22', border: '1px solid var(--status-warn)',
          color: 'var(--fg-2)', fontSize: 12, fontWeight: 600,
        }}>
          {t.workbench.breakingInfoGate}
        </div>
      )}
      {blocking && (
        <div style={{
          marginTop: 10, padding: 'var(--s2) var(--s3)', borderRadius: 'var(--r-md)',
          background: 'var(--status-crit)22', border: '1px solid var(--status-crit)',
          color: 'var(--status-crit)', fontSize: 12, fontWeight: 600,
        }}>
          {t.workbench.breakingBlocked}
        </div>
      )}
    </div>
  );
}
