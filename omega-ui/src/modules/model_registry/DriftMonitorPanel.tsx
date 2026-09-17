import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  AlertTriangle,
  RotateCcw,
  Clock,
  ShieldCheck,
  ShieldAlert,
  Save,
  Layers,
} from 'lucide-react';
import {
  advancedQuantApi,
  DriftMonitorStatus,
  DriftScheduleRequest,
} from '../../api/advancedQuant';
import { useUiStore } from '../../store/uiStore';

export interface DriftMonitorPanelProps {
  status?: string;
  onRefresh?: () => void;
}

export const DriftMonitorPanel: React.FC<DriftMonitorPanelProps> = ({ onRefresh }) => {
  const addToast = useUiStore((state) => state.addToast);
  const [monitorStatus, setMonitorStatus] = useState<DriftMonitorStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Form state
  const [enabled, setEnabled] = useState<boolean>(true);
  const [schedule, setSchedule] = useState<string>('0 2 * * *');
  const [timezone, setTimezone] = useState<string>('UTC');
  const [sharpeDrop, setSharpeDrop] = useState<number>(0.30);
  const [icDrop, setIcDrop] = useState<number>(0.015);
  const [turnoverSpike, setTurnoverSpike] = useState<number>(0.10);

  const fetchStatus = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await advancedQuantApi.getDriftMonitorStatus();
      setMonitorStatus(res);
      setEnabled(res.enabled);
      setSchedule(res.schedule);
      setTimezone(res.timezone);
      if (res.thresholds) {
        if (res.thresholds.sharpe_drop !== undefined) setSharpeDrop(res.thresholds.sharpe_drop);
        if (res.thresholds.ic_drop !== undefined) setIcDrop(res.thresholds.ic_drop);
        if (res.thresholds.turnover_spike !== undefined) setTurnoverSpike(res.thresholds.turnover_spike);
      }
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Drift Sentinel Fetch Failed',
        message: err?.message || 'Unable to retrieve drift sentinel status',
      });
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleSaveSchedule = async () => {
    if (!monitorStatus) return;
    setIsSaving(true);
    const req: DriftScheduleRequest = {
      enabled,
      schedule,
      timezone,
      thresholds: {
        sharpe_drop: sharpeDrop,
        ic_drop: icDrop,
        turnover_spike: turnoverSpike,
      },
      revision: monitorStatus.revision,
    };

    try {
      const updated = await advancedQuantApi.updateDriftSchedule(req);
      setMonitorStatus(updated);
      addToast({
        type: 'success',
        title: 'Schedule Updated',
        message: `Drift Sentinel schedule revision ${updated.revision} saved.`,
      });
      if (onRefresh) onRefresh();
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Schedule Update Failed',
        message: err?.message || 'Revision conflict or validation failure',
      });
      // Refresh to get current revision
      fetchStatus();
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="drift-monitor-panel flex flex-col gap-4 font-mono select-none" data-testid="drift-monitor-panel">
      {/* Sentinel Status Banner */}
      <div className="p-4 rounded-xl bg-zinc-900/70 border border-white/10 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-amber-400" />
            <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-wide">
              Autonomous Drift Sentinel & Concept Decay Engine
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span
              data-testid="drift-status"
              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                monitorStatus?.enabled
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40'
                  : 'bg-zinc-950 text-zinc-500 border border-white/10'
              }`}
            >
              {monitorStatus?.enabled ? 'SENTINEL ACTIVE' : 'SENTINEL DISABLED'}
            </span>
            <button
              onClick={fetchStatus}
              disabled={isLoading}
              className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
              title="Refresh Sentinel Status"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Telemetry Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-white/5 text-[11px]">
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Heartbeat</span>
            <span className="text-zinc-300 font-mono mt-0.5">
              {monitorStatus?.heartbeat ? new Date(monitorStatus.heartbeat).toLocaleTimeString() : 'N/A'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Last Evaluation</span>
            <span className="text-zinc-300 font-mono mt-0.5">
              {monitorStatus?.last_run ? new Date(monitorStatus.last_run).toLocaleDateString() : 'Never'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Next Scheduled</span>
            <span className="text-cyan-400 font-mono mt-0.5">
              {monitorStatus?.next_run ? new Date(monitorStatus.next_run).toLocaleDateString() : 'Auto (Cron)'}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-zinc-500 uppercase">Config Revision</span>
            <span className="text-purple-400 font-mono mt-0.5">rev #{monitorStatus?.revision || 1}</span>
          </div>
        </div>
      </div>

      {/* Schedule Configuration & Threshold Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
          <div className="flex items-center gap-2 pb-2 border-b border-white/5">
            <Clock className="w-4 h-4 text-cyan-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Inspection Cadence & Detection Thresholds
            </h4>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">Cron Schedule (UTC)</label>
              <input
                type="text"
                value={schedule}
                onChange={(e) => setSchedule(e.target.value)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
                placeholder="0 2 * * *"
              />
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">Timezone</label>
              <input
                type="text"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs focus:outline-none"
                placeholder="UTC"
              />
            </div>
            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer pb-1">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="rounded bg-zinc-950 border-white/20 text-emerald-500 focus:ring-0"
                />
                <span className="text-[11px] font-bold">Sentinel Enabled</span>
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-white/5 text-xs">
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">Sharpe Drop Threshold</label>
              <input
                type="number"
                step="0.05"
                min="0.05"
                max="1.0"
                value={sharpeDrop}
                onChange={(e) => setSharpeDrop(Number(e.target.value))}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 30% drop triggers alert</span>
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">IC Decay Threshold</label>
              <input
                type="number"
                step="0.005"
                min="0.001"
                max="0.1"
                value={icDrop}
                onChange={(e) => setIcDrop(Number(e.target.value))}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 0.015 drop triggers alert</span>
            </div>
            <div>
              <label className="text-[10px] text-zinc-400 block mb-1">Turnover Spike Threshold</label>
              <input
                type="number"
                step="0.02"
                min="0.01"
                max="0.5"
                value={turnoverSpike}
                onChange={(e) => setTurnoverSpike(Number(e.target.value))}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
              />
              <span className="text-[9px] text-zinc-500">&gt; 10% spike triggers alert</span>
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              onClick={handleSaveSchedule}
              disabled={isSaving}
              className={`py-1.5 px-3 rounded text-xs font-bold flex items-center gap-1.5 transition-all ${
                isSaving
                  ? 'bg-amber-950/40 text-amber-400 border border-amber-500/30 cursor-not-allowed'
                  : 'bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold'
              }`}
            >
              {isSaving ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              <span>Save Schedule (rev #{monitorStatus?.revision || 1})</span>
            </button>
          </div>
        </div>

        {/* Model Scope & Resolution */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
          <div className="flex items-center gap-2 pb-2 border-b border-white/5">
            <Layers className="w-4 h-4 text-purple-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Monitored Model Scope
            </h4>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-zinc-400">Evaluated in Catalog:</span>
              <span className="font-bold text-emerald-400">
                {monitorStatus?.evaluated_model_ids.length || 0} models
              </span>
            </div>
            <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
              {(monitorStatus?.evaluated_model_ids || []).map((m) => (
                <span
                  key={m}
                  className="px-1.5 py-0.5 rounded bg-zinc-950 text-[9px] text-zinc-300 border border-white/5"
                >
                  {m}
                </span>
              ))}
            </div>

            {monitorStatus?.missing_model_ids && monitorStatus.missing_model_ids.length > 0 && (
              <div className="flex flex-col gap-1 pt-2 border-t border-white/5">
                <span className="text-[10px] text-rose-400 font-bold">
                  Missing from Registry ({monitorStatus.missing_model_ids.length}):
                </span>
                <div className="flex flex-wrap gap-1">
                  {monitorStatus.missing_model_ids.map((m) => (
                    <span
                      key={m}
                      className="px-1.5 py-0.5 rounded bg-rose-950/40 text-[9px] text-rose-300 border border-rose-500/20"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Active Alerts Strip */}
      <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-2">
        <div className="flex items-center justify-between pb-2 border-b border-white/5">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <h4 className="text-xs font-bold text-zinc-200 uppercase">
              Sentinel Incident & Drift Log
            </h4>
          </div>
          <span className="text-[10px] text-zinc-400">
            {monitorStatus?.alerts.length || 0} Incidents Recorded
          </span>
        </div>

        {monitorStatus?.alerts && monitorStatus.alerts.length > 0 ? (
          <div className="flex flex-col gap-2">
            {monitorStatus.alerts.map((al, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded bg-rose-950/20 border border-rose-500/30 flex items-center justify-between text-xs font-mono"
              >
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                  <span className="text-rose-200">{al.message}</span>
                </div>
                <span className="text-[10px] text-zinc-400">{al.timestamp}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-3 rounded bg-emerald-950/20 border border-emerald-500/20 flex items-center gap-2 text-xs text-emerald-400 font-mono">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Autonomous Sentinel report: All monitored models operate within certified variance envelope.</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default DriftMonitorPanel;
