import React, { useRef, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { API_BASE } from '../../api/client';

const invalid = (): never => { throw new Error('Execution data unavailable'); };
export const executionRecord = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : invalid();
export const executionNumber = (value: unknown, min = 0, max = 1e12): number =>
  typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max ? value : invalid();
export const executionText = (value: unknown): string =>
  typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value) ? value : invalid();
export const executionClock = (value: unknown): number => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d{1,6})?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)) return invalid();
  const clock = Date.parse(value) + Number(`0.${(/\.(\d+)/.exec(value)?.[1] ?? '').padEnd(3, '0').slice(3) || '0'}`);
  return Number.isFinite(clock) && new Date(`${value.slice(0, 10)}T00:00:00Z`).toISOString().slice(0, 10) === value.slice(0, 10) ? clock : invalid();
};

export async function requestExecutionData(path: string, signal: AbortSignal, method = 'GET'): Promise<unknown> {
  if (!/^\/api\/v1\/execution\/(status|start|stop|pause|resume|blotter|timeline|slippage-distribution|settlement-timeline)(\?as_of=[^&]+)?$/.test(path)) return invalid();
  try {
    const response = await fetch(`${API_BASE}${path}`, { signal, method, headers: { Accept: 'application/json' } });
    const reader = response.body?.getReader();
    if (!reader) return invalid();
    try {
      const cap = 1024 * 1024;
      if (!response.ok || signal.aborted || Number(response.headers.get('Content-Length')) > cap) return invalid();
      const bytes = new Uint8Array(cap);
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (signal.aborted) return invalid();
        if (done) break;
        if (!ArrayBuffer.isView(value) || value.BYTES_PER_ELEMENT !== 1 || value.byteLength > cap - size) return invalid();
        bytes.set(value, size);
        size += value.byteLength;
      }
      if (size >= 3 && bytes[0] === 239 && bytes[1] === 187 && bytes[2] === 191) return invalid();
      return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, size)));
    } catch {
      await reader.cancel().catch(() => undefined);
      return invalid();
    } finally {
      reader.releaseLock();
    }
  } catch {
    return invalid();
  }
}

export function validateDaemonStatus(value: unknown) {
  const row = executionRecord(value);
  if (!['STOPPED', 'RUNNING', 'PAUSED'].includes(row.state as string) || row.active !== (row.state === 'RUNNING') ||
      typeof row.workers_available !== 'boolean') return invalid();
  const processed = executionNumber(row.processed_orders_count);
  const active = executionNumber(row.active_orders_count, 0, processed);
  const workers = executionNumber(row.active_workers, 0, 5000);
  if (![processed, active, workers].every(Number.isInteger)) return invalid();
  if (row.last_heartbeat !== null && executionClock(row.last_heartbeat) > Date.now()) return invalid();
  return { state: row.state as string, uptime: executionNumber(row.uptime_seconds),
    pnl: executionNumber(row.daily_pnl_vnd, -1e12), processed, active, workers,
    workersAvailable: row.workers_available as boolean, mode: executionText(row.mode) };
}

export interface PaperDaemonPanelProps {
  status?: string;
  onRefresh?: () => void;
  onStateChange?: (newState: string) => void;
  autoPoll?: boolean;
}

// ponytail: explicit refresh only; streaming telemetry needs a backend subscription contract.
export const PaperDaemonPanel: React.FC<PaperDaemonPanelProps> = ({ onRefresh, onStateChange }) => {
  const mutationController = useRef<AbortController | null>(null);
  const actionPending = useRef(false);
  useEffect(() => () => mutationController.current?.abort(), []);
  const query = useQuery({
    queryKey: ['execution-daemon'],
    queryFn: async ({ signal }) => validateDaemonStatus(await requestExecutionData('/api/v1/execution/status', AbortSignal.any([signal, AbortSignal.timeout(10000)]))),
    retry: false, retryOnMount: false, refetchOnWindowFocus: false, refetchOnReconnect: false,
    enabled: (query) => query.state.status !== 'error', staleTime: Infinity,
  });
  const action = useMutation({
    mutationFn: async (name: string) => {
      const controller = new AbortController();
      mutationController.current = controller;
      return validateDaemonStatus(await requestExecutionData(`/api/v1/execution/${name}`, AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]), 'POST'));
    },
    retry: false,
    onSettled: () => { actionPending.current = false; },
    onSuccess: (data) => {
      if (mutationController.current?.signal.aborted) return;
      onStateChange?.(data.state);
      onRefresh?.();
      void query.refetch();
    },
  });
  const data = query.isError || action.isError ? undefined : query.data;
  const changeState = (name: string) => {
    if (!data || query.isFetching || actionPending.current) return;
    if (window.confirm(`Confirm paper daemon ${name}? A request timeout does not prove the action was cancelled.`)) {
      actionPending.current = true;
      action.mutate(name);
    }
  };
  return <section aria-label="Paper Trading Daemon" className="rounded-xl border border-white/10 bg-zinc-950 p-4 font-mono text-sm text-zinc-200">
    <h3 className="font-bold">Paper Trading Daemon</h3>
    <p data-testid="daemon-state" role={query.isError || action.isError ? 'alert' : 'status'}>
      {query.isError || action.isError ? 'Daemon unavailable. Refresh status before another action.' : data?.state ?? 'Loading daemon status…'}
    </p>
    {data && <dl className="flex flex-wrap gap-4 py-3">
      <div><dt>Mode</dt><dd>{data.mode}</dd></div>
      <div><dt>Daemon Uptime</dt><dd>{data.uptime.toLocaleString()} s</dd></div>
      <div><dt>Daily Simulated PnL</dt><dd>{data.pnl.toLocaleString()} VND</dd></div>
      <div><dt>Active Workers</dt><dd>{data.workersAvailable ? data.workers : 'Unavailable'}</dd></div>
      <div><dt>Processed Orders</dt><dd>{data.processed}</dd></div>
    </dl>}
    <div className="flex flex-wrap gap-2">
      {data && (data.state === 'STOPPED' ? ['start'] : data.state === 'PAUSED' ? ['resume', 'stop'] : ['pause', 'stop']).map((name) =>
        <button key={name} disabled={query.isFetching || action.isPending} onClick={() => changeState(name)} className="min-h-11 rounded border border-zinc-500 px-3 capitalize focus-visible:outline-2 disabled:opacity-50">{name}</button>)}
      <button disabled={query.isFetching || action.isPending} onClick={() => { action.reset(); void query.refetch(); }} className="min-h-11 rounded border border-zinc-500 px-3 focus-visible:outline-2 disabled:opacity-50">Refresh daemon status</button>
    </div>
  </section>;
};
