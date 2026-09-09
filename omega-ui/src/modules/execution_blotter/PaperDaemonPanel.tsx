import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Play, Square, Pause, PlayCircle, RefreshCw, Activity, Cpu, ShieldCheck, AlertCircle } from 'lucide-react';
import { advancedQuantApi, PaperDaemonStatusResponse } from '../../api/advancedQuant';

export interface PaperDaemonPanelProps {
  status?: string;
  onRefresh?: () => void;
  onStateChange?: (newState: string) => void;
  autoPoll?: boolean;
}

export const PaperDaemonPanel: React.FC<PaperDaemonPanelProps> = ({
  status: initialStatus = 'STOPPED',
  onRefresh,
  onStateChange,
  autoPoll = false,
}) => {
  const [daemonStatus, setDaemonStatus] = useState<PaperDaemonStatusResponse | null>(null);
  const [currentStatus, setCurrentStatus] = useState<string>(initialStatus);
  const [isActing, setIsActing] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchStatus = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await advancedQuantApi.getPaperDaemonStatus(controller.signal);
      if (!controller.signal.aborted) {
        setDaemonStatus(res);
        setCurrentStatus(res.state);
        onStateChange?.(res.state);
      }
    } catch {
      // Fallback for mocked or offline environments
    }
  }, [onStateChange]);

  useEffect(() => {
    fetchStatus();
    if (!autoPoll) return;
    const interval = setInterval(fetchStatus, 5000);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [fetchStatus, autoPoll]);

  useEffect(() => {
    if (initialStatus && initialStatus !== currentStatus) {
      setCurrentStatus(initialStatus);
    }
  }, [initialStatus]);

  const handleAction = async (action: 'start' | 'stop' | 'pause' | 'resume') => {
    setIsActing(true);
    setFeedback(null);
    try {
      let res: PaperDaemonStatusResponse;
      if (action === 'start') {
        res = await advancedQuantApi.startPaperDaemon();
      } else if (action === 'stop') {
        res = await advancedQuantApi.stopPaperDaemon();
      } else if (action === 'pause') {
        res = await advancedQuantApi.pausePaperDaemon();
      } else {
        res = await advancedQuantApi.resumePaperDaemon();
      }
      setDaemonStatus(res);
      setCurrentStatus(res.state);
      onStateChange?.(res.state);
      onRefresh?.();
      setFeedback({ type: 'success', message: `Daemon ${action}ed successfully.` });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to ${action} daemon`;
      setFeedback({ type: 'error', message: msg });
      setTimeout(() => setFeedback(null), 5000);
    } finally {
      setIsActing(false);
    }
  };

  const isRunning = currentStatus === 'RUNNING';
  const isPaused = currentStatus === 'PAUSED';
  const isStopped = currentStatus === 'STOPPED';

  const formatUptime = (seconds: number) => {
    const s = Math.floor(seconds);
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="paper-daemon-panel glass-card rounded-xl p-4 border border-white/10 bg-zinc-950/60 font-mono flex flex-col gap-3">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wider">
                Paper Trading Daemon
              </h3>
              <span
                data-testid="daemon-state"
                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                  isRunning
                    ? 'bg-emerald-950/80 text-emerald-400 border-emerald-500/40 animate-pulse'
                    : isPaused
                    ? 'bg-amber-950/80 text-amber-400 border-amber-500/40'
                    : 'bg-zinc-900 text-zinc-400 border-zinc-700'
                }`}
              >
                {currentStatus}
              </span>
            </div>
            <p className="text-[10px] text-zinc-500">Virtual execution simulation, slippage & worker lifecycle</p>
          </div>
        </div>

        {/* Lifecycle Buttons */}
        <div className="flex items-center gap-1.5">
          {isStopped && (
            <button
              disabled={isActing}
              onClick={() => handleAction('start')}
              className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-[11px] font-semibold flex items-center gap-1.5 shadow-sm shadow-emerald-500/20 transition-colors"
            >
              <Play className="w-3 h-3" />
              <span>Start Daemon</span>
            </button>
          )}

          {isRunning && (
            <>
              <button
                disabled={isActing}
                onClick={() => handleAction('pause')}
                className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-[11px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <Pause className="w-3 h-3" />
                <span>Pause</span>
              </button>
              <button
                disabled={isActing}
                onClick={() => handleAction('stop')}
                className="px-2.5 py-1 rounded bg-rose-700 hover:bg-rose-600 disabled:opacity-50 text-white text-[11px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <Square className="w-3 h-3" />
                <span>Stop</span>
              </button>
            </>
          )}

          {isPaused && (
            <>
              <button
                disabled={isActing}
                onClick={() => handleAction('resume')}
                className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-[11px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <PlayCircle className="w-3 h-3" />
                <span>Resume</span>
              </button>
              <button
                disabled={isActing}
                onClick={() => handleAction('stop')}
                className="px-2.5 py-1 rounded bg-rose-700 hover:bg-rose-600 disabled:opacity-50 text-white text-[11px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <Square className="w-3 h-3" />
                <span>Stop</span>
              </button>
            </>
          )}

          <button
            disabled={isActing}
            onClick={() => {
              fetchStatus();
              onRefresh?.();
            }}
            title="Refresh daemon status"
            className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isActing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="bg-zinc-900/60 p-2.5 rounded-lg border border-white/5 flex flex-col gap-0.5">
          <span className="text-[10px] text-zinc-400 flex items-center gap-1">
            <Activity className="w-3 h-3 text-cyan-400" />
            Daemon Uptime
          </span>
          <div className="text-sm font-bold text-zinc-200">
            {daemonStatus ? formatUptime(daemonStatus.uptime_seconds) : '00:00:00'}
          </div>
        </div>

        <div className="bg-zinc-900/60 p-2.5 rounded-lg border border-white/5 flex flex-col gap-0.5">
          <span className="text-[10px] text-zinc-400 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            Daily Simulated PnL
          </span>
          <div className={`text-sm font-bold ${
            (daemonStatus?.daily_pnl_vnd ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            {(daemonStatus?.daily_pnl_vnd ?? 0).toLocaleString()} VND
          </div>
        </div>

        <div className="bg-zinc-900/60 p-2.5 rounded-lg border border-white/5 flex flex-col gap-0.5">
          <span className="text-[10px] text-zinc-400 flex items-center gap-1">
            <Cpu className="w-3 h-3 text-purple-400" />
            Active Workers
          </span>
          <div className="text-sm font-bold text-purple-300">
            {daemonStatus?.active_workers ?? 1} worker(s)
          </div>
        </div>

        <div className="bg-zinc-900/60 p-2.5 rounded-lg border border-white/5 flex flex-col gap-0.5">
          <span className="text-[10px] text-zinc-400">Processed Orders</span>
          <div className="text-sm font-bold text-cyan-300">
            {daemonStatus?.processed_orders_count ?? 0} virtual order(s)
          </div>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div className={`text-[11px] px-3 py-1.5 rounded flex items-center gap-1.5 ${
          feedback.type === 'success'
            ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30'
            : 'bg-rose-950/60 text-rose-300 border border-rose-500/30'
        }`}>
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{feedback.message}</span>
        </div>
      )}
    </div>
  );
};

export default PaperDaemonPanel;
