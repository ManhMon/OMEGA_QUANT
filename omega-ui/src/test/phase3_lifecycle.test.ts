import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { apiClient, normalizeStockScreenerItem, parseNullableNumber } from '../api/client';

import { AlphaFactoryDiscoveryStation } from '../modules/alpha_factory/AlphaFactoryDiscoveryStation';
import { ExecutionBlotterView } from '../modules/execution_blotter/ExecutionBlotterView';
import { TotpRebalanceModal } from '../modules/execution_blotter/TotpRebalanceModal';
import { formatMetricValue, formatMomentumScore, momentumColor } from '../modules/fundamental_matrix/FundamentalMatrixView';
import { QuantControlCenter } from '../modules/control_center/QuantControlCenter';
import { useUiStore } from '../store/uiStore';

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
    vi.spyOn(advancedQuantApi, 'getResourceGovernor').mockResolvedValue({ status: 'success', mode: 'MANUAL', target_concurrency: 8, thread_pool_size: 16, batch_size: 256, version: 1, active_workers: 4, queue_depth: 0, system_load_pct: 20, memory_usage_mb: 512, mode_description: 'manual', updated_at: '2026-09-09T00:00:00Z' });
    vi.spyOn(apiClient, 'getLakehouseStatus').mockResolvedValue({ status: 'success', schema_version: '1', api_contract_version: 1, primary_provider: 'vci', backup_providers: [], timestamp: '2026-09-09T00:00:00Z', datasets: [] });
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockResolvedValue({ status: 'success', schema_version: '1', api_contract_version: 1, universe_preset: 'default', total_selected: 0, top_symbols: [], items: [], model_governance: 'ok', provenance_sha256: 'a'.repeat(64) } as any);
    vi.spyOn(apiClient, 'getStrategyBenchmarks').mockResolvedValue({ status: 'success', schema_version: '1', benchmark_protocol: 'cpcv', data_release_commit: 'a'.repeat(40), artifact_sha256: 'a'.repeat(64), generated_at: '2026-09-09T00:00:00Z', total_strategies: 1, strategies: [{ strategy_id: 'bad', name: 'Malformed', is_optimal: false, sharpe_ratio: Number.NaN, calmar_ratio: 0, win_rate_pct: 0, max_drawdown_pct: 0, annual_return_pct: 0, annual_volatility_pct: 0, cpcv_k_folds: 2, description: '' }] });
    vi.spyOn(apiClient, 'getControlReceipts').mockResolvedValue({ status: 'success', total_receipts: 1, artifact_root: 'artifacts', receipts: [{ schema_version: 1, task_id: 'task_1', operation: 'INGEST', status: 'COMPLETED', request_fingerprint: 'fingerprint', output_sha256: 'a'.repeat(64), published_at: '2026-09-09T00:00:00Z' }] });
  });

  afterEach(() => {
    if (root && container) {
      act(() => {
        root?.unmount();
      });
      container.remove();
    }
    vi.restoreAllMocks();
    useUiStore.setState({ activeSubTabs: { ...useUiStore.getState().activeSubTabs, control_center: 'overview' }, isKillSwitchEngaged: false, tasks: {}, toasts: [] });
    vi.clearAllTimers();
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    act(() => {
      root?.render(
        React.createElement(QueryClientProvider, { client: queryClient }, ui)
      );
    });
  };

  const setInputValue = (input: HTMLInputElement, value: string) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
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

  it('3a. rejected rebalance authorization remains open and never triggers the kill switch', async () => {
    const rebalance = vi.spyOn(apiClient, 'triggerRebalance').mockRejectedValue(new Error('invalid TOTP'));
    const killSwitch = vi.spyOn(apiClient, 'killSwitch');
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Portfolio'))?.click(); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('AUTHORIZE REBALANCE'))?.click(); });
    const input = container?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    await act(async () => { setInputValue(input, '123456'); });
    await act(async () => { (container?.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await Promise.resolve(); });
    expect(rebalance).toHaveBeenCalledWith({ totp_code: '123456' });
    expect(killSwitch).not.toHaveBeenCalled();
    expect(container?.textContent).toContain('invalid TOTP');
  });

  it('3b. emergency halt preserves its separate authorization path', async () => {
    const killSwitch = vi.spyOn(apiClient, 'killSwitch').mockResolvedValue({ status: 'success', timestamp: '2026-09-09T00:00:00Z', is_engaged: true } as any);
    const rebalance = vi.spyOn(apiClient, 'triggerRebalance');
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('EMERGENCY HALT'))?.click(); });
    const input = container?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    await act(async () => { setInputValue(input, '123456'); });
    await act(async () => { (container?.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await Promise.resolve(); });
    expect(killSwitch).toHaveBeenCalledWith({ totp_code: '123456', reason: 'Operator emergency halt', cancel_active_orders: true, freeze_engines: true });
    expect(rebalance).not.toHaveBeenCalled();
  });

  it('4. preserves unavailable screener metrics instead of manufacturing zeroes', () => {
    const item = normalizeStockScreenerItem({ ticker: 'FPT', pe: null, pb: 'NaN', roe: undefined, piotroski_f: null, altman_z: null, momentum_score: 'Infinity' });

    expect(item).toMatchObject({ ticker: 'FPT', pe: null, pb: null, roe: null, piotroskiF: null, altmanZ: null, momentumScore: null });
  });

  it('5. parseNullableNumber strictly rejects malformed types', () => {
    for (const value of [undefined, null, '', ' ', 'NaN', 'Infinity', '-Infinity', '12px', NaN, Infinity, -Infinity, {}, [], true, false]) {
      expect(parseNullableNumber(value)).toBeNull();
    }
    expect(parseNullableNumber('0')).toBe(0);
    expect(parseNullableNumber('12.5')).toBe(12.5);
  });

  it('6. normalizeStockScreenerItem and formatters handle adversarial payloads safely', () => {
    const missing = normalizeStockScreenerItem({ ticker: 'old', pe: null, pb: {}, roe: [], piotroski_f: undefined, altman_z: 'Infinity', momentum_score: false });
    const bounded = normalizeStockScreenerItem({ ticker: 'fpt', pe: 0, pb: '1.2', roe: '15', piotroski_f: 12, altman_z: '-1.5', momentum_score: '-0.25' });

    expect(missing).toMatchObject({ ticker: 'OLD', pe: null, pb: null, roe: null, piotroskiF: null, altmanZ: null, momentumScore: null });
    expect(bounded).toMatchObject({ ticker: 'FPT', pe: 0, pb: 1.2, roe: 15, piotroskiF: 9, altmanZ: -1.5, momentumScore: -0.25 });
    expect(formatMetricValue(null, 1)).toBe('--');
    expect(formatMetricValue(Infinity, 1)).toBe('--');
    expect(formatMetricValue(0, 1)).toBe('0.0');
    expect(formatMomentumScore(null)).toBe('--');
    expect(formatMomentumScore(-0.25)).toBe('-0.25');
  });

  it('7. QuantControlCenter mounts every tab, preserves control parity, and rejects non-finite Sharpe', async () => {
    renderWithProviders(React.createElement(QuantControlCenter, null));
    expect(container?.textContent).toContain('Governor');
    for (const label of ['Overview', 'Ingest', 'Alphas', 'Portfolio', 'Backtest', 'Receipts', 'Copilot', 'LLM Bridge']) {
      await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes(label))?.click(); await Promise.resolve(); });
    }
    expect(container?.textContent).toContain('LLM Bridge manages');
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Backtest'))?.click(); await Promise.resolve(); });
    expect(container?.textContent).toContain('Sharpe --');
  });

  it('7a. shared control state and legacy portfolio/backtest payloads survive tab switches', async () => {
    const optimize = vi.spyOn(apiClient, 'optimizePortfolio').mockResolvedValue({ task_id: 'task-opt', status: 'accepted', message: '', stream_url: '' } as any);
    const backtest = vi.spyOn(apiClient, 'runBacktest').mockResolvedValue({ task_id: 'task-bt', status: 'accepted', message: '', stream_url: '' } as any);
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Portfolio'))?.click(); });
    await act(async () => { setInputValue(container?.querySelector('input[aria-label="Portfolio universe"]') as HTMLInputElement, 'FPT, VNM'); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Backtest'))?.click(); });
    await act(async () => { setInputValue(container?.querySelector('input[aria-label="Backtest start date"]') as HTMLInputElement, '2021-01-01'); setInputValue(container?.querySelector('input[aria-label="Backtest slippage bps"]') as HTMLInputElement, '12'); setInputValue(container?.querySelector('input[aria-label="Backtest commission bps"]') as HTMLInputElement, '8'); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'RUN BACKTEST')?.click(); await Promise.resolve(); });
    expect(backtest).toHaveBeenCalledWith({ strategy_id: 'ALPHA_HRP_V2', start_date: '2021-01-01', slippage_bps: 12, commission_bps: 8 });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Portfolio'))?.click(); });
    expect((container?.querySelector('input[aria-label="Portfolio universe"]') as HTMLInputElement).value).toBe('FPT, VNM');
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'OPTIMIZE PORTFOLIO')?.click(); await Promise.resolve(); });
    expect(optimize).toHaveBeenCalledWith({ objective: 'ALPHA_RANK_RISK_CAPPED', universe: ['FPT', 'VNM'], max_single_weight: 0.15 });
  });

  it('7b. restores portfolio objective, alpha filters, governor switching, source exclusion, and schema-drift safety', async () => {
    const governorUpdate = vi.spyOn(advancedQuantApi, 'updateResourceGovernor');
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'SWITCH TO COPILOT')?.click(); await Promise.resolve(); });
    expect(governorUpdate).toHaveBeenCalledWith({ mode: 'COPILOT' });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Portfolio'))?.click(); });
    expect((container?.querySelector('select[aria-label="Optimization objective"]') as HTMLSelectElement).value).toBe('ALPHA_RANK_RISK_CAPPED');
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Ingest'))?.click(); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'KBS')?.click(); });
    expect(Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'VCI')?.className).toContain('text-zinc-500');
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'VCI')?.click(); });
    expect(Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'KBS')?.className).toContain('text-zinc-500');
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockResolvedValueOnce({ items: [null, { rank: 1, symbol: 'FPT', sector: 'TECH', status_label: 'QUALIFIED' }] } as any);
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Alphas'))?.click(); await Promise.resolve(); });
    expect(container?.textContent).toContain('1. FPT');
    const topN = container?.querySelector('input[aria-label="Top ranked symbols"]') as HTMLInputElement;
    await act(async () => { setInputValue(topN, '7'); await Promise.resolve(); });
    expect(apiClient.getControlDynamicUniverse).toHaveBeenLastCalledWith({ universe_preset: 'default', top_n: 7, sector_filter: undefined }, expect.any(AbortSignal));
  });

  it('7c. governor update serializes duplicate requests and surfaces failures', async () => {
    const governorUpdate = vi.spyOn(advancedQuantApi, 'updateResourceGovernor').mockRejectedValue(new Error('governor offline'));
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { await Promise.resolve(); });
    const button = Array.from(container?.querySelectorAll('button') ?? []).find((item) => item.textContent === 'SWITCH TO COPILOT') as HTMLButtonElement;
    await act(async () => { button.click(); button.click(); await Promise.resolve(); });
    expect(governorUpdate).toHaveBeenCalledTimes(1);
    expect(useUiStore.getState().toasts.some((toast) => toast.title === 'Governor update failed' && toast.message === 'governor offline')).toBe(true);
  });

  it('7d. rejects malformed alpha envelopes and sectors, filters null datasets, and preserves delisted historical members', async () => {
    vi.spyOn(apiClient, 'getLakehouseStatus').mockResolvedValueOnce({ datasets: [null, { id: 'prices', file_name: 'prices.parquet', freshness_status: 'HEALTHY', total_rows: 1 }] } as any);
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockResolvedValueOnce({ items: [{ rank: 1, symbol: 'OLD', sector: 'INDUSTRIALS', status_label: 'DELISTED' }] } as any);
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Ingest'))?.click(); await Promise.resolve(); });
    expect(container?.textContent).toContain('prices.parquet');
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Alphas'))?.click(); await Promise.resolve(); });
    expect(container?.textContent).toContain('1. OLD');
    expect(container?.textContent).toContain('DELISTED');
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockResolvedValueOnce({ items: [{ rank: 1, symbol: 'FPT', sector: '', status_label: 'QUALIFIED' }] } as any);
    const topN = container?.querySelector('input[aria-label="Top ranked symbols"]') as HTMLInputElement;
    await act(async () => { setInputValue(topN, '8'); await Promise.resolve(); await Promise.resolve(); });
    expect(useUiStore.getState().toasts.some((toast) => toast.title === 'Alpha telemetry failed' && toast.message === 'Invalid alpha telemetry response.')).toBe(true);
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockResolvedValueOnce({ top_symbols: ['FPT'] } as any);
    await act(async () => { setInputValue(topN, '9'); await Promise.resolve(); await Promise.resolve(); });
    expect(useUiStore.getState().toasts.filter((toast) => toast.title === 'Alpha telemetry failed' && toast.message === 'Invalid alpha telemetry response.')).toHaveLength(2);
  });

  it('8. operation lock blocks same-tick duplicate dispatches', async () => {
    let resolve!: (value: any) => void;
    const ingest = vi.spyOn(apiClient, 'ingestData').mockImplementation(() => new Promise((done) => { resolve = done; }) as any);
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((item) => item.textContent?.includes('Ingest'))?.click(); await Promise.resolve(); });
    const button = Array.from(container?.querySelectorAll('button') ?? []).find((item) => item.textContent === 'DISPATCH INGEST') as HTMLButtonElement;
    await act(async () => { button.click(); button.click(); await Promise.resolve(); });
    expect(ingest).toHaveBeenCalledTimes(1);
    await act(async () => { resolve({ task_id: 'task_1', status: 'accepted', message: '', stream_url: '' }); });
  });

  it('8a. invalid portfolio weight fails closed before dispatch', async () => {
    const optimize = vi.spyOn(apiClient, 'optimizePortfolio');
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Portfolio'))?.click(); });
    const input = container?.querySelector('input[aria-label="Maximum single weight"]') as HTMLInputElement;
    await act(async () => { setInputValue(input, '1.01'); });
    const optimizeButton = Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent === 'OPTIMIZE PORTFOLIO') as HTMLButtonElement;
    expect(optimizeButton.disabled).toBe(true);
    expect(container?.textContent).toContain('Maximum single weight must be between 0.01 and 1.');
    optimizeButton.click();
    expect(optimize).not.toHaveBeenCalled();
  });

  it('9. tab switch aborts outstanding fetches and failures surface toast errors', async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(apiClient, 'getLakehouseStatus').mockImplementation((nextSignal) => { signal = nextSignal; return new Promise(() => {}) as any; });
    renderWithProviders(React.createElement(QuantControlCenter, null));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Ingest'))?.click(); await Promise.resolve(); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Alphas'))?.click(); await Promise.resolve(); });
    expect(signal?.aborted).toBe(true);
    vi.spyOn(apiClient, 'getControlDynamicUniverse').mockRejectedValueOnce(new Error('offline'));
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Ingest'))?.click(); await Promise.resolve(); });
    await act(async () => { Array.from(container?.querySelectorAll('button') ?? []).find((button) => button.textContent?.includes('Alphas'))?.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    expect(useUiStore.getState().toasts.some((toast) => toast.title === 'Alpha telemetry failed')).toBe(true);
  });

  it('10. missing momentum remains neutral instead of negative', () => {
    expect(formatMomentumScore(null)).toBe('--');
    expect(momentumColor(null)).toBe('text-zinc-500');
    expect(momentumColor(-0.01)).toBe('text-rose-400');
    expect(momentumColor(0)).toBe('text-emerald-400');
  });

});
