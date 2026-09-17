import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { API_BASE, StreamUpdate } from '../api/client';
import { useUiStore } from '../store/uiStore';

export interface UseRealtimeStreamOptions {
  enabled?: boolean;
  onUpdate?: (update: StreamUpdate) => void;
}

export function useRealtimeStream(options: UseRealtimeStreamOptions = {}) {
  const { enabled = true, onUpdate } = options;
  const queryClient = useQueryClient();
  const [latestUpdate, setLatestUpdate] = useState<StreamUpdate | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const setStreamingConnected = useUiStore((state) => state.setStreamingConnected);
  const setLastStreamMessageTimestamp = useUiStore((state) => state.setLastStreamMessageTimestamp);

  useEffect(() => {
    if (!enabled) {
      setStreamingConnected(false);
      return;
    }

    const intervalId = window.setInterval(() => {
      // Periodic heartbeat keepalive checker
    }, 60000);

    const source = new EventSource(`${API_BASE}/sse/v1/events/system`);
    source.onopen = () => {
      setIsConnected(true);
      setStreamingConnected(true);
    };

    const handleEventMessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as Record<string, unknown>;
        if (typeof payload.timestamp !== 'string') return;
        const update: StreamUpdate = { type: 'ALERT', timestamp: payload.timestamp, data: payload };
        setLatestUpdate(update);
        setLastStreamMessageTimestamp(payload.timestamp);
        void queryClient.invalidateQueries({ refetchType: 'active' });
        onUpdate?.(update);
      } catch {
        return;
      }
    };

    source.onmessage = handleEventMessage;
    source.addEventListener('status', handleEventMessage);
    source.addEventListener('progress', handleEventMessage);
    source.addEventListener('complete', handleEventMessage);
    source.addEventListener('error', handleEventMessage);
    source.addEventListener('artifact', handleEventMessage);

    source.onerror = () => {
      setIsConnected(false);
      setStreamingConnected(false);
    };

    return () => {
      window.clearInterval(intervalId);
      source.removeEventListener('status', handleEventMessage);
      source.removeEventListener('progress', handleEventMessage);
      source.removeEventListener('complete', handleEventMessage);
      source.removeEventListener('error', handleEventMessage);
      source.removeEventListener('artifact', handleEventMessage);
      source.close();
      setIsConnected(false);
      setStreamingConnected(false);
    };
  }, [enabled, onUpdate, queryClient, setStreamingConnected, setLastStreamMessageTimestamp]);

  return {
    latestUpdate,
    isConnected
  };
}
