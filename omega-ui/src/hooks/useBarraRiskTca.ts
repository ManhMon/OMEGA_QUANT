import { useMutation } from '@tanstack/react-query';
import type {
  BarraDecompositionResponse, StressScenariosResponse, PreTradeImpactRequest,
  PreTradeImpactResponse, PostTradeTCAReportResponse, RoutingDiagnosticsResponse,
} from '../api/client';
import { unavailable, useUnavailableQuery } from './useUnavailableQuery';

export const useBarraDecomposition = () => useUnavailableQuery<BarraDecompositionResponse>(['barra']);
export const useStressScenarios = () => useUnavailableQuery<StressScenariosResponse>(['stress']);
export const usePostTradeReport = () => useUnavailableQuery<PostTradeTCAReportResponse>(['post-trade']);
export const useRoutingDiagnostics = () => useUnavailableQuery<RoutingDiagnosticsResponse>(['routing']);
export const usePreTradeImpact = () => useMutation<PreTradeImpactResponse, Error, PreTradeImpactRequest>({
  mutationFn: unavailable<PreTradeImpactResponse>,
  retry: false,
});
