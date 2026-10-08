import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { advancedQuantApi, portfolioErrorMessage, validatePortfolioRequest } from '../api/advancedQuant';
import type { PortfolioReadRequest, PortfolioUniverseRequest } from '../api/advancedQuant';

export const useExecutionBlotter = () => useQuery({
  queryKey: ['execution-blotter'], queryFn: apiClient.getExecutionBlotter, retry: false,
});

function usePortfolioRead<T>(key: string, request: PortfolioUniverseRequest | null, universe: boolean, read: (params: PortfolioUniverseRequest, signal: AbortSignal) => Promise<T>) {
  let snapshot: PortfolioUniverseRequest | null = null;
  try { if (request !== null) snapshot = validatePortfolioRequest(request, universe); } catch { /* Invalid edits disengage reads immediately. */ }
  const binding = JSON.stringify(snapshot), generation = useRef({ binding, value: 0 });
  if (generation.current.binding !== binding) generation.current = { binding, value: generation.current.value + 1 };
  const query = useQuery({
    queryKey: ['alpha-portfolio', key, snapshot], enabled: snapshot !== null,
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
    errorMessage: snapshot === null ? 'Invalid portfolio inputs.' : query.isError ? portfolioErrorMessage(query.error) : null,
    refresh: () => { if (snapshot !== null) void query.refetch(); },
  };
}

export const usePortfolioState = (request: PortfolioReadRequest | null = {}) => usePortfolioRead('state', request, false, advancedQuantApi.getTargetPortfolioState);
export const usePortfolioDynamicUniverse = (request: PortfolioUniverseRequest | null = {}) => usePortfolioRead('universe', request, true, advancedQuantApi.getPortfolioDynamicUniverse);
