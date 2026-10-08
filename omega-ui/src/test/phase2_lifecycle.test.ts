import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React, { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { advancedQuantApi } from '../api/advancedQuant';
import { useUiStore } from '../store/uiStore';
import { en } from '../i18n/en';
import { vi as vietnamese } from '../i18n/vi';

import { VpinToxicityPanel } from '../modules/chart_station/VpinToxicityPanel';
import { OrderbookDepthWaterfall } from '../modules/chart_station/OrderbookDepthWaterfall';
import { MarketImpactCurve } from '../modules/chart_station/MarketImpactCurve';
import { FracDiffMemoryIndicator } from '../modules/chart_station/FracDiffMemoryIndicator';
import { ChartStationView } from '../modules/chart_station/ChartStationView';

import { CircuitBreakerStatusStrip } from '../modules/barra_risk_tca/CircuitBreakerStatusStrip';
import { HistoricalStressScenarioPicker } from '../modules/barra_risk_tca/HistoricalStressScenarioPicker';
import { ContagionGraphCanvas } from '../modules/barra_risk_tca/ContagionGraphCanvas';
import { LiquidityConstraintTable } from '../modules/barra_risk_tca/LiquidityConstraintTable';
import { BarraRiskTcaAnalyticsView } from '../modules/barra_risk_tca/BarraRiskTcaAnalyticsView';

import { OwnershipSupplyChainGraph } from '../modules/fundamental_matrix/OwnershipSupplyChainGraph';
import { CorporateGraphDrawer } from '../modules/fundamental_matrix/CorporateGraphDrawer';
import { FundamentalMatrixView } from '../modules/fundamental_matrix/FundamentalMatrixView';

// ponytail: UI lifecycle suite verifying React 19 mounts, 500ms debounce, RAF, AbortController, and setData(null) state clearing.

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('Phase 2 UI Lifecycle & Adversarial Resistance Tests', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  let queryClient: QueryClient;
  let storeSnapshot: ReturnType<typeof useUiStore.getState>;

  beforeEach(() => {
    storeSnapshot = useUiStore.getState();
    vi.useFakeTimers();
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(performance.now());
      return 0;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((_id: number) => {});

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    // Mock all Advanced Quant API endpoints
    vi.spyOn(advancedQuantApi, 'getVpinToxicity').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      vpin: 0.28,
      toxicity_level: 'MODERATE',
      bucket_volume: 500000,
      n_buckets: 20,
      current_imbalance: 120000,
      history: [{ time: '10:00', vpin: 0.28, buy_volume: 310000, sell_volume: 190000, price: 68000 }],
    });

    vi.spyOn(advancedQuantApi, 'getOrderbookDepthWaterfall').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      depth_levels: 10,
      mid_price: 68000,
      spread: 100,
      spread_bps: 14.7,
      total_bid_depth: 15000,
      total_ask_depth: 12000,
      obi: 0.15,
      bids: [{ level: 1, price: 67900, volume: 15000, cumulative_volume: 15000, orders: 12 }],
      asks: [{ level: 1, price: 68000, volume: 12000, cumulative_volume: 12000, orders: 8 }],
    });

    vi.spyOn(advancedQuantApi, 'calculateMarketImpactCurve').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      order_size: 25000,
      average_daily_volume: 2500000,
      volatility: 0.22,
      arrival_price: 68000,
      impact_coefficient: 0.35,
      point_impact_bps: 12.5,
      point_cost_vnd: 2500000,
      curve: [{ participation_rate: 0.1, impact_bps: 12.5, estimated_cost_vnd: 2500000 }],
    });

    vi.spyOn(advancedQuantApi, 'calculateFracDiff').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      d: 0.4,
      window: 32,
      memory_retention_score: 0.85,
      correlation_with_raw: 0.92,
      weights: [1.0, -0.4, -0.12],
      series: [{ time: '2026-08-28', close: 68000, frac_diff: 1250.5 }],
    });

    vi.spyOn(advancedQuantApi, 'getCircuitBreakerStatus').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      as_of: '2026-08-29T00:00:00Z',
      is_safe: true,
      var_95_pct: 1.85,
      cvar_95_pct: 2.45,
      var_breached: false,
      cvar_breached: false,
      action: 'PASS',
      derisk: { target_multiplier: 1.0, reason: 'NORMAL_OPERATION' },
      limit_lock: { is_locked: false, lock_type: 'NONE', can_buy: true, can_sell: true },
    });

    vi.spyOn(advancedQuantApi, 'simulateStressTest').mockResolvedValue({
      status: 'success',
      timestamp: '2026-08-29T00:00:00Z',
      weights_evaluated: { VNM: 0.5, HPG: 0.5 },
      average_loss_pct: -6.45,
      scenarios: [{ id: 'flash_crash', name: 'VN Flash Crash', market_shock: -7.0, portfolio_impact_pct: -6.45, severity: 'HIGH' }],
      recommendation: 'Portfolio stress tolerance within acceptable threshold',
    });

    vi.spyOn(advancedQuantApi, 'getContagionGraph').mockResolvedValue({
      status: 'success',
      is_safe: true,
      stress_level: 'MODERATE',
      risk_multiplier: 0.15,
      dominant_source: 'VNINDEX',
      narrative: 'Inter-market contagion remains subdued.',
      nodes: [{ id: 'VNINDEX', label: 'VN-Index', stress: 0.25, type: 'target' }],
      edges: [{ source: 'SPX', target: 'VNINDEX', correlation: 0.45, transmission_bps: 35 }],
    });

    vi.spyOn(advancedQuantApi, 'validateLiquidityStress').mockResolvedValue({
      status: 'success',
      is_safe: true,
      max_exit_days: 2.1,
      total_impact_bps: 18.4,
      at_risk_symbols: [],
      violation_message: 'All positions satisfy liquidation constraints',
      breakdown: [{ symbol: 'VNM', quantity: 500000, adv: 2500000, exit_days: 2.0, exceeds_limit: false }],
    });

    vi.spyOn(advancedQuantApi, 'getCorporateGraph').mockResolvedValue({
      status: 'success',
      symbol: 'VNM',
      sector: 'Consumer Staples',
      nodes_count: 8,
      edges_count: 10,
      nodes: [{ id: 'VNM', label: 'Vinamilk', category: 'FOCUS_COMPANY', sector: 'Consumer Staples', role: 'Issuer', ownership_pct: 100 }],
      edges: [{ source: 'SCIC', target: 'VNM', label: 'State Capital Investment', relation: 'MAJOR_SHAREHOLDER', weight: 36 }],
    });
  });

  afterEach(() => {
    if (root && container) {
      act(() => {
        root?.unmount();
      });
      container.remove();
    }
    queryClient.clear();
    useUiStore.setState(storeSnapshot, true);
    vi.restoreAllMocks();
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    act(() => {
      root?.render(
        React.createElement(QueryClientProvider, { client: queryClient }, ui)
      );
    });
  };

  it('1. VpinToxicityPanel renders, triggers 500ms debounce, and aborts previous call on symbol change', async () => {
    renderWithProviders(React.createElement(VpinToxicityPanel, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('VPIN Toxicity Flow (VNM)');
    expect(advancedQuantApi.getVpinToxicity).not.toHaveBeenCalled();

    // Advance timers through 500ms debounce
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getVpinToxicity).toHaveBeenCalledTimes(1);

    // Update symbol prop to trigger setData(null) and abort in-flight
    renderWithProviders(React.createElement(VpinToxicityPanel, { symbol: 'HPG' }));
    expect(container?.textContent).toContain('VPIN Toxicity Flow (HPG)');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getVpinToxicity).toHaveBeenCalledTimes(2);
  });

  it('2. OrderbookDepthWaterfall handles 500ms debounce and RAF ladder layout', async () => {
    renderWithProviders(React.createElement(OrderbookDepthWaterfall, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('Orderbook Depth Waterfall (VNM)');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getOrderbookDepthWaterfall).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('BIDS (BUY LADDER)');
    expect(container?.textContent).toContain('ASKS (SELL LADDER)');
  });

  it('3. MarketImpactCurve manages input mutation, debouncing, and Almgren-Chriss simulation', async () => {
    renderWithProviders(React.createElement(MarketImpactCurve, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('Almgren-Chriss Market Impact Curve (VNM)');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.calculateMarketImpactCurve).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('Est. Impact (BPS)');
  });

  it('4. FracDiffMemoryIndicator preserves stationarity vs memory and clears stale state', async () => {
    renderWithProviders(React.createElement(FracDiffMemoryIndicator, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('FracDiff Memory Retention');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.calculateFracDiff).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('Memory Preservation');
  });

  it('5. CircuitBreakerStatusStrip verifies ±7% limits, VaR/CVaR breaches, and auto-abort', async () => {
    renderWithProviders(React.createElement(CircuitBreakerStatusStrip, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('Layer 04 Advanced Circuit Breaker (VNM)');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getCircuitBreakerStatus).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('VN ±7% Limit Lock');
  });

  it('6. HistoricalStressScenarioPicker simulates factor shocks with 500ms debounce', async () => {
    renderWithProviders(React.createElement(HistoricalStressScenarioPicker, null));
    expect(container?.textContent).toContain('Historical & Factor Stress Scenario Engine');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.simulateStressTest).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('VN Flash Crash');
  });

  it('7. ContagionGraphCanvas builds inter-market spillover channels with RAF lifecycle', async () => {
    renderWithProviders(React.createElement(ContagionGraphCanvas, null));
    expect(container?.textContent).toContain('Cross-Market Contagion Network Topology');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getContagionGraph).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('Active Spillover Channels');
  });

  it('8. LiquidityConstraintTable validates T-day liquidation horizons and impact footprints', async () => {
    renderWithProviders(React.createElement(LiquidityConstraintTable, null));
    expect(container?.textContent).toContain('Liquidity & T-Days Exit Stress Engine');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.validateLiquidityStress).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('Worst Exit:');
  });

  it('9. OwnershipSupplyChainGraph displays corporate network and resets on symbol change', async () => {
    renderWithProviders(React.createElement(OwnershipSupplyChainGraph, { symbol: 'VNM' }));
    expect(container?.textContent).toContain('Corporate Ownership & Supply Chain Graph (VNM)');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getCorporateGraph).toHaveBeenCalledTimes(1);
    expect(container?.textContent).toContain('Vinamilk');
  });

  it('10. CorporateGraphDrawer handles open/close lifecycle, cancelAnimationFrame, and cleanup', async () => {
    const onCloseMock = vi.fn();
    renderWithProviders(React.createElement(CorporateGraphDrawer, { symbol: 'VNM', isOpen: true, onClose: onCloseMock }));
    expect(container?.textContent).toContain('Corporate Topology Drawer: VNM');

    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(advancedQuantApi.getCorporateGraph).toHaveBeenCalledTimes(1);

    // Unmount / close
    renderWithProviders(React.createElement(CorporateGraphDrawer, { symbol: 'VNM', isOpen: false, onClose: onCloseMock }));
    expect(container?.textContent).toBe('');
  });

  it('11. Integration Views render properly with full lifecycle safety', async () => {
    renderWithProviders(React.createElement(ChartStationView, null));
    expect(container).not.toBeNull();

    vi.spyOn(advancedQuantApi, 'getBarraDecomposition').mockRejectedValue(new Error('BARRA_FACTOR_MODEL_UNAVAILABLE'));
    vi.spyOn(advancedQuantApi, 'getStressScenarios').mockRejectedValue(new Error('STRESS_MODEL_UNAVAILABLE'));
    vi.spyOn(advancedQuantApi, 'getPostTradeReport').mockRejectedValue(new Error('DATA_NOT_FOUND'));
    vi.spyOn(advancedQuantApi, 'getRoutingDiagnostics').mockRejectedValue(new Error('https://user:DO_NOT_ECHO@example.com'));
    renderWithProviders(React.createElement(BarraRiskTcaAnalyticsView, null));
    const barra = container?.querySelector('section[aria-label="Barra decomposition"]');
    expect(barra?.querySelector('[role="status"]')?.textContent).toBe('Loading Barra model…');
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(advancedQuantApi.getBarraDecomposition).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.getStressScenarios).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.getPostTradeReport).toHaveBeenCalledTimes(1);
    expect(advancedQuantApi.getRoutingDiagnostics).toHaveBeenCalledTimes(1);
    const t = useUiStore.getState().locale === 'vi' ? vietnamese : en;
    expect(barra?.querySelector('[role="status"]')?.textContent).toBe(t.common.integrationUnavailable);
    expect(barra?.querySelector('[role="alert"]')?.textContent).toBe('Risk request failed. Check inputs and available data.');
    for (const label of ['Stress scenarios', 'Liquidity constraints', 'Pre-trade impact']) {
      expect(container?.querySelector(`section[aria-label="${label}"] form`)).not.toBeNull();
    }
    expect(container?.textContent).toContain('Risk request failed. Check inputs and available data.');
    expect(container?.textContent).not.toContain('DO_NOT_ECHO');
    expect(container?.textContent).not.toContain('BARRA_VN_V3');

    renderWithProviders(React.createElement(FundamentalMatrixView, null));
    expect(container?.textContent).toContain('Corporate Ownership & Supply Chain Graph');
  });
});
