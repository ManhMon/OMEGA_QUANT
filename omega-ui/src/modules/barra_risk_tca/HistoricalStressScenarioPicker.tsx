import React, { useState, useEffect, useRef } from 'react';
import { Play, AlertTriangle, RefreshCw, Layers } from 'lucide-react';
import { advancedQuantApi, StressTestSimulateResponse } from '../../api/advancedQuant';

export const HistoricalStressScenarioPicker: React.FC = () => {
  const [data, setData] = useState<StressTestSimulateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [shockPct, setShockPct] = useState(-7.0);
  const [volMultiplier, setVolMultiplier] = useState(1.5);
  const [includeContagion, setIncludeContagion] = useState(true);

  const rafRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const runSimulation = async () => {
    setData(null);
    setError(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    try {
      const res = await advancedQuantApi.simulateStressTest({
        portfolio_weights: { VNM: 0.35, HPG: 0.35, FPT: 0.30 },
        market_shock_pct: shockPct,
        volatility_shock_multiplier: volMultiplier,
        include_contagion: includeContagion,
      }, controller.signal);
      setData(res);
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        setData(null);
        setError(err?.message || 'Failed to execute stress scenario simulation');
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
            const res = await advancedQuantApi.simulateStressTest({
              portfolio_weights: { VNM: 0.35, HPG: 0.35, FPT: 0.30 },
              market_shock_pct: shockPct,
              volatility_shock_multiplier: volMultiplier,
              include_contagion: includeContagion,
            }, controller.signal);
            setData(res);
          } catch (err: any) {
            if (err?.name !== 'AbortError') {
              setData(null);
              setError(err?.message || 'Failed to execute stress scenario simulation');
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
  }, [shockPct, volMultiplier, includeContagion]);

  return (
    <div className="flex flex-col gap-3 p-3.5 rounded-xl border border-white/10 bg-zinc-950/70 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-purple-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider">
            Historical & Factor Stress Scenario Engine
          </span>
        </div>
        <button
          onClick={runSimulation}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold transition-all disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          <span>Run Scenarios</span>
        </button>
      </div>

      {/* Shock Presets */}
      <div className="flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500">Market Floor Shock:</span>
          <select
            value={shockPct}
            onChange={(e) => setShockPct(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          >
            <option value={-3.0}>-3% Moderate Dip</option>
            <option value={-7.0}>-7% VN Daily Floor</option>
            <option value={-14.0}>-14% 2-Day Cascade</option>
            <option value={-21.0}>-21% Systemic Crash</option>
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500">Vol Multiplier:</span>
          <select
            value={volMultiplier}
            onChange={(e) => setVolMultiplier(Number(e.target.value))}
            className="px-2 py-1 rounded bg-zinc-900 border border-white/10 text-zinc-200"
          >
            <option value={1.0}>1.0x Normal</option>
            <option value={1.5}>1.5x Elevated</option>
            <option value={2.5}>2.5x Crisis Surge</option>
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <input
            type="checkbox"
            id="includeContagionCheck"
            checked={includeContagion}
            onChange={(e) => setIncludeContagion(e.target.checked)}
            className="rounded accent-purple-500 bg-zinc-900 border border-white/10"
          />
          <label htmlFor="includeContagionCheck" className="text-zinc-400 cursor-pointer">
            Include Contagion Multiplier
          </label>
        </div>
      </div>

      {isLoading ? (
        <div className="py-6 flex items-center justify-center gap-2 text-zinc-500">
          <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
          <span>Propagating multi-factor shocks through portfolio covariance matrix...</span>
        </div>
      ) : error ? (
        <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/20 text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-3">
          <div className="p-2.5 rounded bg-zinc-900/60 border border-white/5 flex items-center justify-between text-[11px]">
            <span className="text-zinc-400">Mean Portfolio Simulated Drawdown:</span>
            <span className="font-bold text-rose-400 text-sm">{data.average_loss_pct.toFixed(2)}%</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {data.scenarios.map((sc) => (
              <div
                key={sc.id}
                className="p-3 rounded-lg border border-white/5 bg-zinc-900/40 flex flex-col gap-1.5"
              >
                <div className="flex items-center justify-between font-bold">
                  <span className="text-zinc-200">{sc.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400">
                    {sc.severity}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-1 border-t border-white/5">
                  <span>Market Shock: {sc.market_shock}%</span>
                  <span className="font-bold text-rose-400">
                    Est. Loss: {sc.portfolio_impact_pct.toFixed(2)}%
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="text-[11px] text-cyan-300/90 italic bg-cyan-950/20 border border-cyan-500/20 p-2.5 rounded">
            <strong>Advisory:</strong> {data.recommendation}
          </div>
        </div>
      ) : null}
    </div>
  );
};
export default HistoricalStressScenarioPicker;

