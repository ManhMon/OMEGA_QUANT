import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient, API_BASE } from '../api/client';
import type { CopilotAskResponse, CopilotExecutedToolItem, CopilotStreamEvent, CopilotSystemSynthesisResponse, RecommendationActionItem } from '../api/client';
import { useUiStore } from '../store/uiStore';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  textVi: string;
  textEn: string;
  executedTools?: CopilotExecutedToolItem[];
  suggestedActions?: string[];
}

const INVALID = 'Copilot returned an invalid response.';
const FAILED = 'Copilot request failed. Retry manually.';
const UNAVAILABLE = 'Copilot integration unavailable.';
const TIMEOUT_MS = 15000;
const MAX_TEXT = 16000;
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string' && value.length <= MAX_TEXT;
const timestamp = (value: unknown) => text(value) && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12;
const member = (value: unknown, choices: string[]) => typeof value === 'string' && choices.includes(value);

function bounded(value: unknown, depth = 0): boolean {
  if (depth > 8) return false;
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'number') return finite(value);
  if (typeof value === 'string') return text(value);
  if (Array.isArray(value)) return value.length <= 100 && value.every(item => bounded(item, depth + 1));
  return object(value) && Object.keys(value).length <= 100 && Object.entries(value).every(([key, item]) => text(key) && bounded(item, depth + 1));
}

function success(value: unknown): asserts value is Record<string, unknown> {
  if (!object(value)) throw new Error(INVALID);
  if (member(value.status, ['unavailable', 'disabled'])) throw new Error(UNAVAILABLE);
  if (value.status !== 'success' || !timestamp(value.timestamp) || !bounded(value)) throw new Error(INVALID);
}

function fields(value: unknown, strings: string[], numbers: string[] = []) {
  return object(value) && strings.every(key => text(value[key]) && Boolean(value[key])) && numbers.every(key => finite(value[key]));
}

function synthesisResponse(value: unknown): CopilotSystemSynthesisResponse {
  success(value);
  if (!fields(value, ['focus_symbol', 'holistic_verdict', 'verdict_reasoning_vi', 'verdict_reasoning_en'], ['executive_quant_score']) ||
      (value.executive_quant_score as number) < 0 || (value.executive_quant_score as number) > 100 ||
      !fields(value.macro, ['regime', 'vsi_sentiment_level', 'fx_volatility'], ['regime_confidence_pct', 'vsi_sentiment_score', 'sbv_omo_injection_billion_vnd', 'foreign_net_flow_billion_vnd', 'systemic_stress_index', 'interbank_rate_pct']) ||
      !fields(value.alpha, [], ['active_alphas_count', 'candidate_alphas_count', 'total_alpha_universe', 'mean_ic', 'ic_tstat']) ||
      !fields((value.alpha as Record<string, unknown>).top_active_signal, ['alpha_id', 'name', 'category'], ['ic', 'ir', 'turnover_pct']) ||
      !fields(value.screener, [], ['universe_size', 'qualified_count', 'watch_count']) ||
      !fields((value.screener as Record<string, unknown>).target_ticker_profile, ['ticker', 'status'], ['pe', 'pb', 'roe_pct', 'piotroski_f', 'altman_z']) ||
      !fields(value.risk_tca, ['top_risk_contributor', 'fastest_gateway'], ['portfolio_total_risk_annualized_pct', 'factor_risk_pct', 'specific_risk_pct', 'cvar_95_pct', 'cvar_99_pct', 'avg_is_bps', 'avg_slippage_bps', 'active_broker_routes']) ||
      !fields(value.pipeline, ['in_process_engine_status', 'last_job_status', 'audit_verification_status']) ||
      typeof (value.pipeline as Record<string, unknown>).kill_switch_active !== 'boolean' ||
      typeof (value.pipeline as Record<string, unknown>).sod_boundary_isolated !== 'boolean') throw new Error(INVALID);
  return value as unknown as CopilotSystemSynthesisResponse;
}

function validRecommendation(value: unknown): value is RecommendationActionItem {
  return fields(value, ['id', 'title', 'description']) && object(value) &&
    member(value.category, ['REBALANCE', 'RISK_MITIGATION', 'ALPHA_HARVEST', 'HEDGE', 'EXECUTION_TIMING']) &&
    member(value.impact_level, ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']) &&
    member(value.action_type, ['DISPATCH_REBALANCE', 'TRIGGER_PIPELINE', 'ADJUST_POSITION', 'EXECUTE_ORDER', 'RUN_BACKTEST']) &&
    finite(value.confidence_score) && value.confidence_score >= 0 && value.confidence_score <= 1 &&
    (value.target_symbol === undefined || (text(value.target_symbol) && /^[A-Z0-9]{3,10}$/.test(value.target_symbol))) &&
    timestamp(value.created_at) && object(value.payload) && bounded(value);
}

function recommendationsResponse(value: unknown): RecommendationActionItem[] {
  success(value);
  if (!Number.isSafeInteger(value.total_recommendations) || (value.total_recommendations as number) < 0 ||
      !Array.isArray(value.recommendations) || value.recommendations.length > 50 ||
      (value.total_recommendations as number) < value.recommendations.length ||
      !value.recommendations.every(validRecommendation) ||
      new Set(value.recommendations.map(item => item.id)).size !== value.recommendations.length) throw new Error(INVALID);
  return value.recommendations;
}

function askResponse(value: unknown): CopilotAskResponse {
  success(value);
  if (!fields(value, ['query', 'intent', 'focus_ticker', 'response_vi', 'response_en'], ['confidence']) ||
      (value.confidence as number) < 0 || (value.confidence as number) > 1 || !object(value.metrics) ||
      !Array.isArray(value.suggested_actions) || value.suggested_actions.length > 20 || !value.suggested_actions.every(text) ||
      (value.executed_tools !== undefined && (!Array.isArray(value.executed_tools) || value.executed_tools.length > 20 ||
        !value.executed_tools.every(tool => fields(tool, ['tool_name']) && object(tool) &&
          (tool.status === undefined || member(tool.status, ['success', 'pending', 'error'])) &&
          (tool.parameters === undefined || object(tool.parameters)) &&
          (tool.target === undefined || tool.target === null || text(tool.target)) &&
          (tool.action_type === undefined || text(tool.action_type)) &&
          (tool.result === undefined || tool.result === null || object(tool.result)) &&
          (tool.timestamp === undefined || timestamp(tool.timestamp)))))) throw new Error(INVALID);
  return value as unknown as CopilotAskResponse;
}

// ponytail: client methods lack AbortSignal; bound waiting, discard late results. Add transport cancellation when client accepts signals.
function request<T>(start: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error: unknown, result?: T) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(result as T);
    };
    const abort = () => finish(new Error(FAILED));
    const timer = setTimeout(() => finish(new Error(FAILED)), TIMEOUT_MS);
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort', abort, { once: true });
    Promise.resolve().then(() => { if (!settled) return start(); }).then(result => { if (!settled) finish(null, result as T); }, error => finish(error));
  });
}

const errorMessage = (error: unknown) => error instanceof Error && [INVALID, UNAVAILABLE].includes(error.message) ? error.message : FAILED;

interface CopilotState {
  synthesis: CopilotSystemSynthesisResponse | undefined;
  isSynthesisLoading: boolean;
  isUnavailable: boolean;
  refetchSynthesis: () => void;
  recommendations: RecommendationActionItem[];
  chatHistory: ChatMessage[];
  isAsking: boolean;
  sendQuery: (query: string) => void;
  clearChat: () => void;
  dispatchAction: (item: RecommendationActionItem) => void;
  executingActionId: string | null;
  streamEvents: CopilotStreamEvent[];
  isSseConnected: boolean;
  synthesisError?: string | null;
  isRecommendationsLoading?: boolean;
  recommendationsError?: string | null;
  chatError?: string | null;
  actionError?: string | null;
  streamError?: string | null;
}

export function useCopilot(enabled: boolean): CopilotState {
  const ticker = useUiStore(state => state.selectedTicker);
  const activeModule = useUiStore(state => state.activeModule);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [streamEvents, setStreamEvents] = useState<CopilotStreamEvent[]>([]);
  const [isSseConnected, setSseConnected] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isAsking, setAsking] = useState(false);
  const [executingActionId, setExecutingActionId] = useState<string | null>(null);
  const generation = useRef(0);
  const chatGeneration = useRef(0);
  const asking = useRef(false);
  const executing = useRef(false);
  const sequence = useRef(0);
  const live = useRef(enabled);
  live.current = enabled;

  const queryScope = useRef({ enabled, ticker, generation: 0 });
  if (queryScope.current.enabled !== enabled || queryScope.current.ticker !== ticker) queryScope.current = { enabled, ticker, generation: queryScope.current.generation + 1 };
  const queryRequest = async <T,>(start: () => Promise<T>, signal: AbortSignal) => {
    const current = queryScope.current.generation;
    const result = await request(start, signal);
    if (!live.current || current !== queryScope.current.generation) throw new Error(FAILED);
    return result;
  };
  const options = { enabled, retry: false as const, refetchInterval: false as const, refetchOnWindowFocus: false as const, refetchOnReconnect: false as const };
  const synthesisQuery = useQuery({ ...options, queryKey: ['copilot', 'system-synthesis', ticker], queryFn: async ({ signal }) => synthesisResponse(await queryRequest(() => apiClient.getCopilotSystemSynthesis(ticker), signal)) });
  const recommendationsQuery = useQuery({ ...options, queryKey: ['copilot', 'actionable-recommendations'], queryFn: async ({ signal }) => recommendationsResponse(await queryRequest(() => apiClient.getCopilotRecommendations(10), signal)) });
  const ask = useMutation({ retry: false, mutationFn: async (query: string) => askResponse(await request(() => apiClient.askCopilot({ query, context_ticker: ticker, active_module: activeModule }))) });
  const action = useMutation({ retry: false, mutationFn: async (item: RecommendationActionItem) => {
    // ponytail: only RUN_BACKTEST has a real execute-tool mapping. Never invent trade/rebalance execution.
    if (item.action_type !== 'RUN_BACKTEST') throw new Error(UNAVAILABLE);
    const result = await request(() => apiClient.executeCopilotTool({ tool_name: 'trigger_backtest', parameters: item.payload }));
    success(result);
    if (!fields(result, ['message', 'action_type']) || result.tool_name !== 'trigger_backtest' || !object(result.execution_result)) throw new Error(INVALID);
    return result;
  } });

  useEffect(() => {
    const current = ++generation.current;
    setSseConnected(false);
    setStreamError(null);
    setStreamEvents([]);
    if (!enabled) return;
    let source: EventSource | undefined;
    let stopped = false;
    const valid = () => !stopped && live.current && generation.current === current;
    const stop = () => {
      stopped = true;
      if (source) { source.onopen = null; source.onmessage = null; source.onerror = null; source.close(); }
    };
    try {
      source = new EventSource(`${API_BASE}/sse/v1/copilot/stream`);
      source.onopen = () => { if (valid()) setSseConnected(true); };
      source.onmessage = event => {
        if (!valid()) return;
        try {
          if (typeof event.data !== 'string' || event.data.length > 65536) throw new Error(INVALID);
          const value: unknown = JSON.parse(event.data);
          if (!fields(value, ['event_type', 'title']) || !object(value) || !timestamp(value.timestamp) ||
              !member(value.severity, ['INFO', 'SUCCESS', 'WARNING', 'ERROR']) || !object(value.payload) || !bounded(value)) throw new Error(INVALID);
          setStreamEvents(events => [...events.slice(-99), value as unknown as CopilotStreamEvent]);
        } catch {
          stop(); setSseConnected(false); setStreamError(INVALID);
        }
      };
      source.onerror = () => { if (valid()) { stop(); setSseConnected(false); setStreamError(FAILED); } };
    } catch { stop(); setStreamError(UNAVAILABLE); }
    return () => {
      ++generation.current; ++chatGeneration.current;
      asking.current = false; executing.current = false;
      setAsking(false); setExecutingActionId(null);
      stop();
    };
  }, [enabled]);

  const append = (message: Omit<ChatMessage, 'id' | 'timestamp'>) => setChatHistory(history => [...history.slice(-99), { ...message, id: `copilot-${++sequence.current}`, timestamp: new Date().toISOString() }]);
  const sendQuery = (query: string) => {
    if (!live.current || asking.current) return;
    if (!text(query) || !query.trim() || query.trim().length > 4000) { setChatError('Enter a query of 1–4000 characters.'); return; }
    const current = generation.current;
    const chat = chatGeneration.current;
    asking.current = true; setAsking(true); setChatError(null);
    append({ sender: 'user', textVi: query.trim(), textEn: query.trim() });
    ask.mutate(query.trim(), {
      onSuccess: result => {
        if (!live.current || generation.current !== current || chatGeneration.current !== chat) return;
        append({ sender: 'assistant', textVi: result.response_vi, textEn: result.response_en, executedTools: result.executed_tools, suggestedActions: result.suggested_actions });
      },
      onError: error => { if (live.current && generation.current === current && chatGeneration.current === chat) setChatError(errorMessage(error)); },
      onSettled: () => { if (generation.current === current && chatGeneration.current === chat) { asking.current = false; setAsking(false); } },
    });
  };
  const clearChat = () => {
    ++chatGeneration.current; asking.current = false; setAsking(false); ask.reset();
    setChatHistory([]); setChatError(null);
  };
  const dispatchAction = (item: RecommendationActionItem) => {
    if (!live.current || executing.current) return;
    if (!validRecommendation(item) || !recommendationsQuery.data?.some(candidate => candidate === item)) { setActionError(INVALID); return; }
    const current = generation.current;
    executing.current = true; setExecutingActionId(item.id); setActionError(null);
    action.mutate(item, {
      onSuccess: result => { if (live.current && generation.current === current) append({ sender: 'assistant', textVi: result.message, textEn: result.message }); },
      onError: error => { if (live.current && generation.current === current) setActionError(errorMessage(error)); },
      onSettled: () => { if (generation.current === current) { executing.current = false; setExecutingActionId(null); } },
    });
  };
  return {
    synthesis: synthesisQuery.isError ? undefined : synthesisQuery.data,
    isSynthesisLoading: enabled && synthesisQuery.isFetching,
    synthesisError: synthesisQuery.error ? errorMessage(synthesisQuery.error) : null,
    isUnavailable: synthesisQuery.error instanceof Error && synthesisQuery.error.message === UNAVAILABLE,
    refetchSynthesis: () => { if (live.current) { void synthesisQuery.refetch(); void recommendationsQuery.refetch(); } },
    recommendations: recommendationsQuery.isError ? [] : recommendationsQuery.data ?? [],
    isRecommendationsLoading: enabled && recommendationsQuery.isFetching,
    recommendationsError: recommendationsQuery.error ? errorMessage(recommendationsQuery.error) : null,
    chatHistory, isAsking: enabled && isAsking, sendQuery, clearChat, chatError,
    dispatchAction, executingActionId: enabled ? executingActionId : null, actionError,
    streamEvents: enabled ? streamEvents : [], isSseConnected: enabled && isSseConnected, streamError,
  };
}
