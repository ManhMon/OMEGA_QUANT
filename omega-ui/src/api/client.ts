export interface LLMProfileItem {
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  enabled: boolean;
  has_key?: boolean;
}

export interface MultiProfileLLMConfigPayload {
  global_profile: LLMProfileItem;
  alpha_quant: LLMProfileItem;
  news_sentiment: LLMProfileItem;
  macro_micro: LLMProfileItem;
}

export interface LLMConfigResponse {
  status: string;
  timestamp: string;
  message?: string;
  profiles: {
    global_profile: LLMProfileItem;
    alpha_quant: LLMProfileItem;
    news_sentiment: LLMProfileItem;
    macro_micro: LLMProfileItem;
  };
}

export interface LLMProbeTestRequest {
  profile_key: 'global_profile' | 'alpha_quant' | 'news_sentiment' | 'macro_micro';
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
  temperature: number;
  timeout_seconds: number;
}

export interface LLMProbeTestResponse {
  status: 'success' | 'error';
  profile_key: string;
  provider: string;
  model: string;
  latency_ms: number;
  message: string;
  timestamp: string;
  error_code?: string;
  retryable?: boolean;
}

export interface LLMModelItem {
  id: string;
  name: string;
  category: 'FRONTIER' | 'INSTITUTIONAL' | 'FAST' | 'LOCAL' | 'LEGACY' | 'GENERAL';
  context_window?: number;
  description?: string;
}

export interface LLMModelFetchRequest {
  provider: string;
  base_url?: string;
  api_key?: string;
  profile_key?: 'global_profile' | 'alpha_quant' | 'news_sentiment' | 'macro_micro';
  timeout_seconds?: number;
}

export interface LLMModelFetchResponse {
  status: string;
  provider: string;
  source: string;
  models: LLMModelItem[];
  total_count: number;
  message: string;
  timestamp: string;
  error_code?: string;
  retryable?: boolean;
  offline_suggestions?: boolean;
}

export interface MacroMetrics {
  hmmRegime: 'EXPANSION' | 'NEUTRAL_CHOP' | 'HIGH_VOL_BEAR' | 'CRISIS';
  regimeConfidence: number;
  marketBreadth: number;
  advanceDeclineRatio: number;
  macroStressIndex: number;
  vsiTurbulence: number;
  fxVolatility: 'LOW' | 'NORMAL' | 'HIGH';
  interbankRate: number;
  sbvOmoNetInjectionBillionVnd: number;
  foreignNetFlowBillionVnd: number;
  stateProbabilities: {
    bullExpansion: number;
    neutralChop: number;
    highVolBear: number;
  };
  timestamp: string;
}

export interface StockScreenerItem {
  ticker: string;
  exchange: 'HOSE' | 'HNX' | 'UPCOM';
  pe: number;
  pb: number;
  roe: number;
  piotroskiF: number;
  altmanZ: number;
  sector: string;
  marketCapBillionVnd: number;
  adv20BillionVnd: number;
  momentumScore: number;
  status: 'QUALIFIED' | 'WATCH' | 'DISQUALIFIED';
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface ScreenerFilters {
  search?: string;
  exchange?: string;
  sector?: string;
  minPiotroski?: number;
  minRoe?: number;
  minAltmanZ?: number;
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface PortfolioHolding {
  symbol: string;
  weight: number;
  alphaScore: number;
  barraMomentum: number;
  barraValue: number;
  barraSize: number;
  turnoverContribution: number;
  sector: string;
  unrealizedPnlPercent: number;
}

export interface PortfolioState {
  expectedIrAnnualized: number;
  portfolioBeta: number;
  maxDrawdownEstimatePercent: number;
  dailyTurnoverEstimatePercent: number;
  icMean: number;
  icTStat: number;
  cvar99Percent: number;
  totalAumBillionVnd: number;
  holdings: PortfolioHolding[];
  timestamp: string;
}

export interface OrderBlotterItem {
  orderId: string;
  timestamp: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  orderType: 'LO' | 'ATO' | 'ATC' | 'MP';
  qty: number;
  price: number;
  filledQty: number;
  status: 'FILLED' | 'PENDING' | 'ROUTING' | 'CANCELLED';
  broker: 'VNDIRECT' | 'SSI' | 'VPS' | 'VCI';
  algoType: 'TWAP' | 'VWAP' | 'DIRECT';
}

export interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartStationData {
  ticker: string;
  interval: string;
  currentPrice: number;
  priceChangePercent: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  rsi14: number;
  macd1226: number;
  obvMillion: number;
  candles: CandleData[];
}

export interface OrderbookLevel {
  level: number;
  price: number;
  volume: number;
  orders: number;
}

export interface OrderbookData {
  status: string;
  symbol: string;
  exchange: string;
  timestamp: string;
  reference_price: number;
  ceiling_price: number;
  floor_price: number;
  spread: number;
  spread_bps: number;
  total_bid_depth: number;
  total_ask_depth: number;
  bids: OrderbookLevel[];
  asks: OrderbookLevel[];
}

export interface MarketOhlcvResponse {
  status: string;
  symbol: string;
  exchange: string;
  total_bars: number;
  bars: CandleData[];
}

export interface StreamUpdate {
  type: 'TICK' | 'ORDER_UPDATE' | 'REGIME_SHIFT' | 'ALERT';
  data: Record<string, unknown>;
  timestamp: string;
}

export interface PipelineRunParams {
  universe?: string[];
  start_date?: string;
  end_date?: string;
  as_of_time?: string;
  rebalance_frequency?: string;
  initial_capital?: number;
  slippage_bps?: number;
  commission_bps?: number;
  max_single_weight?: number;
  alpha_families?: string[];
  mode?: 'IN_PROCESS' | 'DRY_RUN';
}

export interface PipelineRunResponse {
  status: string;
  job_id: string;
  task_id: string;
  message: string;
  stream_url: string;
}

export interface PipelineCancelResponse {
  status: string;
  job_id: string;
  task_id: string;
  cancelled: boolean;
  message: string;
  timestamp: string;
}

export interface PipelineStreamEvent {
  task_id?: string;
  job_id?: string;
  event_type: 'SNAPSHOT' | 'PROGRESS' | 'PING' | 'COMPLETE' | 'ERROR' | 'CANCELLED';
  progress: number | null;
  stage?: string;
  status?: string;
  message?: string;
  payload?: Record<string, any>;
  timestamp: string;
}

export interface TaskReceipt {
  schema_version: number;
  task_id: string;
  operation: string;
  status: 'COMPLETED';
  request_fingerprint: string;
  output_sha256: string;
  published_at: string;
  artifact_id?: string;
}

export interface IngestDataParams {
  symbols?: string[];
  sources?: string[];
  start_date?: string;
  end_date?: string;
  force_refresh?: boolean;
}

export interface ComputeAlphasParams {
  universe?: string[];
  alpha_families?: string[];
  start_date?: string;
  end_date?: string;
  as_of_time?: string;
}

export interface OptimizePortfolioParams {
  objective?: string;
  universe?: string[];
  start_date?: string;
  end_date?: string;
  as_of_time?: string;
  max_single_weight?: number;
}

export interface RunBacktestParams {
  strategy_id?: string;
  universe?: string[];
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  slippage_bps?: number;
  commission_bps?: number;
  include_benchmark?: boolean;
  as_of_time?: string;
}

export interface RebalanceParams {
  totp_code: string;
  target_portfolio?: Record<string, number>;
  strategy_id?: string;
  portfolio_value?: number;
  drift_threshold?: number;
  max_turnover?: number;
}

export interface RebalanceResponse {
  status: string;
  job_id: string;
  timestamp: string;
  totp_verified: boolean;
  strategy_id: string;
  should_rebalance: boolean;
  reason: string;
  estimated_turnover: number;
  estimated_cost_vnd: number;
  target_changes: Record<string, any>;
  liquidity_violations: Record<string, any>;
}

export interface KillSwitchParams {
  totp_code: string;
  reason?: string;
  cancel_active_orders?: boolean;
  freeze_engines?: boolean;
}

export interface ControlTaskResponse {
  status: string;
  task_id: string;
  message: string;
  stream_url: string;
}

export interface KillSwitchResponse {
  status: string;
  timestamp: string;
  totp_verified: boolean;
  kill_switch_active: boolean;
  cancelled_orders_count: number;
  frozen_engines_count: number;
  reason: string;
  message: string;
}

export interface TaskProgressEvent {
  task_id?: string;
  job_id?: string;
  event_type?: 'SNAPSHOT' | 'PROGRESS' | 'PING' | 'COMPLETE' | 'ERROR' | 'CANCELLED';
  progress?: number | null;
  stage?: string;
  message?: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

export interface EvaluateExpressionRequest {
  expression: string;
  universe?: string;
  sample_data?: Record<string, number[]>;
}

export interface EvaluateExpressionResponse {
  status: string;
  expression: string;
  is_valid: boolean;
  ast_type: string;
  sample_result?: number[];
  ic_estimate: number;
  ir_estimate: number;
  turnover_estimate_pct: number;
  complexity_score: number;
  ast_tree: Record<string, unknown>;
  error?: string;
}

export interface AlphaSignalItem {
  alpha_id: string;
  name: string;
  category: string;
  formula: string;
  ic_mean: number;
  ic_tstat: number;
  ir_annualized: number;
  turnover_daily_pct: number;
  decay_half_life_days: number;
  status: 'ACTIVE' | 'CANDIDATE' | 'DECAYED' | 'INCUBATING';
  last_updated: string;
}

export interface DecayProfilePoint {
  lag_days: number;
  ic: number;
  ir: number;
  sharpe: number;
  correlation_decay: number;
}

export interface DecayProfileResponse {
  alpha_id: string;
  name: string;
  half_life_days: number;
  decay_regime: 'SLOW_DECAY' | 'MODERATE' | 'RAPID_DECAY';
  profile: DecayProfilePoint[];
}

export interface StartDiscoveryRequest {
  population_size?: number;
  generations?: number;
  mutation_rate?: number;
  crossover_rate?: number;
  target_ic?: number;
  target_ir?: number;
  allowed_operators?: string[];
}

export interface StartDiscoveryResponse {
  status: string;
  session_id: string;
  message: string;
  stream_url: string;
}

export interface DiscoveryProgressEvent {
  session_id: string;
  event_type: 'SNAPSHOT' | 'GENERATION_UPDATE' | 'DISCOVERY_COMPLETED' | 'PING';
  generation: number;
  max_generations: number;
  progress: number;
  best_fitness: number;
  best_formula: string;
  message?: string;
  population_sample?: { id: string; formula: string; ic: number; ir: number; fitness: number }[];
  timestamp: string;
}

export interface BacktestResultData {
  strategy_id: string;
  cagr_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  calmar_ratio: number;
  win_rate_pct: number;
  total_trades: number;
  alpha_vs_vnindex_pct: number;
  equity_curve: { date: string; strategy_nav: number; vnindex_nav: number; drawdown_pct: number }[];
  monthly_returns: { year: number; months: number[] }[];
}

export interface MacroNewsItem {
  news_id: string;
  title: string;
  summary?: string;
  source: string;
  symbol?: string;
  sector?: string;
  sentiment_score: number;
  polarity: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  macro_tags: string[];
  entities: string[];
  published_at: string;
  url?: string;
}

export interface MacroNewsLatestResponse {
  status: string;
  total_count: number;
  as_of: string;
  items: MacroNewsItem[];
}

export interface VSIGreedFearResponse {
  status: string;
  score: number;
  level: string;
  article_count: number;
  avg_sentiment: number;
  bullish_ratio: number;
  bearish_ratio: number;
  neutral_ratio: number;
  sub_indices: Record<string, number>;
  history_7d: { date: string; vsi_score: number; level: string }[];
  as_of: string;
}

export interface SectorContagionNode {
  sector: string;
  stress_score: number;
  contagion_level: 'LOW' | 'NORMAL' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
  trend_24h: 'RISING' | 'STABLE' | 'FALLING';
  sentiment_delta: number;
  transmission_risk: number;
  correlated_sectors: { sector: string; correlation_weight: number }[];
}

export interface SectorContagionResponse {
  status: string;
  overall_contagion_index: number;
  systemic_risk_level: string;
  as_of: string;
  nodes: SectorContagionNode[];
}

export interface LLMMacroIntelligenceResponse {
  status: string;
  as_of: string;
  model: string;
  prompt_version: string;
  regime_summary: string;
  primary_risks: string[];
  catalysts: string[];
  sector_impacts: Record<string, string>;
  macro_tags: string[];
  key_entities: string[];
  sentiment_confidence: number;
  executive_verdict: string;
}

export interface BarraFactorExposure {
  name: string;
  exposure: number;
  variance_contribution_pct: number;
  t_stat: number;
  status: string;
}

export interface BarraAssetExposure {
  symbol: string;
  sector: string;
  weight_pct: number;
  market_beta: number;
  size_smb: number;
  value_hml: number;
  momentum: number;
  volatility: number;
  specific_risk_pct: number;
}

export interface BarraDecompositionResponse {
  status: string;
  timestamp: string;
  model: string;
  total_risk_annualized_pct: number;
  factor_risk_pct: number;
  specific_risk_pct: number;
  factor_variance_ratio_pct: number;
  portfolio_r_squared: number;
  factors: BarraFactorExposure[];
  asset_exposures: BarraAssetExposure[];
}

export interface StressScenarioItem {
  scenario_id: string;
  name: string;
  description: string;
  estimated_portfolio_pnl_pct: number;
  max_loss_vnd_billion: number;
  risk_level: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
  benchmark_pnl_pct: number;
  alpha_resilience_pct: number;
}

export interface StressScenariosResponse {
  status: string;
  timestamp: string;
  cvar_95_pct: number;
  cvar_99_pct: number;
  var_95_pct: number;
  risk_warning: string;
  risk_concentration: { symbol: string; risk_contribution_pct: number }[];
  scenarios: StressScenarioItem[];
}

export interface PreTradeImpactRequest {
  symbol: string;
  order_size: number;
  average_daily_volume: number;
  volatility?: number;
  participation_rate?: number;
  side?: 'BUY' | 'SELL';
  arrival_price?: number;
}

export interface PreTradeImpactResponse {
  status: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_size: number;
  arrival_price: number;
  order_notional_vnd: number;
  order_adv_pct: number;
  estimated_impact_bps: number;
  spread_cost_bps: number;
  total_cost_bps: number;
  estimated_execution_price: number;
  total_cost_vnd: number;
  timing_risk_bps: number;
  recommended_algo: 'DIRECT' | 'TWAP' | 'VWAP' | 'ICEBERG';
  recommended_duration_min: number;
  volatility_used: number;
  participation_rate: number;
}

export interface TCATradeItem {
  trade_id: string;
  timestamp: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  parent_quantity: number;
  filled_quantity: number;
  avg_fill_price: number;
  benchmark_price: number;
  pre_trade_impact_bps: number;
  post_trade_slippage_bps: number;
  implementation_shortfall_bps: number;
  traded_value_vnd: number;
  broker: string;
  algo: string;
  status: string;
}

export interface PostTradeTCAReportResponse {
  status: string;
  timestamp: string;
  summary: {
    num_trades: number;
    total_traded_value_billion_vnd: number;
    average_is_bps: number;
    average_slippage_bps: number;
    max_is_bps: number;
    min_is_bps: number;
    total_savings_vs_arrival_bps: number;
  };
  trades: TCATradeItem[];
}

export interface BrokerRoutingDiagnostics {
  broker: string;
  channel: string;
  ping_ms: number;
  fill_rate_pct: number;
  price_improvement_bps: number;
  rejection_rate_pct: number;
  status: 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
  active_routes: number;
}

export interface ActiveExecutionQueue {
  queue_id: string;
  symbol: string;
  algo: string;
  active_slices: number;
  total_slices: number;
  completion_pct: number;
  target_qty: number;
  filled_qty: number;
  obi_pressure: number;
}

export interface RoutingDiagnosticsResponse {
  status: string;
  timestamp: string;
  engine: string;
  total_active_orders: number;
  total_active_slices: number;
  avg_roundtrip_latency_ms: number;
  routers: BrokerRoutingDiagnostics[];
  active_queues: ActiveExecutionQueue[];
}

export interface CopilotSystemSynthesisResponse {
  status: string;
  timestamp: string;
  focus_symbol: string;
  macro: {
    regime: string;
    regime_confidence_pct: number;
    vsi_sentiment_score: number;
    vsi_sentiment_level: string;
    sbv_omo_injection_billion_vnd: number;
    foreign_net_flow_billion_vnd: number;
    systemic_stress_index: number;
    fx_volatility: string;
    interbank_rate_pct: number;
  };
  alpha: {
    active_alphas_count: number;
    candidate_alphas_count: number;
    total_alpha_universe: number;
    mean_ic: number;
    ic_tstat: number;
    top_active_signal: {
      alpha_id: string;
      name: string;
      category: string;
      ic: number;
      ir: number;
      turnover_pct: number;
    };
  };
  screener: {
    universe_size: number;
    qualified_count: number;
    watch_count: number;
    target_ticker_profile: {
      ticker: string;
      pe: number;
      pb: number;
      roe_pct: number;
      piotroski_f: number;
      altman_z: number;
      status: string;
    };
  };
  risk_tca: {
    portfolio_total_risk_annualized_pct: number;
    factor_risk_pct: number;
    specific_risk_pct: number;
    cvar_95_pct: number;
    cvar_99_pct: number;
    top_risk_contributor: string;
    avg_is_bps: number;
    avg_slippage_bps: number;
    active_broker_routes: number;
    fastest_gateway: string;
  };
  pipeline: {
    in_process_engine_status: string;
    last_job_status: string;
    kill_switch_active: boolean;
    sod_boundary_isolated: boolean;
    audit_verification_status: string;
  };
  executive_quant_score: number;
  holistic_verdict: string;
  verdict_reasoning_vi: string;
  verdict_reasoning_en: string;
}

export interface RecommendationActionItem {
  id: string;
  category: 'REBALANCE' | 'RISK_MITIGATION' | 'ALPHA_HARVEST' | 'HEDGE' | 'EXECUTION_TIMING';
  title: string;
  description: string;
  impact_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  confidence_score: number;
  target_symbol?: string;
  action_type: 'DISPATCH_REBALANCE' | 'TRIGGER_PIPELINE' | 'ADJUST_POSITION' | 'EXECUTE_ORDER' | 'RUN_BACKTEST';
  payload: Record<string, any>;
  created_at: string;
}

export interface CopilotRecommendationsResponse {
  status: string;
  timestamp: string;
  total_recommendations: number;
  recommendations: RecommendationActionItem[];
}

export interface CopilotAskRequest {
  query: string;
  context_ticker?: string;
  active_module?: string;
  temperature?: number;
}

export interface CopilotExecutedToolItem {
  tool_name: string;
  action_type?: string;
  status?: string;
  target?: string;
  parameters?: Record<string, any>;
  result?: Record<string, any>;
  timestamp?: string;
}

export interface CopilotToolExecutionRequest {
  tool_name: string;
  parameters?: Record<string, any>;
}

export interface CopilotToolExecutionResponse {
  status: string;
  timestamp: string;
  tool_name: string;
  action_type: string;
  execution_result: Record<string, any>;
  message: string;
}

export interface CopilotAskResponse {
  status: string;
  timestamp: string;
  query: string;
  intent: string;
  focus_ticker: string;
  response_vi: string;
  response_en: string;
  metrics: Record<string, any>;
  suggested_actions: string[];
  executed_tools?: CopilotExecutedToolItem[];
  confidence: number;
}

export interface CopilotStreamEvent {
  event_type: string;
  title: string;
  severity: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR';
  timestamp: string;
  payload: Record<string, any>;
}

export interface DynamicUniverseSymbolItem {
  symbol: string;
  sector: string;
  score: number;
  adv_billion_vnd: number;
  status: string;
}

export interface DynamicUniverseResponse {
  status: string;
  timestamp: string;
  selector_model: string;
  total_evaluated: number;
  total_selected: number;
  selected_symbols: string[];
  sector_weights: Record<string, number>;
  selected_details: DynamicUniverseSymbolItem[];
  excluded_summary: Record<string, string>;
}

export interface DynamicUniverseQueryParams {
  min_adv_billion?: number;
  top_n?: number;
  sector_cap?: number;
  min_score?: number;
}

export const API_BASE = typeof window !== 'undefined' && window.location?.origin
  ? (window.location.port === '3000' || window.location.port === '5173' ? 'http://127.0.0.1:8000' : window.location.origin)
  : 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly errorCode: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
  });
  const body = await response.json().catch(() => null) as Record<string, unknown> | null;
  if (!response.ok) {
    const detail = body?.detail;
    const envelope = detail && typeof detail === 'object' ? detail as Record<string, unknown> : body;
    const code = typeof envelope?.error_code === 'string'
      ? envelope.error_code
      : typeof detail === 'string' ? detail : `HTTP_${response.status}`;
    const message = typeof envelope?.message === 'string' ? envelope.message : code;
    throw new ApiError(response.status, code, message, typeof envelope?.request_id === 'string' ? envelope.request_id : undefined);
  }
  return body as T;
}

export const apiClient = {
  getMarketOhlcv: async (symbol: string, start?: string, end?: string, limit = 500): Promise<MarketOhlcvResponse> => {
    const params = new URLSearchParams();
    if (start) params.append('start', start);
    if (end) params.append('end', end);
    if (limit) params.append('limit', String(limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiRequest<MarketOhlcvResponse>(`/api/v1/market/ohlcv/${encodeURIComponent(symbol)}${qs}`);
  },

  getMarketOrderbook: async (symbol: string, depth = 10): Promise<OrderbookData> => {
    return apiRequest<OrderbookData>(`/api/v1/market/orderbook/${encodeURIComponent(symbol)}?depth=${depth}`);
  },

  getMacroData: async (): Promise<MacroMetrics> => {
    return apiRequest<MacroMetrics>('/api/v1/macro/summary');
  },

  getQuantScreener: async (filters: ScreenerFilters = {}): Promise<PaginatedResponse<StockScreenerItem>> => {
    const params = new URLSearchParams();
    if (filters.search) params.append('symbol', filters.search);
    if (filters.page) params.append('page', String(filters.page));
    if (filters.pageSize) params.append('limit', String(filters.pageSize));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiRequest<PaginatedResponse<StockScreenerItem>>(`/api/v1/quant/screener${qs}`);
  },

  getPortfolioState: async (): Promise<PortfolioState> => {
    return apiRequest<PortfolioState>('/api/v1/portfolio/state');
  },

  getExecutionBlotter: async (): Promise<OrderBlotterItem[]> => {
    return apiRequest<OrderBlotterItem[]>('/api/v1/execution/blotter');
  },

  getChartData: async (ticker = 'FPT', interval = '1D'): Promise<ChartStationData> => {
    return apiRequest<ChartStationData>(`/api/v1/market/chart/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}`);
  },

  // Control APIs (Phase 5)
  ingestData: async (params: IngestDataParams = {}): Promise<ControlTaskResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/ingest-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to dispatch ingest task: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  computeAlphas: async (params: ComputeAlphasParams = {}): Promise<ControlTaskResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/compute-alphas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to compute alphas: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  optimizePortfolio: async (params: OptimizePortfolioParams = {}): Promise<ControlTaskResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/optimize-portfolio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to optimize portfolio: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  runBacktest: async (params: RunBacktestParams = {}): Promise<ControlTaskResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/run-backtest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to run backtest: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  killSwitch: async (params: KillSwitchParams): Promise<KillSwitchResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/kill-switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to trigger kill switch: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  triggerRebalance: async (params: RebalanceParams): Promise<RebalanceResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/rebalance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to execute rebalance: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getBacktestReport: async (strategyId = 'ALPHA_HRP_V2'): Promise<BacktestResultData> => {
    const resp = await fetch(`${API_BASE}/api/v1/strategy/backtest/${encodeURIComponent(strategyId)}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch backtest report for ${strategyId}: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Alpha Factory & Discovery APIs (Phase 6)
  evaluateAlphaExpression: async (req: EvaluateExpressionRequest): Promise<EvaluateExpressionResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/alpha/ast/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Failed to evaluate alpha expression: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getAlphaArsenalSignals: async (params: { category?: string; status?: string; search?: string; limit?: number } = {}): Promise<{ status: string; total_available: number; count: number; signals: AlphaSignalItem[] }> => {
    const qParams = new URLSearchParams();
    if (params.category) qParams.append('category', params.category);
    if (params.status) qParams.append('status', params.status);
    if (params.search) qParams.append('search', params.search);
    if (params.limit) qParams.append('limit', String(params.limit));

    const resp = await fetch(`${API_BASE}/api/v1/alpha/arsenal/signals?${qParams.toString()}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch alpha arsenal signals: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getAlphaDecayProfile: async (alphaId: string): Promise<DecayProfileResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/alpha/decay-profile/${encodeURIComponent(alphaId)}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch alpha decay profile for ${alphaId}: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  startAlphaDiscovery: async (req: StartDiscoveryRequest = {}): Promise<StartDiscoveryResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/alpha/discovery/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Failed to start alpha discovery: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Macro News & LLM Sentiment APIs (Phase 7)
  getMacroNewsLatest: async (params: { limit?: number; ticker?: string; sector?: string } = {}): Promise<MacroNewsLatestResponse> => {
    const qParams = new URLSearchParams();
    if (params.limit) qParams.append('limit', String(params.limit));
    if (params.ticker) qParams.append('ticker', params.ticker);
    if (params.sector) qParams.append('sector', params.sector);

    const resp = await fetch(`${API_BASE}/api/v1/macro/news/latest?${qParams.toString()}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch latest macro news: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getVSISentiment: async (asOf?: string): Promise<VSIGreedFearResponse> => {
    const qParams = new URLSearchParams();
    if (asOf) qParams.append('as_of', asOf);

    const resp = await fetch(`${API_BASE}/api/v1/sentiment/vsi?${qParams.toString()}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch VSI sentiment: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getSectorContagion: async (): Promise<SectorContagionResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/sentiment/contagion`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch sector contagion: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getLLMMacroAnalysis: async (): Promise<LLMMacroIntelligenceResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/sentiment/llm-analysis`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch LLM macro analysis: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Phase 8: Barra Multi-Factor Risk & TCA Analytics
  getBarraDecomposition: async (): Promise<BarraDecompositionResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/risk/barra/decomposition`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch Barra risk decomposition: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getStressScenarios: async (): Promise<StressScenariosResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/risk/stress-scenarios`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch stress scenarios: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  calculatePreTradeImpact: async (req: PreTradeImpactRequest): Promise<PreTradeImpactResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/risk/tca/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Failed to calculate pre-trade impact: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getPostTradeReport: async (): Promise<PostTradeTCAReportResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/tca/post-trade-report`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch post-trade TCA report: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getRoutingDiagnostics: async (): Promise<RoutingDiagnosticsResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/execution/routing-diagnostics`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch routing diagnostics: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Phase 9: Real-Engine Pipeline Bridge
  triggerPipelineRun: async (params: PipelineRunParams = {}): Promise<PipelineRunResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/pipeline-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      throw new Error(`Failed to trigger pipeline run: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  cancelPipelineRun: async (jobId: string): Promise<PipelineCancelResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/cancel/${encodeURIComponent(jobId)}`, {
      method: 'POST',
    });
    if (!resp.ok) {
      throw new Error(`Failed to cancel pipeline run ${jobId}: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getControlOpsStatus: async (): Promise<{ status: string; kill_switch_active: boolean; active_tasks_count: number; total_tasks_count: number; recent_tasks: any[] }> => {
    const resp = await fetch(`${API_BASE}/api/v1/control/status`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch control ops status: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Phase 11: Omni-Quant AI Copilot & Real-Time Recommendation Assistant
  getCopilotSystemSynthesis: async (contextTicker?: string): Promise<CopilotSystemSynthesisResponse> => {
    const qParams = new URLSearchParams();
    if (contextTicker) qParams.append('context_ticker', contextTicker);

    const resp = await fetch(`${API_BASE}/api/v1/copilot/system-synthesis?${qParams.toString()}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch system synthesis: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getCopilotRecommendations: async (limit = 10): Promise<CopilotRecommendationsResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/actionable-recommendations?limit=${limit}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch recommendations: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  askCopilot: async (req: CopilotAskRequest): Promise<CopilotAskResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Copilot query failed: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  executeCopilotTool: async (req: CopilotToolExecutionRequest): Promise<CopilotToolExecutionResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/execute-tool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Copilot tool execution failed: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  // Phase 12: LLM Multi-Profile Configuration Engine APIs
  getLLMConfig: async (): Promise<LLMConfigResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/config`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch LLM configuration: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  updateLLMConfig: async (payload: MultiProfileLLMConfigPayload): Promise<LLMConfigResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => null);
      let errorMsg = `Failed to save LLM configuration: HTTP ${resp.status} ${resp.statusText}`;
      if (errBody?.detail) {
        if (Array.isArray(errBody.detail)) {
          errorMsg = errBody.detail
            .map((d: any) => (typeof d === 'object' && d?.msg ? (d.loc ? d.loc.join('.') + ': ' : '') + d.msg : JSON.stringify(d)))
            .join('; ');
        } else if (typeof errBody.detail === 'object') {
          errorMsg = JSON.stringify(errBody.detail);
        } else {
          errorMsg = String(errBody.detail);
        }
      }
      throw new Error(errorMsg);
    }
    return await resp.json();
  },

  testLLMProbe: async (req: LLMProbeTestRequest): Promise<LLMProbeTestResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/config/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Failed to probe model: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  getDynamicUniverse: async (params?: DynamicUniverseQueryParams): Promise<DynamicUniverseResponse> => {
    const q = new URLSearchParams();
    if (params?.min_adv_billion !== undefined) q.append('min_adv_billion', params.min_adv_billion.toString());
    if (params?.top_n !== undefined) q.append('top_n', params.top_n.toString());
    if (params?.sector_cap !== undefined) q.append('sector_cap', params.sector_cap.toString());
    if (params?.min_score !== undefined) q.append('min_score', params.min_score.toString());

    const qs = q.toString() ? `?${q.toString()}` : '';
    const resp = await fetch(`${API_BASE}/api/v1/portfolio/dynamic-universe${qs}`);
    if (!resp.ok) {
      throw new Error(`Failed to fetch dynamic universe: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  },

  fetchLLMModels: async (req: LLMModelFetchRequest): Promise<LLMModelFetchResponse> => {
    const resp = await fetch(`${API_BASE}/api/v1/copilot/config/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`Failed to fetch LLM models: HTTP ${resp.status} ${resp.statusText}`);
    }
    return await resp.json();
  }
};
