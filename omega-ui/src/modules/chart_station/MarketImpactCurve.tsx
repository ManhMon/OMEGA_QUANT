import React, { useEffect, useState, useRef } from 'react';
import { TrendingDown, RefreshCw, Play, AlertTriangle } from 'lucide-react';
import { advancedQuantApi, MarketImpactResponse } from '../../api/advancedQuant';

interface MarketImpactCurveProps {
  symbol: string;
}

export const MarketImpactCurve: React.FC<MarketImpactCurveProps> = ({ symbol }) => {
  const [data, setData] = useState<MarketImpactResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [orderSize, setOrderSize] = useState(25000);
  const [adv, setAdv] = useState(1500000);
  const [volatility, setVolatility] = useState(0.02);
  const [arrivalPrice, setArrivalPrice] = useState(50000);
  const [participationRate, setParticipationRate] = useState(0.10);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Clear stale state on symbol change
    setData(null);
    setError(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let timeoutId: NodeJS.Timeout;
    const startDebounce = () => {
      timeoutId = setTimeout(() => {
        rafRef.current = requestAnimationFrame(async () => {
          setIsLoading(true);
          setError(null);
          try {
            const res = await advancedQuantApi.calculateMarketImpactCurve({
              symbol,
              order_size: orderSize,
              average_daily_volume: adv,
              volatility,
              arrival_price: arrivalPrice,
              participation_rate: participationRate,
              impact_coefficient: 0.25,
            }, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to simulate market impact curve');
            }
          } finally {
            setIsLoading(false);
          }
        });
      }, 500);
    };

    startDebounce();

    return () => {
      clearTimeout(timeoutId);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      controller.abort();
    };
  }, [symbol]);

  const calculateCurve = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.calculateMarketImpactCurve({
        symbol,
        order_size: orderSize,
        average_daily_volume: adv,
        volatility,
        arrival_price: arrivalPrice,
        participation_rate: participationRate,
        impact_coefficient: 0.25,
      }, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to simulate market impact curve');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const maxImpactBps = data?.curve.reduce((max, pt) => Math.max(max, pt.impact_bps), 1) || 50;

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <TrendingDown className="w-4 h-4 text-purple-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Almgren-Chriss Market Impact Curve ({symbol})
          </span>
        </div>
        <button
          onClick={calculateCurve}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-purple-600/80 hover:bg-purple-500 text-white text-[11px] font-bold transition-all disabled:opacity-50"
        >
          <Play className="w-3 h-3" />
          <span>Simulate</span>
        </button>
      </div>

      {/* Input Parameters Form */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px]">
        <div>
          <label className="text-zinc-500 block mb-0.5">Order Size</label>
          <input
            type="number"
            value={orderSize}
            onChange={(e) => setOrderSize(Number(e.target.value))}
            className="w-full px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          />
        </div>
        <div>
          <label className="text-zinc-500 block mb-0.5">ADV (Shares)</label>
          <input
            type="number"
            value={adv}
            onChange={(e) => setAdv(Number(e.target.value))}
            className="w-full px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          />
        </div>
        <div>
          <label className="text-zinc-500 block mb-0.5">Daily Vol (σ)</label>
          <input
            type="number"
            step="0.005"
            value={volatility}
            onChange={(e) => setVolatility(Number(e.target.value))}
            className="w-full px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          />
        </div>
        <div>
          <label className="text-zinc-500 block mb-0.5">Arrival Price</label>
          <input
            type="number"
            value={arrivalPrice}
            onChange={(e) => setArrivalPrice(Number(e.target.value))}
            className="w-full px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          />
        </div>
        <div>
          <label className="text-zinc-500 block mb-0.5">Part. Rate</label>
          <input
            type="number"
            step="0.01"
            value={participationRate}
            onChange={(e) => setParticipationRate(Number(e.target.value))}
            className="w-full px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="py-8 flex flex-col items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-5 h-5 animate-spin text-purple-400" />
          <span>Simulating Almgren-Chriss Slippage Curve...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          {/* Summary Stat Badges */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Est. Impact (BPS)</span>
              <span className="font-bold text-purple-400 text-sm">+{data.point_impact_bps.toFixed(2)} bps</span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Impact Cost (VND)</span>
              <span className="font-bold text-amber-300 text-sm">{data.point_cost_vnd.toLocaleString(undefined, { maximumFractionDigits: 0 })} VND</span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Order Notional</span>
              <span className="font-bold text-zinc-200 text-sm">{((orderSize * arrivalPrice) / 1000000).toFixed(1)}M VND</span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">ADV Participation</span>
              <span className="font-bold text-cyan-300 text-sm">{((orderSize / adv) * 100).toFixed(2)}% of ADV</span>
            </div>
          </div>

          {/* Curve Visualization */}
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[10px] text-zinc-500 uppercase font-semibold">Impact vs Participation Rate Curve</span>
            <div className="flex items-end gap-1.5 h-20 w-full pt-2">
              {data.curve.map((pt, idx) => {
                const heightPct = Math.min(100, Math.max(5, (pt.impact_bps / maxImpactBps) * 100));
                const isSelected = Math.abs(pt.participation_rate - participationRate) < 0.02;
                return (
                  <div
                    key={idx}
                    title={`${(pt.participation_rate * 100).toFixed(0)}% Part. Rate -> ${pt.impact_bps.toFixed(2)} bps (${pt.estimated_cost_vnd.toLocaleString()} VND)`}
                    className="flex-1 bg-zinc-900/80 hover:bg-zinc-800 rounded-t transition-all flex flex-col justify-end items-center gap-1 group"
                  >
                    <div
                      className={`w-full rounded-t transition-all ${
                        isSelected ? 'bg-purple-400 ring-2 ring-purple-300' : 'bg-purple-600/70 group-hover:bg-purple-500'
                      }`}
                      style={{ height: `${heightPct}%` }}
                    />
                    <span className="text-[9px] text-zinc-500 group-hover:text-zinc-300">
                      {(pt.participation_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default MarketImpactCurve;

