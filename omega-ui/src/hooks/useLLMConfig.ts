import { useMutation } from '@tanstack/react-query';
import type {
  MultiProfileLLMConfigPayload, LLMProbeTestRequest, LLMProbeTestResponse,
  LLMModelFetchRequest, LLMModelFetchResponse,
} from '../api/client';
import { unavailable, useUnavailableQuery } from './useUnavailableQuery';

export function useLLMConfig() {
  const query = useUnavailableQuery<MultiProfileLLMConfigPayload>(['llm-config']);
  const save = useMutation<MultiProfileLLMConfigPayload, Error, MultiProfileLLMConfigPayload>({
    mutationFn: unavailable<MultiProfileLLMConfigPayload>, retry: false,
  });
  const models = useMutation<LLMModelFetchResponse, Error, LLMModelFetchRequest>({
    mutationFn: unavailable<LLMModelFetchResponse>, retry: false,
  });
  return {
    config: query.data, isLoading: query.isLoading, isError: query.isError,
    saveConfig: save.mutateAsync, isSaving: save.isPending,
    testProbe: (_request: LLMProbeTestRequest) => unavailable<LLMProbeTestResponse>(),
    fetchModels: models.mutateAsync, isFetchingModels: models.isPending,
  };
}
