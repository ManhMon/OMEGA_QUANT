import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi, validateSystemTelemetry, validateOperationsBreaker, validateResourceGovernor, validateGovernorUpdate, operationsTime } from '../api/advancedQuant';
import { OverviewTab } from '../modules/control_center/tabs/OverviewTab';
import { apiClient, macroTime, validateMacroNews, validateMacroVSI, validateMacroContagion, validateMacroIntelligence } from '../api/client';
import { MacroNewsHubView } from '../modules/macro_news/MacroNewsHubView';
import { ModelRegistryView, validateModelCatalog, validateModelVersions, validateModelLineage } from '../modules/model_registry/ModelRegistryView';
import { ConceptDriftPanel, DriftMonitorPanel, getRegistryEvidence, validateConceptDrift, validateMonitorStatus, registryTime } from '../modules/model_registry/DriftMonitorPanel';
import { useUiStore } from '../store/uiStore';
import { QuantControlCenter } from '../modules/control_center/QuantControlCenter';
import { PipelineOrchestrationConsole, PIPELINE_STAGES, pipelineRequest, validatePipelineTelemetry } from '../modules/pipeline_console/PipelineOrchestrationConsole';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const operationsBase = (source: 'PSUTIL_AND_DURABLE_JOB_QUEUE' | 'OMEGA_RISK_CIRCUIT_BREAKER') => ({ schema_version: 'operations/v1' as const, as_of: '2026-10-10T08:30:00Z', available_at: '2026-10-10T08:30:00Z', provenance: { source, sha256: 'a'.repeat(64), normalized_timezone: 'UTC' as const, observation_mode: 'CURRENT_ONLY' as const, is_synthetic: false as const } });
const systemFrame = () => ({ ...operationsBase('PSUTIL_AND_DURABLE_JOB_QUEUE'), cpu_usage_pct: 0, memory_usage_mb: 512, memory_usage_pct: 50, memory_unit: 'MiB' as const, io_read_bytes: 0, io_write_bytes: 1024, io_unit: 'bytes_cumulative_since_boot' as const, ipc_queue_depth: 0, ipc_unit: 'queued_jobs' as const, gpu_telemetry: null });
const breakerFrame = (triggered = false) => ({ ...operationsBase('OMEGA_RISK_CIRCUIT_BREAKER'), state: triggered ? 'TRIGGERED' as const : 'NORMAL' as const, circuit_broken: triggered, reasons: triggered ? ['Risk circuit breaker activated' as const] : [], triggered_at: triggered ? '2026-10-10T08:30:00Z' : null, daily_pnl: null, drawdown_pct: null, max_drawdown_limit: null });
const governorFrame = () => ({ status: 'success', mode: 'MANUAL' as const, target_concurrency: 8, thread_pool_size: 16, batch_size: 256, version: 1, active_workers: 0, queue_depth: 0, system_load_pct: 0, memory_usage_mb: 0, mode_description: 'Manual policy summary', updated_at: '2026-10-10T08:30:00Z' });

const MODEL = 'ALPHA_XGBOOST_V2';
const lineage = () => ({ status: 'success', model_name: MODEL, version: 'v1.0.0', evidence_status: 'incomplete', provenance_status: 'registry_recorded_unverified', automated_retrain: false, automated_deploy: false,
  nodes: [{ version: 'v1.0.0', parent_versions: [] as string[], dataset_snapshot: null, training_run: null, git_commit: null, deployment_receipt: null }] });
const drift = () => ({ status: 'success', model_name: MODEL, version: 'v1.0.0', evaluated_at: '2026-10-10T08:30:00Z', provenance_status: 'registry_recorded_unverified', automated_retrain: false, automated_deploy: false,
  reference_window: { window_id: 'reference', start: '2026-10-09T00:00:00Z', end: '2026-10-10T00:00:00Z', available_at: '2026-10-10T00:00:00Z', unit: 'VND_FULL', sample_counts: { price: 2 } },
  current_window: { window_id: 'current', start: '2026-10-10T00:00:00Z', end: '2026-10-10T15:30:00+07:00', available_at: '2026-10-10T08:30:00Z', unit: 'VND_FULL', sample_counts: { price: 2 } },
  metrics: [{ feature: 'price', psi: 0, ks: 0, drift_detected: false }], drift_detected: false, psi_method: 'reference_equal_width_additive_smoothing', ks_method: 'two_sample_empirical_cdf', constant_reference_policy: 'below_equal_above', bins: 10, smoothing: 1e-6, psi_threshold: 0.2, ks_threshold: 0.1 });
const jsonResponse = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const sentinel = () => ({ status: 'success', enabled: true, schedule: '0 2 * * *', timezone: 'UTC', last_run: null, next_run: null, heartbeat: '2026-10-10T00:00:00Z', evaluated_model_ids: [MODEL], missing_model_ids: [], alerts: [], last_job: null, thresholds: { sharpe_drop: 0.3, ic_drop: 0.015, turnover_spike: 0.1 }, revision: 1 });

describe('Phase 4 Model Governance & Resource Governor UI Lifecycle Tests', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.useFakeTimers();
    useUiStore.setState({ activeFeatureId: null, activeSubTabs: { model_registry: 'registry' } });
    vi.stubGlobal('fetch', vi.fn(async (url: string) => jsonResponse(url.includes('/lineage?') ? lineage() : drift())));
    vi.spyOn(advancedQuantApi, 'getDriftMonitorStatus').mockResolvedValue(sentinel());
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      return window.setTimeout(() => cb(performance.now()), 16);
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id: number) => {
      clearTimeout(id);
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchInterval: false,
        },
      },
    });

    vi.spyOn(advancedQuantApi, 'getSystemTelemetry').mockResolvedValue(systemFrame());
  vi.spyOn(advancedQuantApi, 'getOperationsCircuitBreaker').mockResolvedValue(breakerFrame());
  // Mock advancedQuantApi Phase 4 methods
    vi.spyOn(advancedQuantApi, 'getModelList').mockResolvedValue({
      status: 'success',
      count: 2,
      models: [
        {
          model_name: 'ALPHA_XGBOOST_V2',
          active_versions: { PRODUCTION: 'v1.0.0', VALIDATED: 'v1.0.0', STAGING: 'v1.0.0' },
          total_versions: 2,
          latest_version: 'v1.0.1',
          last_updated: '2026-08-29T00:00:00Z',
        },
        {
          model_name: 'HMM_REGIME_DETECTOR',
          active_versions: { PRODUCTION: 'v1.0.0', VALIDATED: null, STAGING: null },
          total_versions: 1,
          latest_version: 'v1.0.0',
          last_updated: '2026-08-29T00:00:00Z',
        },
      ],
    });

    vi.spyOn(advancedQuantApi, 'getModelVersions').mockResolvedValue({
      status: 'success',
      model_name: 'ALPHA_XGBOOST_V2',
      active_versions: { PRODUCTION: 'v1.0.0' },
      versions: [
        {
          version: 'v1.0.1',
          status: 'STAGING',
          checksum: 'a'.repeat(64),
          artifact_path: '.models/artifacts/ALPHA_XGBOOST_V2/v1.0.1/model.joblib',
          registered_at: '2026-08-29T00:00:00Z',
          metadata: { metrics: { sharpe: 1.95, ic: 0.058, turnover: 0.16 } },
        },
        {
          version: 'v1.0.0',
          status: 'PRODUCTION',
          checksum: 'b'.repeat(64),
          artifact_path: '.models/artifacts/ALPHA_XGBOOST_V2/v1.0.0/model.joblib',
          registered_at: '2026-08-01T00:00:00Z',
          metadata: { metrics: { sharpe: 1.85, ic: 0.052, turnover: 0.18 } },
        },
      ],
    });

    vi.spyOn(advancedQuantApi, 'getModelDrift').mockResolvedValue({
      status: 'success',
      model_name: 'ALPHA_XGBOOST_V2',
      active_version: 'v1.0.0',
      drift_detected: false,
      drift_level: 'LOW',
      drift_score: 0.12,
      evaluated_at: '2026-08-29T00:00:00Z',
      metrics: [
        { metric_name: 'out_of_sample_sharpe', baseline_value: 1.85, current_value: 1.82, drift_detected: false, threshold: 0.30, p_value: 0.45 },
        { metric_name: 'information_coefficient_ic', baseline_value: 0.052, current_value: 0.050, drift_detected: false, threshold: 0.015, p_value: 0.62 },
        { metric_name: 'portfolio_turnover_rate', baseline_value: 0.18, current_value: 0.19, drift_detected: false, threshold: 0.10, p_value: 0.28 },
      ],
      summary: {},
    });

    vi.spyOn(advancedQuantApi, 'getResourceGovernor').mockResolvedValue({
      status: 'success',
      mode: 'MANUAL',
      target_concurrency: 8,
      thread_pool_size: 16,
      batch_size: 256,
      version: 1,
      active_workers: 4,
      queue_depth: 0,
      system_load_pct: 24.5,
      memory_usage_mb: 512.0,
      mode_description: 'Operator manual concurrency and worker pool configuration.',
      updated_at: '2026-08-29T00:00:00Z',
    });

    vi.spyOn(advancedQuantApi, 'updateResourceGovernor').mockResolvedValue({
      status: 'success',
      mode: 'COPILOT',
      target_concurrency: 12,
      thread_pool_size: 24,
      batch_size: 256,
      version: 2,
      active_workers: 8,
      queue_depth: 0,
      system_load_pct: 35.2,
      memory_usage_mb: 768.0,
      mode_description: 'Autonomous dynamic resource scheduling governed by Copilot telemetry.',
      updated_at: '2026-08-29T00:00:00Z',
    });

    vi.spyOn(advancedQuantApi, 'promoteModelVersion').mockResolvedValue({
      status: 'success',
      model_name: 'ALPHA_XGBOOST_V2',
      version: 'v1.0.1',
      target_status: 'PRODUCTION',
      totp_verified: true,
      promoted_at: '2026-08-29T00:00:00Z',
      message: 'Model ALPHA_XGBOOST_V2 v1.0.1 promoted to PRODUCTION',
    });

    vi.spyOn(advancedQuantApi, 'rollbackModel').mockResolvedValue({
      status: 'success',
      model_name: 'ALPHA_XGBOOST_V2',
      target_version: 'v1.0.0',
      totp_verified: true,
      rolled_back_at: '2026-08-29T00:00:00Z',
      previous_active_version: 'v1.0.1',
      message: 'Model ALPHA_XGBOOST_V2 rolled back to v1.0.0',
    });
  });

  afterEach(() => {
    if (root && container) {
      act(() => {
        root?.unmount();
      });
      container.remove();
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.clearAllTimers();
    vi.useRealTimers();
    useUiStore.setState({ activeFeatureId: null, activeSubTabs: {} });
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    act(() => {
      root?.render(
        React.createElement(QueryClientProvider, { client: queryClient }, ui)
      );
    });
  };

  it('1. ModelRegistryView mounts, triggers debounced version and drift inspection', async () => {
    renderWithProviders(React.createElement(ModelRegistryView, null));
    expect(container).not.toBeNull();

    await act(async () => { await Promise.resolve(); });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    await act(async () => { await Promise.resolve(); });

    expect(advancedQuantApi.getModelList).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.getModelVersions).toHaveBeenCalledWith('ALPHA_XGBOOST_V2', expect.any(AbortSignal));
    expect(advancedQuantApi.getModelDrift).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(`/${MODEL}/lineage?version=v1.0.0`), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(`/${MODEL}/concept-drift?version=v1.0.0`), expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(container?.textContent).toContain('Registry-recorded evidence, unverified');
    expect(container?.textContent).not.toContain('DRIFT NORMAL');
  });

  it('2. ModelRegistryView handles Resource Governor mode switch', async () => {
    renderWithProviders(React.createElement(ModelRegistryView, null));

    await act(async () => { await Promise.resolve(); });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    await act(async () => { await Promise.resolve(); });

    expect(advancedQuantApi.getResourceGovernor).toHaveBeenCalledTimes(1);
  });

  it('catalog empty/error clears targets without fabricated versions', async () => {
    vi.mocked(advancedQuantApi.getModelList).mockResolvedValue({ status: 'success', count: 0, models: [] });
    renderWithProviders(React.createElement(ModelRegistryView));
    await act(async () => { await Promise.resolve(); await vi.advanceTimersByTimeAsync(600); });
    expect(advancedQuantApi.getModelVersions).not.toHaveBeenCalled();
    expect(container?.textContent).toContain('No version selected');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('partial 424 drift failure preserves lineage and versions', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => String(input).includes('/lineage?') ? jsonResponse(lineage()) : new Response('', { status: 424 }));
    renderWithProviders(React.createElement(ModelRegistryView));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(600); });
    await act(async () => { await Promise.resolve(); });
    expect(container?.textContent).toContain('Evidence: incomplete');
    expect(container?.textContent).toContain('Concept drift unavailable: Recorded evidence unavailable (HTTP 424)');
    expect(container?.textContent).not.toContain('NO DRIFT DETECTED');
  });

  it('version buttons request exactly the selected version', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = new URL(String(input));
      const version = url.searchParams.get('version')!;
      const value = url.pathname.endsWith('/lineage') ? lineage() : drift();
      value.version = version;
      if ('nodes' in value) value.nodes[0].version = version;
      return jsonResponse(value);
    });
    renderWithProviders(React.createElement(ModelRegistryView));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(600); });
    const button = [...container!.querySelectorAll('button')].find((button) => button.textContent === 'v1.0.1')!;
    await act(async () => { button.click(); });
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('lineage?version=v1.0.1'), expect.anything());
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('concept-drift?version=v1.0.1'), expect.anything());
    expect(advancedQuantApi.promoteModelVersion).not.toHaveBeenCalled();
    expect(advancedQuantApi.rollbackModel).not.toHaveBeenCalled();
  });

  it('late old selection cannot replace newer concept drift', async () => {
    let resolveOld!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; })).mockResolvedValue(jsonResponse({ ...drift(), version: 'v1.0.1' }));
    renderWithProviders(React.createElement(ConceptDriftPanel, { modelName: MODEL, version: 'v1.0.0', refreshKey: 0 }));
    renderWithProviders(React.createElement(ConceptDriftPanel, { modelName: MODEL, version: 'v1.0.1', refreshKey: 0 }));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { resolveOld(jsonResponse(drift())); });
    expect(container?.textContent).toContain('v1.0.1');
    expect(container?.textContent).not.toContain('v1.0.0');
  });

  it('sentinel failure is unavailable, never disabled or writable', async () => {
    vi.mocked(advancedQuantApi.getDriftMonitorStatus).mockRejectedValue(new Error('https://user:secret@host'));
    renderWithProviders(React.createElement(DriftMonitorPanel));
    await act(async () => { await Promise.resolve(); });
    expect(container?.textContent).toContain('SENTINEL UNAVAILABLE');
    expect(container?.textContent).not.toContain('secret');
    expect(container?.textContent).not.toContain('SENTINEL DISABLED');
    expect(container?.textContent).not.toContain('certified variance');
    expect(container?.textContent).toContain('Sentinel incidents unavailable.');
    expect(container?.querySelector('button:disabled')).not.toBeNull();
  });

  it('successful concept drift renders real zero metrics and window units', async () => {
    renderWithProviders(React.createElement(ConceptDriftPanel, { modelName: MODEL, version: 'v1.0.0', refreshKey: 0 }));
    await act(async () => { await Promise.resolve(); });
    expect(container?.textContent).toContain('NO DRIFT DETECTED');
    expect(container?.textContent).toContain('VND_FULL');
    expect(container?.querySelector('table')?.textContent).toContain('0.0000');
    expect(container?.textContent).toContain('unverified');
  });

  it('empty threshold blocks writes; failed saves after unmount stay silent', async () => {
    const status = { status: 'success', enabled: true, schedule: '0 2 * * *', timezone: 'UTC', revision: 1, evaluated_model_ids: [MODEL], missing_model_ids: [], thresholds: { sharpe_drop: 0.3, ic_drop: 0.015, turnover_spike: 0.1 }, heartbeat: '2026-10-10T00:00:00Z', last_run: null, next_run: null, last_job: null, alerts: [] };
    vi.mocked(advancedQuantApi.getDriftMonitorStatus).mockResolvedValue(status);
    let rejectSave!: (error: Error) => void;
    vi.spyOn(advancedQuantApi, 'updateDriftSchedule').mockImplementation(() => new Promise((_resolve, reject) => { rejectSave = reject; }));
    renderWithProviders(React.createElement(DriftMonitorPanel));
    await act(async () => { await Promise.resolve(); });
    const input = container!.querySelector<HTMLInputElement>('#sentinel-ic')!;
    const save = [...container!.querySelectorAll('button')].find((button) => button.textContent?.includes('Save'))!;
    const change = (value: string) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    };
    act(() => { change(''); });
    act(() => { save.click(); });
    expect(advancedQuantApi.updateDriftSchedule).not.toHaveBeenCalled();
    expect(container?.textContent).toContain('Invalid schedule or thresholds');
    act(() => { change('0.015'); });
    act(() => { save.click(); save.click(); });
    expect(advancedQuantApi.updateDriftSchedule).toHaveBeenCalledTimes(1);
    act(() => { root!.unmount(); });
    root = null;
    const toasts = useUiStore.getState().toasts.length;
    await act(async () => { rejectSave(new Error('secret')); });
    expect(useUiStore.getState().toasts).toHaveLength(toasts);
    expect(advancedQuantApi.getDriftMonitorStatus).toHaveBeenCalledTimes(1);
  });

  it('3. QuantControlCenter integrates Model Governance and Resource Governor telemetry', async () => {
    renderWithProviders(React.createElement(QuantControlCenter, null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(advancedQuantApi.getResourceGovernor).toHaveBeenCalledTimes(1);
  });
});


describe('Slice15 unknown envelope adversarial boundaries', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
  it.each([null, undefined, [], '', 1, NaN, Infinity])('rejects malformed envelope %s', (value) => {
    expect(() => validateModelCatalog(value)).toThrow();
    expect(() => validateModelVersions(value, MODEL)).toThrow();
    expect(() => validateModelLineage(value, MODEL, 'v1.0.0')).toThrow();
    expect(() => validateConceptDrift(value, MODEL, 'v1.0.0')).toThrow();
    expect(() => validateMonitorStatus(value)).toThrow();
  });
  it.each([NaN, Infinity, -Infinity, -1, 1e12 + 1, '0', [], null])('rejects invalid PSI %s', (value) => {
    const data = drift(); (data.metrics[0] as any).psi = value;
    expect(() => validateConceptDrift(data, MODEL, 'v1.0.0')).toThrow();
  });
  it('keeps zero metrics and inclusive 15:30 ICT availability', () => {
    expect(validateConceptDrift(drift(), MODEL, 'v1.0.0').metrics[0].psi).toBe(0);
    expect(registryTime('2026-10-10T15:30:00+07:00')).toBe(registryTime('2026-10-10T08:30:00Z'));
  });
  it.each(['2026-02-30T00:00:00Z', '2026-10-10', '2026-10-10T00:00:00', '2026-10-10T25:00:00Z', 'NaN'])('rejects invalid timestamp %s', (value) => {
    expect(() => registryTime(value)).toThrow();
  });
  it('preserves microsecond ordering within a millisecond', () => {
    expect(registryTime('2026-10-10T08:30:00.000002Z')).toBeGreaterThan(registryTime('2026-10-10T08:30:00.000001Z'));
    const data = drift();
    data.current_window.available_at = '2026-10-10T08:30:00.000002Z';
    data.evaluated_at = '2026-10-10T08:30:00.000001Z';
    expect(() => validateConceptDrift(data, MODEL, 'v1.0.0')).toThrow();
  });
  it.each(['model_name', 'version', 'provenance_status', 'automated_retrain', 'automated_deploy'])('rejects evidence binding or automation %s', (field) => {
    for (const data of [drift(), lineage()]) {
      (data as any)[field] = field.startsWith('automated') ? true : 'wrong';
      const validate = 'nodes' in data ? validateModelLineage : validateConceptDrift;
      expect(() => validate(data, MODEL, 'v1.0.0')).toThrow();
      delete (data as any)[field];
      expect(() => validate(data, MODEL, 'v1.0.0')).toThrow();
    }
  });
  it.each(['duplicate', 'self', 'missing', 'cycle', 'missing-selected', 'false-complete'])('rejects invalid graph %s', (kind) => {
    const data = lineage();
    if (kind === 'duplicate') data.nodes.push({ ...data.nodes[0] });
    if (kind === 'self') data.nodes[0].parent_versions = ['v1.0.0'];
    if (kind === 'missing') data.nodes[0].parent_versions = ['v9.0.0'];
    if (kind === 'cycle') { data.nodes[0].parent_versions = ['v1.0.1']; data.nodes.push({ ...data.nodes[0], version: 'v1.0.1', parent_versions: ['v1.0.0'] }); }
    if (kind === 'missing-selected') data.nodes[0].version = 'v1.0.1';
    if (kind === 'false-complete') data.evidence_status = 'recorded';
    expect(() => validateModelLineage(data, MODEL, 'v1.0.0')).toThrow();
  });
  it.each(['snapshot-order', 'training-order', 'deployment-order', 'receipt-version', 'missing-field'])('rejects invalid lineage evidence %s', (kind) => {
    const data: any = lineage();
    Object.assign(data.nodes[0], { dataset_snapshot: { dataset_id: 'prices', version: 'snapshot1', content_hash: 'a'.repeat(64), as_of: '2026-10-09T00:00:00Z', available_at: '2026-10-09T01:00:00Z' }, training_run: { run_id: 'run1', trained_at: '2026-10-09T02:00:00Z' }, deployment_receipt: { receipt_id: 'receipt1', version: 'v1.0.0', deployed_at: '2026-10-09T03:00:00Z' } });
    const node = data.nodes[0];
    if (kind === 'snapshot-order') node.dataset_snapshot.as_of = '2026-10-09T04:00:00Z';
    if (kind === 'training-order') node.training_run.trained_at = '2026-10-09T00:00:00Z';
    if (kind === 'deployment-order') node.deployment_receipt.deployed_at = '2026-10-09T00:00:00Z';
    if (kind === 'receipt-version') node.deployment_receipt.version = 'v9.0.0';
    if (kind === 'missing-field') delete node.training_run;
    expect(() => validateModelLineage(data, MODEL, 'v1.0.0')).toThrow();
  });
  it('bounds graphs and accepts a deep acyclic lineage without recursion', () => {
    const data = lineage();
    data.nodes = Array.from({ length: 4096 }, (_, index) => ({ ...data.nodes[0], version: `v1.0.${index}`, parent_versions: index ? [`v1.0.${index - 1}`] : [] }));
    expect(validateModelLineage(data, MODEL, 'v1.0.0').nodes).toHaveLength(4096);
    data.nodes.push({ ...data.nodes[0], version: 'v1.0.4096' });
    expect(() => validateModelLineage(data, MODEL, 'v1.0.0')).toThrow();
  });
  it('accepts multiple roots and branches because backend returns all versions', () => {
    const data = lineage(); data.nodes.push({ ...data.nodes[0], version: 'v1.0.1', parent_versions: ['v1.0.0'] }, { ...data.nodes[0], version: 'v2.0.0' });
    expect(validateModelLineage(data, MODEL, 'v1.0.0').nodes).toHaveLength(3);
  });
  it.each(['reversed', 'overlap', 'future', 'unit', 'samples', 'zero-samples', 'duplicates', 'aggregate', 'threshold'])('rejects invalid drift branch %s', (kind) => {
    const data = drift();
    if (kind === 'reversed') data.current_window.start = data.current_window.end;
    if (kind === 'overlap') data.current_window.start = '2026-10-09T12:00:00Z';
    if (kind === 'future') data.current_window.available_at = '2026-10-11T00:00:00Z';
    if (kind === 'unit') data.current_window.unit = 'UNITLESS';
    if (kind === 'samples') data.current_window.sample_counts.price = 10001;
    if (kind === 'zero-samples') data.current_window.sample_counts.price = 0;
    if (kind === 'duplicates') data.metrics.push({ ...data.metrics[0] });
    if (kind === 'aggregate') data.drift_detected = true;
    if (kind === 'threshold') data.metrics[0].psi = 0.2;
    expect(() => validateConceptDrift(data, MODEL, 'v1.0.0')).toThrow();
  });
  it('rejects duplicate/overflow catalog and duplicate versions', () => {
    const model = { model_name: MODEL, active_versions: {}, total_versions: 0 };
    expect(() => validateModelCatalog({ status: 'success', count: 2, models: [model, model] })).toThrow();
    expect(() => validateModelCatalog({ status: 'success', count: 1, models: [{ ...model, total_versions: Infinity }] })).toThrow();
    const version = { version: 'v1.0.0', status: 'STAGING', metadata: {}, registered_at: '2026-10-10T00:00:00Z' };
    expect(() => validateModelVersions({ status: 'success', model_name: MODEL, versions: [version, version] }, MODEL)).toThrow();
  });
  it.each(['bad-json', 'bom', 'invalid-utf8', 'oversize', 'http', 'rate-limit', 'network', 'spoofed-prefix'])('bounded GET rejects %s without secrets', async (kind) => {
    let response = new Response('not-json');
    if (kind === 'bom') response = new Response(new Uint8Array([239,187,191,123,125]));
    if (kind === 'invalid-utf8') response = new Response(new Uint8Array([255]));
    if (kind === 'oversize') response = new Response(' '.repeat(1048577));
    if (kind === 'http') response = new Response('https://user:secret@host', { status: 500 });
    if (kind === 'rate-limit') response = new Response('secret', { status: 429 });
    vi.stubGlobal('fetch', ['network', 'spoofed-prefix'].includes(kind) ? vi.fn().mockRejectedValue(new Error('Registry response https://user:secret@host')) : vi.fn().mockResolvedValue(response));
    await expect(getRegistryEvidence(MODEL, 'v1.0.0', 'lineage', new AbortController().signal)).rejects.not.toThrow('secret');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('aborts timeout with no retry', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_path, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('abort'))))));
    const result = getRegistryEvidence(MODEL, 'v1.0.0', 'lineage', new AbortController().signal);
    const assertion = expect(result).rejects.toThrow('unavailable');
    await vi.advanceTimersByTimeAsync(10000);
    await assertion;
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('rejects identifier injection before network', async () => {
    vi.stubGlobal('fetch', vi.fn());
    await expect(getRegistryEvidence('../bad', 'v1.0.0', 'lineage', new AbortController().signal)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('Slice19 operations boundaries', () => {
  it('accepts zero, null, inclusive ICT close and microsecond ordering', () => {
    expect(validateSystemTelemetry(systemFrame()).cpu_usage_pct).toBe(0);
    const frame = systemFrame(); frame.memory_usage_mb = null as any;
    expect(validateSystemTelemetry(frame).memory_usage_mb).toBeNull();
    expect(operationsTime('2026-10-10T15:30:00+07:00')).toBe(operationsTime(frame.as_of));
    expect(operationsTime('2026-10-10T08:30:00.000002Z')).toBeGreaterThan(operationsTime('2026-10-10T08:30:00.000001Z'));
    expect(validateOperationsBreaker(breakerFrame(true)).triggered_at).toBe(frame.as_of);
    expect(validateResourceGovernor(governorFrame()).active_workers).toBe(0);
  });
  it.each([undefined, NaN, Infinity, -Infinity, -1, 101, 1e13, '', '10', [], {}])('rejects malformed measurements %s', (bad) => {
    expect(() => validateSystemTelemetry({ ...systemFrame(), cpu_usage_pct: bad })).toThrow();
    expect(() => validateResourceGovernor({ ...governorFrame(), system_load_pct: bad })).toThrow();
    if (bad !== 101) expect(() => validateGovernorUpdate({ target_concurrency: bad })).toThrow();
    else expect(validateGovernorUpdate({ target_concurrency: bad }).target_concurrency).toBe(101);
  });
  it.each([null, [], '', {}, { mode: undefined }, { mode: null }, { mode: 'AUTO' }, { mode: 'MANUAL', unexpected: true }, { batch_size: 10001 }, { thread_pool_size: 257 }, { target_concurrency: 129 }])('rejects malformed update before network %s', async (bad) => {
    vi.stubGlobal('fetch', vi.fn());
    await expect(advancedQuantApi.updateResourceGovernor(bad as any)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it.each(['schema', 'source', 'digest', 'synthetic', 'future', 'order', 'microseconds', 'unit', 'missing', 'extra', 'gpu', 'counter', 'queue'])('rejects telemetry contract drift %s', (kind) => {
    const r: any = systemFrame();
    if (kind === 'schema') r.schema_version = 'operations/v2';
    if (kind === 'source') r.provenance.source = 'caller_sample';
    if (kind === 'digest') r.provenance.sha256 = 'x';
    if (kind === 'synthetic') r.provenance.is_synthetic = true;
    if (kind === 'future') r.available_at = '2099-01-01T00:00:00Z';
    if (kind === 'order') r.as_of = '2026-10-11T00:00:00Z';
    if (kind === 'microseconds') { r.as_of = '2026-10-10T08:30:00.000002Z'; r.available_at = '2026-10-10T08:30:00.000001Z'; }
    if (kind === 'unit') r.memory_unit = 'GB';
    if (kind === 'missing') delete r.cpu_usage_pct;
    if (kind === 'extra') r.verified_pit = true;
    if (kind === 'gpu') r.gpu_telemetry = { usage_pct: 0, memory_usage_mb: 0, memory_unit: 'GB' };
    if (kind === 'counter') r.io_read_bytes = Number.MAX_SAFE_INTEGER + 1;
    if (kind === 'queue') r.ipc_queue_depth = 1e9 + 1;
    expect(() => validateSystemTelemetry(r)).toThrow();
  });
  it.each(['state', 'flag', 'reason', 'time', 'future', 'pnl', 'missing'])('rejects unsafe breaker contract %s', (kind) => {
    const r: any = breakerFrame(true);
    if (kind === 'state') r.state = 'normal';
    if (kind === 'flag') r.circuit_broken = false;
    if (kind === 'reason') r.reasons = ['https://user:secret@provider'];
    if (kind === 'time') r.triggered_at = null;
    if (kind === 'future') r.triggered_at = '2026-10-10T08:30:00.000001Z';
    if (kind === 'pnl') r.daily_pnl = 0;
    if (kind === 'missing') delete r.provenance;
    expect(() => validateOperationsBreaker(r)).toThrow();
  });
  it.each(['2026-02-30T00:00:00Z', '2026-10-10', '2026-10-10T00:00:00', '2026-10-10T24:00:00Z', 'NaN'])('rejects malformed time %s', (time) => expect(() => operationsTime(time)).toThrow());
});

describe('Slice19 Control Center lifecycle', () => {
  let container: HTMLDivElement, root: Root, initial: ReturnType<typeof useUiStore.getState>, unmounted: boolean;
  const settle = async () => { await act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); }); };
  const button = (text: string) => [...container.querySelectorAll('button')].find((item) => item.textContent === text)!;
  beforeEach(() => {
    initial = useUiStore.getState(); useUiStore.setState({ activeSubTabs: { ...initial.activeSubTabs, control_center: 'overview' }, isKillSwitchEngaged: false, toasts: [] });
    vi.spyOn(apiClient, 'getControlReceipts').mockResolvedValue({ status: 'success', receipts: [] } as any);
    vi.spyOn(advancedQuantApi, 'getSystemTelemetry').mockResolvedValue(systemFrame());
    vi.spyOn(advancedQuantApi, 'getOperationsCircuitBreaker').mockResolvedValue(breakerFrame());
    vi.spyOn(advancedQuantApi, 'getResourceGovernor').mockResolvedValue(governorFrame());
    vi.spyOn(advancedQuantApi, 'updateResourceGovernor').mockResolvedValue({ ...governorFrame(), mode: 'COPILOT', version: 2 });
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); unmounted = false;
  });
  afterEach(() => { if (!unmounted) act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); useUiStore.setState(initial, true); });
  const render = () => act(() => root.render(React.createElement(QuantControlCenter)));
  it('renders authoritative halt, measured zero, unavailable GPU and no purple; keeps ops drawer', async () => {
    vi.mocked(advancedQuantApi.getOperationsCircuitBreaker).mockResolvedValue(breakerFrame(true));
    render(); await settle();
    expect(container.textContent).toContain('SYSTEM HALTED'); expect(button('SYSTEM HALTED').disabled).toBe(true);
    expect(container.textContent).toContain('CPU usage (%)0.00'); expect(container.textContent).toContain('GPU usage (%)--');
    expect(container.textContent).toContain('bytes since boot'); expect(container.textContent).not.toContain('STANDBY ARMED');
    expect(container.innerHTML).not.toMatch(/purple|violet|fuchsia/i);
    act(() => button('OPEN OPS DRAWER').click()); expect(useUiStore.getState().isOpsDrawerOpen).toBe(true);
    expect(useUiStore.getState().isKillSwitchEngaged).toBe(false);
  });
  it('partial failure keeps independent telemetry; no false normal or raw secrets', async () => {
    vi.mocked(advancedQuantApi.getOperationsCircuitBreaker).mockRejectedValue(new Error('https://user:secret@provider'));
    render(); await settle();
    expect(container.textContent).toContain('BREAKER UNAVAILABLE'); expect(container.textContent).toContain('CPU usage (%)0.00');
    expect(container.textContent).not.toContain('secret'); expect(container.textContent).not.toContain('NORMAL');
  });
  it('serializes write, passes abort signal, reconciles unknown outcome before another write', async () => {
    let reject!: (error: Error) => void;
    vi.mocked(advancedQuantApi.updateResourceGovernor).mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
    render(); await settle(); act(() => { button('SWITCH TO COPILOT').click(); button('SWITCH TO COPILOT').click(); });
    expect(advancedQuantApi.updateResourceGovernor).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.updateResourceGovernor).toHaveBeenCalledWith({ mode: 'COPILOT' }, expect.any(AbortSignal));
    await act(async () => { reject(new Error('secret')); });
    expect(container.textContent).toContain('outcome unknown'); expect(button('SWITCH TO COPILOT').disabled).toBe(true);
    expect(container.textContent).not.toContain('secret');
    act(() => button('REFRESH OPERATIONS').click()); await settle(); expect(button('SWITCH TO COPILOT').disabled).toBe(false);
  });
  it.each(['read', 'write'])('tab exit aborts %s; late failure stays silent and reentry gets fresh state', async (kind) => {
    let reject!: (error: Error) => void, signal!: AbortSignal;
    if (kind === 'read') vi.mocked(advancedQuantApi.getSystemTelemetry).mockImplementationOnce((s) => { signal = s!; return new Promise((_resolve, fail) => { reject = fail; }); });
    render(); await settle();
    if (kind === 'write') { vi.mocked(advancedQuantApi.updateResourceGovernor).mockImplementationOnce((_p, s) => { signal = s!; return new Promise((_resolve, fail) => { reject = fail; }); }); act(() => button('SWITCH TO COPILOT').click()); }
    act(() => button('Receipts').click()); expect(signal.aborted).toBe(true);
    await act(async () => reject(new Error('secret'))); expect(useUiStore.getState().toasts).toHaveLength(0);
    expect(container.textContent).toContain('BREAKER UNAVAILABLE');
    act(() => button('Overview').click()); await settle(); expect(container.textContent).toContain('BREAKER NORMAL (OBSERVED)');
  });
  it('StrictMode ignores obsolete reads, serializes refresh and accepts confirmed mode updates', async () => {
    let stale!: (value: ReturnType<typeof systemFrame>) => void;
    vi.mocked(advancedQuantApi.getSystemTelemetry).mockImplementationOnce(() => new Promise((done) => { stale = done; }));
    act(() => root.render(React.createElement(React.StrictMode, null, React.createElement(QuantControlCenter)))); await settle();
    await act(async () => stale({ ...systemFrame(), cpu_usage_pct: 99 }));
    expect(container.textContent).toContain('CPU usage (%)0.00'); expect(container.textContent).not.toContain('99.00');
    act(() => { button('REFRESH OPERATIONS').click(); button('REFRESH OPERATIONS').click(); }); await settle();
    expect(advancedQuantApi.getSystemTelemetry).toHaveBeenCalledTimes(3);
    act(() => button('SWITCH TO COPILOT').click()); await settle();
    expect(button('SWITCH TO MANUAL').disabled).toBe(false);
  });
  it('write success after unmount is ignored; local authorized halt survives a normal observation', async () => {
    let resolve!: (value: ReturnType<typeof governorFrame>) => void, signal!: AbortSignal;
    useUiStore.setState({ isKillSwitchEngaged: true }); render(); await settle();
    expect(container.textContent).toContain('SYSTEM HALTED');
    vi.mocked(advancedQuantApi.updateResourceGovernor).mockImplementationOnce((_payload, s) => { signal = s!; return new Promise((done) => { resolve = done; }); });
    act(() => button('SWITCH TO COPILOT').click()); act(() => root.unmount()); unmounted = true;
    expect(signal.aborted).toBe(true); await act(async () => resolve(governorFrame())); expect(useUiStore.getState().toasts).toHaveLength(0);
  });
  it('late read success after unmount never publishes a breaker state', async () => {
    let resolve!: (value: ReturnType<typeof breakerFrame>) => void;
    vi.mocked(advancedQuantApi.getOperationsCircuitBreaker).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const observed = vi.fn(); act(() => root.render(React.createElement(OverviewTab, { activeTasks: [], isKillSwitchEngaged: false, onOpenOps: vi.fn(), onKillSwitch: vi.fn(), onBreakerObservation: observed })));
    act(() => root.unmount()); unmounted = true;
    await act(async () => resolve(breakerFrame(true))); expect(observed).not.toHaveBeenCalledWith(expect.objectContaining({ state: 'TRIGGERED' }));
  });
});

describe('Slice19 operations transport', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
  it.each([424, 422, 429, 500])('does not retry HTTP %s or disclose body', async (status) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('https://user:secret@provider', { status })));
    await expect(advancedQuantApi.getSystemTelemetry()).rejects.toThrow('Operations observation unavailable or invalid.');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each(['oversized', 'utf8', 'bom', 'malformed'])('rejects bounded JSON %s', async (kind) => {
    const body = kind === 'oversized' ? 'x'.repeat(65537) : kind === 'utf8' ? new Uint8Array([255]) : kind === 'bom' ? '﻿' + JSON.stringify(systemFrame()) : '{';
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body)));
    await expect(advancedQuantApi.getSystemTelemetry()).rejects.toThrow('Operations observation unavailable or invalid.');
  });
  it('accepts CRLF JSON and validated PATCH; fixed route and no caller query', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(systemFrame(), null, 2).replace(/\n/g, '\r\n'))));
    expect((await advancedQuantApi.getSystemTelemetry()).cpu_usage_pct).toBe(0);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(governorFrame())));
    await advancedQuantApi.updateResourceGovernor({ mode: 'MANUAL' });
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/v1/operations/resource-governor'), expect.objectContaining({ method: 'PATCH', body: '{"mode":"MANUAL"}' }));
  });
  it.each(['read', 'write'])('bounds %s timeout and leaves no timers', async (kind) => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init) => new Promise((_resolve, reject) => init!.signal!.addEventListener('abort', () => reject(new Error('secret'))))));
    const result = kind === 'read' ? advancedQuantApi.getSystemTelemetry() : advancedQuantApi.updateResourceGovernor({ mode: 'MANUAL' });
    const assertion = expect(result).rejects.toThrow(kind === 'read' ? 'Operations observation unavailable or invalid.' : 'outcome unknown');
    await vi.advanceTimersByTimeAsync(10000); await assertion; expect(fetch).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0);
  });
  it('pre-aborted reads do not fetch', async () => {
    vi.stubGlobal('fetch', vi.fn()); const controller = new AbortController(); controller.abort();
    await expect(advancedQuantApi.getSystemTelemetry(controller.signal)).rejects.toThrow(); expect(fetch).not.toHaveBeenCalled();
  });
});

const PIPE_JOB = 'job-pipe-1234abcd';
const pipelineFrame = (revision = 1, status = 'RUNNING', stage = 'DATA_INGEST') => ({
  schema_version: 'pipeline-telemetry/v1', revision, task_id: PIPE_JOB, job_id: PIPE_JOB,
  event_type: status === 'COMPLETED' ? 'COMPLETE' : status === 'FAILED' ? 'ERROR' : status === 'CANCELLED' ? 'CANCELLED' : 'PROGRESS',
  status, stage, progress: status === 'COMPLETED' ? 100 : 20, timestamp: '2026-10-11T08:30:00Z', message: 'Provider safe message', payload: {} as Record<string, unknown>,
  dag: PIPELINE_STAGES.map((name, i) => ({ stage_id: name, depends_on: i ? [PIPELINE_STAGES[i - 1]] : [],
    status: status === 'COMPLETED' || i < PIPELINE_STAGES.indexOf(stage as typeof PIPELINE_STAGES[number]) ? 'COMPLETED' : name === stage ? status : 'PENDING' })),
});
const pipelineReceipt = () => ({ schema_version: 1, task_id: PIPE_JOB, operation: 'PIPELINE_RUN', status: 'COMPLETED',
  request_fingerprint: 'a'.repeat(64), output_sha256: 'b'.repeat(64), receipt_hmac: 'c'.repeat(64), artifact_id: 'receipts/task.json', published_at: '2026-10-11T08:30:00Z' });

class PipelineSource {
  static instances: PipelineSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { PipelineSource.instances.push(this); }
  send(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
}

const macroBase = (source = 'parquet_store', is_synthetic = false) => ({ status: 'success', as_of: '2026-10-10T08:30:00.000000001Z', source, is_synthetic });
const macroArticle = () => ({ news_id: 'news-1', title: 'Policy update', source: 'News desk', symbol: 'FPT', sector: 'Technology', summary: '<script>not executable</script>', sentiment_score: 0, polarity: 'NEUTRAL', macro_tags: ['SBV'], entities: ['SBV'], published_at: '2026-10-10T15:30:00+07:00', available_at: '2026-10-10T08:30:00.000000001Z', url: 'https://user:secret@host' });
const macroNews = () => ({ ...macroBase(), total_count: 1, items: [macroArticle()] });
const macroVSI = () => ({ ...macroBase('vsi_engine'), score: 50, level: 'neutral', article_count: 1, avg_sentiment: 0, bullish_ratio: 0, bearish_ratio: 0, neutral_ratio: 1, sub_indices: { retail_sentiment: 50 }, history_7d: [{ date: '2026-10-10', as_of: '2026-10-10T08:30:00Z', vsi_score: 50, level: 'neutral', article_count: 1 }] });
const macroContagion = () => ({ ...macroBase('synthetic_simulation', true), overall_contagion_index: 0, systemic_risk_level: 'LOW', nodes: [{ sector: 'Technology', stress_score: 0, contagion_level: 'LOW', trend_24h: 'STABLE', sentiment_delta: 0, transmission_risk: 0, correlated_sectors: [{ sector: 'Telecommunication', correlation_weight: 0 }] }] });
const macroIntelligence = () => ({ ...macroBase('synthetic_simulation', true), model: 'synthetic_macro_template', prompt_version: 'v1', regime_summary: 'Demonstration only', primary_risks: ['Rates'], catalysts: ['Policy'], sector_impacts: { Technology: 'No measured effect' }, macro_tags: ['SBV'], key_entities: ['SBV'], sentiment_confidence: 0, executive_verdict: 'Not trading advice' });
const macroReply = (url: string) => url.includes('/news/latest') ? macroNews() : url.includes('/vsi?') ? macroVSI() : url.includes('/contagion') ? macroContagion() : macroIntelligence();

describe('Slice21 macro news lifecycle', () => {
  let container: HTMLDivElement, root: Root, unmounted: boolean;
  let initial: ReturnType<typeof useUiStore.getState>;
  const settle = async () => { await act(async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); }); };
  const render = (strict = false) => act(() => root.render(React.createElement(strict ? React.StrictMode : React.Fragment, null, React.createElement(MacroNewsHubView))));
  const button = (name: string) => container.querySelector<HTMLButtonElement>(`button[aria-label="${name}"]`)!;
  beforeEach(() => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-11T08:30:00Z'));
    initial = useUiStore.getState(); useUiStore.setState({ ...initial, locale: 'en' }, true);
    vi.stubGlobal('fetch', vi.fn(async (url: string) => jsonResponse(macroReply(url))));
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); unmounted = false;
  });
  afterEach(() => { if (!unmounted) act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); useUiStore.setState(initial, true); });
  it('renders honest independent snapshots, measured zero, matrix external targets and no purple', async () => {
    render(); await settle(); expect(fetch).toHaveBeenCalledTimes(4);
    expect(container.textContent).toContain('SIMULATION — Not live evidence'); expect(container.textContent).toContain('Observed — Not PIT-verified');
    expect(container.querySelector('meter')?.value).toBe(50); expect(container.textContent).toContain('0.0%');
    expect(container.querySelector('section[aria-label="Sector contagion matrix"] table')?.textContent).toContain('Telecommunication'); expect(container.textContent).toContain('0.00');
    expect(container.textContent).not.toContain('secret'); expect(container.querySelector('script')).toBeNull(); expect(container.querySelector('a')).toBeNull();
    expect(container.innerHTML).not.toMatch(/purple|violet|fuchsia/i); expect(container.textContent).not.toContain('SSE STREAM ACTIVE');
    const input = container.querySelector('input')!;
    act(() => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'missing'); input.dispatchEvent(new Event('input', { bubbles: true })); });
    expect(container.textContent).toContain('No news matching filters.');
    act(() => useUiStore.getState().setLocale('vi')); expect(container.textContent).toContain('Trung tâm tin tức vĩ mô'); expect(fetch).toHaveBeenCalledTimes(4);
  });
  it('isolates failure, clears old data, serializes manual retry and never exposes errors', async () => {
    render(); await settle(); vi.mocked(fetch).mockImplementation(async (url) => String(url).includes('/vsi?') ? new Response('secret', { status: 429 }) : jsonResponse(macroReply(String(url))));
    act(() => { button('Refresh Vietnam Sentiment Index (VSI)').click(); button('Refresh Vietnam Sentiment Index (VSI)').click(); }); await settle();
    expect(fetch).toHaveBeenCalledTimes(5); expect(container.querySelector('meter')).toBeNull(); expect(container.textContent).toContain('Observation unavailable or invalid.'); expect(container.textContent).toContain('Policy update');
    await act(async () => { await vi.advanceTimersByTimeAsync(120000); }); expect(fetch).toHaveBeenCalledTimes(5); expect(container.textContent).not.toContain('secret');
    vi.mocked(fetch).mockImplementation(async (url) => jsonResponse(macroReply(String(url)))); act(() => button('Refresh Vietnam Sentiment Index (VSI)').click()); await settle(); expect(container.querySelector('meter')).not.toBeNull();
  });
  it('aborts all unmounted reads and ignores StrictMode obsolete completion', async () => {
    let resolve!: (value: Response) => void, oldSignal!: AbortSignal;
    vi.mocked(fetch).mockImplementationOnce((_url, init) => { oldSignal = init!.signal as AbortSignal; return new Promise((done) => { resolve = done; }); });
    render(true); await settle(); expect(oldSignal.aborted).toBe(true);
    await act(async () => resolve(jsonResponse({ ...macroNews(), items: [{ ...macroArticle(), title: 'obsolete' }] }))); await settle(); expect(container.textContent).not.toContain('obsolete');
    const signals: AbortSignal[] = [];
    vi.mocked(fetch).mockImplementation((_url, init) => { signals.push(init!.signal as AbortSignal); return new Promise(() => {}); });
    act(() => root.render(null)); render(); await settle(); act(() => root.unmount()); unmounted = true; expect(signals).toHaveLength(4); expect(signals.every((signal) => signal.aborted)).toBe(true); expect(vi.getTimerCount()).toBe(0);
  });
  it('shows no-sample VSI and empty news without invented scores', async () => {
    vi.mocked(fetch).mockImplementation(async (url) => jsonResponse(String(url).includes('/vsi?') ? { ...macroVSI(), article_count: 0, neutral_ratio: 0 } : String(url).includes('/news/latest') ? { ...macroNews(), total_count: 0, items: [] } : macroReply(String(url))));
    render(); await settle(); expect(container.querySelector('meter')).toBeNull(); expect(container.textContent).toContain('VSI unavailable — No article samples.'); expect(container.textContent).toContain('No news matching filters.');
  });
  it.each([null, undefined, [], '', 1, NaN, Infinity, -Infinity])('rejects malformed envelopes %s', (bad) => {
    for (const validate of [validateMacroNews, validateMacroVSI, validateMacroContagion, validateMacroIntelligence]) expect(() => validate(bad)).toThrow();
  });
  it.each([null, '0', [], NaN, Infinity, -Infinity, -1, 1e12 + 1])('rejects invalid bounded numeric payloads %s', (bad) => {
    expect(() => validateMacroVSI({ ...macroVSI(), score: bad })).toThrow(); expect(() => validateMacroContagion({ ...macroContagion(), overall_contagion_index: bad })).toThrow(); expect(() => validateMacroIntelligence({ ...macroIntelligence(), sentiment_confidence: bad })).toThrow();
  });
  it.each(['future', 'availability', 'nanosecond', 'duplicate', 'tags', 'title', 'synthetic', 'status', 'oversize'])('rejects news drift %s', (kind) => {
    const data: any = macroNews();
    if (kind === 'future') data.as_of = '2099-01-01T00:00:00Z'; if (kind === 'availability') data.items[0].available_at = '2026-10-09T00:00:00Z';
    if (kind === 'nanosecond') data.items[0].available_at = '2026-10-10T08:30:00.000000002Z'; if (kind === 'duplicate') { data.items.push(data.items[0]); data.total_count = 2; }
    if (kind === 'tags') data.items[0].macro_tags = [null]; if (kind === 'title') data.items[0].title = {}; if (kind === 'synthetic') delete data.is_synthetic;
    if (kind === 'status') data.status = 'failed'; if (kind === 'oversize') data.items = Array(101).fill(data.items[0]); expect(() => validateMacroNews(data)).toThrow();
  });
  it.each(['ratios', 'level', 'history-future', 'history-duplicate', 'history-date', 'indices', 'confidence', 'impact', 'edge', 'node', 'delta', 'transmission'])('rejects indicator drift %s', (kind) => {
    const vsi: any = macroVSI(), contagion: any = macroContagion(), intelligence: any = macroIntelligence();
    if (kind === 'ratios') vsi.neutral_ratio = 0; if (kind === 'level') vsi.level = 'unknown'; if (kind === 'history-future') vsi.history_7d[0].as_of = '2099-01-01T00:00:00Z'; if (kind === 'history-duplicate') vsi.history_7d.push(vsi.history_7d[0]); if (kind === 'history-date') vsi.history_7d[0].date = '2026-10-09'; if (kind === 'indices') vsi.sub_indices = { bad: NaN };
    if (kind === 'confidence') intelligence.sentiment_confidence = 2; if (kind === 'impact') intelligence.sector_impacts = { bad: [] }; if (kind === 'edge') contagion.nodes[0].correlated_sectors.push(contagion.nodes[0].correlated_sectors[0]); if (kind === 'node') contagion.nodes.push(contagion.nodes[0]); if (kind === 'delta') contagion.nodes[0].sentiment_delta = -2; if (kind === 'transmission') contagion.nodes[0].transmission_risk = 2;
    expect(() => kind.startsWith('history') || ['ratios', 'level', 'indices'].includes(kind) ? validateMacroVSI(vsi) : ['confidence', 'impact'].includes(kind) ? validateMacroIntelligence(intelligence) : validateMacroContagion(contagion)).toThrow();
  });
  it('preserves inclusive ICT close, nanosecond ordering and zero values', () => {
    expect(validateMacroVSI({ ...macroVSI(), score: 81, level: 'greed' }).level).toBe('greed');
    expect(macroTime('2026-10-10T15:30:00+07:00')).toBe(macroTime('2026-10-10T08:30:00Z'));
    expect(macroTime('2026-10-10T08:30:00.000000002Z') - macroTime('2026-10-10T08:30:00.000000001Z')).toBe(1n);
    expect(validateMacroNews(macroNews()).items[0].sentiment_score).toBe(0); expect(validateMacroContagion(macroContagion()).nodes[0].transmission_risk).toBe(0);
    for (const time of ['2026-02-30T08:30:00Z', '2026-10-10T24:00:00Z', '2026-10-10T08:30:00', '', null]) expect(() => macroTime(time)).toThrow();
  });
  it.each(['bad-json', 'null', 'bom', 'utf8', 'large', '429', '424', '500', 'network'])('bounds all four GET failure branches %s', async (kind) => {
    vi.mocked(fetch).mockImplementation(async () => {
      if (kind === 'network') throw new Error('https://user:secret@host');
      const body = kind === 'null' ? 'null' : kind === 'bom' ? '﻿{}' : kind === 'utf8' ? new Uint8Array([255]) : kind === 'large' ? 'x'.repeat(1048577) : '{';
      return new Response(body, { status: ['429', '424', '500'].includes(kind) ? Number(kind) : 200 });
    });
    for (const call of [() => apiClient.getMacroNewsLatest(), () => apiClient.getVSISentiment(), () => apiClient.getSectorContagion(), () => apiClient.getLLMMacroAnalysis()]) await expect(call()).rejects.toThrow('Macro observation unavailable or invalid.');
    expect(fetch).toHaveBeenCalledTimes(4); expect(vi.getTimerCount()).toBe(0);
  });
  it('accepts CRLF, encodes filters, rejects invalid queries before network', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(macroNews(), null, 2).replace(/\n/g, '\r\n')));
    await apiClient.getMacroNewsLatest({ limit: 1, ticker: 'FPT&limit=99', sector: 'A/B', as_of: '2026-10-10T15:30:00+07:00' });
    const url = new URL(String(vi.mocked(fetch).mock.calls[0][0]), 'https://example.com'); expect(url.searchParams.get('ticker')).toBe('FPT&limit=99'); expect(url.searchParams.get('limit')).toBe('1');
    vi.mocked(fetch).mockClear(); for (const limit of [0, -1, 101, NaN, Infinity]) await expect(apiClient.getMacroNewsLatest({ limit })).rejects.toThrow();
    const controller = new AbortController(); controller.abort(); await expect(apiClient.getSectorContagion(controller.signal)).rejects.toThrow(); expect(fetch).not.toHaveBeenCalled();
  });
  it.each(['fetch', 'body'])('times out stalled %s even when fetch ignores abort, with no retry', async (kind) => {
    vi.mocked(fetch).mockImplementation(() => kind === 'fetch' ? new Promise(() => {}) : Promise.resolve(new Response(new ReadableStream({ start() {} }))));
    const request = apiClient.getVSISentiment(), assertion = expect(request).rejects.toThrow('Macro observation unavailable or invalid.'); await vi.advanceTimersByTimeAsync(10000); await assertion; expect(fetch).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0);
  });
});

describe('Slice17 pipeline console lifecycle', () => {
  let container: HTMLDivElement;
  let root: Root;
  let unmounted: boolean;
  const initial = useUiStore.getState();
  const button = (name: string) => [...container.querySelectorAll('button')].find((item) => item.textContent === name)!;
  const settle = async () => { await act(async () => { await Promise.resolve(); await Promise.resolve(); }); };
  const dispatch = async () => { act(() => button('Run pipeline').click()); await settle(); return PipelineSource.instances.at(-1)!; };
  beforeEach(() => {
    vi.useFakeTimers();
    useUiStore.setState({ ...initial, locale: 'en' }, true);
    PipelineSource.instances = [];
    vi.stubGlobal('EventSource', PipelineSource);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'success', job_id: PIPE_JOB, task_id: PIPE_JOB, stream_url: `/sse/v1/pipeline/${PIPE_JOB}/stream` })));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); unmounted = false;
    act(() => root.render(React.createElement(PipelineOrchestrationConsole)));
  });
  afterEach(() => {
    if (!unmounted) act(() => root.unmount());
    container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); useUiStore.setState(initial, true);
  });
  it('dispatches exact contract once and renders real DAG; heartbeat never changes execution state', async () => {
    expect(container.textContent).toContain('Awaiting server DAG telemetry');
    act(() => { button('Run pipeline').click(); button('Run pipeline').click(); }); await settle();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/control/pipeline-run'), expect.objectContaining({ method: 'POST', body: expect.stringContaining('IN_PROCESS') }));
    const stream = PipelineSource.instances[0];
    act(() => stream.send(pipelineFrame()));
    expect(container.querySelector('progress')?.value).toBe(20);
    expect(container.querySelectorAll('ol[aria-label="Pipeline stages"] li')).toHaveLength(5);
    act(() => stream.send({ ...pipelineFrame(), event_type: 'PING' }));
    expect(container.querySelectorAll('ol[aria-label="Stage event history"] li')).toHaveLength(1);
    expect(container.textContent).not.toContain('Provider safe message');
  });
  it('accepts receipt-bearing terminal snapshot and ignores closed-source callbacks', async () => {
    const stream = await dispatch(); const done = pipelineFrame(5, 'COMPLETED', 'RESEARCH_EXECUTION'); done.event_type = 'SNAPSHOT'; done.payload.receipt = pipelineReceipt();
    act(() => stream.send(done)); expect(stream.close).toHaveBeenCalled(); expect(container.textContent).toContain('not independently verified');
    act(() => stream.send(pipelineFrame(6))); expect(container.querySelector('progress')?.value).toBe(100);
    expect(button('Cancel task').disabled).toBe(true);
  });
  it.each(['malformed', 'wrong-job', 'receipt', 'nan', 'dag', 'large', 'regression'])('fails closed on %s without inferring terminal task failure', async (kind) => {
    const stream = await dispatch(); act(() => stream.send(pipelineFrame()));
    const bad = pipelineFrame(2);
    if (kind === 'wrong-job') bad.task_id = 'other';
    if (kind === 'receipt') Object.assign(bad, pipelineFrame(2, 'COMPLETED', 'RESEARCH_EXECUTION'));
    if (kind === 'nan') bad.progress = NaN;
    if (kind === 'dag') bad.dag[0].depends_on = ['DATA_INGEST'];
    if (kind === 'large') bad.message = 'x'.repeat(65537);
    if (kind === 'regression') bad.progress = 1;
    act(() => kind === 'malformed' ? stream.onmessage?.({ data: '{' }) : stream.send(bad));
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Invalid pipeline telemetry');
    expect(button('Run pipeline').disabled).toBe(true); expect(button('Reconnect telemetry').disabled).toBe(false);
    expect(container.textContent).not.toContain('Pipeline failed.');
  });
  it('reconnects the same task without dispatch and bounds silence and stale callbacks', async () => {
    const first = await dispatch(); act(() => first.send(pipelineFrame()));
    act(() => first.onerror?.()); expect(first.close).toHaveBeenCalled();
    act(() => button('Reconnect telemetry').click()); const second = PipelineSource.instances[1];
    expect(second.url).toBe(first.url); expect(fetch).toHaveBeenCalledTimes(1);
    act(() => first.send(pipelineFrame(99, 'FAILED'))); expect(container.textContent).not.toContain('Pipeline failed.');
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(container.textContent).toContain('Telemetry timeout'); expect(second.close).toHaveBeenCalled();
  });
  it('cancel failures remain visible; cancellation requires authoritative snapshot', async () => {
    await dispatch(); vi.mocked(fetch).mockResolvedValueOnce(new Response('', { status: 409 }));
    act(() => button('Cancel task').click()); await settle(); expect(container.textContent).toContain('Cancellation not confirmed');
    expect(button('Run pipeline').disabled).toBe(true);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ status: 'success', task_id: PIPE_JOB, job_id: PIPE_JOB, cancelled: true }));
    act(() => { button('Cancel task').click(); button('Cancel task').click(); }); await settle();
    expect(fetch).toHaveBeenCalledTimes(3); expect(button('Run pipeline').disabled).toBe(true);
    act(() => PipelineSource.instances.at(-1)!.send(pipelineFrame(2, 'CANCELLED')));
    expect(button('Run pipeline').disabled).toBe(false);
  });
  it('terminal execution wins a late cancel response; retries only explicit retryable failures', async () => {
    const stream = await dispatch(); let resolve!: (response: Response) => void;
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    act(() => button('Cancel task').click());
    const done = pipelineFrame(2, 'COMPLETED', 'RESEARCH_EXECUTION'); done.payload.receipt = pipelineReceipt(); act(() => stream.send(done));
    resolve(jsonResponse({ status: 'success', task_id: PIPE_JOB, job_id: PIPE_JOB, cancelled: true })); await settle();
    expect(PipelineSource.instances).toHaveLength(1); expect(container.querySelector('progress')?.value).toBe(100);
    expect(button('Retry as new task').disabled).toBe(true);
  });
  it('retry dispatches saved parameters only after server-reported retryable failure', async () => {
    const stream = await dispatch(); const failed = pipelineFrame(2, 'FAILED'); failed.payload.retryable = true; act(() => stream.send(failed));
    act(() => button('Retry as new task').click()); await settle(); expect(fetch).toHaveBeenCalledTimes(2);
    expect(vi.mocked(fetch).mock.calls[1][1]?.body).toBe(vi.mocked(fetch).mock.calls[0][1]?.body);
  });
  it.each([403, 422, 429, 500])('handles dispatch HTTP %s with bounded explicit error', async (status) => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response('https://user:secret@host/?key=secret', { status })); await dispatch();
    expect(container.querySelector('[role="alert"]')).not.toBeNull(); expect(container.textContent).not.toContain('secret');
    expect(button('Run pipeline').disabled).toBe(status === 500);
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); }); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('timeouts and malformed dispatch prevent duplicate work; unmount aborts in-flight requests', async () => {
    let signal!: AbortSignal;
    vi.mocked(fetch).mockImplementation((_input, init) => new Promise((_resolve, reject) => { signal = init!.signal as AbortSignal; signal.addEventListener('abort', () => reject(new Error('secret')), { once: true }); }));
    act(() => button('Run pipeline').click()); await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(signal.aborted).toBe(true); expect(container.textContent).toContain('Dispatch outcome unknown'); expect(button('Run pipeline').disabled).toBe(true);
    act(() => root.unmount()); unmounted = true;
  });
  it.each(['malformed', 'off-origin', 'oversized', 'invalid-utf8', 'offline'])('rejects %s dispatch without exposing response details or opening SSE', async (kind) => {
    const reply = { status: 'success', job_id: PIPE_JOB, task_id: PIPE_JOB, stream_url: 'https://user:secret@other/stream' };
    if (kind === 'offline') vi.mocked(fetch).mockRejectedValueOnce(new Error('https://user:secret@provider'));
    else vi.mocked(fetch).mockResolvedValueOnce(kind === 'off-origin' ? jsonResponse(reply) : new Response(kind === 'oversized' ? 'x'.repeat(65537) : kind === 'invalid-utf8' ? new Uint8Array([255]) : '{'));
    await dispatch(); expect(PipelineSource.instances).toHaveLength(0); expect(button('Run pipeline').disabled).toBe(true);
    expect(container.textContent).toContain('Dispatch outcome unknown'); expect(container.textContent).not.toContain('secret');
  });
  it('unmount aborts dispatch and never opens a late stream', async () => {
    let resolve!: (response: Response) => void; let signal!: AbortSignal;
    vi.mocked(fetch).mockImplementationOnce((_url, init) => new Promise((done) => { resolve = done; signal = init!.signal as AbortSignal; }));
    act(() => button('Run pipeline').click()); act(() => root.unmount()); unmounted = true;
    expect(signal.aborted).toBe(true);
    resolve(jsonResponse({ status: 'success', job_id: PIPE_JOB, task_id: PIPE_JOB, stream_url: `/sse/v1/pipeline/${PIPE_JOB}/stream` })); await settle();
    expect(PipelineSource.instances).toHaveLength(0);
  });
  it('unmount closes stream, clears timers and ignores late callbacks', async () => {
    const stream = await dispatch(); act(() => root.unmount()); unmounted = true;
    expect(stream.close).toHaveBeenCalled(); act(() => stream.send(pipelineFrame())); expect(vi.getTimerCount()).toBe(0);
  });
  it('bounds event history at 100 and ignores duplicate revisions', async () => {
    const stream = await dispatch(); act(() => { for (let i = 1; i <= 110; i++) stream.send(pipelineFrame(i)); stream.send(pipelineFrame(1)); });
    expect(container.querySelectorAll('ol[aria-label="Stage event history"] li')).toHaveLength(100);
  });
});

describe('Slice17 pipeline boundary validation', () => {
  it.each([null, [], '', NaN, Infinity, -Infinity, {}, { ...pipelineFrame(), progress: 1e12 }, { ...pipelineFrame(), revision: -1 }])('rejects malformed telemetry %j', (value) => {
    expect(() => validatePipelineTelemetry(value, PIPE_JOB)).toThrow();
  });
  it.each(['', 'NaN', 'Infinity', '-Infinity', '0', '-1', '1000000000001'])('rejects capital %s', (capital) => {
    expect(() => pipelineRequest('FPT', '2023-01-01', '2023-12-31', capital)).toThrow();
  });
  it('accepts 1e12 VND_FULL; rejects symbols, duplicate universe, invalid dates and future cutoffs', () => {
    expect(pipelineRequest('fpt, hpg', '2023-01-01', '2023-12-31', '1e12').initial_capital).toBe(1e12);
    for (const universe of ['', 'FPT;--', 'FPT,FPT', Array(101).fill('FPT').join(',')]) expect(() => pipelineRequest(universe, '2023-01-01', '2023-12-31', '1')).toThrow();
    for (const date of ['', '2023-02-30', '2099-01-01']) expect(() => pipelineRequest('FPT', '2023-01-01', date, '1')).toThrow();
  });
  it.each(['2026-02-30T08:30:00Z', '2026-10-11T24:00:00Z', '2026-10-11T08:30:00', '', null])('rejects invalid event time %s', (timestamp) => {
    expect(() => validatePipelineTelemetry({ ...pipelineFrame(), timestamp }, PIPE_JOB)).toThrow();
  });
  it('accepts inclusive ICT session-close boundary; rejects the following cutoff', () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2023-12-31T15:30:00+07:00'));
    try {
      expect(pipelineRequest('FPT', '2023-01-01', '2023-12-31', '1').end_date).toBe('2023-12-31');
      expect(() => pipelineRequest('FPT', '2023-01-01', '2024-01-01', '1')).toThrow();
    } finally { vi.restoreAllMocks(); }
  });
  it('accepts server snapshot without optional message; preserves terminal PING', () => {
    const data = pipelineFrame(2, 'COMPLETED', 'RESEARCH_EXECUTION'); data.payload.receipt = pipelineReceipt(); data.event_type = 'PING';
    delete (data as any).message;
    expect(validatePipelineTelemetry(data, PIPE_JOB).status).toBe('COMPLETED');
  });
  it.each(['task_id', 'operation', 'status', 'schema_version', 'request_fingerprint', 'output_sha256', 'receipt_hmac', 'published_at', 'artifact_id'])('rejects receipt field %s', (field) => {
    const data = pipelineFrame(1, 'COMPLETED', 'RESEARCH_EXECUTION'); const receipt = pipelineReceipt(); delete (receipt as any)[field]; data.payload.receipt = receipt;
    expect(() => validatePipelineTelemetry(data, PIPE_JOB)).toThrow();
  });
});
