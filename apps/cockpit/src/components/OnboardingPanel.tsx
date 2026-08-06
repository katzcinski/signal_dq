import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useExtract } from '@/api/objects';
import { useInventory, useSeedContract, useDryRunChecks } from '@/api/contracts';
import { t } from '@/i18n/de';
import type { InventoryDataset } from '@/types';

const datasetId = (d: InventoryDataset): string =>
  String(d.id ?? d.technicalName ?? d.name ?? '');

function StepCard({ step, title, desc, done, locked, children }: {
  step: number;
  title: string;
  desc: string;
  done: boolean;
  locked: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div style={{
      display: 'flex', gap: 14, padding: 'var(--s4)',
      background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
      opacity: locked ? 0.45 : 1,
    }}>
      <div aria-hidden style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: done ? 'var(--status-ok)' : 'var(--bg-3)',
        border: done ? 'none' : '1px solid var(--line-2)',
        color: done ? '#fff' : 'var(--fg-2)', fontSize: 13, fontWeight: 600,
      }}>
        {done ? '✓' : step}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>
          {title}
          {done && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--status-ok)' }}>{t.onboarding.done}</span>}
        </div>
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: locked ? 0 : 10 }}>{desc}</div>
        {!locked && children}
      </div>
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: 'var(--cont)', color: '#fff', border: 'none',
  borderRadius: 'var(--r-md)', padding: '6px 14px', fontSize: 13,
};

// U4 onboarding: empty tenant → Extract → Seed → Dry-Run → first run.
export function OnboardingPanel() {
  const extract = useExtract();
  const inventory = useInventory();
  const seed = useSeedContract();
  const [seededId, setSeededId] = useState('');
  const [pick, setPick] = useState('');
  const dryRun = useDryRunChecks(seededId);

  const extractDone = extract.isSuccess;
  const seedDone = seed.isSuccess && !!seededId;
  const dryRunDone = dryRun.isSuccess;

  const datasets = inventory.data?.datasets ?? [];

  const extractCounts = extract.data
    ? Object.entries(extract.data).filter(([, v]) => typeof v === 'number') as [string, number][]
    : [];

  const dryRunData = dryRun.data as { total?: number; passed?: number; failed?: number } | undefined;

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', display: 'flex', flexDirection: 'column', gap: 'var(--s3)' }}>
      <div>
        <h2 style={{ fontSize: 17, fontWeight: 700 }}>{t.onboarding.title}</h2>
        <p style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>{t.onboarding.intro}</p>
      </div>

      <StepCard step={1} title={t.onboarding.step1Title} desc={t.onboarding.step1Desc} done={extractDone} locked={false}>
        {!extractDone && (
          <button style={btnStyle} disabled={extract.isPending} onClick={() => extract.mutate({})}>
            {extract.isPending ? t.common.loading : t.onboarding.step1Button}
          </button>
        )}
        {extract.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 6 }}>{t.onboarding.failedAction}</div>}
        {extractDone && extractCounts.length > 0 && (
          <div style={{ fontSize: 12, color: 'var(--fg-2)', fontFamily: 'var(--font-mono)' }}>
            {extractCounts.map(([k, v]) => `${k}: ${v}`).join(' · ')}
          </div>
        )}
      </StepCard>

      <StepCard step={2} title={t.onboarding.step2Title} desc={t.onboarding.step2Desc} done={seedDone} locked={!extractDone}>
        {!seedDone && (
          <div style={{ display: 'flex', gap: 'var(--s2)', alignItems: 'center' }}>
            <select
              value={pick}
              onChange={e => setPick(e.target.value)}
              style={{
                background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)',
                borderRadius: 'var(--r-md)', padding: '6px 10px', fontSize: 12, minWidth: 220,
              }}
            >
              <option value="">{t.onboarding.step2Pick}</option>
              {datasets.map(d => {
                const id = datasetId(d);
                return <option key={id} value={id}>{d.name ?? d.technicalName ?? id}</option>;
              })}
            </select>
            <button
              style={btnStyle}
              disabled={!pick || seed.isPending}
              onClick={() => seed.mutate(pick, { onSuccess: () => setSeededId(pick) })}
            >
              {seed.isPending ? t.workbench.seeding : t.onboarding.step2Button}
            </button>
          </div>
        )}
        {seed.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 6 }}>{t.onboarding.failedAction}</div>}
        {seedDone && <div style={{ fontSize: 12, color: 'var(--fg-2)', fontFamily: 'var(--font-mono)' }}>{seededId}</div>}
      </StepCard>

      <StepCard step={3} title={t.onboarding.step3Title} desc={t.onboarding.step3Desc} done={dryRunDone} locked={!seedDone}>
        {!dryRunDone && (
          <button style={btnStyle} disabled={dryRun.isPending} onClick={() => dryRun.mutate({})}>
            {dryRun.isPending ? t.common.loading : t.onboarding.step3Button}
          </button>
        )}
        {dryRun.isError && <div style={{ color: 'var(--status-fail)', fontSize: 12, marginTop: 6 }}>{t.onboarding.failedAction}</div>}
        {dryRunDone && dryRunData && (
          <div style={{ fontSize: 12 }}>
            <span style={{ color: 'var(--status-ok)' }}>{dryRunData.passed ?? 0} {t.onboarding.passed}</span>
            {' · '}
            <span style={{ color: 'var(--status-fail)' }}>{dryRunData.failed ?? 0} {t.onboarding.failed}</span>
          </div>
        )}
      </StepCard>

      <StepCard step={4} title={t.onboarding.step4Title} desc={t.onboarding.step4Desc} done={false} locked={!dryRunDone}>
        <Link to={`/objects/${seededId}`} style={{ color: 'var(--cont)', fontSize: 13 }}>
          {t.onboarding.step4Link}
        </Link>
      </StepCard>
    </div>
  );
}
