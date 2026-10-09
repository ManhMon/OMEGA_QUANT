import React, { useState, useEffect } from 'react';
import {
  CandlestickChart,
  Layers,
  Zap,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  Sliders,
  Cpu,
} from 'lucide-react';
import { useUiStore } from '../../store/uiStore';
import { isMarketPrice, useMarketOhlcv, useMarketOrderbook } from '../../hooks/useMarketData';
import { LightweightChartContainer } from './LightweightChartContainer';
import { OrderbookDepth } from './OrderbookDepth';
import { VpinToxicityPanel } from './VpinToxicityPanel';
import { OrderbookDepthWaterfall } from './OrderbookDepthWaterfall';
import { MarketImpactCurve } from './MarketImpactCurve';
import { FracDiffMemoryIndicator } from './FracDiffMemoryIndicator';
import { useTranslation } from '../../i18n';

export const ChartStationView: React.FC = () => {
  const selectedTicker = useUiStore((state) => state.selectedTicker);
  const setSelectedTicker = useUiStore((state) => state.setSelectedTicker);
  const chartInterval = useUiStore((state) => state.chartInterval);
  const setChartInterval = useUiStore((state) => state.setChartInterval);
  const storeSubTab = useUiStore((state) => state.activeSubTabs['chart_station']);
  const activeFeatureId = useUiStore((state) => state.activeFeatureId);
  const setActiveSubTabInStore = useUiStore((state) => state.setActiveSubTab);
  const { t } = useTranslation();

  const [showSMA, setShowSMA] = useState(true);
  const [showEMA, setShowEMA] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const [showAlphas, setShowAlphas] = useState(true);
  const activeSubTab = (storeSubTab as 'waterfall' | 'vpin' | 'impact' | 'fracdiff') || 'waterfall';
  const setActiveSubTab = (tab: 'waterfall' | 'vpin' | 'impact' | 'fracdiff') => setActiveSubTabInStore('chart_station', tab);

  useEffect(() => {
    if (activeFeatureId) {
      if (activeFeatureId === 'F01') setActiveSubTabInStore('chart_station', 'vpin');
      else if (activeFeatureId === 'F02') setActiveSubTabInStore('chart_station', 'waterfall');
      else if (activeFeatureId === 'F03') setActiveSubTabInStore('chart_station', 'impact');
      else if (activeFeatureId === 'F04') setActiveSubTabInStore('chart_station', 'fracdiff');
    }
  }, [activeFeatureId, setActiveSubTabInStore]);

  const {
    data: ohlcvData,
    isLoading: isOhlcvLoading,
    isError: isOhlcvError,
    refetch: refetchOhlcv,
    isFetching: isOhlcvFetching,
  } = useMarketOhlcv(selectedTicker, undefined, undefined, 1000, chartInterval);

  const {
    data: orderbookData,
    isLoading: isOrderbookLoading,
    isError: isOrderbookError,
    refetch: refetchOrderbook,
  } = useMarketOrderbook(selectedTicker, 10);

  const AVAILABLE_TICKERS = ['FPT', 'HPG', 'MBB', 'MWG', 'DGC', 'VNM', 'TCB', 'PNJ', 'VN30F1M'];
  const AVAILABLE_TIMEFRAMES = ['1D', '1W', '1M'];

  const candles = isOhlcvError ? [] : ohlcvData?.bars || [];
  const latestCandle = candles[candles.length - 1];
  const prevCandle = candles[candles.length - 2];
  const rawPriceChange =
    latestCandle && prevCandle && isMarketPrice(latestCandle.close) && isMarketPrice(prevCandle.close)
      ? ((latestCandle.close - prevCandle.close) / prevCandle.close) * 100
      : NaN;
  const priceChange = Number.isFinite(rawPriceChange) ? Number(rawPriceChange.toFixed(2)) : null;

  // ponytail: Slice 8 has no alpha-marker source; never fabricate trading signals.

  return (
    <div className="flex flex-col gap-4 h-full pb-8">
      {/* Chart Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-zinc-950/60 border border-white/10 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-3">
          {/* Ticker Selector */}
          <div className="flex items-center gap-2">
            <span className="text-zinc-500">{t.chartStation.tickerLabel}</span>
            <div className="flex flex-wrap gap-1">
              {AVAILABLE_TICKERS.map((ticker) => (
                <button
                  key={ticker}
                  onClick={() => setSelectedTicker(ticker)}
                aria-pressed={selectedTicker === ticker}
                  className={`px-2 py-1 rounded font-bold transition-all ${
                    selectedTicker === ticker
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-zinc-900 text-zinc-400 border border-white/5 hover:bg-zinc-800'
                  }`}
                >
                  {ticker}
                </button>
              ))}
            </div>
          </div>

          <div className="h-4 w-px bg-white/10 hidden sm:block" />

          {/* Timeframe Intervals */}
          <div className="flex items-center gap-1">
            <span className="text-zinc-500 mr-1">{t.chartStation.tfLabel}</span>
            {AVAILABLE_TIMEFRAMES.map((interval) => (
              <button
                key={interval}
                onClick={() => setChartInterval(interval)}
                aria-pressed={chartInterval === interval}
                className={`px-2.5 py-1 rounded font-semibold text-[11px] transition-all ${
                  chartInterval === interval
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    : 'bg-zinc-900 text-zinc-400 border border-white/5 hover:text-zinc-200'
                }`}
              >
                {interval}
              </button>
            ))}
          </div>
        </div>

        {/* Indicators and Overlays Toggles */}
        <div className="flex flex-wrap items-center gap-2">
          {isOhlcvFetching && <RefreshCw className="w-3.5 h-3.5 text-cyan-400 animate-spin" />}

          <button
            onClick={() => setShowSMA(!showSMA)}
            aria-pressed={showSMA}
            className={`px-2 py-1 rounded border flex items-center gap-1.5 transition-all ${
              showSMA
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                : 'bg-zinc-900 text-zinc-500 border-white/5 opacity-60'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>{t.chartStation.smaToggle}</span>
          </button>

          <button
            onClick={() => setShowEMA(!showEMA)}
            aria-pressed={showEMA}
            className={`px-2 py-1 rounded border flex items-center gap-1.5 transition-all ${
              showEMA
                ? 'bg-purple-500/15 text-purple-300 border-purple-500/30'
                : 'bg-zinc-900 text-zinc-500 border-white/5 opacity-60'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>{t.chartStation.emaToggle}</span>
          </button>

          <button
            onClick={() => setShowVolume(!showVolume)}
            aria-pressed={showVolume}
            className={`px-2 py-1 rounded border flex items-center gap-1.5 transition-all ${
              showVolume
                ? 'bg-sky-500/15 text-sky-300 border-sky-500/30'
                : 'bg-zinc-900 text-zinc-500 border-white/5 opacity-60'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>{t.chartStation.volToggle}</span>
          </button>

          <button
            onClick={() => setShowAlphas(!showAlphas)}
            aria-pressed={showAlphas}
            className={`px-2 py-1 rounded border flex items-center gap-1.5 transition-all ${
              showAlphas
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                : 'bg-zinc-900 text-zinc-500 border-white/5 opacity-60'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>{t.chartStation.alphaToggle}</span>
          </button>
        </div>
      </div>

      <p role="status" className="text-xs text-zinc-300">
        Daily OHLCV refreshed every 15 seconds while healthy; failures pause refresh until explicit retry succeeds. Weekly/monthly bars aggregate available daily history, including incomplete periods.
        {showAlphas && ' Alpha markers unavailable: no backend signal source.'}
      </p>
      {/* Main Grid: TradingView Lightweight Chart (70%) + Orderbook Depth Ladder (30%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[480px]">
        {/* Chart Column (8 Cols) */}
        <div className="lg:col-span-8 flex flex-col rounded-xl border border-white/10 bg-zinc-950/60 p-4">
          {/* Header Info */}
          {latestCandle ? (
            <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
              <div className="flex flex-wrap items-center gap-3 font-mono">
                <span className="text-xl font-bold text-zinc-100">{selectedTicker}</span>
                <span
                  className={`font-bold text-sm ${
                    priceChange === null ? 'text-zinc-400' : priceChange >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {isMarketPrice(latestCandle.close) ? `${latestCandle.close.toLocaleString()} VND` : 'Price unavailable'} ({priceChange === null ? <span role="status" aria-label="Price return">Return unavailable</span> : priceChange >= 0 ? `+${priceChange}%` : `${priceChange}%`})
                </span>
                <span className="text-xs text-zinc-400 hidden sm:inline">
                  O: {latestCandle.open.toLocaleString()} | H: {latestCandle.high.toLocaleString()} | L: {latestCandle.low.toLocaleString()} | Vol: {(latestCandle.volume / 1000000).toFixed(2)}M
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    refetchOhlcv();
                    refetchOrderbook();
                  }}
                  className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
                  title="Refetch Market Data"
                  aria-label="Refetch Market Data"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isOhlcvFetching ? 'animate-spin text-cyan-400' : ''}`} />
                </button>
              </div>
            </div>
          ) : null}

          {/* Chart Rendering / Loading / Error State */}
          <div className="flex-1 flex flex-col min-h-[380px]">
            {isOhlcvLoading ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-zinc-500 font-mono text-xs">
                <CandlestickChart className="w-8 h-8 text-cyan-400 animate-spin" />
                <span>{t.chartStation.streamingBars} {selectedTicker}...</span>
              </div>
            ) : isOhlcvError || candles.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-rose-400 font-mono text-xs">
                <AlertTriangle className="w-8 h-8 text-rose-400" />
                <span>{t.chartStation.failedLoad} {selectedTicker}</span>
                <button
                  onClick={() => refetchOhlcv()}
                  className="px-3 py-1.5 rounded bg-rose-900/60 hover:bg-rose-800 text-white flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>{t.chartStation.retryFeed}</span>
                </button>
              </div>
            ) : (
              <div className="flex-1 w-full relative min-h-[380px]">
                <LightweightChartContainer
                  symbol={selectedTicker}
                  candles={candles}
                  showSMA={showSMA}
                  showEMA={showEMA}
                  showVolume={showVolume}
                  alphaMarkers={[]}
                />
              </div>
            )}
          </div>

          {/* Footer Sub-indicator Ribbon */}
          <div className="border-t border-white/10 pt-3 mt-3 flex flex-wrap items-center justify-between text-[11px] font-mono text-zinc-400">
            <div>
              {t.chartStation.engineLabel} <span className="text-cyan-400 font-semibold">TradingView Lightweight v4</span>
            </div>
            <div>
              {t.chartStation.barsLabel} <span className="text-zinc-200 font-bold">{candles.length}</span>
            </div>
            <div>
              {t.chartStation.datasetLabel} <span className="text-emerald-400 font-semibold">data/market_2015_now.parquet</span>
            </div>
          </div>
        </div>

        {/* Orderbook Depth Column (4 Cols) */}
        <div className="lg:col-span-4 flex flex-col">
          <OrderbookDepth data={orderbookData} isLoading={isOrderbookLoading} isError={isOrderbookError} onRetry={() => { void refetchOrderbook(); }} />
        </div>
      </div>

      {/* Phase 2 Sub-Analytics Station (Tabbed Modular Section) */}
      <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-zinc-900/40 p-4">
        {/* Navigation Ribbon for Microstructure & Quant Features */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-mono font-bold text-zinc-200 uppercase tracking-wider">
              Advanced Microstructure & Quant Intelligence
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs">
            <button
              onClick={() => setActiveSubTab('waterfall')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeSubTab === 'waterfall'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Depth Waterfall
            </button>
            <button
              onClick={() => setActiveSubTab('vpin')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeSubTab === 'vpin'
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              VPIN Toxicity
            </button>
            <button
              onClick={() => setActiveSubTab('impact')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeSubTab === 'impact'
                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              Market Impact Curve
            </button>
            <button
              onClick={() => setActiveSubTab('fracdiff')}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                activeSubTab === 'fracdiff'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold'
                  : 'bg-zinc-950 text-zinc-400 border-white/5 hover:text-zinc-200'
              }`}
            >
              FracDiff Memory
            </button>
          </div>
        </div>

        {/* Tab Body */}
        <div>
          {activeSubTab === 'waterfall' && <OrderbookDepthWaterfall symbol={selectedTicker} />}
          {activeSubTab === 'vpin' && <VpinToxicityPanel symbol={selectedTicker} />}
          {activeSubTab === 'impact' && <MarketImpactCurve symbol={selectedTicker} />}
          {activeSubTab === 'fracdiff' && <FracDiffMemoryIndicator symbol={selectedTicker} />}
        </div>
      </div>
    </div>
  );
};
export default ChartStationView;

