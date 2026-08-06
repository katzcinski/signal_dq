import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { dump } from 'js-yaml';
import type { AxiosError } from 'axios';
import { toast } from 'sonner';
import {
  useContracts, useContract, usePutContract, useApproveContract, useDeprecateContract,
  useDiffContract, useInventory, useCertifyContract, usePromoteContract, useObservedReality,
} from '@/api/contracts';
import { LifecycleStepper } from '@/components/LifecycleStepper';
import { SchemaDriftBanner } from '@/components/SchemaDriftBanner';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { OwnershipTag } from '@/components/ui/OwnershipTag';
import { Tooltip } from '@/components/ui/Tooltip';
import { Button } from '@/components/ui/Button';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { t } from '@/i18n/de';
import { useRoleStore, canWriteContract } from '@/store/role';
import {
  cardStyle, monoStyle, datasetName, sectionOfKind, toPutBody, majorOf, extractValidationErrors,
  FrameTag, type Section,
} from '@/components/workbench/shared';
import { GuaranteeEditor } from '@/components/workbench/GuaranteeEditor';
import { CheckBuilder } from '@/components/workbench/CheckBuilder';
import { CompilePanel } from '@/components/workbench/CompilePanel';
import { BacktestPanel } from '@/components/workbench/BacktestPanel';
import { BreakingDiffPanel } from '@/components/workbench/BreakingDiffPanel';
import { SlaBars } from '@/components/workbench/SlaBars';
import { ContractList } from '@/components/workbench/ContractList';
import { WorkbenchHero, type HeroChip, type HeroFact } from '@/components/workbench/WorkbenchHero';
import { Vertragsblatt, type PathStep } from '@/components/workbench/Vertragsblatt';
import { ObservedSlot } from '@/components/workbench/ObservedSlot';
import { MinerSuggestions } from '@/components/workbench/MinerSuggestions';
import type { ArtifactKind, ContractPutBody, DiffEntry, ObservedGuarantee } from '@/types';

const cleanVersion = (v: string | undefined): string => `v${String(v ?? '').replace(/^v/i, '')}`;

// Zweistufige Navigation (§4): Gruppen + Untertabs, beide URL-getrieben.
type NavTab = 'definition' | 'checkDiff' | 'operations';
type DefTab = 'guarantees' | 'builder' | 'metadata';
const NAV_TABS: NavTab[] = ['definition', 'checkDiff', 'operations'];

// ─── Editor pane ─────────────────────────────────────────────────────────────

function EditorPane({ product, onPromote, promotePending }: {
  product: string;
  onPromote: () => void;
  promotePending: boolean;
}) {
  const { data: contract, isLoading, isError, refetch } = useContract(product);
  const put = usePutContract(product);
  const certify = useCertifyContract(product);
  const approve = useApproveContract(product);
  const deprecate = useDeprecateContract(product);
  const diff = useDiffContract(product);
  const inventory = useInventory();
  const observed = useObservedReality(product);
  const role = useRoleStore(s => s.role);

  // Beobachtete Realität je Garantie-Familie (letzter Messwert, Sparkline, PASS/FAIL).
  const observedByFamily = useMemo(() => {
    const m: Record<string, ObservedGuarantee> = {};
    for (const g of observed.data?.guarantees ?? []) m[g.family] = g;
    return m;
  }, [observed.data]);

  const [draft, setDraft] = useState<ContractPutBody | null>(null);
  const [confirmAction, setConfirmAction] = useState<'release' | 'deprecate' | null>(null);
  const [navTab, setNavTab] = useSearchParamState('wtab', 'definition');
  const [defTab, setDefTab] = useSearchParamState('wsub', 'guarantees');
  const tab = (NAV_TABS as string[]).includes(navTab) ? (navTab as NavTab) : 'definition';

  // Initialize the draft from the (full) contract; re-key on product change.
  useEffect(() => {
    if (contract && (!draft || draft.product !== contract.product)) {
      setDraft(toPutBody(contract));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contract, product]);

  const draftJson = useMemo(() => draft ? JSON.stringify(draft) : '', [draft]);
  const draftKind = draft?.kind ?? contract?.kind ?? 'internal_gate';
  const savedJson = useMemo(() => contract ? JSON.stringify(toPutBody(contract)) : '', [contract]);
  const dirty = draftJson !== '' && draftJson !== savedJson;

  // BreakingDiffPanel: re-diff on every draft change, debounced.
  const diffMutate = diff.mutate;
  useEffect(() => {
    if (!draft) return;
    const timer = setTimeout(() => diffMutate(JSON.parse(draftJson) as ContractPutBody), 600);
    return () => clearTimeout(timer);
  }, [draftJson, diffMutate, draft]);

  // Inventory-backed picker sources.
  const datasets = useMemo(() => inventory.data?.datasets ?? [], [inventory.data]);
  const datasetOptions = useMemo(
    () => [...new Set(datasets.map(datasetName).filter(Boolean))].sort(),
    [datasets],
  );
  const columnsOfDataset = useMemo(() => (name: string): string[] => {
    if (!name) return [];
    const ds = datasets.find(d =>
      datasetName(d) === name || String(d.id ?? '') === name || String(d.name ?? '') === name);
    return (ds?.columns ?? []).map(c => c.name).filter(Boolean);
  }, [datasets]);
  const columnOptions = useMemo(() => {
    const own = columnsOfDataset(draft?.dataset ?? '');
    if (own.length > 0) return own;
    // Fallback: union of all known columns so the picker is never a dead end.
    return [...new Set(datasets.flatMap(d => (d.columns ?? []).map(c => c.name)))].sort();
  }, [columnsOfDataset, draft?.dataset, datasets]);

  const lifecycle = contract?.lifecycle ?? 'draft';
  const report = diff.data;
  const reportedActiveVersion = report && !Array.isArray(report)
    ? (typeof report.active_version === 'string' ? report.active_version
      : typeof report.from_version === 'string' ? report.from_version
      : undefined)
    : undefined;
  const hasActiveBaseline = contract?.certified === true || !!reportedActiveVersion;
  const canReleaseDraft = lifecycle === 'draft' && draftKind !== 'internal_gate' && hasActiveBaseline;

  if (isLoading || !draft) {
    return <EditorSkeleton />;
  }
  if (isError) {
    return <div style={{ flex: 1, padding: 'var(--s6)' }}><ErrorBanner onRetry={() => refetch()} /></div>;
  }

  // [AUTHZ] FE mirror of can_write_contract_data — server stays authoritative on PUT.
  const canWrite = canWriteContract(role, contract?.owned_by);
  const writeTitle = canWrite ? undefined : t.role.noWriteContract;

  // Breaking gate (G3): breaking diff + draft major ≤ active major ⇒ block approve.
  const entries: DiffEntry[] = Array.isArray(report)
    ? report as unknown as DiffEntry[]
    : (report?.entries ?? []);
  const hasBreaking = entries.some(e => e.breaking === true || /breaking/i.test(e.kind))
    || (!!report && !Array.isArray(report) && report.breaking === true);
  const activeVersion = reportedActiveVersion || contract?.version;
  const ceremonyRequired = report && !Array.isArray(report) && typeof report.ceremony_required === 'boolean'
    ? report.ceremony_required
    : draft.kind !== 'internal_gate';
  const ceremonyBreaking = report && !Array.isArray(report) && typeof report.blocking === 'boolean'
    ? report.blocking
    : ceremonyRequired && hasBreaking;
  const breakingBlocked = ceremonyBreaking && majorOf(draft.version) <= majorOf(String(activeVersion));

  const validationErrors = [
    ...(put.isError ? extractValidationErrors(put.error) : []),
    ...(certify.isError ? extractValidationErrors(certify.error) : []),
  ];

  const yamlPreview = (() => {
    try {
      return dump(JSON.parse(draftJson), { lineWidth: 100, noRefs: true });
    } catch {
      return '';
    }
  })();

  const draftBody = () => JSON.parse(draftJson) as ContractPutBody;

  const handleConfirmAction = () => {
    const action = confirmAction;
    setConfirmAction(null);
    if (action === 'release') approve.mutate();
    if (action === 'deprecate') deprecate.mutate();
  };

  const versionLabel = cleanVersion(draft.version);
  const primaryAction = (() => {
    if (draftKind === 'internal_gate' || (lifecycle === 'draft' && !hasActiveBaseline)) {
      return {
        kind: 'activate' as const,
        label: t.workbench.activate,
        pendingLabel: t.workbench.activating,
        pending: certify.isPending,
        disabled: !canWrite || certify.isPending,
        title: writeTitle,
        variant: 'primary' as const,
        onClick: () => certify.mutate(draftBody()),
      };
    }
    if (canReleaseDraft) {
      return {
        kind: 'release' as const,
        label: `${t.workbench.release} (${versionLabel})`,
        pendingLabel: t.workbench.releasing,
        pending: approve.isPending,
        disabled: !canWrite || breakingBlocked || approve.isPending,
        title: !canWrite ? writeTitle : breakingBlocked ? t.workbench.breakingBlocked : undefined,
        variant: 'primary' as const,
        onClick: () => setConfirmAction('release'),
      };
    }
    if (lifecycle === 'active') {
      return {
        kind: 'deprecate' as const,
        label: t.workbench.deprecate,
        pendingLabel: t.workbench.deprecating,
        pending: deprecate.isPending,
        disabled: !canWrite || deprecate.isPending,
        title: writeTitle,
        variant: 'danger' as const,
        onClick: () => setConfirmAction('deprecate'),
      };
    }
    return null;
  })();

  // ─── Hero ────────────────────────────────────────────────────────────────
  const isInternal = draftKind === 'internal_gate';
  const chips: HeroChip[] = [
    { label: isInternal ? t.workbench.frameInternal : t.workbench.frameContract, tone: isInternal ? 'var(--qual)' : 'var(--cont)' },
  ];
  if (hasActiveBaseline && activeVersion) {
    chips.push({ label: `${t.lifecycle.active} · ${cleanVersion(String(activeVersion))}`, tone: 'var(--status-ok)', subtle: true });
  }
  if (lifecycle === 'draft' || dirty) {
    chips.push({ label: `${t.lifecycle.draft} · ${versionLabel}`, tone: 'var(--status-warn)', subtle: true });
  }
  const meta = [contract?.owned_by, draft.dataset].filter(Boolean) as string[];
  const enabledGuarantees = Object.entries(draft.guarantees ?? {}).filter(([, v]) => !!v).length;
  const facts: HeroFact[] = [
    { label: t.workbench.hero.factGuarantees, value: enabledGuarantees },
    { label: t.workbench.hero.factActiveVersion, value: activeVersion ? cleanVersion(String(activeVersion)) : '—' },
    { label: t.workbench.hero.factDraftVersion, value: versionLabel },
  ];

  const promoteMenu = isInternal && lifecycle !== 'deprecated' ? (
    <details style={{ position: 'relative' }}>
      <summary
        aria-label={t.workbench.moreActions}
        title={t.workbench.moreActions}
        style={{
          listStyle: 'none', width: 34, height: 32, padding: 0, cursor: 'pointer',
          display: 'grid', placeItems: 'center', fontSize: 18, lineHeight: 1,
          background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', color: 'var(--fg-2)',
        }}
      >
        ⋯
      </summary>
      <div style={{
        position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 10,
        minWidth: 220, background: 'var(--bg-1)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', padding: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
      }}>
        <Tooltip content={canWrite ? t.workbench.promoteHint : writeTitle} focusable={!canWrite} className="tooltip-full">
          <Button variant="ghost" disabled={!canWrite || promotePending} pending={promotePending} pendingLabel={t.workbench.promoting} onClick={onPromote} style={{ width: '100%' }}>
            {t.workbench.promote}
          </Button>
        </Tooltip>
      </div>
    </details>
  ) : null;

  const heroActions = (
    <>
      <Button variant="ghost" disabled={!dirty} onClick={() => contract && setDraft(toPutBody(contract))}>
        {t.workbench.hero.discard}
      </Button>
      <Button variant="secondary" onClick={() => setNavTab('checkDiff')}>{t.workbench.hero.dryRunStart}</Button>
      <Tooltip content={writeTitle} focusable={Boolean(writeTitle)}>
        <Button variant="primary" disabled={!canWrite || put.isPending} pending={put.isPending} pendingLabel={t.workbench.saving} onClick={() => put.mutate(draftBody())}>
          {t.workbench.hero.saveDraft}
        </Button>
      </Tooltip>
      {promoteMenu}
    </>
  );

  // ─── Vertragsblatt: Freigabepfad ───────────────────────────────────────────
  const steps: PathStep[] = [
    {
      key: 'saved', label: t.workbench.sheet.stepSaved,
      hint: dirty ? t.workbench.sheet.stepSavedHint : t.workbench.saved,
      status: dirty ? 'current' : 'done',
    },
    {
      key: 'validated', badge: 'G1', label: t.workbench.sheet.stepValidated,
      hint: validationErrors.length ? validationErrors[0] : t.workbench.sheet.stepValidatedHint,
      status: validationErrors.length ? 'blocked' : dirty ? 'pending' : 'done',
    },
    {
      key: 'compiled', label: t.workbench.sheet.stepCompiled,
      hint: t.workbench.sheet.stepCompiledHint, status: 'pending',
    },
    ...(ceremonyRequired ? [{
      key: 'breaking', badge: 'G3', label: t.workbench.sheet.stepBreaking,
      hint: t.workbench.sheet.stepBreakingHint,
      status: (breakingBlocked ? 'blocked' : hasBreaking ? 'current' : 'done') as PathStep['status'],
    }] : []),
    {
      key: 'activate', label: t.workbench.sheet.stepActivate,
      status: (primaryAction?.disabled ? 'blocked' : 'current') as PathStep['status'],
    },
  ];

  const sheetFooter = primaryAction ? (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
      <Tooltip content={primaryAction.title} focusable={Boolean(primaryAction.title && primaryAction.disabled)}>
        <Button
          variant={primaryAction.variant}
          disabled={primaryAction.disabled}
          pending={primaryAction.pending}
          pendingLabel={primaryAction.pendingLabel}
          onClick={primaryAction.onClick}
          style={{ width: '100%' }}
        >
          {primaryAction.label}
        </Button>
      </Tooltip>
      {primaryAction.disabled && primaryAction.kind === 'release' && (
        <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.workbench.sheet.activateLocked}</div>
      )}
    </div>
  ) : null;

  // ─── Tab content ───────────────────────────────────────────────────────────
  const subTab = (defTab as DefTab);
  const defContent = (
    <>
      <SubTabs
        value={subTab}
        onChange={setDefTab}
        showBuilder={isInternal}
      />
      {subTab === 'builder' && isInternal ? (
        <CheckBuilder
          checks={draft.checks ?? []}
          onChange={c => setDraft({ ...draft, checks: c })}
          columnOptions={columnOptions}
        />
      ) : subTab === 'metadata' ? (
        <MetadataPanel
          dataset={draft.dataset}
          kind={draftKind}
          ownedBy={contract?.owned_by}
          owners={contract?.owners}
          description={contract?.description}
        />
      ) : (
        <>
          <MinerSuggestions
            product={product}
            guarantees={draft.guarantees ?? {}}
            onApply={g => setDraft({ ...draft, guarantees: g })}
          />
          <GuaranteeEditor
            guarantees={draft.guarantees ?? {}}
            onChange={g => setDraft({ ...draft, guarantees: g })}
            columnOptions={columnOptions}
            datasetOptions={datasetOptions}
            columnsOfDataset={columnsOfDataset}
            observed={family => <ObservedSlot observed={observedByFamily[family]} />}
          />
        </>
      )}
      {validationErrors.length > 0 && (
        <div style={{ background: 'var(--status-fail)22', border: '1px solid var(--status-fail)', borderRadius: 'var(--r-md)', padding: 'var(--s2) var(--s3)' }}>
          <div style={{ color: 'var(--status-fail)', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{t.workbench.validationErrors}</div>
          {validationErrors.map((e, i) => <div key={i} style={{ color: 'var(--status-fail)', fontSize: 12 }}>• {e}</div>)}
        </div>
      )}
    </>
  );

  const checkDiffContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <CompilePanel objectId={product} dataset={draft.dataset || product} />
      <BacktestPanel product={product} draft={draft} />
      <BreakingDiffPanel
        entries={entries}
        pending={diff.isPending}
        isError={diff.isError}
        blocking={breakingBlocked}
        ceremonyRequired={ceremonyRequired}
      />
    </div>
  );

  const operationsContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', gap: 'var(--s4)', flexWrap: 'wrap' }}>
        <LifecycleStepper current={lifecycle} />
        <FrameTag internal={isInternal} />
        <OwnershipTag ownedBy={contract?.owned_by} />
        {(!contract?.owners || contract.owners.length === 0) && (
          <Tooltip content={t.role.ownersEmpty}>
            <span style={{ fontSize: 10, color: 'var(--status-warn)', whiteSpace: 'nowrap' }}>{'⚠'} {t.workbench.metadataTab.noOwners}</span>
          </Tooltip>
        )}
        <div style={{ flex: 1 }} />
        {lifecycle === 'active' && !isInternal && <SlaBars product={product} />}
      </div>
      <SchemaDriftBanner product={product} />
    </div>
  );

  const statusLine = (
    <div style={{ display: 'flex', gap: 'var(--s3)', flexWrap: 'wrap', minHeight: 16 }}>
      {put.isSuccess && <span style={{ color: 'var(--status-ok)', fontSize: 12 }}>{t.workbench.saved}</span>}
      {put.isError && validationErrors.length === 0 && <span style={{ color: 'var(--status-fail)', fontSize: 12 }}>{t.workbench.saveError}</span>}
      {certify.isSuccess && <span style={{ color: 'var(--status-ok)', fontSize: 12 }}>{t.workbench.certified}</span>}
      {certify.isError && validationErrors.length === 0 && <span style={{ color: 'var(--status-fail)', fontSize: 12 }}>{t.workbench.saveError}</span>}
      {approve.isError && <span style={{ color: 'var(--status-fail)', fontSize: 12 }}>{extractValidationErrors(approve.error).join(' · ') || t.common.error}</span>}
      {deprecate.isError && <span style={{ color: 'var(--status-fail)', fontSize: 12 }}>{t.common.error}</span>}
    </div>
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 'var(--s5)', gap: 14, overflowY: 'auto', minWidth: 0 }}>
      {!canWrite && <ReadOnlyBanner hint={t.role.noWriteContract} />}

      <WorkbenchHero title={product} chips={chips} meta={meta} facts={facts} unsaved={dirty} actions={heroActions} />
      {statusLine}

      {/* Attention-Band: Breaking-Change-Hinweis (G3). */}
      {ceremonyBreaking && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--s3)', flexWrap: 'wrap',
          background: 'color-mix(in srgb, var(--status-warn) 12%, transparent)',
          border: '1px solid var(--status-warn)', borderRadius: 'var(--r-lg)', padding: 'var(--s3) var(--s4)',
        }}>
          <span aria-hidden style={{ fontSize: 16 }}>⚠</span>
          <span style={{ fontSize: 13, color: 'var(--fg)', flex: 1 }}>
            {breakingBlocked ? t.workbench.breakingBlocked : t.workbench.breakingHint}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setNavTab('checkDiff')}>{t.workbench.diffTitle}</Button>
        </div>
      )}

      {confirmAction && (
        <div style={{ ...cardStyle, border: `1px solid ${confirmAction === 'deprecate' ? 'var(--status-fail)' : 'var(--cont)'}` }}>
          <div style={{ fontSize: 13, marginBottom: 10 }}>
            {confirmAction === 'deprecate' ? t.workbench.deprecateConfirm : t.workbench.approveConfirm}
          </div>
          <div style={{ display: 'flex', gap: 'var(--s2)' }}>
            <Button variant={confirmAction === 'deprecate' ? 'danger' : 'primary'} onClick={handleConfirmAction}>{t.common.confirm}</Button>
            <Button variant="ghost" onClick={() => setConfirmAction(null)}>{t.common.cancel}</Button>
          </div>
        </div>
      )}

      {/* Zweistufige Navigation */}
      <div style={{ display: 'flex', gap: 'var(--s1)', borderBottom: '1px solid var(--line)' }}>
        {NAV_TABS.map(key => (
          <button
            key={key}
            onClick={() => setNavTab(key)}
            style={{
              padding: 'var(--s2) var(--s4)', fontSize: 13, cursor: 'pointer', background: 'none', border: 'none',
              borderBottom: tab === key ? '2px solid var(--cont)' : '2px solid transparent',
              color: tab === key ? 'var(--fg)' : 'var(--fg-3)', fontWeight: tab === key ? 600 : 400,
            }}
          >
            {t.workbench.sections[key]}
          </button>
        ))}
      </div>

      <div className="workbench-body">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          {tab === 'definition' && defContent}
          {tab === 'checkDiff' && checkDiffContent}
          {tab === 'operations' && operationsContent}
        </div>
        <Vertragsblatt
          versionFrom={activeVersion ? cleanVersion(String(activeVersion)) : versionLabel}
          versionTo={versionLabel}
          majorRequired={breakingBlocked}
          yaml={yamlPreview}
          steps={steps}
          footer={sheetFooter}
        />
      </div>
    </div>
  );
}

// Untertabs der Definition-Gruppe.
function SubTabs({ value, onChange, showBuilder }: { value: DefTab; onChange: (v: DefTab) => void; showBuilder: boolean }) {
  const tabs: [DefTab, string][] = [
    ['guarantees', t.workbench.subtabs.guarantees],
    ...(showBuilder ? [['builder', t.workbench.subtabs.builder] as [DefTab, string]] : []),
    ['metadata', t.workbench.subtabs.metadata],
  ];
  return (
    <div style={{ display: 'flex', gap: 'var(--s4)', marginBottom: 4 }}>
      {tabs.map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            padding: '2px 0', fontSize: 12, cursor: 'pointer', background: 'none', border: 'none',
            borderBottom: value === key ? '2px solid var(--cont)' : '2px solid transparent',
            color: value === key ? 'var(--fg)' : 'var(--fg-3)', fontWeight: value === key ? 600 : 400,
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// Metadaten & Ports (read-only-Überblick).
function MetadataPanel({ dataset, kind, ownedBy, owners, description }: {
  dataset: string; kind: ArtifactKind; ownedBy?: string; owners?: string[]; description?: string;
}) {
  const row = (label: string, value: React.ReactNode) => (
    <div style={{ display: 'flex', gap: 'var(--s4)', padding: 'var(--s2) 0', borderBottom: '1px solid var(--line)' }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)', width: 130, flexShrink: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--fg)', minWidth: 0 }}>{value}</span>
    </div>
  );
  return (
    <div style={cardStyle}>
      {row(t.workbench.metadataTab.dataset, <span style={monoStyle}>{dataset || '—'}</span>)}
      {row(t.workbench.metadataTab.kind, kind === 'internal_gate' ? t.workbench.frameInternal : t.workbench.frameContract)}
      {row(t.workbench.metadataTab.ownedBy, ownedBy || '—')}
      {row(t.workbench.metadataTab.owners, owners && owners.length ? owners.join(', ') : t.workbench.metadataTab.noOwners)}
      {row(t.workbench.metadataTab.description, description || t.workbench.metadataTab.noDescription)}
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div style={{ flex: 1, padding: 'var(--s5)', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ ...cardStyle, height: 120 }}><div className="skeleton" style={{ width: 220, height: 24, borderRadius: 6 }} /></div>
      <div style={{ ...cardStyle, height: 300 }} />
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ContractWorkbench() {
  const contractsQuery = useContracts();
  const inventory = useInventory();
  const navigate = useNavigate();
  const [productParam, setProduct] = useSearchParamState('product');
  const [promoteProduct, setPromoteProduct] = useSearchParamState('promote');
  const [compileParam] = useSearchParamState('compile');
  const [sectionParam] = useSearchParamState('section');
  const [, setSearchParams] = useSearchParams();
  const promote = usePromoteContract();
  const handledPromoteRef = useRef('');

  // Frame + selection live in the URL together; update them in a single
  // navigation. Two separate setSearchParams calls in one tick clobber each other
  // (react-router does not compose functional updaters), so combine them here.
  const showInFrame = useCallback((next: Section, productId: string) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      params.delete('compile');
      params.delete('promote');
      if (productId) params.set('product', productId); else params.delete('product');
      if (next === 'contract') params.set('section', 'contract'); else params.delete('section');
      return params;
    }, { replace: true });
  }, [setSearchParams]);

  // Honor the legacy /contracts?compile={id} deep link.
  const product = productParam || compileParam;

  const contracts = contractsQuery.data ?? [];
  const hasContracts = contracts.some(
    c => c.kind === 'consumer_contract' || c.kind === 'provider_contract',
  );

  // The active frame follows the selected item's kind, so jump-ins from an object
  // and deep links always land in the right frame (a seeded gate → internal). With
  // nothing selected, the ?section= toggle decides; internal is the common default.
  const selected = contracts.find(c => c.product === product);
  const section: Section = selected ? sectionOfKind(selected.kind)
    : sectionParam === 'contract' ? 'contract' : 'internal';

  const runPromote = useCallback((target: string) => {
    promote.mutate(target, {
      onSuccess: promoted => {
        toast.success(t.lineage.promotionSuccess);
        handledPromoteRef.current = '';
        // Land the promoted contract in the contract frame, in place.
        showInFrame('contract', promoted.product);
      },
      onError: err => {
        const detail = (err as AxiosError<{ detail?: unknown }>)?.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : t.workbench.promotionFailed);
        setPromoteProduct('');
        handledPromoteRef.current = '';
      },
    });
  }, [promote, showInFrame, setPromoteProduct]);

  useEffect(() => {
    if (!promoteProduct || handledPromoteRef.current === promoteProduct) return;
    handledPromoteRef.current = promoteProduct;
    runPromote(promoteProduct);
  }, [promoteProduct, runPromote]);

  // Switching frame clears the selection so the editor never shows an item from
  // the other frame while the list shows this one.
  const handleSectionChange = (next: Section) => showInFrame(next, '');

  return (
    <div className="page-full">
      <h1 style={{ fontSize: 'var(--fs-h2)', fontWeight: 700, margin: '0 0 var(--s4)' }}>{t.workbench.title}</h1>
      {contractsQuery.isError && <ErrorBanner onRetry={() => contractsQuery.refetch()} />}
      <div style={{
        background: 'var(--bg-1)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)', overflow: 'hidden', display: 'flex', minHeight: '70vh',
      }}>
        <ContractList
          contracts={contracts}
          inventory={inventory.data?.datasets ?? []}
          selected={product}
          onSelect={setProduct}
          section={section}
          onSectionChange={handleSectionChange}
        />
        {product ? (
          <EditorPane
            key={product}
            product={product}
            onPromote={() => runPromote(product)}
            promotePending={promote.isPending}
          />
        ) : section === 'contract' && !contractsQuery.isLoading && !hasContracts ? (
          <div style={{ flex: 1, padding: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{
              background: 'var(--bg-1)', border: '1px dashed var(--line-2)',
              borderRadius: 'var(--r-lg)', padding: 32, textAlign: 'center', maxWidth: 560,
            }}>
              <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', marginBottom: 8 }}>
                {t.contracts.onboardingTitle}
              </h2>
              <p style={{ fontSize: 13, color: 'var(--fg-3)', maxWidth: 480, margin: '0 auto 16px' }}>
                {t.contracts.onboardingDesc}
              </p>
              <Button variant="primary" onClick={() => navigate('/lineage')}>{t.contracts.onboardingCta}</Button>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-3)' }}>
            {t.workbench.selectPrompt}
          </div>
        )}
      </div>
    </div>
  );
}
