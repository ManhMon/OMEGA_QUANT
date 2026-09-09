import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldCheck,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Layers,
} from 'lucide-react';
import {
  advancedQuantApi,
  ConformalCalibrationResponse,
  ConformalCalibrationStatusResponse,
  MondrianGroupCoverage,
} from '../../api/advancedQuant';

export interface CalibrationPanelProps {
  modelName?: string;
  status?: string;
  onCalibrate?: () => void;
  onRefresh?: () => void;
}

export const CalibrationPanel: React.FC<CalibrationPanelProps> = ({
  modelName = 'CONFORMAL_PREDICTOR',
  status: initialStatus = 'NOT_CALIBRATED',
  onCalibrate,
  onRefresh,
}) => {
  const [targetCoverage, setTargetCoverage] = useState<number>(0.90);
  const [nSplits, setNSplits] = useState<number>(5);
  const [embargoPct, setEmbargoPct] = useState<number>(0.01);
  const [labelHorizon, setLabelHorizon] = useState<number>(1);
  const calibDays = 252;
  const [isCalibrating, setIsCalibrating] = useState<boolean>(false);
  const [calibrationData, setCalibrationData] = useState<ConformalCalibrationResponse | null>(null);
  const [statusData, setStatusData] = useState<ConformalCalibrationStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setError(null);
      const res = await advancedQuantApi.getConformalCalibrationStatus(modelName);
      setStatusData(res);
    } catch {
      // Graceful fallback on initial load
    }
  }, [modelName]);

  useEffect(() => {
    fetchStatus();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchStatus]);

  const handleTriggerCalibration = async () => {
    setIsCalibrating(true);
    setError(null);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await advancedQuantApi.calibrateConformalCpcv(
        {
          model_name: modelName,
          target_coverage: targetCoverage,
          n_splits: nSplits,
          embargo_pct: embargoPct,
          label_horizon: labelHorizon,
          calib_days: calibDays,
          alphas: [0.5, 0.2, 0.1, 0.05],
        },
        controller.signal
      );
      setCalibrationData(res);
      await fetchStatus();
      if (onCalibrate) onCalibrate();
      if (onRefresh) onRefresh();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Calibration failed';
      setError(msg);
    } finally {
      setIsCalibrating(false);
    }
  };

  const currentStatus = isCalibrating
    ? 'CALIBRATING'
    : calibrationData?.status === 'success'
    ? 'CALIBRATED'
    : statusData?.status || initialStatus;

  const empiricalCov = calibrationData?.empirical_coverage ?? statusData?.empirical_coverage;
  const meanWidth = calibrationData?.mean_interval_width ?? statusData?.mean_interval_width;
  const groupCoverages: MondrianGroupCoverage[] =
    calibrationData?.group_coverages ?? statusData?.group_coverages ?? [];

  return (
    <div
      className="calibration-panel rounded-lg border border-zinc-800 bg-zinc-950 p-5 text-zinc-100 shadow-lg"
      data-testid="calibration-panel"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-emerald-950/60 p-2 text-emerald-400 border border-emerald-800/40">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold tracking-wide text-zinc-100">
              Conformal CPCV Calibration
            </h3>
            <p className="text-xs text-zinc-400">
              Model: <span className="font-mono text-zinc-200">{modelName}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span
            data-testid="calibration-status"
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium border ${
              currentStatus === 'CALIBRATED'
                ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/50'
                : currentStatus === 'CALIBRATING'
                ? 'bg-amber-950/60 text-amber-400 border-amber-800/50'
                : 'bg-zinc-900 text-zinc-400 border-zinc-800'
            }`}
          >
            {currentStatus === 'CALIBRATED' ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : currentStatus === 'CALIBRATING' ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <AlertCircle className="h-3.5 w-3.5" />
            )}
            {currentStatus}
          </span>

          <button
            type="button"
            onClick={fetchStatus}
            title="Refresh Status"
            className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Calibration Controls Grid */}
      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">
            Target Coverage ({Math.round(targetCoverage * 100)}%)
          </label>
          <input
            type="range"
            min="0.60"
            max="0.99"
            step="0.01"
            value={targetCoverage}
            onChange={(e) => setTargetCoverage(parseFloat(e.target.value))}
            className="w-full accent-emerald-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">
            CPCV Folds ({nSplits} splits)
          </label>
          <select
            value={nSplits}
            onChange={(e) => setNSplits(parseInt(e.target.value, 10))}
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value={3}>3 Folds (Fast)</option>
            <option value={5}>5 Folds (Balanced)</option>
            <option value={10}>10 Folds (Deep Purged)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">
            Embargo Buffer ({Math.round(embargoPct * 100)}%)
          </label>
          <input
            type="number"
            min="0"
            max="0.05"
            step="0.005"
            value={embargoPct}
            onChange={(e) => setEmbargoPct(parseFloat(e.target.value))}
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">
            Label Horizon
          </label>
          <select
            value={labelHorizon}
            onChange={(e) => setLabelHorizon(parseInt(e.target.value, 10))}
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value={1}>1-Day Ahead (T+1)</option>
            <option value={5}>5-Day Forward (T+5)</option>
            <option value={10}>10-Day Horizon (T+10)</option>
          </select>
        </div>
      </div>

      {/* Action Button */}
      <div className="mt-5 flex items-center justify-between border-t border-zinc-800 pt-4">
        <div className="text-xs text-zinc-500">
          Leakage-free non-parametric uncertainty calibration with Combinatorial Purging.
        </div>
        <button
          type="button"
          data-testid="trigger-calibration-btn"
          onClick={handleTriggerCalibration}
          disabled={isCalibrating}
          className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
        >
          {isCalibrating ? (
            <>
              <RefreshCw className="h-4 w-4 animate-spin" />
              Calibrating CPCV...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Trigger CPCV Calibration
            </>
          )}
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mt-4 rounded-md border border-rose-800/60 bg-rose-950/40 p-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      {/* Results Headline Cards */}
      {(empiricalCov !== undefined || meanWidth !== undefined) && (
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">Empirical Coverage</span>
            <div
              data-testid="empirical-coverage"
              className="mt-1 text-lg font-bold text-emerald-400 font-mono"
            >
              {empiricalCov !== undefined && empiricalCov !== null
                ? `${(empiricalCov * 100).toFixed(1)}%`
                : '--'}
            </div>
            <span className="text-[10px] text-zinc-500">
              Target: {Math.round(targetCoverage * 100)}%
            </span>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">Mean Interval Width</span>
            <div
              data-testid="mean-interval-width"
              className="mt-1 text-lg font-bold text-zinc-200 font-mono"
            >
              {meanWidth !== undefined && meanWidth !== null
                ? `±${(meanWidth * 100).toFixed(2)}%`
                : '--'}
            </div>
            <span className="text-[10px] text-zinc-500">Tightness indicator</span>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <span className="text-[11px] text-zinc-400">CPCV Verification</span>
            <div className="mt-1 text-lg font-bold text-indigo-400 font-mono">
              {calibrationData?.n_folds ?? nSplits} Folds
            </div>
            <span className="text-[10px] text-zinc-500">Purged & Embargoed</span>
          </div>
        </div>
      )}

      {/* Mondrian Conditional Coverage Table */}
      {groupCoverages.length > 0 && (
        <div className="mt-5">
          <h4 className="text-xs font-semibold text-zinc-300 mb-2 flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5 text-zinc-400" />
            Mondrian Conditional Coverage by Regime & Liquidity
          </h4>
          <div className="overflow-x-auto rounded border border-zinc-800">
            <table
              data-testid="mondrian-group-table"
              className="w-full text-left text-xs text-zinc-300"
            >
              <thead className="bg-zinc-900 text-zinc-400 text-[10px] uppercase">
                <tr>
                  <th className="px-3 py-2">Regime</th>
                  <th className="px-3 py-2">Liquidity</th>
                  <th className="px-3 py-2">Samples</th>
                  <th className="px-3 py-2">Coverage</th>
                  <th className="px-3 py-2">Width</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800 bg-zinc-950 font-mono text-[11px]">
                {groupCoverages.map((grp, idx) => (
                  <tr key={`${grp.regime}-${grp.liquidity_bucket}-${idx}`} className="hover:bg-zinc-900/40">
                    <td className="px-3 py-2 text-zinc-200 uppercase">{grp.regime}</td>
                    <td className="px-3 py-2 text-zinc-400 uppercase">{grp.liquidity_bucket}</td>
                    <td className="px-3 py-2">{grp.sample_count}</td>
                    <td className="px-3 py-2 text-emerald-400">
                      {(grp.coverage * 100).toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 text-zinc-300">
                      ±{(grp.mean_interval_width * 100).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default CalibrationPanel;

