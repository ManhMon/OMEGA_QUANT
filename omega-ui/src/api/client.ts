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
  pe: number | null;
  pb: number | null;
  roe: number | null;
  piotroskiF: number | null;
  altmanZ: number | null;
  altmanZone?: string | null;
  sector: string;
  marketCapBillionVnd?: number | null;
  adv20BillionVnd?: number | null;
  momentumScore: number | null;
  momentum1m?: number | null;
  momentum3m?: number | null;
  status: 'QUALIFIED' | 'WATCH' | 'DISTRESS' | 'DISQUALIFIED';
}

export function parseNullableNumber(val: unknown): number | null {
  if (val === null || val === undefined) return null;
  if (typeof val === 'number') {
    return Number.isFinite(val) ? val : null;
  }
  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (trimmed === '' || trimmed === 'NaN' || trimmed === 'Infinity' || trimmed === '-Infinity') {
      return null;
    }
    const num = Number(trimmed);
    return Number.isFinite(num) ? num : null;
  }
  return null;
}

export function normalizeStockScreenerItem(raw: unknown): StockScreenerItem {
  if (!raw || typeof raw !== 'object') {
    return {
      ticker: 'UNKNOWN',
      exchange: 'HOSE',
      pe: null,
      pb: null,
      roe: null,
      piotroskiF: null,
      altmanZ: null,
      altmanZone: null,
      sector: 'General',
      marketCapBillionVnd: null,
      adv20BillionVnd: null,
      momentumScore: null,
      momentum1m: null,
      momentum3m: null,
      status: 'WATCH',
    };
  }

  const r = raw as Record<string, unknown>;

  const rawTicker = r.ticker ?? r.symbol ?? r.ticker_symbol ?? r.stock_code;
  const ticker = typeof rawTicker === 'string' && rawTicker.trim()
    ? rawTicker.trim().toUpperCase()
    : 'UNKNOWN';

  const rawExchange = typeof r.exchange === 'string' ? r.exchange.trim().toUpperCase() : '';
  const exchange: 'HOSE' | 'HNX' | 'UPCOM' =
    rawExchange === 'HNX' || rawExchange === 'UPCOM' ? rawExchange : 'HOSE';

  const rawSector = r.sector ?? r.industry ?? r.sector_name;
  const sector = typeof rawSector === 'string' && rawSector.trim()
    ? rawSector.trim()
    : 'General';

  const pe = parseNullableNumber(r.pe ?? r.p_e ?? r.price_to_earnings);
  const pb = parseNullableNumber(r.pb ?? r.p_b ?? r.price_to_book);
  const roe = parseNullableNumber(r.roe ?? r.return_on_equity ?? r.roe_pct);

  const rawPiotroski = parseNullableNumber(r.piotroskiF ?? r.piotroski_f ?? r.f_score ?? r.piotroski);
  const piotroskiF = rawPiotroski != null ? Math.max(0, Math.min(9, Math.round(rawPiotroski))) : null;

  const altmanZ = parseNullableNumber(r.altmanZ ?? r.altman_z ?? r.z_score);
  const marketCapBillionVnd = parseNullableNumber(r.marketCapBillionVnd ?? r.market_cap_billion_vnd ?? r.market_cap);
  const adv20BillionVnd = parseNullableNumber(r.adv20BillionVnd ?? r.adv20_billion_vnd ?? r.adv20 ?? r.adv);

  const momentumScore = parseNullableNumber(r.momentumScore ?? r.momentum_score ?? r.momentum ?? r.quant_score ?? r.hybrid_score);
  const momentum1m = parseNullableNumber(r.momentum1m ?? r.momentum_1m);
  const momentum3m = parseNullableNumber(r.momentum3m ?? r.momentum_3m);
  const altmanZone = typeof r.altman_zone === 'string' ? r.altman_zone.trim().toLowerCase() : typeof r.altmanZone === 'string' ? r.altmanZone.trim().toLowerCase() : null;

  let status: 'QUALIFIED' | 'WATCH' | 'DISTRESS' | 'DISQUALIFIED' = 'WATCH';
  const rawStatus = typeof r.status === 'string' ? r.status.trim().toUpperCase() : typeof r.decision === 'string' ? r.decision.trim().toUpperCase() : '';
  if (rawStatus === 'QUALIFIED' || rawStatus === 'WATCH' || rawStatus === 'DISTRESS' || rawStatus === 'DISQUALIFIED') {
    status = rawStatus as 'QUALIFIED' | 'WATCH' | 'DISTRESS' | 'DISQUALIFIED';
  } else if (r.is_veto === true) {
    status = 'DISQUALIFIED';
  } else if (altmanZone === 'distress' || (piotroskiF !== null && piotroskiF <= 3)) {
    status = 'DISTRESS';
  } else if (r.is_fallback === true) {
    status = 'WATCH';
  } else if (piotroskiF !== null && roe !== null && piotroskiF >= 7 && roe >= 15) {
    status = 'QUALIFIED';
  }

  return {
    ticker,
    exchange,
    pe,
    pb,
    roe,
    piotroskiF,
    altmanZ,
    altmanZone,
    sector,
    marketCapBillionVnd,
    adv20BillionVnd,
    momentumScore: momentumScore ?? momentum1m,
    momentum1m,
    momentum3m,
    status,
  };
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

export interface LakehouseDatasetMeta {
  id: string;
  file_name: string;
  role: string;
  exists: boolean;
  size_mb: number;
  total_rows: number;
  symbols_count: number;
  start_date: string | null;
  end_date: string | null;
  freshness_status: 'HEALTHY' | 'WARNING' | 'STALE' | 'FAILED';
  days_lag: number;
  last_modified: string | null;
}

export interface FreshnessDriftAlert {
  dataset_id: string;
  file_name: string;
  days_lag: number;
  freshness_status: string;
  message: string;
}

export interface LakehouseStatusResponse {
  status: string;
  schema_version: string;
  api_contract_version: number;
  primary_provider: string;
  backup_providers: string[];
  timestamp: string;
  lineage_commit_sha?: string;
  pit_safe_boundary?: string;
  freshness_drift_alerts?: FreshnessDriftAlert[];
  datasets: LakehouseDatasetMeta[];
}

export interface IngestSchedulerTelemetry {
  status: 'HEALTHY' | 'DEGRADED' | 'HALTED' | 'IDLE';
  active_feed: string | null;
  backup_feed: string | null;
  failover_ready: boolean;
  cron_interval: string;
  last_sync_timestamp: string | null;
  next_scheduled_sync: string | null;
  auto_refresh_enabled: boolean;
  active_workers: number;
  stale_threshold_days: number;
  feed_health: Record<string, 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'STANDBY'>;
  provenance_commit: string;
}

export interface DynamicUniverseItem {
  rank: number;
  symbol: string;
  hybrid_score: number;
  quant_score: number;
  llm_score: number;
  roe: number | null;
  momentum_3m: number | null;
  sector: string;
  decision_cutoff: string;
  status_label: 'QUALIFIED' | 'WATCH' | 'DISTRESS' | 'DELISTED';
}

export interface DynamicUniverseResponse {
  status: string;
  schema_version: string;
  api_contract_version: number;
  universe_preset: string;
  total_selected: number;
  top_symbols: string[];
  items: DynamicUniverseItem[];
  model_governance: string;
  provenance_sha256: string;
  quant_weight?: number;
  llm_weight?: number;
  ranking_method?: string;
  score_formula_meta?: Record<string, any>;
}

export interface OptimizationMetricPreview {
  objective: string;
  name: string;
  expected_annual_return_pct: number;
  estimated_volatility_pct: number;
  cvar_95_pct: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  diversification_ratio: number;
  recommended_max_single_weight: number;
  recommended_sector_cap: number;
  recommended_cvar_confidence: number;
  convergence_status: string;
  rationale: string;
}

export interface OptimizationBoundsPreviewResponse {
  status: string;
  schema_version: string;
  generated_at: string;
  objectives: OptimizationMetricPreview[];
}

export interface StrategyBenchmarkItem {
  strategy_id: string;
  name: string;
  is_optimal: boolean;
  sharpe_ratio: number;
  calmar_ratio: number;
  win_rate_pct: number;
  max_drawdown_pct: number;
  annual_return_pct: number;
  annual_volatility_pct: number;
  cpcv_k_folds: number;
  description: string;
}

export interface StrategyBenchmarksResponse {
  status: string;
  schema_version: string;
  benchmark_protocol: string;
  data_release_commit: string;
  artifact_sha256: string;
  generated_at: string;
  total_strategies: number;
  strategies: StrategyBenchmarkItem[];
}

export interface ControlDynamicUniverseParams {
  universe_preset?: string;
  top_n?: number;
  sector_filter?: string;
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

export interface MacroObservation {
  is_synthetic: boolean;
  source: string;
}

export interface MacroNewsItem {
  news_id: string;
  title: string;
  summary?: string | null;
  source: string;
  symbol?: string | null;
  sector?: string | null;
  sentiment_score: number;
  polarity: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  macro_tags: string[];
  entities: string[];
  published_at: string;
  available_at: string;
  url?: string | null;
}

export interface MacroNewsLatestResponse extends MacroObservation {
  status: string;
  total_count: number;
  as_of: string;
  items: MacroNewsItem[];
}

export interface VSIGreedFearResponse extends MacroObservation {
  status: string;
  score: number;
  level: string;
  article_count: number;
  avg_sentiment: number;
  bullish_ratio: number;
  bearish_ratio: number;
  neutral_ratio: number;
  sub_indices: Record<string, number>;
  history_7d: { date: string; as_of: string; vsi_score: number; level: string; article_count: number }[];
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

export interface SectorContagionResponse extends MacroObservation {
  status: string;
  overall_contagion_index: number;
  systemic_risk_level: string;
  as_of: string;
  nodes: SectorContagionNode[];
}

export interface LLMMacroIntelligenceResponse extends MacroObservation {
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

function macroRecord(value: unknown): Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid macro observation');
  return value as Record<string, any>;
}
function macroText(value: unknown, max = 65536): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max) throw new Error('Invalid macro text');
  return value;
}
function macroNumber(value: unknown, min: number, max: number, integer = false): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) throw new Error('Invalid macro number');
  return value;
}
function macroList(value: unknown, max: number): any[] {
  if (!Array.isArray(value) || value.length > max) throw new Error('Invalid macro list');
  return value;
}
function macroStrings(value: unknown) { macroList(value, 100).forEach((item) => macroText(item, 1024)); }

export function macroTime(value: unknown): bigint {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)) throw new Error('Invalid macro timestamp');
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed) || new Date(`${value.slice(0, 10)}T00:00:00Z`).toISOString().slice(0, 10) !== value.slice(0, 10)) throw new Error('Invalid macro timestamp');
  const fraction = /\.(\d{1,9})/.exec(value)?.[1] || '';
  return BigInt(parsed) * 1000000n + BigInt(fraction.padEnd(9, '0').slice(3));
}
function macroSnapshot(value: unknown) {
  const r = macroRecord(value);
  if (r.status !== 'success' || typeof r.is_synthetic !== 'boolean' || macroTime(r.as_of) > BigInt(Date.now()) * 1000000n) throw new Error('Invalid macro snapshot');
  macroText(r.source, 128);
  if ((r.source === 'synthetic_simulation') !== r.is_synthetic) throw new Error('Invalid macro provenance');
  return r;
}
export function validateMacroNews(value: unknown): MacroNewsLatestResponse {
  const r = macroSnapshot(value), ids = new Set<string>();
  const items = macroList(r.items, 100);
  macroNumber(r.total_count, items.length, 1e12, true);
  for (const raw of items) {
    const item = macroRecord(raw), id = macroText(item.news_id, 256);
    if (ids.has(id)) throw new Error('Duplicate macro news');
    ids.add(id); macroText(item.title, 8192); macroText(item.source, 256);
    for (const key of ['summary', 'symbol', 'sector', 'url']) if (item[key] != null) macroText(item[key], key === 'summary' ? 65536 : 8192);
    macroNumber(item.sentiment_score, -1, 1);
    if (!['BULLISH', 'BEARISH', 'NEUTRAL'].includes(item.polarity)) throw new Error('Invalid macro polarity');
    macroStrings(item.macro_tags); macroStrings(item.entities);
    if (macroTime(item.published_at) > macroTime(item.available_at) || macroTime(item.available_at) > macroTime(r.as_of)) throw new Error('Invalid news availability');
  }
  return r as MacroNewsLatestResponse;
}
export function validateMacroVSI(value: unknown): VSIGreedFearResponse {
  const r = macroSnapshot(value);
  macroNumber(r.score, 0, 100); macroNumber(r.article_count, 0, 1e12, true); macroNumber(r.avg_sentiment, -100, 100);
  // Backend classifies before rounding the displayed score; validate vocabulary, not inferred thresholds.
  const levels = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'];
  if (!levels.includes(r.level)) throw new Error('Invalid VSI level');
  const ratios = ['bullish_ratio', 'bearish_ratio', 'neutral_ratio'].map((key) => macroNumber(r[key], 0, 1));
  if (Math.abs(ratios.reduce((a, b) => a + b, 0) - (r.article_count ? 1 : 0)) > 0.001) throw new Error('Invalid VSI ratios');
  const indices = macroRecord(r.sub_indices);
  if (Object.keys(indices).length > 100) throw new Error('Oversized VSI indices');
  Object.values(indices).forEach((n) => macroNumber(n, 0, 100));
  let previous = -1n;
  for (const raw of macroList(r.history_7d, 8)) {
    const point = macroRecord(raw), time = macroTime(point.as_of);
    if (point.date !== point.as_of.slice(0, 10) || time <= previous || time > macroTime(r.as_of)) throw new Error('Invalid VSI history');
    previous = time; macroNumber(point.vsi_score, 0, 100); macroNumber(point.article_count, 0, 1e12, true);
    if (!levels.includes(point.level)) throw new Error('Invalid historical VSI level');
  }
  return r as VSIGreedFearResponse;
}
export function validateMacroContagion(value: unknown): SectorContagionResponse {
  const r = macroSnapshot(value), names = new Set<string>();
  macroNumber(r.overall_contagion_index, 0, 100); macroText(r.systemic_risk_level, 128);
  const nodes = macroList(r.nodes, 32).map(macroRecord);
  for (const node of nodes) {
    const name = macroText(node.sector, 100);
    if (names.has(name)) throw new Error('Duplicate sector');
    names.add(name); macroNumber(node.stress_score, 0, 100); macroNumber(node.sentiment_delta, -1, 1); macroNumber(node.transmission_risk, 0, 1);
    if (!['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'CRITICAL'].includes(node.contagion_level) || !['RISING', 'STABLE', 'FALLING'].includes(node.trend_24h)) throw new Error('Invalid sector state');
  }
  for (const node of nodes) {
    const related = new Set<string>();
    for (const raw of macroList(node.correlated_sectors, 32)) {
      const edge = macroRecord(raw), name = macroText(edge.sector, 100);
      if (name === node.sector || related.has(name)) throw new Error('Invalid sector relationship');
      related.add(name); macroNumber(edge.correlation_weight, 0, 1);
    }
  }
  return r as SectorContagionResponse;
}
export function validateMacroIntelligence(value: unknown): LLMMacroIntelligenceResponse {
  const r = macroSnapshot(value);
  for (const key of ['model', 'prompt_version', 'regime_summary', 'executive_verdict']) macroText(r[key]);
  for (const key of ['primary_risks', 'catalysts', 'macro_tags', 'key_entities']) macroStrings(r[key]);
  const impacts = macroRecord(r.sector_impacts);
  if (Object.keys(impacts).length > 32) throw new Error('Oversized sector impacts');
  Object.entries(impacts).forEach(([key, text]) => { macroText(key, 100); macroText(text); });
  macroNumber(r.sentiment_confidence, 0, 1);
  return r as LLMMacroIntelligenceResponse;
}

// ponytail: macro GETs only, 1 MiB/10 seconds; share transport when wider API scope is authorized.
async function macroRequest<T>(path: string, validate: (value: unknown) => T, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const abort = () => { clearTimeout(timer); controller.abort(); };
  if (signal?.aborted) throw new Error('Macro observation unavailable or invalid.');
  signal?.addEventListener('abort', abort, { once: true });
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  timer = setTimeout(abort, 10000);
  const cancelled = new Promise<never>((_, reject) => controller.signal.addEventListener('abort', () => reject(new Error('Macro observation unavailable or invalid.')), { once: true }));
  try {
    const response = await Promise.race([fetch(`${API_BASE}${path}`, { signal: controller.signal, headers: { Accept: 'application/json' } }), cancelled]);
    if (!response.ok || !response.body) throw new Error('Invalid macro response');
    reader = response.body.getReader();
    const chunks: Uint8Array[] = []; let size = 0;
    while (true) {
      const { done, value } = await Promise.race([reader.read(), cancelled]);
      if (done) break;
      size += value.byteLength;
      if (size > 1048576) throw new Error('Oversized macro response');
      chunks.push(value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
    if (text.startsWith('﻿') || controller.signal.aborted) throw new Error('Invalid macro encoding');
    return validate(JSON.parse(text));
  } catch {
    throw new Error('Macro observation unavailable or invalid.');
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', abort);
    void reader?.cancel().catch(() => {}); controller.abort();
  }
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
    if (filters.pageSize !== undefined && filters.pageSize !== null) params.append('limit', String(filters.pageSize));
    if (filters.minPiotroski) params.append('min_piotroski', String(filters.minPiotroski));
    if (filters.minRoe) params.append('min_roe', String(filters.minRoe));
    if (filters.minAltmanZ) params.append('min_altman_z', String(filters.minAltmanZ));
    if (filters.status) params.append('status', String(filters.status));
    if (filters.sector) params.append('sector', String(filters.sector));
    if (filters.exchange) params.append('exchange', String(filters.exchange));
    const qs = params.toString() ? `?${params.toString()}` : '';
    const rawResp = await apiRequest<PaginatedResponse<unknown>>(`/api/v1/quant/screener${qs}`);
    return {
      ...rawResp,
      data: Array.isArray(rawResp?.data) ? rawResp.data.map(normalizeStockScreenerItem) : [],
    };
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

  getLakehouseStatus: async (signal?: AbortSignal): Promise<LakehouseStatusResponse> => {
    return apiRequest<LakehouseStatusResponse>('/api/v1/control/lakehouse-status', { signal });
  },

  getIngestSchedulerTelemetry: async (signal?: AbortSignal, probe = false): Promise<IngestSchedulerTelemetry> => {
    return apiRequest<IngestSchedulerTelemetry>(`/api/v1/control/ingest-scheduler/telemetry${probe ? '?probe=true' : ''}`, { signal });
  },

  getControlReceipts: async (limit = 50, signal?: AbortSignal): Promise<{ status: string; total_receipts: number; receipts: TaskReceipt[]; artifact_root: string }> => {
    return apiRequest<{ status: string; total_receipts: number; receipts: TaskReceipt[]; artifact_root: string }>(`/api/v1/control/receipts?limit=${limit}`, { signal });
  },

  getOptimizationBoundsPreview: async (): Promise<OptimizationBoundsPreviewResponse> => {
    return apiRequest<OptimizationBoundsPreviewResponse>('/api/v1/control/optimization-bounds-preview');
  },

  getStrategyBenchmarks: async (signal?: AbortSignal): Promise<StrategyBenchmarksResponse> => {
    return apiRequest<StrategyBenchmarksResponse>('/api/v1/control/strategy-benchmarks', { signal });
  },

  getControlDynamicUniverse: async (params?: ControlDynamicUniverseParams, signal?: AbortSignal): Promise<DynamicUniverseResponse> => {
    const query = new URLSearchParams();
    if (params?.universe_preset) query.set('universe_preset', params.universe_preset);
    if (params?.top_n) query.set('top_n', String(params.top_n));
    if (params?.sector_filter) query.set('sector_filter', params.sector_filter);
    const qs = query.toString();
    return apiRequest<DynamicUniverseResponse>(`/api/v1/control/dynamic-universe${qs ? `?${qs}` : ''}`, { signal });
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
  getMacroNewsLatest: async (params: { limit?: number; ticker?: string; sector?: string; as_of?: string } = {}, signal?: AbortSignal): Promise<MacroNewsLatestResponse> => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set('limit', String(macroNumber(params.limit, 1, 100, true)));
    if (params.ticker !== undefined) query.set('ticker', macroText(params.ticker, 32));
    if (params.sector !== undefined) query.set('sector', macroText(params.sector, 100));
    if (params.as_of !== undefined) { macroTime(params.as_of); query.set('as_of', params.as_of); }
    return macroRequest(`/api/v1/macro/news/latest?${query}`, validateMacroNews, signal);
  },

  getVSISentiment: async (asOf?: string, signal?: AbortSignal): Promise<VSIGreedFearResponse> => {
    const query = new URLSearchParams();
    if (asOf !== undefined) { macroTime(asOf); query.set('as_of', asOf); }
    return macroRequest(`/api/v1/sentiment/vsi?${query}`, validateMacroVSI, signal);
  },

  getSectorContagion: async (signal?: AbortSignal): Promise<SectorContagionResponse> => {
    return macroRequest('/api/v1/sentiment/contagion', validateMacroContagion, signal);
  },

  getLLMMacroAnalysis: async (signal?: AbortSignal): Promise<LLMMacroIntelligenceResponse> => {
    return macroRequest('/api/v1/sentiment/llm-analysis', validateMacroIntelligence, signal);
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
