import React, { useEffect, useState, useRef } from 'react';
import { Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { advancedQuantApi, VpinToxicityResponse } from '../../api/advancedQuant';

interface VpinToxicityPanelProps {
  symbol: string;
}

export const VpinToxicityPanel: React.FC<VpinToxicityPanelProps> = ({ symbol }) => {
  const [data, setData] = useState<VpinToxicityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [buckets, setBuckets] = useState(20);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Clear stale state on symbol change
    setData(null);
    setError(null);

    // Cancel in-flight requests and RAF debouncing
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
            const res = await advancedQuantApi.getVpinToxicity(symbol, buckets, 150, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to compute VPIN');
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
  }, [symbol, buckets]);

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.getVpinToxicity(symbol, buckets, 150, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to compute VPIN');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const vpinVal = data?.vpin ?? 0.0;
  const level = data?.toxicity_level ?? 'LOW';

  const getToxicityColor = (lvl: string) => {
    switch (lvl) {
      case 'TOXIC':
        return 'text-rose-500 border-rose-500/40 bg-rose-500/10';
      case 'HIGH':
        return 'text-amber-400 border-amber-400/40 bg-amber-400/10';
      case 'MODERATE':
        return 'text-cyan-400 border-cyan-400/40 bg-cyan-400/10';
      default:
        return 'text-emerald-400 border-emerald-400/40 bg-emerald-400/10';
    }
  };

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            VPIN Toxicity Flow ({symbol})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={buckets}
            onChange={(e) => setBuckets(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-300 text-[11px]"
          >
            <option value={10}>10 Buckets</option>
            <option value={20}>20 Buckets</option>
            <option value={50}>50 Buckets</option>
          </select>
          <button
            onClick={handleManualRefresh}
            disabled={isLoading}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
            title="Refresh VPIN"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-8 flex flex-col items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
          <span>Computing Bulk Volume Classification...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className={`p-2.5 rounded-lg border flex flex-col ${getToxicityColor(level)}`}>
              <span className="text-[10px] text-zinc-400">Toxicity Level</span>
              <span className="text-base font-bold">{level}</span>
            </div>
            <div className="p-2.5 rounded-lg border border-white/10 bg-zinc-900/50 flex flex-col">
              <span className="text-[10px] text-zinc-400">VPIN Score</span>
              <span className="text-base font-bold text-zinc-100">{(vpinVal * 100).toFixed(1)}%</span>
            </div>
            <div className="p-2.5 rounded-lg border border-white/10 bg-zinc-900/50 flex flex-col">
              <span className="text-[10px] text-zinc-400">Bucket Volume</span>
              <span className="text-base font-bold text-cyan-300">
                {(data.bucket_volume / 1000).toFixed(0)}k
              </span>
            </div>
            <div className="p-2.5 rounded-lg border border-white/10 bg-zinc-900/50 flex flex-col">
              <span className="text-[10px] text-zinc-400">Imbalance</span>
              <span className={`text-base font-bold ${data.current_imbalance >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {(data.current_imbalance / 1000).toFixed(0)}k
              </span>
            </div>
          </div>

          {/* VPIN History Mini Bar Chart */}
          <div className="flex flex-col gap-1 pt-1">
            <span className="text-[10px] text-zinc-500 uppercase font-semibold">Toxicity Timeline (Last 50 Bars)</span>
            <div className="flex items-end gap-1 h-16 w-full pt-1">
              {data.history.map((pt, i) => {
                const heightPct = Math.min(100, Math.max(5, pt.vpin * 150));
                const barColor =
                  pt.vpin > 0.55 ? 'bg-rose-500' : pt.vpin > 0.4 ? 'bg-amber-400' : pt.vpin > 0.25 ? 'bg-cyan-400' : 'bg-emerald-400';
                return (
                  <div
                    key={i}
                    title={`${pt.time}: VPIN ${(pt.vpin * 100).toFixed(1)}% | Price ${pt.price.toLocaleString()} VND`}
                    className="flex-1 bg-zinc-800 hover:opacity-100 opacity-80 rounded-t transition-all flex flex-col justify-end"
                  >
                    <div className={`w-full rounded-t ${barColor}`} style={{ height: `${heightPct}%` }} />
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
export default VpinToxicityPanel;

