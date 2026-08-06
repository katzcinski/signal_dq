import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type {
  BacktestOut, ContractOut, ContractPutBody, ContractVersionDiff, DiffReport,
  InventoryResponse, ObservedReality, SchemaDriftReport, SlaResponse,
} from '@/types';

// List items may carry EMPTY guarantees (served from the index) — always
// fetch the single contract for the full document.
export const useContracts = () =>
  useQuery<ContractOut[]>({
    queryKey: ['contracts'],
    queryFn: () => api.get('/contracts').then(r => {
      const d = r.data;
      return Array.isArray(d) ? d : (d?.contracts ?? []);
    }),
  });

export const useContract = (id: string) =>
  useQuery<ContractOut>({
    queryKey: ['contracts', id],
    queryFn: () => api.get(`/contracts/${id}`).then(r => r.data),
    enabled: !!id,
    retry: false,
  });

export const usePutContract = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ContractPutBody) => api.put(`/contracts/${id}`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts', id] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
      toast.success(t.toast.contractSaved);
    },
    onError: () => toast.error(t.toast.contractSaveError),
  });
};

// Direct activation: save → certify (active) → compile in one server round-trip,
// so guarantees light up the cockpit (status, compliance, coverage) without the
// version-release ceremony.
export const useCertifyContract = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ContractPutBody) => api.post(`/contracts/${id}/certify`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts', id] });
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['objects'] });
      toast.success(t.toast.contractCertified);
    },
    onError: () => toast.error(t.toast.contractSaveError),
  });
};

export const useSeedContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/contracts/${id}/seed`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  });
};

export const usePromoteContract = () => {
  const qc = useQueryClient();
  return useMutation<ContractOut, unknown, string>({
    mutationFn: (product: string) =>
      api.post(`/contracts/${product}/promote`).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contracts', data.product] });
      qc.invalidateQueries({ queryKey: ['coverage', 'summary'] });
      qc.invalidateQueries({ queryKey: ['lineage'] });
    },
  });
};

export const useDiffContract = (id: string) =>
  useMutation({
    mutationFn: (draft: ContractPutBody) =>
      api.post(`/contracts/${id}/diff`, draft).then(r => r.data as DiffReport),
  });

// UX-N13: semantic diff of the working contract vs. the last certified version.
export const useContractVersionDiff = (product: string, enabled = true) =>
  useQuery<ContractVersionDiff>({
    queryKey: ['contracts', product, 'version-diff'],
    queryFn: () => api.get(`/contracts/${product}/version-diff`).then(r => r.data),
    enabled: !!product && enabled,
    retry: false,
  });

// Shift-Left (§A): read-only Report, ob die Quelle vom Schema-Versprechen abweicht.
export const useSchemaDrift = (product: string, enabled = true) =>
  useQuery<SchemaDriftReport>({
    queryKey: ['contracts', product, 'drift'],
    queryFn: () => api.get(`/contracts/${product}/drift`).then(r => r.data),
    enabled: !!product && enabled,
    retry: false,
  });

// V1 Backtesting: Entwurf gegen die persistierte Messwert-Historie simulieren.
export const useBacktestContract = (product: string) =>
  useMutation({
    mutationFn: (contract: ContractPutBody) =>
      api.post(`/contracts/${product}/backtest`, { contract }).then(r => r.data as BacktestOut),
  });

// Einzel-Expectation (Proposal-Badge): „hätte N× in 90 d gefeuert".
export const useExpectationBacktest = (product: string, checkName: string, expect: string, enabled = true) =>
  useQuery<BacktestOut>({
    queryKey: ['backtest', product, checkName, expect],
    queryFn: () => api.post(`/contracts/${product}/backtest`, {
      checks: [{ check_name: checkName, expect }],
    }).then(r => r.data),
    enabled: enabled && !!product && !!checkName && !!expect,
    staleTime: 5 * 60_000,
    retry: false,
  });

export const useContractSla = (product: string, enabled = true) =>
  useQuery<SlaResponse>({
    queryKey: ['contracts', product, 'sla'],
    queryFn: () => api.get(`/contracts/${product}/sla`).then(r => r.data),
    enabled: !!product && enabled,
  });

export const useInventory = () =>
  useQuery<InventoryResponse>({
    queryKey: ['inventory'],
    queryFn: () => api.get('/inventory').then(r => r.data),
    staleTime: 5 * 60_000,
  });

// P6: beobachtete Realität je Garantie (letzter Messwert, Sparkline, PASS/FAIL).
export const useObservedReality = (product: string, enabled = true) =>
  useQuery<ObservedReality>({
    queryKey: ['contracts', product, 'observed'],
    queryFn: () => api.get(`/contracts/${encodeURIComponent(product)}/observed`).then(r => r.data),
    enabled: !!product && enabled,
    retry: false,
  });

export const useApproveContract = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/contracts/${id}/approve`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contracts', id] });
      qc.invalidateQueries({ queryKey: ['objects'] });
    },
  });
};

export const useDeprecateContract = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/contracts/${id}/deprecate`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts'] });
      qc.invalidateQueries({ queryKey: ['contracts', id] });
      qc.invalidateQueries({ queryKey: ['objects'] });
    },
  });
};

export const useCompileContract = (id: string) =>
  useMutation({
    mutationFn: () => api.post(`/contracts/${id}/compile`).then(r => r.data),
  });

export const useCompileContractDryRun = (id: string) =>
  useMutation({
    mutationFn: () => api.post(`/contracts/${id}/compile?dry_run=true`).then(r => r.data),
  });

export const useDryRunChecks = (dataset: string) =>
  useMutation({
    mutationFn: (body: { environment?: string } = {}) =>
      api.post(`/checks/${dataset}/dry-run`, body).then(r => r.data),
  });

export const useRevertChecks = (dataset: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/checks/${dataset}/revert`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  });
};

export const useExportBdc = (product: string) =>
  useMutation({
    mutationFn: () => api.post(`/contracts/${product}/export/bdc`).then(r => r.data),
  });
