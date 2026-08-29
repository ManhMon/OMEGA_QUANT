import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient, API_BASE, PipelineRunParams, PipelineStreamEvent } from '../api/client';

export interface PipelineTaskHistoryItem {
  jobId: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  progress: number;
  stage: string;
  timestamp: string;
  universe: string[];
  metrics?: Record<string, any>;
  events: PipelineStreamEvent[];
  retryOf?: string;
}

export function usePipelineRunner() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [currentProgress, setCurrentProgress] = useState<number>(0);
  const [currentStage, setCurrentStage] = useState<string>('IDLE');
  const [currentStatus, setCurrentStatus] = useState<'IDLE' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'>('IDLE');
  const [liveTelemetry, setLiveTelemetry] = useState<Record<string, any> | null>(null);
  const [streamLogs, setStreamLogs] = useState<PipelineStreamEvent[]>([]);
  const [taskHistory, setTaskHistory] = useState<PipelineTaskHistoryItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<'IDLE' | 'CONNECTED' | 'RECONNECTING' | 'EXHAUSTED'>('IDLE');
  const [retryable, setRetryable] = useState(false);
  const [receiptValidated, setReceiptValidated] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const generationRef = useRef(0);
  const lastRequestRef = useRef<PipelineRunParams | null>(null);
  const retryingRef = useRef(false);

  // Stop current SSE stream
  const closeStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  // Connect to SSE stream for a job_id
  const connectToStream = useCallback((jobId: string, universe: string[] = [], streamUrl?: string) => {
    closeStream();
    const generation = ++generationRef.current;
    const es = new EventSource(streamUrl ? `${API_BASE}${streamUrl}` : `${API_BASE}/sse/v1/pipeline/${encodeURIComponent(jobId)}/stream`);
    eventSourceRef.current = es;
    setConnectionState('CONNECTED');

    // Create or initialize task entry in history
    setTaskHistory((prev) => {
      const existing = prev.find((t) => t.jobId === jobId);
      if (existing) return prev;
      return [
        {
          jobId,
          status: 'QUEUED',
          progress: 0,
          stage: 'INIT',
          timestamp: new Date().toISOString(),
          universe,
          events: [],
        },
        ...prev,
      ];
    });

    es.onmessage = (event) => {
      try {
        const parsed: PipelineStreamEvent = JSON.parse(event.data);
        if (generation !== generationRef.current || eventSourceRef.current !== es) return;
        const jId = parsed.job_id || parsed.task_id;
        if (jId !== jobId) return;

        if (parsed.event_type !== 'PING') {
          setStreamLogs((prev) => [...prev.slice(-200), parsed]);
        }

        if (typeof parsed.progress === 'number') {
          setCurrentProgress(parsed.progress);
        }

        if (parsed.stage) {
          setCurrentStage(parsed.stage);
        }

        let newStatus: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' = 'RUNNING';
        const receipt = parsed.payload?.receipt as { task_id?: string; status?: string; request_fingerprint?: string; output_sha256?: string } | undefined;
        const validReceipt = parsed.event_type === 'COMPLETE' && receipt?.task_id === jobId && receipt.status === 'COMPLETED' && Boolean(receipt.request_fingerprint && receipt.output_sha256);
        if (parsed.event_type === 'ERROR') {
          newStatus = 'FAILED';
        } else if (parsed.event_type === 'CANCELLED') {
          newStatus = 'CANCELLED';
        } else if (validReceipt) {
          newStatus = 'COMPLETED';
          setReceiptValidated(true);
        } else if (parsed.event_type === 'COMPLETE') {
          newStatus = 'FAILED';
          setError('Completion receipt is missing or invalid.');
        }
        setCurrentStatus(newStatus);

        if (parsed.payload && Object.keys(parsed.payload).length > 0) {
          setLiveTelemetry((prev) => ({ ...prev, ...parsed.payload }));
        }

        // Update taskHistory
        setTaskHistory((prev) =>
          prev.map((item) => {
            if (item.jobId === jId) {
              return {
                ...item,
                status: newStatus,
                progress: typeof parsed.progress === 'number' ? parsed.progress : item.progress,
                stage: parsed.stage || item.stage,
                metrics: parsed.payload?.metrics || parsed.payload || item.metrics,
                events: parsed.event_type !== 'PING' ? [...item.events.slice(-100), parsed] : item.events,
              };
            }
            return item;
          })
        );

        if (newStatus === 'COMPLETED' || newStatus === 'FAILED' || newStatus === 'CANCELLED') {
          setRetryable(Boolean(parsed.payload?.retryable));
          closeStream();
        }
      } catch (err) {
        console.error('SSE JSON parse error:', err);
      }
    };

    es.onerror = () => {
      if (generation !== generationRef.current || eventSourceRef.current !== es) return;
      closeStream();
      setConnectionState('EXHAUSTED');
      setCurrentStatus('FAILED');
      setRetryable(true);
      setError('Telemetry connection lost before validated completion. Retry creates a new task.');
    };
  }, [closeStream]);

  // Dispatch a new in-process pipeline run
  const runPipeline = useCallback(
    async (params: PipelineRunParams = {}) => {
      setIsSubmitting(true);
      setError(null);
      try {
        const resp = await apiClient.triggerPipelineRun(params);
        lastRequestRef.current = structuredClone(params);
        setActiveJobId(resp.job_id);
        setCurrentProgress(0);
        setCurrentStage('DATA_INGEST');
        setCurrentStatus('RUNNING');
        setStreamLogs([]);
        setLiveTelemetry(null);
        setReceiptValidated(false);
        setRetryable(false);

        connectToStream(resp.job_id, params.universe || [], resp.stream_url);
        return resp;
      } catch (err: any) {
        const msg = err?.message || 'Failed to dispatch pipeline run';
        setError(msg);
        setCurrentStatus('FAILED');
        throw err;
      } finally {
        setIsSubmitting(false);
      }
    },
    [connectToStream]
  );

  const retryPipeline = useCallback(async () => {
    if (retryingRef.current || !lastRequestRef.current || !retryable) return;
    retryingRef.current = true;
    setConnectionState('RECONNECTING');
    try {
      await runPipeline(structuredClone(lastRequestRef.current));
    } finally {
      retryingRef.current = false;
    }
  }, [retryable, runPipeline]);

  // Cancel an active job
  const cancelJob = useCallback(
    async (jobId?: string) => {
      const targetId = jobId || activeJobId;
      if (!targetId) return;

      try {
        await apiClient.cancelPipelineRun(targetId);
        setCurrentStatus('CANCELLED');
        closeStream();
        setTaskHistory((prev) =>
          prev.map((item) => (item.jobId === targetId ? { ...item, status: 'CANCELLED' } : item))
        );
      } catch (err: any) {
        console.error('Cancel job failed:', err);
      }
    },
    [activeJobId, closeStream]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      closeStream();
    };
  }, [closeStream]);

  return {
    activeJobId,
    currentProgress,
    currentStage,
    currentStatus,
    liveTelemetry,
    streamLogs,
    taskHistory,
    isSubmitting,
    error,
    connectionState,
    retryable,
    receiptValidated,
    runPipeline,
    cancelJob,
    retryPipeline,
    connectToStream,
    setActiveJobId,
  };
}
