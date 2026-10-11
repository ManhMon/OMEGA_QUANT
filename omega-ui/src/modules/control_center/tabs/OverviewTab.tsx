import { useEffect, useRef, useState } from 'react';
import { advancedQuantApi, formatAlphaMetric, validateOperationsBreaker, validateResourceGovernor, validateSystemTelemetry } from '../../../api/advancedQuant';
import type { OperationsCircuitBreakerResponse, ResourceGovernorStateResponse, SystemTelemetryResponse } from '../../../api/advancedQuant';
import { useUiStore } from '../../../store/uiStore';
import type { OverviewTabProps } from '../controlCenterTypes';

export function OverviewTab({ activeTasks, isKillSwitchEngaged, onOpenOps, onKillSwitch, onBreakerObservation }: OverviewTabProps) {
  const [governor, setGovernor] = useState<ResourceGovernorStateResponse | null>(null);
  const [telemetry, setTelemetry] = useState<SystemTelemetryResponse | null>(null);
  const [breaker, setBreaker] = useState<OperationsCircuitBreakerResponse | null>(null);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const addToast = useUiStore((state) => state.addToast);
  const generation = useRef(0), request = useRef<AbortController | null>(null), operation = useRef(false);

  async function refresh() {
    if (operation.current) return;
    operation.current = true;
    const controller = new AbortController(), current = ++generation.current;
    request.current?.abort(); request.current = controller;
    setLoading(true); setErrors([]); setGovernor(null); setTelemetry(null); setBreaker(null); onBreakerObservation?.(null);
    const live = () => !controller.signal.aborted && current === generation.current;
    await Promise.all([
      advancedQuantApi.getSystemTelemetry(controller.signal).then((data) => { if (live()) setTelemetry(validateSystemTelemetry(data)); }).catch(() => { if (live()) setErrors((prior) => [...prior, 'System telemetry unavailable.']); }),
      advancedQuantApi.getOperationsCircuitBreaker(controller.signal).then((data) => { if (live()) { const valid = validateOperationsBreaker(data); setBreaker(valid); onBreakerObservation?.(valid); } }).catch(() => { if (live()) setErrors((prior) => [...prior, 'Circuit breaker observation unavailable.']); }),
      advancedQuantApi.getResourceGovernor(controller.signal).then((data) => { if (live()) setGovernor(validateResourceGovernor(data)); }).catch(() => { if (live()) setErrors((prior) => [...prior, 'Governor telemetry unavailable.']); }),
    ]);
    if (live()) { operation.current = false; setLoading(false); }
  }
  useEffect(() => {
    void refresh();
    return () => { ++generation.current; request.current?.abort(); operation.current = false; onBreakerObservation?.(null); };
  }, [onBreakerObservation]);

  const toggleGovernorMode = async () => {
    if (!governor || operation.current) return;
    operation.current = true; setIsUpdatingGovernor(true);
    const controller = new AbortController(), current = ++generation.current;
    request.current = controller;
    const live = () => !controller.signal.aborted && current === generation.current;
    try {
      const data = await advancedQuantApi.updateResourceGovernor({ mode: governor.mode === 'COPILOT' ? 'MANUAL' : 'COPILOT' }, controller.signal);
      if (live()) setGovernor(validateResourceGovernor(data));
    } catch {
      if (live()) {
        setGovernor(null);
        const message = 'Governor update outcome unknown. Refresh operations before another update.';
        setErrors((prior) => [...prior, message]);
        addToast({ type: 'error', title: 'Governor update failed', message });
      }
    } finally { if (live()) { operation.current = false; setIsUpdatingGovernor(false); } }
  };
  const buttonClass = 'min-h-11 rounded border px-3 py-2 text-xs font-bold focus-visible:outline-2 focus-visible:outline-cyan-300 disabled:opacity-50';
  return <section aria-label="Operations observations" aria-busy={loading || isUpdatingGovernor} className="min-w-0 space-y-3">
    <div className="grid gap-3 sm:grid-cols-3"><Metric label="Governor" value={governor?.mode ?? 'UNAVAILABLE'} /><Metric label="Workers (governor policy)" value={governor ? `${governor.active_workers}/${governor.target_concurrency}` : '--'} /><Metric label="Active tasks" value={String(activeTasks.filter((task) => task.status === 'RUNNING').length)} /></div>
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={!governor || loading || isUpdatingGovernor} className={`${buttonClass} border-emerald-400 text-emerald-300`} onClick={() => void toggleGovernorMode()}>{isUpdatingGovernor ? 'UPDATING GOVERNOR' : governor?.mode === 'COPILOT' ? 'SWITCH TO MANUAL' : 'SWITCH TO COPILOT'}</button>
      <button type="button" disabled={loading || isUpdatingGovernor} className={`${buttonClass} border-white/20 text-zinc-100`} onClick={() => void refresh()}>REFRESH OPERATIONS</button>
      <button type="button" className={`${buttonClass} border-cyan-400 text-cyan-300`} onClick={onOpenOps}>OPEN OPS DRAWER</button>
      <button type="button" disabled={isKillSwitchEngaged || breaker?.circuit_broken === true} className={`${buttonClass} border-rose-500 text-rose-300`} onClick={onKillSwitch}>{isKillSwitchEngaged || breaker?.circuit_broken ? 'SYSTEM HALTED' : 'EMERGENCY HALT'}</button>
    </div>
    {loading && <p role="status" className="text-sm text-zinc-300">Loading operations observations…</p>}
    {errors.length > 0 && <div role="alert" className="rounded border border-rose-400/40 p-3 text-sm text-zinc-100">{errors.map((error) => <p key={error}>{error}</p>)}</div>}
    <div className="rounded-lg border border-white/10 p-4 text-sm text-zinc-100">
      <h2 className="font-bold">Circuit breaker</h2>
      <p role="status">{breaker ? `Observed state: ${breaker.state}` : 'UNAVAILABLE — halt state unknown'}</p>
      {breaker && <><p className="break-words">Observed: {breaker.as_of} · Available: {breaker.available_at}</p>{breaker.reasons.map((reason) => <p key={reason}>{reason}</p>)}{breaker.triggered_at && <p className="break-words">Triggered: {breaker.triggered_at}</p>}</>}
      <p className="text-zinc-300">Current observation only; not historical/PIT evidence. No reset control.</p>
    </div>
    <div className="rounded-lg border border-white/10 p-4 text-sm text-zinc-100">
      <h2 className="font-bold">System telemetry</h2>
      <p className="break-words text-zinc-300">{telemetry ? `Observed: ${telemetry.as_of} · Available: ${telemetry.available_at}` : 'UNAVAILABLE'}</p>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        <Reading label="CPU usage (%)" value={formatAlphaMetric(telemetry?.cpu_usage_pct)} />
        <Reading label="Memory usage (MiB)" value={formatAlphaMetric(telemetry?.memory_usage_mb)} />
        <Reading label="Memory usage (%)" value={formatAlphaMetric(telemetry?.memory_usage_pct)} />
        <Reading label="Disk read (bytes since boot)" value={telemetry?.io_read_bytes?.toLocaleString() ?? '--'} />
        <Reading label="Disk write (bytes since boot)" value={telemetry?.io_write_bytes?.toLocaleString() ?? '--'} />
        <Reading label="IPC queue (queued jobs)" value={telemetry?.ipc_queue_depth?.toLocaleString() ?? '--'} />
        <Reading label="GPU usage (%)" value={formatAlphaMetric(telemetry?.gpu_telemetry?.usage_pct)} />
        <Reading label="GPU memory (MiB)" value={formatAlphaMetric(telemetry?.gpu_telemetry?.memory_usage_mb)} />
      </dl>
      <p className="mt-3 text-zinc-300">Missing measurements: --. Disk counters are cumulative, not throughput. Current-only observation; provenance digest is not authenticated lineage.</p>
    </div>
    {governor && <p className="break-words text-sm text-zinc-300">Governor policy revision {governor.version} · Updated: {governor.updated_at}. Governor load/memory are policy summaries, not measured system telemetry.</p>}
  </section>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="min-w-0 rounded-lg border border-white/10 bg-zinc-900/80 p-4 font-mono"><p className="text-xs uppercase text-zinc-400">{label}</p><p className="mt-1 break-words text-lg font-bold text-zinc-100">{value}</p></div>; }
function Reading({ label, value }: { label: string; value: string }) { return <div className="min-w-0"><dt className="text-zinc-300">{label}</dt><dd className="break-words font-bold text-zinc-100">{value}</dd></div>; }
