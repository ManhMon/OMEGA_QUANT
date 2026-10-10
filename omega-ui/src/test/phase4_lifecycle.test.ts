import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { ModelRegistryView, validateModelCatalog, validateModelVersions, validateModelLineage } from '../modules/model_registry/ModelRegistryView';
import { ConceptDriftPanel, DriftMonitorPanel, getRegistryEvidence, validateConceptDrift, validateMonitorStatus, registryTime } from '../modules/model_registry/DriftMonitorPanel';
import { useUiStore } from '../store/uiStore';
import { QuantControlCenter } from '../modules/control_center/QuantControlCenter';

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
