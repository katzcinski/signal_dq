// Kompilieren / Dry-Run / BDC-Export / Revert. Der Compiler erzeugt das SQL aus
// den Garantien (G1) — der Vertrag selbst enthält kein SQL.
import { useState } from 'react';
import {
  useCompileContractDryRun, useDryRunChecks, useRevertChecks, useExportBdc,
} from '@/api/contracts';
import { useOperationStream } from '@/api/operations';
import { OperationProgress } from '@/components/OperationProgress';
import { StatePill } from '@/components/ui/StatePill';
import { Button } from '@/components/ui/Button';
import { t } from '@/i18n/de';
import { cardStyle, monoStyle, ConflictList } from './shared';
import type { CheckState } from '@/types';

export function CompilePanel({ objectId, dataset }: { objectId: string; dataset: string }) {
  const compile = useCompileContractDryRun(objectId);
  const dryRun = useDryRunChecks(dataset);
  const revert = useRevertChecks(dataset);
  const exportBdc = useExportBdc(objectId);
  const [showRevertConfirm, setShowRevertConfirm] = useState(false);
  const [activeTab, setActiveTab] = useState<'preview' | 'dryrun' | 'export'>('preview');
  const [dryRunOpId, setDryRunOpId] = useState<string | null>(null);
  const { data: dryRunOperation } = useOperationStream<{
    mode?: string; overall_status?: string; total?: number; passed?: number; failed?: number;
    results?: { name: string; passed: boolean; actual_value: unknown; expect: string; state: CheckState }[];
    message?: string; checks_yaml?: string;
  }>(dryRunOpId);

  const compileData = compile.data as {
    yaml_preview?: string; conflicts?: string[]; determinism_hash?: string;
    checks?: { name: string; type: string; expect: string; severity: string }[];
  } | undefined;
  const dryRunData = (dryRunOperation?.state === 'finished' ? dryRunOperation.result : dryRun.data) as {
    mode?: string; overall_status?: string; total?: number; passed?: number; failed?: number;
    results?: { name: string; passed: boolean; actual_value: unknown; expect: string; state: CheckState }[];
    message?: string; checks_yaml?: string; op_id?: string;
  } | undefined;
  const dryRunRunning = dryRun.isPending || dryRunOperation?.state === 'running';

  const tabStyle = (tabKey: string): React.CSSProperties => ({
    padding: '5px 14px', fontSize: 12, cursor: 'pointer', background: 'none', border: 'none',
    borderBottom: activeTab === tabKey ? '2px solid var(--cont)' : '2px solid transparent',
    color: activeTab === tabKey ? 'var(--fg)' : 'var(--fg-3)',
  });

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 'var(--s2)' }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{t.workbench.compile.title}</div>
        <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap' }}>
          <Button variant="primary" onClick={() => { compile.mutate(); setActiveTab('preview'); }} pending={compile.isPending} pendingLabel={t.workbench.compile.compiling}>
            {t.workbench.compile.compileDry}
          </Button>
          <Button variant="ghost" pending={dryRunRunning} pendingLabel={t.workbench.compile.running} onClick={() => {
            setDryRunOpId(null);
            dryRun.mutate({}, {
              onSuccess: data => {
                const opId = (data as { op_id?: string })?.op_id;
                if (opId) setDryRunOpId(opId);
              },
            });
            setActiveTab('dryrun');
          }}>
            {t.workbench.compile.runChecks}
          </Button>
          <Button variant="ghost" onClick={() => { exportBdc.mutate(); setActiveTab('export'); }}>{t.workbench.compile.bdcExport}</Button>
          <Button variant="danger" onClick={() => setShowRevertConfirm(true)}>{t.workbench.compile.revert}</Button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', marginBottom: 12 }}>
        <button style={tabStyle('preview')} onClick={() => setActiveTab('preview')}>{t.workbench.compile.preview}</button>
        <button style={tabStyle('dryrun')} onClick={() => setActiveTab('dryrun')}>{t.workbench.compile.dryRun}</button>
        <button style={tabStyle('export')} onClick={() => setActiveTab('export')}>{t.workbench.compile.bdcExport}</button>
      </div>

      {activeTab === 'preview' && compileData && (
        <div>
          {compileData.determinism_hash && (
            <div style={{ ...monoStyle, fontSize: 11, color: 'var(--fg-3)', marginBottom: 8 }}>
              {t.workbench.compile.hash}: {compileData.determinism_hash}
            </div>
          )}
          <ConflictList conflicts={compileData.conflicts ?? []} />
          {compileData.checks && (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8, fontSize: 12 }}>
              <thead>
                <tr style={{ color: 'var(--fg-3)', textAlign: 'left' }}>
                  <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.check}</th>
                  <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.type}</th>
                  <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.expect}</th>
                  <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.common.severity}</th>
                </tr>
              </thead>
              <tbody>
                {compileData.checks.map(c => (
                  <tr key={c.name} style={{ borderTop: '1px solid var(--line)' }}>
                    <td style={{ padding: 'var(--s1) var(--s2)', ...monoStyle }}>{c.name}</td>
                    <td style={{ padding: 'var(--s1) var(--s2)', color: 'var(--fg-3)' }}>{c.type}</td>
                    <td style={{ padding: 'var(--s1) var(--s2)', ...monoStyle }}>{c.expect}</td>
                    <td style={{ padding: 'var(--s1) var(--s2)', color: 'var(--fg-2)' }}>{c.severity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {compileData.yaml_preview && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--fg-3)' }}>
                {t.workbench.compile.yamlPreview} <span style={monoStyle}>checks/{dataset}/checks.yml</span>
              </summary>
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 6, fontStyle: 'italic' }}>
                {t.workbench.compile.yamlPreviewHint}
              </div>
              <pre style={{ ...monoStyle, background: 'var(--bg-2)', padding: 'var(--s3)', borderRadius: 'var(--r-md)', marginTop: 6, overflow: 'auto', maxHeight: 300, fontSize: 11 }}>
                {compileData.yaml_preview}
              </pre>
            </details>
          )}
        </div>
      )}

      {activeTab === 'dryrun' && (
        <div>
          {dryRunOperation && <OperationProgress operation={dryRunOperation} />}
          {dryRunData?.mode === 'compile_only' ? (
            <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>{dryRunData.message}</div>
          ) : dryRunData ? (
            <div>
              <div style={{ display: 'flex', gap: 'var(--s6)', marginBottom: 12 }}>
                <span style={{ fontSize: 13 }}>{t.workbench.compile.statusLabel} <strong style={{ color: dryRunData.overall_status === 'pass' ? 'var(--status-ok)' : 'var(--status-fail)' }}>{dryRunData.overall_status}</strong></span>
                <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>{dryRunData.passed}/{dryRunData.total} {t.workbench.compile.passedOf}</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: 'var(--fg-3)', textAlign: 'left' }}>
                    <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.check}</th>
                    <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.actual}</th>
                    <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.expect}</th>
                    <th style={{ padding: 'var(--s1) var(--s2)' }}>{t.workbench.compile.state}</th>
                  </tr>
                </thead>
                <tbody>
                  {(dryRunData.results ?? []).map((r) => (
                    <tr key={r.name} style={{ borderTop: '1px solid var(--line)' }}>
                      <td style={{ padding: 'var(--s1) var(--s2)', ...monoStyle }}>{r.name}</td>
                      <td style={{ padding: 'var(--s1) var(--s2)', ...monoStyle }}>{String(r.actual_value ?? '—')}</td>
                      <td style={{ padding: 'var(--s1) var(--s2)', ...monoStyle }}>{r.expect}</td>
                      <td style={{ padding: 'var(--s1) var(--s2)' }}>
                        {r.state && r.state !== 'executed' ? (
                          <StatePill state={r.state} size="sm" />
                        ) : (
                          <span style={{ color: r.passed ? 'var(--status-ok)' : 'var(--status-fail)' }}>
                            {r.passed ? 'pass' : 'fail'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      )}

      {activeTab === 'export' && exportBdc.data && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8 }}>{t.workbench.compile.csn}</div>
          <pre style={{ ...monoStyle, background: 'var(--bg-2)', padding: 'var(--s3)', borderRadius: 'var(--r-md)', overflow: 'auto', maxHeight: 200, fontSize: 11 }}>
            {JSON.stringify((exportBdc.data as { csn_fragment: unknown }).csn_fragment, null, 2)}
          </pre>
          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8, marginTop: 12 }}>{t.workbench.compile.ord}</div>
          <pre style={{ ...monoStyle, background: 'var(--bg-2)', padding: 'var(--s3)', borderRadius: 'var(--r-md)', overflow: 'auto', maxHeight: 200, fontSize: 11 }}>
            {JSON.stringify((exportBdc.data as { ord_fragment: unknown }).ord_fragment, null, 2)}
          </pre>
        </div>
      )}

      {compile.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 8 }}>{t.workbench.compile.compileFailed}</div>}
      {dryRun.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 8 }}>{t.workbench.compile.dryRunFailed}</div>}

      {/* Revert confirmation */}
      {showRevertConfirm && (
        <div style={{ marginTop: 12, background: 'var(--status-fail)22', border: '1px solid var(--status-fail)', borderRadius: 'var(--r-md)', padding: 14 }}>
          <div style={{ fontSize: 13, marginBottom: 10 }}>{t.workbench.compile.revertConfirm} <strong style={monoStyle}>checks/{dataset}/checks.yml</strong></div>
          <div style={{ display: 'flex', gap: 'var(--s2)' }}>
            <Button variant="danger" pending={revert.isPending} pendingLabel={t.workbench.compile.reverting} onClick={() => { revert.mutate(); setShowRevertConfirm(false); }}>
              {t.workbench.compile.revertConfirmBtn}
            </Button>
            <Button variant="ghost" onClick={() => setShowRevertConfirm(false)}>{t.common.cancel}</Button>
          </div>
          {revert.isSuccess && (
            <div style={{ color: 'var(--status-ok)', fontSize: 12, marginTop: 8 }}>
              {t.workbench.compile.revertedTo} {(revert.data as { reverted_to_commit?: string })?.reverted_to_commit?.slice(0, 8)}
            </div>
          )}
          {revert.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 8 }}>{t.workbench.compile.revertFailed}</div>}
        </div>
      )}
    </div>
  );
}
