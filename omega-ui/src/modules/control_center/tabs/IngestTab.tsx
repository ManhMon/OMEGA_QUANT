import { useEffect, useRef, useState } from 'react';
import { apiClient, IngestSchedulerTelemetry, LakehouseDatasetMeta } from '../../../api/client';
import { useUiStore } from '../../../store/uiStore';
import type { IngestTabProps } from '../controlCenterTypes';

export function IngestTab({ activeTasks, runOperation, onIngest, onStopIngest, sources, setSources, forceRefresh, setForceRefresh }: IngestTabProps) {
  const [datasets, setDatasets] = useState<LakehouseDatasetMeta[]>([]); const [telemetry, setTelemetry] = useState<IngestSchedulerTelemetry | null>(null); const addToast = useUiStore((state) => state.addToast); const generation = useRef(0);
  const ingestRunning = activeTasks.some((task) => task.taskType === 'DATA_INGESTION' && ['RUNNING', 'PENDING', 'RECONNECTING'].includes(task.status));
  useEffect(() => {
    const controller = new AbortController(); const current = ++generation.current;
    const loadTelemetry = async () => {
       const results = await Promise.allSettled([apiClient.getLakehouseStatus(controller.signal), apiClient.getIngestSchedulerTelemetry(controller.signal, true)]);
      if (controller.signal.aborted || current !== generation.current) return;
      const [lakehouse, scheduler] = results;
      if (lakehouse.status === 'fulfilled') setDatasets(parseLakehouseDatasets(lakehouse.value));
      if (scheduler.status === 'fulfilled') setTelemetry(scheduler.value);
      const failed = results.find((result) => result.status === 'rejected');
      if (failed?.status === 'rejected') addToast({ type: 'error', title: 'Ingest telemetry failed', message: failed.reason instanceof Error ? failed.reason.message : 'Unexpected telemetry error.' });
    };
    void loadTelemetry().catch((error) => { if (!controller.signal.aborted && current === generation.current) addToast({ type: 'error', title: 'Ingest telemetry failed', message: error instanceof Error ? error.message : 'Unexpected telemetry error.' }); });
     return () => controller.abort();
  }, [addToast, ingestRunning]);
  const toggleSource = (source: string) => setSources(sources.includes(source) ? sources.filter((item) => item !== source) : [...sources, source]);
  return <section className="space-y-3 font-mono"><div className="flex flex-wrap gap-2">{['vci', 'kbs', 'tcbs', 'macro', 'news'].map((source) => <button key={source} aria-pressed={sources.includes(source)} className={`rounded border px-2 py-1 text-xs ${sources.includes(source) ? 'border-emerald-400 text-emerald-300' : 'border-white/10 text-zinc-500'}`} onClick={() => toggleSource(source)}>{source.toUpperCase()}</button>)}<label className="text-xs text-zinc-400"><input checked={forceRefresh} onChange={(event) => setForceRefresh(event.target.checked)} type="checkbox" /> FORCE REFRESH</label></div><div className="flex gap-2"><button className="rounded bg-emerald-500 px-3 py-2 text-xs font-bold text-zinc-950" onClick={() => void runOperation('Ingest', () => onIngest({ sources, force_refresh: forceRefresh }))}>DISPATCH INGEST</button><button disabled={!ingestRunning} className="rounded border border-rose-500 px-3 py-2 text-xs font-bold text-rose-300 disabled:opacity-50" onClick={() => void runOperation('Stop ingest', onStopIngest)}>STOP INGEST</button></div>{telemetry && <div aria-live="polite" className="rounded border border-white/10 p-3 text-xs"><div className="flex flex-wrap justify-between gap-2 text-zinc-400"><span>SCHEDULER {telemetry.status}</span><span>ACTIVE {telemetry.active_feed?.toUpperCase() ?? '--'}</span><span>FAILOVER {telemetry.failover_ready ? 'READY' : 'UNAVAILABLE'}</span></div><div className="mt-2 flex flex-wrap gap-2">{Object.entries(telemetry.feed_health).map(([feed, health]) => <span key={feed} className={`rounded border px-2 py-1 ${health === 'ONLINE' ? 'border-emerald-400 text-emerald-300' : health === 'DEGRADED' || health === 'OFFLINE' ? 'border-rose-400 text-rose-300' : 'border-white/10 text-zinc-400'}`}>{feed.toUpperCase()} {health}</span>)}</div><div className="mt-2 text-zinc-500">LAST {telemetry.last_sync_timestamp ?? '--'} | WORKERS {telemetry.active_workers}</div></div>}<div className="overflow-x-auto rounded border border-white/10"><table className="w-full text-left text-xs"><thead><tr className="text-zinc-500"><th className="p-3">Dataset</th><th className="p-3">Freshness</th><th className="p-3">Rows</th></tr></thead><tbody>{datasets.map((dataset) => <tr key={dataset.id} className="border-t border-white/5"><td className="p-3">{dataset.file_name}</td><td className="p-3">{dataset.freshness_status}</td><td className="p-3">{Number.isFinite(dataset.total_rows) ? dataset.total_rows.toLocaleString() : '--'}</td></tr>)}</tbody></table></div></section>;
}

function parseLakehouseDatasets(response: unknown): LakehouseDatasetMeta[] {
  if (!response || typeof response !== 'object' || !Array.isArray((response as { datasets?: unknown }).datasets)) throw new Error('Invalid lakehouse telemetry response.');
  return (response as { datasets: unknown[] }).datasets.filter(isLakehouseDatasetMeta);
}

function isLakehouseDatasetMeta(dataset: unknown): dataset is LakehouseDatasetMeta {
  if (!dataset || typeof dataset !== 'object') return false;
  const value = dataset as Record<string, unknown>;
  return typeof value.id === 'string' && value.id.trim() !== '' && typeof value.file_name === 'string' && typeof value.freshness_status === 'string';
}
