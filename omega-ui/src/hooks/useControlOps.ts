import { useCallback, useEffect, useRef } from 'react';
import {
  apiClient,
  API_BASE,
  IngestDataParams,
  ComputeAlphasParams,
  OptimizePortfolioParams,
  RunBacktestParams,
  KillSwitchParams,
  TaskProgressEvent,
  ControlTaskResponse,
  KillSwitchResponse
} from '../api/client';
import { useUiStore, ActiveTask } from '../store/uiStore';

export type { ActiveTask };

export function useControlOps() {
  const tasks = useUiStore((state) => state.tasks);
  const isDrawerOpen = useUiStore((state) => state.isOpsDrawerOpen);
  const setIsDrawerOpen = useUiStore((state) => state.setIsOpsDrawerOpen);
  const selectedTaskId = useUiStore((state) => state.selectedTaskId);
  const setSelectedTaskId = useUiStore((state) => state.setSelectedTaskId);
  const isTotpModalOpen = useUiStore((state) => state.isTotpModalOpen);
  const setIsTotpModalOpen = useUiStore((state) => state.setIsTotpModalOpen);
  const isKillSwitchEngaged = useUiStore((state) => state.isKillSwitchEngaged);
  const setIsKillSwitchEngaged = useUiStore((state) => state.setIsKillSwitchEngaged);
  const upsertTask = useUiStore((state) => state.upsertTask);
  const updateTaskProgress = useUiStore((state) => state.updateTaskProgress);
  const addToast = useUiStore((state) => state.addToast);
  const streams = useRef(new Map<string, { source: EventSource; generation: number }>());
  const generation = useRef(0);

  useEffect(() => () => {
    streams.current.forEach(({ source }) => source.close());
    streams.current.clear();
  }, []);

  const connectTaskSse = useCallback((taskId: string, initialType: ActiveTask['taskType']) => {
    const streamGeneration = ++generation.current;
    const eventSource = new EventSource(`${API_BASE}/sse/v1/tasks/${encodeURIComponent(taskId)}/progress`);
    streams.current.set(taskId, { source: eventSource, generation: streamGeneration });

    upsertTask({
      taskId,
      taskType: initialType,
      progress: 0,
      stage: 'INITIALIZING',
      message: 'Connecting to telemetry pipeline...',
      status: 'RUNNING',
      startedAt: new Date().toISOString()
    });
    setIsDrawerOpen(true);
    setSelectedTaskId(taskId);

    eventSource.onmessage = (event) => {
      try {
        const data: TaskProgressEvent = JSON.parse(event.data);
        if (streams.current.get(taskId)?.generation !== streamGeneration || (data.task_id && data.task_id !== taskId)) return;
        updateTaskProgress(taskId, data);

        const receipt = data.payload?.receipt as { task_id?: string; status?: string; request_fingerprint?: string; output_sha256?: string } | undefined;
        const completed = data.event_type === 'COMPLETE' && receipt?.task_id === taskId && receipt.status === 'COMPLETED' && Boolean(receipt.request_fingerprint && receipt.output_sha256);
        if (completed || data.event_type === 'ERROR' || data.event_type === 'CANCELLED') {
          eventSource.close();
          streams.current.delete(taskId);
          if (completed) addToast({
            type: 'success',
            title: `Task Completed: ${initialType}`,
            message: data.message || `Task ${taskId} finished successfully.`
          });
        }
      } catch (err) {
        console.error('Failed to parse SSE task update:', err);
      }
    };

    eventSource.onerror = () => {
      if (streams.current.get(taskId)?.generation !== streamGeneration) return;
      eventSource.close();
      streams.current.delete(taskId);
      updateTaskProgress(taskId, { event_type: 'ERROR', stage: 'CONNECTION_LOST', message: 'Telemetry connection lost. Retry creates a new task.', payload: { error_code: 'SSE_DISCONNECTED', retryable: true } });
      addToast({ type: 'error', title: `Task connection lost: ${initialType}`, message: 'No completion was received. Retry the operation.' });
    };
  }, [upsertTask, updateTaskProgress, setIsDrawerOpen, setSelectedTaskId, addToast]);

  const triggerIngestData = async (params: IngestDataParams = {}): Promise<ControlTaskResponse> => {
    addToast({
      type: 'info',
      title: 'Ingest Data Dispatched',
      message: `Sources: ${(params.sources || ['vci']).join(', ').toUpperCase()}`
    });
    const res = await apiClient.ingestData(params);
    connectTaskSse(res.task_id, 'DATA_INGESTION');
    return res;
  };

  const triggerComputeAlphas = async (params: ComputeAlphasParams = {}): Promise<ControlTaskResponse> => {
    addToast({
      type: 'info',
      title: 'Alpha Computation Dispatched',
      message: `Universe: ${(params.universe || []).join(', ') || 'default'} | Family: MOMENTUM`
    });
    const res = await apiClient.computeAlphas(params);
    connectTaskSse(res.task_id, 'ALPHA_COMPUTATION');
    return res;
  };

  const triggerOptimizePortfolio = async (params: OptimizePortfolioParams = {}): Promise<ControlTaskResponse> => {
    addToast({
      type: 'info',
      title: 'Portfolio Optimization Dispatched',
      message: `Objective: ${params.objective || 'MAX_SHARPE'} | Max Weight: ${params.max_single_weight ?? 0.15}`
    });
    const res = await apiClient.optimizePortfolio(params);
    connectTaskSse(res.task_id, 'PORTFOLIO_OPTIMIZATION');
    return res;
  };

  const triggerRunBacktest = async (params: RunBacktestParams = {}): Promise<ControlTaskResponse> => {
    addToast({
      type: 'info',
      title: 'Walk-Forward Backtest Dispatched',
      message: `Strategy: ${params.strategy_id || 'ALPHA_HRP_V2'} from ${params.start_date || '2020-01-01'}`
    });
    const res = await apiClient.runBacktest(params);
    connectTaskSse(res.task_id, 'STRATEGY_BACKTEST');
    return res;
  };

  const triggerKillSwitch = async (params: KillSwitchParams): Promise<KillSwitchResponse> => {
    const res = await apiClient.killSwitch(params);
    setIsKillSwitchEngaged(true);
    addToast({
      type: 'warning',
      title: 'Emergency Kill Switch Engaged',
      message: 'All OMS gateways halted and active orders cancelled.'
    });
    return res;
  };

  return {
    tasks,
    activeTaskList: Object.values(tasks).sort((a, b) => b.startedAt.localeCompare(a.startedAt)),
    isDrawerOpen,
    setIsDrawerOpen,
    selectedTaskId,
    setSelectedTaskId,
    isTotpModalOpen,
    setIsTotpModalOpen,
    isKillSwitchEngaged,
    triggerIngestData,
    triggerComputeAlphas,
    triggerOptimizePortfolio,
    triggerRunBacktest,
    triggerKillSwitch
  };
}
