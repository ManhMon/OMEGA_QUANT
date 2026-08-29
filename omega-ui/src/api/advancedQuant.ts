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
};

