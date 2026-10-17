import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { API_BASE, StreamUpdate } from '../api/client';
import { useUiStore } from '../store/uiStore';

export interface UseRealtimeStreamOptions {
  enabled?: boolean;
  onUpdate?: (update: StreamUpdate) => void;
}

const MAX_RETRIES = 3;
const CONNECTION_TIMEOUT_MS = 10000;
const EVENT_TYPES = ['status', 'progress', 'complete', 'error', 'artifact'];

export function useRealtimeStream(options: UseRealtimeStreamOptions = {}) {
  const { enabled = true, onUpdate } = options;
  const queryClient = useQueryClient();
  const [latestUpdate, setLatestUpdate] = useState<StreamUpdate | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isExhausted, setIsExhausted] = useState(false);
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  const setStreamingConnected = useUiStore((state) => state.setStreamingConnected);
  const setLastStreamMessageTimestamp = useUiStore((state) => state.setLastStreamMessageTimestamp);

  useEffect(() => {
    let disposed = false;
    let source: EventSource | null = null;
    let timer: number | undefined;
    let retries = 0;
    const connected = (value: boolean) => {
      setIsConnected(value);
      setStreamingConnected(value);
    };
    const stop = () => {
      window.clearTimeout(timer);
      timer = undefined;
      if (source) {
        source.onopen = null;
        source.onmessage = null;
        source.onerror = null;
        for (const type of EVENT_TYPES) source.removeEventListener(type, handleEventMessage);
        source.close();
        source = null;
      }
    };
    const handleEventMessage = (event: MessageEvent) => {
      if (disposed || event.currentTarget !== source) return;
      let payload: Record<string, unknown>;
      try { payload = JSON.parse(event.data) as Record<string, unknown>; }
      catch { return; }
      if (!payload || Array.isArray(payload) || typeof payload.timestamp !== 'string') return;
      const update: StreamUpdate = { type: 'ALERT', timestamp: payload.timestamp, data: payload };
      setLatestUpdate(update);
      setLastStreamMessageTimestamp(payload.timestamp);
      void queryClient.invalidateQueries({ refetchType: 'active' });
      onUpdateRef.current?.(update);
    };
    const fail = () => {
      stop();
      connected(false);
      if (retries === MAX_RETRIES) {
        setIsExhausted(true);
        return;
      }
      timer = window.setTimeout(connect, 1000 * 2 ** retries++);
    };
    const connect = () => {
      if (disposed) return;
      stop();
      try {
        const current = new EventSource(`${API_BASE}/sse/v1/events/system`);
        source = current;
        current.onopen = () => {
          if (disposed || source !== current) return;
          window.clearTimeout(timer);
          timer = undefined;
          connected(true);
        };
        current.onmessage = handleEventMessage;
        current.addEventListener('status', handleEventMessage);
        current.addEventListener('progress', handleEventMessage);
        current.addEventListener('complete', handleEventMessage);
        current.addEventListener('error', handleEventMessage);
        current.addEventListener('artifact', handleEventMessage);
        current.onerror = (event) => {
          if (disposed || source !== current || event instanceof MessageEvent) return;
          fail();
        };
        timer = window.setTimeout(() => {
          if (!disposed && source === current) fail();
        }, CONNECTION_TIMEOUT_MS);
      } catch { fail(); }
    };

    connected(false);
    setIsExhausted(false);
    if (enabled) connect();
    return () => {
      disposed = true;
      stop();
      connected(false);
    };
  }, [enabled, queryClient, setStreamingConnected, setLastStreamMessageTimestamp]);

  return { latestUpdate, isConnected, isExhausted };
}
