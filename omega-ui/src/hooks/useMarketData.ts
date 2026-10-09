import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../api/client';
import type { CandleData, MarketOhlcvResponse, OrderbookData } from '../api/client';

const invalid = () => { throw new Error('Invalid market response'); };
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : invalid();
const finite = (value: unknown, minimum = 0): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= 1e12;
export const isMarketPrice = (value: unknown): value is number => finite(value, 1);
const day = (value: unknown): value is string =>
  typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;

export function validateCandles(value: unknown): CandleData[] {
  if (!Array.isArray(value) || value.length > 5000) return invalid();
  let previous = '';
  return value.map((item) => {
    const bar = record(item);
    if (!day(bar.time) || bar.time <= previous || !finite(bar.volume) ||
        ![bar.open, bar.high, bar.low, bar.close].every(isMarketPrice) ||
        !(Number(bar.low) <= Number(bar.open) && Number(bar.open) <= Number(bar.high) &&
          Number(bar.low) <= Number(bar.close) && Number(bar.close) <= Number(bar.high))) return invalid();
    previous = bar.time;
    return { time: bar.time, open: bar.open as number, high: bar.high as number,
      low: bar.low as number, close: bar.close as number, volume: bar.volume };
  });
}

export function validateOhlcv(value: unknown, symbol: string, limit: number): MarketOhlcvResponse {
  const data = record(value);
  const bars = validateCandles(data.bars);
  if (data.status !== 'success' || data.symbol !== symbol || typeof data.exchange !== 'string' ||
      data.total_bars !== bars.length || bars.length > limit) return invalid();
  return { status: 'success', symbol, exchange: data.exchange, total_bars: bars.length, bars };
}

export function validateOrderbook(value: unknown, symbol: string, depth: number): OrderbookData {
  const data = record(value);
  if (data.status !== 'success' || data.symbol !== symbol || data.is_synthetic === true ||
      typeof data.exchange !== 'string' || typeof data.timestamp !== 'string' ||
      !/(Z|[+-]\d{2}:\d{2})$/.test(data.timestamp) || !Number.isFinite(Date.parse(data.timestamp)) ||
      Date.parse(data.timestamp) > Date.now() ||
      !['reference_price', 'ceiling_price', 'floor_price'].every((key) => isMarketPrice(data[key])) ||
      !['spread', 'spread_bps', 'total_bid_depth', 'total_ask_depth'].every((key) => finite(data[key]))) return invalid();
  for (const side of ['bids', 'asks']) {
    const levels = data[side];
    if (!Array.isArray(levels) || levels.length === 0 || levels.length > depth) return invalid();
    let previous = side === 'bids' ? Infinity : 0;
    for (const [index, item] of levels.entries()) {
      const level = record(item);
      if (level.level !== index + 1 || !isMarketPrice(level.price) || !finite(level.volume) ||
          !finite(level.orders) || !Number.isInteger(level.orders) ||
          (side === 'bids' ? level.price >= previous : level.price <= previous)) return invalid();
      previous = level.price;
    }
  }
  const book = data as unknown as OrderbookData;
  const spread = book.asks[0].price - book.bids[0].price;
  const close = (a: number, b: number) => Math.abs(a - b) <= Math.max(1, Math.abs(b)) * 1e-8;
  if (spread < 0 || !close(book.spread, spread) || book.floor_price > book.reference_price ||
      book.reference_price > book.ceiling_price ||
      !close(book.total_bid_depth, book.bids.reduce((sum, level) => sum + level.volume, 0)) ||
      !close(book.total_ask_depth, book.asks.reduce((sum, level) => sum + level.volume, 0))) return invalid();
  return book;
}

export function aggregateCandles(bars: CandleData[], interval: string): CandleData[] {
  if (!['1D', '1W', '1M'].includes(interval)) return invalid();
  if (interval === '1D') return bars;
  const groups: CandleData[] = [];
  let previous = '';
  for (const bar of bars) {
    const date = new Date(`${bar.time}T00:00:00Z`);
    if (interval === '1W') date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    const key = interval === '1M' ? bar.time.slice(0, 7) : date.toISOString().slice(0, 10);
    const last = groups[groups.length - 1];
    if (key !== previous) groups.push({ ...bar });
    else {
      last.high = Math.max(last.high, bar.high);
      last.low = Math.min(last.low, bar.low);
      last.close = bar.close;
      last.volume += bar.volume;
      if (!finite(last.volume)) return invalid();
    }
    previous = key;
  }
  return groups;
}

async function request(path: string, signal: AbortSignal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const timeout = setTimeout(abort, 10000);
  try { return await apiRequest<unknown>(path, { signal: controller.signal }); }
  finally { clearTimeout(timeout); signal.removeEventListener('abort', abort); }
}

export const useMarketOhlcv = (symbol: string, start?: string, end?: string, limit = 500, interval = '1D') =>
  useQuery({
    queryKey: ['ohlcv', symbol, start, end, limit, interval],
    queryFn: async ({ signal }) => {
      if (!/^[A-Z0-9_]{1,32}$/.test(symbol) || !Number.isInteger(limit) || limit < 1 || limit > 5000 ||
          (start !== undefined && !day(start)) || (end !== undefined && !day(end)) ||
          (start && end && start > end) || !['1D', '1W', '1M'].includes(interval)) return invalid();
      const params = new URLSearchParams({ limit: String(limit) });
      if (start) params.set('start', start);
      if (end) params.set('end', end);
      const data = validateOhlcv(await request(`/api/v1/market/ohlcv/${encodeURIComponent(symbol)}?${params}`, signal), symbol, limit);
      const bars = aggregateCandles(data.bars, interval);
      return { ...data, bars, total_bars: bars.length };
    },
    retry: false,
    retryOnMount: false,
    // Failed queries ignore timers, focus/reconnect and stream invalidation until manual refetch succeeds.
    enabled: (query) => query.state.status !== 'error',
    staleTime: 10000,
    refetchInterval: (query) => query.state.status === 'error' ? false : 15000,
  });

export const useMarketOrderbook = (symbol: string, depth = 10) =>
  useQuery({
    queryKey: ['orderbook', symbol, depth],
    queryFn: async ({ signal }) => {
      if (!/^[A-Z0-9_]{1,32}$/.test(symbol) || !Number.isInteger(depth) || depth < 1 || depth > 20) return invalid();
      return validateOrderbook(await request(`/api/v1/market/orderbook/${encodeURIComponent(symbol)}?depth=${depth}`, signal), symbol, depth);
    },
    retry: false,
    staleTime: 10000,
    // ponytail: unavailable observed L2 feed; manual refresh until a live provider exists.
  });
