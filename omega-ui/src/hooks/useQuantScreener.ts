import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ScreenerFilters } from '../api/client';
import { advancedQuantApi, fundamentalErrorMessage, validateFundamentalRead } from '../api/advancedQuant';
import type { FundamentalRead, FundamentalSymbolRead, FundamentalScreenerRead } from '../api/advancedQuant';

export function screenerRequest(filters: ScreenerFilters, asOf?: string): FundamentalScreenerRead {
  const allowed = ['search', 'exchange', 'sector', 'minPiotroski', 'minRoe', 'minAltmanZ', 'status', 'page', 'pageSize'];
  if (!filters || typeof filters !== 'object' || Array.isArray(filters) || Object.keys(filters).some(key => !allowed.includes(key))) throw new Error('INVALID_FUNDAMENTAL_REQUEST');
  const request: Record<string, unknown> = {};
  for (const [input, output] of [['search', 'symbol'], ['exchange', 'exchange'], ['sector', 'sector'], ['status', 'status'], ['minPiotroski', 'min_piotroski'], ['minRoe', 'min_roe'], ['minAltmanZ', 'min_altman_z'], ['page', 'page'], ['pageSize', 'limit']] as const) {
    const value = filters[input];
    if (value !== undefined && value !== '') request[output] = value;
  }
  if (asOf !== undefined) request.as_of = asOf;
  return validateFundamentalRead(request, 'screener');
}

function useFundamentalRead<R extends FundamentalRead, T>(key: string, request: R | null, kind: 'read' | 'symbol' | 'screener', read: (request: R, signal: AbortSignal) => Promise<T>) {
  let snapshot: R | null = null;
  try { if (request !== null) snapshot = validateFundamentalRead(request, kind) as R; } catch { /* Invalid inputs hide cached data immediately. */ }
  const binding = JSON.stringify(snapshot), generation = useRef({ binding, value: 0 });
  if (generation.current.binding !== binding) generation.current = { binding, value: generation.current.value + 1 };
  const query = useQuery({
    queryKey: ['fundamental-matrix', key, snapshot], enabled: snapshot !== null,
    queryFn: async ({ signal }) => {
      const current = generation.current.value;
      const result = await read(structuredClone(snapshot!), signal);
      if (signal.aborted || current !== generation.current.value) throw new DOMException('Aborted', 'AbortError');
      return result;
    },
    retry: false, staleTime: 0, refetchOnWindowFocus: false,
  });
  return {
    ...query, data: snapshot !== null && query.isSuccess && !query.isFetching ? query.data : undefined,
    errorMessage: snapshot === null ? 'Invalid fundamental inputs.' : query.isError ? fundamentalErrorMessage(query.error) : null,
    refresh: () => { if (snapshot !== null) void query.refetch(); },
  };
}

export function useQuantScreener(filters: ScreenerFilters, asOf?: string) {
  let request: FundamentalScreenerRead | null = null;
  try { request = screenerRequest(filters, asOf); } catch { /* Fail closed before transport. */ }
  return useFundamentalRead('screener', request, 'screener', advancedQuantApi.getFundamentalScreener);
}
export const useFundamentalValuation = (request: FundamentalRead | null) => useFundamentalRead('valuation', request, 'read', advancedQuantApi.getFundamentalValuation);
export const useFundamentalDuPont = (request: FundamentalSymbolRead | null) => useFundamentalRead('dupont', request, 'symbol', advancedQuantApi.getFundamentalDuPont);
export const useFundamentalPiotroski = (request: FundamentalSymbolRead | null) => useFundamentalRead('piotroski', request, 'symbol', advancedQuantApi.getFundamentalPiotroski);
