import { act } from 'react';
import { ExecutionBlotterView, validateExecutionData, useExecutionData } from '../modules/execution_blotter/ExecutionBlotterView';
import { PaperDaemonPanel, requestExecutionData, validateDaemonStatus } from '../modules/execution_blotter/PaperDaemonPanel';
import { createRoot, type Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../App';
import { useUiStore } from '../store/uiStore';
import type { ModuleType } from '../layout/SideDock';
import { useTranslation } from '../i18n';
import { useLLMConfig } from '../hooks/useLLMConfig';
import * as useLLMConfigModule from '../hooks/useLLMConfig';
import { usePreTradeImpact } from '../hooks/useBarraRiskTca';
import { useMarketOhlcv, validateCandles, validateOrderbook, aggregateCandles } from '../hooks/useMarketData';
import { LandingDatabaseHub, validateMacroData } from '../modules/macro_cockpit/LandingDatabaseHub';
import * as useMarketDataModule from '../hooks/useMarketData';
import { ChartStationView } from '../modules/chart_station/ChartStationView';
import { useCopilot } from '../hooks/useCopilot';
import * as useCopilotModule from '../hooks/useCopilot';
import { unavailableMessage } from '../hooks/useUnavailableQuery';
import { en } from '../i18n/en';
import { vi as vietnamese } from '../i18n/vi';
import { LightweightChartContainer } from '../modules/chart_station/LightweightChartContainer';
import { OrderbookDepth } from '../modules/chart_station/OrderbookDepth';
import { OmniQuantCopilotDrawer } from '../modules/copilot/OmniQuantCopilotDrawer';
import { LLMConfigModal, containModalFocus } from '../modules/copilot/LLMConfigModal';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { MultiProfileLLMConfigPayload } from '../api/client';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const initialState = useUiStore.getState();
const originalDialogDescriptors = Object.getOwnPropertyDescriptors(HTMLDialogElement.prototype);
const originalFocus = HTMLElement.prototype.focus;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
let storageSnapshot: [string, string][];
const closed = vi.fn();

const mockConfigPayload: MultiProfileLLMConfigPayload = {
  global_profile: {
    provider: 'openai',
    model: 'gpt-4o',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  alpha_quant: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.1,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  news_sentiment: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  macro_micro: {
    provider: 'openai',
    model: 'gpt-4o',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
};

const mockCopilotAvailable = {
  synthesis: {
    holistic_verdict: 'ACCUMULATE_BULLISH',
    verdict_reasoning_en: 'Bullish regime verified across multi-factor models',
    verdict_reasoning_vi: 'Nhận định tích cực dựa trên mô hình đa nhân tố',
    executive_quant_score: 92.5,
    focus_symbol: 'FPT',
    screener: {
      target_ticker_profile: {
        piotroski_f: 8,
        altman_z: 3.42,
        roe_pct: 26.5,
      },
    },
    risk_tca: {
      cvar_99_pct: 2.68,
      factor_risk_pct: 11.25,
      specific_risk_pct: 3.57,
      fastest_gateway: 'VNDIRECT_DMA',
    },
  } as any,
  isSynthesisLoading: false,
  isUnavailable: false,
  refetchSynthesis: vi.fn(),
  recommendations: [],
  chatHistory: [],
  isAsking: false,
  sendQuery: vi.fn(),
  clearChat: vi.fn(),
  dispatchAction: vi.fn(),
  executingActionId: null,
  streamEvents: [],
  isSseConnected: true,
};

beforeEach(() => {
  storageSnapshot = Object.entries(window.localStorage);
  vi.useFakeTimers();
  HTMLElement.prototype.focus = function (this: HTMLElement, ...args: any[]) {
    const dialog = this.closest('dialog');
    if (dialog && !dialog.open) {
      (dialog as any)._pendingAutoFocus = this;
      return;
    }
    return originalFocus.apply(this, args as any);
  };
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      writable: true,
      value: function (this: HTMLDialogElement) {
        this.open = true;
        const pending = (this as any)._pendingAutoFocus;
        delete (this as any)._pendingAutoFocus;
        const autoFocusTarget = pending || Array.from(this.querySelectorAll<HTMLElement>('*')).find(
          (el) => el.hasAttribute('autofocus') || (el as any).autofocus === true
        ) || this.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (autoFocusTarget) {
          autoFocusTarget.focus();
        } else {
          this.focus();
        }
        const onKeyDown = (e: KeyboardEvent) => {
          if (e.key === 'Escape' && this.open) {
            const cancelEvt = new Event('cancel', { cancelable: true });
            this.dispatchEvent(cancelEvt);
            if (!cancelEvt.defaultPrevented) {
              this.close();
            }
          }
        };
        if ((this as any)._cleanupKeyDown) {
          (this as any)._cleanupKeyDown();
        }
        this.addEventListener('keydown', onKeyDown);
        (this as any)._cleanupKeyDown = () => this.removeEventListener('keydown', onKeyDown);
      },
    },
    close: {
      configurable: true,
      writable: true,
      value: function (this: HTMLDialogElement) {
        this.open = false;
        if (typeof (this as any)._cleanupKeyDown === 'function') {
          (this as any)._cleanupKeyDown();
          delete (this as any)._cleanupKeyDown;
        }
        this.dispatchEvent(new Event('close'));
      },
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Injected offline failure')));
  vi.stubGlobal('EventSource', class {
    close = closed;
    addEventListener() {}
    removeEventListener() {}
  });
  useUiStore.setState({ ...initialState, locale: 'en', activeModule: 'pipeline_console', tasks: {}, toasts: [] }, true);
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.clear();
  }
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
  container.remove();
  document.body.innerHTML = '';
  useUiStore.setState(initialState, true);
  window.localStorage.clear();
  for (const [key, value] of storageSnapshot) window.localStorage.setItem(key, value);
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  HTMLElement.prototype.focus = originalFocus;
  for (const key of ['showModal', 'close']) {
    if (originalDialogDescriptors[key]) {
      Object.defineProperty(HTMLDialogElement.prototype, key, originalDialogDescriptors[key]);
    } else {
      Reflect.deleteProperty(HTMLDialogElement.prototype, key);
    }
  }
});
const settle = async (ms = 50) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

const executionCutoff = '2026-10-09T08:30:00Z';
const executionPayloads = (cutoff = executionCutoff): any[] => {
  const envelope = { status: 'success', timestamp: cutoff, effective_cutoff: cutoff, provenance: 'RECORDED', price_unit: 'VND_FULL' };
  const order = { orderId: 'o1', parentOrderId: null, timestamp: '2026-10-05T03:00:00Z', availableAt: '2026-10-05T03:00:00Z',
    symbol: 'VCB', side: 'BUY', orderType: 'LO', qty: 100, price: 10100, filledQty: 100, status: 'FILLED',
    broker: 'PAPER', venue: 'HOSE', algoType: 'DIRECT', sequence: null };
  return [{ ...envelope, orders: [order], count: 1 }, { ...envelope, parents: [], standalone: [order] },
    { ...envelope, benchmark: 'ARRIVAL_PRICE', sign_convention: 'POSITIVE_IS_COST', fees_included: true,
      points: [{ order_id: 'o1', venue: 'HOSE', side: 'BUY', quantity: 100, arrival_price: 10000, executed_price: 10100, fee_vnd: 1000, slippage_bps: 110 }],
      venues: [{ venue: 'HOSE', count: 1, arrival_notional_vnd: 1000000, average_slippage_bps: 110 }], excluded_missing_benchmark_or_fee: 0 },
    { ...envelope, calendar_timezone: 'Asia/Ho_Chi_Minh', forecast_policy: 'T_PLUS_2_TRADING_DAYS_15_30_ICT_NOT_CONFIRMATION',
      settlements: [{ order_id: 'o1', broker: 'PAPER', symbol: 'VCB', side: 'BUY', trade_at: order.timestamp,
        expected_settlement_at: '2026-10-07T08:30:00Z', broker_effective_at: null, settlement_effective_at: null,
        confirmation_available_at: null, confirmed: false, cash_available_vnd: null, shares_available: null, skipped_closed_dates: [] }] }];
};
const daemonPayload = () => ({ state: 'STOPPED', active: false, mode: 'SHADOW', workers_available: false,
  processed_orders_count: 0, active_orders_count: 0, active_workers: 0, last_heartbeat: null, uptime_seconds: 0, daily_pnl_vnd: 0 });

it('accepts recorded execution at inclusive cutoff and separates forecasts from confirmed funds', () => {
  vi.setSystemTime(new Date(executionCutoff));
  const values = executionPayloads();
  values[0].orders![0].availableAt = executionCutoff;
  values[1].standalone![0].availableAt = executionCutoff;
  const data = validateExecutionData(values, executionCutoff);
  expect(data.points[0].bps).toBe(110);
  expect(data.orders[0].price).toBe(10100);
  expect(data.settlements[0].cash).toBeNull();
  values[3].settlements![0] = { ...values[3].settlements![0], confirmed: true, broker_effective_at: '2026-10-05T03:00:00Z',
    settlement_effective_at: '2026-10-07T08:30:00Z', confirmation_available_at: executionCutoff, cash_available_vnd: 0 as any, shares_available: 100 as any };
  expect(validateExecutionData(values, executionCutoff).settlements[0].confirmed).toBe(true);
});

it.each([null, '', '1', [], {}, true, NaN, Infinity, -Infinity, -1, 1e13])('rejects malformed execution numeric value %s', (value) => {
  vi.setSystemTime(new Date(executionCutoff));
  for (const field of ['qty', 'price', 'filledQty']) {
    const payload = executionPayloads();
    Object.assign(payload[0].orders![0], { [field]: value });
    expect(() => validateExecutionData(payload, executionCutoff)).toThrow('Execution data unavailable');
  }
  for (const field of ['quantity', 'arrival_price', 'executed_price', 'fee_vnd']) {
    const payload = executionPayloads();
    Object.assign(payload[2].points![0], { [field]: value });
    expect(() => validateExecutionData(payload, executionCutoff)).toThrow('Execution data unavailable');
  }
});

it.each(['cutoff', 'future', 'naive', 'invalid-day', 'unit', 'provenance', 'duplicates', 'oversized', 'count', 'sign', 'fee', 'weighted', 'overflow', 'confirmation', 'future-confirmation', 'false-funds', 'close', 'venue', 'status'])('rejects execution boundary %s', (fault) => {
  vi.setSystemTime(new Date(executionCutoff));
  const values = executionPayloads();
  if (fault === 'cutoff') values[1].effective_cutoff = '2026-10-08T08:30:00Z';
  if (fault === 'future') values[0].orders![0].availableAt = '2099-01-01T00:00:00Z';
  if (fault === 'naive') values[0].orders![0].timestamp = '2026-10-05T03:00:00';
  if (fault === 'invalid-day') values[0].orders![0].timestamp = '2026-02-30T03:00:00Z';
  if (fault === 'unit') values[0].price_unit = 'VND_THOUSANDS';
  if (fault === 'provenance') values[0].provenance = 'LIVE_UNVERIFIED';
  if (fault === 'duplicates') { values[0].orders!.push(values[0].orders![0]); values[0].count = 2; }
  if (fault === 'oversized') values[0].orders = Array(5001).fill(values[0].orders![0]);
  if (fault === 'count') values[0].count = 0;
  if (fault === 'sign') values[2].sign_convention = 'NEGATIVE_IS_COST';
  if (fault === 'fee') values[2].fees_included = false;
  if (fault === 'weighted') values[2].venues![0].average_slippage_bps = 111;
  if (fault === 'overflow') Object.assign(values[0].orders![0], { qty: 1e8, filledQty: 1e8, price: 1e8 });
  if (fault === 'confirmation') values[3].settlements![0].confirmed = true;
  if (fault === 'future-confirmation') Object.assign(values[3].settlements![0], { confirmed: true, broker_effective_at: executionCutoff, settlement_effective_at: executionCutoff, confirmation_available_at: '2099-01-01T00:00:00Z', cash_available_vnd: 0, shares_available: 100 });
  if (fault === 'false-funds') Object.assign(values[3].settlements![0], { cash_available_vnd: 0 });
  if (fault === 'close') values[3].settlements![0].expected_settlement_at = '2026-10-07T08:29:59Z';
  if (fault === 'venue') values[2].points![0].venue = 'HNX';
  if (fault === 'status') values[0].orders![0].status = 'PENDING';
  expect(() => validateExecutionData(values, executionCutoff)).toThrow('Execution data unavailable');
});

it('rejects sub-millisecond future publication and confirmation at the inclusive cutoff', () => {
  vi.setSystemTime(new Date(executionCutoff));
  const values = executionPayloads();
  values[0].orders[0].availableAt = '2026-10-09T08:30:00.000001Z';
  expect(() => validateExecutionData(values, executionCutoff)).toThrow();
});

it('handles zero quantity hierarchy without dividing or inventing completion', () => {
  vi.setSystemTime(new Date(executionCutoff));
  const values = executionPayloads() as any[];
  const parent = { ...values[0].orders[0], orderId: 'parent', qty: 0, filledQty: 0, price: 0, status: 'PENDING' };
  const child = { ...parent, orderId: 'child', parentOrderId: 'parent', sequence: 0 };
  values[0].orders = [parent, child]; values[0].count = 2;
  values[1].standalone = []; values[1].parents = [{ parent_order_id: 'parent', symbol: 'VCB', side: 'BUY', algo_type: 'DIRECT', target_qty: 0, filled_qty: 0, completion_pct: null, sequence_complete: true, slices: [child] }];
  values[2].points = []; values[2].venues = []; values[3].settlements = [];
  expect(validateExecutionData(values, executionCutoff).parents[0].completion).toBeNull();
  for (const change of [{ completion_pct: 0 }, { sequence_complete: false }, { filled_qty: 1 }]) {
    const broken = structuredClone(values); Object.assign(broken[1].parents[0], change);
    expect(() => validateExecutionData(broken, executionCutoff)).toThrow();
  }
});

it.each(['oversized', 'length', 'utf8', 'bom', 'json', 'http', 'stream', 'abort', 'read'])('bounds execution response and redacts %s failures', async (fault) => {
  const controller = new AbortController();
  let response: Response;
  if (fault === 'oversized') response = new Response(new Uint8Array(1024 * 1024 + 1));
  else if (fault === 'length') response = new Response('{}', { headers: { 'Content-Length': '1048577' } });
  else if (fault === 'utf8') response = new Response(new Uint8Array([34, 195, 34]));
  else if (fault === 'bom') response = new Response(new Uint8Array([239, 187, 191, 123, 125]));
  else if (fault === 'json') response = new Response('SECRET malformed');
  else if (fault === 'http') response = new Response('SECRET', { status: 429 });
  else if (fault === 'stream') response = new Response(null);
  else if (fault === 'read') response = new Response(new ReadableStream({ start(c) { c.error(Error('SECRET')); } }));
  else { controller.abort(); response = new Response('{}'); }
  vi.stubGlobal('fetch', vi.fn(async () => response));
  await expect(requestExecutionData('/api/v1/execution/status', controller.signal)).rejects.toThrow('Execution data unavailable');
});

it('accepts exact 1 MiB, split UTF-8 and CRLF payloads but rejects accumulated overflow', async () => {
  const controller = new AbortController();
  for (const content of ['{}' + ' '.repeat(1024 * 1024 - 2), '{\r\n"value":"đồng"\r\n}']) {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(content)));
    expect(await requestExecutionData('/api/v1/execution/status', controller.signal)).toEqual(JSON.parse(content));
  }
  const bytes = new TextEncoder().encode('{"value":"đồng"}');
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({ start(c) { for (const byte of bytes) c.enqueue(new Uint8Array([byte])); c.close(); } }))));
  expect(await requestExecutionData('/api/v1/execution/status', controller.signal)).toEqual({ value: 'đồng' });
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({ start(c) { c.enqueue(new Uint8Array(1024 * 1024)); c.enqueue(new Uint8Array([32])); c.close(); } }), { headers: { 'Content-Length': '2' } })));
  await expect(requestExecutionData('/api/v1/execution/status', controller.signal)).rejects.toThrow('Execution data unavailable');
});

it('preserves unequal venue weighting, sell sign, missing fee exclusion and closed-date evidence', () => {
  vi.setSystemTime(new Date(executionCutoff));
  const values = executionPayloads();
  const sell = { ...values[0].orders[0], orderId: 'sell', side: 'SELL', qty: 200, filledQty: 200, price: 9900 };
  values[0].orders.push(sell); values[0].count = 2; values[1].standalone.push(sell);
  values[2].points.push({ ...values[2].points[0], order_id: 'sell', side: 'SELL', quantity: 200, executed_price: 9900, slippage_bps: 105 });
  Object.assign(values[2].venues[0], { count: 2, arrival_notional_vnd: 3000000, average_slippage_bps: 320 / 3 });
  values[3].settlements.push({ ...values[3].settlements[0], order_id: 'sell', side: 'SELL' });
  expect(validateExecutionData(values, executionCutoff).venues[0].bps).toBeCloseTo(320 / 3);
  values[2].points.pop(); values[2].excluded_missing_benchmark_or_fee = 1;
  Object.assign(values[2].venues[0], { count: 1, arrival_notional_vnd: 1000000, average_slippage_bps: 110 });
  expect(validateExecutionData(values, executionCutoff).excluded).toBe(1);
  const closed = executionPayloads();
  closed[0].orders[0].timestamp = '2026-10-02T03:00:00Z'; closed[0].orders[0].availableAt = closed[0].orders[0].timestamp;
  closed[3].settlements[0].trade_at = closed[0].orders[0].timestamp;
  closed[3].settlements[0].expected_settlement_at = '2026-10-06T08:30:00Z'; closed[3].settlements[0].skipped_closed_dates = ['2026-10-03', '2026-10-04'];
  expect(validateExecutionData(closed, executionCutoff).settlements[0].skipped).toHaveLength(2);
});

it('serializes rapid confirmed daemon actions and suppresses post-unmount callbacks', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  let resolve!: (response: Response) => void;
  let signal!: AbortSignal;
  const changed = vi.fn(), refresh = vi.fn();
  const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
    if (init.method === 'GET') return new Response(JSON.stringify(daemonPayload()));
    signal = init.signal as AbortSignal;
    return new Promise<Response>((done) => { resolve = done; });
  });
  vi.stubGlobal('fetch', fetcher);
  act(() => root.render(<QueryClientProvider client={client}><PaperDaemonPanel onStateChange={changed} onRefresh={refresh} /></QueryClientProvider>));
  await settle();
  const start = Array.from(container.querySelectorAll('button')).find((button) => button.textContent === 'start')!;
  act(() => { start.click(); start.click(); }); await settle();
  expect(fetcher.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(1);
  act(() => root.render(null));
  expect(signal.aborted).toBe(true);
  resolve(new Response(JSON.stringify({ ...daemonPayload(), state: 'RUNNING', active: true }))); await settle();
  expect(changed).not.toHaveBeenCalled(); expect(refresh).not.toHaveBeenCalled();
});

it('renders all execution widgets from four real endpoint envelopes with one cutoff', async () => {
  vi.setSystemTime(new Date(executionCutoff));
  const routes = ['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'];
  const fetcher = vi.fn(async (url: string) => {
    const route = new URL(url, 'http://localhost').pathname.split('/').pop()!;
    const cutoff = new URL(url, 'http://localhost').searchParams.get('as_of')!;
    return new Response(JSON.stringify(route === 'status' ? daemonPayload() : executionPayloads(cutoff)[routes.indexOf(route)]));
  });
  vi.stubGlobal('fetch', fetcher);
  act(() => root.render(<QueryClientProvider client={client}><ExecutionBlotterView /></QueryClientProvider>));
  await settle();
  expect(container.querySelectorAll('section')).toHaveLength(5);
  expect(container.textContent).toContain('110.00');
  expect(container.textContent).toContain('Unconfirmed forecast');
  expect(container.textContent).not.toContain('VCI / SSI');
  expect(container.textContent).not.toContain('-0.04%');
  expect(container.innerHTML).not.toMatch(/purple|violet|fuchsia/i);
  const calls = fetcher.mock.calls.filter(([url]) => url.includes('as_of='));
  expect(calls).toHaveLength(4);
  expect(new Set(calls.map(([url]) => new URL(url, 'http://localhost').searchParams.get('as_of'))).size).toBe(1);
  act(() => (container.querySelector('button[aria-label="Open VCB in Chart Station"]') as HTMLButtonElement).click());
  expect(useUiStore.getState().selectedTicker).toBe('VCB');
  expect(useUiStore.getState().activeModule).toBe('chart_station');
});

it('fails closed on refresh then recovers explicitly without retries or stale success', async () => {
  vi.setSystemTime(new Date(executionCutoff));
  let failure = false;
  const routes = ['blotter', 'timeline', 'slippage-distribution', 'settlement-timeline'];
  const fetcher = vi.fn(async (url: string) => {
    const parsed = new URL(url, 'http://localhost'), route = parsed.pathname.split('/').pop()!;
    return new Response(JSON.stringify(route === 'status' ? daemonPayload() : failure ? { detail: 'SECRET' } : executionPayloads(parsed.searchParams.get('as_of')!)[routes.indexOf(route)]), { status: route === 'status' || !failure ? 200 : 424 });
  });
  vi.stubGlobal('fetch', fetcher);
  act(() => root.render(<QueryClientProvider client={client}><ExecutionBlotterView /></QueryClientProvider>));
  await settle();
  const refresh = () => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === 'Refresh execution data')!.click();
  failure = true; act(refresh); await settle();
  expect(container.querySelector('table')).toBeNull();
  expect(container.textContent).not.toContain('SECRET');
  expect(container.textContent).toContain('Execution data unavailable');
  const executionAttempts = () => fetcher.mock.calls.filter(([url]) => url.includes('as_of=')).length;
  const attempts = executionAttempts();
  await settle(120000);
  await act(async () => { focusManager.setFocused(false); focusManager.setFocused(true); onlineManager.setOnline(false); onlineManager.setOnline(true); await client.invalidateQueries(); });
  expect(executionAttempts()).toBe(attempts);
  failure = false; act(refresh); await settle();
  expect(container.textContent).toContain('110.00');
});

it('deduplicates execution reads and aborts siblings at deadline or module departure', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
    signals.push(init.signal as AbortSignal);
    init.signal!.addEventListener('abort', () => reject(Error('SECRET aborted')), { once: true });
  })));
  function Probe() { useExecutionData(); return null; }
  act(() => root.render(<QueryClientProvider client={client}><Probe /><Probe /></QueryClientProvider>));
  await settle(); expect(signals).toHaveLength(4);
  act(() => root.render(null)); await settle();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  client.clear(); signals.length = 0;
  act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
  await settle(10050);
  expect(signals).toHaveLength(4); expect(signals.every((signal) => signal.aborted)).toBe(true);
});

it('daemon remains unknown offline and requires confirmed mutation with no repeated action', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(daemonPayload()))));
  act(() => root.render(<QueryClientProvider client={client}><PaperDaemonPanel /></QueryClientProvider>));
  await settle();
  const start = () => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === 'start')!.click();
  act(start); expect(confirm).toHaveBeenCalledTimes(1); expect(fetch).toHaveBeenCalledTimes(1);
  confirm.mockReturnValue(true);
  vi.stubGlobal('fetch', vi.fn(async () => { throw Error('https://user:SECRET@private.invalid'); }));
  act(start); await settle();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Daemon unavailable');
  expect(container.textContent).not.toContain('SECRET');
  expect(container.textContent).not.toContain('worker(s)');
  expect(container.querySelector('dl')).toBeNull();
  await settle(60000); expect(fetch).toHaveBeenCalledTimes(1);
});

it.each([null, '', '0', [], true, NaN, Infinity, -Infinity, -1, 1e13])('validates daemon metrics %s without mock fallback', (value) => {
  for (const field of ['uptime_seconds', 'processed_orders_count', 'active_workers']) {
    expect(() => validateDaemonStatus({ ...daemonPayload(), [field]: value })).toThrow();
  }
});

const macroCutoff = '2026-01-30T08:30:00Z';
const macroPayloads = (cutoff = macroCutoff) => {
  const tuple = <T extends unknown[]>(...items: T) => items;
  const envelope = { status: 'success', effective_cutoff: cutoff };
  const observation = { as_of: '2026-01-30T01:00:00Z', available_at: '2026-01-30T01:00:00Z', source: 'fixture' };
  return tuple(
    { ...envelope, interbank: [{ ...observation, curve_type: 'INTERBANK', tenor: 'overnight', tenor_days: 1, rate: 4,
      rate_unit: 'PERCENT_PER_ANNUM' }], sovereign: [] },
    { ...envelope, regime: 'EXPANSION', coordinates: { growth: 0, inflation: -0.5, unit: 'DIMENSIONLESS' },
      probability_method: 'DETERMINISTIC_RULE_ONE_HOT', coordinate_method: 'TANH_NATIVE_UNIT_ZSCORE',
      state_probabilities: { expansion: 1, neutral_chop: 0, high_vol_bear: 0, crisis: 0 },
      indicators: [{ name: 'stress', value: 0, unit: 'INDEX_0_100' }], omo_net_billion_vnd: -20 },
    { ...envelope, bands: [{ ...observation, venue: 'HOSE', instrument: 'VCB', floor: 46500, reference: 50000,
      ceiling: 53500, price_scale: 'VND_FULL', effective_from: '2026-01-30T02:00:00Z', effective_to: '2026-01-30T09:00:00Z' }] },
  );
};

it('validates inclusive macro PIT cutoff, zero metrics and unscaled VND at 15:30 ICT', () => {
  const [curve, regime, bands] = macroPayloads();
  curve.interbank![0].available_at = macroCutoff;
  const data = validateMacroData(curve, regime, bands, macroCutoff);
  expect(data.growth).toBe(0);
  expect(data.omo).toBe(-20);
  expect(data.bands[0].reference).toBe(50000);
  expect(data.interbank[0].rate).toBe(4);
});

it.each([null, '', '4', [], true, NaN, Infinity, -Infinity, -1, 1e13])('rejects malformed macro rates %s', (value) => {
  const [curve, regime, bands] = macroPayloads();
  (curve.interbank![0] as Record<string, unknown>).rate = value;
  expect(() => validateMacroData(curve, regime, bands, macroCutoff)).toThrow('Invalid macro response');
});

it.each(['growth', 'inflation', 'omo', 'indicator', 'floor', 'reference', 'ceiling'])('rejects malformed macro numeric field %s', (field) => {
  for (const value of [null, '', '1', [], true, NaN, Infinity, -Infinity, 1e13]) {
    const [curve, regime, bands] = macroPayloads();
    if (field === 'growth' || field === 'inflation') Object.assign(regime.coordinates, { [field]: value });
    else if (field === 'omo') Object.assign(regime, { omo_net_billion_vnd: value });
    else if (field === 'indicator') Object.assign(regime.indicators[0], { value });
    else Object.assign(bands.bands[0], { [field]: value });
    expect(() => validateMacroData(curve, regime, bands, macroCutoff)).toThrow('Invalid macro response');
  }
});

it.each(['future', 'naive', 'invalid-day', 'invalid-hour', 'cutoff', 'mass', 'method', 'scale', 'order', 'expired', 'duplicate', 'oversized', 'schema'])('rejects macro %s boundary violations', (fault) => {
  const [curve, regime, bands] = macroPayloads();
  if (fault === 'future') curve.interbank![0].available_at = '2026-01-30T08:30:01Z';
  if (fault === 'naive') curve.interbank![0].as_of = '2026-01-30T01:00:00';
  if (fault === 'invalid-day') curve.interbank![0].as_of = '2026-02-30T01:00:00Z';
  if (fault === 'invalid-hour') curve.interbank![0].as_of = '2026-01-29T24:00:00Z';
  if (fault === 'cutoff') regime.effective_cutoff = '2026-01-30T08:29:59Z';
  if (fault === 'mass') regime.state_probabilities!.expansion = 0.9;
  if (fault === 'method') regime.probability_method = 'HMM';
  if (fault === 'scale') bands.bands![0].price_scale = 'VND_THOUSAND';
  if (fault === 'order') bands.bands![0].floor = 60000;
  if (fault === 'expired') bands.bands![0].effective_to = macroCutoff;
  if (fault === 'duplicate') curve.interbank!.push(curve.interbank![0]);
  if (fault === 'oversized') curve.interbank = Array(101).fill(curve.interbank![0]);
  if (fault === 'schema') regime.coordinates = null as any;
  expect(() => validateMacroData(curve, regime, bands, macroCutoff)).toThrow('Invalid macro response');
});

it('deduplicates simultaneous macro consumers and isolates malformed cutoffs', async () => {
  const { useMacroData } = await import('../modules/macro_cockpit/LandingDatabaseHub');
  const Consumer = () => { useMacroData(); return null; };
  vi.setSystemTime(new Date(macroCutoff));
  const fetch = vi.fn(async (url: string) => {
    const cutoff = new URL(url, 'http://localhost').searchParams.get('as_of')!;
    const routes = ['yield-curve', 'regime-metrics', 'limit-bands'];
    return { ok: true, json: async () => macroPayloads(cutoff)[routes.findIndex((route) => url.includes(route))] };
  });
  vi.stubGlobal('fetch', fetch);
  act(() => root.render(<QueryClientProvider client={client}><Consumer /><Consumer /></QueryClientProvider>));
  await settle();
  expect(fetch).toHaveBeenCalledTimes(3);
  const [curve, regime, bands] = macroPayloads();
  for (const cutoff of ['', '2026-01-30', '2099-01-30T08:30:00Z']) {
    expect(() => validateMacroData(curve, regime, bands, cutoff)).toThrow('Invalid macro response');
  }
});

it('loads dedicated macro endpoints in parallel with a shared cutoff and renders honest empty states', async () => {
  const cutoff = '2026-01-30T08:30:00.000Z';
  vi.setSystemTime(new Date(cutoff));
  const payloads = macroPayloads(cutoff);
  const routes = ['yield-curve', 'regime-metrics', 'limit-bands'];
  const fetch = vi.fn(async (url: string) => new Response(JSON.stringify(payloads[routes.findIndex((route) => url.includes(route))])));
  vi.stubGlobal('fetch', fetch);
  act(() => useUiStore.setState({ activeModule: 'macro_cockpit' }));
  act(() => root.render(<QueryClientProvider client={client}><LandingDatabaseHub /></QueryClientProvider>));
  await settle();
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(fetch.mock.calls.every(([url]) => new URL(url, 'http://localhost').searchParams.get('as_of') === cutoff)).toBe(true);
  expect(container.textContent).toContain('Rule-based classification, not HMM confidence');
  expect(container.textContent).toContain('50,000');
  expect(container.textContent).toContain('No observations at this cutoff');
  expect(container.textContent).not.toContain('PIT VALIDATED');
  expect(container.querySelectorAll('table')).toHaveLength(2);
});

it.each(['429', '503', 'network', 'timeout', 'malformed'])('fails closed for macro %s without automatic retry or secret echo', async (fault) => {
  let signals: AbortSignal[] = [];
  const fetch = vi.fn((_: string, init: RequestInit) => {
    signals.push(init.signal as AbortSignal);
    if (fault === 'network') return Promise.reject(new Error('https://user:SECRET@example.com'));
    if (fault === 'timeout') return new Promise((_, reject) => init.signal!.addEventListener('abort', () => reject(new Error('SECRET timeout')), { once: true }));
    return Promise.resolve({ ok: fault === 'malformed', status: Number(fault), json: async () => ({ detail: 'SECRET', status: 'success' }) });
  });
  vi.stubGlobal('fetch', fetch);
  act(() => useUiStore.setState({ activeModule: 'macro_cockpit' }));
  act(() => root.render(<QueryClientProvider client={client}><LandingDatabaseHub /></QueryClientProvider>));
  await settle(10050);
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Macro data unavailable');
  expect(container.textContent).not.toContain('SECRET');
  expect(container.querySelector('table')).toBeNull();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  await settle(120000);
  act(() => { focusManager.setFocused(false); onlineManager.setOnline(false); });
  act(() => { focusManager.setFocused(true); onlineManager.setOnline(true); });
  await act(async () => { await client.invalidateQueries({ queryKey: ['macro-cockpit'] }); });
  await settle();
  expect(fetch).toHaveBeenCalledTimes(3);
  const refresh = container.querySelector('button')!;
  act(() => refresh.click());
  await settle(10050);
  expect(fetch).toHaveBeenCalledTimes(6);
});

it('hides prior macro success after refresh failure and recovers through explicit retry across locales', async () => {
  vi.setSystemTime(new Date(macroCutoff));
  let fail = false;
  const routes = ['yield-curve', 'regime-metrics', 'limit-bands'];
  const fetch = vi.fn(async (url: string) => {
    const cutoff = new URL(url, 'http://localhost').searchParams.get('as_of')!;
    return new Response(JSON.stringify(fail ? { detail: 'SECRET' } : macroPayloads(cutoff)[routes.findIndex((route) => url.includes(route))]), { status: fail ? 424 : 200 });
  });
  vi.stubGlobal('fetch', fetch);
  act(() => useUiStore.setState({ activeModule: 'macro_cockpit' }));
  act(() => root.render(<QueryClientProvider client={client}><LandingDatabaseHub /></QueryClientProvider>));
  await settle();
  expect(container.textContent).toContain('50,000');
  fail = true;
  act(() => container.querySelector('button')!.click());
  await settle();
  expect(container.querySelector('table')).toBeNull();
  expect(container.textContent).not.toContain('50,000');
  act(() => useUiStore.setState({ locale: 'vi' }));
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Dữ liệu vĩ mô không khả dụng');
  expect(fetch).toHaveBeenCalledTimes(6);
  fail = false;
  act(() => container.querySelector('button')!.click());
  await settle();
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(container.textContent).toContain('50.000');
  expect(fetch).toHaveBeenCalledTimes(9);
});

it('aborts macro requests on module departure without fetching macro data in the news hub', async () => {
  const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', vi.fn((_: string, init: RequestInit) => {
    signals.push(init.signal as AbortSignal);
    return new Promise((_, reject) => init.signal!.addEventListener('abort', () => reject(new Error('aborted')), { once: true }));
  }));
  act(() => useUiStore.setState({ activeModule: 'macro_cockpit' }));
  act(() => root.render(<QueryClientProvider client={client}><LandingDatabaseHub /></QueryClientProvider>));
  await settle();
  expect(signals).toHaveLength(3);
  act(() => useUiStore.setState({ activeModule: 'macro_news_hub' }));
  await settle();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  expect(signals).toHaveLength(3);
});

it.each(['429', '503', 'network', 'timeout', 'malformed'])('bounds OHLCV %s failures until explicit retry, including cached-data failures', async (failure) => {
  const payload = (symbol = 'FPT') => ({ status: 'success', symbol, exchange: 'HOSE', total_bars: 1,
    bars: [{ time: '2026-10-09', open: 100000, high: 100100, low: 99900, close: 100000, volume: 1000 }] });
  const fail = (_url: unknown, init: RequestInit) => {
    if (failure === 'timeout') return new Promise<Response>((_resolve, reject) => {
      init.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    });
    if (failure === 'network') return Promise.reject(new Error('Injected offline failure'));
    return Promise.resolve(new Response(JSON.stringify(failure === 'malformed' ? null : { detail: 'Unavailable' }),
      { status: failure === 'malformed' ? 200 : Number(failure) }));
  };
  for (const interval of ['1D', '1W', '1M']) {
    for (const cached of [false, true]) {
      client.clear();
      const fetcher = vi.fn(fail);
      if (cached) fetcher.mockImplementationOnce(() => Promise.resolve(new Response(JSON.stringify(payload()))));
      vi.stubGlobal('fetch', fetcher);
      let query!: ReturnType<typeof useMarketOhlcv>;
      function Probe() { query = useMarketOhlcv('FPT', undefined, undefined, 500, interval); return <p>{query.status}</p>; }
      const mount = () => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>);
      act(mount);
      await settle();
      if (cached) { expect(query.isSuccess).toBe(true); await settle(15000); }
      await settle(10050);
      expect(query.isError).toBe(true);
      const failedCalls = cached ? 2 : 1;
      expect(fetcher).toHaveBeenCalledTimes(failedCalls);
      await settle(120000);
      // App stream events invalidate all active queries. They must not revive failed OHLCV.
      await act(async () => {
        focusManager.setFocused(false); focusManager.setFocused(true);
        onlineManager.setOnline(false); onlineManager.setOnline(true);
        await client.invalidateQueries({ refetchType: 'active' });
      });
      act(() => root.render(null));
      act(mount);
      await settle(60000);
      expect(fetcher).toHaveBeenCalledTimes(failedCalls);
      // A failed manual attempt remains bounded too.
      act(() => { void query.refetch(); });
      await settle(10050);
      expect(query.isError).toBe(true);
      await settle(60000);
      expect(fetcher).toHaveBeenCalledTimes(failedCalls + 1);
      fetcher.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(payload()))));
      act(() => { void query.refetch(); });
      await settle();
      expect(query.isSuccess).toBe(true);
      expect(query.data?.symbol).toBe('FPT');
      expect(fetcher).toHaveBeenCalledTimes(failedCalls + 2);
      await settle(15000);
      expect(fetcher).toHaveBeenCalledTimes(failedCalls + 3);
      act(() => root.render(null));
    }
  }
  focusManager.setFocused(undefined);
});

it('isolates failed OHLCV keys and deduplicates concurrent manual recovery', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 429 }));
  vi.stubGlobal('fetch', fetcher);
  let query!: ReturnType<typeof useMarketOhlcv>;
  function Probe({ symbol }: { symbol: string }) { query = useMarketOhlcv(symbol); return <p>{query.status}</p>; }
  const mount = (symbol: string) => root.render(<QueryClientProvider client={client}><Probe symbol={symbol} /></QueryClientProvider>);
  act(() => mount('FPT'));
  await settle();
  act(() => mount('HPG'));
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(2);
  act(() => mount('FPT'));
  await settle(60000);
  expect(fetcher).toHaveBeenCalledTimes(2);
  let recover!: (response: Response) => void;
  fetcher.mockImplementation(() => new Promise<Response>((resolve) => { recover = resolve; }));
  act(() => { void query.refetch({ cancelRefetch: false }); void query.refetch({ cancelRefetch: false }); });
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(query.isFetching).toBe(true);
  recover(new Response(JSON.stringify({ status: 'success', symbol: 'FPT', exchange: 'HOSE', total_bars: 0, bars: [] })));
  await settle();
  expect(query.isSuccess).toBe(true);
});

it('mounts every real App route under network failure and closes streams', async () => {
  act(() => root.render(<App />));
  const modules: ModuleType[] = ['pipeline_console', 'control_center', 'model_registry', 'alpha_factory',
    'strategy_lab', 'macro_cockpit', 'macro_news_hub', 'fundamental_matrix', 'alpha_portfolio',
    'barra_risk_tca', 'chart_station', 'execution_blotter'];
  for (const module of modules) {
    act(() => useUiStore.getState().setActiveModule(module));
    await settle();
    expect(container.querySelector('main')?.textContent).not.toBe('');
    if (module === 'pipeline_console') {
      const section = container.querySelector('main section')!;
      expect(section.getAttribute('aria-label')).toBe('VALIDATED RESEARCH PIPELINE');
      expect(section.querySelector('[role="status"]')?.textContent).toBe('This module is unavailable in this build.');
      expect(section.querySelectorAll('button, form, progress')).toHaveLength(0);
      act(() => useUiStore.getState().setLocale('vi'));
      expect(section.getAttribute('aria-label')).toBe('PIPELINE NGHIÊN CỨU ĐÃ XÁC THỰC');
      act(() => useUiStore.getState().setLocale('en'));
    }
    if (module === 'barra_risk_tca') {
      const risk = container.querySelector('section[aria-label="Barra decomposition"]')!;
      expect(risk.querySelector('[role="status"]')?.textContent).toBe(en.common.integrationUnavailable);
      expect(risk.querySelector('[role="alert"]')?.textContent).toBe('Risk request failed. Check inputs and available data.');
      expect(risk.querySelector('form')).not.toBeNull();
      expect(container.textContent).not.toContain('BARRA_VN_V3');
    }
  }
  for (const label of ['Copilot', 'Configuration']) {
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === label)!.click());
    await settle();
    const dialog = container.querySelector('[aria-modal="true"]')!;
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);
    expect(dialog).toBeInstanceOf(HTMLDialogElement);
    expect((dialog as HTMLDialogElement).open).toBe(true);
    act(() => useUiStore.getState().setLocale('vi'));
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe(vietnamese.common.integrationUnavailable);
    expect(dialog.getAttribute('aria-label')).toBe(label === 'Configuration'
      ? vietnamese.copilot.configModalTitle : vietnamese.copilot.drawerTitle);
    act(() => dialog.dispatchEvent(new Event('cancel', { cancelable: true })));
    act(() => useUiStore.getState().setLocale('en'));
    expect(container.querySelector('[aria-modal="true"]')).toBeNull();
  }
  expect(useUiStore.getState().isStreamingConnected).toBe(false);
  act(() => root.render(null));
  expect(closed).toHaveBeenCalled();
});

it('rejects unavailable actions and invalid risk inputs without network calls, success data or secret echo', async () => {
  let config!: ReturnType<typeof useLLMConfig>;
  let impact!: ReturnType<typeof usePreTradeImpact>;
  let copilot!: ReturnType<typeof useCopilot>;
  function Probe() {
    config = useLLMConfig();
    impact = usePreTradeImpact();
    copilot = useCopilot(true);
    const { t } = useTranslation();
    return <p>{t.common.retry}</p>;
  }
  act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
  await settle();
  expect(config.isError).toBe(true);
  const profile = { provider: 'custom', model: 'test', api_key: 'DO_NOT_ECHO', base_url: 'https://user:password@example.com',
    temperature: 0, max_tokens: 1, timeout_seconds: 1, enabled: true };
  await act(async () => {
    await expect(config.saveConfig({ global_profile: profile, alpha_quant: profile, news_sentiment: profile, macro_micro: profile })).rejects.toThrow(unavailableMessage);
    await expect(config.testProbe({ ...profile, profile_key: 'global_profile' })).rejects.toThrow(unavailableMessage);
    await expect(config.fetchModels(profile)).rejects.toThrow(unavailableMessage);
    await expect(impact.mutateAsync({ symbol: '', order_size: 0, average_daily_volume: 0, arrival_price: 0 })).rejects.toThrow('INVALID_ALPHA_TEXT');
    copilot.sendQuery('DO_NOT_ECHO');
    copilot.dispatchAction({ id: 'invalid' } as Parameters<typeof copilot.dispatchAction>[0]);
  });
  await settle();
  expect(impact.data).toBeUndefined();
  expect(config.config).toBeUndefined();
  expect(copilot.recommendations).toEqual([]);
  expect(copilot.chatHistory[0].textEn).toBe(unavailableMessage);
  expect(JSON.stringify(copilot.chatHistory)).not.toContain('DO_NOT_ECHO');
  expect(fetch).not.toHaveBeenCalled();
  act(() => useUiStore.getState().setLocale('vi'));
  expect(container.textContent).not.toBe('Retry');
});

it('wraps modal boundaries while ignoring disabled, hidden and negative tab stops', () => {
  const dialog = document.createElement('dialog');
  dialog.open = true;
  dialog.tabIndex = -1;
  dialog.innerHTML = '<button>first</button><button disabled>disabled</button><button hidden>hidden</button><button tabindex="-1">skip</button><button>last</button>';
  container.appendChild(dialog);
  const buttons = Array.from(dialog.querySelectorAll('button'));
  for (const button of buttons) vi.spyOn(button, 'getClientRects').mockReturnValue(button.hidden ? [] as unknown as DOMRectList : [{}] as unknown as DOMRectList);
  const key = (shiftKey = false, value = 'Tab') => {
    const preventDefault = vi.fn();
    containModalFocus({ key: value, shiftKey, currentTarget: dialog, preventDefault } as unknown as ReactKeyboardEvent<HTMLDialogElement>);
    return preventDefault;
  };
  buttons[0].focus();
  expect(key()).not.toHaveBeenCalled();
  expect(key(false, 'Escape')).not.toHaveBeenCalled();
  expect(key(true)).toHaveBeenCalled();
  expect(document.activeElement).toBe(buttons[4]);
  expect(key()).toHaveBeenCalled();
  expect(document.activeElement).toBe(buttons[0]);
  dialog.innerHTML = '';
  expect(key()).toHaveBeenCalled();
  expect(document.activeElement).toBe(dialog);
});

it('blocks malformed and non-finite pre-trade inputs before transport', async () => {
  let impact!: ReturnType<typeof usePreTradeImpact>;
  function Probe() { impact = usePreTradeImpact(); return null; }
  act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
  const valid = { symbol: 'FPT', side: 'BUY' as const, order_size: 1000, average_daily_volume: 10000,
    volatility: 0.02, participation_rate: 0.1, arrival_price: 20000, observed_spread_bps: 1 };
  await act(async () => {
    for (const field of ['order_size', 'average_daily_volume', 'volatility', 'participation_rate', 'arrival_price', 'observed_spread_bps']) {
      for (const value of [null, '', '1', [], NaN, Infinity, -Infinity, -1, 1e13]) {
        await expect(impact.mutateAsync({ ...valid, [field]: value })).rejects.toThrow();
      }
    }
    for (const field of ['order_size', 'average_daily_volume', 'volatility', 'participation_rate', 'arrival_price']) {
      await expect(impact.mutateAsync({ ...valid, [field]: 0 })).rejects.toThrow();
    }
  });
  await settle();
  expect(impact.isError).toBe(true);
  expect(impact.data).toBeUndefined();
  expect(fetch).not.toHaveBeenCalled();
});

it('preserves chart fallback and observed L2 failure states without synthetic data claims', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => { throw new Error('Unsupported renderer'); });
  const onRetry = vi.fn();
  const renderCharts = (candles: Parameters<typeof LightweightChartContainer>[0]['candles'], isLoading = false, isError = false) => {
    act(() => root.render(<>
      <LightweightChartContainer symbol="FPT" candles={candles} showSMA showEMA showVolume alphaMarkers={[]} />
      <OrderbookDepth isLoading={isLoading} isError={isError} onRetry={onRetry} />
    </>));
  };
  renderCharts([]);
  const chart = container.querySelector('section[aria-label="FPT chart"]')!;
  const depth = container.querySelector('section[aria-label="Orderbook depth"]')!;
  expect(chart.querySelector('[role="alert"]')?.textContent).toBe('Chart unavailable. Invalid data or unsupported renderer.');
  expect(chart.querySelector('caption')?.textContent).toBe('FPT · VND full prices');
  expect(chart.querySelectorAll('tbody tr')).toHaveLength(0);
  expect(depth.querySelector('[role="status"]')?.textContent).toBe('Observed L2 feed unavailable. No synthetic depth displayed.');
  expect(depth.querySelector('table')).toBeNull();
  act(() => (depth.querySelector('button') as HTMLButtonElement).click());
  expect(onRetry).toHaveBeenCalledTimes(1);

  const bar = { time: '2026-10-09', open: 100000, high: 100100, low: 99900, close: 100000, volume: 1000 };
  renderCharts([bar]);
  expect(chart.querySelectorAll('tbody tr')).toHaveLength(1);
  expect(chart.textContent).toContain('2026-10-09');
  for (const close of [null, '', '100000', [], NaN, Infinity, -Infinity, 0, -1, 1e13]) {
    renderCharts([{ ...bar, close } as unknown as typeof bar]);
    expect(chart.querySelectorAll('tbody tr')).toHaveLength(0);
    expect(chart.textContent).not.toContain('2026-10-09');
  }
  renderCharts([], true);
  expect(depth.querySelector('[role="status"]')?.textContent).toBe('Loading orderbook…');
  expect(depth.querySelector('button, table')).toBeNull();
  renderCharts([], false, true);
  expect(depth.querySelector('[role="status"]')?.textContent).toBe('Observed L2 feed unavailable. No synthetic depth displayed.');
  expect(depth.querySelector('table')).toBeNull();
  expect(container.textContent).not.toContain(unavailableMessage);
});

it('rejects tiny market prices and keeps OHLCV returns finite or explicitly unavailable', async () => {
  const bar = (time: string, price: number) => ({ time, open: price, high: price, low: price, close: price, volume: 0 });
  const prices = [null, '', '1', [], NaN, Infinity, -Infinity, 0, -1, Number.MIN_VALUE, 1e-310, 0.999999, 1e12 + 1];
  const book = { status: 'success', symbol: 'FPT', exchange: 'HOSE', timestamp: '2026-01-01T08:30:00Z',
    reference_price: 1, floor_price: 1, ceiling_price: 1, spread: 0, spread_bps: 0,
    total_bid_depth: 0, total_ask_depth: 0,
    bids: [{ level: 1, price: 1, volume: 0, orders: 0 }], asks: [{ level: 1, price: 1, volume: 0, orders: 0 }] };
  expect(validateOrderbook(book, 'FPT', 10).reference_price).toBe(1);
  for (const price of prices) {
    for (const field of ['open', 'high', 'low', 'close']) {
      expect(() => validateCandles([{ ...bar('2026-01-01', 1), [field]: price }])).toThrow();
    }
    for (const field of ['reference_price', 'floor_price', 'ceiling_price']) {
      expect(() => validateOrderbook({ ...book, [field]: price }, 'FPT', 10)).toThrow();
    }
    for (const side of ['bids', 'asks']) {
      expect(() => validateOrderbook({ ...book, [side]: [{ level: 1, price, volume: 0, orders: 0 }] }, 'FPT', 10)).toThrow();
    }
  }
  for (const interval of ['1D', '1W', '1M']) {
    const bars = validateCandles([bar('2026-01-01', 1), bar('2026-01-02', 1e12)]);
    expect(aggregateCandles(bars, interval).every((item) => Number.isFinite(item.close))).toBe(true);
  }
  let market!: ReturnType<typeof useMarketOhlcv>;
  function Probe() { market = useMarketOhlcv('FPT'); return null; }
  const response = (price: number) => new Response(JSON.stringify({ status: 'success', symbol: 'FPT', exchange: 'HOSE',
    bars: [bar('2026-01-01', price), bar('2026-01-02', 1e12)], total_bars: 2 }));
  const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response(1e-310)));
  vi.stubGlobal('fetch', fetcher);
  act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
  await settle();
  expect(market.isError).toBe(true);
  expect(market.data).toBeUndefined();
  await settle(60000);
  expect(fetcher).toHaveBeenCalledTimes(1);
  fetcher.mockImplementation(() => Promise.resolve(response(1)));
  act(() => { void market.refetch(); });
  await settle();
  expect(market.isSuccess).toBe(true);
  act(() => root.render(null));

  const query = { isError: false, isLoading: false, isFetching: false, refetch: vi.fn() };
  const ohlcv = vi.spyOn(useMarketDataModule, 'useMarketOhlcv');
  vi.spyOn(useMarketDataModule, 'useMarketOrderbook').mockReturnValue({ ...query, data: undefined } as any);
  for (const [previous, latest, expected] of [
    [100, 110, '+10%'], [100, 90, '-10%'], [1, 1, '+0%'], [1, 1e12, '+99999999999900%'],
    [1e12, 1, '-100%'], [undefined, 1, 'Return unavailable'],
    ...prices.map((price) => [price, 1e12, 'Return unavailable']),
    ...[NaN, Infinity, -Infinity, Number.MIN_VALUE, 0, -1, 1e12 + 1].map((price) => [1, price, 'Return unavailable']),
  ]) {
    const bars = previous === undefined ? [bar('2026-01-02', latest as number)] :
      [bar('2026-01-01', previous as number), bar('2026-01-02', latest as number)];
    ohlcv.mockReturnValue({ ...query, data: { bars } } as any);
    act(() => root.render(<QueryClientProvider client={client}><ChartStationView /></QueryClientProvider>));
    expect(container.textContent).toContain(expected);
    expect(container.textContent).not.toMatch(/(?:Infinity|NaN)%/);
    if (expected === 'Return unavailable') expect(container.querySelector('[role="status"][aria-label="Price return"]')?.textContent).toBe(expected);
  }
});

it('manages native HTMLDialogElement lifecycle, showModal autofocus, cancel Escape forwarding and focus restoration in unavailable mode', async () => {
  const onClose = vi.fn();
  function Harness({ isOpen, isDrawer }: { isOpen: boolean; isDrawer: boolean }) {
    return (
      <QueryClientProvider client={client}>
        <div>
          <button type="button" id="trigger-btn">Trigger</button>
          {isDrawer ? (
            <OmniQuantCopilotDrawer isOpen={isOpen} onClose={onClose} />
          ) : (
            <LLMConfigModal isOpen={isOpen} onClose={onClose} />
          )}
        </div>
      </QueryClientProvider>
    );
  }

  // 1. Copilot Drawer unavailable lifecycle
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  const trigger = container.querySelector('#trigger-btn') as HTMLButtonElement;
  trigger.focus();
  expect(document.activeElement).toBe(trigger);

  act(() => root.render(<Harness isOpen={true} isDrawer={true} />));
  await settle();
  const copilotDialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(copilotDialog).toBeInstanceOf(HTMLDialogElement);
  expect(copilotDialog.open).toBe(true);

  // Initial focus modeled via showModal autofocus
  const cancelBtn = Array.from(copilotDialog.querySelectorAll('button')).find(
    (b) => (b as any).autofocus || b.hasAttribute('autofocus') || b.textContent === en.common.cancel
  ) as HTMLButtonElement;
  expect(cancelBtn).not.toBeNull();
  expect(document.activeElement).toBe(cancelBtn);

  // Escape keydown forwarding to cancel event
  act(() => {
    cancelBtn.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restoration after close
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
  expect(container.querySelector('dialog')).toBeNull();

  // 2. Config Modal unavailable lifecycle
  onClose.mockClear();
  trigger.focus();
  expect(document.activeElement).toBe(trigger);

  act(() => root.render(<Harness isOpen={true} isDrawer={false} />));
  await settle();
  const configDialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(configDialog.open).toBe(true);

  const configCancelBtn = Array.from(configDialog.querySelectorAll('button')).find(
    (b) => (b as any).autofocus || b.hasAttribute('autofocus') || b.textContent === en.common.cancel
  ) as HTMLButtonElement;
  expect(configCancelBtn).not.toBeNull();
  expect(document.activeElement).toBe(configCancelBtn);

  // Native cancel event triggers onClose
  act(() => {
    configDialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restored on close
  act(() => root.render(<Harness isOpen={false} isDrawer={false} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
  expect(container.querySelector('dialog')).toBeNull();
});

it('manages native HTMLDialogElement lifecycle, autofocus, Escape forwarding and focus restoration in available mode', async () => {
  vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue(mockCopilotAvailable);
  const fetchModelsMock = vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' });
  const testProbeMock = vi.fn().mockResolvedValue({ status: 'success', latency_ms: 20, message: 'OK' });
  const saveConfigMock = vi.fn().mockResolvedValue(mockConfigPayload);
  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: saveConfigMock,
    isSaving: false,
    testProbe: testProbeMock,
    fetchModels: fetchModelsMock,
    isFetchingModels: false,
  });

  const onClose = vi.fn();
  function Harness({ isOpen, isDrawer }: { isOpen: boolean; isDrawer: boolean }) {
    return (
      <QueryClientProvider client={client}>
        <div>
          <button type="button" id="trigger-btn">Trigger</button>
          {isDrawer ? (
            <OmniQuantCopilotDrawer isOpen={isOpen} onClose={onClose} />
          ) : (
            <LLMConfigModal isOpen={isOpen} onClose={onClose} />
          )}
        </div>
      </QueryClientProvider>
    );
  }

  // 1. Available Copilot Drawer
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  const trigger = container.querySelector('#trigger-btn') as HTMLButtonElement;
  trigger.focus();

  act(() => root.render(<Harness isOpen={true} isDrawer={true} />));
  await settle();
  const drawerDialog = container.querySelector('dialog[data-drawer]') as HTMLDialogElement;
  expect(drawerDialog.open).toBe(true);

  // Initial focus lands on close button with autofocus
  const drawerCloseBtn = drawerDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(drawerCloseBtn).not.toBeNull();
  expect(document.activeElement).toBe(drawerCloseBtn);

  // Escape keydown forwarding
  act(() => {
    drawerCloseBtn.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restored on close
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  await settle();
  expect(document.activeElement).toBe(trigger);

  // 2. Available Config Modal
  onClose.mockClear();
  trigger.focus();

  act(() => root.render(<Harness isOpen={true} isDrawer={false} />));
  await settle();
  const configDialog = container.querySelector('dialog[aria-label="' + en.copilot.configModalTitle + '"]') as HTMLDialogElement;
  expect(configDialog.open).toBe(true);

  const configCloseBtn = configDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(configCloseBtn).not.toBeNull();
  expect(document.activeElement).toBe(configCloseBtn);

  // Dispatch cancel event
  act(() => {
    configDialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  act(() => root.render(<Harness isOpen={false} isDrawer={false} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
});

it('restores focus through nested config over copilot stack in App', async () => {
  vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue(mockCopilotAvailable);
  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: vi.fn().mockResolvedValue(mockConfigPayload),
    isSaving: false,
    testProbe: vi.fn().mockResolvedValue({ status: 'success', latency_ms: 10, message: 'OK' }),
    fetchModels: vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' }),
    isFetchingModels: false,
  });

  act(() => root.render(<App />));
  await settle();

  // Focus top-level copilot trigger
  const copilotBtn = Array.from(container.querySelectorAll('header button')).find(
    (btn) => btn.textContent === 'Copilot'
  ) as HTMLButtonElement;
  copilotBtn.focus();
  expect(document.activeElement).toBe(copilotBtn);

  // Open Copilot Drawer
  act(() => copilotBtn.click());
  await settle();
  const copilotDialog = container.querySelector('dialog[data-drawer]') as HTMLDialogElement;
  expect(copilotDialog.open).toBe(true);
  const copilotCloseBtn = copilotDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(document.activeElement).toBe(copilotCloseBtn);

  // Locate and focus nested Configuration button inside Copilot Drawer
  const configSettingsBtn = copilotDialog.querySelector('button[title="' + en.copilot.configModalTitle + '"]') as HTMLButtonElement;
  expect(configSettingsBtn).not.toBeNull();
  configSettingsBtn.focus();
  expect(document.activeElement).toBe(configSettingsBtn);

  // Open Configuration Modal over Copilot Drawer
  act(() => configSettingsBtn.click());
  await settle();

  const configDialog = Array.from(container.querySelectorAll('dialog')).find(
    (d) => d.getAttribute('aria-label') === en.copilot.configModalTitle
  ) as HTMLDialogElement;
  expect(configDialog.open).toBe(true);
  const configCloseBtn = configDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(document.activeElement).toBe(configCloseBtn);

  // Close nested Configuration Modal
  act(() => configCloseBtn.click());
  await settle();

  // Focus restored back to the Settings button inside Copilot Drawer
  expect(document.activeElement).toBe(configSettingsBtn);

  // Close Copilot Drawer
  act(() => copilotCloseBtn.click());
  await settle();

  // Focus restored back to the original Copilot header button
  expect(document.activeElement).toBe(copilotBtn);
  expect(container.querySelector('dialog[data-drawer]')).toBeNull();
});

it('handles branch transitions without leaving stranded open dialogs', async () => {
  const onClose = vi.fn();
  function TransitionHarness({ isUnavailable, isDrawer }: { isUnavailable: boolean; isDrawer: boolean }) {
    vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue({
      ...mockCopilotAvailable,
      isUnavailable,
    });
    vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
      config: isUnavailable ? undefined : mockConfigPayload,
      isLoading: false,
      isError: isUnavailable,
      saveConfig: vi.fn(),
      isSaving: false,
      testProbe: vi.fn(),
      fetchModels: vi.fn(),
      isFetchingModels: false,
    });
    return (
      <QueryClientProvider client={client}>
        {isDrawer ? (
          <OmniQuantCopilotDrawer isOpen={true} onClose={onClose} />
        ) : (
          <LLMConfigModal isOpen={true} onClose={onClose} />
        )}
      </QueryClientProvider>
    );
  }

  // 1. Drawer transition from available -> unavailable -> available
  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  act(() => root.render(<TransitionHarness isUnavailable={true} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);

  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  // 2. Config Modal transition from available -> unavailable -> available
  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  act(() => root.render(<TransitionHarness isUnavailable={true} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);

  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it('cleans up dialogs and timers properly on unmount', async () => {
  const closeSpy = vi.spyOn(HTMLDialogElement.prototype, 'close');
  function UnmountHarness() {
    return <OmniQuantCopilotDrawer isOpen={true} onClose={vi.fn()} />;
  }
  act(() => root.render(<UnmountHarness />));
  await settle();
  const dialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(dialog).not.toBeNull();
  expect(dialog.open).toBe(true);

  act(() => root.unmount());
  expect(closeSpy).toHaveBeenCalled();
  expect(container.querySelector('dialog')).toBeNull();
});

it('injects missing error message for model catalog and probe, and tests localized apply-to-all in EN and VI', async () => {
  const credentialErrorUrl = 'https://admin:SECRET_PASSWORD_1234@upstream.secure.bank.internal/api';
  const fetchModelsMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));
  const testProbeMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));
  const saveConfigMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));

  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: saveConfigMock,
    isSaving: false,
    testProbe: testProbeMock,
    fetchModels: fetchModelsMock,
    isFetchingModels: false,
  });

  function ConfigHarness() {
    return (
      <QueryClientProvider client={client}>
        <LLMConfigModal isOpen={true} onClose={vi.fn()} />
      </QueryClientProvider>
    );
  }

  // 1. English localized notifications and fallbacks
  useUiStore.setState({ locale: 'en' });
  act(() => root.render(<ConfigHarness />));
  await settle();

  // Model catalog probe error with injected credential URL
  const fetchBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.fetchModelsBtn)
  ) as HTMLButtonElement;
  expect(fetchBtnEn).not.toBeNull();
  act(() => fetchBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.modelCatalogFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Connection probe error with injected credential URL
  const testConnBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.testConnectionBtn)
  ) as HTMLButtonElement;
  expect(testConnBtnEn).not.toBeNull();
  act(() => testConnBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.probeFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Apply to all profiles notification
  const applyAllBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.applyToAllBtn)
  ) as HTMLButtonElement;
  expect(applyAllBtnEn).not.toBeNull();
  act(() => applyAllBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.profilesSynchronized);

  // Save config error with injected credential URL
  const saveBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.saveConfigBtn)
  ) as HTMLButtonElement;
  expect(saveBtnEn).not.toBeNull();
  act(() => saveBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.saveFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // 2. Vietnamese localized notifications and fallbacks
  act(() => useUiStore.getState().setLocale('vi'));
  await settle();

  // Model catalog probe error fallback VI
  const fetchBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.fetchModelsBtn)
  ) as HTMLButtonElement;
  act(() => fetchBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.modelCatalogFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Connection probe error fallback VI
  const testConnBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.testConnectionBtn)
  ) as HTMLButtonElement;
  act(() => testConnBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.probeFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Apply to all profiles notification VI
  const applyAllBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.applyToAllBtn)
  ) as HTMLButtonElement;
  act(() => applyAllBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.profilesSynchronized);

  // Save config error fallback VI
  const saveBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.saveConfigBtn)
  ) as HTMLButtonElement;
  expect(saveBtnVi).not.toBeNull();
  act(() => saveBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.saveFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');
});

it('strictly guards against backend secret echo across locales in copilot and config', async () => {
  const secretKey = 'CRITICAL_SECRET_KEY_NEVER_ECHO_TOKEN_999';
  const secretHost = 'https://admin:SECRET_PASSWORD_1234@upstream.secure.bank.vn';
  const sensitiveConfig: MultiProfileLLMConfigPayload = {
    global_profile: { ...mockConfigPayload.global_profile, api_key: secretKey, base_url: secretHost },
    alpha_quant: { ...mockConfigPayload.alpha_quant, api_key: secretKey, base_url: secretHost },
    news_sentiment: { ...mockConfigPayload.news_sentiment, api_key: secretKey, base_url: secretHost },
    macro_micro: { ...mockConfigPayload.macro_micro, api_key: secretKey, base_url: secretHost },
  };

  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: sensitiveConfig,
    isLoading: false,
    isError: false,
    saveConfig: vi.fn().mockResolvedValue(sensitiveConfig),
    isSaving: false,
    testProbe: vi.fn().mockResolvedValue({ status: 'success', latency_ms: 15, message: 'OK' }),
    fetchModels: vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' }),
    isFetchingModels: false,
  });

  for (const loc of ['en', 'vi'] as const) {
    act(() => useUiStore.setState({ locale: loc }));
    act(() => root.render(
      <QueryClientProvider client={client}>
        <LLMConfigModal isOpen={true} onClose={vi.fn()} />
      </QueryClientProvider>
    ));
    await settle();

    // Verify raw secret key and embedded password are never echoed into DOM text
    expect(container.textContent).not.toContain(secretKey);
    expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

    // Input must be masked password type by default
    const keyInput = container.querySelector('input[type="password"]') as HTMLInputElement;
    expect(keyInput).not.toBeNull();

    // Verification of localized status indicator
    const expectedStatus = loc === 'vi' ? vietnamese.copilot.hasKeySet : en.copilot.hasKeySet;
    expect(container.textContent).toContain(expectedStatus);
  }
});
