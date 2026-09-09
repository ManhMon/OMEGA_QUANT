import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Sparkles,
  Play,
  RotateCcw,
  AlertTriangle,
  Layers,
} from 'lucide-react';
import {
  advancedQuantApi,
  EvolutionRunRequest,
  EvolutionSummary,
} from '../../api/advancedQuant';

export interface VarianceExplorerProps {
  runId?: string;
  seeds?: number[];
  onRunStarted?: (jobId: string) => void;
}

export const VarianceExplorer: React.FC<VarianceExplorerProps> = ({
  runId: initialRunId,
  seeds: initialSeeds = [42, 1042, 2042, 3042, 4042],
  onRunStarted,
}) => {
  const [currentJobId, setCurrentJobId] = useState<string | null>(initialRunId || null);
  const [strategyId, setStrategyId] = useState<string>('GENETIC_ALPHA_EVOLUTION');
  const [seedsInput, setSeedsInput] = useState<string>(initialSeeds.join(', '));
  const [population, setPopulation] = useState<number>(30);
  const [generations, setGenerations] = useState<number>(5);
  const [txCostBps, setTxCostBps] = useState<number>(25);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [progressPct, setProgressPct] = useState<number>(0);
  const [summary, setSummary] = useState<EvolutionSummary | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pollIntervalRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const pollJobStatus = useCallback((jobId: string) => {
    stopPolling();
    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const statusRes = await advancedQuantApi.getEvolutionRun(jobId);
        setJobStatus(statusRes.status);
        setProgressPct(statusRes.progress_pct || 0);

        if (statusRes.status === 'SUCCEEDED' && statusRes.result) {
          stopPolling();
          setIsLoading(false);
          setSummary(statusRes.result as unknown as EvolutionSummary);
        } else if (statusRes.status === 'FAILED' || statusRes.status === 'CANCELLED') {
          stopPolling();
          setIsLoading(false);
          setErrorMsg(statusRes.error?.message || `Job ${statusRes.status.toLowerCase()}`);
        }
      } catch (err: any) {
        // Poll failed or job completed
        console.warn('Poll status error:', err);
      }
    }, 1500);
  }, [stopPolling]);

  useEffect(() => {
    if (initialRunId) {
      setCurrentJobId(initialRunId);
      pollJobStatus(initialRunId);
    }
    return () => stopPolling();
  }, [initialRunId, pollJobStatus, stopPolling]);

  const handleStartRun = async () => {
    setErrorMsg(null);
    setIsLoading(true);
    setSummary(null);

    const parsedSeeds = seedsInput
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n >= 0);

    const uniqueSeeds = Array.from(new Set(parsedSeeds));
    if (uniqueSeeds.length === 0) {
      setErrorMsg('Please specify at least one valid seed.');
      setIsLoading(false);
      return;
    }

    const nowUtc = new Date().toISOString();
    const req: EvolutionRunRequest = {
      dataset: 'data/market_2015_now.parquet',
      pit_cutoff: nowUtc,
      strategy_id: strategyId,
      seeds: uniqueSeeds,
      population: population,
      generations: generations,
      workers: 1,
      transaction_cost_bps: txCostBps,
    };

    try {
      const accepted = await advancedQuantApi.runEvolution(req);
      setCurrentJobId(accepted.job_id);
      setJobStatus('QUEUED');
      setProgressPct(0);
      if (onRunStarted) {
        onRunStarted(accepted.job_id);
      }
      pollJobStatus(accepted.job_id);
    } catch (err: any) {
      setIsLoading(false);
      setErrorMsg(err?.message || 'Failed to submit evolution run');
    }
  };

  const parsedSeedsCount = seedsInput
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n)).length;

  return (
    <div className="variance-explorer-panel flex flex-col gap-4 font-mono select-none" data-testid="variance-explorer">
      {/* Configuration & Trigger Bar */}
      <div className="p-4 rounded-xl bg-zinc-900/70 border border-white/10 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wide">
              Multi-Seed Genetic Evolution & Variance Explorer
            </h3>
          </div>
          {currentJobId && (
            <div className="flex items-center gap-2 text-[10px] text-zinc-400">
              <span>Run ID:</span>
              <span className="text-cyan-400 font-bold">{currentJobId.slice(0, 8)}...</span>
              <span
                className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                  jobStatus === 'SUCCEEDED'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                    : jobStatus === 'FAILED'
                    ? 'bg-rose-950 text-rose-400 border border-rose-500/30'
                    : 'bg-cyan-950 text-cyan-300 border border-cyan-500/30 animate-pulse'
                }`}
              >
                {jobStatus || 'IDLE'}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 pt-2 border-t border-white/5 text-xs">
          <div>
            <label className="text-[10px] text-zinc-400 block mb-1">Strategy ID</label>
            <input
              type="text"
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
            />
          </div>

          <div className="md:col-span-2">
            <label className="text-[10px] text-zinc-400 block mb-1">
              Random Seeds ({parsedSeedsCount} configured)
            </label>
            <input
              type="text"
              value={seedsInput}
              onChange={(e) => setSeedsInput(e.target.value)}
              placeholder="42, 1042, 2042, 3042, 4042"
              className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] text-zinc-400 block mb-1">Pop / Gen / Bps</label>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min={2}
                max={500}
                value={population}
                onChange={(e) => setPopulation(Number(e.target.value))}
                className="w-1/3 bg-zinc-950 border border-white/10 rounded px-1.5 py-1 text-zinc-200 text-xs"
                title="Population size"
              />
              <span className="text-zinc-500">/</span>
              <input
                type="number"
                min={1}
                max={200}
                value={generations}
                onChange={(e) => setGenerations(Number(e.target.value))}
                className="w-1/3 bg-zinc-950 border border-white/10 rounded px-1.5 py-1 text-zinc-200 text-xs"
                title="Generations"
              />
              <span className="text-zinc-500">/</span>
              <input
                type="number"
                min={0}
                max={500}
                value={txCostBps}
                onChange={(e) => setTxCostBps(Number(e.target.value))}
                className="w-1/3 bg-zinc-950 border border-white/10 rounded px-1.5 py-1 text-zinc-200 text-xs"
                title="Transaction cost (bps)"
              />
            </div>
          </div>

          <div className="flex items-end">
            <button
              onClick={handleStartRun}
              disabled={isLoading}
              className={`w-full py-1.5 px-3 rounded font-bold text-xs flex items-center justify-center gap-1.5 transition-all ${
                isLoading
                  ? 'bg-purple-950/50 text-purple-400 border border-purple-500/20 cursor-not-allowed'
                  : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-950/50'
              }`}
            >
              {isLoading ? (
                <>
                  <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                  <span>Evolving ({progressPct}%)...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Run Multi-Seed</span>
                </>
              )}
            </button>
          </div>
        </div>

        {errorMsg && (
          <div className="p-2 rounded bg-rose-950/40 border border-rose-500/30 text-rose-400 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {/* Dispersion Summary Metric Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">Completed Seeds</span>
            <span className="text-base font-bold text-emerald-400 mt-1">
              {summary.completed_seeds} / {summary.requested_seeds}
            </span>
            <span className="text-[9px] text-zinc-500">
              {summary.failed_seeds > 0 ? `${summary.failed_seeds} failed` : '100% convergence'}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">Median Sharpe</span>
            <span className={`text-base font-bold mt-1 ${summary.median_sharpe && summary.median_sharpe > 1.0 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {summary.median_sharpe !== null ? summary.median_sharpe.toFixed(2) : 'N/A'}
            </span>
            <span className="text-[9px] text-zinc-500">Robust Rank Measure</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">IQR Dispersion</span>
            <span className="text-base font-bold text-cyan-400 mt-1">
              {summary.iqr_sharpe !== null ? summary.iqr_sharpe.toFixed(3) : 'N/A'}
            </span>
            <span className="text-[9px] text-zinc-500">Interquartile Range</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">Sample Std Dev</span>
            <span className="text-base font-bold text-purple-400 mt-1">
              {summary.std_sharpe !== null ? summary.std_sharpe.toFixed(3) : 'N/A (N<2)'}
            </span>
            <span className="text-[9px] text-zinc-500">Seed Sensitivity</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">Worst Drawdown</span>
            <span className="text-base font-bold text-rose-400 mt-1">
              {summary.worst_drawdown !== null ? `${(summary.worst_drawdown * 100).toFixed(1)}%` : 'N/A'}
            </span>
            <span className="text-[9px] text-zinc-500">Tail Risk Bound</span>
          </div>

          <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col">
            <span className="text-[10px] text-zinc-400 uppercase">Median Rank IC</span>
            <span className="text-base font-bold text-zinc-100 mt-1">
              {summary.median_ic !== null ? summary.median_ic.toFixed(4) : 'N/A'}
            </span>
            <span className="text-[9px] text-zinc-500">Cross-Sectional</span>
          </div>
        </div>
      )}

      {/* Seed Results Breakdown Table */}
      <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
        <div className="flex items-center justify-between pb-2 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-zinc-200 uppercase">
              Seed Results & Convergence Accounting
            </h3>
          </div>
          <span className="text-[10px] text-zinc-400">
            {summary?.seed_results.length || 0} Evaluated Shards
          </span>
        </div>

        {summary && summary.seed_results.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-[10px] text-zinc-400">
                  <th className="py-2 px-2">Seed</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 px-2 text-right">Sharpe</th>
                  <th className="py-2 px-2 text-right">Rank IC</th>
                  <th className="py-2 px-2 text-right">Max DD</th>
                  <th className="py-2 px-2 text-right">Turnover</th>
                  <th className="py-2 px-2 text-right">Trades</th>
                  <th className="py-2 px-2">Artifact</th>
                </tr>
              </thead>
              <tbody>
                {summary.seed_results.map((sr) => {
                  const isCompleted = sr.status === 'COMPLETED';
                  return (
                    <tr
                      key={sr.seed}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors font-mono"
                    >
                      <td className="py-2 px-2 font-bold text-zinc-200">#{sr.seed}</td>
                      <td className="py-2 px-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            isCompleted
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-950 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {sr.status}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right font-bold text-emerald-400">
                        {sr.sharpe !== null ? sr.sharpe.toFixed(2) : '-'}
                      </td>
                      <td className="py-2 px-2 text-right text-zinc-300">
                        {sr.ic !== null ? sr.ic.toFixed(4) : '-'}
                      </td>
                      <td className="py-2 px-2 text-right text-rose-400">
                        {sr.max_drawdown !== null ? `${(sr.max_drawdown * 100).toFixed(1)}%` : '-'}
                      </td>
                      <td className="py-2 px-2 text-right text-zinc-400">
                        {sr.turnover !== null ? sr.turnover.toFixed(2) : '-'}
                      </td>
                      <td className="py-2 px-2 text-right text-zinc-400">{sr.trade_count}</td>
                      <td className="py-2 px-2 text-[10px] text-zinc-500 truncate max-w-[140px]">
                        {sr.artifact_reference || sr.failure_code || 'None'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-zinc-500 text-xs border border-dashed border-white/5 rounded-lg">
            No multi-seed run executed yet. Configure seeds above and click &quot;Run Multi-Seed&quot; to explore strategy variance.
          </div>
        )}
      </div>
    </div>
  );
};

export default VarianceExplorer;
