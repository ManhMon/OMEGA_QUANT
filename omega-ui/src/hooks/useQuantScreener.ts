import type { PaginatedResponse, ScreenerFilters, StockScreenerItem } from '../api/client';
import { useUnavailableQuery } from './useUnavailableQuery';

export const useQuantScreener = (filters: ScreenerFilters) =>
  useUnavailableQuery<PaginatedResponse<StockScreenerItem>>(['screener', filters]);
