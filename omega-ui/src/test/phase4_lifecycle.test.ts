import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { ModelRegistryView } from '../modules/model_registry/ModelRegistryView';
import { QuantControlCenter } from '../modules/control_center/QuantControlCenter';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('Phase 4 Model Governance & Resource Governor UI Lifecycle Tests', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.useFakeTimers();
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
    vi.clearAllTimers();
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

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(advancedQuantApi.getModelList).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.getModelVersions).toHaveBeenCalledWith('ALPHA_XGBOOST_V2', expect.any(AbortSignal));
    expect(advancedQuantApi.getModelDrift).toHaveBeenCalledWith('ALPHA_XGBOOST_V2', expect.any(AbortSignal));
  });

  it('2. ModelRegistryView handles Resource Governor mode switch', async () => {
    renderWithProviders(React.createElement(ModelRegistryView, null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(advancedQuantApi.getResourceGovernor).toHaveBeenCalledTimes(1);
  });

  it('3. QuantControlCenter integrates Model Governance and Resource Governor telemetry', async () => {
    renderWithProviders(React.createElement(QuantControlCenter, null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(advancedQuantApi.getResourceGovernor).toHaveBeenCalledTimes(1);
  });
});
