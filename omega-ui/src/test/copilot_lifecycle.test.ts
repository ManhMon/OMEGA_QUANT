import React, { act, StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { useCopilot } from '../hooks/useCopilot';
import { OmniQuantCopilotDrawer } from '../modules/copilot/OmniQuantCopilotDrawer';
import { useUiStore } from '../store/uiStore';

vi.mock('../api/client', () => ({ API_BASE: '', apiClient: {
  getCopilotSystemSynthesis: vi.fn(), getCopilotRecommendations: vi.fn(),
  askCopilot: vi.fn(), executeCopilotTool: vi.fn(),
} }));

const time = '2026-10-11T08:30:00Z';
const synthesis = {
  status: 'success', timestamp: time, focus_symbol: 'FPT', executive_quant_score: 0,
  holistic_verdict: 'NEUTRAL', verdict_reasoning_vi: 'Chờ dữ liệu', verdict_reasoning_en: 'Wait for data',
  macro: { regime: 'NEUTRAL', regime_confidence_pct: 0, vsi_sentiment_score: 0, vsi_sentiment_level: 'NEUTRAL', sbv_omo_injection_billion_vnd: 0, foreign_net_flow_billion_vnd: 0, systemic_stress_index: 0, fx_volatility: 'LOW', interbank_rate_pct: 0 },
  alpha: { active_alphas_count: 0, candidate_alphas_count: 0, total_alpha_universe: 0, mean_ic: 0, ic_tstat: 0, top_active_signal: { alpha_id: 'A', name: 'Signal', category: 'TEST', ic: 0, ir: 0, turnover_pct: 0 } },
  screener: { universe_size: 0, qualified_count: 0, watch_count: 0, target_ticker_profile: { ticker: 'FPT', pe: 0, pb: 0, roe_pct: 0, piotroski_f: 0, altman_z: 0, status: 'WAIT' } },
  risk_tca: { portfolio_total_risk_annualized_pct: 0, factor_risk_pct: 0, specific_risk_pct: 0, cvar_95_pct: 0, cvar_99_pct: 0, top_risk_contributor: 'FPT', avg_is_bps: 0, avg_slippage_bps: 0, active_broker_routes: 0, fastest_gateway: 'NONE' },
  pipeline: { in_process_engine_status: 'WAIT', last_job_status: 'WAIT', kill_switch_active: false, sod_boundary_isolated: true, audit_verification_status: 'UNVERIFIED' },
};
const recommendation = { id: 'R1', category: 'ALPHA_HARVEST' as const, title: 'Backtest', description: 'Run research', impact_level: 'LOW' as const, confidence_score: 0, action_type: 'RUN_BACKTEST' as const, payload: { strategy_id: 'A' }, created_at: time };
const answer = { status: 'success', timestamp: time, query: 'Question', intent: 'research', focus_ticker: 'FPT', response_vi: 'Trả lời', response_en: 'Answer', metrics: {}, suggested_actions: [], confidence: 0 };
const event = { event_type: 'HEARTBEAT', title: 'Alive', severity: 'INFO', timestamp: time, payload: {} };

class Source {
  static all: Source[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { Source.all.push(this); }
}
let root: Root;
let container: HTMLDivElement;
let client: QueryClient;
let state: ReturnType<typeof useCopilot>;
let enabled: boolean;
let initialStore: ReturnType<typeof useUiStore.getState>;
let descriptors: PropertyDescriptorMap;
const flush = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(1); }); };
function Probe() { state = useCopilot(enabled); return null; }
async function renderHook(on = true, strict = false) {
  enabled = on;
  const tree = React.createElement(QueryClientProvider, { client }, React.createElement(Probe));
  await act(async () => root.render(strict ? React.createElement(StrictMode, null, tree) : tree));
  await flush();
}
async function renderDrawer(on = true) {
  await act(async () => root.render(React.createElement(QueryClientProvider, { client }, React.createElement(OmniQuantCopilotDrawer, { isOpen: on, onClose: vi.fn() }))));
  await flush();
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('EventSource', Source);
  Source.all = [];
  initialStore = useUiStore.getState();
  useUiStore.setState({ locale: 'en', selectedTicker: 'FPT', activeModule: 'macro_cockpit' });
  descriptors = Object.getOwnPropertyDescriptors(HTMLDialogElement.prototype);
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value: function () { this.open = true; this.querySelector('[autofocus]')?.focus(); } },
    close: { configurable: true, value: function () { this.open = false; } },
  });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  vi.mocked(apiClient.getCopilotSystemSynthesis).mockResolvedValue(synthesis);
  vi.mocked(apiClient.getCopilotRecommendations).mockResolvedValue({ status: 'success', timestamp: time, total_recommendations: 1, recommendations: [recommendation] });
  vi.mocked(apiClient.askCopilot).mockResolvedValue(answer);
  vi.mocked(apiClient.executeCopilotTool).mockResolvedValue({ status: 'success', timestamp: time, tool_name: 'trigger_backtest', action_type: 'BACKEND_TASK', execution_result: {}, message: 'Research started' });
});
afterEach(() => {
  act(() => root.unmount()); client.clear();
  document.body.replaceChildren(); useUiStore.setState(initialStore, true);
  for (const key of ['showModal', 'close']) {
    if (descriptors[key]) Object.defineProperty(HTMLDialogElement.prototype, key, descriptors[key]);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, key);
  }
  vi.restoreAllMocks(); vi.resetAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

describe('Copilot query lifecycle', () => {
  it('does no work while disabled; fetches once without polling or automatic retry', async () => {
    await renderHook(false);
    expect(apiClient.getCopilotSystemSynthesis).not.toHaveBeenCalled(); expect(Source.all).toHaveLength(0);
    await renderHook(); expect(state.synthesis?.executive_quant_score).toBe(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(apiClient.getCopilotSystemSynthesis).toHaveBeenCalledTimes(1);
    expect(apiClient.getCopilotRecommendations).toHaveBeenCalledTimes(1);
    act(() => state.refetchSynthesis()); await flush();
    expect(apiClient.getCopilotSystemSynthesis).toHaveBeenCalledTimes(2);
  });
  it('separates loading, transport failure and unavailable; never exposes stale success on error', async () => {
    const pending = deferred<typeof synthesis>();
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockReturnValueOnce(pending.promise);
    await renderHook(); expect(state.isSynthesisLoading).toBe(true); expect(state.isUnavailable).toBe(false);
    await act(async () => pending.resolve(synthesis)); await flush(); expect(state.synthesis).toBeDefined();
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockRejectedValueOnce(new Error('https://user:secret@host'));
    act(() => state.refetchSynthesis()); await flush(); expect(state.synthesis).toBeUndefined();
    expect(state.synthesisError).toBe('Copilot request failed. Retry manually.');
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockResolvedValueOnce({ status: 'unavailable' } as never);
    act(() => state.refetchSynthesis()); await flush(); expect(state.isUnavailable).toBe(true);
  });
  it.each([null, [], {}, { ...synthesis, status: 'error' }, { ...synthesis, macro: null }, { ...synthesis, timestamp: 'bad' }, ...[NaN, Infinity, -Infinity, -1, 101, 1e13, '0'].map(executive_quant_score => ({ ...synthesis, executive_quant_score }))])('rejects malformed synthesis %#', async value => {
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockResolvedValueOnce(value as never);
    await renderHook(); expect(state.synthesis).toBeUndefined(); expect(state.synthesisError).toBeTruthy();
  });
  it.each([null, [], { status: 'success', timestamp: time, total_recommendations: 1, recommendations: [null] }, { status: 'success', timestamp: time, total_recommendations: 2, recommendations: [recommendation, recommendation] }, { status: 'success', timestamp: time, total_recommendations: 1, recommendations: [{ ...recommendation, confidence_score: NaN }] }])('rejects malformed recommendation lists %#', async value => {
    vi.mocked(apiClient.getCopilotRecommendations).mockResolvedValueOnce(value as never);
    await renderHook(); expect(state.recommendations).toEqual([]); expect(state.recommendationsError).toBeTruthy();
  });
  it('times out a hung query without retry', async () => {
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockReturnValueOnce(new Promise(() => {}));
    await renderHook(); await act(async () => { await vi.advanceTimersByTimeAsync(15001); });
    expect(state.isSynthesisLoading).toBe(false); expect(state.synthesisError).toBeTruthy(); expect(apiClient.getCopilotSystemSynthesis).toHaveBeenCalledTimes(1);
  });
});

describe('Copilot SSE lifecycle', () => {
  it('connects exact route, bounds events, closes on disable; ignores stale callbacks after reopen', async () => {
    await renderHook(); const source = Source.all[0]; expect(source.url).toBe('/sse/v1/copilot/stream');
    act(() => source.onopen!()); expect(state.isSseConnected).toBe(true);
    const late = source.onmessage!;
    act(() => { for (let i = 0; i < 120; i++) source.onmessage!({ data: JSON.stringify({ ...event, title: String(i) }) }); });
    expect(state.streamEvents).toHaveLength(100); expect(state.streamEvents[0].title).toBe('20');
    await renderHook(false); expect(source.close).toHaveBeenCalled(); expect(state.isSseConnected).toBe(false);
    await renderHook(); act(() => late({ data: JSON.stringify(event) })); expect(state.streamEvents).toEqual([]);
  });
  it.each(['{', 'null', '[]', JSON.stringify({ ...event, severity: 'BAD' }), JSON.stringify({ ...event, timestamp: 'bad' }), JSON.stringify({ ...event, title: {} }), 'x'.repeat(65537)])('fails closed on malformed SSE %#', async data => {
    await renderHook(); const source = Source.all[0]; const late = source.onopen!;
    act(() => source.onmessage!({ data })); expect(source.close).toHaveBeenCalled(); expect(state.streamError).toBeTruthy();
    act(() => late()); expect(state.isSseConnected).toBe(false);
  });
  it('stops native reconnect after error; constructor failure remains explicit', async () => {
    await renderHook(); act(() => Source.all[0].onerror!());
    expect(Source.all[0].close).toHaveBeenCalled(); expect(state.streamError).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); }); expect(Source.all).toHaveLength(1);
    await renderHook(false); vi.stubGlobal('EventSource', class { constructor() { throw new Error('unavailable'); } });
    await renderHook(); expect(state.streamError).toBe('Copilot integration unavailable.');
  });
  it('cleans every StrictMode source on unmount', async () => {
    await renderHook(true, true); expect(Source.all.length).toBeGreaterThanOrEqual(2);
    await act(async () => root.render(null)); expect(Source.all.every(source => source.close.mock.calls.length > 0)).toBe(true);
  });
});

describe('Copilot mutation lifecycle', () => {
  it('submits trimmed context once; ignores duplicate send; completes chat', async () => {
    const pending = deferred<typeof answer>(); vi.mocked(apiClient.askCopilot).mockReturnValueOnce(pending.promise);
    await renderHook(); act(() => { state.sendQuery(' Question '); state.sendQuery('Duplicate'); }); await flush();
    expect(apiClient.askCopilot).toHaveBeenCalledExactlyOnceWith({ query: 'Question', context_ticker: 'FPT', active_module: 'macro_cockpit' }); expect(state.isAsking).toBe(true);
    await act(async () => pending.resolve(answer)); await flush();
    expect(state.isAsking).toBe(false); expect(state.chatHistory.map(message => message.textEn)).toEqual(['Question', 'Answer']);
  });
  it.each(['', ' ', 'x'.repeat(4001), null, [], NaN])('rejects invalid prompt %#', async value => {
    await renderHook(); act(() => state.sendQuery(value as string)); await flush();
    expect(apiClient.askCopilot).not.toHaveBeenCalled(); expect(state.chatError).toBeTruthy();
  });
  it.each([null, { ...answer, response_en: [] }, { ...answer, suggested_actions: {} }, { ...answer, executed_tools: [null] }, { ...answer, confidence: Infinity }])('rejects malformed ask result %#', async value => {
    vi.mocked(apiClient.askCopilot).mockResolvedValueOnce(value as never);
    await renderHook(); act(() => state.sendQuery('Question')); await flush();
    expect(state.chatHistory).toHaveLength(1); expect(state.chatError).toBeTruthy(); expect(state.isAsking).toBe(false);
  });
  it('clear isolates an old response from a new pending ask', async () => {
    const first = deferred<typeof answer>(); const second = deferred<typeof answer>();
    vi.mocked(apiClient.askCopilot).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    await renderHook(); act(() => state.sendQuery('First')); await flush();
    act(() => { state.clearChat(); state.sendQuery('Second'); }); await flush();
    await act(async () => first.resolve(answer)); await flush(); expect(state.chatHistory.map(message => message.textEn)).toEqual(['Second']); expect(state.isAsking).toBe(true);
    await act(async () => second.resolve(answer)); await flush(); expect(state.isAsking).toBe(false); expect(state.chatHistory).toHaveLength(2);
  });
  it('close/reopen discards old ask errors and unlocks state', async () => {
    const pending = deferred<typeof answer>(); vi.mocked(apiClient.askCopilot).mockReturnValueOnce(pending.promise);
    await renderHook(); act(() => state.sendQuery('Question')); await flush(); await renderHook(false); await renderHook();
    await act(async () => pending.reject(new Error('secret'))); await flush(); expect(state.chatError).toBeNull(); expect(state.isAsking).toBe(false);
  });
  it('timeouts ask and action without retry; validates action membership and unsupported mappings', async () => {
    await renderHook(); act(() => state.dispatchAction({ ...recommendation })); expect(state.actionError).toBeTruthy();
    const item = state.recommendations[0]; vi.mocked(apiClient.executeCopilotTool).mockReturnValueOnce(new Promise(() => {}));
    act(() => { state.dispatchAction(item); state.dispatchAction(item); }); await flush(); expect(apiClient.executeCopilotTool).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(15001); }); expect(state.executingActionId).toBeNull(); expect(state.actionError).toBeTruthy();
    vi.mocked(apiClient.askCopilot).mockReturnValueOnce(new Promise(() => {})); act(() => state.sendQuery('Question')); await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(15001); }); expect(state.isAsking).toBe(false); expect(state.chatError).toBeTruthy();
  });
  it('late timeout response cannot append; disable aborts stale query waiter', async () => {
    const pending = deferred<typeof answer>(); vi.mocked(apiClient.askCopilot).mockReturnValueOnce(pending.promise);
    await renderHook(); act(() => state.sendQuery('Question')); await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(15001); });
    await act(async () => pending.resolve(answer)); await flush(); expect(state.chatHistory).toHaveLength(1);
    const query = deferred<typeof synthesis>(); vi.mocked(apiClient.getCopilotSystemSynthesis).mockReturnValueOnce(query.promise);
    act(() => useUiStore.setState({ selectedTicker: 'HPG' })); await flush();
    await renderHook(false); await act(async () => query.resolve(synthesis)); await flush();
    expect(client.getQueryData(['copilot', 'system-synthesis', 'HPG'])).toBeUndefined();
  });
  it('unsupported recommendation never dispatches execution; action close race discards response', async () => {
    vi.mocked(apiClient.getCopilotRecommendations).mockResolvedValueOnce({ status: 'success', timestamp: time, total_recommendations: 1, recommendations: [{ ...recommendation, action_type: 'EXECUTE_ORDER' }] });
    await renderHook(); act(() => state.dispatchAction(state.recommendations[0])); await flush();
    expect(apiClient.executeCopilotTool).not.toHaveBeenCalled(); expect(state.actionError).toBe('Copilot integration unavailable.');
    vi.mocked(apiClient.getCopilotRecommendations).mockResolvedValueOnce({ status: 'success', timestamp: time, total_recommendations: 1, recommendations: [recommendation] });
    act(() => state.refetchSynthesis()); await flush();
    const pending = deferred<Awaited<ReturnType<typeof apiClient.executeCopilotTool>>>(); vi.mocked(apiClient.executeCopilotTool).mockReturnValueOnce(pending.promise);
    act(() => state.dispatchAction(state.recommendations[0])); await flush(); await renderHook(false); await renderHook();
    await act(async () => pending.resolve({ status: 'success', timestamp: time, tool_name: 'trigger_backtest', action_type: 'BACKEND_TASK', execution_result: {}, message: 'Late' })); await flush();
    expect(state.chatHistory).toEqual([]); expect(state.executingActionId).toBeNull();
  });
  it('dispatches real backtest once; rejects malformed execution response', async () => {
    await renderHook(); act(() => state.dispatchAction(state.recommendations[0])); await flush();
    expect(apiClient.executeCopilotTool).toHaveBeenCalledExactlyOnceWith({ tool_name: 'trigger_backtest', parameters: recommendation.payload });
    expect(state.chatHistory[0].textEn).toBe('Research started');
    vi.mocked(apiClient.executeCopilotTool).mockResolvedValueOnce({ status: 'success', timestamp: time } as never);
    act(() => state.dispatchAction(state.recommendations[0])); await flush(); expect(state.actionError).toBeTruthy();
  });
});

describe('Copilot drawer integration', () => {
  it('does not fabricate synthesis while loading or failed; distinguishes recommendation failure', async () => {
    vi.mocked(apiClient.getCopilotSystemSynthesis).mockReturnValueOnce(new Promise(() => {}));
    vi.mocked(apiClient.getCopilotRecommendations).mockRejectedValueOnce(new Error('offline'));
    await renderDrawer(); expect(container.textContent).toContain('Loading system synthesis'); expect(container.textContent).not.toContain('ACCUMULATE_BULLISH'); expect(container.textContent).not.toContain('88.5');
    const tab = [...container.querySelectorAll('button')].find(button => button.textContent?.includes('Actionable'));
    expect(tab).toBeDefined(); act(() => tab!.click()); expect(container.querySelector('[role="alert"]')?.textContent).toContain('failed');
  });
  it('preserves zero values and native focus during state transitions; wraps Tab and restores opener', async () => {
    const pending = deferred<typeof synthesis>(); vi.mocked(apiClient.getCopilotSystemSynthesis).mockReturnValueOnce(pending.promise);
    const opener = document.createElement('button'); document.body.appendChild(opener); opener.focus(); await renderDrawer();
    const focused = document.activeElement; await act(async () => pending.resolve(synthesis)); await flush(); expect(document.activeElement).toBe(focused);
    expect(container.textContent).toContain('0/100'); expect(container.textContent).not.toContain('88.5');
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList);
    const dialog = container.querySelector('dialog')!; const controls = [...dialog.querySelectorAll<HTMLButtonElement>('button')].filter(button => !button.disabled);
    controls.at(-1)!.focus(); const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }); act(() => controls.at(-1)!.dispatchEvent(tab)); expect(tab.defaultPrevented).toBe(true); expect(document.activeElement).toBe(controls[0]);
    const back = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }); act(() => controls[0].dispatchEvent(back)); expect(document.activeElement).toBe(controls.at(-1));
    await renderDrawer(false); expect(document.activeElement).toBe(opener);
  });
  it('uses AA contrast for body/action text and visible keyboard focus', async () => {
    const luminance = (hex: string) => { const rgb = hex.match(/\w\w/g)!.map(value => parseInt(value, 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4); return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722; };
    const contrast = (a: string, b: string) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
    expect(contrast('ffffff', '047857')).toBeGreaterThanOrEqual(4.5); expect(contrast('a1a1aa', '18181b')).toBeGreaterThanOrEqual(4.5);
    await renderDrawer(); expect(container.innerHTML).not.toContain('text-zinc-500'); expect(container.querySelector('dialog')?.className).toContain('focus-visible:outline');
  });
});
