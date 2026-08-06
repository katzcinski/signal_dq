import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ContractWorkbench from '@/pages/ContractWorkbench';
import { t } from '@/i18n/de';
import type { ContractOut, DiffReport } from '@/types';

let currentContract: ContractOut;
// When a test needs more than the single selected contract (e.g. to exercise the
// frame split), it sets currentList; otherwise the list mirrors currentContract.
let currentList: ContractOut[] | null;
let currentDiff: DiffReport | null;
let mutations: Record<string, ReturnType<typeof vi.fn>>;

function mutation(name?: string) {
  const mutate = name && mutations[name] ? mutations[name] : vi.fn();
  if (name) mutations[name] = mutate;
  return {
    mutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
    data: undefined,
  };
}

vi.mock('@/api/contracts', () => ({
  useContracts: () => ({
    data: currentList ?? [currentContract],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useContract: () => ({
    data: currentContract,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useInventory: () => ({ data: { datasets: [] } }),
  usePutContract: () => mutation('put'),
  useCertifyContract: () => mutation('certify'),
  useApproveContract: () => mutation('approve'),
  useDeprecateContract: () => mutation('deprecate'),
  useCompileContractDryRun: mutation,
  useDryRunChecks: mutation,
  useRevertChecks: mutation,
  useExportBdc: mutation,
  usePromoteContract: () => mutation('promote'),
  useSeedContract: mutation,
  useDiffContract: () => ({
    ...mutation(),
    data: currentDiff ?? { ceremony_required: currentContract.kind !== 'internal_gate', entries: [] },
  }),
  useContractSla: () => ({
    data: {
      windows: { '7d': null, '30d': null, '90d': null },
    },
  }),
  useSchemaDrift: () => ({ data: undefined, isLoading: false, isError: false }),
  useObservedReality: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock('@/api/proposals', () => ({
  useProposals: () => ({ data: [], isLoading: false, isError: false }),
}));

vi.mock('@/api/operations', () => ({
  useOperation: () => ({ data: null }),
  useOperationStream: () => ({ data: null }),
}));

// The check builder renders for internal gates, so every internal-gate render
// here now consumes the library. Mock it (real hook needs a QueryClient) with a
// mix that exercises the eligibility filter: eligible (value_range,
// allowed_values), guarantee-covered (missing), empty-template (custom_sql),
// expr-param (cross_field_consistency).
const libCheck = (over: Record<string, unknown>) => ({
  id: '', label: '', short: '', help: '', example: '', category: 'Konsistenz',
  family: 'quality', gating: 'standard', sql_template: 'SELECT 1',
  default_expect: '= 0', default_severity: 'fail', unit: '', params: [], ...over,
});
vi.mock('@/api/library', () => ({
  useLibrary: () => ({
    data: {
      categories: ['Konsistenz', 'Vollständigkeit'],
      families: ['observability', 'quality'],
      checks: [
        libCheck({ id: 'value_range', label: 'Value Range (Min/Max)', help: 'Range help', params: [
          { token: '<SPALTE>', type: 'identifier', label: 'Spalte' },
          { token: '<MIN>', type: 'number', label: 'Minimum' },
          { token: '<MAX>', type: 'number', label: 'Maximum' },
        ] }),
        libCheck({ id: 'allowed_values', label: 'Allowed Values (Set)', params: [
          { token: '<SPALTE>', type: 'identifier', label: 'Spalte' },
          { token: '<WERTE>', type: 'value_list', label: 'Erlaubte Werte' },
        ] }),
        libCheck({ id: 'missing', label: 'Missing Values', category: 'Vollständigkeit',
          params: [{ token: '<SPALTE>', type: 'identifier', label: 'Spalte' }] }),
        libCheck({ id: 'cross_field_consistency', label: 'Cross-Field Consistency',
          sql_template: 'SELECT 1 WHERE NOT (<REGEL>)',
          params: [{ token: '<REGEL>', type: 'expr', label: 'Regel' }] }),
        libCheck({ id: 'custom_sql', label: 'Custom SQL', sql_template: '' }),
      ],
    },
  }),
}));

const contract = (overrides: Partial<ContractOut> = {}): ContractOut => ({
  product: 'P_MODE',
  kind: 'internal_gate',
  dataset: 'P_MODE',
  owned_by: 'platform',
  owners: [],
  lifecycle: 'active',
  version: '1.0.0',
  guarantees: {},
  compliance: null,
  certified: false,
  ...overrides,
});

function renderWorkbench(route = '/contracts?product=P_MODE') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ContractWorkbench />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  currentContract = contract();
  currentList = null;
  currentDiff = null;
  mutations = {};
});

describe('ContractWorkbench primary action derivation', () => {
  it('uses one-click activation for internal gates', () => {
    renderWorkbench();

    fireEvent.click(screen.getByRole('button', { name: t.workbench.activate }));

    expect(mutations.certify).toHaveBeenCalledWith(expect.objectContaining({ product: 'P_MODE', kind: 'internal_gate' }));
    const buttonLabels = screen.getAllByRole('button').map(button => button.textContent ?? '');
    expect(buttonLabels.some(label => /zertifizieren|workflow/i.test(label))).toBe(false);
  });

  it('uses one-click activation for never-live contract drafts', () => {
    currentContract = contract({
      kind: 'consumer_contract',
      owned_by: 'platform',
      lifecycle: 'draft',
      certified: false,
    });

    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: t.workbench.activate }));

    expect(mutations.certify).toHaveBeenCalledWith(expect.objectContaining({ product: 'P_MODE', kind: 'consumer_contract' }));
    expect(mutations.approve).not.toHaveBeenCalled();
  });

  it('uses release ceremony for certified draft amendments', () => {
    currentContract = contract({
      kind: 'consumer_contract',
      owned_by: 'platform',
      lifecycle: 'draft',
      certified: true,
      version: '1.1.0',
    });

    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: `${t.workbench.release} (v1.1.0)` }));
    expect(screen.getByText(t.workbench.approveConfirm)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.common.confirm }));

    expect(mutations.approve).toHaveBeenCalledTimes(1);
    expect(mutations.certify).not.toHaveBeenCalled();
  });

  it('blocks release ceremony when the breaking gate blocks it', () => {
    currentContract = contract({
      kind: 'consumer_contract',
      owned_by: 'platform',
      lifecycle: 'draft',
      certified: true,
      version: '1.1.0',
    });
    currentDiff = {
      ceremony_required: true,
      active_version: '1.1.0',
      blocking: true,
      breaking: true,
      entries: [{ kind: 'breaking', path: 'guarantees.keys', breaking: true }],
    };

    renderWorkbench();
    const release = screen.getByRole('button', { name: `${t.workbench.release} (v1.1.0)` });

    expect(release).toBeDisabled();
    expect(screen.getAllByRole('tooltip').some(el => el.textContent === t.workbench.breakingBlocked)).toBe(true);
  });

  it('uses deprecation as the primary action for active governance contracts', () => {
    currentContract = contract({
      kind: 'consumer_contract',
      owned_by: 'platform',
      lifecycle: 'active',
      certified: true,
    });

    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: t.workbench.deprecate }));
    expect(screen.getByText(t.workbench.deprecateConfirm)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.common.confirm }));

    expect(mutations.deprecate).toHaveBeenCalledTimes(1);
  });

  it('does not render SLA bars for active internal gates', () => {
    renderWorkbench();

    expect(screen.queryByText(t.workbench.slaTitle)).not.toBeInTheDocument();
  });
});

describe('ContractWorkbench frame split', () => {
  beforeEach(() => {
    currentContract = contract();
    currentList = null;
  });

  it('splits the list into internal and contract frames and filters by the active one', () => {
    currentList = [
      contract({ product: 'P_GATE', dataset: 'P_GATE', kind: 'internal_gate' }),
      contract({ product: 'P_CONTRACT', dataset: 'P_CONTRACT', kind: 'consumer_contract', owned_by: 'product' }),
    ];

    renderWorkbench('/contracts');

    // Default frame = internal: the gate shows, the contract does not.
    expect(screen.getByText('P_GATE')).toBeInTheDocument();
    expect(screen.queryByText('P_CONTRACT')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: t.workbench.tabContract }));

    expect(screen.getByText('P_CONTRACT')).toBeInTheDocument();
    expect(screen.queryByText('P_GATE')).not.toBeInTheDocument();
  });

  it('lands a selected contract in the contract frame regardless of the section param', () => {
    currentContract = contract({ product: 'P_MODE', kind: 'consumer_contract', owned_by: 'product' });

    // Deep link forces ?section=internal, but the selected item is a contract:
    // the item's kind wins, so the editor renders the contract frame, not internal.
    renderWorkbench('/contracts?product=P_MODE&section=internal');

    expect(screen.getByText(t.workbench.frameContract)).toBeInTheDocument();
    expect(screen.queryByText(t.workbench.frameInternal)).not.toBeInTheDocument();
  });

  it('offers in-place promotion for an internal gate', () => {
    renderWorkbench('/contracts?product=P_MODE');

    fireEvent.click(screen.getByTitle(t.workbench.moreActions));

    expect(screen.getByRole('button', { name: t.workbench.promote })).toBeInTheDocument();
  });

  it('does not offer promotion for a governance contract', () => {
    currentContract = contract({
      kind: 'consumer_contract',
      owned_by: 'product',
      certified: true,
      compliance: 'unknown',
    });

    renderWorkbench();

    expect(screen.queryByRole('button', { name: t.workbench.promote })).not.toBeInTheDocument();
  });
});

describe('ContractWorkbench check builder', () => {
  beforeEach(() => {
    currentContract = contract();   // internal_gate → builder visible
    currentList = null;
  });

  it('renders the library check builder in the internal frame', () => {
    renderWorkbench();
    // Redesign (P6): der Check-Builder liegt unter dem Definition-Untertab.
    fireEvent.click(screen.getByRole('button', { name: t.workbench.subtabs.builder }));
    expect(screen.getByText(t.workbench.checks.title)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: t.workbench.checks.add })).toBeInTheDocument();
  });

  it('excludes guarantee-covered, custom_sql and expr-param checks from the picker', () => {
    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: t.workbench.subtabs.builder }));
    const add = screen.getByRole('combobox', { name: t.workbench.checks.add }) as HTMLSelectElement;
    const values = Array.from(add.options).map(o => o.value);
    expect(values).toContain('value_range');
    expect(values).toContain('allowed_values');
    expect(values).not.toContain('missing');                  // guarantee-covered
    expect(values).not.toContain('custom_sql');               // empty template (deferred)
    expect(values).not.toContain('cross_field_consistency');  // expr param (deferred)
  });

  it('adds a selected check into the draft as an editable, prefilled row', () => {
    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: t.workbench.subtabs.builder }));
    expect(screen.queryByLabelText(t.workbench.checks.expect)).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: t.workbench.checks.add }), {
      target: { value: 'value_range' },
    });

    const expectInput = screen.getByLabelText(t.workbench.checks.expect) as HTMLInputElement;
    expect(expectInput.value).toBe('= 0');          // prefilled from default_expect
    expect(screen.getByText('Minimum')).toBeInTheDocument();  // param form rendered
  });

  it('does not render the check builder for a boundary contract', () => {
    currentContract = contract({ kind: 'consumer_contract', owned_by: 'product' });
    renderWorkbench();
    expect(screen.queryByText(t.workbench.checks.title)).not.toBeInTheDocument();
  });
});
