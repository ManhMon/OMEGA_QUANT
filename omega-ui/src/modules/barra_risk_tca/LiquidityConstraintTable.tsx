import React, { useState, useEffect, useRef } from 'react';
import { Play, AlertTriangle, RefreshCw, Activity, ShieldCheck, ShieldAlert } from 'lucide-react';
import { advancedQuantApi, LiquidityStressValidateResponse } from '../../api/advancedQuant';

export const LiquidityConstraintTable: React.FC = () => {
  const [data, setData] = useState<LiquidityStressValidateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [maxAdvPart, setMaxAdvPart] = useState(0.10);
  const [maxDays, setMaxDays] = useState(3);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const runValidation = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const res = await advancedQuantApi.validateLiquidityStress({
        positions: { VNM: 500000, HPG: 1200000, FPT: 300000, MWG: 450000 },
        max_adv_participation: maxAdvPart,
        max_exit_days: maxDays,
        market_impact_coefficient: 0.25,
      }, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setError(err?.message || 'Failed to validate liquidity stress constraints');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
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
            const res = await advancedQuantApi.validateLiquidityStress({
              positions: { VNM: 500000, HPG: 1200000, FPT: 300000, MWG: 450000 },
              max_adv_participation: maxAdvPart,
              max_exit_days: maxDays,
              market_impact_coefficient: 0.25,
            }, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setError(err?.message || 'Failed to validate liquidity stress constraints');
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
  }, [maxAdvPart, maxDays]);

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-amber-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Liquidity & T-Days Exit Stress Engine
          </span>
        </div>
        <button
          onClick={runValidation}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold transition-all disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          <span>Validate Liquidity</span>
        </button>
      </div>

      {/* Inputs */}
      <div className="flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500">Max ADV Part/Day:</span>
          <select
            value={maxAdvPart}
            onChange={(e) => setMaxAdvPart(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          >
            <option value={0.05}>5% (Conservative)</option>
            <option value={0.10}>10% (Institutional Standard)</option>
            <option value={0.20}>20% (Aggressive)</option>
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500">Max Allowed Exit Horizon:</span>
          <select
            value={maxDays}
            onChange={(e) => setMaxDays(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          >
            <option value={1}>1 Day (T+1 Immediate)</option>
            <option value={3}>3 Days (Standard)</option>
            <option value={5}>5 Days (Illiquid Tolerance)</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="py-6 flex items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-4 h-4 animate-spin text-amber-400" />
          <span>Computing liquidation footprint and Almgren-Chriss market impact...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          {/* Status Badge */}
          <div className="flex items-center justify-between p-2.5 rounded bg-zinc-900/60 border border-white/5 text-[11px]">
            <div className="flex items-center gap-2">
              {data.is_safe ? <ShieldCheck className="w-4 h-4 text-emerald-400" /> : <ShieldAlert className="w-4 h-4 text-rose-400" />}
              <span className="font-bold text-zinc-100">{data.violation_message}</span>
            </div>
            <div className="flex items-center gap-4 text-zinc-400">
              <span>Worst Exit: <strong className="text-cyan-300">{data.max_exit_days.toFixed(1)} Days</strong></span>
              <span>Avg Impact: <strong className="text-amber-400">{data.total_impact_bps.toFixed(1)} bps</strong></span>
            </div>
          </div>

          {/* Table Breakdown */}
          <div className="overflow-x-auto rounded border border-white/5">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-zinc-900 text-zinc-400 uppercase text-[9px] border-b border-white/5">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Position</th>
                  <th className="px-3 py-2">20D ADV</th>
                  <th className="px-3 py-2">Days to Exit</th>
                  <th className="px-3 py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 bg-zinc-950/40">
                {data.breakdown.map((row) => (
                  <tr key={row.symbol} className="hover:bg-white/5">
                    <td className="px-3 py-2 font-bold text-zinc-200">{row.symbol}</td>
                    <td className="px-3 py-2 text-zinc-300">{row.quantity.toLocaleString()}</td>
                    <td className="px-3 py-2 text-zinc-400">{row.adv.toLocaleString()}</td>
                    <td className={`px-3 py-2 font-bold ${row.exceeds_limit ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {row.exit_days.toFixed(1)} days
                    </td>
                    <td className="px-3 py-2 text-right font-bold">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${row.exceeds_limit ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
                        {row.exceeds_limit ? 'EXCEEDED' : 'PASS'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default LiquidityConstraintTable;

