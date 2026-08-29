import React, { useEffect, useState, useRef } from 'react';
import { RefreshCw, AlertTriangle, Cpu } from 'lucide-react';
import { advancedQuantApi, FracDiffResponse } from '../../api/advancedQuant';

interface FracDiffMemoryIndicatorProps {
  symbol: string;
}

export const FracDiffMemoryIndicator: React.FC<FracDiffMemoryIndicatorProps> = ({ symbol }) => {
  const [data, setData] = useState<FracDiffResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [d, setD] = useState(0.4);
  const [windowSize, setWindowSize] = useState(32);

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
            const res = await advancedQuantApi.calculateFracDiff({
              symbol,
              d,
              window: windowSize,
              limit: 150,
            }, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to compute fractional differentiation');
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
  }, [symbol, d, windowSize]);

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.calculateFracDiff({
        symbol,
        d,
        window: windowSize,
        limit: 150,
      }, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to compute fractional differentiation');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            FracDiff Memory Retention (d={d.toFixed(2)})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={windowSize}
            onChange={(e) => setWindowSize(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-300 text-[11px]"
          >
            <option value={16}>Window: 16</option>
            <option value={32}>Window: 32</option>
            <option value={64}>Window: 64</option>
          </select>
          <button
            onClick={handleManualRefresh}
            disabled={isLoading}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
            title="Refresh FracDiff"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Interactive d slider */}
      <div className="flex items-center gap-3 p-2 rounded bg-zinc-900/40 border border-white/5 text-[11px]">
        <span className="text-zinc-400 whitespace-nowrap">Fractional Order (d):</span>
        <input
          type="range"
          min="0.0"
          max="1.0"
          step="0.05"
          value={d}
          onChange={(e) => setD(Number(e.target.value))}
          className="flex-1 accent-cyan-400"
        />
        <span className="font-bold text-cyan-300 w-10 text-right">{d.toFixed(2)}</span>
      </div>

      {isLoading ? (
        <div className="py-8 flex flex-col items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
          <span>Computing Long-Memory Binomial Kernel Expansion...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Memory Preservation</span>
              <span className="font-bold text-emerald-400 text-sm">
                {(data.memory_retention_score * 100).toFixed(1)}%
              </span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Raw Price Correlation</span>
              <span className="font-bold text-cyan-300 text-sm">
                {data.correlation_with_raw.toFixed(3)}
              </span>
            </div>
            <div className="p-2 rounded bg-zinc-900/60 border border-white/5">
              <span className="text-zinc-500 block">Stationarity / Memory Balance</span>
              <span className="font-bold text-purple-300 text-sm">
                {d < 0.3 ? 'High Memory' : d > 0.7 ? 'High Stationarity' : 'Optimal Balance'}
              </span>
            </div>
          </div>

          {/* Kernel Weights Decay Curve */}
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[10px] text-zinc-500 uppercase font-semibold">Binomial Kernel Lag Weights (k=1..{windowSize})</span>
            <div className="flex items-end gap-1 h-14 w-full pt-1">
              {data.weights.map((w, idx) => {
                const absW = Math.abs(w);
                const heightPct = Math.min(100, Math.max(4, absW * 120));
                return (
                  <div
                    key={idx}
                    title={`Lag -${idx}: Weight ${w.toFixed(4)}`}
                    className="flex-1 bg-zinc-900 hover:bg-zinc-800 rounded-t flex flex-col justify-end"
                  >
                    <div
                      className={`w-full rounded-t ${w >= 0 ? 'bg-cyan-400' : 'bg-rose-400'}`}
                      style={{ height: `${heightPct}%` }}
                    />
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
export default FracDiffMemoryIndicator;

