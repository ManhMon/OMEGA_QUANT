import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  advancedQuantApi, AlphaDiscoveryRequest, AlphaDiscoveryEvent,
  validateAlphaDiscoveryEvent, alphaDiscoveryUrl, alphaErrorMessage,
} from '../api/advancedQuant';

export interface DiscoverySessionState {
  sessionId: string;
  generation: number;
  maxGenerations: number;
  progress: number;
  bestFitness: number | null;
  bestFormula: string;
  status: 'IDLE' | 'RUNNING' | 'COMPLETED' | 'ERROR';
  history: AlphaDiscoveryEvent[];
}

const initialDiscovery: DiscoverySessionState = {
  sessionId: '', generation: 0, maxGenerations: 10, progress: 0,
  bestFitness: null, bestFormula: '', status: 'IDLE', history: [],
};

export function useAlphaFactory() {
  const queryClient = useQueryClient();
  const [expression, setExpression] = useState('ts_rank(close, 10)');
  const [targetUniverse, setTargetUniverse] = useState('VN703');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAlphaId, setSelectedAlphaId] = useState('ALPHA_0001_VNM');
  const [discoveryState, setDiscoveryState] = useState(initialDiscovery);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const discoveryController = useRef<AbortController | null>(null);
  const evaluationController = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  const arsenal = useQuery({
    queryKey: ['alpha-arsenal', selectedCategory, selectedStatus, searchQuery],
    queryFn: ({ signal }) => advancedQuantApi.getAlphaArsenalSignals({
      category: selectedCategory || undefined, status: selectedStatus || undefined,
      search: searchQuery || undefined, limit: 703,
    }, signal),
    staleTime: 60000, retry: false,
  });
  const decay = useQuery({
    queryKey: ['alpha-decay-profile', selectedAlphaId],
    queryFn: ({ signal }) => advancedQuantApi.getAlphaDecayProfile(selectedAlphaId, signal),
    enabled: Boolean(selectedAlphaId), staleTime: 30000, retry: false,
  });

  const evaluateMutation = useMutation({
    mutationFn: ({ expr, universe, controller }: { expr: string; universe: string; controller: AbortController }) => {
      const cutoff = new Date().toISOString();
      return advancedQuantApi.evaluateAlphaAst({ expression: expr, universe, as_of: cutoff, pit_cutoff: cutoff }, controller.signal);
    },
    retry: false,
  });
  const handleEvaluate = useCallback(() => {
    if (!expression.trim()) return;
    evaluationController.current?.abort();
    const controller = new AbortController();
    evaluationController.current = controller;
    evaluateMutation.mutate({ expr: expression.trim(), universe: targetUniverse, controller });
  }, [expression, targetUniverse, evaluateMutation]);
  useEffect(() => {
    evaluationController.current?.abort();
    evaluateMutation.reset();
  }, [expression, targetUniverse]);

  const startDiscoveryMutation = useMutation({
    mutationFn: ({ params, controller }: { params: AlphaDiscoveryRequest; controller: AbortController }) =>
      advancedQuantApi.startAlphaDiscovery(params, controller.signal),
    retry: false,
    onSuccess: (resp, { controller }) => {
      if (!mounted.current || controller.signal.aborted) return;
      const sessionId = resp.session_id ?? resp.job_id;
      const fail = () => {
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        setDiscoveryState((prev) => ({ ...prev, status: 'ERROR' }));
        setDiscoveryError('Discovery failed. Retry with available data.');
      };
      if (resp.stream_url) {
        try {
          const es = new EventSource(alphaDiscoveryUrl(resp.stream_url, sessionId));
          eventSourceRef.current = es;
          setDiscoveryState({ ...initialDiscovery, sessionId, maxGenerations: resp.generations, status: 'RUNNING' });
          let generation = 0;
          let progress = 0;
          es.onmessage = (event) => {
            if (!mounted.current || controller.signal.aborted || eventSourceRef.current !== es) return;
            try {
              if (event.data.length > 65536) throw new Error('INVALID_ALPHA_EVENT');
              const data = validateAlphaDiscoveryEvent(JSON.parse(event.data), sessionId);
              if (data.event_type === 'PING') return;
              if (data.event_type === 'DISCOVERY_FAILED') { fail(); return; }
              if (data.generation < generation || data.progress < progress || data.max_generations !== resp.generations) throw new Error('INVALID_ALPHA_EVENT');
              generation = data.generation;
              progress = data.progress;
              const completed = data.event_type === 'DISCOVERY_COMPLETED';
              setDiscoveryState((prev) => ({
                sessionId, generation, maxGenerations: data.max_generations, progress,
                bestFitness: data.best_formula ? data.best_fitness : null,
                bestFormula: data.best_formula, status: completed ? 'COMPLETED' : 'RUNNING',
                history: [...prev.history.slice(-19), data],
              }));
              if (completed) {
                es.close(); eventSourceRef.current = null;
                queryClient.invalidateQueries({ queryKey: ['alpha-arsenal'] });
              }
            } catch { fail(); }
          };
          es.onerror = () => {
            if (eventSourceRef.current === es && !controller.signal.aborted && mounted.current) fail();
          };
        } catch { fail(); }
        return;
      }
      const last = resp.history.at(-1);
      if (!last || last.generation !== resp.generations) { fail(); return; }
      setDiscoveryState({
        sessionId, generation: last.generation, maxGenerations: resp.generations, progress: 100,
        bestFitness: resp.best_fitness, bestFormula: resp.best_formula, status: 'COMPLETED',
        history: resp.history.slice(-20).map((h) => ({
          ...h, session_id: sessionId, event_type: 'GENERATION_UPDATE',
          progress: h.generation / resp.generations * 100, timestamp: new Date().toISOString(),
        })),
      });
      queryClient.invalidateQueries({ queryKey: ['alpha-arsenal'] });
    },
    onError: (error, { controller }) => {
      if (!mounted.current || controller.signal.aborted) return;
      setDiscoveryState((prev) => ({ ...prev, status: 'ERROR' }));
      setDiscoveryError(alphaErrorMessage(error));
    },
  });
  const handleStartDiscovery = useCallback((params: AlphaDiscoveryRequest = {}) => {
    discoveryController.current?.abort();
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    const controller = new AbortController();
    discoveryController.current = controller;
    setDiscoveryError(null);
    setDiscoveryState(initialDiscovery);
    startDiscoveryMutation.mutate({ params, controller });
  }, [startDiscoveryMutation]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      eventSourceRef.current?.close();
      discoveryController.current?.abort();
      evaluationController.current?.abort();
    };
  }, []);

  return {
    expression, setExpression, targetUniverse, setTargetUniverse,
    selectedCategory, setSelectedCategory, selectedStatus, setSelectedStatus,
    searchQuery, setSearchQuery, selectedAlphaId, setSelectedAlphaId,
    arsenalSignals: arsenal.isError ? [] : arsenal.data?.signals ?? [],
    totalArsenalCount: arsenal.isError ? null : arsenal.data?.total_available ?? null,
    isArsenalLoading: arsenal.isLoading, arsenalError: arsenal.error, refetchArsenal: arsenal.refetch,
    decayProfile: decay.isError ? undefined : decay.data, isDecayLoading: decay.isLoading, decayError: decay.error,
    evaluationResult: evaluateMutation.data, isEvaluating: evaluateMutation.isPending,
    evaluateError: evaluateMutation.error, handleEvaluate,
    discoveryState, discoveryError,
    isDiscovering: startDiscoveryMutation.isPending || discoveryState.status === 'RUNNING', handleStartDiscovery,
  };
}
