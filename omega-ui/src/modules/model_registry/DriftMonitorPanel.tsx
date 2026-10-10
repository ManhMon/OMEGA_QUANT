import React, { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE } from '../../api/client';
import {
  Activity,
  AlertTriangle,
  RotateCcw,
  Clock,
  ShieldCheck,
  ShieldAlert,
  Save,
  Layers,
} from 'lucide-react';
import {
  advancedQuantApi,
  DriftMonitorStatus,
  DriftScheduleRequest,
} from '../../api/advancedQuant';
import { useUiStore } from '../../store/uiStore';

const IDENTIFIER = /^[A-Za-z0-9_-]{1,128}$/;
const VERSION = /^v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}$/;

export function registryObject(value: unknown): Record<string, any> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid registry response');
  return value as Record<string, any>;
}

export function registryNumber(value: unknown, min = -1e12, max = 1e12): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw new Error('Invalid registry number');
  return value;
}

export function registryTime(value: unknown): number {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}[T ](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)) throw new Error('Invalid registry timestamp');
  const day = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed) || day.toISOString().slice(0, 10) !== value.slice(0, 10)) throw new Error('Invalid registry timestamp');
  const fraction = /\.(\d{1,6})/.exec(value)?.[1] || '';
  return parsed + Number(fraction.padEnd(6, '0').slice(3)) / 1000;
}

export function registryIdentity(value: unknown, model: string, version: string) {
  const data = registryObject(value);
  if (!IDENTIFIER.test(model) || !VERSION.test(version) || data.status !== 'success' || data.model_name !== model || data.version !== version || data.automated_retrain !== false || data.automated_deploy !== false || data.provenance_status !== 'registry_recorded_unverified') throw new Error('Invalid registry evidence binding');
  return data;
}

// ponytail: scoped GET boundary, 1 MiB/10 seconds; move into shared API when scope permits.
export async function getRegistryEvidence(model: string, version: string, route: 'lineage' | 'concept-drift', signal: AbortSignal): Promise<unknown> {
  if (!IDENTIFIER.test(model) || !VERSION.test(version)) throw new Error('Invalid registry selection');
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  const deadline = setTimeout(abort, 10000);
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let failure = 'Registry evidence unavailable or invalid';
  try {
    const response = await fetch(`${API_BASE}/api/v1/models/${encodeURIComponent(model)}/${route}?version=${encodeURIComponent(version)}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) {
      failure = response.status === 424 ? 'Recorded evidence unavailable (HTTP 424)' : `Registry request failed (HTTP ${response.status})`;
      throw new Error(failure);
    }
    if (!response.body) { failure = 'Empty registry response'; throw new Error(failure); }
    reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (controller.signal.aborted) throw new Error('Registry request cancelled or timed out');
      if (done) break;
      size += value.byteLength;
      if (size > 1048576) { failure = 'Registry response exceeds 1 MiB'; throw new Error(failure); }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    chunks.forEach((chunk) => { bytes.set(chunk, offset); offset += chunk.length; });
    if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) { failure = 'Registry response contains BOM'; throw new Error(failure); }
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    throw new Error(failure);
  } finally {
    clearTimeout(deadline);
    signal.removeEventListener('abort', abort);
    controller.abort();
    await reader?.cancel().catch(() => undefined);
  }
}

interface DriftWindowSummary {
  window_id: string;
  start: string;
  end: string;
  available_at: string;
  unit: 'UNITLESS' | 'VND_FULL';
  sample_counts: Record<string, number>;
}
export interface ConceptDriftEvidence {
  model_name: string;
  version: string;
  evaluated_at: string;
  reference_window: DriftWindowSummary;
  current_window: DriftWindowSummary;
  metrics: { feature: string; psi: number; ks: number; drift_detected: boolean }[];
  drift_detected: boolean;
  psi_threshold: number;
  ks_threshold: number;
}

export function validateConceptDrift(value: unknown, model: string, version: string): ConceptDriftEvidence {
  const data = registryIdentity(value, model, version);
  if (data.psi_method !== 'reference_equal_width_additive_smoothing' || data.ks_method !== 'two_sample_empirical_cdf' || data.constant_reference_policy !== 'below_equal_above' || !Number.isInteger(registryNumber(data.bins, 2, 50)) || data.smoothing !== 1e-6 || data.psi_threshold !== 0.2 || data.ks_threshold !== 0.1 || typeof data.drift_detected !== 'boolean') throw new Error('Invalid drift methods');
  const evaluated = registryTime(data.evaluated_at);
  if (evaluated > Date.now()) throw new Error('Future drift evaluation');
  const windows = [data.reference_window, data.current_window].map((raw) => {
    const window = registryObject(raw);
    if (typeof window.window_id !== 'string' || !IDENTIFIER.test(window.window_id) || !['UNITLESS', 'VND_FULL'].includes(window.unit)) throw new Error('Invalid drift window');
    const start = registryTime(window.start), end = registryTime(window.end), available = registryTime(window.available_at);
    if (!(start < end && end <= available && available <= evaluated)) throw new Error('Invalid drift time order');
    const counts = Object.entries(registryObject(window.sample_counts));
    if (!counts.length || counts.length > 32 || counts.reduce((sum, [feature, count]) => {
      if (!IDENTIFIER.test(feature) || !Number.isInteger(registryNumber(count, 2, 10000))) throw new Error('Invalid drift sample count');
      return sum + count;
    }, 0) > 100000) throw new Error('Invalid drift sample budget');
    return window;
  });
  const [reference, current] = windows;
  const features = Object.keys(reference.sample_counts).sort();
  if (reference.window_id === current.window_id || registryTime(reference.end) > registryTime(current.start) || reference.unit !== current.unit || features.join(',') !== Object.keys(current.sample_counts).sort().join(',')) throw new Error('Invalid drift window pair');
  if (!Array.isArray(data.metrics) || data.metrics.length !== features.length) throw new Error('Invalid drift metrics');
  const seen = new Set<string>();
  data.metrics.forEach((raw: unknown) => {
    const metric = registryObject(raw);
    if (typeof metric.feature !== 'string' || !features.includes(metric.feature) || seen.has(metric.feature) || typeof metric.drift_detected !== 'boolean') throw new Error('Invalid drift feature');
    seen.add(metric.feature);
    registryNumber(metric.psi, 0); registryNumber(metric.ks, 0, 1);
    if (metric.drift_detected !== (metric.psi >= data.psi_threshold || metric.ks >= data.ks_threshold)) throw new Error('Invalid drift classification');
  });
  if (data.drift_detected !== data.metrics.some((metric: any) => metric.drift_detected)) throw new Error('Invalid aggregate drift');
  return data as unknown as ConceptDriftEvidence;
}

export const ConceptDriftPanel: React.FC<{ modelName: string; version: string | null; refreshKey: number }> = ({ modelName, version, refreshKey }) => {
  const [state, setState] = useState<{ key: string; data?: ConceptDriftEvidence; error?: string }>({ key: '' });
  const key = `${modelName}/${version}/${refreshKey}`;
  useEffect(() => {
    const controller = new AbortController();
    if (modelName && version) {
      setState({ key });
      getRegistryEvidence(modelName, version, 'concept-drift', controller.signal)
        .then((raw) => validateConceptDrift(raw, modelName, version))
        .then((data) => { if (!controller.signal.aborted) setState({ key, data }); })
        .catch((error) => { if (!controller.signal.aborted) setState({ key, error: error.message }); });
    }
    return () => controller.abort();
  }, [modelName, version, refreshKey, key]);
  const data = state.key === key ? state.data : undefined;
  return <section aria-label="Concept drift monitor" className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 text-sm text-zinc-200 space-y-3">
    <h2 className="font-bold">Concept drift • {modelName || 'No model selected'} / {version || 'No version'}</h2>
    <p>Registry-recorded evidence, unverified. Automated retrain and deploy disabled.</p>
    {!version ? <p role="status">Select a registered version to inspect drift.</p> : !data ? <p role={state.error && state.key === key ? 'alert' : 'status'}>{state.key === key && state.error ? `Concept drift unavailable: ${state.error}` : 'Loading concept drift...'}</p> : <>
      <p role="status">{data.drift_detected ? 'DRIFT DETECTED' : 'NO DRIFT DETECTED'} • Evaluated {data.evaluated_at}</p>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {[['Reference', data.reference_window], ['Current', data.current_window]].map(([label, raw]) => {
          const window = raw as DriftWindowSummary;
          return <div key={label as string}><dt className="font-semibold">{label as string} window • {window.window_id}</dt><dd className="break-words">{window.start} — {window.end}<br />Available {window.available_at} • {window.unit}</dd></div>;
        })}
      </dl>
      <div className="overflow-x-auto"><table className="w-full text-left"><caption className="text-left">Feature drift • PSI threshold {data.psi_threshold}, KS threshold {data.ks_threshold}</caption><thead><tr>{['Feature', 'Reference samples', 'Current samples', 'PSI', 'KS', 'State'].map((label) => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead><tbody>{data.metrics.map((metric) => <tr key={metric.feature}><th scope="row" className="p-2">{metric.feature}</th><td>{data.reference_window.sample_counts[metric.feature]}</td><td>{data.current_window.sample_counts[metric.feature]}</td><td>{metric.psi.toFixed(4)}</td><td>{metric.ks.toFixed(4)}</td><td>{metric.drift_detected ? 'Drift' : 'Stable'}</td></tr>)}</tbody></table></div>
    </>}
  </section>;
};

export function validateMonitorStatus(value: unknown): void {
  const data = registryObject(value);
  if (data.status !== 'success' || typeof data.enabled !== 'boolean' || typeof data.schedule !== 'string' || !data.schedule.trim() || data.schedule.length > 64 || typeof data.timezone !== 'string' || !data.timezone.trim() || data.timezone.length > 64 || !Number.isInteger(registryNumber(data.revision, 0, Number.MAX_SAFE_INTEGER))) throw new Error('Invalid sentinel status');
  ['evaluated_model_ids', 'missing_model_ids'].forEach((field) => {
    if (!Array.isArray(data[field]) || data[field].length > 4096 || new Set(data[field]).size !== data[field].length || data[field].some((id: unknown) => typeof id !== 'string' || !IDENTIFIER.test(id))) throw new Error('Invalid sentinel scope');
  });
  const thresholds = registryObject(data.thresholds);
  ['sharpe_drop', 'ic_drop', 'turnover_spike'].forEach((key) => registryNumber(thresholds[key], 0, 10));
  registryTime(data.heartbeat);
  if (data.last_run != null) registryTime(data.last_run);
  if (data.next_run != null) registryTime(data.next_run);
  if (!Array.isArray(data.alerts) || data.alerts.length > 4096) throw new Error('Invalid sentinel alerts');
  data.alerts.forEach((raw: unknown) => {
    const alert = registryObject(raw);
    if (typeof alert.alert_id !== 'string' || alert.alert_id.length > 128 || !['INFO', 'WARNING', 'CRITICAL'].includes(alert.severity) || typeof alert.message !== 'string' || alert.message.length > 4096) throw new Error('Invalid sentinel alert');
    registryTime(alert.timestamp);
  });
}

export interface DriftMonitorPanelProps {
  status?: string;
  onRefresh?: () => void;
}

export const DriftMonitorPanel: React.FC<DriftMonitorPanelProps> = ({ onRefresh }) => {
  const addToast = useUiStore((state) => state.addToast);
  const [monitorStatus, setMonitorStatus] = useState<DriftMonitorStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const statusRequest = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const saving = useRef(false);

  // Form state
  const [enabled, setEnabled] = useState<boolean>(true);
  const [schedule, setSchedule] = useState<string>('0 2 * * *');
  const [timezone, setTimezone] = useState<string>('UTC');
  const [sharpeDrop, setSharpeDrop] = useState<number>(0.30);
  const [icDrop, setIcDrop] = useState<number>(0.015);
  const [turnoverSpike, setTurnoverSpike] = useState<number>(0.10);

  const fetchStatus = useCallback(async () => {
    statusRequest.current?.abort();
    const controller = new AbortController();
    statusRequest.current = controller;
    try {
      setIsLoading(true);
      setMonitorStatus(null);
      setStatusError(null);
      const res = await advancedQuantApi.getDriftMonitorStatus(controller.signal);
      validateMonitorStatus(res);
      if (controller.signal.aborted || !mounted.current) return;
      setMonitorStatus(res);
      setEnabled(res.enabled);
      setSchedule(res.schedule);
      setTimezone(res.timezone);
      if (res.thresholds) {
        if (res.thresholds.sharpe_drop !== undefined) setSharpeDrop(res.thresholds.sharpe_drop);
        if (res.thresholds.ic_drop !== undefined) setIcDrop(res.thresholds.ic_drop);
        if (res.thresholds.turnover_spike !== undefined) setTurnoverSpike(res.thresholds.turnover_spike);
      }
    } catch {
      if (controller.signal.aborted || !mounted.current) return;
      setStatusError('Drift sentinel unavailable or invalid');
      addToast({ type: 'error', title: 'Drift Sentinel Fetch Failed', message: 'Drift sentinel unavailable or invalid' });
    } finally {
      if (!controller.signal.aborted && mounted.current) setIsLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    mounted.current = true;
    fetchStatus();
    return () => { mounted.current = false; statusRequest.current?.abort(); };
  }, [fetchStatus]);

  const handleSaveSchedule = async () => {
    if (!monitorStatus || saving.current || isLoading || !mounted.current) return;
    if (![sharpeDrop, icDrop, turnoverSpike].every((value) => Number.isFinite(value) && value >= 0 && value <= 10) || !schedule.trim() || schedule.length > 64 || !timezone.trim() || timezone.length > 64) {
      setStatusError('Invalid schedule or thresholds');
      return;
    }
    saving.current = true;
    setIsSaving(true);
    const req: DriftScheduleRequest = {
      enabled,
      schedule,
      timezone,
      thresholds: {
        sharpe_drop: sharpeDrop,
        ic_drop: icDrop,
        turnover_spike: turnoverSpike,
      },
      revision: monitorStatus.revision,
    };

    try {
      const updated = await advancedQuantApi.updateDriftSchedule(req);
      validateMonitorStatus(updated);
      if (!mounted.current) return;
      setStatusError(null);
      setMonitorStatus(updated);
      addToast({
        type: 'success',
        title: 'Schedule Updated',
        message: `Drift Sentinel schedule revision ${updated.revision} saved.`,
      });
      if (onRefresh) onRefresh();
    } catch {
      if (!mounted.current) return;
      addToast({
        type: 'error',
        title: 'Schedule Update Failed',
        message: 'Revision conflict or validation failure',
      });
      // Refresh to get current revision
      fetchStatus();
    } finally {
      saving.current = false;
      if (mounted.current) setIsSaving(false);
    }
  };

  return (
    <div className="drift-monitor-panel flex flex-col gap-4 font-mono select-none" data-testid="drift-monitor-panel">
      {statusError && <p role="alert" className="text-sm text-zinc-200">{statusError}</p>}
      {/* Sentinel Status Banner */}
      <div className="p-4 rounded-xl bg-zinc-900/70 border border-white/10 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-amber-400" />
            <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wide">
              Autonomous Drift Sentinel & Concept Decay Engine
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span
              data-testid="drift-status"
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                monitorStatus?.enabled
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40'
                  : 'bg-zinc-950 text-zinc-500 border border-white/10'
              }`}
            >
              {!monitorStatus ? 'SENTINEL UNAVAILABLE' : monitorStatus.enabled ? 'SENTINEL ACTIVE' : 'SENTINEL DISABLED'}
            </span>
            <button
              onClick={fetchStatus}
              disabled={isLoading || isSaving}
              className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
              title="Refresh Sentinel Status"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Telemetry Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-white/5 text-[11px]">
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Heartbeat</span>
            <span className="text-zinc-300 font-mono mt-0.5">
              {monitorStatus?.heartbeat ? new Date(monitorStatus.heartbeat).toLocaleTimeString() : 'N/A'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Last Evaluation</span>
            <span className="text-zinc-300 font-mono mt-0.5">
              {monitorStatus?.last_run ? new Date(monitorStatus.last_run).toLocaleDateString() : 'N/A'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Next Scheduled</span>
            <span className="text-cyan-400 font-mono mt-0.5">
              {monitorStatus?.next_run ? new Date(monitorStatus.next_run).toLocaleDateString() : 'N/A'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Config Revision</span>
            <span className="text-purple-400 font-mono mt-0.5">rev #{monitorStatus?.revision ?? 'N/A'}</span>
          </div>
        </div>
      </div>

      {/* Schedule Configuration & Threshold Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
          <div className="flex items-center gap-2 pb-2 border-b border-white/5">
            <Clock className="w-4 h-4 text-cyan-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Inspection Cadence & Detection Thresholds
            </h4>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label htmlFor="sentinel-schedule" className="text-[10px] text-zinc-400 block mb-1">Cron Schedule (UTC)</label>
              <input id="sentinel-schedule"
                type="text"
                value={schedule}
                onChange={(e) => setSchedule(e.target.value)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
                placeholder="0 2 * * *"
              />
            </div>
            <div>
              <label htmlFor="sentinel-timezone" className="text-[10px] text-zinc-400 block mb-1">Timezone</label>
              <input id="sentinel-timezone"
                type="text"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
                placeholder="UTC"
              />
            </div>
            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer pb-1">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="rounded bg-zinc-950 border-white/20 text-emerald-500 focus:ring-0"
                />
                <span className="text-[11px] font-bold">Sentinel Enabled</span>
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-white/5 text-xs">
            <div>
              <label htmlFor="sentinel-sharpe" className="text-[10px] text-zinc-400 block mb-1">Sharpe Drop Threshold</label>
              <input id="sentinel-sharpe"
                type="number"
                step="0.05"
                min="0.05"
                max="1.0"
                value={Number.isFinite(sharpeDrop) ? sharpeDrop : ''}
                onChange={(e) => setSharpeDrop(e.target.valueAsNumber)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 30% drop triggers alert</span>
            </div>
            <div>
              <label htmlFor="sentinel-ic" className="text-[10px] text-zinc-400 block mb-1">IC Decay Threshold</label>
              <input id="sentinel-ic"
                type="number"
                step="0.005"
                min="0.001"
                max="0.1"
                value={Number.isFinite(icDrop) ? icDrop : ''}
                onChange={(e) => setIcDrop(e.target.valueAsNumber)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 0.015 drop triggers alert</span>
            </div>
            <div>
              <label htmlFor="sentinel-turnover" className="text-[10px] text-zinc-400 block mb-1">Turnover Spike Threshold</label>
              <input id="sentinel-turnover"
                type="number"
                step="0.02"
                min="0.01"
                max="0.5"
                value={Number.isFinite(turnoverSpike) ? turnoverSpike : ''}
                onChange={(e) => setTurnoverSpike(e.target.valueAsNumber)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 10% spike triggers alert</span>
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              onClick={handleSaveSchedule}
              disabled={isSaving || isLoading || !monitorStatus}
              className={`py-1.5 px-3 rounded text-xs font-bold flex items-center gap-1.5 transition-all ${
                isSaving
                  ? 'bg-amber-950/40 text-amber-400 border border-amber-500/30 cursor-not-allowed'
                  : 'bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold'
              }`}
            >
              {isSaving ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              <span>Save Schedule (rev #{monitorStatus?.revision ?? 'N/A'})</span>
            </button>
          </div>
        </div>

        {/* Model Scope & Resolution */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
          <div className="flex items-center gap-2 pb-2 border-b border-white/5">
            <Layers className="w-4 h-4 text-purple-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Monitored Model Scope
            </h4>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-zinc-400">Evaluated in Catalog:</span>
              <span className="font-bold text-emerald-400">
                {monitorStatus?.evaluated_model_ids.length || 0} models
              </span>
            </div>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {(monitorStatus?.evaluated_model_ids || []).map((m) => (
                <span
                  key={m}
                  className="px-1.5 py-0.5 rounded bg-zinc-950 text-[9px] text-zinc-300 border border-white/5"
                >
                  {m}
                </span>
              ))}
            </div>

            {monitorStatus?.missing_model_ids && monitorStatus.missing_model_ids.length > 0 && (
              <div className="flex flex-col gap-1 pt-2 border-t border-white/5">
                <span className="text-[10px] text-rose-400 font-bold">
                  Missing from Registry ({monitorStatus.missing_model_ids.length}):
                </span>
                <div className="flex flex-wrap gap-1">
                  {monitorStatus.missing_model_ids.map((m) => (
                    <span
                      key={m}
                      className="px-1.5 py-0.5 rounded bg-rose-950/40 text-[9px] text-rose-300 border border-rose-500/20"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Active Alerts Strip */}
      <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-2">
        <div className="flex items-center justify-between pb-2 border-b border-white/5">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Sentinel Incident & Drift Log
            </h4>
          </div>
          <span className="text-[10px] text-zinc-400">
            {monitorStatus?.alerts.length || 0} Incidents Recorded
          </span>
        </div>

        {monitorStatus?.alerts && monitorStatus.alerts.length > 0 ? (
          <div className="flex flex-col gap-2">
            {monitorStatus.alerts.map((al, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded bg-rose-950/20 border border-rose-500/30 flex items-center justify-between text-xs font-mono"
              >
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                  <span className="text-rose-200">{al.message}</span>
                </div>
                <span className="text-[10px] text-zinc-400">{al.timestamp}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-3 rounded bg-emerald-950/20 border border-emerald-500/20 flex items-center gap-2 text-xs text-emerald-400 font-mono">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{monitorStatus ? 'No recorded sentinel incidents. This does not certify model health.' : 'Sentinel incidents unavailable.'}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default DriftMonitorPanel;
