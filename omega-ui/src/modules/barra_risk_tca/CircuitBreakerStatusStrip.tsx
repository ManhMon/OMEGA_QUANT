import React, { useEffect, useState, useRef } from 'react';
import { ShieldCheck, ShieldAlert, AlertTriangle, RefreshCw, Lock, Unlock } from 'lucide-react';
import { advancedQuantApi, CircuitBreakerStatusResponse } from '../../api/advancedQuant';

interface CircuitBreakerStatusStripProps {
  symbol?: string;
}

export const CircuitBreakerStatusStrip: React.FC<CircuitBreakerStatusStripProps> = ({ symbol = 'VNM' }) => {
  const [data, setData] = useState<CircuitBreakerStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
            const res = await advancedQuantApi.getCircuitBreakerStatus(symbol, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to fetch circuit breaker status');
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

  const handleManualRefresh = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.getCircuitBreakerStatus(symbol, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to fetch circuit breaker status');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-emerald-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Layer 04 Advanced Circuit Breaker ({symbol})
          </span>
        </div>
        <button
          onClick={handleManualRefresh}
          disabled={isLoading}
          className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-white/5"
          title="Refresh Circuit Breaker"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-emerald-400' : ''}`} />
        </button>
      </div>

      {isLoading ? (
        <div className="py-6 flex items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
          <span>Evaluating real-time VaR/CVaR & Limit-Lock boundaries...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* Status Guard */}
          <div
            className={`p-3 rounded-lg border flex items-center gap-3 ${
              data.is_safe
                ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-950/30 border-rose-500/30 text-rose-300'
            }`}
          >
            {data.is_safe ? <ShieldCheck className="w-6 h-6 text-emerald-400" /> : <ShieldAlert className="w-6 h-6 text-rose-400" />}
            <div className="flex flex-col">
              <span className="text-[10px] text-zinc-400">Risk Barrier</span>
              <span className="font-bold text-sm uppercase">{data.is_safe ? 'PASS (SAFE)' : 'BREACH TRIGGERED'}</span>
            </div>
          </div>

          {/* VaR & CVaR */}
          <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 flex flex-col justify-center">
            <span className="text-[10px] text-zinc-500">VaR (95%) / CVaR (95%)</span>
            <div className="flex items-center gap-2 font-bold text-sm">
              <span className={data.var_breached ? 'text-rose-400' : 'text-zinc-200'}>
                {data.var_95_pct.toFixed(2)}%
              </span>
              <span className="text-zinc-600">/</span>
              <span className={data.cvar_breached ? 'text-rose-400' : 'text-zinc-200'}>
                {data.cvar_95_pct.toFixed(2)}%
              </span>
            </div>
          </div>

          {/* De-risking Action */}
          <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 flex flex-col justify-center">
            <span className="text-[10px] text-zinc-500">Auto De-Risk Multiplier</span>
            <div className="flex items-center gap-2 font-bold text-sm">
              <span className="text-cyan-300">{(data.derisk.target_multiplier * 100).toFixed(0)}% Exposure</span>
              <span className="text-[10px] text-zinc-500">({data.action})</span>
            </div>
          </div>

          {/* Vietnam Limit-Lock State */}
          <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 flex items-center gap-3">
            {data.limit_lock.is_locked ? <Lock className="w-5 h-5 text-rose-400" /> : <Unlock className="w-5 h-5 text-emerald-400" />}
            <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500">VN ±7% Limit Lock</span>
              <span className="font-bold text-xs text-zinc-200">
                {data.limit_lock.is_locked ? `Locked (${data.limit_lock.lock_type})` : 'Normal Trading'}
              </span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default CircuitBreakerStatusStrip;

