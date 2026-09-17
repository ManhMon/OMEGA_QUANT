import React, { useState, useEffect, useRef } from 'react';
import {
  TrendingUp,
  ArrowDownRight,
  Calendar,
  BarChart3,
  ShieldCheck,
  Layers,
  Sparkles,
} from 'lucide-react';
import { createChart, IChartApi, LineData, Time } from 'lightweight-charts';
import { apiClient, BacktestResultData } from '../../api/client';
import { advancedQuantApi, OverfittingDiagnosticsResponse, ConformalPredictResponse, WalkForwardCpcvResponse } from '../../api/advancedQuant';
import { VarianceExplorer } from './VarianceExplorer';
import { useTranslation } from '../../i18n';

import { useUiStore } from '../../store/uiStore';

export const StrategyLabView: React.FC = () => {
  const storeSubTab = useUiStore((state) => state.activeSubTabs['strategy_lab']);
  const activeFeatureId = useUiStore((state) => state.activeFeatureId);
  const setActiveSubTabInStore = useUiStore((state) => state.setActiveSubTab);
  const activeSubTab = (storeSubTab as 'cpcv' | 'conformal' | 'overfitting' | 'lab' | 'variance') || 'lab';
  const setActiveSubTab = (tab: 'cpcv' | 'conformal' | 'overfitting' | 'lab' | 'variance') => setActiveSubTabInStore('strategy_lab', tab);

  useEffect(() => {
    if (activeFeatureId) {
      if (activeFeatureId === 'F15') setActiveSubTabInStore('strategy_lab', 'cpcv');
      else if (activeFeatureId === 'F16') setActiveSubTabInStore('strategy_lab', 'conformal');
      else if (activeFeatureId === 'F17') setActiveSubTabInStore('strategy_lab', 'overfitting');
    }
  }, [activeFeatureId, setActiveSubTabInStore]);

  const [data, setData] = useState<BacktestResultData | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState('ALPHA_HRP_V2');
  const [isLoading, setIsLoading] = useState(false);
  const [overfittingData, setOverfittingData] = useState<OverfittingDiagnosticsResponse | null>(null);
  const [conformalData, setConformalData] = useState<ConformalPredictResponse | null>(null);
  const [cpcvData, setCpcvData] = useState<WalkForwardCpcvResponse | null>(null);
  const [isCpcvRunning, setIsCpcvRunning] = useState(false);
  const { t } = useTranslation();

  const equityContainerRef = useRef<HTMLDivElement>(null);
  const underwaterContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const underwaterChartRef = useRef<IChartApi | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const rafIdRef = useRef<number | null>(null);

  useEffect(() => {
    // Abort previous in-flight requests and clear stale data
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setData(null);
    setOverfittingData(null);
    setConformalData(null);

    // 500ms debounce timer
    const debounceTimer = setTimeout(() => {
      setIsLoading(true);

      const fetchAll = async () => {
        try {
          const [reportRes, overfitRes, confRes] = await Promise.all([
            apiClient.getBacktestReport(selectedStrategy),
            advancedQuantApi.getOverfittingDiagnostics(selectedStrategy, 20, controller.signal),
            advancedQuantApi.getMarketConformal('VNM', 5, controller.signal),
          ]);

          if (controller.signal.aborted) return;

          // Use requestAnimationFrame to publish state updates smoothly
          if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = requestAnimationFrame(() => {
            setData(reportRes);
            setOverfittingData(overfitRes);
            setConformalData(confRes);
            setIsLoading(false);
          });
        } catch (err: unknown) {
          if (!controller.signal.aborted) {
            console.error('Failed to load Strategy Lab data:', err);
            setIsLoading(false);
          }
        }
      };

      fetchAll();
    }, 500);

    return () => {
      clearTimeout(debounceTimer);
      controller.abort();
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [selectedStrategy]);

  const loadBacktestReport = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    try {
      const [reportRes, overfitRes] = await Promise.all([
        apiClient.getBacktestReport(selectedStrategy),
        advancedQuantApi.getOverfittingDiagnostics(selectedStrategy, 20, controller.signal),
      ]);
      if (!controller.signal.aborted) {
        if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = requestAnimationFrame(() => {
          setData(reportRes);
          setOverfittingData(overfitRes);
          setIsLoading(false);
        });
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        console.error('Failed to reload backtest report:', err);
        setIsLoading(false);
      }
    }
  };

  const handleRunCpcv = async () => {
    setIsCpcvRunning(true);
    try {
      const res = await advancedQuantApi.runWalkForwardCpcv({
        universe: ['FPT', 'HPG', 'MBB', 'MWG'],
        n_splits: 6,
        n_test_splits: 2,
        embargo_pct: 0.01,
        label_horizon: 5,
      });
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = requestAnimationFrame(() => {
        setCpcvData(res);
        setIsCpcvRunning(false);
      });
    } catch (err) {
      console.error('CPCV run failed:', err);
      setIsCpcvRunning(false);
    }
  };

  // Render Charts with Lightweight Charts
  useEffect(() => {
    if (!data || !equityContainerRef.current || !underwaterContainerRef.current) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }
    if (underwaterChartRef.current) {
      underwaterChartRef.current.remove();
      underwaterChartRef.current = null;
    }

    // 1. Equity Curve vs VNINDEX
    const equityChart = createChart(equityContainerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#a1a1aa',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
    });

    const stratLine = equityChart.addLineSeries({
      color: '#10b981',
      lineWidth: 2,
      title: t.strategyLab.strategyNavLegend,
    });

    const benchLine = equityChart.addLineSeries({
      color: '#a855f7',
      lineWidth: 2,
      lineStyle: 2, // dashed
      title: t.strategyLab.benchmarkLegend,
    });

    const stratData: LineData[] = data.equity_curve.map((d) => ({
      time: d.date as Time,
      value: d.strategy_nav,
    }));

    const benchData: LineData[] = data.equity_curve.map((d) => ({
      time: d.date as Time,
      value: d.vnindex_nav,
    }));

    stratLine.setData(stratData);
    benchLine.setData(benchData);

    equityChart.timeScale().fitContent();
    chartInstanceRef.current = equityChart;

    // 2. Underwater Drawdown Chart
    const underwaterChart = createChart(underwaterContainerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#a1a1aa',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
    });

    const ddLine = underwaterChart.addLineSeries({
      color: '#f43f5e',
      lineWidth: 1,
      title: t.strategyLab.underwaterDdTitle,
    });

    const ddData: LineData[] = data.equity_curve.map((d) => ({
      time: d.date as Time,
      value: d.drawdown_pct,
    }));

    ddLine.setData(ddData);

    underwaterChart.timeScale().fitContent();
    underwaterChartRef.current = underwaterChart;

    const handleResize = () => {
      if (equityContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({
          width: equityContainerRef.current.clientWidth,
          height: equityContainerRef.current.clientHeight,
        });
      }
      if (underwaterContainerRef.current && underwaterChartRef.current) {
        underwaterChartRef.current.applyOptions({
          width: underwaterContainerRef.current.clientWidth,
          height: underwaterContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartInstanceRef.current) chartInstanceRef.current.remove();
      if (underwaterChartRef.current) underwaterChartRef.current.remove();
    };
  }, [data, t]);

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  return (
    <div className="flex flex-col gap-4 h-full font-mono select-none overflow-y-auto pr-1">
      {/* Sub-Tab Navigation Bar */}
      <div className="flex items-center gap-1.5 p-1 rounded-lg bg-zinc-950/80 border border-white/10 text-xs">
        <button
          onClick={() => setActiveSubTab('lab')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'lab'
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Overview & Equity Curve
        </button>
        <button
          onClick={() => setActiveSubTab('cpcv')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'cpcv'
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Walk-Forward CPCV (15 Folds)
        </button>
        <button
          onClick={() => setActiveSubTab('conformal')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'conformal'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Conformal Prediction Bands
        </button>
        <button
          onClick={() => setActiveSubTab('overfitting')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'overfitting'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Overfitting Diagnostics (DSR/PBO)
        </button>
        <button
          onClick={() => setActiveSubTab('variance')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'variance'
              ? 'bg-fuchsia-500/20 text-fuchsia-300 border border-fuchsia-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          Multi-Seed Variance
        </button>
      </div>

      {activeSubTab === 'variance' ? (
        <VarianceExplorer />
      ) : (
        <>
      {/* Control / Toolbar Bar */}
      <div className="p-3 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-bold text-zinc-100">{t.strategyLab.title}</span>
          </div>

          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="bg-zinc-950 border border-white/10 rounded-lg px-3 py-1 text-xs text-zinc-200 focus:outline-none"
          >
            <option value="ALPHA_HRP_V2">Alpha HRP v2 (Ledoit-Wolf & APSE)</option>
            <option value="MOMENTUM_VN30">Momentum Trend Filter VN30</option>
            <option value="QUALITY_BARRA">Quality-Value Barra Neutral</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRunCpcv}
            disabled={isCpcvRunning}
            className="px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-xs font-bold text-zinc-950 transition-colors flex items-center gap-1.5"
          >
            <Layers className="w-3.5 h-3.5" />
            {isCpcvRunning ? 'Running CPCV...' : 'Run CPCV (15 Folds)'}
          </button>

          <span className="text-xs text-zinc-400">{t.strategyLab.benchmarkLabel}</span>
          <span className="text-xs px-2 py-0.5 rounded bg-purple-950 border border-purple-500/30 text-purple-300 font-bold">
            {t.strategyLab.benchmarkVal}
          </span>
          <button
            onClick={loadBacktestReport}
            className="px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-xs font-bold text-zinc-950 transition-colors"
          >
            {isLoading ? t.strategyLab.recalculating : t.strategyLab.rerunLab}
          </button>
        </div>
      </div>

      {/* KPI Headline Cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.cagrReturn}</span>
            <span className="text-base font-bold text-emerald-400">+{data.cagr_pct}%</span>
            <span className="text-[9px] text-zinc-500">{t.strategyLab.annualizedCompound}</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.sharpeRatio}</span>
            <span className="text-base font-bold text-cyan-400">{data.sharpe_ratio}</span>
            <span className="text-[9px] text-zinc-500">{t.strategyLab.rfRate}</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.maxDrawdown}</span>
            <span className="text-base font-bold text-rose-400">{data.max_drawdown_pct}%</span>
            <span className="text-[9px] text-zinc-500">{t.strategyLab.peakToTrough}</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.calmarRatio}</span>
            <span className="text-base font-bold text-amber-400">{data.calmar_ratio}</span>
            <span className="text-[9px] text-zinc-500">{t.strategyLab.calmarDesc}</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.winRate}</span>
            <span className="text-base font-bold text-zinc-100">{data.win_rate_pct}%</span>
            <span className="text-[9px] text-zinc-500">{data.total_trades} {t.strategyLab.executedTrades}</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 flex flex-col gap-1">
            <span className="text-[10px] text-zinc-400">{t.strategyLab.alphaVsVnindex}</span>
            <span className="text-base font-bold text-purple-400">+{data.alpha_vs_vnindex_pct}%</span>
            <span className="text-[9px] text-zinc-500">{t.strategyLab.excessReturn}</span>
          </div>
        </div>
      )}

      {/* Phase 3 Institutional Overfitting Diagnostics & Conformal Bands */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 1. Overfitting Diagnostics (PBO, DSR, FDR) */}
        <div className="p-4 rounded-xl bg-zinc-900/70 border border-white/10 flex flex-col gap-2">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-bold text-zinc-200">Institutional Overfitting Diagnostics</h3>
            </div>
            {overfittingData && (
              <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                overfittingData.is_overfitted
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}>
                {overfittingData.verdict}
              </span>
            )}
          </div>

          {overfittingData ? (
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                <span className="text-[10px] text-zinc-400">PBO (Overfit Prob)</span>
                <span className={`text-base font-bold mt-0.5 ${overfittingData.pbo > 0.5 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {(overfittingData.pbo * 100).toFixed(1)}%
                </span>
                <span className="text-[9px] text-zinc-500">&lt; 50% Threshold</span>
              </div>

              <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                <span className="text-[10px] text-zinc-400">DSR Confidence</span>
                <span className={`text-base font-bold mt-0.5 ${overfittingData.deflated_sharpe_ratio >= 0.95 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {(overfittingData.deflated_sharpe_ratio * 100).toFixed(1)}%
                </span>
                <span className="text-[9px] text-zinc-500">&gt;= 95% Confidence</span>
              </div>

              <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                <span className="text-[10px] text-zinc-400">Trials Tested</span>
                <span className="text-base font-bold text-cyan-400 mt-0.5">
                  {overfittingData.trials_tested}
                </span>
                <span className="text-[9px] text-zinc-500">Search Intensity</span>
              </div>
            </div>
          ) : (
            <div className="p-4 text-center text-zinc-500 text-xs">Loading Overfitting Diagnostics...</div>
          )}
        </div>

        {/* 2. Conformal Prediction Uncertainty Bounds */}
        <div className="p-4 rounded-xl bg-zinc-900/70 border border-white/10 flex flex-col gap-2">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-zinc-200">Conformal Risk Bands (VNM)</h3>
            </div>
            {conformalData && (
              <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-bold">
                {conformalData.regime}
              </span>
            )}
          </div>

          {conformalData ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between bg-zinc-950 p-2 rounded border border-white/5 text-xs">
                <span className="text-zinc-400">Point Forecast (5D):</span>
                <span className="font-bold text-emerald-400">
                  {conformalData.point_forecast_price.toLocaleString()} VND ({conformalData.point_forecast_return_pct > 0 ? '+' : ''}{conformalData.point_forecast_return_pct.toFixed(2)}%)
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {conformalData.intervals.map((inv) => (
                  <div key={inv.confidence_level} className="bg-zinc-950 p-2 rounded border border-white/5 flex flex-col">
                    <span className="text-[10px] text-zinc-400 font-bold">{(inv.confidence_level * 100).toFixed(0)}% Band</span>
                    <span className="text-[11px] font-mono text-zinc-200 mt-0.5">
                      {inv.lower_price.toFixed(0)} - {inv.upper_price.toFixed(0)}
                    </span>
                    <span className="text-[9px] text-zinc-500">±{(inv.interval_width_pct / 2).toFixed(1)}% width</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-4 text-center text-zinc-500 text-xs">Loading Conformal Prediction...</div>
          )}
        </div>
      </div>

      {/* CPCV Active Fold Results (if executed) */}
      {cpcvData && (
        <div className="p-4 rounded-xl bg-zinc-900/70 border border-cyan-500/30 flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-zinc-200">
                CPCV Combinatorial Purged K-Fold Results ({cpcvData.total_folds} Folds)
              </h3>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">Mean OOS Sharpe:</span>
              <span className="font-bold text-emerald-400">{cpcvData.mean_oos_sharpe.toFixed(2)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 max-h-48 overflow-y-auto">
            {cpcvData.folds.map((f) => (
              <div key={f.fold} className="bg-zinc-950 p-2 rounded border border-white/5 flex flex-col gap-0.5 text-xs font-mono">
                <div className="flex items-center justify-between text-[10px] text-zinc-400">
                  <span>Fold #{f.fold + 1}</span>
                  <span className="text-emerald-400">SR: {f.out_of_sample_sharpe.toFixed(2)}</span>
                </div>
                <div className="text-[10px] text-zinc-300">
                  OOS Ret: {f.out_of_sample_return_pct > 0 ? '+' : ''}{f.out_of_sample_return_pct.toFixed(1)}%
                </div>
                <div className="text-[9px] text-rose-400">
                  MaxDD: {f.max_drawdown_pct.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chart Section: 1. Equity Curve vs VNINDEX, 2. Underwater Drawdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main Equity Comparison Chart */}
        <div className="lg:col-span-2 p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-2 min-h-[320px]">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-bold text-zinc-200">{t.strategyLab.equityCurveTitle}</h3>
            </div>
            <div className="flex items-center gap-3 text-[10px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="w-2.5 h-0.5 bg-emerald-400 inline-block" /> {t.strategyLab.strategyNavLegend}
              </span>
              <span className="flex items-center gap-1 text-purple-400">
                <span className="w-2.5 h-0.5 bg-purple-400 border-b border-dashed inline-block" /> {t.strategyLab.benchmarkLegend}
              </span>
            </div>
          </div>
          <div ref={equityContainerRef} className="flex-1 w-full h-[260px]" />
        </div>

        {/* Underwater Drawdown Chart */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-2 min-h-[320px]">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <ArrowDownRight className="w-4 h-4 text-rose-400" />
              <h3 className="text-xs font-bold text-zinc-200">{t.strategyLab.underwaterDdTitle}</h3>
            </div>
            <span className="text-[10px] text-rose-400 font-bold">{t.strategyLab.maxDdLabel} {data?.max_drawdown_pct}%</span>
          </div>
          <div ref={underwaterContainerRef} className="flex-1 w-full h-[260px]" />
        </div>
      </div>

      {/* Monthly Return Heatmap */}
      {data && (
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
          <div className="flex items-center justify-between pb-2 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-zinc-200 uppercase">{t.strategyLab.monthlyHeatmapTitle}</h3>
            </div>
            <span className="text-[10px] text-zinc-400">{t.strategyLab.pitAccounting}</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-center border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-[10px] text-zinc-400">
                  <th className="py-2 text-left px-2">{t.strategyLab.yearTh}</th>
                  {monthNames.map((m) => (
                    <th key={m} className="py-2 px-1">{m}</th>
                  ))}
                  <th className="py-2 text-right px-2">{t.strategyLab.ytdTh}</th>
                </tr>
              </thead>
              <tbody>
                {data.monthly_returns.map((row) => {
                  const ytd = row.months.reduce((acc, cur) => acc + cur, 0);
                  return (
                    <tr key={row.year} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="py-2 text-left px-2 font-bold text-zinc-200">{row.year}</td>
                      {row.months.map((val, idx) => {
                        const isPositive = val >= 0;
                        const intensity = Math.min(Math.abs(val) * 15, 90);
                        const bgStyle = isPositive
                          ? `rgba(16, 185, 129, ${intensity / 100})`
                          : `rgba(244, 63, 94, ${intensity / 100})`;

                        return (
                          <td
                            key={idx}
                            style={{ backgroundColor: bgStyle }}
                            className={`py-2 px-1 text-[11px] font-mono rounded ${
                              isPositive ? 'text-emerald-100 font-semibold' : 'text-rose-100 font-semibold'
                            }`}
                          >
                            {val > 0 ? `+${val.toFixed(1)}` : val.toFixed(1)}%
                          </td>
                        );
                      })}
                      <td className={`py-2 text-right px-2 font-bold ${ytd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {ytd > 0 ? `+${ytd.toFixed(1)}` : ytd.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
};

