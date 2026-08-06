export type Family = 'observability' | 'quality' | 'contract';
export type ArtifactKind = 'internal_gate' | 'consumer_contract' | 'provider_contract';

// ---- Datasphere data loads ----
export interface DataLoad {
  object_id: string;
  load_type: 'task_chain' | 'replication_flow' | string;
  run_id: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  triggered_by: string | null;
  raw: Record<string, unknown>;
}
export type Lifecycle = 'draft' | 'active' | 'deprecated';
export type Severity = 'critical' | 'fail' | 'warn';
export type OverallStatus = 'pass' | 'fail' | 'warn' | 'critical' | 'unknown';
export type RunState = 'running' | 'finished' | 'error';
export type CovFlag = 'covered' | 'partial' | 'gap' | 'out_of_scope';
// G6 gating states: anything other than 'executed' must NOT render as pass/fail.
export type CheckState = 'executed' | 'skipped_stale' | 'skipped_dependency' | 'downgraded' | 'error';

// ---- Inventory ----
export interface InventoryObject {
  id: string;
  name: string;
  display_name: string;
  space: string;
  schema: string;
  layer: 'source' | 'transformation' | 'consumption';
  family: Family;
  lifecycle: Lifecycle;
  owned_by: 'platform' | 'product';
  owners: string[];
  description?: string;
}

// ---- Inventory picker source (GET /api/inventory) ----
export interface InventoryColumn {
  name: string;
  [key: string]: unknown;
}

export interface InventoryDataset {
  id?: string;
  technicalName?: string;
  name?: string;
  schema?: string;
  columns?: InventoryColumn[];
  [key: string]: unknown;
}

export interface InventoryResponse {
  datasets: InventoryDataset[];
}

// ---- Environments (GET /api/environments) ----
export interface Environment {
  name: string;
  schema: string;
  host?: string;
  secret_status?: boolean;
}

export interface EnvironmentsResponse {
  environments: Environment[];
}

// ---- Schedules (Option E, ADR-0005) ----
// A per-object scheduling toggle: manual (no row), internal (Signal's poller
// drives the cadence) or external (a Task Chain / cron → CLI drives it; the
// poller never claims it).
export type ScheduleMode = 'internal' | 'external' | 'on_load';

export interface Schedule {
  schedule_id: string;
  object_id: string;
  mode: ScheduleMode;
  environment: string;
  execution_mode: string;
  interval_seconds: number;
  enabled: boolean;
  next_due_at: string;
  last_run_at?: string | null;
  last_run_id?: string | null;
  last_status?: string | null;
  created_by?: string;
  created_at?: string;
  updated_at?: string | null;
}

export interface ScheduleUpsert {
  mode: ScheduleMode;
  interval_seconds: number;
  environment?: string;
  execution_mode?: string;
  enabled?: boolean;
}

// ---- Admin connection settings (GET /api/admin/environments) ----
// The password value is never returned; `password_ref` is the secret reference
// (e.g. "env:HANA_PW_PROD") and `password_set` mirrors whether it resolves.
export interface AdminEnvironment {
  name: string;
  host: string;
  port: number;
  user: string;
  schema: string;
  password_ref: string;
  password_set: boolean;
  encrypt: boolean;
  validate_cert: boolean;
}

export interface AdminEnvironmentsResponse {
  environments: AdminEnvironment[];
  can_edit: boolean;
}

// ---- Connection test (POST /api/environments/{name}/test → operation) ----
export interface ConnectionTestResult {
  ok: boolean;
  latency_ms: number;
  server_version: string | null;
  schema_visible: boolean;
  failure_stage: string | null;
  error: string | null;
}

export interface OperationProgressLine {
  id?: number;
  ts: string;
  line: string;
}

export interface OperationStart {
  op_id: string;
}

export interface OperationStatus<T = unknown> {
  op_id: string;
  kind: string;
  state: 'running' | 'finished' | 'error';
  created_by?: string;
  started_at: string | null;
  finished_at: string | null;
  result: T | null;
  error: string | null;
  progress: OperationProgressLine[];
}

// ---- Per-family status rollup ----
export interface FamilyStatus {
  observability: string; // pass|warn|fail|critical|error|unknown
  quality: string;       // pass|warn|fail|critical|error|unknown
}

// ---- Objects (API enriched) — mirrors backend ObjectOut ----
export interface ObjectSummary {
  id: string;
  name: string;
  schema_name: string;
  family: Family;
  layer: string;
  status: OverallStatus;
  family_status?: FamilyStatus;
  contract_status: string;        // '' | draft | active | deprecated
  cov_flag: CovFlag;              // covered | partial | gap | out_of_scope
  check_count: number;
  owned_by: string;
  last_run?: string | null;
  last_run_id?: string | null;
  space: string;
}

// ---- Check Library ----
// Param binding type — drives both the builder input and the compiler's
// escaping. 'expr' params are raw SQL fragments with no GUI path (deferred §5).
export type CheckParamType = 'identifier' | 'number' | 'string' | 'regex' | 'value_list' | 'expr';

export interface CheckTemplateParam {
  token: string;
  type?: CheckParamType;
  label: string;
  hint?: string;
}

// Functional axis: which family a check's result rolls up into (obs/quality).
export type CheckFamily = 'observability' | 'quality';
// Execution axis: role in the gating chain (cheap gates gate expensive checks).
export type CheckGating = 'gate' | 'expensive' | 'standard';

export interface CheckDef {
  id: string;
  label: string;
  short: string;
  help: string;
  example?: string;
  category: string;
  family: CheckFamily;
  gating: CheckGating;
  sql_template: string;
  params: CheckTemplateParam[];
  default_expect: string;
  default_severity: Severity;
  unit: string;
}

export interface CheckLibrary {
  checks: CheckDef[];
  categories: string[];
  families: CheckFamily[];
}

// ---- Runs ----
export interface CheckResult {
  name: string;
  sql: string;
  expect: string;
  severity: Severity;
  passed: boolean;
  actual_value?: string;
  error?: string;
  duration_ms: number;
  state: CheckState;
  kind: ArtifactKind;
}

export interface RunSummary {
  run_id: string;
  dataset: string;
  schema_name: string;
  started_at: string;
  finished_at: string;
  overall_status: OverallStatus;
  total: number;
  passed: number;
  failed: number;
  warnings: number;
  triggered_by: string;
  contract_version: string;
  actor: string;
  run_state: RunState;
  gate_verdict?: GateVerdict;
  results: CheckResult[];
}

export interface RunListItem {
  run_id: string;
  dataset: string;
  started_at: string;
  finished_at: string;
  overall_status: OverallStatus;
  total: number;
  passed: number;
  failed: number;
  warnings: number;
  run_state: RunState;
  triggered_by: string;
  gate_verdict?: GateVerdict;
}

// ---- Run comparison / regression diff (GET /api/runs/compare) — UX-N5 ----
export type CheckCompareStatus = 'pass' | 'fail' | 'warn' | 'error' | 'skipped';
export type CheckTransition =
  | 'regressed' | 'recovered' | 'unchanged' | 'changed' | 'added' | 'removed';

export interface RunCompareHeader {
  run_id: string;
  dataset: string;
  started_at: string;
  finished_at: string;
  overall_status: OverallStatus;
  total: number;
  passed: number;
  failed: number;
  warnings: number;
}

// B-1 Value-Diff (§B.2): vorher/nachher je Check inkl. Delta (numerisch wo möglich).
export interface ValueDelta {
  base: string | number | null;
  head: string | number | null;
  abs_delta: number | null;
  pct_delta: number | null;
}

export interface CheckChange {
  check_name: string;
  base_status: CheckCompareStatus | null;
  head_status: CheckCompareStatus | null;
  transition: CheckTransition;
  value_delta?: ValueDelta;
}

export interface RunCompare {
  base: RunCompareHeader;
  head: RunCompareHeader;
  summary: Record<CheckTransition, number>;
  changes: CheckChange[];
}

// ---- Contract version diff (GET /api/contracts/{product}/version-diff) — UX-N13 ----
export interface VersionDiffEntry {
  kind: string;
  path: string;
  old?: unknown;
  new?: unknown;
  breaking: boolean;
}

export interface ContractVersionDiff {
  available: boolean;
  kind?: ArtifactKind;
  ceremony_required?: boolean;
  from_version: string | null;
  to_version: string;
  lifecycle?: Lifecycle;
  breaking: boolean;
  blocking?: boolean;
  entries: VersionDiffEntry[];
}

// ---- Activity / audit feed (GET /api/activity) — UX-N15 ----
export interface ActivityItem {
  kind: 'incident' | 'proposal' | 'contract';
  action: string;
  actor: string;
  at: string;
  product: string;
  summary: string;
  ref: string;
}

// ---- Check history (GET /api/objects/{id}/checks/{name}/history) ----
export interface CheckHistoryPoint {
  actual_value: string | null;
  passed: 0 | 1;
  state: string;
  started_at: string;
  run_id: string;
}

// ---- Metric time-series (GET /api/objects/{id}/timeseries) — UX-N1 ----
export interface MetricPoint {
  at: string;
  value: number | null;
  raw: string | null;
  passed: boolean;
  state: string;
  run_id: string;
  anomaly: boolean;
}

export interface MetricBaseline {
  mean: number;
  lower: number;
  upper: number;
  p01: number | null;
  p99: number | null;
}

export type MetricFamily = 'freshness' | 'volume' | 'observability';

export interface MetricSeries {
  check_name: string;
  check_type: string;
  metric: MetricFamily;
  baseline: MetricBaseline | null;
  points: MetricPoint[];
}

export interface ObjectTimeseries {
  dataset: string;
  series: MetricSeries[];
}

// ---- Data products (GET /api/products) ----
export interface ProductListItem {
  product: string;
  owners: string[];
  port_count: number;
  own_health: OverallStatus;
  upstream_risk_count: number;
  finding_count: number;
  lifecycle: Lifecycle;
}

export interface ProductPort {
  dataset: string;
  kind: ArtifactKind | null;
  lifecycle: Lifecycle | null;
  compliance: string | null;
  version: string | null;
}

export interface ProductInterior {
  id: string;
  layer: string | null;
  role: string | null;
  coverage_flag: string | null;
}

export interface ProductUpstreamRiskEntry {
  product: string;
  pinned_version: string;
  current_version: string | null;
  compliance: string | null;
  upstream_breach: boolean;
  version_drift: boolean;
}

export interface ProductFinding {
  finding_type: 'dangling_port' | 'contested' | 'boundary_leak';
  scope: 'port' | 'interior' | null;
  object_id: string;
  detail: string;
}

export interface ProductDetail {
  product: string;
  owners: string[];
  lifecycle: Lifecycle;
  own_health: OverallStatus;
  ports: ProductPort[];
  interior: ProductInterior[];
  inbound_sources: string[];
  upstream_risk: ProductUpstreamRiskEntry[];
  findings: ProductFinding[];
  subgraph: LineageGraph;
}

// ---- Contracts: canonical guarantee schema (§1.5) ----
export interface GuaranteeSchema {
  columns: string[];
  mode: 'closed' | 'open';
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface GuaranteeKey {
  columns: string[];
  unique: boolean;
  severity?: Severity;
  enforcement?: EnforcementMode;
  proposed?: boolean;
}

export interface GuaranteeReferential {
  fk: string[];          // single-column in v1
  parent: string;
  parent_key: string[];  // single-column in v1
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface GuaranteeFreshness {
  column: string;
  max_age: string; // ISO-8601 duration, e.g. PT24H
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface GuaranteeVolume {
  min_rows?: number;
  baseline?: 'rolling';
  bounds?: 'auto';
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface GuaranteeCompleteness {
  column: string;
  min_pct: number;
  segment_by?: string;
  max_segments?: number;
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface GuaranteeNotNull {
  columns: string[];
  severity?: Severity;
  enforcement?: EnforcementMode;
}

export interface ContractGuarantees {
  schema?: GuaranteeSchema;
  keys?: GuaranteeKey[];
  referential?: GuaranteeReferential[];
  freshness?: GuaranteeFreshness;
  volume?: GuaranteeVolume;
  completeness?: GuaranteeCompleteness[];
  not_null?: GuaranteeNotNull[];
}

export type ObservabilityBaseline = 'rolling' | 'seasonal';
export type ObservabilitySeason = 'dow' | 'eom' | 'hour';
export type ObservabilitySensitivity = 'low' | 'medium' | 'high';

export interface ObservabilityFamilyConfig {
  baseline?: ObservabilityBaseline;
  season?: ObservabilitySeason[];
  sensitivity?: ObservabilitySensitivity;
}

export interface ContractObservability {
  volume?: ObservabilityFamilyConfig;
  freshness?: ObservabilityFamilyConfig;
}

// A library-instantiated check on an internal gate (HANDOVER Iteration 1).
// params values are strings for scalar types, string[] for value_list.
export interface GateCheck {
  id: string;
  params: Record<string, string | string[]>;
  expect: string;
  severity: Severity;
}

export interface Contract {
  product: string;
  kind: ArtifactKind;
  dataset: string;
  schema?: string;
  owned_by: string;
  owners?: string[];
  lifecycle: Lifecycle;
  version: string;
  description?: string;
  guarantees?: ContractGuarantees;
  observability?: ContractObservability;
  checks?: GateCheck[];
}

export interface ContractOut extends Contract {
  compliance?: string | null;
  certified?: boolean;
  updated_at?: string;
}

// PUT body has NO lifecycle field (server forces draft).
export interface ContractPutBody {
  product: string;
  kind: ArtifactKind;
  dataset: string;
  owned_by: string;
  owners?: string[];
  version: string;
  description?: string;
  guarantees?: ContractGuarantees;
  observability?: ContractObservability;
  checks?: GateCheck[];
}

// ---- Breaking-diff (POST /api/contracts/{product}/diff) ----
export interface DiffEntry {
  kind: string;
  path: string;
  old?: unknown;
  new?: unknown;
  breaking?: boolean;
}

export interface DiffReport {
  kind?: ArtifactKind;
  ceremony_required?: boolean;
  breaking?: boolean;
  blocking?: boolean;
  entries?: DiffEntry[];
  active_version?: string;
  [key: string]: unknown;
}

// ---- SLA (GET /api/contracts/{product}/sla) ----
export interface SlaResponse {
  product: string;
  kind: ArtifactKind;
  current: string;
  windows: { '7d': number | null; '30d': number | null; '90d': number | null };
}

// ---- Coverage (GET /api/coverage/summary) ----
export interface CoverageSummary {
  objects_total: number;
  with_active_contract: number;
  with_internal_gate: number;
  with_contract_checks: number;
  contracts_breached: number;
  gates_failing: number;
  with_checks: number;
  contract_coverage_pct: number;
  unvalidated_30d: string[];
}

// ---- Health trend (GET /api/coverage/health) — UX-N12 ----
export interface HealthTrend {
  current_pct: number | null;
  previous_pct: number | null;
  datasets: number;
}

// ---- Status heatmap (GET /api/coverage/heatmap) — UX-N10 ----
export interface StatusHeatmap {
  days: string[];
  datasets: string[];
  matrix: Record<string, Record<string, string>>; // dataset → (day → status)
}

// ---- Notification routing (UX-N2) ----
export type ChannelType = 'slack' | 'teams' | 'webhook';

export interface NotificationChannel {
  id: number;
  name: string;
  type: ChannelType | string;
  url: string;
  enabled: boolean;
  digest_enabled: boolean;
  created_at: string;
  created_by: string;
}

// ---- Qualitäts-Digest (GET /api/notifications/digest/preview) — V4 ----
export interface DigestPreview {
  period_hours: number;
  generated_at: string;
  incidents_new: number;
  incidents_new_by_severity: Record<string, number>;
  incidents_open: number;
  top_incidents: { id: number; product: string; severity: string; title: string }[];
  runs: number;
  runs_failed: number;
  gate_verdicts: Record<string, number>;
  quarantine_open: number;
  drift_objects: number;
  drift_breaking_objects: number;
  enabled: boolean;
  interval_hours: number;
  subscribed_channels: number;
  last_sent_at: string | null;
}

export interface NotificationRule {
  id: number;
  name: string;
  channel_id: number;
  match_severity: string;   // '' | critical | fail | warn
  match_space: string;
  match_product: string;
  match_owned_by: string;   // '' | platform | product
  match_owner: string;
  match_kind: string;
  enabled: boolean;
  created_at: string;
  created_by: string;
}

export interface NotificationMute {
  id: number;
  reason: string;
  match_space: string;
  match_product: string;
  starts_at: string;
  ends_at: string;
  created_at: string;
  created_by: string;
}

export interface NotificationConfig {
  channels: NotificationChannel[];
  rules: NotificationRule[];
  mutes: NotificationMute[];
  can_edit: boolean;
}

// ---- Lineage ----
export interface LineageColumn {
  name?: string;
  label?: string;
  data_type?: string;
  type?: string;
  [key: string]: unknown;
}

export interface LineageNode {
  id: string;
  label?: string;
  layer: string;
  layerCode?: string;
  role?: string;
  confidence?: number;
  columns?: LineageColumn[];
  family?: Family | string;
  space?: string;
  /** Quellsystem (z. B. "DEMO", "Datasphere") — im Schaltplan die "Platform". */
  system?: string;
  // Coverage annotation fields (from /api/lineage)
  coverage_flag?: '●' | '◐' | '▲' | '○';
  dq_status?: string;
  has_contract?: boolean;
  has_internal_gate?: boolean;
  has_boundary_contract?: boolean;
  kind?: ArtifactKind | '';
  last_run?: string;
}

export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  edgeType?: string;
  confidence?: number;
  expression?: string;
}

export interface LineageColumnEdge {
  source: string;
  sourceColumn: string;
  target: string;
  targetColumn: string;
  edgeType?: ColumnEdgeType;
  expression?: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
  columnEdges?: LineageColumnEdge[];
  extract_age?: number | null;
  extracted_at?: string | null;
  stale?: boolean;
}

export type ColumnEdgeType = 'direct' | 'computed' | 'passthrough' | string;

export interface ColumnLineageStep {
  object: string;
  column: string;
  edgeType: ColumnEdgeType;
  expression?: string;
}

export interface ColumnLineageEntry {
  upstream: ColumnLineageStep[];
  downstream: ColumnLineageStep[];
}

export interface ColumnLineageObjectResponse {
  object: string;
  columns: Record<string, ColumnLineageEntry>;
}

export interface ColumnLineageColumnResponse {
  object: string;
  column: string;
  lineage: ColumnLineageEntry;
}

export type ColumnLineageResponse = ColumnLineageObjectResponse | ColumnLineageColumnResponse;

export interface ColumnImpactRow {
  object: string;
  column: string;
  edgeType: ColumnEdgeType;
  expression?: string;
  depth: number;
  ownedBy?: string;
  owners?: string[];
  coverageFlag?: string;
  dqStatus?: string;
}

export interface ColumnImpactResponse {
  object: string;
  column: string;
  impacted: ColumnImpactRow[];
  totalImpacted: number;
  maxDepth: number;
  truncated: boolean;
}

// ---- Object profiling (POST /api/objects/{id}/profile) ----
export interface ObjectProfileColumn {
  column: string;
  data_type: string;
  total: number;
  nulls: number;
  null_pct: number;
  distinct: number;
  uniqueness_pct: number;
  pk_candidate: boolean;
  text_like?: boolean;
  numeric_like?: boolean;
  decimal_like?: boolean;
  empty_count?: number | null;
  empty_pct?: number | null;
  min?: number | string | null;
  max?: number | string | null;
  avg?: number | string | null;
  median?: number | string | null;
}

export interface ProfileSingleCandidate {
  column: string;
  data_type?: string;
  exact?: boolean;
  nulls?: number;
  null_pct?: number;
  empty_count?: number | null;
  empty_pct?: number | null;
  distinct?: number;
  uniqueness_pct?: number;
  rank_reason?: string;
  technical_score?: number;
  business_score?: number;
  final_score?: number;
  reasons?: string[];
}

export interface ProfileCompositeCandidate {
  columns: string[];
  width?: number;
  exact?: boolean;
  distinct?: number;
  uniqueness_pct?: number;
  rank_reason?: string;
  technical_score?: number;
  business_score?: number;
  final_score?: number;
  reasons?: string[];
}

export interface ProfileSearchMeta {
  max_width?: number;
  eligible_columns?: number;
  eligible_column_names?: string[];
  full_search_skipped?: boolean;
  skip_reason?: string;
  heuristic_combo_count?: number;
}

export interface ProfileKeyCandidates {
  single?: string[];
  composite?: string[][];
  ranked_single?: ProfileSingleCandidate[];
  ranked_composite?: ProfileCompositeCandidate[];
  search_meta?: ProfileSearchMeta;
}

export interface ProfileScores {
  overall_key_confidence?: number;
  uniqueness?: number;
  completeness?: number;
  business_fit?: number;
  compound_viability?: number;
  weights?: Record<string, number>;
}

export interface ProfileIssue {
  column: string;
  type: string;
  detail: string;
}

export interface ProfileDerivedStats {
  empty_string_columns?: { column: string; empty_count: number; empty_pct: number }[];
  numeric_stats?: { column: string; min?: unknown; max?: unknown; avg?: unknown; median?: unknown }[];
}

export interface ProfileSampleRows {
  enabled: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
  reason?: string;
}

export interface ObjectProfileResult {
  schema: string;
  table: string;
  view?: string;
  row_count: number;
  column_count: number;
  columns: ObjectProfileColumn[];
  pk_candidates: ProfileKeyCandidates;
  profiling?: ProfileDerivedStats;
  issues?: ProfileIssue[];
  scores?: ProfileScores;
  heuristics?: Record<string, unknown>;
  sample_rows?: ProfileSampleRows;
}

// ---- Incidents: persistent lifecycle objects ----
export type IncidentStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved';

export interface Incident {
  id: number;
  product: string;
  run_id: string;
  severity: string;
  status: IncidentStatus;
  owner: string;
  title: string;
  failed_checks: string[];
  opened_at: string;
  resolved_at: string | null;
  contract_version: string;
  kind: ArtifactKind;
  cluster_id?: string;
  correlation_key?: string;
  member_count?: number;
  representative_incident_id?: number;
  impacted_objects?: IncidentImpactObject[];
}

export interface IncidentImpactObject {
  product: string;
  distance: number;
  label?: string;
  business_name?: string;
  object_type?: string;
  space?: string;
  layer?: string;
  role?: string;
  owned_by?: string;
  owners?: string[];
  lifecycle?: string;
  kind?: ArtifactKind | string;
  version?: string;
}

export interface IncidentEvent {
  id: number;
  at: string;
  actor: string;
  action: string;
  note: string;
}

export interface IncidentDetail extends Incident {
  events: IncidentEvent[];
}

// ---- Quarantäne: Enforcement-Episoden (Konzept_Datasphere_Integration) ----
export type QuarantineStatus = 'open' | 'reconciled' | 'released' | 'resolved' | 'superseded';
export type GateVerdict = 'proceed' | 'quarantine' | 'block';
export type EnforcementMode = 'gate' | 'quarantine' | 'monitor';

export interface QuarantineEpisode {
  id: number;
  product: string;
  run_id: string;
  status: QuarantineStatus;
  failed_checks: string[];
  contract_version: string;
  manifest_hash: string;
  generation: number;
  row_count: number | null;
  opened_at: string;
  released_at: string | null;
  released_by: string;
  resolved_at: string | null;
  resolve_reason: string;
}

export interface QuarantineEpisodeDetail extends QuarantineEpisode {
  events: IncidentEvent[];
}

export interface IncidentTransitionBody {
  status: string;
  owner?: string;
  note?: string;
}

export interface IncidentRca {
  incident_id: number;
  probable_cause_object: string;
  cause_confidence: number | null;
  cause_candidates: Record<string, unknown>[];
  affected_contracts: Record<string, unknown>[];
  affected_internal_gates: Record<string, unknown>[];
  recurrence_count: number;
  recurrence_last_at: string;
  computed_at: string;
}

// ---- Derived failing-checks view (GET /api/incidents/checks) ----
export interface FailedCheck {
  id: string;                    // "<run_id>:<check_name>" (backend-provided)
  check_name: string;
  dataset: string;
  severity: Severity;
  expect_expr: string;
  actual_value?: string;
  error_message?: string;
  state: CheckState;
  run_id: string;
  started_at: string;
  schema_name: string;
}

// ---- Proposals ----
export interface ProposalStats {
  n: number;
  min: number;
  max: number;
  mean: number;
  p01: number;
  p99: number;
  stddev: number;
}

export interface Proposal {
  id: string;
  product: string;
  check_name: string;
  current_expect: string;
  proposed_expect: string;
  rationale: string;
  confidence: number;
  status: 'open' | 'accepted' | 'rejected' | 'snoozed';
  kind: ArtifactKind;
  stats?: ProposalStats;
}

// ---- Observed reality per guarantee (P6: GET /contracts/{id}/observed) ----
export interface ObservedPoint {
  at: string;
  value: number | null;
  raw: string | null;
  passed: boolean | null;
  state: string;
  run_id: string;
}
export interface ObservedCheck {
  name: string;
  type: string;
  family: string | null;
  severity: string;
  expect: string;
  last_value: string | null;
  passed: boolean | null;
  state: string;
  points: ObservedPoint[];
}
export interface ObservedGuarantee {
  family: string;
  state: 'pass' | 'fail' | 'unknown';
  checks: ObservedCheck[];
}
export interface ObservedReality {
  product: string;
  dataset: string;
  guarantees: ObservedGuarantee[];
}

// ---- Run progress events (streamed via SSE, polled as fallback) ----
export interface RunEvent {
  ts: string;
  line: string;
}

// ---- SSE Events ----
export type SSEEvent =
  | { type: 'connected' }
  | { type: 'run_started'; run_id: string; dataset: string }
  | { type: 'progress'; run_id: string; ts: string; line: string }
  | { type: 'run_finished'; run_id: string; overall_status: OverallStatus }
  | { type: 'run_error'; run_id: string; error: string };

// ---- Shift-Left-Schema-Drift (GET /api/contracts/{product}/drift) — Konzept §A ----
export type SchemaDriftCategory =
  | 'column_added' | 'column_removed' | 'type_changed'
  | 'nullable_relaxed' | 'key_changed';

export interface SchemaDriftFinding {
  category: SchemaDriftCategory;
  column: string;
  before: string;
  after: string;
  breaking: boolean;
}

export interface SchemaDriftSummary {
  total: number;
  breaking: number;
  has_breaking: boolean;
  by_category: Record<string, number>;
}

export interface SchemaDriftHistoryRow {
  id: number;
  object_name: string;
  detected_at: string;
  category: string;
  column_name: string;
  before_value: string;
  after_value: string;
  breaking: number;
  contract_version: string;
  incident_id: number | null;
}

export interface SchemaDriftReport {
  product: string;
  dataset: string;
  object_found: boolean;
  kind: string;
  findings: SchemaDriftFinding[];
  summary: SchemaDriftSummary;
  history: SchemaDriftHistoryRow[];
}

// ---- Schema-Evolution-Screen (GET /api/schema-drift[…]) — A2/UX-N9 ----
export interface SchemaDriftObjectRow {
  object_name: string;
  snapshots: number;
  first_captured_at: string | null;
  last_captured_at: string | null;
  distinct_schemas: number;
  findings: number;
  breaking: number;
  last_detected_at: string | null;
  last_incident_id: number | null;
  column_count: number | null;
  product: string | null;
  kind: string | null;
  contract_version: string | null;
  lifecycle: string | null;
}

export interface SchemaEvolutionSnapshot {
  id: number;
  captured_at: string;
  inventory_hash: string;
  column_count: number;
}

export interface SchemaEvolutionChange {
  category: SchemaDriftCategory;
  column: string;
  before: string;
  after: string;
}

export interface SchemaEvolutionStep {
  from_id: number;
  to_id: number;
  from_at: string;
  to_at: string;
  changes: SchemaEvolutionChange[];
}

export interface SchemaEvolutionOut {
  object_name: string;
  contract: { product: string; version: string; kind: string; lifecycle: string } | null;
  snapshots: SchemaEvolutionSnapshot[];
  steps: SchemaEvolutionStep[];
  drift_events: SchemaDriftHistoryRow[];
  latest_columns: { name?: string; type?: string; key?: unknown; nullable?: unknown }[];
}

// ---- Healing-Workbench (/api/healing) — Konzept_Manuelles_Healing H1/H3 ----
export interface HealingEpisodeRow {
  episode_id: number;
  object_id: string;
  status: string;
  row_count: number | null;
  failed_checks: string[];
  opened_at: string;
  corrections: number;
  kind: string;
  four_eyes: boolean;
}

export interface HealingCorrection {
  id: number;
  object_id: string;
  episode_id: number;
  row_key: Record<string, string>;
  column_name: string;
  before_value: string | null;
  after_value: string | null;
  reason: string;
  actor: string;
  created_at: string;
  applied: boolean;
  apply_error: string;
}

export interface HealingPatch {
  id: string;
  object_id: string;
  keys: Record<string, string>;
  values: Record<string, string>;
  reason: string;
  actor: string;
  created_at: string;
  valid_until: string | null;
  status: 'active' | 'revoked' | 'expired';
  revoked_at: string | null;
  revoked_by: string;
  applied: boolean;
  apply_error: string;
}

export interface HealingOverview {
  materialization_enabled: boolean;
  signal_schema: string;
  episodes: HealingEpisodeRow[];
  patches: HealingPatch[];
  patches_total: number;
  corrections_total: number;
}

export interface HealingEpisodeDetail {
  episode: QuarantineEpisode;
  object_id: string;
  kind: string;
  four_eyes: boolean;
  columns: string[];
  key_columns: string[];
  row_capable: boolean;
  predicates: { check: string; type: string }[];
  skipped: { check: string; type: string; reason: string }[];
  remaining_bad_rows: number | null;
  release_ready: boolean;
  corrections: HealingCorrection[];
  correction_actors: string[];
}

export interface HealingPlan {
  object_id: string;
  enabled: boolean;
  signal_schema: string;
  h1: {
    quarantine_table: string;
    upgrade: string[];
    procedure: string;
    row_capable: boolean;
  } | null;
  h3: {
    patch_table: string;
    healed_view: string;
    key_columns: string[];
    patch_columns: string[];
    ddl: string[];
  } | null;
}

// ---- Garantie-Backtesting (POST /api/contracts/{p}/backtest) — V1 ----
export interface BacktestWindow {
  days: number;
  points: number;
  breaches: number;
}

export interface BacktestBreach {
  run_id: string;
  at: string;
  value: string | null;
  breach: boolean;
}

export interface BacktestCheck {
  check_name: string;
  expect: string;
  type: string;
  severity: string;
  points: number;
  evaluated: number;
  skipped: number;
  breaches: number;
  breach_rate: number;
  first_breach_at: string | null;
  last_breach_at: string | null;
  sample: BacktestBreach[];
  windows: BacktestWindow[];
}

export interface BacktestOut {
  product: string;
  dataset: string;
  window_days: number[];
  checks: BacktestCheck[];
  checks_total: number;
  checks_with_history: number;
  summary_windows: { days: number; breaches: number; checks_firing: number }[];
}

// ---- Data-Diff über Profil-Snapshots (POST /api/objects/{id}/diff) — Konzept §B ----
export interface MetricDelta {
  base: number | null;
  head: number | null;
  delta: number | null;
}

export interface ColumnDiff {
  column: string;
  metrics: Record<string, MetricDelta>;
  changed: boolean;
}

export interface DistributionDiff {
  row_count: { base: number | null; head: number | null; delta: number | null; pct_delta: number | null };
  column_count: { base: number | null; head: number | null; delta: number | null };
  columns: ColumnDiff[];
  added_columns: string[];
  removed_columns: string[];
  changed_columns: string[];
}

export interface KeyReconKey {
  column: string;
  base_distinct: number | null;
  head_distinct: number | null;
  distinct_delta: number | null;
  base_duplicates: boolean;
  head_duplicates: boolean;
}

export interface KeyReconciliation {
  key_columns: string[];
  base_rows: number | null;
  head_rows: number | null;
  row_delta: number | null;
  row_pct_delta: number | null;
  keys: KeyReconKey[];
}

export interface ObjectDiffSnapshotRef {
  snapshot_id: number;
  captured_at: string;
  environment: string;
}

export interface ObjectDiffResult {
  object_id: string;
  mode: 'distribution' | 'keys';
  base: ObjectDiffSnapshotRef;
  head: ObjectDiffSnapshotRef;
  distribution?: DistributionDiff;
  reconciliation?: KeyReconciliation;
}
