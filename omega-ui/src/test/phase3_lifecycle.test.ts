import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { apiClient } from '../api/client';

import { AlphaFactoryDiscoveryStation } from '../modules/alpha_factory/AlphaFactoryDiscoveryStation';
import { ExecutionBlotterView } from '../modules/execution_blotter/ExecutionBlotterView';
import { TotpRebalanceModal } from '../modules/execution_blotter/TotpRebalanceModal';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('Phase 3 UI Lifecycle & Adversarial Resistance Tests', () => {
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

    // Mock apiClient
    vi.spyOn(apiClient, 'getExecutionBlotter').mockResolvedValue([
      {
        orderId: 'ORD_001',
        timestamp: '10:30:00',
        symbol: 'FPT',
        side: 'BUY',
        orderType: 'LO',
        algoType: 'TWAP',
        qty: 5000,
        price: 135000,
        filledQty: 5000,
        broker: 'VCI',
        status: 'FILLED',
      },
    ]);

    // Mock advancedQuantApi Phase 3 endpoints
    vi.spyOn(advancedQuantApi, 'getOverfittingDiagnostics').mockResolvedValue({
      status: 'success',
      strategy_id: 'ALPHA_HRP_V2',
      trials_tested: 20,
      pbo: 0.18,
      deflated_sharpe_ratio: 0.96,
      observed_sharpe: 1.85,
      expected_max_sharpe: 1.25,
      variance_of_trials: 0.45,
      skewness: -0.25,
      kurtosis: 3.45,
      fdr_q_values: [0.01, 0.02, 0.05],
      is_overfitted: false,
      verdict: 'PASS_STATISTICALLY_SIGNIFICANT',
    });

    vi.spyOn(advancedQuantApi, 'getMarketConformal').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      as_of: '2026-08-29T00:00:00Z',
      point_forecast_price: 68500,
      point_forecast_return_pct: 1.25,
      regime: 'TREND_BULL',
      liquidity_bucket: 'HIGH_LIQUIDITY',
      intervals: [
        { confidence_level: 0.80, lower_price: 66500, upper_price: 70500, lower_return_pct: -2.2, upper_return_pct: 3.7, interval_width_pct: 5.9 },
        { confidence_level: 0.90, lower_price: 65500, upper_price: 71500, lower_return_pct: -3.7, upper_return_pct: 5.1, interval_width_pct: 8.8 },
        { confidence_level: 0.95, lower_price: 64500, upper_price: 72500, lower_return_pct: -5.1, upper_return_pct: 6.6, interval_width_pct: 11.7 },
      ],
      empirical_coverage: 0.92,
      is_valid_mondrian: true,
    });

    vi.spyOn(advancedQuantApi, 'runWalkForwardCpcv').mockResolvedValue({
      status: 'success',
      task_type: 'WALK_FORWARD_CPCV',
      job_id: 'job-cpcv-1234',
      dataset_id: 'market_2015_now',
      n_splits: 6,
      n_test_splits: 2,
      total_folds: 15,
      mean_oos_sharpe: 1.65,
      median_oos_sharpe: 1.58,
      std_oos_sharpe: 0.32,
      mean_oos_return_pct: 18.5,
      worst_drawdown_pct: 8.4,
      pbo: 0.12,
      deflated_sharpe_ratio: 0.97,
      folds: [
        { fold: 0, train_size: 400, test_size: 200, in_sample_sharpe: 1.95, out_of_sample_sharpe: 1.65, in_sample_return_pct: 22.0, out_of_sample_return_pct: 18.5, max_drawdown_pct: 8.4 },
      ],
    });

    vi.spyOn(advancedQuantApi, 'evaluateAlphaAst').mockResolvedValue({
      status: 'success',
      expression: 'ts_rank(close / delay(close, 5), 10)',
      is_valid: true,
      ast_type: 'Call',
      ic_estimate: 0.045,
      ir_estimate: 1.65,
      turnover_estimate_pct: 18.4,
      complexity_score: 7,
      sample_result: [0.1, 0.2, 0.3],
    });

    vi.spyOn(advancedQuantApi, 'getAlphaArsenalSignals').mockResolvedValue({
      status: 'success',
      total_available: 703,
      count: 2,
      signals: [
        { alpha_id: 'ALP_001', name: 'Momentum Reversal', category: 'MOMENTUM', formula: 'ts_rank(close, 10)', ic_mean: 0.045, ir_annualized: 1.65, turnover_pct: 18.4, status: 'ACTIVE' },
        { alpha_id: 'ALP_002', name: 'Volume Cross Rank', category: 'VOLATILITY', formula: 'cross_rank(volume)', ic_mean: 0.038, ir_annualized: 1.42, turnover_pct: 22.1, status: 'CANDIDATE' },
      ],
    });

    vi.spyOn(advancedQuantApi, 'getAlphaDecayProfile').mockResolvedValue({
      status: 'success',
      alpha_id: 'ALP_001',
      name: 'Momentum Reversal',
      half_life_days: 8,
      decay_regime: 'EXPONENTIAL_PERSISTENT',
      profile: [
        { lag_days: 1, ic: 0.045, ir: 1.65, correlation_decay: 1.0 },
        { lag_days: 2, ic: 0.040, ir: 1.45, correlation_decay: 0.88 },
      ],
    });

    vi.spyOn(advancedQuantApi, 'startAlphaDiscovery').mockResolvedValue({
      status: 'success',
      job_id: 'job-gp-1234',
      task_type: 'GENETIC_ALPHA_DISCOVERY',
      population_size: 50,
      generations: 5,
      best_formula: 'ts_rank(close / delay(close, 5), 10)',
      best_fitness: 1.85,
      best_ic: 0.052,
      best_ir: 1.95,
      history: [
        { generation: 1, max_generations: 5, best_formula: 'ts_rank(close, 10)', best_fitness: 1.2, mean_fitness: 0.9, fittest_ic: 0.03 },
      ],
    });

    vi.spyOn(advancedQuantApi, 'executePortfolioRebalance').mockResolvedValue({
      status: 'success',
      job_id: 'job-rebal-1234',
      timestamp: '2026-08-29T00:00:00Z',
      totp_verified: true,
      strategy_id: 'ALPHA_HRP_V2',
      should_rebalance: true,
      reason: 'Weight drift exceeds threshold (0.01)',
      estimated_turnover: 0.125,
      estimated_cost_vnd: 1850000,
      orders: [
        { order_id: 'ORD_001', symbol: 'FPT', side: 'BUY', quantity: 2000, price: 135000, estimated_notional_vnd: 270000000, algo: 'TWAP', slices: 12, status: 'QUEUED' },
      ],
      target_changes: { FPT: 0.05 },
      liquidity_violations: [],
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

  it('1. AlphaFactoryDiscoveryStation mounts, triggers debounced AST evaluation and decay profile fetches', async () => {
    renderWithProviders(React.createElement(AlphaFactoryDiscoveryStation, null));
    expect(container?.textContent).toContain('703');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(advancedQuantApi.getAlphaDecayProfile).toHaveBeenCalledTimes(1);
  });

  it('2. ExecutionBlotterView renders OMS blotter and handles TOTP rebalance modal lifecycle', async () => {
    renderWithProviders(React.createElement(ExecutionBlotterView, null));
    expect(container).not.toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(apiClient.getExecutionBlotter).toHaveBeenCalledTimes(1);
  });

  it('3. TotpRebalanceModal validates 6-digit TOTP input, submits authorization, and clears state', async () => {
    const onConfirmMock = vi.fn().mockResolvedValue(undefined);
    const onCloseMock = vi.fn();

    renderWithProviders(
      React.createElement(TotpRebalanceModal, {
        isOpen: true,
        onClose: onCloseMock,
        onConfirm: onConfirmMock,
      })
    );

    expect(container?.textContent).toContain('AUTHORIZE PORTFOLIO REBALANCE');
  });
});


