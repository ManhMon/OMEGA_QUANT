import React, { useState, useEffect } from 'react';
import {
  Database,
  Cpu,
  Layers,
  Play,
  ShieldAlert,
  RefreshCw,
  Sliders,
  Activity,
  GitBranch
} from 'lucide-react';
import { useControlOps } from '../../hooks/useControlOps';
import { useUiStore } from '../../store/uiStore';
import { advancedQuantApi, ResourceGovernorStateResponse } from '../../api/advancedQuant';
import { TotpRebalanceModal } from '../execution_blotter/TotpRebalanceModal';
import { useTranslation } from '../../i18n';

export const QuantControlCenter: React.FC = () => {
  const {
    activeTaskList,
    setIsDrawerOpen,
    isTotpModalOpen,
    setIsTotpModalOpen,
    isKillSwitchEngaged,
    triggerIngestData,
    triggerComputeAlphas,
    triggerOptimizePortfolio,
    triggerRunBacktest,
    triggerKillSwitch
  } = useControlOps();

  const { t } = useTranslation();
  const setActiveModule = useUiStore((state) => state.setActiveModule);
  const addToast = useUiStore((state) => state.addToast);

  const [governorState, setGovernorState] = useState<ResourceGovernorStateResponse | null>(null);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState<boolean>(false);

  useEffect(() => {
    advancedQuantApi.getResourceGovernor()
      .then((res) => setGovernorState(res))
      .catch(() => {});
  }, []);

  const handleToggleGovernor = async () => {
    try {
      setIsUpdatingGovernor(true);
      const nextMode = governorState?.mode === 'COPILOT' ? 'MANUAL' : 'COPILOT';
      const res = await advancedQuantApi.updateResourceGovernor({ mode: nextMode });
      if (res) {
        setGovernorState(res);
        addToast({
          type: 'success',
          title: 'Resource Governor Updated',
          message: `Switched to ${nextMode} mode`
        });
      }
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Governor Error',
        message: err?.message || 'Failed to update governor'
      });
    } finally {
      setIsUpdatingGovernor(false);
    }
  };

  // Ingest state
  const [sources, setSources] = useState<string[]>(['vci', 'macro', 'news']);
  const [forceRefresh, setForceRefresh] = useState(false);

  // Alpha state
  const [universe, setUniverse] = useState('VN703');
  const [icThreshold, setIcThreshold] = useState(0.03);
  const [irThreshold, setIrThreshold] = useState(0.5);
  const [parallelJobs, setParallelJobs] = useState(4);

  // Portfolio state
  const [optObjective, setOptObjective] = useState('MAX_SHARPE');
  const [maxWeight, setMaxWeight] = useState(0.15);
  const [sectorCap, setSectorCap] = useState(0.35);
  const [cvarConf, setCvarConf] = useState(0.99);

  // Backtest state
  const [btStrategy, setBtStrategy] = useState('ALPHA_HRP_V2');
  const [btStartDate, setBtStartDate] = useState('2020-01-01');
  const [btSlippage, setBtSlippage] = useState(15);
  const [btCommission, setBtCommission] = useState(10);

  const toggleSource = (src: string) => {
    setSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src]
    );
  };

  const handleExecuteKillSwitch = async (code: string) => {
    await triggerKillSwitch({
      totp_code: code,
      reason: 'EMERGENCY_RISK_BREACH',
      cancel_active_orders: true,
      freeze_engines: true
    });
  };

  return (
    <div className="flex flex-col gap-6 h-full font-mono select-none">
      {/* Top Banner Status */}
      <div className={`p-4 rounded-xl border flex items-center justify-between transition-colors ${
        isKillSwitchEngaged
          ? 'bg-rose-950/40 border-rose-500/50 text-rose-300'
          : 'bg-zinc-900/80 border-white/10 text-zinc-300'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${isKillSwitchEngaged ? 'bg-rose-500 animate-ping' : 'bg-emerald-400 animate-pulse'}`} />
          <div>
            <div className="font-bold text-sm text-zinc-100 flex items-center gap-2">
              <span>{t.controlCenter.title}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded border ${
                isKillSwitchEngaged
                  ? 'bg-rose-900/80 border-rose-500/50 text-rose-300'
                  : 'bg-emerald-950 border-emerald-500/30 text-emerald-400'
              }`}>
                {isKillSwitchEngaged ? t.controlCenter.systemHalted : t.controlCenter.standbyArmed}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {t.controlCenter.description}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setActiveModule('model_registry')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/60 text-xs border border-emerald-500/30 text-emerald-300 transition-colors"
          >
            <GitBranch className="w-3.5 h-3.5 text-emerald-400" />
            <span>MODEL GOVERNANCE</span>
          </button>

          <button
            onClick={handleToggleGovernor}
            disabled={isUpdatingGovernor}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors ${
              governorState?.mode === 'COPILOT'
                ? 'bg-cyan-950/60 border-cyan-500/40 text-cyan-300'
                : 'bg-zinc-800 border-white/10 text-zinc-300 hover:bg-zinc-700'
            }`}
          >
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span>GOVERNOR: {governorState?.mode || 'MANUAL'}</span>
          </button>

          <button
            onClick={() => setIsDrawerOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs border border-white/10 text-zinc-200 transition-colors"
          >
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            <span>{t.controlCenter.opsDrawerBtn} ({activeTaskList.length})</span>
          </button>

          <button
            onClick={() => setIsTotpModalOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 text-xs border border-rose-500/40 font-bold transition-colors"
          >
            <ShieldAlert className="w-4 h-4 text-rose-400" />
            <span>{t.controlCenter.killSwitchBtn}</span>
          </button>
        </div>
      </div>

      {/* Grid of 4 Core Interactive Operational Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 overflow-y-auto pr-1">
        {/* Pillar 1: Market Data Ingestion */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col justify-between hover:border-emerald-500/30 transition-colors">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-400" />
                <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.dataIngestionTitle}</h2>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/20">
                HOSE/HNX 703
              </span>
            </div>

            <div className="flex flex-col gap-2 text-xs">
              <label className="text-zinc-400 text-[11px]">{t.controlCenter.sourcesLabel}</label>
              <div className="flex items-center gap-2">
                {['vci', 'macro', 'news'].map((src) => (
                  <button
                    key={src}
                    onClick={() => toggleSource(src)}
                    className={`px-2.5 py-1 rounded text-xs border transition-colors ${
                      sources.includes(src)
                        ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
                        : 'bg-zinc-800 border-white/5 text-zinc-500'
                    }`}
                  >
                    {src.toUpperCase()}
                  </button>
                ))}
              </div>

              <div className="flex items-center justify-between pt-2">
                <span className="text-zinc-400 text-[11px]">{t.controlCenter.forceCacheLabel}</span>
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(e) => setForceRefresh(e.target.checked)}
                  className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => triggerIngestData({ sources, force_refresh: forceRefresh, symbols: ['ALL'] })}
            className="mt-4 w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-lg shadow-emerald-950"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>{t.controlCenter.dispatchIngestBtn}</span>
          </button>
        </div>

        {/* Pillar 2: Alpha Factor Engine */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col justify-between hover:border-cyan-500/30 transition-colors">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.alphaEngineTitle}</h2>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-500/20">
                APSE REGISTRY
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.universeLabel}</span>
                <select
                  value={universe}
                  onChange={(e) => setUniverse(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                >
                  <option value="VN703">VN703 Full Universe</option>
                  <option value="VN30">VN30 Bluechips</option>
                  <option value="VN100">VN100 Liquid</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.parallelWorkersLabel}</span>
                <input
                  type="number"
                  min="1"
                  max="16"
                  value={parallelJobs}
                  onChange={(e) => setParallelJobs(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.minIcLabel}</span>
                <input
                  type="number"
                  step="0.01"
                  value={icThreshold}
                  onChange={(e) => setIcThreshold(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.minIrLabel}</span>
                <input
                  type="number"
                  step="0.1"
                  value={irThreshold}
                  onChange={(e) => setIrThreshold(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => triggerComputeAlphas({ universe: ['FPT', 'HPG', 'MBB', 'MWG', 'DGC', 'VNM', 'TCB', 'PNJ'], alpha_families: ['MOMENTUM'] })}
            className="mt-4 w-full py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-lg shadow-cyan-950"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{t.controlCenter.dispatchAlphaBtn}</span>
          </button>
        </div>

        {/* Pillar 3: Portfolio Optimization & Barra */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col justify-between hover:border-amber-500/30 transition-colors">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-amber-400" />
                <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.portfolioOptTitle}</h2>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-500/20">
                HRP / CVAR
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.solverObjectiveLabel}</span>
                <select
                  value={optObjective}
                  onChange={(e) => setOptObjective(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                >
                  <option value="MAX_SHARPE">Max Expected Sharpe</option>
                  <option value="MIN_CVAR">Min CVaR Risk (Tail)</option>
                  <option value="RISK_PARITY">Hierarchical Risk Parity</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.cvarConfidenceLabel}</span>
                <select
                  value={cvarConf}
                  onChange={(e) => setCvarConf(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                >
                  <option value={0.99}>99.0% Confidence</option>
                  <option value={0.95}>95.0% Confidence</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.maxStockCapLabel}</span>
                <input
                  type="number"
                  step="0.01"
                  value={maxWeight}
                  onChange={(e) => setMaxWeight(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.maxSectorCapLabel}</span>
                <input
                  type="number"
                  step="0.01"
                  value={sectorCap}
                  onChange={(e) => setSectorCap(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => triggerOptimizePortfolio({ objective: 'ALPHA_RANK_RISK_CAPPED', max_single_weight: maxWeight })}
            className="mt-4 w-full py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-lg shadow-amber-950"
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>{t.controlCenter.dispatchSolverBtn}</span>
          </button>
        </div>

        {/* Pillar 4: Walk-Forward Backtester */}
        <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col justify-between hover:border-purple-500/30 transition-colors">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-purple-400 fill-current" />
                <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.backtesterTitle}</h2>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950 text-purple-400 border border-purple-500/20">
                PURGED CPCV
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.strategyIdLabel}</span>
                <select
                  value={btStrategy}
                  onChange={(e) => setBtStrategy(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                >
                  <option value="ALPHA_HRP_V2">Alpha HRP v2 (Official)</option>
                  <option value="MOMENTUM_VN30">Momentum Trend Filter</option>
                  <option value="QUALITY_BARRA">Quality-Value Barra</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.startDateLabel}</span>
                <input
                  type="date"
                  value={btStartDate}
                  onChange={(e) => setBtStartDate(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.slippageBpsLabel}</span>
                <input
                  type="number"
                  value={btSlippage}
                  onChange={(e) => setBtSlippage(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-zinc-400 text-[10px]">{t.controlCenter.commissionBpsLabel}</span>
                <input
                  type="number"
                  value={btCommission}
                  onChange={(e) => setBtCommission(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded px-2 py-1 text-zinc-200 text-xs"
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => triggerRunBacktest({ strategy_id: btStrategy, start_date: btStartDate, slippage_bps: btSlippage, commission_bps: btCommission })}
            className="mt-4 w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-lg shadow-purple-950"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{t.controlCenter.dispatchBacktestBtn}</span>
          </button>
        </div>
      </div>

      {/* TOTP Confirmation Modal */}
      <TotpRebalanceModal
        isOpen={isTotpModalOpen}
        onClose={() => setIsTotpModalOpen(false)}
        onConfirm={handleExecuteKillSwitch}
        title={t.controlCenter.modalTitle}
        description={t.controlCenter.modalDescription}
        actionType="KILL_SWITCH"
      />
    </div>
  );
};
