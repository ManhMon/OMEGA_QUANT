import { useEffect, useMemo, useRef, useState } from 'react';
import { ColorType, CrosshairMode, LineStyle, createChart } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import type { CandleData } from '../../api/client';
import { isMarketPrice, validateCandles } from '../../hooks/useMarketData';

export interface AlphaMarker {
  time: string;
  side: 'BUY' | 'SELL';
  price: number;
  label: string;
}

interface LightweightChartContainerProps {
  symbol: string;
  candles: CandleData[];
  showSMA: boolean;
  showEMA: boolean;
  showVolume: boolean;
  alphaMarkers: AlphaMarker[];
}

export function movingAverages(candles: CandleData[], period = 20) {
  if (!Number.isInteger(period) || period < 1 || period > 5000) throw new Error('Invalid period');
  const sma: { time: Time; value: number }[] = [];
  const ema: { time: Time; value: number }[] = [];
  let sum = 0;
  let previous = 0;
  candles.forEach((bar, index) => {
    sum += bar.close;
    if (index >= period) sum -= candles[index - period].close;
    if (index < period - 1) return;
    previous = index === period - 1 ? sum / period : previous + 2 / (period + 1) * (bar.close - previous);
    sma.push({ time: bar.time, value: sum / period });
    ema.push({ time: bar.time, value: previous });
  });
  return { sma, ema };
}

export function LightweightChartContainer({ symbol, candles, showSMA, showEMA, showVolume, alphaMarkers }: LightweightChartContainerProps) {
  const safeCandles = useMemo(() => { try { return validateCandles(candles); } catch { return null; } }, [candles]);
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const series = useRef<{ price: ISeriesApi<'Candlestick'>; sma: ISeriesApi<'Line'>; ema: ISeriesApi<'Line'> } | null>(null);
  const fitted = useRef(false);
  const volumeContainer = useRef<HTMLDivElement>(null);
  const volumeChartRef = useRef<IChartApi | null>(null);
  const volumeSeries = useRef<ISeriesApi<'Histogram'> | null>(null);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<CandleData | null>(null);

  useEffect(() => {
    if (!container.current) return;
    let chart: IChartApi | undefined;
    let observer: ResizeObserver | undefined;
    setError(false);
    fitted.current = false;
    try {
      chart = createChart(container.current, {
        width: container.current.clientWidth || 320, height: 380,
        layout: { background: { type: ColorType.Solid, color: '#09090b' }, textColor: '#d4d4d8' },
        grid: { vertLines: { color: '#18181b' }, horzLines: { color: '#18181b' } },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#3f3f46' },
        timeScale: { borderColor: '#3f3f46' },
      });
      const price = chart.addCandlestickSeries({
        upColor: '#09090b', downColor: '#a1a1aa', borderUpColor: '#e4e4e7', borderDownColor: '#a1a1aa',
        wickUpColor: '#e4e4e7', wickDownColor: '#a1a1aa',
        priceFormat: { type: 'price', precision: 0, minMove: 1 },
      });
      const sma = chart.addLineSeries({ color: '#3987e5', lineWidth: 1, title: 'SMA 20', lastValueVisible: true, priceLineVisible: false });
      const ema = chart.addLineSeries({ color: '#d95926', lineWidth: 1, lineStyle: LineStyle.Dashed, title: 'EMA 20', lastValueVisible: true, priceLineVisible: false });
      chartRef.current = chart;
      series.current = { price, sma, ema };
      chart.subscribeCrosshairMove((param) => {
        const item = param.seriesData.get(price);
        setHover(item && 'close' in item ? { ...item, volume: 0 } as CandleData : null);
      });
      observer = new ResizeObserver(([entry]) => {
        if (entry.contentRect.width > 0) {
          chart?.applyOptions({ width: entry.contentRect.width });
          volumeChartRef.current?.applyOptions({ width: entry.contentRect.width });
        }
      });
      observer.observe(container.current);
      if (volumeContainer.current) {
        const volumeChart = createChart(volumeContainer.current, {
          width: container.current.clientWidth || 320, height: 120,
          layout: { background: { type: ColorType.Solid, color: '#09090b' }, textColor: '#d4d4d8' },
          grid: { vertLines: { visible: false }, horzLines: { color: '#18181b' } },
          handleScroll: false, handleScale: false,
        });
        volumeChartRef.current = volumeChart;
        volumeSeries.current = volumeChart.addHistogramSeries({ color: '#a1a1aa', priceFormat: { type: 'volume' } });
        chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
          if (range) volumeChart.timeScale().setVisibleLogicalRange(range);
        });
      }
    } catch {
      observer?.disconnect();
      chart?.remove();
      volumeChartRef.current?.remove();
      volumeChartRef.current = null;
      volumeSeries.current = null;
      chart = undefined;
      series.current = null;
      chartRef.current = null;
      setError(true);
    }
    return () => {
      observer?.disconnect();
      series.current = null;
      chartRef.current = null;
      chart?.remove();
      volumeChartRef.current?.remove();
      volumeChartRef.current = null;
      volumeSeries.current = null;
    };
  }, [symbol]);

  useEffect(() => {
    if (!series.current || !chartRef.current) return;
    try {
      const bars = validateCandles(candles);
      const times = new Set(bars.map((bar) => bar.time));
      if (alphaMarkers.length > 5000 || alphaMarkers.some((marker) =>
        !times.has(marker.time) || !['BUY', 'SELL'].includes(marker.side) ||
        !isMarketPrice(marker.price) ||
        typeof marker.label !== 'string' || marker.label.length > 80)) throw new Error('Invalid markers');
      const averages = movingAverages(bars);
      series.current.price.setData(bars);
      volumeSeries.current?.setData(bars.map((bar) => ({ time: bar.time, value: bar.volume })));
      series.current.sma.setData(averages.sma);
      series.current.ema.setData(averages.ema);
      series.current.sma.applyOptions({ visible: showSMA });
      series.current.ema.applyOptions({ visible: showEMA });
      series.current.price.setMarkers([...alphaMarkers].sort((a, b) => a.time.localeCompare(b.time)).map((marker) => ({
        time: marker.time, position: marker.side === 'BUY' ? 'belowBar' : 'aboveBar',
        shape: marker.side === 'BUY' ? 'arrowUp' : 'arrowDown', color: '#e4e4e7', text: marker.label,
      })));
      if (!fitted.current && bars.length) { chartRef.current.timeScale().fitContent(); fitted.current = true; }
      setHover(null);
      setError(false);
    } catch {
      volumeSeries.current?.setData([]);
      series.current.price.setData([]);
      series.current.price.setMarkers([]);
      series.current.sma.setData([]);
      series.current.ema.setData([]);
      setError(true);
    }
  }, [candles, showSMA, showEMA, alphaMarkers, symbol]);

  const latest = safeCandles ? hover || safeCandles[safeCandles.length - 1] : null;
  return <section aria-label={`${symbol} chart`} className="min-w-0 text-xs text-zinc-300">
    <div className="flex flex-wrap gap-3" aria-label="Chart legend">
      <span>OHLC · hollow up / filled down · VND</span>
      {showSMA && <span><span style={{ color: '#3987e5' }}>━</span> SMA 20</span>}
      {showEMA && <span><span style={{ color: '#d95926' }}>┄</span> EMA 20</span>}
    </div>
    {error && <p role="alert">Chart unavailable. Invalid data or unsupported renderer.</p>}
    <div ref={container} className="w-full" aria-hidden="true" />
    <div hidden={!showVolume}><p>Volume · shares</p><div ref={volumeContainer} aria-hidden="true" /></div>
    {latest && <p>{latest.time} · O {latest.open.toLocaleString()} · H {latest.high.toLocaleString()} · L {latest.low.toLocaleString()} · C {latest.close.toLocaleString()} VND</p>}
    <details>
      <summary className="cursor-pointer py-2 focus-visible:outline">OHLCV data table{showVolume ? ' · volume in shares' : ''}</summary>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-right tabular-nums"><caption>{symbol} · VND full prices</caption>
          <thead><tr>{['Date', 'Open', 'High', 'Low', 'Close', ...(showVolume ? ['Volume'] : [])].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody>{(safeCandles || []).map((bar) => <tr key={bar.time}><th scope="row">{bar.time}</th>{[bar.open, bar.high, bar.low, bar.close, ...(showVolume ? [bar.volume] : [])].map((value, index) => <td key={index}>{value.toLocaleString()}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>
    <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="underline">Charts by TradingView</a>
  </section>;
}
