import { API_BASE, apiRequest } from './client';

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
  in_sample_sharpe: number;
  out_of_sample_sharpe: number;
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
  mean_oos_sharpe: number;
  median_oos_sharpe: number;
  std_oos_sharpe: number;
  mean_oos_return_pct: number;
  worst_drawdown_pct: number;
  pbo: number;
  deflated_sharpe_ratio: number;
  folds: WalkForwardFoldResult[];
  provenance?: ProvenanceEnvelope | null;
}

export interface OverfittingDiagnosticsResponse {
  status: string;
  strategy_id: string;
  trials_tested: number;
  pbo: number;
  deflated_sharpe_ratio: number;
  observed_sharpe: number;
  expected_max_sharpe: number;
  variance_of_trials: number;
  skewness: number;
  kurtosis: number;
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
  provenance?: ProvenanceEnvelope | null;
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

export const advancedQuantApi = {
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

  simulateStressTest: (payload: { portfolio_weights: Record<string, number>; market_shock_pct?: number; volatility_shock_multiplier?: number; include_contagion?: boolean }, signal?: AbortSignal) =>
    apiRequest<StressTestSimulateResponse>('/api/v1/risk/stress-test/simulate', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getContagionGraph: (signal?: AbortSignal) =>
    apiRequest<ContagionRiskGraphResponse>('/api/v1/risk/contagion-graph', { signal }),

  validateLiquidityStress: (payload: { positions: Record<string, number>; max_adv_participation?: number; max_exit_days?: number; market_impact_coefficient?: number }, signal?: AbortSignal) =>
    apiRequest<LiquidityStressValidateResponse>('/api/v1/risk/liquidity-stress/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

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
  runWalkForwardCpcv: (payload: { dataset_id?: string; universe?: string[]; start_date?: string; end_date?: string; n_splits?: number; n_test_splits?: number; embargo_pct?: number; label_horizon?: number; initial_capital?: number; slippage_bps?: number; commission_bps?: number }, signal?: AbortSignal) =>
    apiRequest<WalkForwardCpcvResponse>('/api/v1/quant/walk-forward', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getOverfittingDiagnostics: (strategyId = 'ALPHA_HRP_V2', trialsTested = 20, signal?: AbortSignal) =>
    apiRequest<OverfittingDiagnosticsResponse>(`/api/v1/quant/overfitting-diagnostics?strategy_id=${encodeURIComponent(strategyId)}&trials_tested=${trialsTested}`, { signal }),

  predictConformal: (payload: { symbol: string; horizon_days?: number; confidence_levels?: number[]; features?: Record<string, number> }, signal?: AbortSignal) =>
    apiRequest<ConformalPredictResponse>('/api/v1/quant/conformal/predict', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getMarketConformal: (symbol: string, horizonDays = 5, signal?: AbortSignal) =>
    apiRequest<ConformalPredictResponse>(`/api/v1/market/conformal/${encodeURIComponent(symbol)}?horizon_days=${horizonDays}`, { signal }),

  evaluateAlphaAst: (payload: { expression: string; universe?: string; sample_data?: Record<string, number[]> }, signal?: AbortSignal) =>
    apiRequest<AlphaEvaluationResponse>('/api/v1/alpha/ast/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

  getAlphaArsenalSignals: (params: { category?: string; status?: string; search?: string; limit?: number } = {}, signal?: AbortSignal) => {
    const qParams = new URLSearchParams();
    if (params.category) qParams.append('category', params.category);
    if (params.status) qParams.append('status', params.status);
    if (params.search) qParams.append('search', params.search);
    if (params.limit) qParams.append('limit', String(params.limit));
    return apiRequest<AlphaArsenalResponse>(`/api/v1/alpha/arsenal/signals?${qParams.toString()}`, { signal });
  },

  getAlphaDecayProfile: (alphaId: string, signal?: AbortSignal) =>
    apiRequest<AlphaDecayProfileResponse>(`/api/v1/alpha/decay-profile/${encodeURIComponent(alphaId)}`, { signal }),

  startAlphaDiscovery: (payload: { population_size?: number; generations?: number; mutation_rate?: number; crossover_rate?: number; target_ic?: number; target_ir?: number; allowed_operators?: string[] }, signal?: AbortSignal) =>
    apiRequest<GeneticDiscoveryResponse>('/api/v1/alpha/discovery/start', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      signal,
    }),

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
};


