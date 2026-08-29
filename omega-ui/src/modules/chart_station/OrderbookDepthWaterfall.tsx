import React, { useEffect, useState, useRef } from 'react';
import { Layers, RefreshCw, AlertTriangle, ArrowDown, ArrowUp } from 'lucide-react';
import { advancedQuantApi, OrderbookDepthWaterfallResponse } from '../../api/advancedQuant';

interface OrderbookDepthWaterfallProps {
  symbol: string;
}

export const OrderbookDepthWaterfall: React.FC<OrderbookDepthWaterfallProps> = ({ symbol }) => {
  const [data, setData] = useState<OrderbookDepthWaterfallResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState(10);
  const [spreadBps] = useState(10.0);

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
            const res = await advancedQuantApi.getOrderbookDepthWaterfall(symbol, depth, spreadBps, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to fetch depth waterfall');
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
  }, [symbol, depth, spreadBps]);

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.getOrderbookDepthWaterfall(symbol, depth, spreadBps, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to fetch depth waterfall');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const maxCumVol = Math.max(data?.total_bid_depth || 1, data?.total_ask_depth || 1);

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-emerald-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Orderbook Depth Waterfall ({symbol})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-300 text-[11px]"
          >
            <option value={5}>5 Levels</option>
            <option value={10}>10 Levels</option>
            <option value={15}>15 Levels</option>
          </select>
          <button
            onClick={handleManualRefresh}
            disabled={isLoading}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
            title="Refresh Depth Waterfall"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-8 flex flex-col items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
          <span>Building Market Microstructure Depth Ladder...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Mid Price</span>
              <span className="font-bold text-zinc-100">{data.mid_price.toLocaleString()} VND</span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Spread (BPS)</span>
              <span className="font-bold text-cyan-400">
                {data.spread.toLocaleString()} VND ({data.spread_bps.toFixed(1)} bps)
              </span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">OBI Imbalance</span>
              <span className={`font-bold ${data.obi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {data.obi >= 0 ? `+${(data.obi * 100).toFixed(1)}%` : `${(data.obi * 100).toFixed(1)}%`}
              </span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Total Liquidity</span>
              <span className="font-bold text-zinc-200">
                {((data.total_bid_depth + data.total_ask_depth) / 1000).toFixed(0)}k shares
              </span>
            </div>
          </div>

          {/* Dual Waterfall Table: Bids on Left, Asks on Right */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            {/* Bids Waterfall (Buy Side) */}
            <div className="flex flex-col gap-1 rounded-lg border border-emerald-500/20 bg-emerald-950/10 p-2.5">
              <div className="flex items-center justify-between text-emerald-400 font-bold text-[11px] pb-1 border-b border-emerald-500/20">
                <span className="flex items-center gap-1">
                  <ArrowUp className="w-3.5 h-3.5" /> BIDS (BUY LADDER)
                </span>
                <span>Total: {(data.total_bid_depth / 1000).toFixed(0)}k</span>
              </div>
              <div className="flex flex-col gap-1 mt-1">
                {data.bids.map((b) => {
                  const barWidth = Math.min(100, Math.max(2, (b.cumulative_volume / maxCumVol) * 100));
                  return (
                    <div key={b.level} className="relative flex items-center justify-between px-2 py-1 rounded text-[11px]">
                      <div
                        className="absolute inset-y-0 right-0 bg-emerald-500/20 rounded pointer-events-none"
                        style={{ width: `${barWidth}%` }}
                      />
                      <span className="z-10 font-bold text-emerald-300">{b.price.toLocaleString()}</span>
                      <span className="z-10 text-zinc-300">
                        {b.volume.toLocaleString()} ({b.orders} ord)
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Asks Waterfall (Sell Side) */}
            <div className="flex flex-col gap-1 rounded-lg border border-rose-500/20 bg-rose-950/10 p-2.5">
              <div className="flex items-center justify-between text-rose-400 font-bold text-[11px] pb-1 border-b border-rose-500/20">
                <span className="flex items-center gap-1">
                  <ArrowDown className="w-3.5 h-3.5" /> ASKS (SELL LADDER)
                </span>
                <span>Total: {(data.total_ask_depth / 1000).toFixed(0)}k</span>
              </div>
              <div className="flex flex-col gap-1 mt-1">
                {data.asks.map((a) => {
                  const barWidth = Math.min(100, Math.max(2, (a.cumulative_volume / maxCumVol) * 100));
                  return (
                    <div key={a.level} className="relative flex items-center justify-between px-2 py-1 rounded text-[11px]">
                      <div
                        className="absolute inset-y-0 left-0 bg-rose-500/20 rounded pointer-events-none"
                        style={{ width: `${barWidth}%` }}
                      />
                      <span className="z-10 font-bold text-rose-300">{a.price.toLocaleString()}</span>
                      <span className="z-10 text-zinc-300">
                        {a.volume.toLocaleString()} ({a.orders} ord)
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default OrderbookDepthWaterfall;

