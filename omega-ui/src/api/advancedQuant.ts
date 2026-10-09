import { API_BASE, apiRequest } from './client';
import type { PostTradeTCAReportResponse, TCATradeItem, RoutingDiagnosticsResponse } from './client';

export type JobStatus = 'CREATED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'DEAD_LETTERED';

export interface ProvenanceEnvelope {
  source: string;
  dataset_id: string;
  dataset_version: string;
  as_of: string;
  computed_at: string;
  requested_pit_cutoff: string | null;
  effective_cutoff: string;
  input_timezone: string;
  normalized_timezone: 'UTC';
  cutoff_resolution: 'REQUESTED' | 'AS_OF_DEFAULT';
  max_included_available_at: string | null;
  excluded_future_rows: number;
  content_hash: string;
  artifact_uri: string | null;
  is_synthetic: false;
}

export interface ErrorEnvelope {
  error_code: string;
  message: string;
  request_id: string;
  retryable: boolean;
  details: Record<string, unknown> | null;
  timestamp: string;
}

export interface JobSubmitRequest {
  task_type: string;
  payload: Record<string, unknown>;
  pit_cutoff: string;
  max_attempts?: number;
}

export interface JobAcceptedResponse {
  job_id: string;
  status: 'QUEUED';
  job_url: string;
  stream_url: string;
  request_id: string;
  submitted_at: string;
  request_sha256: string;
}

export interface JobStatusResponse {
  job_id: string;
  task_type: string;
  status: JobStatus;
  progress_pct: number;
  stage: string;
  message: string;
  submitted_at: string;
  updated_at: string;
  pit_cutoff: string;
  request_sha256: string;
  attempt_count: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error: ErrorEnvelope | null;
}

export interface JobCancelResponse {
  job_id: string;
  status: JobStatus;
  cancellation_requested_at: string;
}

// Phase 2 Analytics Interfaces

export interface VpinHistoryPoint {
  time: string;
  vpin: number;
  buy_volume: number;
  sell_volume: number;
  price: number;
}

export interface VpinToxicityResponse {
  status: string;
  symbol: string;
  vpin: number;
  toxicity_level: 'LOW' | 'MODERATE' | 'HIGH' | 'TOXIC';
  bucket_volume: number;
  n_buckets: number;
  current_imbalance: number;
  history: VpinHistoryPoint[];
}

export interface DepthLadderLevel {
  level: number;
  price: number;
  volume: number;
  cumulative_volume: number;
  orders: number;
}

export interface OrderbookDepthWaterfallResponse {
  status: string;
  symbol: string;
  depth_levels: number;
  mid_price: number;
  spread: number;
  spread_bps: number;
  total_bid_depth: number;
  total_ask_depth: number;
  obi: number;
  bids: DepthLadderLevel[];
  asks: DepthLadderLevel[];
}

export interface ImpactCurvePoint {
  participation_rate: number;
  impact_bps: number;
  estimated_cost_vnd: number;
}

export interface MarketImpactResponse {
  status: string;
  symbol: string;
  order_size: number;
  average_daily_volume: number;
  volatility: number;
  arrival_price: number;
  impact_coefficient: number;
  point_impact_bps: number;
  point_cost_vnd: number;
  curve: ImpactCurvePoint[];
}

export interface FracDiffPoint {
  time: string;
  close: number;
  frac_diff: number | null;
}

export interface FracDiffResponse {
  status: string;
  symbol: string;
  d: number;
  window: number;
  memory_retention_score: number;
  correlation_with_raw: number;
  weights: number[];
  series: FracDiffPoint[];
}

export interface CircuitBreakerStatusResponse {
  status: string;
  symbol: string;
  as_of: string;
  is_safe: boolean;
  var_95_pct: number;
  cvar_95_pct: number;
  var_breached: boolean;
  cvar_breached: boolean;
  action: string;
  derisk: {
    target_multiplier: number;
    reason: string;
  };
  limit_lock: {
    is_locked: boolean;
    lock_type: string;
    can_buy: boolean;
    can_sell: boolean;
  };
}

export interface StressScenarioSimResult {
  id: string;
  name: string;
  market_shock: number;
  portfolio_impact_pct: number;
  severity: string;
}

export interface StressTestSimulateResponse {
  status: string;
  timestamp: string;
  weights_evaluated: Record<string, number>;
  average_loss_pct: number;
  scenarios: StressScenarioSimResult[];
  recommendation: string;
  provenance?: ProvenanceEnvelope;
}

export interface ContagionNode {
  id: string;
  label: string;
  type: string;
  stress: number;
  sri?: number;
  weight?: number;
}

export interface ContagionEdge {
  source: string;
  target: string;
  correlation: number;
  transmission_bps: number;
}

export interface ContagionRiskGraphResponse {
  status: string;
  is_safe: boolean;
  stress_level: string;
  risk_multiplier: number;
  dominant_source: string;
  narrative: string;
  nodes: ContagionNode[];
  edges: ContagionEdge[];
}

export interface LiquidityStressBreakdownItem {
  symbol: string;
  quantity: number;
  adv: number;
  exit_days: number;
  exceeds_limit: boolean;
}

export interface LiquidityStressValidateResponse {
  status: string;
  is_safe: boolean;
  max_exit_days: number;
  total_impact_bps: number;
  at_risk_symbols: string[];
  violation_message: string;
  breakdown: LiquidityStressBreakdownItem[];
  provenance?: ProvenanceEnvelope;
}

export interface CorporateGraphNode {
  id: string;
  label: string;
  category: string;
  sector: string;
  ownership_pct: number;
  role: string;
}

export interface CorporateGraphEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
  label: string;
}

export interface CorporateGraphResponse {
  status: string;
  symbol: string;
  sector: string;
  nodes_count: number;
  edges_count: number;
  nodes: CorporateGraphNode[];
  edges: CorporateGraphEdge[];
  provenance?: ProvenanceEnvelope | null;
}

// Phase 2 Multi-Ticker Network Graph Interfaces
export interface NetworkNodeItem {
  id: string;
  symbol: string;
  name: string;
  sector: string;
  ecosystem?: string | null;
  market_cap?: number | null;
  market_cap_str: string;
  adv20?: number | null;
  adv20_str: string;
  pe?: number | null;
  roe?: number | null;
  hybrid_score?: number | null;
  degree: number;
}

export interface NetworkEdgeItem {
  id: string;
  source: string;
  target: string;
  relationship: string;
  relationship_type: string;
  weight: number;
}

export interface EcosystemDefinitionItem {
  ecosystem_id: string;
  name: string;
  group_type: string;
  record_created_at_utc: string;
}

export interface NetworkGraphMetadata {
  taxonomy_name: string;
  taxonomy_source: string;
  taxonomy_version: string;
  canonicalization_version: string;
  as_of: string;
  resolved_as_of: string;
  nodes_count: number;
  edges_count: number;
  ecosystems_count: number;
  manifest_sha256: string;
  dataset_sha256: string;
  payload_sha256?: string;
}

export interface NetworkGraphApiResponse {
  status: string;
  metadata: NetworkGraphMetadata;
  nodes: NetworkNodeItem[];
  edges: NetworkEdgeItem[];
  ecosystems: EcosystemDefinitionItem[];
}

// Phase 3 Active Quant, Evolution & Smart Execution Interfaces

export interface WalkForwardFoldResult {
  fold: number;
  train_size: number;
  test_size: number;
  in_sample_sharpe: number | null;
  out_of_sample_sharpe: number | null;
  in_sample_return_pct: number;
  out_of_sample_return_pct: number;
  max_drawdown_pct: number;
}

export interface WalkForwardCpcvResponse {
  status: string;
  task_type: string;
  job_id: string;
  dataset_id: string;
  n_splits: number;
  n_test_splits: number;
  total_folds: number;
  mean_oos_sharpe: number | null;
  median_oos_sharpe: number | null;
  std_oos_sharpe: number | null;
  mean_oos_return_pct: number;
  worst_drawdown_pct: number;
  pbo: number | null;
  deflated_sharpe_ratio: number | null;
  folds: WalkForwardFoldResult[];
  provenance?: ProvenanceEnvelope | null;
}

export interface OverfittingDiagnosticsResponse {
  status: string;
  strategy_id: string;
  trials_tested: number;
  pbo: number | null;
  deflated_sharpe_ratio: number | null;
  observed_sharpe: number | null;
  expected_max_sharpe: number | null;
  variance_of_trials: number | null;
  skewness: number | null;
  kurtosis: number | null;
  fdr_q_values: number[];
  is_overfitted: boolean;
  verdict: string;
  provenance?: ProvenanceEnvelope | null;
}

export interface ConformalInterval {
  confidence_level: number;
  lower_price: number;
  upper_price: number;
  lower_return_pct: number;
  upper_return_pct: number;
  interval_width_pct: number;
}

export interface ConformalPredictResponse {
  status: string;
  symbol: string;
  as_of: string;
  point_forecast_price: number;
  point_forecast_return_pct: number;
  regime: string;
  liquidity_bucket: string;
  intervals: ConformalInterval[];
  empirical_coverage: number;
  is_valid_mondrian: boolean;
  provenance?: ProvenanceEnvelope | null;
}

export interface CallerSampleProvenance extends Omit<ProvenanceEnvelope, 'source' | 'dataset_id' | 'is_synthetic' | 'max_included_available_at'> {
  source: 'caller_sample';
  dataset_id: 'caller_sample';
  is_synthetic: true;
  pit_verified: false;
  max_included_available_at: null;
}

export interface AlphaEvaluationRequest {
  expression: string;
  universe?: string;
  sample_data?: Record<string, number[]>;
  as_of?: string;
  pit_cutoff?: string;
}

export interface AlphaDiscoveryRequest {
  population_size?: number;
  generations?: number;
  mutation_rate?: number;
  crossover_rate?: number;
  target_ic?: number;
  target_ir?: number;
  allowed_operators?: string[];
}

export interface AlphaDiscoveryEvent {
  session_id: string;
  event_type: 'SNAPSHOT' | 'GENERATION_UPDATE' | 'DISCOVERY_COMPLETED' | 'DISCOVERY_FAILED' | 'PING';
  generation: number;
  max_generations: number;
  progress: number;
  best_fitness: number;
  best_formula: string;
  timestamp: string;
}

export interface AlphaEvaluationResponse {
  status: string;
  expression: string;
  is_valid: boolean;
  ast_type: string;
  ic_estimate: number;
  ir_estimate: number;
  turnover_estimate_pct: number;
  complexity_score: number;
  sample_result?: number[] | null;
  error?: string | null;
  provenance?: ProvenanceEnvelope | CallerSampleProvenance | null;
}

export interface AlphaSignalItem {
  alpha_id: string;
  name: string;
  category: string;
  formula: string;
  ic_mean: number;
  ir_annualized: number;
  turnover_pct: number;
  status: 'ACTIVE' | 'CANDIDATE' | 'DECAYED' | 'INCUBATING';
}

export interface AlphaArsenalResponse {
  status: string;
  total_available: number;
  count: number;
  signals: AlphaSignalItem[];
  provenance?: ProvenanceEnvelope | null;
}

export interface DecayPoint {
  lag_days: number;
  ic: number;
  ir: number;
  correlation_decay: number;
}

export interface AlphaDecayProfileResponse {
  status: string;
  alpha_id: string;
  name: string;
  half_life_days: number;
  decay_regime: string;
  profile: DecayPoint[];
  provenance?: ProvenanceEnvelope | null;
}

export interface GeneticDiscoveryGenerationHistory {
  generation: number;
  max_generations: number;
  best_formula: string;
  best_fitness: number;
  mean_fitness: number;
  fittest_ic: number;
}

export interface GeneticDiscoveryResponse {
  session_id?: string | null;
  stream_url?: string | null;
  status: string;
  job_id: string;
  task_type: string;
  population_size: number;
  generations: number;
  best_formula: string;
  best_fitness: number;
  best_ic: number;
  best_ir: number;
  history: GeneticDiscoveryGenerationHistory[];
  provenance?: ProvenanceEnvelope | null;
}

export interface RebalanceOrderItem {
  order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | 'HOLD';
  quantity: number;
  price: number;
  estimated_notional_vnd: number;
  algo: 'TWAP' | 'VWAP' | 'POV' | 'DIRECT';
  slices: number;
  status: 'QUEUED' | 'SUBMITTED' | 'EXECUTED';
}

export interface PortfolioRebalanceExecuteResponse {
  status: string;
  job_id: string;
  timestamp: string;
  totp_verified: boolean;
  strategy_id: string;
  should_rebalance: boolean;
  reason: string;
  estimated_turnover: number;
  estimated_cost_vnd: number;
  orders: RebalanceOrderItem[];
  target_changes: Record<string, number>;
  liquidity_violations: string[];
  provenance?: ProvenanceEnvelope | null;
}

// Phase 4 Model Governance & Resource Governor Interfaces

export type ModelCategory = 'DEEP_LEARNING' | 'MACHINE_LEARNING' | 'ALPHA' | 'RISK_EXECUTION' | 'LLM' | 'HYBRID';

export interface ModelVersionItem {
  version: string;
  status: 'STAGING' | 'VALIDATED' | 'PRODUCTION' | 'ARCHIVED' | 'DEPRECATED';
  checksum?: string | null;
  artifact_path: string;
  registered_at: string;
  metadata: Record<string, any>;
}

export interface ModelSummaryItem {
  model_name: string;
  category?: ModelCategory;
  framework?: string | null;
  description?: string | null;
  source_path?: string | null;
  implementation_symbol?: string | null;
  active_versions: Record<string, string | null>;
  total_versions: number;
  latest_version?: string | null;
  last_updated?: string | null;
}

export interface ModelListResponse {
  status: string;
  count: number;
  models: ModelSummaryItem[];
  categories?: string[];
  selected_category?: string | null;
  category_counts?: Record<string, number>;
  provenance?: ProvenanceEnvelope | null;
}

export interface ModelVersionsResponse {
  status: string;
  model_name: string;
  category?: ModelCategory | null;
  framework?: string | null;
  description?: string | null;
  source_path?: string | null;
  implementation_symbol?: string | null;
  active_versions: Record<string, string | null>;
  versions: ModelVersionItem[];
  provenance?: ProvenanceEnvelope | null;
}

export interface ModelVersionDetailResponse {
  status: string;
  model_name: string;
  category?: ModelCategory | null;
  framework?: string | null;
  description?: string | null;
  source_path?: string | null;
  implementation_symbol?: string | null;
  version: string;
  version_info: ModelVersionItem;
  provenance?: ProvenanceEnvelope | null;
}

export interface DriftMetricItem {
  metric_name: string;
  baseline_value: number;
  current_value: number;
  drift_detected: boolean;
  threshold: number;
  p_value?: number | null;
}

export interface ModelDriftResponse {
  status: string;
  model_name: string;
  active_version?: string | null;
  drift_detected: boolean;
  drift_level: 'LOW' | 'MODERATE' | 'CRITICAL' | 'NONE';
  drift_score: number;
  evaluated_at: string;
  metrics: DriftMetricItem[];
  summary: Record<string, any>;
  provenance?: ProvenanceEnvelope | null;
}

export interface ModelPromoteResponse {
  status: string;
  model_name: string;
  version: string;
  target_status: 'VALIDATED' | 'PRODUCTION';
  totp_verified: boolean;
  promoted_at: string;
  message: string;
  provenance?: ProvenanceEnvelope | null;
}

export interface ModelRollbackResponse {
  status: string;
  model_name: string;
  target_version: string;
  totp_verified: boolean;
  rolled_back_at: string;
  previous_active_version?: string | null;
  message: string;
  provenance?: ProvenanceEnvelope | null;
}

export interface ResourceGovernorStateResponse {
  status: string;
  mode: 'MANUAL' | 'COPILOT';
  target_concurrency: number;
  thread_pool_size: number;
  batch_size: number;
  version: number;
  active_workers: number;
  queue_depth: number;
  system_load_pct: number;
  memory_usage_mb: number;
  mode_description: string;
  updated_at: string;
  provenance?: ProvenanceEnvelope | null;
}

export interface PitWindows {
  train_start_date: string;
  train_end_date: string;
  validation_start_date: string;
  validation_end_date: string;
  test_start_date: string;
  test_end_date: string;
}

export interface EvolutionRunRequest {
  dataset?: string;
  pit_cutoff: string;
  strategy_id?: string;
  seeds?: number[];
  population?: number;
  generations?: number;
  workers?: number;
  transaction_cost_bps?: number;
  windows?: PitWindows;
  risk_parameters?: Record<string, unknown>;
}

export interface SeedResult {
  seed: number;
  status: 'COMPLETED' | 'FAILED' | 'SKIPPED';
  sharpe: number | null;
  ic: number | null;
  max_drawdown: number | null;
  turnover: number | null;
  trade_count: number;
  artifact_reference?: string | null;
  failure_code?: string | null;
}

export interface EvolutionSummary {
  status: 'success' | 'partial' | 'failed';
  strategy_id: string;
  requested_seeds: number;
  completed_seeds: number;
  failed_seeds: number;
  median_sharpe: number | null;
  iqr_sharpe: number | null;
  std_sharpe: number | null;
  worst_drawdown: number | null;
  median_ic: number | null;
  median_turnover: number | null;
  seed_results: SeedResult[];
  provenance?: ProvenanceEnvelope | null;
}

export interface DriftScheduleRequest {
  enabled?: boolean;
  schedule?: string;
  timezone?: string;
  model_ids?: string[];
  thresholds?: Record<string, number>;
  revision: number;
}

export interface DriftMonitorAlert {
  alert_id: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  timestamp: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface DriftMonitorStatus {
  status: string;
  enabled: boolean;
  schedule: string;
  timezone: string;
  last_run: string | null;
  next_run: string | null;
  heartbeat: string;
  evaluated_model_ids: string[];
  missing_model_ids: string[];
  alerts: DriftMonitorAlert[];
  last_job: Record<string, unknown> | null;
  thresholds: Record<string, number>;
  revision: number;
  provenance?: ProvenanceEnvelope | null;
}

export interface AdvancedQuantRequestOptions extends RequestInit {
  timeoutMs?: number;
  maxRetries?: number;
  retryDelayMs?: number;
}

export async function resilientApiRequest<T>(
  path: string,
  options: AdvancedQuantRequestOptions = {}
): Promise<T> {
  const {
    timeoutMs = 10000,
    maxRetries = 3,
    retryDelayMs = 100,
    signal,
    ...fetchInit
  } = options;

  let attempt = 0;
  while (true) {
    attempt++;
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    let onAbort: (() => void) | undefined;
    if (signal) {
      if (signal.aborted) {
        clearTimeout(timer);
        throw new DOMException('Aborted', 'AbortError');
      }
      onAbort = () => controller.abort();
      signal.addEventListener('abort', onAbort);
    }

    try {
      return await apiRequest<T>(path, {
        ...fetchInit,
        signal: controller.signal,
      });
    } catch (err: any) {
      if (timedOut) {
        throw new Error(`Request to ${path} timed out after ${timeoutMs}ms`);
      }
      if (signal?.aborted) {
        throw err;
      }
      const is429 = err?.status === 429 || (typeof err?.message === 'string' && err.message.includes('429'));
      if (is429 && attempt <= maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs * attempt));
        continue;
      }
      throw err;
    } finally {
      clearTimeout(timer);
      if (signal && onAbort) {
        signal.removeEventListener('abort', onAbort);
      }
    }
  }
}

export function formatAlphaMetric(value: unknown, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12
    ? value.toFixed(digits) : '--';
}

function alphaFields(value: unknown, allowed: string[]): void {
  if (Object.keys(alphaRecord(value)).some((key) => !allowed.includes(key))) throw new Error('INVALID_ALPHA_PAYLOAD');
}

function alphaRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('INVALID_ALPHA_PAYLOAD');
  return value as Record<string, unknown>;
}

function alphaNumber(value: unknown, min = -1e12, max = 1e12, integer = false): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) {
    throw new Error('INVALID_ALPHA_NUMBER');
  }
  return value;
}

function alphaText(value: unknown, max: number, empty = false): string {
  if (typeof value !== 'string' || value.length > max || (!empty && !value.trim())) throw new Error('INVALID_ALPHA_TEXT');
  return value;
}

function alphaArray(value: unknown, max: number): unknown[] {
  if (!Array.isArray(value) || value.length > max) throw new Error('INVALID_ALPHA_ARRAY');
  return value;
}

function alphaTimestamp(value: unknown): number {
  const text = alphaText(value, 64);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new Error('INVALID_ALPHA_TIMESTAMP');
  }
  if (new Date(`${text.slice(0, 10)}T00:00:00Z`).toISOString().slice(0, 10) !== text.slice(0, 10) || Number(text.slice(11, 13)) > 23 || Number(text.slice(14, 16)) > 59 || Number(text.slice(17, 19)) > 59) throw new Error('INVALID_ALPHA_TIMESTAMP');
  return Date.parse(text);
}

export function validateAlphaProvenance(value: unknown): void {
  if (value == null) return;
  const p = alphaRecord(value);
  alphaText(p.source, 64); alphaText(p.dataset_id, 128); alphaText(p.dataset_version, 128);
  if (typeof p.content_hash !== 'string' || !/^[0-9a-f]{64}$/.test(p.content_hash)) throw new Error('INVALID_ALPHA_PIT');
  alphaTimestamp(p.computed_at);
  alphaNumber(p.excluded_future_rows, 0, 1e12, true);
  const asOf = alphaTimestamp(p.as_of);
  const cutoff = alphaTimestamp(p.effective_cutoff);
  if (cutoff > asOf || p.normalized_timezone !== 'UTC') throw new Error('INVALID_ALPHA_PIT');
  if (p.requested_pit_cutoff != null && alphaTimestamp(p.requested_pit_cutoff) !== cutoff) throw new Error('INVALID_ALPHA_PIT');
  if (p.source === 'caller_sample') {
    if (p.dataset_id !== 'caller_sample' || p.excluded_future_rows !== 0 || p.is_synthetic !== true || p.pit_verified !== false || p.input_timezone !== 'UNVERIFIED' || p.max_included_available_at !== null) {
      throw new Error('INVALID_ALPHA_PIT');
    }
  } else if (p.is_synthetic !== false || p.pit_verified === false || (p.max_included_available_at != null && alphaTimestamp(p.max_included_available_at) > cutoff)) {
    throw new Error('INVALID_ALPHA_PIT');
  }
}

export function validateAlphaEvaluation(value: unknown): AlphaEvaluationResponse {
  const r = alphaRecord(value);
  alphaText(r.expression, 4096);
  alphaText(r.ast_type, 64);
  if (r.status !== 'success' || typeof r.is_valid !== 'boolean') throw new Error('INVALID_ALPHA_PAYLOAD');
  alphaNumber(r.ic_estimate, -1, 1);
  alphaNumber(r.ir_estimate);
  alphaNumber(r.turnover_estimate_pct, 0, 100);
  alphaNumber(r.complexity_score, 1, 10000, true);
  if (r.sample_result != null) alphaArray(r.sample_result, 10).forEach((v) => alphaNumber(v));
  if (r.error != null) alphaText(r.error, 4096, true);
  validateAlphaProvenance(r.provenance);
  return value as AlphaEvaluationResponse;
}

export function validateAlphaArsenal(value: unknown): AlphaArsenalResponse {
  const r = alphaRecord(value);
  if (r.status !== 'success') throw new Error('INVALID_ALPHA_PAYLOAD');
  alphaNumber(r.total_available, 0, 1e12, true);
  const signals = alphaArray(r.signals, 1000);
  if (alphaNumber(r.count, 0, 1000, true) !== signals.length || (r.total_available as number) < signals.length) throw new Error('INVALID_ALPHA_PAYLOAD');
  const ids = new Set<string>();
  signals.forEach((value) => {
    const s = alphaRecord(value);
    const id = alphaText(s.alpha_id, 64);
    if (ids.has(id) || !['ACTIVE', 'CANDIDATE', 'DECAYED', 'INCUBATING'].includes(s.status as string)) throw new Error('INVALID_ALPHA_PAYLOAD');
    ids.add(id);
    alphaText(s.name, 256); alphaText(s.category, 64); alphaText(s.formula, 4096);
    alphaNumber(s.ic_mean, -1, 1); alphaNumber(s.ir_annualized); alphaNumber(s.turnover_pct, 0, 100);
  });
  validateAlphaProvenance(r.provenance);
  return value as AlphaArsenalResponse;
}

export function validateAlphaDecay(value: unknown): AlphaDecayProfileResponse {
  const r = alphaRecord(value);
  if (r.status !== 'success') throw new Error('INVALID_ALPHA_PAYLOAD');
  alphaText(r.alpha_id, 64); alphaText(r.name, 256); alphaText(r.decay_regime, 128);
  alphaNumber(r.half_life_days, 1, 1e12);
  let previousLag = 0;
  alphaArray(r.profile, 1000).forEach((value) => {
    const p = alphaRecord(value);
    previousLag = alphaNumber(p.lag_days, previousLag + 1, 1e12, true);
    alphaNumber(p.ic, -1, 1); alphaNumber(p.ir); alphaNumber(p.correlation_decay, 0, 1);
  });
  validateAlphaProvenance(r.provenance);
  return value as AlphaDecayProfileResponse;
}

export function validateAlphaDiscoveryEvent(value: unknown, sessionId: string): AlphaDiscoveryEvent {
  const r = alphaRecord(value);
  if (r.session_id !== sessionId || !['SNAPSHOT', 'GENERATION_UPDATE', 'DISCOVERY_COMPLETED', 'DISCOVERY_FAILED', 'PING'].includes(r.event_type as string)) throw new Error('INVALID_ALPHA_EVENT');
  if (r.event_type === 'PING' || r.event_type === 'DISCOVERY_FAILED') return value as AlphaDiscoveryEvent;
  const max = alphaNumber(r.max_generations, 1, 100, true);
  alphaNumber(r.generation, 0, max, true); alphaNumber(r.progress, 0, 100);
  alphaNumber(r.best_fitness); alphaText(r.best_formula, 1024, r.event_type === 'SNAPSHOT'); alphaTimestamp(r.timestamp);
  if (r.event_type === 'DISCOVERY_COMPLETED' && (r.progress !== 100 || r.generation !== max)) throw new Error('INVALID_ALPHA_EVENT');
  return value as AlphaDiscoveryEvent;
}

function validateAlphaDiscovery(value: unknown): GeneticDiscoveryResponse {
  const r = alphaRecord(value);
  if (r.status !== 'success') throw new Error('INVALID_ALPHA_PAYLOAD');
  alphaText(r.job_id, 64);
  const max = alphaNumber(r.generations, 1, 100, true);
  alphaNumber(r.population_size, 10, 500, true);
  alphaNumber(r.best_fitness); alphaNumber(r.best_ic, -1, 1); alphaNumber(r.best_ir);
  alphaText(r.best_formula, 1024);
  if (r.stream_url != null) alphaText(r.stream_url, 256);
  if (r.session_id != null) alphaText(r.session_id, 64);
  let generation = 0;
  alphaArray(r.history, 100).forEach((value) => {
    const h = alphaRecord(value);
    generation = alphaNumber(h.generation, generation + 1, max, true);
    if (h.max_generations !== max) throw new Error('INVALID_ALPHA_PAYLOAD');
    alphaText(h.best_formula, 1024); alphaNumber(h.best_fitness); alphaNumber(h.mean_fitness); alphaNumber(h.fittest_ic, -1, 1);
  });
  validateAlphaProvenance(r.provenance);
  return value as GeneticDiscoveryResponse;
}

export function alphaDiscoveryUrl(streamUrl: string, sessionId?: string): string {
  const url = new URL(streamUrl, API_BASE);
  const base = new URL(API_BASE);
  if (url.origin !== base.origin || url.username || url.password || url.hash || url.pathname !== '/sse/v1/alpha/discovery/stream') throw new Error('INVALID_ALPHA_STREAM_URL');
  if (sessionId !== undefined && (url.searchParams.getAll('session_id').length !== 1 || url.searchParams.get('session_id') !== sessionId)) throw new Error('INVALID_ALPHA_STREAM_URL');
  return url.toString();
}

export function alphaErrorMessage(error: unknown): string {
  const code = (error as { code?: unknown } | null)?.code;
  if (code === 'DATA_DEPENDENCY_UNAVAILABLE' || code === 'DATA_NOT_FOUND') return String(code);
  return 'Alpha request failed. Retry with valid inputs and available data.';
}

export const BARRA_FACTORS = ['market_beta', 'size_smb', 'value_hml', 'momentum', 'volatility', 'liquidity', 'quality', 'leverage'] as const;
export type BarraFactor = typeof BARRA_FACTORS[number];
export interface BarraAssetInput extends Record<BarraFactor, number> {
  symbol: string; sector: string; weight_pct: number; specific_risk_pct: number;
}
export interface BarraRequest {
  assets: BarraAssetInput[];
  factor_covariance: number[][];
  specific_variances?: number[] | null;
  covariance_unit?: 'annualized_pct_squared' | 'annualized_decimal_squared';
}
interface CallerRiskEstimate {
  status: 'success'; source: 'request_factor_covariance' | 'request_market_observations';
  schema_version: string; data_status: 'estimated'; is_synthetic: false;
  provenance_status: 'caller_supplied_unverified'; pit_verified: false;
  units: Record<string, string>;
}
export interface BarraResponse extends CallerRiskEstimate {
  timestamp: string; factor_variance: number; specific_variance: number; total_variance: number;
  total_risk_annualized_pct: number; factor_order: BarraFactor[];
  factor_exposures: Record<BarraFactor, number>;
  factor_variance_contributions: Record<BarraFactor, number>;
  asset_exposures: BarraAssetInput[];
}
export interface TcaImpactRequest {
  symbol: string; order_size: number; average_daily_volume: number; volatility: number;
  participation_rate: number; side: 'BUY' | 'SELL'; arrival_price: number; observed_spread_bps: number;
}
export interface TcaImpactResponse extends CallerRiskEstimate {
  symbol: string; side: 'BUY' | 'SELL'; estimated_impact_bps: number;
  spread_cost_bps: number; total_cost_bps: number; total_cost_vnd: number;
}
export type TcaReport = Omit<PostTradeTCAReportResponse, 'trades'> & {
  trades: (Omit<TCATradeItem, 'pre_trade_impact_bps'> & { pre_trade_impact_bps: number | null })[];
};
export type RoutingReport = Omit<RoutingDiagnosticsResponse, 'avg_roundtrip_latency_ms' | 'routers'> & {
  avg_roundtrip_latency_ms: number | null;
  routers: (Omit<RoutingDiagnosticsResponse['routers'][number], 'status' | 'ping_ms'> & { status: 'DATA_ONLY'; ping_ms: number | null })[];
};
export interface StressRequest {
  portfolio_weights: Record<string, number>; market_shock_pct?: number;
  volatility_shock_multiplier?: number; include_contagion?: boolean;
}
export interface LiquidityRequest {
  positions: Record<string, number>; max_adv_participation?: number;
  max_exit_days?: number; market_impact_coefficient?: number;
}

export const formatRiskMetric = formatAlphaMetric;
export function riskErrorMessage(error: unknown): string {
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === 'string' && ['DATA_DEPENDENCY_UNAVAILABLE', 'DATA_NOT_FOUND', 'BARRA_FACTOR_MODEL_UNAVAILABLE', 'STRESS_MODEL_UNAVAILABLE', 'INSUFFICIENT_MARKET_HISTORY'].includes(code)
    ? code : 'Risk request failed. Check inputs and available data.';
}
function riskSymbol(value: unknown): string {
  const symbol = alphaText(value, 12).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,12}$/.test(symbol)) throw new Error('INVALID_RISK_SYMBOL');
  return symbol;
}
function riskMap(value: unknown, positive: boolean, max: number): Record<string, number> {
  const entries = Object.entries(alphaRecord(value));
  if (!entries.length || entries.length > 703) throw new Error('INVALID_RISK_INPUT');
  const result: Record<string, number> = {};
  for (const [symbol, amount] of entries) {
    const key = riskSymbol(symbol);
    if (Object.hasOwn(result, key)) throw new Error('INVALID_RISK_INPUT');
    result[key] = alphaNumber(amount, positive ? Number.MIN_VALUE : 0, max);
  }
  if (!Object.values(result).some((v) => v > 0)) throw new Error('INVALID_RISK_INPUT');
  return result;
}
function riskClose(actual: number, expected: number): void {
  if (!Number.isFinite(actual) || !Number.isFinite(expected) || Math.abs(actual - expected) > 1e-8 * Math.max(1, Math.abs(expected))) throw new Error('INVALID_RISK_METRICS');
}
function riskCaller(value: unknown, schema: string, source: string, units: Record<string, string>): Record<string, unknown> {
  const r = alphaRecord(value);
  if (r.status !== 'success' || r.schema_version !== schema || r.source !== source || r.data_status !== 'estimated' || r.is_synthetic !== false || r.provenance_status !== 'caller_supplied_unverified' || r.pit_verified !== false || r.provenance != null) throw new Error('INVALID_RISK_PROVENANCE');
  const actual = alphaRecord(r.units);
  if (Object.keys(actual).length !== Object.keys(units).length || Object.entries(units).some(([k, v]) => actual[k] !== v)) throw new Error('INVALID_RISK_UNITS');
  return r;
}
function riskHistorical(value: unknown, dataset: string): void {
  const p = alphaRecord(value);
  alphaFields(p, ['source', 'dataset_id', 'dataset_version', 'as_of', 'computed_at', 'requested_pit_cutoff', 'effective_cutoff', 'input_timezone', 'normalized_timezone', 'cutoff_resolution', 'max_included_available_at', 'excluded_future_rows', 'content_hash', 'artifact_uri', 'is_synthetic']);
  if (p.dataset_id !== dataset || !['REQUESTED', 'AS_OF_DEFAULT'].includes(p.cutoff_resolution as string)) throw new Error('INVALID_RISK_PROVENANCE');
  alphaText(p.input_timezone, 64);
  if (p.artifact_uri !== null) alphaText(p.artifact_uri, 4096);
  validateAlphaProvenance(p);
  if (p.is_synthetic !== false || p.source === 'caller_sample' || p.max_included_available_at == null || alphaTimestamp(p.computed_at) < alphaTimestamp(p.as_of)) throw new Error('INVALID_RISK_PROVENANCE');
}
function riskAssets(value: unknown): BarraAssetInput[] {
  const assets = alphaArray(value, 703);
  if (!assets.length) throw new Error('INVALID_RISK_INPUT');
  const symbols = new Set<string>();
  assets.forEach((item) => {
    const a = alphaRecord(item);
    alphaFields(a, ['symbol', 'sector', 'weight_pct', 'specific_risk_pct', ...BARRA_FACTORS]);
    const symbol = riskSymbol(a.symbol);
    if (symbol !== a.symbol || symbols.has(symbol)) throw new Error('INVALID_RISK_SYMBOL');
    symbols.add(symbol); alphaText(a.sector, 128);
    alphaNumber(a.weight_pct, 0, 100); alphaNumber(a.specific_risk_pct, 0);
    BARRA_FACTORS.forEach((key) => alphaNumber(a[key]));
  });
  if (!assets.some((a) => (a as BarraAssetInput).weight_pct > 0)) throw new Error('INVALID_RISK_INPUT');
  return assets as BarraAssetInput[];
}
export function validateBarraRequest(value: unknown): BarraRequest {
  const r = alphaRecord(value);
  alphaFields(r, ['assets', 'factor_covariance', 'specific_variances', 'covariance_unit']);
  const assets = riskAssets(r.assets);
  const matrix = alphaArray(r.factor_covariance, 8);
  if (matrix.length !== 8) throw new Error('INVALID_RISK_INPUT');
  matrix.forEach((row) => {
    const cells = alphaArray(row, 8);
    if (cells.length !== 8) throw new Error('INVALID_RISK_INPUT');
    cells.forEach((v) => alphaNumber(v));
  });
  if (r.specific_variances != null) {
    const variances = alphaArray(r.specific_variances, 703);
    if (variances.length !== assets.length) throw new Error('INVALID_RISK_INPUT');
    variances.forEach((v) => alphaNumber(v, 0));
  }
  if (r.covariance_unit !== undefined && !['annualized_pct_squared', 'annualized_decimal_squared'].includes(r.covariance_unit as string)) throw new Error('INVALID_RISK_UNITS');
  // ponytail: PSD and covariance normalization remain the backend's responsibility.
  return value as BarraRequest;
}
export function validateBarraResponse(value: unknown): BarraResponse {
  const r = riskCaller(value, 'barra.v1', 'request_factor_covariance', { exposure: 'dimensionless', weight: 'pct', risk: 'annualized_pct', variance: 'annualized_pct_squared' });
  alphaFields(r, ['status', 'timestamp', 'is_synthetic', 'source', 'factor_variance', 'specific_variance', 'total_variance', 'total_risk_annualized_pct', 'factor_exposures', 'factor_variance_contributions', 'asset_exposures', 'factor_order', 'schema_version', 'units', 'data_status', 'provenance_status', 'pit_verified']);
  alphaTimestamp(r.timestamp);
  const factor = alphaNumber(r.factor_variance, 0), specific = alphaNumber(r.specific_variance, 0), total = alphaNumber(r.total_variance, 0);
  riskClose(total, factor + specific); riskClose(alphaNumber(r.total_risk_annualized_pct, 0) ** 2, total);
  if (JSON.stringify(r.factor_order) !== JSON.stringify(BARRA_FACTORS)) throw new Error('INVALID_RISK_FACTORS');
  const exposures = alphaRecord(r.factor_exposures), contributions = alphaRecord(r.factor_variance_contributions);
  alphaFields(exposures, [...BARRA_FACTORS]); alphaFields(contributions, [...BARRA_FACTORS]);
  BARRA_FACTORS.forEach((key) => { alphaNumber(exposures[key]); alphaNumber(contributions[key]); });
  riskClose(Object.values(contributions).reduce<number>((sum, v) => sum + (v as number), 0), factor);
  const assets = riskAssets(r.asset_exposures);
  riskClose(assets.reduce((sum, a) => sum + a.weight_pct, 0), 100);
  return value as BarraResponse;
}
export function validateImpactRequest(value: unknown): TcaImpactRequest {
  const r = alphaRecord(value);
  alphaFields(r, ['symbol', 'order_size', 'average_daily_volume', 'volatility', 'participation_rate', 'side', 'arrival_price', 'observed_spread_bps']);
  riskSymbol(r.symbol);
  ['order_size', 'average_daily_volume'].forEach((k) => alphaNumber(r[k], Number.MIN_VALUE));
  alphaNumber(r.arrival_price, 1000 + Number.EPSILON * 1000);
  ['volatility', 'participation_rate'].forEach((k) => alphaNumber(r[k], Number.MIN_VALUE, 1));
  alphaNumber(r.observed_spread_bps, 0);
  if (!['BUY', 'SELL'].includes(r.side as string)) throw new Error('INVALID_RISK_INPUT');
  return value as TcaImpactRequest;
}
export function validateImpactResponse(value: unknown, request: TcaImpactRequest): TcaImpactResponse {
  const r = riskCaller(value, 'tca.v1', 'request_market_observations', { price: 'VND_FULL', quantity: 'shares', cost: 'bps', total_cost: 'VND_FULL', volatility: 'daily_decimal' });
  alphaFields(r, ['status', 'symbol', 'side', 'estimated_impact_bps', 'spread_cost_bps', 'total_cost_bps', 'total_cost_vnd', 'is_synthetic', 'source', 'schema_version', 'data_status', 'provenance_status', 'pit_verified', 'units']);
  if (r.symbol !== riskSymbol(request.symbol) || r.side !== request.side) throw new Error('INVALID_RISK_BINDING');
  const impact = alphaNumber(r.estimated_impact_bps, 0), spread = alphaNumber(r.spread_cost_bps, 0), cost = alphaNumber(r.total_cost_bps, 0);
  riskClose(spread, request.observed_spread_bps); riskClose(cost, impact + spread);
  riskClose(alphaNumber(r.total_cost_vnd, 0), request.order_size * request.arrival_price * cost / 10000);
  return value as TcaImpactResponse;
}
export function validateStressResponse(value: unknown, request: StressRequest): StressTestSimulateResponse {
  const r = alphaRecord(value);
  alphaFields(r, ['status', 'timestamp', 'weights_evaluated', 'average_loss_pct', 'scenarios', 'recommendation', 'provenance']);
  if (r.status !== 'success') throw new Error('INVALID_RISK_RESPONSE');
  alphaTimestamp(r.timestamp); alphaNumber(r.average_loss_pct); alphaText(r.recommendation, 4096);
  const weights = riskMap(r.weights_evaluated, false, 1), expected = riskMap(request.portfolio_weights, false, 1);
  const sum = Object.values(expected).reduce((a, b) => a + b, 0);
  if (Object.keys(weights).length !== Object.keys(expected).length) throw new Error('INVALID_RISK_BINDING');
  Object.entries(expected).forEach(([key, weight]) => riskClose(weights[key], weight / sum));
  const scenarios = alphaArray(r.scenarios, 100);
  if (!scenarios.length) throw new Error('INVALID_RISK_RESPONSE');
  const ids = new Set<string>();
  scenarios.forEach((item) => {
    const s = alphaRecord(item), id = alphaText(s.id, 128);
    alphaFields(s, ['id', 'name', 'market_shock', 'portfolio_impact_pct', 'severity']);
    if (ids.has(id)) throw new Error('INVALID_RISK_RESPONSE');
    ids.add(id); alphaText(s.name, 256); alphaText(s.severity, 64);
    alphaNumber(s.market_shock); alphaNumber(s.portfolio_impact_pct);
  });
  riskHistorical(r.provenance, 'stress_test_simulate');
  return value as StressTestSimulateResponse;
}
export function validateLiquidityResponse(value: unknown, request: LiquidityRequest): LiquidityStressValidateResponse {
  const r = alphaRecord(value), positions = riskMap(request.positions, true, 1e12);
  alphaFields(r, ['status', 'is_safe', 'max_exit_days', 'total_impact_bps', 'at_risk_symbols', 'violation_message', 'breakdown', 'provenance']);
  if (r.status !== 'success' || typeof r.is_safe !== 'boolean') throw new Error('INVALID_RISK_RESPONSE');
  alphaNumber(r.max_exit_days, 0); alphaNumber(r.total_impact_bps, 0); alphaText(r.violation_message, 4096, true);
  const rows = alphaArray(r.breakdown, 703), seen = new Set<string>(), atRisk: string[] = [];
  if (rows.length !== Object.keys(positions).length) throw new Error('INVALID_RISK_BINDING');
  rows.forEach((item) => {
    const b = alphaRecord(item), symbol = riskSymbol(b.symbol);
    alphaFields(b, ['symbol', 'quantity', 'adv', 'exit_days', 'exceeds_limit']);
    if (symbol !== b.symbol || seen.has(symbol) || !Object.hasOwn(positions, symbol) || typeof b.exceeds_limit !== 'boolean') throw new Error('INVALID_RISK_RESPONSE');
    seen.add(symbol); riskClose(alphaNumber(b.quantity, Number.MIN_VALUE), positions[symbol]);
    const adv = alphaNumber(b.adv, Number.MIN_VALUE), days = alphaNumber(b.exit_days, 0);
    riskClose(days, positions[symbol] / (adv * (request.max_adv_participation ?? 0.1)));
    if (b.exceeds_limit !== (days > (request.max_exit_days ?? 3))) throw new Error('INVALID_RISK_RESPONSE');
    if (b.exceeds_limit) atRisk.push(symbol);
  });
  riskClose(r.max_exit_days as number, Math.max(...rows.map((row) => (row as { exit_days: number }).exit_days)));
  const reported = alphaArray(r.at_risk_symbols, 703).map(riskSymbol).sort();
  if (JSON.stringify(reported) !== JSON.stringify(atRisk.sort()) || r.is_safe !== (atRisk.length === 0)) throw new Error('INVALID_RISK_RESPONSE');
  riskHistorical(r.provenance, 'liquidity_stress_validate');
  return value as LiquidityStressValidateResponse;
}
export function validateTcaReport(value: unknown): TcaReport {
  const r = alphaRecord(value), summary = alphaRecord(r.summary);
  if (r.status !== 'success') throw new Error('INVALID_RISK_RESPONSE');
  alphaTimestamp(r.timestamp);
  const trades = alphaArray(r.trades, 5000), seen = new Set<string>();
  if (!trades.length || alphaNumber(summary.num_trades, 1, 5000, true) !== trades.length) throw new Error('INVALID_RISK_RESPONSE');
  ['average_is_bps', 'average_slippage_bps', 'max_is_bps', 'min_is_bps', 'total_savings_vs_arrival_bps'].forEach((k) => alphaNumber(summary[k]));
  alphaNumber(summary.total_traded_value_billion_vnd, 0);
  trades.forEach((item) => {
    const t = alphaRecord(item), id = alphaText(t.trade_id, 128);
    if (seen.has(id) || !['BUY', 'SELL'].includes(t.side as string)) throw new Error('INVALID_RISK_RESPONSE');
    seen.add(id); riskSymbol(t.symbol); alphaText(t.timestamp, 64, true); alphaText(t.broker, 64); alphaText(t.algo, 64); alphaText(t.status, 64);
    ['parent_quantity', 'filled_quantity', 'avg_fill_price', 'benchmark_price', 'traded_value_vnd'].forEach((k) => alphaNumber(t[k], Number.MIN_VALUE));
    if ((t.filled_quantity as number) > (t.parent_quantity as number) || (t.avg_fill_price as number) <= 1000 || (t.benchmark_price as number) <= 1000) throw new Error('INVALID_RISK_RESPONSE');
    ['post_trade_slippage_bps', 'implementation_shortfall_bps'].forEach((k) => alphaNumber(t[k]));
    if (t.pre_trade_impact_bps !== null) alphaNumber(t.pre_trade_impact_bps, 0);
    riskClose(t.traded_value_vnd as number, (t.avg_fill_price as number) * (t.filled_quantity as number));
  });
  return value as TcaReport;
}
export function validateRoutingReport(value: unknown): RoutingReport {
  const r = alphaRecord(value);
  if (r.status !== 'success' || r.engine !== 'paper_trading') throw new Error('INVALID_RISK_RESPONSE');
  alphaTimestamp(r.timestamp);
  ['total_active_orders', 'total_active_slices'].forEach((k) => alphaNumber(r[k], 0, 5000, true));
  if (r.avg_roundtrip_latency_ms !== null) alphaNumber(r.avg_roundtrip_latency_ms, 0);
  alphaArray(r.routers, 100).forEach((item) => {
    const b = alphaRecord(item);
    alphaText(b.broker, 64); alphaText(b.channel, 128);
    if (b.status !== 'DATA_ONLY' || b.ping_ms !== null) throw new Error('INVALID_RISK_RESPONSE');
    ['fill_rate_pct', 'rejection_rate_pct'].forEach((k) => alphaNumber(b[k], 0, 100));
    if (b.price_improvement_bps !== null) alphaNumber(b.price_improvement_bps);
    alphaNumber(b.active_routes, 0, 5000, true);
  });
  alphaArray(r.active_queues, 5000).forEach((item) => {
    const q = alphaRecord(item); alphaText(q.queue_id, 128); riskSymbol(q.symbol); alphaText(q.algo, 64);
    ['active_slices', 'total_slices', 'target_qty', 'filled_qty'].forEach((k) => alphaNumber(q[k], 0));
    alphaNumber(q.completion_pct, 0, 100); alphaNumber(q.obi_pressure, -1, 1);
  });
  return value as RoutingReport;
}
async function riskRequest<T>(path: string, validate: (value: unknown) => T, signal?: AbortSignal, payload?: unknown): Promise<T> {
  try {
    return validate(await resilientApiRequest<unknown>(path, { signal, maxRetries: 0, ...(payload === undefined ? {} : { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } }) }));
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    throw new Error(riskErrorMessage(error));
  }
}

export interface PortfolioReadRequest { as_of?: string }
export interface PortfolioUniverseRequest extends PortfolioReadRequest {
  min_adv_billion?: number; top_n?: number; sector_cap?: number; min_score?: number;
}
export interface TargetPortfolioHolding {
  symbol: string; weight: number; marketValueBillionVnd: number; adv20BillionVnd: number;
  alphaScore: number; sector: string; barraMomentum: null; barraValue: null; barraSize: null;
  turnoverContribution: null; unrealizedPnlPercent: null;
}
export interface TargetPortfolioState {
  status: 'success'; account_model: 'target_institutional_allocation';
  weighting_method: 'hrp' | 'hrp_inverse_vol_fallback'; timestamp: string; price_scale: 'VND_FULL';
  nav_method: 'fixed_weight_daily_basket_estimate_not_realized_performance';
  aum_method: 'candidate_market_cap_reference_not_broker_assets';
  total_aum_vnd: number; totalAumBillionVnd: number; unallocated_cash_vnd: number; cash_balance_vnd: number;
  hrp_weights: Record<string, number>; holdings: TargetPortfolioHolding[];
  nav_history: { timestamp: string; nav_vnd: number }[];
  drawdown_series: { timestamp: string; drawdown_percent: number }[];
  maxDrawdownEstimatePercent: number; expectedIrAnnualized: null; portfolioBeta: null;
  dailyTurnoverEstimatePercent: null; icMean: null; icTStat: null; cvar99Percent: null;
  provenance: ProvenanceEnvelope;
}
export interface PortfolioUniverseResponse {
  status: 'success'; timestamp: string; selector_model: 'hybrid_rank_sector_capped';
  symbols: string[]; selected_symbols: string[]; scores: Record<string, number>;
  sector_weights: Record<string, number>; total_evaluated: number; total_selected: number;
  selected_details: { symbol: string; sector: string; score: number; adv_billion_vnd: number; status: 'ACTIVE' | 'QUALIFIED' | 'WATCH' }[];
  excluded_summary: Record<string, string>; units: { adv: 'billion_vnd'; weight: 'fraction' };
  provenance: ProvenanceEnvelope;
}

export function portfolioErrorMessage(error: unknown): string {
  const code = (error as { errorCode?: unknown } | null)?.errorCode ?? (error instanceof Error ? error.message : undefined);
  return typeof code === 'string' && ['DATASET_PIT_INVALID', 'DATA_DEPENDENCY_UNAVAILABLE', 'DATA_SCHEMA_INVALID', 'TRADING_CALENDAR_UNAVAILABLE', 'PIT_CUTOFF_INVALID'].includes(code)
    ? code : 'Portfolio request failed. Check inputs and available data.';
}
function portfolioFields(value: unknown, fields: string[]): Record<string, unknown> {
  const record = alphaRecord(value);
  if (Object.keys(record).length !== fields.length || fields.some((key) => !Object.hasOwn(record, key))) throw new Error('DATA_SCHEMA_INVALID');
  return record;
}
function portfolioSector(value: unknown): string {
  const text = alphaText(value, 80);
  if (text.trim() !== text || /[\r\n]/.test(text)) throw new Error('DATA_SCHEMA_INVALID');
  return text;
}
export function validatePortfolioRequest(value: unknown, universe = false): PortfolioUniverseRequest {
  const r = alphaRecord(value);
  alphaFields(r, universe ? ['as_of', 'min_adv_billion', 'top_n', 'sector_cap', 'min_score'] : ['as_of']);
  if (r.as_of !== undefined && alphaTimestamp(r.as_of) > Date.now()) throw new Error('PIT_CUTOFF_INVALID');
  if (universe) {
    alphaNumber(r.min_adv_billion ?? 20, 1, 500); alphaNumber(r.top_n ?? 30, 5, 100, true);
    alphaNumber(r.sector_cap ?? 0.3, 0.05, 1); alphaNumber(r.min_score ?? 0.25, 0, 1);
    for (const key of ['min_adv_billion', 'top_n', 'sector_cap', 'min_score']) {
      if (Object.hasOwn(r, key) && r[key] == null) throw new Error('DATA_SCHEMA_INVALID');
    }
  }
  return structuredClone(value) as PortfolioUniverseRequest;
}
function portfolioProvenance(value: unknown, dataset: string, timestamp: unknown, request: PortfolioReadRequest): ProvenanceEnvelope {
  const p = portfolioFields(value, ['source', 'dataset_id', 'dataset_version', 'as_of', 'computed_at', 'requested_pit_cutoff', 'effective_cutoff', 'input_timezone', 'normalized_timezone', 'cutoff_resolution', 'max_included_available_at', 'excluded_future_rows', 'content_hash', 'artifact_uri', 'is_synthetic']);
  const decision = alphaTimestamp(timestamp), cutoff = alphaTimestamp(p.effective_cutoff), computed = alphaTimestamp(p.computed_at);
  if (p.source !== 'target_portfolio_parquet' || p.dataset_id !== dataset || p.dataset_version !== 'portfolio.v1' || p.is_synthetic !== false || p.input_timezone !== 'UTC+7' || p.normalized_timezone !== 'UTC' || p.excluded_future_rows !== 0 || p.artifact_uri !== null
    || typeof p.content_hash !== 'string' || !/^[0-9a-f]{64}$/.test(p.content_hash)
    || alphaTimestamp(p.as_of) !== decision || cutoff > decision || computed < decision || computed > Date.now() || alphaTimestamp(p.max_included_available_at) > cutoff) throw new Error('DATASET_PIT_INVALID');
  const close = new Date(cutoff);
  if (close.getUTCHours() !== 8 || close.getUTCMinutes() !== 30 || close.getUTCSeconds() !== 0 || close.getUTCMilliseconds() !== 0 || [0, 6].includes(close.getUTCDay())) throw new Error('DATASET_PIT_INVALID');
  if (request.as_of === undefined) {
    if (p.requested_pit_cutoff !== null || p.cutoff_resolution !== 'AS_OF_DEFAULT') throw new Error('DATASET_PIT_INVALID');
  } else if (p.cutoff_resolution !== 'REQUESTED' || alphaTimestamp(p.requested_pit_cutoff) !== alphaTimestamp(request.as_of) || decision !== alphaTimestamp(request.as_of)) throw new Error('DATASET_PIT_INVALID');
  // ponytail: holiday resolution is backend-owned; enforce session time/order here, extend with a registered calendar contract.
  return value as ProvenanceEnvelope;
}
export function validateTargetPortfolio(value: unknown, request: PortfolioReadRequest = {}): TargetPortfolioState {
  validatePortfolioRequest(request);
  const nulls = ['expectedIrAnnualized', 'portfolioBeta', 'dailyTurnoverEstimatePercent', 'icMean', 'icTStat', 'cvar99Percent'];
  const r = portfolioFields(value, ['status', 'account_model', 'weighting_method', 'timestamp', 'price_scale', 'nav_method', 'aum_method', 'total_aum_vnd', 'totalAumBillionVnd', 'unallocated_cash_vnd', 'cash_balance_vnd', 'hrp_weights', 'nav_history', 'drawdown_series', 'holdings', 'maxDrawdownEstimatePercent', ...nulls, 'provenance']);
  if (r.status !== 'success' || r.account_model !== 'target_institutional_allocation' || !['hrp', 'hrp_inverse_vol_fallback'].includes(r.weighting_method as string) || r.price_scale !== 'VND_FULL' || r.nav_method !== 'fixed_weight_daily_basket_estimate_not_realized_performance' || r.aum_method !== 'candidate_market_cap_reference_not_broker_assets' || nulls.some((key) => r[key] !== null)) throw new Error('DATA_SCHEMA_INVALID');
  const p = portfolioProvenance(r.provenance, 'target_portfolio_state', r.timestamp, request);
  const aum = alphaNumber(r.total_aum_vnd, Number.MIN_VALUE), cash = alphaNumber(r.unallocated_cash_vnd, 0, aum);
  riskClose(alphaNumber(r.totalAumBillionVnd, Number.MIN_VALUE), aum / 1e9); riskClose(alphaNumber(r.cash_balance_vnd, 0, aum), cash);
  const holdings = alphaArray(r.holdings, 10), weights = alphaRecord(r.hrp_weights), seen = new Set<string>();
  if (!holdings.length || Object.keys(weights).length !== holdings.length) throw new Error('DATA_SCHEMA_INVALID');
  const nullable = ['barraMomentum', 'barraValue', 'barraSize', 'turnoverContribution', 'unrealizedPnlPercent'];
  let sum = 0;
  holdings.forEach((item) => {
    const h = portfolioFields(item, ['symbol', 'weight', 'marketValueBillionVnd', 'adv20BillionVnd', 'alphaScore', 'sector', ...nullable]);
    const symbol = riskSymbol(h.symbol), weight = alphaNumber(h.weight, 0, 1);
    if (symbol !== h.symbol || seen.has(symbol) || !Object.hasOwn(weights, symbol) || nullable.some((key) => h[key] !== null)) throw new Error('DATA_SCHEMA_INVALID');
    seen.add(symbol); sum += weight; portfolioSector(h.sector);
    riskClose(alphaNumber(weights[symbol], 0, 1), weight);
    riskClose(alphaNumber(h.marketValueBillionVnd, 0), aum * weight / 1e9);
    alphaNumber(h.adv20BillionVnd, 0, 1000); alphaNumber(h.alphaScore, 0, 1);
  });
  riskClose(sum, 1); riskClose(cash, aum * Math.max(0, 1 - sum));
  const nav = alphaArray(r.nav_history, 253), drawdown = alphaArray(r.drawdown_series, 253);
  if (nav.length < 21 || nav.length !== drawdown.length) throw new Error('DATA_SCHEMA_INVALID');
  let previous = -Infinity, peak = 0, worst = 0;
  nav.forEach((item, i) => {
    const n = portfolioFields(item, ['timestamp', 'nav_vnd']), d = portfolioFields(drawdown[i], ['timestamp', 'drawdown_percent']);
    const time = alphaTimestamp(n.timestamp), amount = alphaNumber(n.nav_vnd, Number.MIN_VALUE);
    if (time <= previous || time > alphaTimestamp(p.effective_cutoff) || alphaTimestamp(d.timestamp) !== time) throw new Error('DATASET_PIT_INVALID');
    const session = new Date(time);
    if (session.getUTCHours() !== 8 || session.getUTCMinutes() !== 30 || session.getUTCSeconds() !== 0 || session.getUTCMilliseconds() !== 0 || [0, 6].includes(session.getUTCDay())) throw new Error('DATASET_PIT_INVALID');
    if (i === 0) riskClose(amount, aum);
    peak = Math.max(peak, amount);
    const dd = alphaNumber(d.drawdown_percent, -100, 0);
    riskClose(dd, (amount / peak - 1) * 100); worst = Math.min(worst, dd); previous = time;
  });
  if (previous !== alphaTimestamp(p.effective_cutoff)) throw new Error('DATASET_PIT_INVALID');
  riskClose(alphaNumber(r.maxDrawdownEstimatePercent, 0, 100), -worst);
  return value as TargetPortfolioState;
}
export function validatePortfolioUniverse(value: unknown, request: PortfolioUniverseRequest = {}): PortfolioUniverseResponse {
  validatePortfolioRequest(request, true);
  const r = portfolioFields(value, ['status', 'timestamp', 'selector_model', 'symbols', 'scores', 'sector_weights', 'selected_symbols', 'selected_details', 'total_evaluated', 'total_selected', 'excluded_summary', 'units', 'provenance']);
  if (r.status !== 'success' || r.selector_model !== 'hybrid_rank_sector_capped') throw new Error('DATA_SCHEMA_INVALID');
  portfolioProvenance(r.provenance, 'dynamic_universe', r.timestamp, request);
  const units = portfolioFields(r.units, ['adv', 'weight']);
  if (units.adv !== 'billion_vnd' || units.weight !== 'fraction') throw new Error('DATA_SCHEMA_INVALID');
  const symbols = alphaArray(r.symbols, request.top_n ?? 30), selected = alphaArray(r.selected_symbols, 100), rows = alphaArray(r.selected_details, 100);
  const scores = alphaRecord(r.scores), sectors = alphaRecord(r.sector_weights), excluded = alphaRecord(r.excluded_summary);
  const total = alphaNumber(r.total_evaluated, 1, 100000, true);
  if (alphaNumber(r.total_selected, 0, 100, true) !== symbols.length || selected.length !== symbols.length || rows.length !== symbols.length || Object.keys(scores).length !== symbols.length || Object.keys(excluded).length + symbols.length !== total) throw new Error('DATA_SCHEMA_INVALID');
  const seen = new Set<string>(), counts: Record<string, number> = Object.create(null);
  let previousScore = Infinity, previousSymbol = '';
  rows.forEach((item, i) => {
    const d = portfolioFields(item, ['symbol', 'sector', 'score', 'adv_billion_vnd', 'status']);
    const symbol = riskSymbol(d.symbol), sector = portfolioSector(d.sector), score = alphaNumber(d.score, request.min_score ?? 0.25, 1);
    if (symbol !== d.symbol || symbol !== symbols[i] || symbol !== selected[i] || seen.has(symbol) || !Object.hasOwn(scores, symbol) || !['ACTIVE', 'QUALIFIED', 'WATCH'].includes(d.status as string) || score > previousScore || (score === previousScore && symbol <= previousSymbol)) throw new Error('DATA_SCHEMA_INVALID');
    seen.add(symbol); riskClose(alphaNumber(scores[symbol], 0, 1), score);
    alphaNumber(d.adv_billion_vnd, request.min_adv_billion ?? 20, 1000);
    counts[sector] = (counts[sector] ?? 0) + 1; previousScore = score; previousSymbol = symbol;
  });
  if (Object.keys(sectors).length !== Object.keys(counts).length) throw new Error('DATA_SCHEMA_INVALID');
  Object.entries(counts).forEach(([sector, count]) => {
    if (!Object.hasOwn(sectors, sector)) throw new Error('DATA_SCHEMA_INVALID');
    riskClose(alphaNumber(sectors[sector], 0, request.sector_cap ?? 0.3), count / symbols.length);
  });
  Object.entries(excluded).forEach(([symbol, reason]) => {
    if (riskSymbol(symbol) !== symbol || seen.has(symbol) || reason !== 'not_selected_by_liquidity_score_lifecycle_or_sector_cap') throw new Error('DATA_SCHEMA_INVALID');
  });
  return value as PortfolioUniverseResponse;
}
async function portfolioRequest<T>(path: string, request: PortfolioUniverseRequest, universe: boolean, validate: (value: unknown, request: PortfolioUniverseRequest) => T, signal?: AbortSignal): Promise<T> {
  try {
    const snapshot = validatePortfolioRequest(request, universe);
    const query = new URLSearchParams(Object.entries(snapshot).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]));
    return validate(await resilientApiRequest<unknown>(`${path}${query.size ? `?${query}` : ''}`, { signal, maxRetries: 0 }), snapshot);
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    throw new Error(portfolioErrorMessage(error));
  }
}

export interface StrategyWalkForwardRequest {
  dataset_id?: string; universe?: string[]; start_date?: string; end_date?: string;
  n_splits?: number; n_test_splits?: number; embargo_pct?: number; label_horizon?: number;
  initial_capital?: number; slippage_bps?: number; commission_bps?: number;
  as_of?: string; price_scale?: 'VND_FULL';
  evaluation_method?: 'COMBINATORIAL_PURGED_K_FOLD' | 'CHRONOLOGICAL_WALK_FORWARD';
}
export interface StrategyReadRequest { strategy_id: string; as_of?: string; trials_tested?: number }
export interface StrategyFold extends WalkForwardFoldResult {
  train_start: string; train_end: string; train_label_end: string; test_start: string; test_end: string;
  decision_time: string | null; train_indices: number[]; test_indices: number[];
  purged_size: number; embargo_size: number; gross_oos_return_pct: number; oos_observations: number;
}
export interface StrategyWalkForward extends WalkForwardCpcvResponse {
  folds: StrategyFold[]; evaluation_method: 'COMBINATORIAL_PURGED_K_FOLD' | 'CHRONOLOGICAL_WALK_FORWARD';
  historical_pit_verified: boolean; historical_timing_validated: boolean; excluded_incomplete_sessions: number;
  coverage_policy: 'FULL_REQUESTED_UNIVERSE' | 'COMPLETE_CASE_INTERSECTION'; strategy_definition: string;
  price_scale: 'VND_FULL'; oos_return_pct: number; gross_oos_return_pct: number;
  metric_unavailable_reason: string; cost_model: string; provenance_verification: string;
}
export interface StrategyDiagnostics extends OverfittingDiagnosticsResponse {
  probabilistic_sharpe_ratio: number | null; trial_distribution: { trial_id: string; sharpe: number | null }[];
  metric_unavailable_reason: string | null; pbo_method: string; sharpe_unit: string;
  statistical_assumption: string; trial_distribution_sharpe_unit: string; provenance_verification: string;
  diagnostic_basis: 'PERSISTED_STRATEGY_TRIALS' | 'EMPIRICAL_INSTRUMENT_PROXY'; requested_trials_tested: number | null;
  input_integrity: { content_sha256: string; effective_cutoff: string; max_included_available_at?: string; selected_proxy?: string; excluded_incomplete_sessions?: number };
}
export interface StrategyEquity {
  status: 'success'; strategy_id: string; price_scale: 'VND_FULL'; provenance_verification: string; cost_model: string;
  benchmark_id: string; equity_curve: { date: string; gross_equity: number; net_equity: number; benchmark_equity: number; drawdown_pct: number; fees_vnd: number }[];
  total_fees_vnd: number; gross_return_pct: number; net_return_pct: number; benchmark_return_pct: number;
  max_drawdown_pct: number; provenance: null; input_integrity: { content_sha256: string; effective_cutoff: string };
}

export const formatStrategyMetric = formatAlphaMetric;
export function strategyErrorMessage(error: unknown): string {
  const code = (error as { errorCode?: unknown } | null)?.errorCode ?? (error instanceof Error ? error.message : undefined);
  return typeof code === 'string' && ['STRATEGY_RESULT_UNAVAILABLE', 'STRATEGY_RESULT_INVALID', 'STRATEGY_MARKET_UNAVAILABLE', 'STRATEGY_MARKET_CONTRACT_INVALID', 'STRATEGY_NUMERIC_INVALID', 'STRATEGY_UNIVERSE_INCOMPLETE', 'STRATEGY_SESSION_GAP', 'TRIAL_COUNT_MISMATCH', 'INVALID_STRATEGY_AS_OF'].includes(code)
    ? code : 'Strategy analytics unavailable. Check inputs and data; retry.';
}
function strategyFields(value: unknown, fields: string[]): Record<string, unknown> {
  return portfolioFields(value, fields);
}
function strategyId(value: unknown): string {
  const id = alphaText(value, 64);
  if (!/^[A-Z0-9_]{1,64}$/.test(id)) throw new Error('INVALID_STRATEGY_INPUT');
  return id;
}
function strategyDate(value: unknown): number {
  const text = alphaText(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) throw new Error('INVALID_STRATEGY_INPUT');
  return alphaTimestamp(`${text}T08:30:00Z`);
}
function strategyNullable(value: unknown, min = -1e12, max = 1e12): number | null {
  return value === null ? null : alphaNumber(value, min, max);
}
function strategySession(value: unknown): number {
  const time = alphaTimestamp(value), date = new Date(time);
  if (date.getUTCHours() !== 8 || date.getUTCMinutes() !== 30 || date.getUTCSeconds() !== 0 || date.getUTCMilliseconds() !== 0 || [0, 6].includes(date.getUTCDay())) throw new Error('INVALID_STRATEGY_EVIDENCE');
  return time;
}
function strategyCutoff(value: unknown): number {
  const time = alphaTimestamp(value);
  if (time > Date.now()) throw new Error('INVALID_STRATEGY_AS_OF');
  return time;
}
export function validateStrategyRead(value: unknown): StrategyReadRequest {
  const r = alphaRecord(value); alphaFields(r, ['strategy_id', 'as_of', 'trials_tested']); strategyId(r.strategy_id);
  if (r.as_of !== undefined) strategyCutoff(r.as_of);
  if (r.trials_tested !== undefined) alphaNumber(r.trials_tested, 2, 100, true);
  return structuredClone(value) as StrategyReadRequest;
}
export function validateStrategyWalkRequest(value: unknown): StrategyWalkForwardRequest {
  const r = alphaRecord(value);
  alphaFields(r, ['dataset_id', 'universe', 'start_date', 'end_date', 'n_splits', 'n_test_splits', 'embargo_pct', 'label_horizon', 'initial_capital', 'slippage_bps', 'commission_bps', 'as_of', 'price_scale', 'evaluation_method']);
  if ((r.dataset_id ?? 'market_2015_now') !== 'market_2015_now' || (r.price_scale ?? 'VND_FULL') !== 'VND_FULL' || !['COMBINATORIAL_PURGED_K_FOLD', 'CHRONOLOGICAL_WALK_FORWARD'].includes((r.evaluation_method ?? 'COMBINATORIAL_PURGED_K_FOLD') as string)) throw new Error('INVALID_STRATEGY_INPUT');
  // Explicit nulls are not omitted/defaulted inputs.
  if (Object.values(r).some((v) => v === null)) throw new Error('INVALID_STRATEGY_INPUT');
  const splits = alphaNumber(r.n_splits ?? 10, 3, 20, true), tests = alphaNumber(r.n_test_splits ?? 2, 1, 5, true);
  let combinations = 1; for (let i = 1; i <= tests; i++) combinations *= (splits - i + 1) / i;
  if (tests >= splits || Math.round(combinations) > 500) throw new Error('INVALID_STRATEGY_INPUT');
  alphaNumber(r.embargo_pct ?? .01, 0, .5 - Number.EPSILON); alphaNumber(r.label_horizon ?? 5, 1, 60, true);
  alphaNumber(r.initial_capital ?? 1e9, Number.MIN_VALUE); alphaNumber(r.slippage_bps ?? 5, 0, 500); alphaNumber(r.commission_bps ?? 1.5, 0, 100);
  const start = strategyDate(r.start_date ?? '2020-01-01'), end = strategyDate(r.end_date ?? '2023-12-31');
  if (start > end || end > (r.as_of === undefined ? Date.now() : strategyCutoff(r.as_of))) throw new Error('INVALID_STRATEGY_INPUT');
  if (r.universe !== undefined) {
    const symbols = alphaArray(r.universe, 100);
    if (!symbols.length || new Set(symbols).size !== symbols.length) throw new Error('INVALID_STRATEGY_INPUT');
    symbols.forEach((s) => { if (!/^[A-Z0-9_]{1,18}$/.test(alphaText(s, 18))) throw new Error('INVALID_STRATEGY_INPUT'); });
  }
  return structuredClone(value) as StrategyWalkForwardRequest;
}
function strategyIntegrity(value: unknown, request: StrategyReadRequest, proxy = false): Record<string, unknown> {
  const r = strategyFields(value, ['content_sha256', 'effective_cutoff', ...(proxy ? ['max_included_available_at', 'selected_proxy', 'excluded_incomplete_sessions'] : [])]);
  if (!/^[0-9a-f]{64}$/.test(alphaText(r.content_sha256, 64))) throw new Error('INVALID_STRATEGY_EVIDENCE');
  const cutoff = strategyCutoff(r.effective_cutoff);
  if (request.as_of !== undefined && cutoff !== alphaTimestamp(request.as_of)) throw new Error('INVALID_STRATEGY_EVIDENCE');
  if (proxy) {
    if (alphaTimestamp(r.max_included_available_at) > cutoff) throw new Error('INVALID_STRATEGY_EVIDENCE');
    strategyId(r.selected_proxy); alphaNumber(r.excluded_incomplete_sessions, 0, 10000, true);
  }
  return r;
}
export function validateStrategyDiagnostics(value: unknown, request: StrategyReadRequest): StrategyDiagnostics {
  validateStrategyRead(request);
  const r = strategyFields(value, ['status', 'strategy_id', 'trials_tested', 'pbo', 'deflated_sharpe_ratio', 'observed_sharpe', 'expected_max_sharpe', 'variance_of_trials', 'skewness', 'kurtosis', 'fdr_q_values', 'is_overfitted', 'verdict', 'provenance', 'probabilistic_sharpe_ratio', 'trial_distribution', 'metric_unavailable_reason', 'pbo_method', 'sharpe_unit', 'statistical_assumption', 'trial_distribution_sharpe_unit', 'provenance_verification', 'diagnostic_basis', 'requested_trials_tested', 'input_integrity']);
  const proxy = r.diagnostic_basis === 'EMPIRICAL_INSTRUMENT_PROXY';
  if (r.status !== 'success' || r.strategy_id !== request.strategy_id || (!proxy && r.diagnostic_basis !== 'PERSISTED_STRATEGY_TRIALS') || r.provenance !== null || r.pbo_method !== 'CSCV_8_BLOCKS_EMPIRICAL_RANK' || r.sharpe_unit !== 'PER_BAR' || r.trial_distribution_sharpe_unit !== 'ANNUALIZED_252' || r.statistical_assumption !== 'IID_APPROXIMATION_CORRELATED_TRIALS_NOT_INDEPENDENT' || r.provenance_verification !== (proxy ? 'EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_EVIDENCE' : 'CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE')) throw new Error('INVALID_STRATEGY_RESPONSE');
  strategyIntegrity(r.input_integrity, request, proxy);
  const count = alphaNumber(r.trials_tested, 2, 100, true), rows = alphaArray(r.trial_distribution, 100);
  if (rows.length !== count || (proxy ? r.requested_trials_tested !== (request.trials_tested ?? null) : r.requested_trials_tested !== null || (request.trials_tested !== undefined && count !== request.trials_tested))) throw new Error('INVALID_STRATEGY_RESPONSE');
  const ids = new Set<string>(); rows.forEach((item) => { const t = strategyFields(item, ['trial_id', 'sharpe']); const id = strategyId(t.trial_id); if (ids.has(id)) throw new Error('INVALID_STRATEGY_RESPONSE'); ids.add(id); strategyNullable(t.sharpe); });
  ['pbo', 'deflated_sharpe_ratio', 'probabilistic_sharpe_ratio'].forEach((k) => strategyNullable(r[k], 0, 1));
  ['observed_sharpe', 'expected_max_sharpe', 'skewness', 'kurtosis'].forEach((k) => strategyNullable(r[k])); strategyNullable(r.variance_of_trials, 0);
  alphaArray(r.fdr_q_values, 100).forEach((v) => alphaNumber(v, 0, 1));
  const missing = ['pbo', 'deflated_sharpe_ratio', 'probabilistic_sharpe_ratio', 'observed_sharpe', 'expected_max_sharpe', 'variance_of_trials', 'skewness', 'kurtosis'].some((k) => r[k] === null);
  if (r.metric_unavailable_reason !== null) alphaText(r.metric_unavailable_reason, 1024);
  if (missing !== (r.metric_unavailable_reason !== null) || typeof r.is_overfitted !== 'boolean' || r.is_overfitted !== (missing || (r.pbo as number) > .5 || (r.deflated_sharpe_ratio as number) < .95)) throw new Error('INVALID_STRATEGY_RESPONSE');
  const verdict = proxy ? 'EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_VALIDATION' : missing ? 'INSUFFICIENT_STATISTICAL_EVIDENCE' : 'EMPIRICAL_DIAGNOSTICS_ONLY';
  if (r.verdict !== verdict) throw new Error('INVALID_STRATEGY_RESPONSE');
  return value as StrategyDiagnostics;
}
export function validateStrategyEquity(value: unknown, request: StrategyReadRequest): StrategyEquity {
  validateStrategyRead(request);
  const r = strategyFields(value, ['status', 'strategy_id', 'price_scale', 'provenance_verification', 'cost_model', 'benchmark_id', 'equity_curve', 'total_fees_vnd', 'gross_return_pct', 'net_return_pct', 'benchmark_return_pct', 'max_drawdown_pct', 'provenance', 'input_integrity']);
  if (r.status !== 'success' || r.strategy_id !== request.strategy_id || r.price_scale !== 'VND_FULL' || r.provenance !== null || r.provenance_verification !== 'CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE' || r.cost_model !== 'PERSISTED_AGGREGATE_FEE_RETURNS_NO_ASSUMED_COSTS') throw new Error('INVALID_STRATEGY_RESPONSE');
  strategyId(r.benchmark_id); const integrity = strategyIntegrity(r.input_integrity, request), cutoff = alphaTimestamp(integrity.effective_cutoff);
  const rows = alphaArray(r.equity_curve, 10001); if (rows.length < 2) throw new Error('INVALID_STRATEGY_RESPONSE');
  let previous = -Infinity, peak = 0, worst = 0, fees = 0;
  rows.forEach((item, i) => {
    const p = strategyFields(item, ['date', 'gross_equity', 'net_equity', 'benchmark_equity', 'drawdown_pct', 'fees_vnd']);
    const time = strategySession(p.date);
    if (time <= previous || time > cutoff) throw new Error('INVALID_STRATEGY_EVIDENCE');
    previous = time; ['gross_equity', 'net_equity', 'benchmark_equity'].forEach((k) => alphaNumber(p[k], Number.MIN_VALUE));
    if ((p.net_equity as number) > (p.gross_equity as number)) throw new Error('INVALID_STRATEGY_RESPONSE');
    peak = Math.max(peak, p.net_equity as number); const dd = alphaNumber(p.drawdown_pct, -100, 0); riskClose(dd, ((p.net_equity as number) / peak - 1) * 100); worst = Math.min(worst, dd);
    fees += alphaNumber(p.fees_vnd, 0);
    if (i === 0) { riskClose(p.net_equity as number, p.gross_equity as number); riskClose(p.net_equity as number, p.benchmark_equity as number); if (p.fees_vnd !== 0) throw new Error('INVALID_STRATEGY_RESPONSE'); }
  });
  riskClose(alphaNumber(r.total_fees_vnd, 0), fees); riskClose(alphaNumber(r.max_drawdown_pct, 0, 100), -worst);
  const first = rows[0] as StrategyEquity['equity_curve'][number], last = rows.at(-1) as StrategyEquity['equity_curve'][number];
  for (const [metric, key] of [['gross_return_pct', 'gross_equity'], ['net_return_pct', 'net_equity'], ['benchmark_return_pct', 'benchmark_equity']] as const) riskClose(alphaNumber(r[metric], -100), (last[key] / first[key] - 1) * 100);
  return value as StrategyEquity;
}
export function validateStrategyWalk(value: unknown, request: StrategyWalkForwardRequest): StrategyWalkForward {
  validateStrategyWalkRequest(request);
  const r = strategyFields(value, ['status', 'task_type', 'job_id', 'dataset_id', 'n_splits', 'n_test_splits', 'total_folds', 'mean_oos_sharpe', 'median_oos_sharpe', 'std_oos_sharpe', 'mean_oos_return_pct', 'worst_drawdown_pct', 'pbo', 'deflated_sharpe_ratio', 'folds', 'provenance', 'evaluation_method', 'historical_pit_verified', 'historical_timing_validated', 'excluded_incomplete_sessions', 'coverage_policy', 'strategy_definition', 'price_scale', 'oos_return_pct', 'gross_oos_return_pct', 'metric_unavailable_reason', 'cost_model', 'provenance_verification']);
  const chronological = r.evaluation_method === 'CHRONOLOGICAL_WALK_FORWARD', splits = request.n_splits ?? 10, tests = request.n_test_splits ?? 2;
  if (r.status !== 'success' || r.task_type !== 'WALK_FORWARD_CPCV' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(alphaText(r.job_id, 36)) || r.dataset_id !== (request.dataset_id ?? 'market_2015_now') || r.n_splits !== splits || r.n_test_splits !== tests || r.evaluation_method !== (request.evaluation_method ?? 'COMBINATORIAL_PURGED_K_FOLD') || r.price_scale !== 'VND_FULL' || r.strategy_definition !== 'FIXED_EQUAL_WEIGHT_DAILY_REBALANCE' || r.cost_model !== 'DECLARED_DAILY_COMMISSION_PLUS_SLIPPAGE_BPS' || r.provenance_verification !== 'VALIDATED_MARKET_METADATA_NOT_AUTHENTICATED_LINEAGE' || r.historical_pit_verified !== false || r.historical_timing_validated !== chronological || r.coverage_policy !== (chronological ? 'FULL_REQUESTED_UNIVERSE' : 'COMPLETE_CASE_INTERSECTION') || r.pbo !== null || r.deflated_sharpe_ratio !== null) throw new Error('INVALID_STRATEGY_RESPONSE');
  alphaText(r.metric_unavailable_reason, 1024); alphaNumber(r.excluded_incomplete_sessions, 0, 10000, true);
  const cutoff = request.as_of === undefined ? Date.now() : alphaTimestamp(request.as_of);
  if (chronological) {
    riskHistorical(r.provenance, request.dataset_id ?? 'market_2015_now');
    const proof = alphaRecord(r.provenance), effective = alphaTimestamp(proof.effective_cutoff);
    if (effective > cutoff || (request.as_of !== undefined && effective !== cutoff) || alphaTimestamp(proof.as_of) !== effective || alphaTimestamp(proof.requested_pit_cutoff) !== effective || proof.cutoff_resolution !== 'REQUESTED') throw new Error('INVALID_STRATEGY_EVIDENCE');
  } else if (r.provenance !== null) throw new Error('INVALID_STRATEGY_EVIDENCE');
  let combinations = 1; for (let i = 1; i <= tests; i++) combinations *= (splits - i + 1) / i;
  const rows = alphaArray(r.folds, 500), expected = chronological ? Math.ceil((splits - 1) / tests) : Math.round(combinations);
  if (r.total_folds !== rows.length || rows.length !== expected) throw new Error('INVALID_STRATEGY_RESPONSE');
  let work = 0, lastTest = -Infinity;
  rows.forEach((item, i) => {
    const f = strategyFields(item, ['fold', 'train_size', 'test_size', 'in_sample_sharpe', 'out_of_sample_sharpe', 'in_sample_return_pct', 'out_of_sample_return_pct', 'max_drawdown_pct', 'train_start', 'train_end', 'train_label_end', 'test_start', 'test_end', 'decision_time', 'train_indices', 'test_indices', 'purged_size', 'embargo_size', 'gross_oos_return_pct', 'oos_observations']);
    if (f.fold !== i) throw new Error('INVALID_STRATEGY_RESPONSE');
    const train = alphaNumber(f.train_size, 2, 10000, true), test = alphaNumber(f.test_size, 2, 10000, true);
    work += train + test; if (work > 500000 || f.oos_observations !== test) throw new Error('INVALID_STRATEGY_RESPONSE');
    const indices = (v: unknown, size: number) => { const a = alphaArray(v, 10000); if (a.length !== size) throw new Error('INVALID_STRATEGY_RESPONSE'); let prev = -1; a.forEach((n) => { prev = alphaNumber(n, prev + 1, 10000, true); }); return a as number[]; };
    const a = indices(f.train_indices, chronological ? 0 : train), b = indices(f.test_indices, chronological ? 0 : test), seen = new Set(a);
    if (b.some((n) => seen.has(n))) throw new Error('INVALID_STRATEGY_RESPONSE');
    alphaNumber(f.purged_size, 0, 10000, true); alphaNumber(f.embargo_size, 0, 10000, true);
    strategyNullable(f.in_sample_sharpe); strategyNullable(f.out_of_sample_sharpe);
    ['in_sample_return_pct', 'out_of_sample_return_pct', 'gross_oos_return_pct'].forEach((k) => alphaNumber(f[k], -100)); alphaNumber(f.max_drawdown_pct, 0, 100);
    const start = strategySession(f.train_start), end = strategySession(f.train_end), label = strategySession(f.train_label_end), testStart = strategySession(f.test_start), testEnd = strategySession(f.test_end);
    if (start > end || end > label || testStart > testEnd || Math.max(label, testEnd) > cutoff || Math.min(start, testStart) < strategyDate(request.start_date ?? '2020-01-01') || Math.max(end, testEnd) > strategyDate(request.end_date ?? '2023-12-31')) throw new Error('INVALID_STRATEGY_EVIDENCE');
    if (chronological ? f.decision_time === null || alphaTimestamp(f.decision_time) < label || alphaTimestamp(f.decision_time) >= testStart || label >= testStart || testStart <= lastTest : f.decision_time !== null) throw new Error('INVALID_STRATEGY_EVIDENCE');
    lastTest = testEnd;
  });
  ['mean_oos_sharpe', 'median_oos_sharpe'].forEach((k) => strategyNullable(r[k])); strategyNullable(r.std_oos_sharpe, 0);
  ['mean_oos_return_pct', 'oos_return_pct', 'gross_oos_return_pct'].forEach((k) => alphaNumber(r[k], -100)); alphaNumber(r.worst_drawdown_pct, 0, 100);
  const folds = rows as StrategyFold[];
  if (!chronological) riskClose(r.worst_drawdown_pct as number, Math.max(...folds.map((f) => f.max_drawdown_pct)));
  riskClose(r.mean_oos_return_pct as number, folds.reduce((s, f) => s + f.out_of_sample_return_pct, 0) / folds.length);
  return value as StrategyWalkForward;
}
async function strategyRequest<T>(path: string, validate: (value: unknown) => T, signal?: AbortSignal, payload?: unknown): Promise<T> {
  try { return validate(await resilientApiRequest<unknown>(path, { signal, maxRetries: 0, ...(payload === undefined ? {} : { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } }) })); }
  catch (error) { if (signal?.aborted) throw new DOMException('Aborted', 'AbortError'); throw new Error(strategyErrorMessage(error)); }
}

export const advancedQuantApi = {
  getTargetPortfolioState: (request: PortfolioReadRequest = {}, signal?: AbortSignal) => portfolioRequest('/api/v1/portfolio/state', request, false, validateTargetPortfolio, signal),
  getPortfolioDynamicUniverse: (request: PortfolioUniverseRequest = {}, signal?: AbortSignal) => portfolioRequest('/api/v1/portfolio/dynamic-universe', request, true, validatePortfolioUniverse, signal),
  getBarraDecomposition: (signal?: AbortSignal) => riskRequest('/api/v1/risk/barra/decomposition', validateBarraResponse, signal),
  calculateBarraDecomposition: (payload: BarraRequest, signal?: AbortSignal) => riskRequest('/api/v1/risk/barra/decomposition', validateBarraResponse, signal, validateBarraRequest(payload)),
  // ponytail: no calibrated CVaR contract exists; never accept a legacy success payload.
  getStressScenarios: (signal?: AbortSignal) => riskRequest('/api/v1/risk/stress-scenarios', (): never => { throw new Error('STRESS_MODEL_UNAVAILABLE'); }, signal),
  calculatePreTradeImpact: (payload: TcaImpactRequest, signal?: AbortSignal) => riskRequest('/api/v1/tca/pre-trade-impact', (value) => validateImpactResponse(value, payload), signal, validateImpactRequest(payload)),
  getPostTradeReport: (signal?: AbortSignal) => riskRequest('/api/v1/tca/post-trade-report', validateTcaReport, signal),
  getRoutingDiagnostics: (signal?: AbortSignal) => riskRequest('/api/v1/execution/routing-diagnostics', validateRoutingReport, signal),
  submitJob: (request: JobSubmitRequest, idempotencyKey: string, signal?: AbortSignal) =>
    apiRequest<JobAcceptedResponse>('/api/v1/jobs', {
      method: 'POST',
      body: JSON.stringify(request),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      signal,
    }),
  getJob: (jobId: string, signal?: AbortSignal) =>
    apiRequest<JobStatusResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, { signal }),
  cancelJob: (jobId: string, signal?: AbortSignal) =>
    apiRequest<{ job_id: string; status: JobStatus; cancellation_requested_at: string }>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST', signal },
    ),
  eventUrl: (streamUrl: string) => new URL(streamUrl, API_BASE).toString(),

  // Phase 2 Microstructure & Risk TCA Analytics
  getVpinToxicity: (symbol: string, nBuckets = 20, limit = 200, signal?: AbortSignal) =>
    apiRequest<VpinToxicityResponse>(`/api/v1/market/vpin/${encodeURIComponent(symbol)}?n_buckets=${nBuckets}&limit=${limit}`, { signal }),

  getOrderbookDepthWaterfall: (symbol: string, depth = 10, spreadBps = 10.0, signal?: AbortSignal) =>
    apiRequest<OrderbookDepthWaterfallResponse>(`/api/v1/market/orderbook-depth/${encodeURIComponent(symbol)}?depth=${depth}&spread_bps=${spreadBps}`, { signal }),

  calculateMarketImpactCurve: (payload: { symbol: string; order_size: number; average_daily_volume: number; volatility?: number; participation_rate?: number; arrival_price?: number; impact_coefficient?: number }, signal?: AbortSignal) =>
    apiRequest<MarketImpactResponse>('/api/v1/market/market-impact', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  calculateFracDiff: (payload: { symbol: string; d?: number; window?: number; limit?: number }, signal?: AbortSignal) =>
    apiRequest<FracDiffResponse>('/api/v1/market/fracdiff', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getCircuitBreakerStatus: (symbol = 'VNM', signal?: AbortSignal) =>
    apiRequest<CircuitBreakerStatusResponse>(`/api/v1/risk/circuit-breaker/status?symbol=${encodeURIComponent(symbol)}`, { signal }),

  simulateStressTest: (payload: StressRequest, signal?: AbortSignal) => {
    alphaFields(payload, ['portfolio_weights', 'market_shock_pct', 'volatility_shock_multiplier', 'include_contagion']);
    riskMap(payload.portfolio_weights, false, 1);
    if (payload.market_shock_pct !== undefined) alphaNumber(payload.market_shock_pct, -50, 50);
    if (payload.volatility_shock_multiplier !== undefined) alphaNumber(payload.volatility_shock_multiplier, 0.5, 10);
    if (payload.include_contagion !== undefined && typeof payload.include_contagion !== 'boolean') throw new Error('INVALID_RISK_INPUT');
    return riskRequest('/api/v1/risk/stress-test/simulate', (value) => validateStressResponse(value, payload), signal, payload);
  },

  getContagionGraph: (signal?: AbortSignal) =>
    apiRequest<ContagionRiskGraphResponse>('/api/v1/risk/contagion-graph', { signal }),

  validateLiquidityStress: (payload: LiquidityRequest, signal?: AbortSignal) => {
    alphaFields(payload, ['positions', 'max_adv_participation', 'max_exit_days', 'market_impact_coefficient']);
    riskMap(payload.positions, true, 1e12);
    if (payload.max_adv_participation !== undefined) alphaNumber(payload.max_adv_participation, Number.MIN_VALUE, 1);
    if (payload.max_exit_days !== undefined) alphaNumber(payload.max_exit_days, 1, 30, true);
    if (payload.market_impact_coefficient !== undefined) alphaNumber(payload.market_impact_coefficient, Number.MIN_VALUE, 2);
    return riskRequest('/api/v1/risk/liquidity-stress/validate', (value) => validateLiquidityResponse(value, payload), signal, payload);
  },

  getCorporateGraph: (symbol: string, signal?: AbortSignal) =>
    apiRequest<CorporateGraphResponse>(`/api/v1/fundamental/corporate-graph/${encodeURIComponent(symbol)}`, { signal }),

  getNetworkGraph: (params: {
    as_of?: string;
    sector?: string;
    ecosystem?: string;
    symbol?: string;
    relationship?: string;
    min_market_cap?: number;
    min_adv20?: number;
    max_nodes?: number;
    metric_color?: string;
  } = {}, signal?: AbortSignal) => {
    const qParams = new URLSearchParams();
    if (params.as_of) qParams.append('as_of', params.as_of);
    if (params.sector) qParams.append('sector', params.sector);
    if (params.ecosystem) qParams.append('ecosystem', params.ecosystem);
    if (params.symbol) qParams.append('symbol', params.symbol);
    if (params.relationship) qParams.append('relationship', params.relationship);
    if (params.min_market_cap !== undefined) qParams.append('min_market_cap', String(params.min_market_cap));
    if (params.min_adv20 !== undefined) qParams.append('min_adv20', String(params.min_adv20));
    if (params.max_nodes !== undefined) qParams.append('max_nodes', String(params.max_nodes));
    if (params.metric_color) qParams.append('metric_color', params.metric_color);
    const qs = qParams.toString();
    return apiRequest<NetworkGraphApiResponse>(`/api/v1/quant/network-graph${qs ? `?${qs}` : ''}`, { signal });
  },

  // Phase 3 Active Quant, Evolution & Smart Execution APIs
  runWalkForwardCpcv: (payload: StrategyWalkForwardRequest, signal?: AbortSignal): Promise<WalkForwardCpcvResponse> => {
    const snapshot = validateStrategyWalkRequest(payload);
    return strategyRequest('/api/v1/quant/walk-forward', (v) => validateStrategyWalk(v, snapshot), signal, snapshot);
  },

  getOverfittingDiagnostics: (strategyId = 'ALPHA_HRP_V2', trialsTested?: number, signal?: AbortSignal, asOf?: string): Promise<OverfittingDiagnosticsResponse> => {
    const request = validateStrategyRead({ strategy_id: strategyId, ...(trialsTested === undefined ? {} : { trials_tested: trialsTested }), ...(asOf === undefined ? {} : { as_of: asOf }) });
    const query = new URLSearchParams(Object.entries(request).map(([k, v]) => [k, String(v)]));
    return strategyRequest(`/api/v1/quant/overfitting-diagnostics?${query}`, (v) => validateStrategyDiagnostics(v, request), signal);
  },

  getStrategyEquity: (request: StrategyReadRequest, signal?: AbortSignal) => {
    const snapshot = validateStrategyRead(request), query = new URLSearchParams([['strategy_id', snapshot.strategy_id], ...(snapshot.as_of === undefined ? [] : [['as_of', snapshot.as_of]])]);
    return strategyRequest(`/api/v1/quant/strategy-equity-curve?${query}`, (v) => validateStrategyEquity(v, snapshot), signal);
  },

  predictConformal: (payload: { symbol: string; horizon_days?: number; confidence_levels?: number[]; features?: Record<string, number> }, signal?: AbortSignal) =>
    apiRequest<ConformalPredictResponse>('/api/v1/quant/conformal/predict', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getMarketConformal: (symbol: string, horizonDays = 5, signal?: AbortSignal) =>
    apiRequest<ConformalPredictResponse>(`/api/v1/market/conformal/${encodeURIComponent(symbol)}?horizon_days=${horizonDays}`, { signal }),

  evaluateAlphaAst: async (payload: AlphaEvaluationRequest, signal?: AbortSignal) => {
    alphaFields(payload, ['expression', 'universe', 'sample_data', 'as_of', 'pit_cutoff']);
    alphaText(payload.expression, 4096);
    if (payload.universe !== undefined) alphaText(payload.universe, 64);
    const asOf = payload.as_of === undefined ? Date.now() : alphaTimestamp(payload.as_of);
    if (payload.pit_cutoff !== undefined && alphaTimestamp(payload.pit_cutoff) > asOf) throw new Error('INVALID_ALPHA_PIT');
    if (payload.sample_data != null) {
      const entries = Object.entries(alphaRecord(payload.sample_data));
      if (!entries.length || entries.length > 64) throw new Error('INVALID_ALPHA_PAYLOAD');
      entries.forEach(([key, values]) => {
        alphaText(key, 64);
        const samples = alphaArray(values, 10000);
        if (!samples.length) throw new Error('INVALID_ALPHA_ARRAY');
        samples.forEach((v) => alphaNumber(v));
      });
    }
    const result = validateAlphaEvaluation(await resilientApiRequest<unknown>('/api/v1/alpha/ast/evaluate', {
      maxRetries: 0,
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }));
    if (result.provenance) {
      if (payload.as_of !== undefined && alphaTimestamp(result.provenance.as_of) !== asOf) throw new Error('INVALID_ALPHA_PIT');
      if (payload.pit_cutoff !== undefined && alphaTimestamp(result.provenance.effective_cutoff) !== alphaTimestamp(payload.pit_cutoff)) throw new Error('INVALID_ALPHA_PIT');
      if (payload.sample_data != null && result.provenance.source !== 'caller_sample') throw new Error('INVALID_ALPHA_PIT');
    }
    return result;
  },

  getAlphaArsenalSignals: (params: { category?: string; status?: string; search?: string; limit?: number } = {}, signal?: AbortSignal) => {
    alphaFields(params, ['category', 'status', 'search', 'limit']);
    const qParams = new URLSearchParams();
    if (params.category !== undefined) qParams.append('category', alphaText(params.category, 64, true));
    if (params.status !== undefined) qParams.append('status', alphaText(params.status, 64, true));
    if (params.search !== undefined) qParams.append('search', alphaText(params.search, 4096, true));
    if (params.limit !== undefined) qParams.append('limit', String(alphaNumber(params.limit, 1, 1000, true)));
    return resilientApiRequest<unknown>(`/api/v1/alpha/arsenal/signals?${qParams.toString()}`, { signal, maxRetries: 0 }).then(validateAlphaArsenal);
  },

  getAlphaDecayProfile: async (alphaId: string, signal?: AbortSignal) => {
    alphaText(alphaId, 64);
    return validateAlphaDecay(await resilientApiRequest<unknown>(`/api/v1/alpha/decay-profile/${encodeURIComponent(alphaId)}`, { signal, maxRetries: 0 }));
  },

  startAlphaDiscovery: async (payload: AlphaDiscoveryRequest, signal?: AbortSignal) => {
    alphaFields(payload, ['population_size', 'generations', 'mutation_rate', 'crossover_rate', 'target_ic', 'target_ir', 'allowed_operators']);
    alphaNumber(payload.generations === undefined ? 10 : payload.generations, 1, 100, true);
    alphaNumber(payload.population_size === undefined ? 50 : payload.population_size, 10, 500, true);
    alphaNumber(payload.mutation_rate === undefined ? 0.15 : payload.mutation_rate, Number.MIN_VALUE, 1);
    alphaNumber(payload.crossover_rate === undefined ? 0.75 : payload.crossover_rate, Number.MIN_VALUE, 1);
    alphaNumber(payload.target_ic === undefined ? 0.04 : payload.target_ic, Number.MIN_VALUE, 0.5);
    alphaNumber(payload.target_ir === undefined ? 1.5 : payload.target_ir, Number.MIN_VALUE, 10);
    if (payload.allowed_operators !== undefined) alphaArray(payload.allowed_operators, 64).forEach((op) => alphaText(op, 64));
    return validateAlphaDiscovery(await resilientApiRequest<unknown>('/api/v1/alpha/discovery/start', {
      maxRetries: 0,
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }));
  },

  executePortfolioRebalance: (payload: { totp_code: string; strategy_id?: string; target_portfolio?: Record<string, number>; portfolio_value?: number; drift_threshold?: number; max_turnover?: number; routing_algo?: string; duration_minutes?: number }, signal?: AbortSignal) =>
    apiRequest<PortfolioRebalanceExecuteResponse>('/api/v1/portfolio/rebalance/execute', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  // Phase 4 Model Governance & Resource Governor APIs
  getModelList: (category?: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) => {
    const q = category ? `?category=${encodeURIComponent(category)}` : '';
    return resilientApiRequest<ModelListResponse>(`/api/v1/models${q}`, { ...options, signal });
  },

  getModelVersions: (modelName: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ModelVersionsResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/versions`, { ...options, signal }),

  getModelVersionDetail: (modelName: string, version: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ModelVersionDetailResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/versions/${encodeURIComponent(version)}`, { ...options, signal }),

  getModelDrift: (modelName: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ModelDriftResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/drift`, { ...options, signal }),

  promoteModelVersion: (modelName: string, version: string, payload: { totp_code: string; target_status: 'VALIDATED' | 'PRODUCTION'; promoter_id?: string; rationale?: string; pit_evidence?: Record<string, any> }, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ModelPromoteResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/versions/${encodeURIComponent(version)}/promote`, {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  rollbackModel: (modelName: string, payload: { totp_code: string; target_version: string; reason?: string }, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ModelRollbackResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/rollback`, {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  getResourceGovernor: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ResourceGovernorStateResponse>('/api/v1/operations/resource-governor', { ...options, signal }),

  updateResourceGovernor: (payload: { mode?: 'MANUAL' | 'COPILOT'; target_concurrency?: number; thread_pool_size?: number; batch_size?: number }, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ResourceGovernorStateResponse>('/api/v1/operations/resource-governor', {
      method: 'PATCH',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  // Paper Trading Lifecycle & Execution Controls
  getPaperDaemonStatus: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperDaemonStatusResponse>('/api/v1/execution/status', { ...options, signal }),

  startPaperDaemon: (payload?: PaperDaemonStartRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperDaemonStatusResponse>('/api/v1/execution/start', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  stopPaperDaemon: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperDaemonStatusResponse>('/api/v1/execution/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  pausePaperDaemon: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperDaemonStatusResponse>('/api/v1/execution/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  resumePaperDaemon: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperDaemonStatusResponse>('/api/v1/execution/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  submitPaperOrder: (payload: PaperOrderExecutionRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<PaperOrderExecutionResponse>('/api/v1/execution/orders', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  getPaperOrders: (limit: number = 100, symbol?: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) => {
    const q = new URLSearchParams();
    q.set('limit', String(limit));
    if (symbol) q.set('symbol', symbol);
    return resilientApiRequest<Array<Record<string, unknown>>>(`/api/v1/execution/orders?${q.toString()}`, { ...options, signal });
  },

  getPaperPositions: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<{ positions: Record<string, unknown>; count: number; as_of: string }>('/api/v1/execution/positions', { ...options, signal }),

  getExecutionWorkers: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<Array<Record<string, unknown>>>('/api/v1/execution/workers', { ...options, signal }),

  // Phase 3 Multi-Seed Evolution, Variance Explorer & Drift Sentinel APIs
  runEvolution: (req: EvolutionRunRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<JobAcceptedResponse>('/api/v1/quant/evolution/runs', {
      method: 'POST',
      body: JSON.stringify(req),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  getEvolutionRun: (jobId: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<JobStatusResponse>(`/api/v1/quant/evolution/runs/${encodeURIComponent(jobId)}`, { ...options, signal }),

  getDriftMonitorStatus: (signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<DriftMonitorStatus>('/api/v1/models/drift-monitor/status', { ...options, signal }),

  updateDriftSchedule: (req: DriftScheduleRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<DriftMonitorStatus>('/api/v1/models/drift-monitor/schedule', {
      method: 'PATCH',
      body: JSON.stringify(req),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  // Conformal CPCV Calibration APIs
  calibrateConformalCpcv: (req: ConformalCalibrationRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ConformalCalibrationResponse>('/api/v1/quant/conformal/calibrate', {
      method: 'POST',
      body: JSON.stringify(req),
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  getConformalCalibrationStatus: (modelName: string = 'CONFORMAL_PREDICTOR', signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ConformalCalibrationStatusResponse>(`/api/v1/quant/conformal/calibration-status?model_name=${encodeURIComponent(modelName)}`, {
      signal,
      ...options,
    }),

  calibrateModelConformal: (modelName: string, req?: ConformalCalibrationRequest, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ConformalCalibrationResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/calibrate`, {
      method: 'POST',
      body: req ? JSON.stringify(req) : undefined,
      headers: { 'Content-Type': 'application/json' },
      signal,
      ...options,
    }),

  getModelCalibrationStatus: (modelName: string, signal?: AbortSignal, options?: AdvancedQuantRequestOptions) =>
    resilientApiRequest<ConformalCalibrationStatusResponse>(`/api/v1/models/${encodeURIComponent(modelName)}/calibration`, {
      signal,
      ...options,
    }),
};

export type PaperDaemonState = 'STOPPED' | 'RUNNING' | 'PAUSED' | 'ERROR';

export interface PaperDaemonStatusResponse {
  state: PaperDaemonState;
  active: boolean;
  mode?: string;
  initial_capital_vnd?: number;
  cash_vnd?: number;
  portfolio_equity_vnd?: number;
  total_pnl_vnd?: number;
  daily_pnl_vnd: number;
  realized_pnl_vnd?: number;
  unrealized_pnl_vnd?: number;
  uptime_seconds: number;
  last_heartbeat: string | null;
  processed_orders_count: number;
  active_orders_count: number;
  positions_count?: number;
  positions?: Record<string, {
    symbol: string;
    shares: number;
    avg_price: number;
    current_price: number;
    realized_pnl_vnd: number;
    unrealized_pnl_vnd?: number;
  }>;
  active_workers?: number;
  workers?: Array<{
    worker_id: string;
    hostname: string;
    pid: number;
    status: string;
    started_at: string;
    last_heartbeat: string;
    metadata?: Record<string, unknown>;
  }>;
  model_pnl?: Record<string, number>;
}

export interface PaperDaemonStartRequest {
  initial_capital?: number;
  mode?: string;
}

export interface PaperOrderExecutionRequest {
  symbol: string;
  side: 'BUY' | 'SELL';
  size: number;
  price: number;
  model_id?: string;
  feature_ts: string;
  decision_ts: string;
  available_at?: string;
  order_book_data?: Record<string, unknown>;
}

export interface PaperOrderExecutionResponse {
  status: string;
  symbol: string;
  side: string;
  executions: Array<Record<string, unknown>>;
  count: number;
  submitted_at: string;
}

export interface ConformalCalibrationRequest {
  model_name?: string;
  universe?: string[];
  target_coverage?: number;
  n_splits?: number;
  n_test_splits?: number;
  embargo_pct?: number;
  label_horizon?: number;
  calib_days?: number;
  alphas?: number[];
  as_of_date?: string;
}

export interface MondrianGroupCoverage {
  regime: string;
  liquidity_bucket: string;
  sample_count: number;
  coverage: number;
  mean_interval_width: number;
}

export interface ConformalCalibrationResponse {
  status: string;
  model_name: string;
  version: string;
  n_folds: number;
  total_samples: number;
  target_coverage: number;
  empirical_coverage: number;
  mean_interval_width: number;
  alphas: number[];
  quantiles: Record<string, number>;
  group_coverages: MondrianGroupCoverage[];
  artifact_path: string;
  calibrated_at: string;
  pit_embargo: string;
  is_valid: boolean;
  provenance?: ProvenanceEnvelope | null;
}

export interface ConformalCalibrationStatusResponse {
  status: 'CALIBRATED' | 'NOT_CALIBRATED' | 'CALIBRATING' | 'ERROR';
  model_name: string;
  is_calibrated: boolean;
  last_calibrated_at: string | null;
  latest_version: string | null;
  target_coverage: number | null;
  empirical_coverage: number | null;
  mean_interval_width: number | null;
  group_coverages: MondrianGroupCoverage[];
  provenance?: ProvenanceEnvelope | null;
}



