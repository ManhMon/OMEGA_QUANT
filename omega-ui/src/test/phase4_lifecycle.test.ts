import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { ModelRegistryView, validateModelCatalog, validateModelVersions, validateModelLineage } from '../modules/model_registry/ModelRegistryView';
import { ConceptDriftPanel, DriftMonitorPanel, getRegistryEvidence, validateConceptDrift, validateMonitorStatus, registryTime } from '../modules/model_registry/DriftMonitorPanel';
import { useUiStore } from '../store/uiStore';
import { QuantControlCenter } from '../modules/control_center/QuantControlCenter';
import { PipelineOrchestrationConsole, PIPELINE_STAGES, pipelineRequest, validatePipelineTelemetry } from '../modules/pipeline_console/PipelineOrchestrationConsole';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

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
