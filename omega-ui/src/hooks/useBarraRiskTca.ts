import { useEffect, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import type { BarraRequest, TcaImpactRequest, StressRequest, LiquidityRequest } from '../api/advancedQuant';

function useRiskQuery<T>(key: string, request: (signal: AbortSignal) => Promise<T>) {
  const query = useQuery({
    queryKey: [key], queryFn: ({ signal }) => request(signal),
    retry: false, refetchOnWindowFocus: false,
  });
  return { ...query, data: query.isError || query.isFetching ? undefined : query.data };
}

function useRiskCalculation<T, R>(request: (params: T, signal: AbortSignal) => Promise<R>) {
  const controller = useRef<AbortController | null>(null);
  const mutation = useMutation({
    mutationFn: (params: T) => {
      controller.current?.abort();
      const next = new AbortController();
      controller.current = next;
      return Promise.resolve().then(() => request(structuredClone(params), next.signal)).then((result) => {
        if (next.signal.aborted || controller.current !== next) throw new DOMException('Aborted', 'AbortError');
        return result;
      });
    },
    retry: false,
  });
  useEffect(() => () => controller.current?.abort(), []);
  return {
    ...mutation,
    data: mutation.isSuccess ? mutation.data : undefined,
    reset: () => { controller.current?.abort(); mutation.reset(); },
  };
}

export const useBarraDecomposition = () => useRiskQuery('barra', advancedQuantApi.getBarraDecomposition);
export const useStressScenarios = () => useRiskQuery('stress', advancedQuantApi.getStressScenarios);
export const usePostTradeReport = () => useRiskQuery('post-trade', advancedQuantApi.getPostTradeReport);
export const useRoutingDiagnostics = () => useRiskQuery('routing', advancedQuantApi.getRoutingDiagnostics);
export const useCallerBarra = () => useRiskCalculation((params: BarraRequest, signal) => advancedQuantApi.calculateBarraDecomposition(params, signal));
export const usePreTradeImpact = () => useRiskCalculation((params: Partial<TcaImpactRequest>, signal) => advancedQuantApi.calculatePreTradeImpact(params as TcaImpactRequest, signal));
export const useStressSimulation = () => useRiskCalculation((params: StressRequest, signal) => advancedQuantApi.simulateStressTest(params, signal));
export const useLiquidityConstraints = () => useRiskCalculation((params: LiquidityRequest, signal) => advancedQuantApi.validateLiquidityStress(params, signal));
