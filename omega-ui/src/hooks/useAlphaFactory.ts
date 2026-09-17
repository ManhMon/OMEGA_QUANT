import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  apiClient,
  API_BASE,
  AlphaSignalItem,
  DecayProfileResponse,
  EvaluateExpressionResponse,
  DiscoveryProgressEvent,
  StartDiscoveryRequest,
} from '../api/client';

export interface DiscoverySessionState {
  sessionId: string;
  generation: number;
  maxGenerations: number;
  progress: number;
  bestFitness: number;
  bestFormula: string;
  status: 'IDLE' | 'RUNNING' | 'COMPLETED' | 'ERROR';
  history: DiscoveryProgressEvent[];
}

export function useAlphaFactory() {
  const queryClient = useQueryClient();

  // 1. AST Formula Studio State
  const [expression, setExpression] = useState<string>('ts_rank(close, 10)');
  const [targetUniverse, setTargetUniverse] = useState<string>('VN703');

  // 2. Arsenal Filters & Selected Signal
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedAlphaId, setSelectedAlphaId] = useState<string>('ALP_001');

  // 3. Genetic Evolution State
  const [discoveryState, setDiscoveryState] = useState<DiscoverySessionState>({
    sessionId: '',
    generation: 0,
    maxGenerations: 10,
    progress: 0,
    bestFitness: 0,
    bestFormula: '',
    status: 'IDLE',
    history: [],
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  // Queries
  const {
    data: arsenalData,
    isLoading: isArsenalLoading,
    refetch: refetchArsenal,
  } = useQuery({
    queryKey: ['alpha-arsenal', selectedCategory, selectedStatus, searchQuery],
    queryFn: () =>
      apiClient.getAlphaArsenalSignals({
        category: selectedCategory || undefined,
        status: selectedStatus || undefined,
        search: searchQuery || undefined,
        limit: 703,
      }),
    staleTime: 60000,
  });

  const {
    data: decayProfile,
    isLoading: isDecayLoading,
  } = useQuery<DecayProfileResponse>({
    queryKey: ['alpha-decay-profile', selectedAlphaId],
    queryFn: () => apiClient.getAlphaDecayProfile(selectedAlphaId),
    enabled: Boolean(selectedAlphaId),
    staleTime: 30000,
  });

  // Evaluate Expression Mutation
  const evaluateMutation = useMutation({
    mutationFn: (expr: string) =>
      apiClient.evaluateAlphaExpression({
        expression: expr,
        universe: targetUniverse,
      }),
  });

  // Start Discovery Mutation
  const startDiscoveryMutation = useMutation({
    mutationFn: (req: StartDiscoveryRequest) => apiClient.startAlphaDiscovery(req),
    onSuccess: (resp: {
      job_id?: string;
      session_id?: string;
      best_fitness?: number;
      best_formula?: string;
      stream_url?: string;
      history?: Array<{
        generation: number;
        max_generations?: number;
        best_fitness: number;
        best_formula: string;
      }>;
    }) => {
      // 1. Prioritize live SSE streaming if stream_url provided
      if (resp.stream_url) {
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }

        const activeSessionId = String(resp.session_id ?? resp.job_id ?? 'alpha-discovery');
        setDiscoveryState({
          sessionId: activeSessionId,
          generation: 0,
          maxGenerations: 10,
          progress: 0,
          bestFitness: 0,
          bestFormula: '',
          status: 'RUNNING',
          history: [],
        });

        const sseUrl = `${API_BASE}${resp.stream_url}`;
        try {
          const es = new EventSource(sseUrl);
          eventSourceRef.current = es;

          es.onmessage = (e) => {
            try {
              const data: DiscoveryProgressEvent = JSON.parse(e.data);
              if (data.event_type === 'PING') return;

              setDiscoveryState((prev) => ({
                ...prev,
                generation: data.generation,
                maxGenerations: data.max_generations ?? prev.maxGenerations,
                progress: data.progress,
                bestFitness: data.best_fitness,
                bestFormula: data.best_formula,
                status: data.progress >= 100 || data.event_type === 'DISCOVERY_COMPLETED' ? 'COMPLETED' : 'RUNNING',
                history: [...prev.history.slice(-19), data],
              }));

              if (data.progress >= 100 || data.event_type === 'DISCOVERY_COMPLETED') {
                es.close();
                queryClient.invalidateQueries({ queryKey: ['alpha-arsenal'] });
              }
            } catch {
              // Malformed event payload
            }
          };

          es.onerror = () => {
            es.close();
            setDiscoveryState((prev) => ({
              ...prev,
              status: prev.progress >= 100 ? 'COMPLETED' : 'ERROR',
            }));
          };
        } catch {
          setDiscoveryState((prev) => ({ ...prev, status: 'ERROR' }));
        }
        return;
      }

      // 2. Synchronous fallback if direct history returned without stream_url
      if (resp.history && resp.history.length > 0) {
        const lastGen = resp.history[resp.history.length - 1];
        setDiscoveryState({
          sessionId: String(resp.job_id ?? resp.session_id ?? 'gp-job'),
          generation: lastGen.generation,
          maxGenerations: lastGen.max_generations ?? 10,
          progress: 100,
          bestFitness: resp.best_fitness ?? lastGen.best_fitness,
          bestFormula: resp.best_formula ?? lastGen.best_formula,
          status: 'COMPLETED',
          history: resp.history.map((h) => ({
            session_id: String(resp.job_id ?? resp.session_id ?? 'gp-job'),
            event_type: 'GENERATION_UPDATE',
            generation: h.generation,
            max_generations: h.max_generations ?? 10,
            progress: Math.round((h.generation / (h.max_generations ?? 10)) * 100),
            best_fitness: h.best_fitness,
            best_formula: h.best_formula,
            timestamp: new Date().toISOString(),
          })),
        });
        queryClient.invalidateQueries({ queryKey: ['alpha-arsenal'] });
        return;
      }

      const fallbackSessionId = String(resp.session_id ?? resp.job_id ?? 'alpha-discovery');
      setDiscoveryState({
        sessionId: fallbackSessionId,
        generation: 0,
        maxGenerations: 10,
        progress: 100,
        bestFitness: resp.best_fitness ?? 0,
        bestFormula: resp.best_formula ?? '',
        status: 'COMPLETED',
        history: [],
      });
    },
  });

  const handleEvaluate = useCallback(() => {
    if (!expression.trim()) return;
    evaluateMutation.mutate(expression);
  }, [expression, evaluateMutation]);

  const handleStartDiscovery = useCallback(
    (params: StartDiscoveryRequest = {}) => {
      startDiscoveryMutation.mutate({
        generations: params.generations || 10,
        population_size: params.population_size || 50,
        mutation_rate: params.mutation_rate || 0.15,
        crossover_rate: params.crossover_rate || 0.75,
        target_ic: params.target_ic || 0.04,
        target_ir: params.target_ir || 1.5,
      });
    },
    [startDiscoveryMutation]
  );

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return {
    expression,
    setExpression,
    targetUniverse,
    setTargetUniverse,
    selectedCategory,
    setSelectedCategory,
    selectedStatus,
    setSelectedStatus,
    searchQuery,
    setSearchQuery,
    selectedAlphaId,
    setSelectedAlphaId,
    arsenalSignals: (arsenalData?.signals as AlphaSignalItem[]) || [],
    totalArsenalCount: arsenalData?.total_available || 0,
    isArsenalLoading,
    refetchArsenal,
    decayProfile,
    isDecayLoading,
    evaluationResult: evaluateMutation.data as EvaluateExpressionResponse | undefined,
    isEvaluating: evaluateMutation.isPending,
    evaluateError: evaluateMutation.error,
    handleEvaluate,
    discoveryState,
    isDiscovering: startDiscoveryMutation.isPending || discoveryState.status === 'RUNNING',
    handleStartDiscovery,
  };
}
