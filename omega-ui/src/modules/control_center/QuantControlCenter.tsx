import React, { useRef, useState } from 'react';
import { Activity, Bot, BrainCircuit, Database, FileCheck2, FlaskConical, Layers3, WalletCards } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { OperationsCircuitBreakerResponse } from '../../api/advancedQuant';
import { useControlOps } from '../../hooks/useControlOps';
import { useTranslation } from '../../i18n';
import { useUiStore } from '../../store/uiStore';
import { TotpRebalanceModal } from '../execution_blotter/TotpRebalanceModal';
import { CONTROL_CENTER_TABS, ControlCenterTab, RunOperation } from './controlCenterTypes';
import { AlphasTab } from './tabs/AlphasTab';
import { BacktestTab } from './tabs/BacktestTab';
import { CopilotTab } from './tabs/CopilotTab';
import { IngestTab } from './tabs/IngestTab';
import { LlmBridgeTab } from './tabs/LlmBridgeTab';
import { OverviewTab } from './tabs/OverviewTab';
import { PortfolioTab } from './tabs/PortfolioTab';
import { ReceiptsTab } from './tabs/ReceiptsTab';

const TAB_META = {
  overview: { label: 'Overview', icon: Activity }, ingest: { label: 'Ingest', icon: Database },
  alphas: { label: 'Alphas', icon: FlaskConical }, portfolio: { label: 'Portfolio', icon: WalletCards },
  backtest: { label: 'Backtest', icon: Layers3 }, receipts: { label: 'Receipts', icon: FileCheck2 },
  copilot: { label: 'Copilot', icon: Bot }, llm_bridge: { label: 'LLM Bridge', icon: BrainCircuit },
} satisfies Record<ControlCenterTab, { label: string; icon: React.ComponentType<{ className?: string }> }>;

function isControlCenterTab(value: string): value is ControlCenterTab { return CONTROL_CENTER_TABS.includes(value as ControlCenterTab); }

export const QuantControlCenter: React.FC = () => {
  const { t } = useTranslation();
  const storedTab = useUiStore((state) => state.activeSubTabs.control_center);
  const setActiveSubTab = useUiStore((state) => state.setActiveSubTab);
  const addToast = useUiStore((state) => state.addToast);
  const lockedOperations = useRef(new Set<string>());
  const { activeTaskList, isTotpModalOpen, setIsTotpModalOpen, isKillSwitchEngaged, setIsDrawerOpen, stopIngestTask, triggerIngestData, triggerComputeAlphas, triggerOptimizePortfolio, triggerRunBacktest, triggerKillSwitch } = useControlOps();
  const [breakerObservation, setBreakerObservation] = useState<OperationsCircuitBreakerResponse | null>(null);
  const halted = isKillSwitchEngaged || breakerObservation?.circuit_broken === true;
  const [totpAction, setTotpAction] = useState<'REBALANCE' | 'KILL_SWITCH'>('REBALANCE');
  const [sources, setSources] = useState(['vci']); const [forceRefresh, setForceRefresh] = useState(false);
  const [alphaUniverse, setAlphaUniverse] = useState('FPT,HPG,MBB,MWG');
  const [portfolioObjective, setPortfolioObjective] = useState('ALPHA_RANK_RISK_CAPPED'); const [maxWeight, setMaxWeight] = useState('0.15'); const [portfolioUniverse, setPortfolioUniverse] = useState('FPT,HPG,MBB,MWG');
  const [strategyId, setStrategyId] = useState('ALPHA_HRP_V2'); const [startDate, setStartDate] = useState('2020-01-01'); const [slippageBps, setSlippageBps] = useState('15'); const [commissionBps, setCommissionBps] = useState('10');
  const activeTab = isControlCenterTab(storedTab) ? storedTab : 'overview';
  const runOperation: RunOperation = async (name, operation) => {
    if (lockedOperations.current.has(name)) return;
    lockedOperations.current.add(name);
    try { await operation(); }
    catch (error) { addToast({ type: 'error', title: `${name} failed`, message: error instanceof Error ? error.message : 'Unexpected operation error.' }); }
    finally { lockedOperations.current.delete(name); }
  };
  const renderTab = () => {
    switch (activeTab) {
      case 'ingest': return <IngestTab activeTasks={activeTaskList} runOperation={runOperation} onIngest={triggerIngestData} onStopIngest={stopIngestTask} sources={sources} setSources={setSources} forceRefresh={forceRefresh} setForceRefresh={setForceRefresh} />;
      case 'alphas': return <AlphasTab runOperation={runOperation} onCompute={triggerComputeAlphas} universe={alphaUniverse} setUniverse={setAlphaUniverse} />;
      case 'portfolio': return <PortfolioTab runOperation={runOperation} onOptimize={triggerOptimizePortfolio} onRebalance={async () => { setTotpAction('REBALANCE'); setIsTotpModalOpen(true); }} objective={portfolioObjective} setObjective={setPortfolioObjective} maxWeight={maxWeight} setMaxWeight={setMaxWeight} universe={portfolioUniverse} setUniverse={setPortfolioUniverse} />;
      case 'backtest': return <BacktestTab runOperation={runOperation} onRun={triggerRunBacktest} strategyId={strategyId} setStrategyId={setStrategyId} startDate={startDate} setStartDate={setStartDate} slippageBps={slippageBps} setSlippageBps={setSlippageBps} commissionBps={commissionBps} setCommissionBps={setCommissionBps} />;
      case 'receipts': return <ReceiptsTab onOpenOps={() => setIsDrawerOpen(true)} />;
      case 'copilot': return <CopilotTab />;
      case 'llm_bridge': return <LlmBridgeTab />;
      default: return <OverviewTab onBreakerObservation={setBreakerObservation} activeTasks={activeTaskList} isKillSwitchEngaged={isKillSwitchEngaged} onOpenOps={() => setIsDrawerOpen(true)} onKillSwitch={() => { setTotpAction('KILL_SWITCH'); setIsTotpModalOpen(true); }} />;
    }
  };
  return <div className="flex h-full flex-col gap-4 font-mono">
    <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-zinc-900/90 p-4"><div><h1 className="text-sm font-bold text-zinc-100">{t.controlCenter.title}</h1><p className="mt-1 text-xs text-zinc-500">Operations, research, execution governance.</p></div><span role="status" className={`rounded border px-2 py-1 text-[10px] font-bold ${halted ? 'border-rose-500/30 bg-rose-950/50 text-rose-300' : breakerObservation ? 'border-emerald-500/30 bg-emerald-950/50 text-emerald-300' : 'border-white/20 text-zinc-300'}`}>{halted ? 'SYSTEM HALTED' : breakerObservation ? 'BREAKER NORMAL (OBSERVED)' : 'BREAKER UNAVAILABLE'}</span></header>
    <nav aria-label="Quant Control Center sections" className="flex flex-wrap gap-1 rounded-xl border border-white/10 bg-zinc-950 p-1.5">{CONTROL_CENTER_TABS.map((tab) => { const { label, icon: Icon } = TAB_META[tab]; return <button key={tab} type="button" aria-current={activeTab === tab ? 'page' : undefined} onClick={() => setActiveSubTab('control_center', tab)} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition-colors ${activeTab === tab ? 'bg-cyan-400 text-zinc-950' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100'}`}><Icon className="h-4 w-4" />{label}</button>; })}</nav>
    <main className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950/60 p-4">{renderTab()}</main>
    <TotpRebalanceModal isOpen={isTotpModalOpen} onClose={() => setIsTotpModalOpen(false)} actionType={totpAction} title={totpAction === 'KILL_SWITCH' ? 'AUTHORIZE EMERGENCY HALT' : undefined} description={totpAction === 'KILL_SWITCH' ? 'Enter a 6-digit TOTP code to halt OMS gateways and cancel active orders.' : undefined} onConfirm={async (totp_code) => {
      try {
        if (totpAction === 'KILL_SWITCH') {
          await triggerKillSwitch({ totp_code, reason: 'Operator emergency halt', cancel_active_orders: true, freeze_engines: true });
          return;
        }
        await apiClient.triggerRebalance({ totp_code });
      } catch (error) {
        addToast({ type: 'error', title: 'Rebalance authorization failed', message: error instanceof Error ? error.message : 'Unexpected authorization error.' });
        throw error;
      }
    }} />
  </div>;
};
