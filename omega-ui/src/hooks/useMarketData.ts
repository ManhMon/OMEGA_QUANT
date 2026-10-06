import type { MarketOhlcvResponse, OrderbookData } from '../api/client';
import { useUnavailableQuery } from './useUnavailableQuery';

export const useMarketOhlcv = (symbol: string, start?: string, end?: string, limit = 500) =>
  useUnavailableQuery<MarketOhlcvResponse>(['ohlcv', symbol, start, end, limit]);
export const useMarketOrderbook = (symbol: string, depth = 10) =>
  useUnavailableQuery<OrderbookData>(['orderbook', symbol, depth]);
