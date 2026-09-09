import { useEffect, useRef, useState } from 'react';
import { advancedQuantApi, ResourceGovernorStateResponse } from '../../../api/advancedQuant';
import { useUiStore } from '../../../store/uiStore';
import type { OverviewTabProps } from '../controlCenterTypes';

export function OverviewTab({ activeTasks, isKillSwitchEngaged, onOpenOps, onKillSwitch }: OverviewTabProps) {
  const [governor, setGovernor] = useState<ResourceGovernorStateResponse | null>(null);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState(false); const addToast = useUiStore((state) => state.addToast); const generation = useRef(0); const governorUpdateLock = useRef(false);
  useEffect(() => { const controller = new AbortController(); const current = ++generation.current; void advancedQuantApi.getResourceGovernor(controller.signal).then((data) => { if (current === generation.current) setGovernor(data); }).catch((error) => { if (!controller.signal.aborted && current === generation.current) addToast({ type: 'error', title: 'Governor telemetry failed', message: error instanceof Error ? error.message : 'Unexpected telemetry error.' }); }); return () => controller.abort(); }, [addToast]);
  const toggleGovernorMode = async () => {
    if (!governor || governorUpdateLock.current) return;
    governorUpdateLock.current = true;
    setIsUpdatingGovernor(true);
    try { setGovernor(await advancedQuantApi.updateResourceGovernor({ mode: governor.mode === 'COPILOT' ? 'MANUAL' : 'COPILOT' })); }
    catch (error) { addToast({ type: 'error', title: 'Governor update failed', message: error instanceof Error ? error.message : 'Unexpected governor update error.' }); }
    finally { governorUpdateLock.current = false; setIsUpdatingGovernor(false); }
  };
  return <section className="space-y-3"><div className="grid gap-3 sm:grid-cols-3"><Metric label="Governor" value={governor?.mode ?? 'UNAVAILABLE'} /><Metric label="Workers" value={governor ? `${governor.active_workers}/${governor.target_concurrency}` : '--'} /><Metric label="Active tasks" value={String(activeTasks.filter((task) => task.status === 'RUNNING').length)} /></div><div className="flex gap-2"><button disabled={!governor || isUpdatingGovernor} className="rounded border border-violet-400 px-3 py-2 text-xs font-bold text-violet-300 disabled:opacity-50" onClick={() => void toggleGovernorMode()}>{isUpdatingGovernor ? 'UPDATING GOVERNOR' : governor?.mode === 'COPILOT' ? 'SWITCH TO MANUAL' : 'SWITCH TO COPILOT'}</button><button className="rounded border border-cyan-400 px-3 py-2 text-xs font-bold text-cyan-300" onClick={onOpenOps}>OPEN OPS DRAWER</button><button disabled={isKillSwitchEngaged} className="rounded border border-rose-500 px-3 py-2 text-xs font-bold text-rose-300 disabled:opacity-50" onClick={onKillSwitch}>{isKillSwitchEngaged ? 'SYSTEM HALTED' : 'EMERGENCY HALT'}</button></div></section>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-white/10 bg-zinc-900/80 p-4 font-mono"><p className="text-xs uppercase text-zinc-500">{label}</p><p className="mt-1 text-lg font-bold text-zinc-100">{value}</p></div>; }
