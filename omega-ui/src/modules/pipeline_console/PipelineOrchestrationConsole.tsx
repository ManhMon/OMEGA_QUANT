import { useEffect, useRef, useState, type FC } from 'react';
import { Terminal } from 'lucide-react';
import { API_BASE } from '../../api/client';
import { useTranslation } from '../../i18n';

export const PIPELINE_STAGES = ['DATA_INGEST', 'FEATURE_ENGINEERING', 'ALPHA_DISCOVERY', 'RISK_OPTIMIZATION', 'RESEARCH_EXECUTION'] as const;
type Status = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
type Stage = { stage_id: string; depends_on: string[]; status: string };
type Telemetry = {
  schema_version: string; revision: number; task_id: string; job_id: string;
  event_type: string; progress: number; stage: string; status: Status;
  timestamp: string; message: string; payload: Record<string, unknown>; dag: Stage[];
};
const terminal = (status?: string) => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status || '');
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const digest = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const time = (value: unknown) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)) return false;
  const day = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value.slice(0, 10) && Number.isFinite(Date.parse(value));
};
const text = (value: unknown, limit: number): value is string => typeof value === 'string' && value.length <= limit;
const jobIdentifier = (value: unknown): value is string => typeof value === 'string' && /^job-pipe-[a-f0-9]{8}$/.test(value);

export function validatePipelineTelemetry(value: unknown, jobId: string): Telemetry {
  const invalid = () => { throw new Error('Invalid pipeline telemetry.'); };
  if (!object(value) || value.schema_version !== 'pipeline-telemetry/v1' || value.task_id !== jobId || value.job_id !== jobId ||
    !Number.isSafeInteger(value.revision) || (value.revision as number) < 0 || typeof value.progress !== 'number' || !Number.isFinite(value.progress) ||
    value.progress < 0 || value.progress > 100 || !time(value.timestamp) || (value.message !== undefined && !text(value.message, 4096)) || !object(value.payload) ||
    typeof value.event_type !== 'string' || !['SNAPSHOT', 'PING', 'PROGRESS', 'COMPLETE', 'ERROR', 'CANCELLED'].includes(value.event_type) ||
    typeof value.status !== 'string' || !['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'].includes(value.status) ||
    !Array.isArray(value.dag) || value.dag.length !== PIPELINE_STAGES.length) return invalid();
  const data = value as unknown as Telemetry;
  const index = PIPELINE_STAGES.indexOf(data.stage as typeof PIPELINE_STAGES[number]);
  if (index < 0 && data.stage !== 'INIT') return invalid();
  if ((data.status === 'RUNNING' && index < 0) || (data.status === 'QUEUED' && data.stage !== 'INIT') ||
    (data.status !== 'COMPLETED' && data.progress >= 100) || (data.status === 'COMPLETED' && data.progress !== 100) ||
    (data.event_type === 'COMPLETE' && data.status !== 'COMPLETED') || (data.event_type === 'ERROR' && data.status !== 'FAILED') ||
    (data.event_type === 'CANCELLED' && data.status !== 'CANCELLED') || (data.event_type === 'PROGRESS' && data.status !== 'RUNNING')) return invalid();
  data.dag.forEach((node, i) => {
    const expected = data.status === 'COMPLETED' || i < index ? 'COMPLETED' : i === index ? data.status : 'PENDING';
    if (!object(node) || node.stage_id !== PIPELINE_STAGES[i] || node.status !== expected ||
      !Array.isArray(node.depends_on) || JSON.stringify(node.depends_on) !== JSON.stringify(i ? [PIPELINE_STAGES[i - 1]] : [])) invalid();
  });
  if (data.status === 'COMPLETED') {
    const receipt = data.payload.receipt;
    if (!object(receipt) || receipt.schema_version !== 1 || receipt.task_id !== jobId || receipt.operation !== 'PIPELINE_RUN' ||
      receipt.status !== 'COMPLETED' || !digest(receipt.request_fingerprint) || !digest(receipt.output_sha256) || !digest(receipt.receipt_hmac) ||
      !time(receipt.published_at) || !text(receipt.artifact_id, 4096) || !receipt.artifact_id) return invalid();
  }
  return data;
}

export function pipelineRequest(universe: string, start: string, end: string, capital: string) {
  const symbols = universe.trim().toUpperCase().split(/[\s,]+/);
  const date = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  const amount = Number(capital);
  if (!symbols.length || symbols.length > 100 || symbols.some((symbol) => !/^[A-Z][A-Z0-9]{1,9}$/.test(symbol)) ||
    new Set(symbols).size !== symbols.length || !date(start) || !date(end) || start > end ||
    Date.parse(end) - Date.parse(start) > 3655 * 86400000 || Date.parse(`${end}T08:30:00Z`) > Date.now() ||
    !capital.trim() || !Number.isFinite(amount) || amount <= 0 || amount > 1e12) throw new Error('Invalid universe, dates or capital (VND_FULL).');
  return { universe: symbols, start_date: start, end_date: end, initial_capital: amount, mode: 'IN_PROCESS' as const };
}

// ponytail: local Slice 16 lifecycle; legacy usePipelineRunner lacks revision/DAG validation and cancel error handling.
export const PipelineOrchestrationConsole: FC = () => {
  const { t } = useTranslation();
  const [universe, setUniverse] = useState('FPT, HPG, MBB, MWG');
  const [start, setStart] = useState('2023-01-01');
  const [end, setEnd] = useState('2023-12-31');
  const [capital, setCapital] = useState('1000000000');
  const [job, setJob] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [logs, setLogs] = useState<Telemetry[]>([]);
  const [connection, setConnection] = useState('IDLE');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const mounted = useRef(false);
  const operation = useRef(false);
  const source = useRef<EventSource | null>(null);
  const latest = useRef<Telemetry | null>(null);
  const request = useRef<AbortController | null>(null);
  const watchdog = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastParams = useRef<ReturnType<typeof pipelineRequest> | null>(null);

  function closeStream() {
    source.current?.close(); source.current = null;
    clearTimeout(watchdog.current);
  }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; closeStream(); request.current?.abort(); };
  }, []);

  function connect(jobId: string) {
    closeStream(); setConnection('CONNECTING');
    let stream: EventSource;
    const fail = (message: string) => { closeStream(); setConnection('UNAVAILABLE'); setError(message); };
    try { stream = new EventSource(`${API_BASE}/sse/v1/pipeline/${jobId}/stream`); }
    catch { fail('Telemetry unavailable. Reconnect the same task; do not duplicate execution.'); return; }
    source.current = stream;
    const current = () => mounted.current && source.current === stream;
    const arm = () => {
      clearTimeout(watchdog.current);
      watchdog.current = setTimeout(() => { if (current()) fail('Telemetry timeout. Task outcome unknown.'); }, 10000);
    };
    arm();
    stream.onopen = () => { if (current()) { setConnection('CONNECTED'); arm(); } };
    stream.onerror = () => { if (current()) fail('Telemetry disconnected. Task outcome unknown.'); };
    stream.onmessage = (event) => {
      if (!current()) return;
      try {
        if (typeof event.data !== 'string' || new TextEncoder().encode(event.data).length > 65536) throw new Error();
        const data = validatePipelineTelemetry(JSON.parse(event.data), jobId);
        const previous = latest.current;
        arm();
        if (previous && data.revision <= previous.revision) return;
        if (previous && (terminal(previous.status) || data.progress < previous.progress ||
          PIPELINE_STAGES.indexOf(data.stage as typeof PIPELINE_STAGES[number]) < PIPELINE_STAGES.indexOf(previous.stage as typeof PIPELINE_STAGES[number]))) throw new Error();
        latest.current = data; setTelemetry(data); setError(null); setConnection('CONNECTED');
        if (data.event_type !== 'PING') setLogs((items) => [...items.slice(-99), data]);
        if (terminal(data.status)) { closeStream(); setConnection('CLOSED'); }
      } catch { fail('Invalid pipeline telemetry. Task outcome unknown; reconnect for a fresh snapshot.'); }
    };
  }

  async function post(path: string, body?: unknown) {
    const controller = new AbortController(); request.current = controller;
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, redirect: 'error' });
      if (!response.ok) throw new Error(`Pipeline request rejected (HTTP ${response.status}).`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error();
      let size = 0;
      let raw = '';
      const decoder = new TextDecoder('utf-8', { fatal: true });
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          size += chunk.value.byteLength;
          if (size > 65536) throw new Error();
          raw += decoder.decode(chunk.value, { stream: true });
        }
        raw += decoder.decode();
      } finally { await reader.cancel(); reader.releaseLock(); }
      return JSON.parse(raw) as unknown;
    } finally { clearTimeout(timer); if (request.current === controller) request.current = null; }
  }

  async function run(retry = false) {
    if (operation.current || uncertain || (job && !terminal(latest.current?.status))) return;
    let params: ReturnType<typeof pipelineRequest>;
    try { params = retry && lastParams.current ? lastParams.current : pipelineRequest(universe, start, end, capital); }
    catch { setError('Invalid universe, dates or capital (VND_FULL).'); return; }
    operation.current = true; setBusy(true); setError(null);
    try {
      const response = await post('/api/v1/control/pipeline-run', params);
      if (!object(response) || response.status !== 'success' || !jobIdentifier(response.job_id) || response.task_id !== response.job_id ||
        response.stream_url !== `/sse/v1/pipeline/${response.job_id}/stream`) throw new Error();
      if (!mounted.current) return;
      latest.current = null; setTelemetry(null); setLogs([]); setJob(response.job_id); lastParams.current = params;
      connect(response.job_id);
    } catch (failure) {
      if (!mounted.current) return;
      const rejected = failure instanceof Error && /^Pipeline request rejected \(HTTP (403|409|422|429)\)\.$/.test(failure.message);
      setUncertain(!rejected);
      setError(rejected ? failure.message : 'Dispatch outcome unknown. Check Control Center before another run.');
    } finally { operation.current = false; if (mounted.current) setBusy(false); }
  }

  async function cancel() {
    if (!job || operation.current || terminal(latest.current?.status)) return;
    operation.current = true; setBusy(true); setError(null);
    try {
      const response = await post(`/api/v1/control/cancel/${job}`);
      if (!object(response) || response.status !== 'success' || response.task_id !== job || response.job_id !== job || response.cancelled !== true) throw new Error();
      if (mounted.current && !terminal(latest.current?.status)) connect(job);
    } catch { if (mounted.current) setError('Cancellation not confirmed. Reconnect for the authoritative task state.'); }
    finally { operation.current = false; if (mounted.current) setBusy(false); }
  }

  const active = Boolean(job && !terminal(telemetry?.status));
  const inputClass = 'min-h-11 w-full rounded-lg border border-white/10 bg-zinc-950 p-2 text-sm text-zinc-100 focus-visible:outline-2 focus-visible:outline-cyan-300';
  const buttonClass = 'min-h-11 rounded-lg border border-white/20 px-4 text-sm text-zinc-100 hover:bg-zinc-800 focus-visible:outline-2 focus-visible:outline-cyan-300 disabled:opacity-50';
  return (
    <section aria-label={t.pipelineConsole.title} className="min-w-0 space-y-4 rounded-xl border border-white/10 bg-zinc-900/60 p-4 font-mono text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-bold"><Terminal aria-hidden="true" className="h-5 w-5" />{t.pipelineConsole.title}</h2>
        <p role="status" className="text-sm">{telemetry?.status || (job ? 'AWAITING TELEMETRY' : 'IDLE')} · SSE {connection}</p>
      </header>
      <p className="text-sm text-zinc-300">In-process research pipeline. No pause/resume or live trading controls.</p>
      <form onSubmit={(event) => { event.preventDefault(); void run(); }} className="space-y-3">
        <fieldset disabled={busy || active || uncertain} className="grid min-w-0 gap-3 sm:grid-cols-2">
          <legend className="sr-only">Pipeline parameters</legend>
          <label className="min-w-0 text-sm">Universe (comma-separated)<input className={inputClass} value={universe} maxLength={1100} onChange={(event) => setUniverse(event.target.value)} /></label>
          <label className="min-w-0 text-sm">Initial capital (VND_FULL)<input className={inputClass} type="number" min="1" max="1000000000000" value={capital} onChange={(event) => setCapital(event.target.value)} /></label>
          <label className="min-w-0 text-sm">Start date<input className={inputClass} type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="min-w-0 text-sm">End date<input className={inputClass} type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        </fieldset>
        <div className="flex flex-wrap gap-3">
          <button className={buttonClass} disabled={busy || active || uncertain} type="submit">Run pipeline</button>
          <button className={buttonClass} disabled={busy || !active} type="button" onClick={() => { if (window.confirm('Cancel this pipeline task?')) void cancel(); }}>Cancel task</button>
          <button className={buttonClass} disabled={busy || !active || connection !== 'UNAVAILABLE'} type="button" onClick={() => { if (job) { setError(null); connect(job); } }}>Reconnect telemetry</button>
          <button className={buttonClass} disabled={busy || !terminal(telemetry?.status) || telemetry?.payload.retryable !== true} type="button" onClick={() => { void run(true); }}>Retry as new task</button>
        </div>
      </form>
      {error && <p role="alert" className="rounded-lg border border-rose-400/40 p-3 text-sm text-zinc-100">{error}</p>}
      <div className="space-y-2">
        <p className="break-all text-sm">Task: {job || 'Not dispatched'}</p>
        <label className="block text-sm">Execution progress: {telemetry ? `${telemetry.progress}%` : 'Unavailable'}
          <progress aria-label="Pipeline execution progress" className="block h-3 w-full" max={100} value={telemetry?.progress} />
        </label>
        {connection === 'UNAVAILABLE' && telemetry && <p className="text-sm">Last known state; telemetry is stale.</p>}
      </div>
      <h3 className="font-bold">Execution DAG</h3>
      {!telemetry ? <p className="text-sm text-zinc-300">Awaiting server DAG telemetry.</p> : <ol aria-label="Pipeline stages" className="space-y-2">
        {telemetry.dag.map((node) => <li key={node.stage_id} className="break-words rounded-lg border border-white/10 p-3 text-sm">
          <strong>{node.stage_id}</strong> · {node.status}<span className="block text-zinc-300">Depends on: {node.depends_on.join(', ') || 'None'}</span>
        </li>)}
      </ol>}
      {telemetry?.status === 'COMPLETED' && <p className="text-sm">Server-reported receipt present. Browser has not independently verified its signature or PIT provenance.</p>}
      {telemetry?.status === 'FAILED' && <p role="alert" className="text-sm">Pipeline failed. No successful execution inferred.</p>}
      <h3 className="font-bold">Stage event history (last 100)</h3>
      <ol aria-label="Stage event history" className="max-h-64 space-y-2 overflow-auto text-sm">
        {logs.map((entry) => <li key={entry.revision} className="break-words border-b border-white/10 pb-2">{entry.timestamp} · #{entry.revision} · {entry.stage} · {entry.status} · {entry.progress}%</li>)}
      </ol>
    </section>
  );
};
