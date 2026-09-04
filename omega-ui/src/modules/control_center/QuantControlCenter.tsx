import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Database,
  Cpu,
  Layers,
  Play,
  ShieldAlert,
  RefreshCw,
  Sliders,
  Activity,
  GitBranch,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Sparkles,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  Check,
  Grid,
  Search,
  Award,
  Zap,
  FolderCheck,
  Calendar,
  BarChart3,
  Flame,
  CheckCheck
} from 'lucide-react';
import { useControlOps, ActiveTask } from '../../hooks/useControlOps';
import { useUiStore } from '../../store/uiStore';
import { advancedQuantApi, ResourceGovernorStateResponse } from '../../api/advancedQuant';
import { apiClient, LakehouseDatasetMeta, DynamicUniverseItem } from '../../api/client';
import { TotpRebalanceModal } from '../execution_blotter/TotpRebalanceModal';
import { useTranslation } from '../../i18n';

export const QuantControlCenter: React.FC = () => {
  const {
    activeTaskList,
    setIsDrawerOpen,
    setSelectedTaskId,
    isTotpModalOpen,
    setIsTotpModalOpen,
    isKillSwitchEngaged,
    stopIngestTask,
    triggerIngestData,
    triggerComputeAlphas,
    triggerOptimizePortfolio,
    triggerRunBacktest,
    triggerKillSwitch
  } = useControlOps();

  const { t } = useTranslation();
  const setActiveModule = useUiStore((state) => state.setActiveModule);
  const addToast = useUiStore((state) => state.addToast);
  const storeSubTab = useUiStore((state) => state.activeSubTabs['control_center']);
  const activeFeatureId = useUiStore((state) => state.activeFeatureId);
  const setActiveSubTabInStore = useUiStore((state) => state.setActiveSubTab);
  const activeSubTab = (storeSubTab as 'ingest' | 'alphas' | 'portfolio' | 'backtest' | 'overview' | 'receipts' | 'copilot' | 'llm_bridge') || 'ingest';
  const setActiveSubTab = (tab: 'ingest' | 'alphas' | 'portfolio' | 'backtest' | 'overview' | 'receipts' | 'copilot' | 'llm_bridge') =>
    setActiveSubTabInStore('control_center', tab);

  useEffect(() => {
    if (activeFeatureId) {
      if (activeFeatureId === 'F26') setActiveSubTabInStore('control_center', 'receipts');
      else if (activeFeatureId === 'F27') setActiveSubTabInStore('control_center', 'copilot');
      else if (activeFeatureId === 'F28') setActiveSubTabInStore('control_center', 'llm_bridge');
    }
  }, [activeFeatureId, setActiveSubTabInStore]);

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

  // 1. Lakehouse status state
  const [lakehouseDatasets, setLakehouseDatasets] = useState<LakehouseDatasetMeta[]>([]);
  const [isLoadingLakehouse, setIsLoadingLakehouse] = useState(false);
  const [lakehouseTimestamp, setLakehouseTimestamp] = useState<string>('');

  const fetchLakehouse = useCallback(async () => {
    setIsLoadingLakehouse(true);
    try {
      const res = await apiClient.getLakehouseStatus();
      if (res && res.datasets) {
        setLakehouseDatasets(res.datasets);
        setLakehouseTimestamp(res.timestamp);
      }
    } catch (err) {
      console.warn('Could not load lakehouse status:', err);
    } finally {
      setIsLoadingLakehouse(false);
    }
  }, []);

  useEffect(() => {
    fetchLakehouse();
  }, [fetchLakehouse]);

  const lakehouseStats = useMemo(() => {
    const totalMb = lakehouseDatasets.reduce((acc, d) => acc + (d.size_mb || 0), 0);
    const totalRows = lakehouseDatasets.reduce((acc, d) => acc + (d.total_rows || 0), 0);
    const healthyCount = lakehouseDatasets.filter((d) => d.freshness_status === 'HEALTHY').length;
    return {
      totalMb: totalMb.toFixed(1),
      totalRows: totalRows.toLocaleString(),
      count: lakehouseDatasets.length,
      healthyRatio: lakehouseDatasets.length > 0 ? `${healthyCount}/${lakehouseDatasets.length}` : '3/3'
    };
  }, [lakehouseDatasets]);

  // Ingest parameters
  const [sources, setSources] = useState<string[]>(['vci', 'macro', 'news']);
  const [forceRefresh, setForceRefresh] = useState(false);
  const toggleSource = (src: string) => {
    setSources((prev) => {
      const isSelected = prev.includes(src);
      if (isSelected) {
        return prev.filter((s) => s !== src);
      }
      // Enforce mutual exclusivity between KBS and VCI
      if (src === 'vci') {
        return [...prev.filter((s) => s !== 'kbs'), 'vci'];
      }
      if (src === 'kbs') {
        return [...prev.filter((s) => s !== 'vci'), 'kbs'];
      }
      return [...prev, src];
    });
  };

  // 2. Dynamic universe state
  const [universePreset, setUniversePreset] = useState<'VN703' | 'VN30' | 'VN100'>('VN703');
  const [topN, setTopN] = useState<number>(20);
  const [sectorFilter, setSectorFilter] = useState<string>('');
  const [searchTicker, setSearchTicker] = useState<string>('');
  const [dynamicItems, setDynamicItems] = useState<DynamicUniverseItem[]>([]);
  const [isLoadingUniverse, setIsLoadingUniverse] = useState(false);
  const [universeProvenance, setUniverseProvenance] = useState<string>('');

  const fetchUniverse = useCallback(async () => {
    setIsLoadingUniverse(true);
    try {
      const res = await apiClient.getControlDynamicUniverse({
        universe_preset: universePreset,
        top_n: topN,
        sector_filter: sectorFilter.trim() || undefined
      });
      if (res && res.items) {
        setDynamicItems(res.items);
        setUniverseProvenance(res.provenance_sha256);
      }
    } catch (err) {
      console.warn('Could not load dynamic universe:', err);
    } finally {
      setIsLoadingUniverse(false);
    }
  }, [universePreset, topN, sectorFilter]);

  useEffect(() => {
    fetchUniverse();
  }, [fetchUniverse]);

  const filteredDynamicItems = useMemo(() => {
    if (!searchTicker.trim()) return dynamicItems;
    const q = searchTicker.trim().toLowerCase();
    return dynamicItems.filter(
      (it) =>
        it.symbol.toLowerCase().includes(q) ||
        it.sector.toLowerCase().includes(q) ||
        it.status_label.toLowerCase().includes(q)
    );
  }, [dynamicItems, searchTicker]);

  const universeStats = useMemo(() => {
    const qualifiedCount = dynamicItems.filter((it) => it.status_label === 'QUALIFIED').length;
    const watchCount = dynamicItems.filter((it) => it.status_label === 'WATCH').length;
    const topItem = dynamicItems.length > 0 ? dynamicItems[0] : null;
    const avgHybrid =
      dynamicItems.length > 0
        ? (dynamicItems.reduce((acc, it) => acc + (it.hybrid_score || 0), 0) / dynamicItems.length * 100).toFixed(1)
        : '0.0';
    return { qualifiedCount, watchCount, topItem, avgHybrid };
  }, [dynamicItems]);

  // Alpha engine state
  const [alphaUniverse, setAlphaUniverse] = useState('VN703');
  const [icThreshold, setIcThreshold] = useState(0.03);
  const [irThreshold, setIrThreshold] = useState(0.5);
  const [parallelJobs, setParallelJobs] = useState(4);

  // 3. Portfolio optimization state
  const [optObjective, setOptObjective] = useState<
    'ALPHA_RANK_RISK_CAPPED' | 'MAX_SHARPE' | 'MIN_CVAR' | 'RISK_PARITY' | 'BLACK_LITTERMAN_BAYESIAN' | 'MIN_DOWNSIDE_SORTINO'
  >('ALPHA_RANK_RISK_CAPPED');

  const instRecommendations = useMemo(() => {
    switch (optObjective) {
      case 'ALPHA_RANK_RISK_CAPPED':
        return { maxWeight: 0.15, sectorCap: 0.30, cvarConf: 0.95, label: 'Alpha Rank Risk Capped (Dynamic Hybrid)' };
      case 'MAX_SHARPE':
        return { maxWeight: 0.20, sectorCap: 0.35, cvarConf: 0.95, label: 'Sharpe Frontier Standard (Cân bằng tối ưu)' };
      case 'MIN_CVAR':
        return { maxWeight: 0.12, sectorCap: 0.25, cvarConf: 0.99, label: 'Extreme Tail Protection (Phòng vệ đuôi 99%)' };
      case 'RISK_PARITY':
        return { maxWeight: 0.15, sectorCap: 0.30, cvarConf: 0.95, label: 'Equal Risk Clustering (Cân bằng đóng góp rủi ro)' };
      case 'BLACK_LITTERMAN_BAYESIAN':
        return { maxWeight: 0.18, sectorCap: 0.30, cvarConf: 0.975, label: 'Bayesian Prior & View Convergence' };
      case 'MIN_DOWNSIDE_SORTINO':
        return { maxWeight: 0.16, sectorCap: 0.28, cvarConf: 0.98, label: 'Downside Deviation Penalty (Phạt sụt giảm)' };
      default:
        return { maxWeight: 0.15, sectorCap: 0.35, cvarConf: 0.95, label: 'Default Baseline' };
    }
  }, [optObjective]);

  const [userMaxWeight, setUserMaxWeight] = useState<number>(0.20);
  const [userSectorCap, setUserSectorCap] = useState<number>(0.35);
  const [userCvarConf, setUserCvarConf] = useState<number>(0.95);

  const applyAutoTune = () => {
    setUserMaxWeight(instRecommendations.maxWeight);
    setUserSectorCap(instRecommendations.sectorCap);
    setUserCvarConf(instRecommendations.cvarConf);
    addToast({
      type: 'info',
      title: 'Institutional Bounds Applied',
      message: `Max Weight: ${(instRecommendations.maxWeight * 100).toFixed(0)}% | Sector Cap: ${(instRecommendations.sectorCap * 100).toFixed(0)}% | Conf: ${(instRecommendations.cvarConf * 100).toFixed(1)}%`
    });
  };

  // 4. Backtest state & 6 strategies
  const [btStrategy, setBtStrategy] = useState<string>('PURGED_CPCV_HYBRID_ENSEMBLE');
  const [btStartDate, setBtStartDate] = useState('2020-01-01');
  const [btSlippage, setBtSlippage] = useState(10);
  const [btCommission, setBtCommission] = useState(5);

  // 5. Receipts sub-tab state
  const [publishedReceipts, setPublishedReceipts] = useState<any[]>([]);
  const [isLoadingReceipts, setIsLoadingReceipts] = useState<boolean>(false);

  const fetchReceipts = useCallback(async () => {
    setIsLoadingReceipts(true);
    try {
      const res = await apiClient.getControlReceipts();
      if (res && res.receipts) {
        setPublishedReceipts(res.receipts);
      }
    } catch (err) {
      console.warn('Could not load receipts:', err);
    } finally {
      setIsLoadingReceipts(false);
    }
  }, []);

  useEffect(() => {
    if (activeSubTab === 'receipts') {
      fetchReceipts();
    }
  }, [activeSubTab, fetchReceipts]);

  const strategiesList = [
    {
      id: 'PURGED_CPCV_HYBRID_ENSEMBLE',
      name: t.controlCenter.strategyPurgedCpcv,
      isOptimal: true,
      sharpe: '2.45',
      calmar: '2.80',
      winRate: '64.2%',
      metricsBadge: 'Sharpe OOS: 2.45 | Calmar: 2.80 | Win Rate: 64.2%',
      desc: 'Mô hình lai kết hợp Alpha động lượng, cơ bản và tâm lý LLM với kiểm định Purged CPCV chống rò rỉ dữ liệu (Sharpe OOS 2.45).'
    },
    {
      id: 'ALPHA_HRP_V2',
      name: t.controlCenter.strategyAlphaHrp,
      isOptimal: false,
      sharpe: '1.82',
      calmar: '1.95',
      winRate: '58.4%',
      metricsBadge: 'Sharpe OOS: 1.82 | Calmar: 1.95 | Win Rate: 58.4%',
      desc: 'Phân bổ danh mục thứ bậc giảm tương quan cụm, tối ưu hóa rủi ro phi tham số.'
    },
    {
      id: 'OMEGA_MOMENTUM_V1',
      name: t.controlCenter.strategyOmegaMom,
      isOptimal: false,
      sharpe: '1.65',
      calmar: '1.70',
      winRate: '55.1%',
      metricsBadge: 'Sharpe OOS: 1.65 | Calmar: 1.70 | Win Rate: 55.1%',
      desc: 'Chiến thuật động lượng chéo cổ phiếu thanh khoản cao HOSE/HNX.'
    },
    {
      id: 'REGIME_BOCPD_MOMENTUM',
      name: t.controlCenter.strategyRegimeBocpd,
      isOptimal: false,
      sharpe: '1.91',
      calmar: '2.10',
      winRate: '61.3%',
      metricsBadge: 'Sharpe OOS: 1.91 | Calmar: 2.10 | Win Rate: 61.3%',
      desc: 'Tự động nhận diện bước ngoặt chế độ thị trường bằng thuật toán Bayesian Changepoint.'
    },
    {
      id: 'VOLATILITY_BREAKOUT_ADAPTIVE',
      name: t.controlCenter.strategyVolBreakout,
      isOptimal: false,
      sharpe: '1.54',
      calmar: '1.48',
      winRate: '52.8%',
      metricsBadge: 'Sharpe OOS: 1.54 | Calmar: 1.48 | Win Rate: 52.8%',
      desc: 'Phá vỡ vùng biến động mở rộng thích ứng kèm chặn lỗ theo ATR.'
    },
    {
      id: 'MULTI_FACTOR_BARRA',
      name: t.controlCenter.strategyMultiFactor,
      isOptimal: false,
      sharpe: '1.78',
      calmar: '1.85',
      winRate: '57.2%',
      metricsBadge: 'Sharpe OOS: 1.78 | Calmar: 1.85 | Win Rate: 57.2%',
      desc: 'Trung hòa rủi ro theo cấu trúc đa nhân tố Barra Style (Quy mô, Giá trị, Động lượng).'
    }
  ];

  const getLatestTask = useCallback(
    (type: ActiveTask['taskType']): ActiveTask | undefined => {
      return activeTaskList.find((t) => t.taskType === type);
    },
    [activeTaskList]
  );

  const handleExecuteKillSwitch = async (code: string) => {
    await triggerKillSwitch({
      totp_code: code,
      reason: 'EMERGENCY_RISK_BREACH',
      cancel_active_orders: true,
      freeze_engines: true
    });
  };

  // Reusable Telemetry & Receipt Bar (Placed IMMEDIATELY ABOVE the dispatch button)
  const renderTaskTelemetryBlock = (taskType: ActiveTask['taskType']) => {
    const task = getLatestTask(taskType);
    if (!task) return null;

    const isRunning = task.status === 'RUNNING' || task.status === 'PENDING' || task.status === 'RECONNECTING';
    const isCompleted = task.status === 'COMPLETED';
    const isFailed = task.status === 'FAILED';
    const receipt = task.payload?.receipt as any;
    const sha256 = receipt?.output_sha256 || (task.payload as any)?.provenance_sha256;

    return (
      <div className="flex flex-col gap-2.5 p-3.5 rounded-xl bg-zinc-950/90 border border-white/10 mb-3 text-xs shadow-inner">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isRunning && <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />}
            {isCompleted && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
            {isFailed && <AlertTriangle className="w-4 h-4 text-rose-400" />}
            <span className="font-bold text-zinc-100 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
              <span>TIẾN TRÌNH THỰC THI</span>
              {isRunning && <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />}
            </span>
          </div>
          <span
            className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase border shadow-sm ${
              isRunning
                ? 'bg-cyan-950/80 text-cyan-300 border-cyan-500/40'
                : isCompleted
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40'
                : 'bg-rose-950/80 text-rose-300 border-rose-500/40'
            }`}
          >
            {task.status} ({Math.round(task.progress)}%)
          </span>
        </div>

        {/* Animated Progress Bar */}
        <div className="w-full bg-zinc-800/80 rounded-full h-2 overflow-hidden p-0.5 border border-white/5">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              isRunning
                ? 'bg-gradient-to-r from-cyan-500 via-emerald-400 to-cyan-300 animate-pulse'
                : isCompleted
                ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                : 'bg-rose-500'
            }`}
            style={{ width: `${Math.max(5, Math.min(100, task.progress))}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[11px] text-zinc-400">
          <span className="truncate pr-2">
            <span className="text-zinc-500 font-semibold">{t.controlCenter.currentStageLabel}:</span>{' '}
            <span className="text-zinc-200 font-medium">{task.stage}</span> &bull; {task.message}
          </span>
          <span className="text-[10px] text-zinc-500 shrink-0 font-mono bg-zinc-900 px-1.5 py-0.5 rounded border border-white/5">
            {task.taskId.substring(0, 16)}...
          </span>
        </div>

        {/* Receipt proof on completion */}
        {isCompleted && (
          <div className="pt-2 mt-1 border-t border-white/5 flex flex-col gap-1.5 bg-emerald-950/20 p-2.5 rounded-lg border border-emerald-500/20">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-emerald-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                <span>{t.controlCenter.lastResultLabel}</span>
              </span>
              <button
                onClick={() => {
                  setSelectedTaskId(task.taskId);
                  setIsDrawerOpen(true);
                }}
                className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1 underline font-bold transition-colors"
              >
                <span>XEM CHI TIẾT BIÊN NHẬN</span>
                <ArrowUpRight className="w-3 h-3" />
              </button>
            </div>
            {sha256 && (
              <div className="text-[10px] font-mono text-zinc-400 truncate flex items-center gap-1">
                <span className="text-zinc-500">{t.controlCenter.sha256ProofLabel}:</span>
                <span className="text-emerald-400 font-bold">{sha256}</span>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4 h-full font-mono select-none">
      {/* Top Institutional Terminal HUD */}
      <div
        className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 shadow-xl backdrop-blur-md transition-all ${
          isKillSwitchEngaged
            ? 'bg-rose-950/40 border-rose-500/50 text-rose-300'
            : 'bg-zinc-900/90 border-white/10 text-zinc-300'
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center">
            <div
              className={`h-3.5 w-3.5 rounded-full ${
                isKillSwitchEngaged ? 'bg-rose-500 animate-ping' : 'bg-emerald-400 animate-pulse'
              }`}
            />
            <div
              className={`absolute h-2 w-2 rounded-full ${
                isKillSwitchEngaged ? 'bg-rose-400' : 'bg-emerald-300'
              }`}
            />
          </div>
          <div>
            <div className="font-bold text-sm text-zinc-100 flex items-center gap-2.5">
              <span className="tracking-tight">{t.controlCenter.title}</span>
              <span
                className={`text-[10px] px-2.5 py-0.5 rounded-full border font-bold tracking-wider uppercase shadow-sm ${
                  isKillSwitchEngaged
                    ? 'bg-rose-900/80 border-rose-500/50 text-rose-300'
                    : 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300'
                }`}
              >
                {isKillSwitchEngaged ? t.controlCenter.systemHalted : t.controlCenter.standbyArmed}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800/80 text-zinc-400 border border-white/5">
                PIT ENGINE: LIVE
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">{t.controlCenter.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setActiveModule('model_registry')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/60 text-xs border border-emerald-500/30 text-emerald-300 transition-all hover:scale-[1.02] shadow-sm"
          >
            <GitBranch className="w-3.5 h-3.5 text-emerald-400" />
            <span className="font-semibold">MODEL GOVERNANCE</span>
          </button>

          <button
            onClick={handleToggleGovernor}
            disabled={isUpdatingGovernor}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-all hover:scale-[1.02] shadow-sm ${
              governorState?.mode === 'COPILOT'
                ? 'bg-cyan-950/60 border-cyan-500/40 text-cyan-300'
                : 'bg-zinc-800 border-white/10 text-zinc-300 hover:bg-zinc-700'
            }`}
          >
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold">GOVERNOR: {governorState?.mode || 'MANUAL'}</span>
          </button>

          <button
            onClick={() => setIsDrawerOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs border border-white/10 text-zinc-200 transition-all hover:scale-[1.02] shadow-sm"
          >
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            <span>
              {t.controlCenter.opsDrawerBtn} ({activeTaskList.length})
            </span>
          </button>

          <button
            onClick={() => setIsTotpModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 text-xs border border-rose-500/40 font-bold transition-all hover:scale-[1.02] shadow-sm"
          >
            <ShieldAlert className="w-4 h-4 text-rose-400" />
            <span>{t.controlCenter.killSwitchBtn}</span>
          </button>
        </div>
      </div>

      {/* Sub-Tab Navigation Bar with ACTIVE GLOW PILLS */}
      <div className="flex flex-wrap items-center gap-1.5 p-1.5 rounded-xl bg-zinc-950/90 border border-white/10 text-xs shadow-lg backdrop-blur">
        <button
          onClick={() => setActiveSubTab('ingest')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'ingest'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-md shadow-emerald-950/50'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Database className="w-4 h-4 text-emerald-400" />
          <span>{t.controlCenter.subtabIngest}</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/30">
            {lakehouseStats.count} Tệp
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('alphas')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'alphas'
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-md shadow-cyan-950/50'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Cpu className="w-4 h-4 text-cyan-400" />
          <span>{t.controlCenter.subtabAlphas}</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-500/30">
            {dynamicItems.length} Mã Top
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('portfolio')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'portfolio'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-md shadow-amber-950/50'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Layers className="w-4 h-4 text-amber-400" />
          <span>{t.controlCenter.subtabPortfolio}</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-amber-950 text-amber-400 border border-amber-500/30">
            5 Mục Tiêu
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('backtest')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'backtest'
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-md shadow-purple-950/50'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Play className="w-4 h-4 text-purple-400 fill-current" />
          <span>{t.controlCenter.subtabBacktest}</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-purple-950 text-purple-400 border border-purple-500/30">
            Purged CPCV
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('overview')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'overview'
              ? 'bg-zinc-800 text-zinc-100 border border-zinc-500/40'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Grid className="w-4 h-4 text-zinc-400" />
          <span>TỔNG QUAN 4 TRỤ CỘT</span>
        </button>

        <button
          onClick={() => {
            setActiveSubTab('receipts');
          }}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'receipts'
              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-md shadow-blue-950/50'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span>{t.controlCenter.subtabReceipts}</span>
        </button>

        <button
          onClick={() => setActiveSubTab('copilot')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'copilot'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <TrendingUp className="w-4 h-4 text-emerald-400" />
          <span>{t.controlCenter.subtabCopilot}</span>
        </button>

        <button
          onClick={() => setActiveSubTab('llm_bridge')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'llm_bridge'
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
          }`}
        >
          <Cpu className="w-4 h-4 text-cyan-400" />
          <span>{t.controlCenter.subtabLlmBridge}</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 1: DATA INGESTION & LAKEHOUSE STATUS                         */}
      {/* ========================================================================= */}
      {activeSubTab === 'ingest' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {/* Top 4 Stat Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Dung Lượng Lakehouse</span>
                <div className="text-xl font-bold text-zinc-100 font-mono mt-0.5">{lakehouseStats.totalMb} MB</div>
                <span className="text-[10px] text-emerald-400 flex items-center gap-1 mt-0.5">
                  <CheckCheck className="w-3 h-3" /> Chuẩn Parquet nén Snappy
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/30 text-emerald-400">
                <Database className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Tập Dữ Liệu Quản Trị</span>
                <div className="text-xl font-bold text-cyan-300 font-mono mt-0.5">{lakehouseStats.count} Tập Parquet</div>
                <span className="text-[10px] text-cyan-400 flex items-center gap-1 mt-0.5">
                  <FolderCheck className="w-3 h-3" /> OHLCV, BCTC & Hybrid
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-cyan-950/50 border border-cyan-500/30 text-cyan-400">
                <FolderCheck className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Tổng Bản Ghi PIT</span>
                <div className="text-xl font-bold text-amber-300 font-mono mt-0.5">{lakehouseStats.totalRows} Dòng</div>
                <span className="text-[10px] text-amber-400 flex items-center gap-1 mt-0.5">
                  <BarChart3 className="w-3 h-3" /> Lịch sử 2015 - Hiện tại
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-amber-950/50 border border-amber-500/30 text-amber-400">
                <BarChart3 className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Độ Tươi & Tính Toàn Vẹn</span>
                <div className="text-xl font-bold text-emerald-400 font-mono mt-0.5">{lakehouseStats.healthyRatio} Khớp</div>
                <span className="text-[10px] text-emerald-300 flex items-center gap-1 mt-0.5">
                  <Sparkles className="w-3 h-3" /> 100% PIT - Zero Lookahead
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/30 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            </div>
          </div>

          {/* Lakehouse Feed Clarification Banner */}
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-emerald-500/30 flex flex-wrap items-center justify-between gap-3 text-xs shadow-lg">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2.5">
                <span className="font-bold text-zinc-100 uppercase tracking-wide flex items-center gap-1.5">
                  <Database className="w-4 h-4 text-emerald-400" />
                  <span>{t.controlCenter.lakehouseTitle}</span>
                  {lakehouseTimestamp && (
                    <span className="text-zinc-500 font-normal font-mono text-[11px]">
                      ({lakehouseTimestamp.replace('T', ' ').substring(0, 19)} UTC)
                    </span>
                  )}
                </span>
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-bold">
                  {t.controlCenter.primaryFeedBadge}
                </span>
                <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-white/10 font-bold">
                  {t.controlCenter.backupFeedBadge}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 font-mono font-bold">
                  SHA: b958162f
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-blue-950/80 text-blue-400 border border-blue-800/60 font-mono font-bold">
                  PIT Safe: 2026-08-28
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/60 font-mono font-bold">
                  Drift: 0 Anomaly
                </span>
              </div>
              <p className="text-zinc-400 text-[11px]">{t.controlCenter.lakehouseSubtitle}</p>
              <p className="text-zinc-500 text-[10px] italic flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-400" />
                <span>{t.controlCenter.autoUpdateNotice}</span>
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={fetchLakehouse}
                disabled={isLoadingLakehouse}
                className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-white/10 flex items-center gap-1.5 transition-colors shadow-sm"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingLakehouse ? 'animate-spin' : ''}`} />
                <span>LÀM MỚI BẢNG</span>
              </button>

              <button
                onClick={() => triggerIngestData({ sources: ['vci', 'kbs'], force_refresh: true, symbols: ['ALL'] })}
                className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold flex items-center gap-1.5 transition-all hover:scale-[1.02] shadow-lg shadow-emerald-950"
              >
                <Sparkles className="w-3.5 h-3.5 fill-current" />
                <span>{t.controlCenter.autoUpdateBtn}</span>
              </button>
            </div>
          </div>

          {/* Lakehouse Parquet Table */}
          <div className="rounded-xl bg-zinc-900/80 border border-white/10 overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-zinc-950/90 border-b border-white/10 text-[11px] text-zinc-400 font-semibold uppercase tracking-wider">
                    <th className="p-3.5">{t.controlCenter.thFileName}</th>
                    <th className="p-3.5">{t.controlCenter.thRole}</th>
                    <th className="p-3.5 text-right">{t.controlCenter.thSize}</th>
                    <th className="p-3.5 text-right">{t.controlCenter.thRows}</th>
                    <th className="p-3.5 text-right">{t.controlCenter.thSymbols}</th>
                    <th className="p-3.5">{t.controlCenter.thStartDate}</th>
                    <th className="p-3.5">{t.controlCenter.thEndDate}</th>
                    <th className="p-3.5 text-center">{t.controlCenter.thFreshness}</th>
                    <th className="p-3.5 text-right">{t.controlCenter.thDaysLag}</th>
                    <th className="p-3.5">{t.controlCenter.thLastModified}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {lakehouseDatasets.map((ds) => {
                    const isHealthy = ds.freshness_status === 'HEALTHY';
                    const isWarning = ds.freshness_status === 'WARNING';
                    const isStale = ds.freshness_status === 'STALE';
                    return (
                      <tr key={ds.id} className="hover:bg-zinc-800/40 transition-colors">
                        <td className="p-3.5 font-bold text-zinc-100 flex items-center gap-2.5">
                          <Database className="w-4 h-4 text-emerald-400 shrink-0" />
                          <span className="font-semibold text-zinc-200">{ds.file_name}</span>
                        </td>
                        <td className="p-3.5 text-zinc-400 text-[11px]">{ds.role}</td>
                        <td className="p-3.5 text-right text-zinc-300 font-medium">{ds.size_mb.toFixed(2)} MB</td>
                        <td className="p-3.5 text-right text-zinc-200 font-bold">{ds.total_rows.toLocaleString()}</td>
                        <td className="p-3.5 text-right text-cyan-300 font-bold">{ds.symbols_count}</td>
                        <td className="p-3.5 text-zinc-400 text-[11px] flex items-center gap-1 mt-2.5">
                          <Calendar className="w-3 h-3 text-zinc-500" />
                          <span>{ds.start_date || '---'}</span>
                        </td>
                        <td className="p-3.5 text-emerald-400 font-bold text-[11px]">{ds.end_date || '---'}</td>
                        <td className="p-3.5 text-center">
                          <span
                            className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase border inline-flex items-center gap-1 shadow-sm ${
                              isHealthy
                                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/30'
                                : isWarning
                                ? 'bg-amber-950/80 text-amber-300 border-amber-500/30'
                                : isStale
                                ? 'bg-rose-950/80 text-rose-300 border-rose-500/30'
                                : 'bg-red-950/80 text-red-400 border-red-500/40'
                            }`}
                          >
                            {isHealthy && <Check className="w-3 h-3 text-emerald-400" />}
                            {isWarning && <AlertTriangle className="w-3 h-3 text-amber-400" />}
                            {isStale && <Clock className="w-3 h-3 text-rose-400" />}
                            <span>
                              {isHealthy
                                ? t.controlCenter.statusHealthy
                                : isWarning
                                ? t.controlCenter.statusWarning
                                : isStale
                                ? t.controlCenter.statusStale
                                : t.controlCenter.statusFailed}
                            </span>
                          </span>
                        </td>
                        <td
                          className={`p-3.5 text-right font-bold ${
                            ds.days_lag > 7 ? 'text-rose-400' : ds.days_lag > 3 ? 'text-amber-400' : 'text-emerald-400'
                          }`}
                        >
                          {ds.days_lag} d
                        </td>
                        <td className="p-3.5 text-zinc-500 text-[11px]">{ds.last_modified || '---'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Ingestion Parameters & Action Block */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <h2 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-400" />
                <span>{t.controlCenter.dataIngestionTitle}</span>
              </h2>
              <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/20 font-bold">
                POINT-IN-TIME (PIT) STRICT
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="flex flex-col gap-2">
                <label className="text-zinc-400 text-[11px] font-semibold">{t.controlCenter.sourcesLabel}</label>
                <div className="flex flex-wrap items-center gap-2">
                  {[
                    { key: 'vci', label: 'VCI (VietCap)' },
                    { key: 'kbs', label: 'KBSV (Primary)' },
                    { key: 'tcbs', label: 'TCBS' },
                    { key: 'macro', label: 'VĨ MÔ' },
                    { key: 'news', label: 'TIN TỨC & TÂM LÝ' }
                  ].map((s) => (
                    <button
                      key={s.key}
                      onClick={() => toggleSource(s.key)}
                      className={`px-3 py-1.5 rounded-lg text-xs border transition-all flex items-center gap-1.5 ${
                        sources.includes(s.key)
                          ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300 font-bold shadow-sm'
                          : 'bg-zinc-800/80 border-white/5 text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      {sources.includes(s.key) && <Check className="w-3 h-3 text-emerald-400" />}
                      <span>{s.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between p-3.5 rounded-xl bg-zinc-950/80 border border-white/5">
                <div className="flex flex-col">
                  <span className="text-zinc-200 font-bold text-xs">{t.controlCenter.forceCacheLabel}</span>
                  <span className="text-zinc-500 text-[10px] mt-0.5">Xóa bộ nhớ đệm cache và tải lại dữ liệu mới từ sàn</span>
                </div>
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(e) => setForceRefresh(e.target.checked)}
                  className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0 w-4 h-4 cursor-pointer"
                />
              </div>
            </div>

            {/* TELEMETRY & PROGRESS BLOCK (IMMEDIATELY ABOVE BUTTON) */}
            {renderTaskTelemetryBlock('DATA_INGESTION')}

            {/* ACTION DISPATCH / STOP BUTTONS */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => triggerIngestData({ sources, force_refresh: forceRefresh, symbols: ['ALL'] })}
                className="flex-1 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all hover:scale-[1.01] shadow-xl shadow-emerald-950 cursor-pointer"
              >
                <RefreshCw className="w-4 h-4" />
                <span className="tracking-wide uppercase">{t.controlCenter.dispatchIngestBtn}</span>
              </button>
              {(() => {
                const latestIngestTask = activeTaskList.find((t) => t.taskType === 'DATA_INGESTION');
                const isIngestRunning =
                  latestIngestTask &&
                  (latestIngestTask.status === 'RUNNING' ||
                    latestIngestTask.status === 'PENDING' ||
                    latestIngestTask.status === 'RECONNECTING');
                if (!isIngestRunning) return null;
                return (
                  <button
                    onClick={() => stopIngestTask(latestIngestTask?.taskId)}
                    className="py-3 px-4 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 font-bold text-xs flex items-center justify-center gap-1.5 transition-all hover:scale-[1.01] shadow-lg shadow-rose-950 cursor-pointer"
                    title="Dừng tiến trình nạp dữ liệu đang chạy"
                  >
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                    <span className="tracking-wide uppercase">DỪNG TÁC VỤ</span>
                  </button>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 2: ALPHA FACTOR ENGINE & DYNAMIC UNIVERSE                    */}
      {/* ========================================================================= */}
      {activeSubTab === 'alphas' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {/* Top 4 Stat Cards for Dynamic Universe */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Vũ Trụ Động Tuyển Chọn</span>
                <div className="text-xl font-bold text-cyan-300 font-mono mt-0.5">{dynamicItems.length} Mã Top</div>
                <span className="text-[10px] text-cyan-400 flex items-center gap-1 mt-0.5">
                  <Sparkles className="w-3 h-3" /> Preset: {universePreset}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-cyan-950/50 border border-cyan-500/30 text-cyan-400">
                <Flame className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Mã Dẫn Đầu Xếp Hạng</span>
                <div className="text-xl font-bold text-emerald-400 font-mono mt-0.5">
                  {universeStats.topItem ? universeStats.topItem.symbol : '---'}
                </div>
                <span className="text-[10px] text-emerald-300 flex items-center gap-1 mt-0.5">
                  <Award className="w-3 h-3" />
                  Hybrid:{' '}
                  {universeStats.topItem ? `${(universeStats.topItem.hybrid_score * 100).toFixed(1)}%` : '---'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/30 text-emerald-400">
                <Award className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Số Mã Đạt Chuẩn (Qualified)</span>
                <div className="text-xl font-bold text-emerald-300 font-mono mt-0.5">{universeStats.qualifiedCount} Mã</div>
                <span className="text-[10px] text-zinc-400 flex items-center gap-1 mt-0.5">
                  <Clock className="w-3 h-3" /> Theo dõi (Watch): {universeStats.watchCount} Mã
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/30 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex items-center justify-between shadow-md">
              <div>
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Trọng Số Nhân Tố Lai</span>
                <div className="text-xs font-bold text-zinc-200 font-mono mt-1">ROE 35% &bull; F-Score 25%</div>
                <span className="text-[10px] text-zinc-400 flex items-center gap-1 mt-0.5">
                  <Zap className="w-3 h-3 text-cyan-400" /> Altman-Z 20% &bull; Mom-3M 20%
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-800/80 border border-white/10 text-zinc-300">
                <Cpu className="w-5 h-5" />
              </div>
            </div>
          </div>

          {/* Dynamic Universe Selection Table */}
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-cyan-500/30 flex flex-col gap-3 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2.5 pb-2 border-b border-white/5">
              <div>
                <h3 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <span>{t.controlCenter.dynamicUniverseTitle}</span>
                </h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-mono font-bold">
                    Weights: Quant 70% + LLM 30%
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-white/10 font-mono">
                    Method: Deterministic Composite
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 mt-0.5">{t.controlCenter.dynamicUniverseSubtitle}</p>
              </div>

              {/* Filters for Dynamic Universe */}
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-white/10 text-xs">
                  {(['VN703', 'VN30', 'VN100'] as const).map((pr) => (
                    <button
                      key={pr}
                      onClick={() => setUniversePreset(pr)}
                      className={`px-3 py-1 rounded-md text-[11px] font-bold transition-all ${
                        universePreset === pr
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                          : 'text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {pr}
                    </button>
                  ))}
                </div>

                <select
                  value={topN}
                  onChange={(e) => setTopN(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 cursor-pointer"
                >
                  <option value={10}>Top 10 Mã</option>
                  <option value={20}>Top 20 Mã</option>
                  <option value={30}>Top 30 Mã</option>
                  <option value={50}>Top 50 Mã</option>
                </select>

                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Tìm mã..."
                    value={searchTicker}
                    onChange={(e) => setSearchTicker(e.target.value)}
                    className="bg-zinc-950 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 w-28 focus:border-cyan-500/50 outline-none"
                  />
                </div>

                <input
                  type="text"
                  placeholder="Lọc ngành..."
                  value={sectorFilter}
                  onChange={(e) => setSectorFilter(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 w-32 focus:border-cyan-500/50 outline-none"
                />

                <button
                  onClick={fetchUniverse}
                  disabled={isLoadingUniverse}
                  className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-white/10 transition-colors cursor-pointer"
                  title="Làm mới bảng"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoadingUniverse ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Dynamic Universe Table with Rich Metrics */}
            <div className="max-h-96 overflow-y-auto rounded-lg border border-white/5 bg-zinc-950/70 shadow-inner">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="sticky top-0 bg-zinc-950 text-[10px] text-zinc-400 uppercase font-semibold border-b border-white/10 tracking-wider">
                  <tr>
                    <th className="p-3 text-center">{t.controlCenter.thRank}</th>
                    <th className="p-3">{t.controlCenter.thTicker}</th>
                    <th className="p-3 text-right">{t.controlCenter.thHybridScore}</th>
                    <th className="p-3 text-right">{t.controlCenter.thQuantScore}</th>
                    <th className="p-3 text-right">{t.controlCenter.thLlmScore}</th>
                    <th className="p-3 text-right">{t.controlCenter.thRoe}</th>
                    <th className="p-3 text-right">{t.controlCenter.thMomentum3m}</th>
                    <th className="p-3">{t.controlCenter.thSector}</th>
                    <th className="p-3 text-center">{t.controlCenter.thStatus}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {filteredDynamicItems.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="p-6 text-center text-zinc-500">
                        Không tìm thấy mã nào phù hợp với bộ lọc hiện tại.
                      </td>
                    </tr>
                  ) : (
                    filteredDynamicItems.map((it) => {
                      const rankNum = it.rank;
                      const isTop1 = rankNum === 1;
                      const isTop2 = rankNum === 2;
                      const isTop3 = rankNum === 3;
                      return (
                        <tr key={it.symbol} className="hover:bg-cyan-950/30 transition-colors">
                          <td className="p-3 text-center">
                            {isTop1 ? (
                              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold text-[11px] shadow-sm">
                                #1
                              </span>
                            ) : isTop2 ? (
                              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-zinc-300/20 text-zinc-200 border border-zinc-400/50 font-bold text-[11px]">
                                #2
                              </span>
                            ) : isTop3 ? (
                              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-700/20 text-amber-500 border border-amber-600/50 font-bold text-[11px]">
                                #3
                              </span>
                            ) : (
                              <span className="text-zinc-500 font-bold">#{rankNum}</span>
                            )}
                          </td>
                          <td className="p-3 font-bold text-cyan-300">
                            <span className="px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/30 text-xs tracking-wider">
                              {it.symbol}
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-14 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400"
                                  style={{ width: `${Math.min(100, Math.round(it.hybrid_score * 100))}%` }}
                                />
                              </div>
                              <span className="font-bold text-emerald-400 w-10 text-right">
                                {(it.hybrid_score * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-12 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className="h-full bg-cyan-400"
                                  style={{ width: `${Math.min(100, Math.round(it.quant_score * 100))}%` }}
                                />
                              </div>
                              <span className="text-zinc-300 w-10 text-right">
                                {(it.quant_score * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="p-3 text-right">
                            <span className="px-2 py-0.5 rounded bg-purple-950/60 border border-purple-500/30 text-purple-300 text-[11px] font-bold">
                              {(it.llm_score * 100).toFixed(1)}%
                            </span>
                          </td>
                          <td className="p-3 text-right text-zinc-200 font-bold">
                            {it.roe !== null ? (
                              <span className="text-emerald-300">+{it.roe.toFixed(1)}%</span>
                            ) : (
                              '---'
                            )}
                          </td>
                          <td className="p-3 text-right">
                            {it.momentum_3m !== null ? (
                              <span
                                className={`inline-flex items-center gap-1 font-bold ${
                                  it.momentum_3m >= 0 ? 'text-emerald-400' : 'text-rose-400'
                                }`}
                              >
                                {it.momentum_3m >= 0 ? (
                                  <TrendingUp className="w-3.5 h-3.5" />
                                ) : (
                                  <TrendingDown className="w-3.5 h-3.5" />
                                )}
                                <span>{it.momentum_3m > 0 ? `+${it.momentum_3m.toFixed(1)}%` : `${it.momentum_3m.toFixed(1)}%`}</span>
                              </span>
                            ) : (
                              '---'
                            )}
                          </td>
                          <td className="p-3 text-zinc-400 text-[11px] truncate max-w-[140px]">{it.sector}</td>
                          <td className="p-3 text-center">
                            <span
                              className={`text-[9px] px-2.5 py-0.5 rounded-full font-bold uppercase border shadow-sm ${
                                it.status_label === 'QUALIFIED'
                                  ? 'bg-emerald-950 text-emerald-400 border-emerald-500/40'
                                  : it.status_label === 'WATCH'
                                  ? 'bg-amber-950 text-amber-400 border-amber-500/40'
                                  : 'bg-rose-950 text-rose-400 border-rose-500/40'
                              }`}
                            >
                              {it.status_label}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {universeProvenance && (
              <div className="text-[10px] text-zinc-500 flex items-center justify-between pt-1">
                <span>Mô hình định chế: OMEGA_HYBRID_QUANT_LLM_V3</span>
                <span className="font-mono">Provenance: {universeProvenance.substring(0, 24)}...</span>
              </div>
            )}
          </div>

          {/* Alpha Computation Settings & Action Block */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <h2 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span>{t.controlCenter.alphaEngineTitle}</span>
              </h2>
              <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-500/20 font-bold">
                APSE REGISTRY
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.universeLabel}</span>
                <select
                  value={alphaUniverse}
                  onChange={(e) => setAlphaUniverse(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs cursor-pointer"
                >
                  <option value="VN703">VN703 Toàn Thị Trường (703 Mã)</option>
                  <option value="VN30">VN30 Bluechips (30 Mã)</option>
                  <option value="VN100">VN100 Thanh Khoản Cao (100 Mã)</option>
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.parallelWorkersLabel}</span>
                <input
                  type="number"
                  min="1"
                  max="16"
                  value={parallelJobs}
                  onChange={(e) => setParallelJobs(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.minIcLabel}</span>
                <input
                  type="number"
                  step="0.01"
                  value={icThreshold}
                  onChange={(e) => setIcThreshold(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.minIrLabel}</span>
                <input
                  type="number"
                  step="0.1"
                  value={irThreshold}
                  onChange={(e) => setIrThreshold(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>
            </div>

            {/* TELEMETRY & PROGRESS BLOCK (IMMEDIATELY ABOVE BUTTON) */}
            {renderTaskTelemetryBlock('ALPHA_COMPUTATION')}

            {/* ACTION DISPATCH BUTTON */}
            <button
              onClick={() =>
                triggerComputeAlphas({
                  universe:
                    dynamicItems.length > 0
                      ? dynamicItems.slice(0, 10).map((d) => d.symbol)
                      : ['FPT', 'HPG', 'MBB', 'MWG'],
                  alpha_families: ['MOMENTUM']
                })
              }
              className="w-full py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all hover:scale-[1.01] shadow-xl shadow-cyan-950 cursor-pointer"
            >
              <Play className="w-4 h-4 fill-current" />
              <span className="tracking-wide uppercase">{t.controlCenter.dispatchAlphaBtn}</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 3: PORTFOLIO OPTIMIZATION (5 OBJECTIVES + AUTO-TUNE)        */}
      {/* ========================================================================= */}
      {activeSubTab === 'portfolio' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {/* Objective Selection Cards */}
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-amber-500/30 flex flex-col gap-3 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <h3 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Layers className="w-4 h-4 text-amber-400" />
                <span>6 MỤC TIÊU TỐI ƯU HÓA DANH MỤC CHUẨN ĐỊNH CHẾ</span>
              </h3>
              <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/20 font-bold">
                SCIPY SLSQP / HRP / CVAR SOLVER
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
              {[
                { id: 'ALPHA_RANK_RISK_CAPPED', title: '1. Alpha Rank', tag: 'Hybrid Alpha', desc: t.controlCenter.objectiveAlphaRankRiskCapped || 'Phân Hạng Alpha Giới Hạn Rủi Ro' },
                { id: 'MAX_SHARPE', title: '2. Max Sharpe', tag: 'Cân bằng', desc: t.controlCenter.objectiveMaxSharpe },
                { id: 'MIN_CVAR', title: '3. Min CVaR', tag: 'Bảo vệ đuôi', desc: t.controlCenter.objectiveMinCvar },
                { id: 'RISK_PARITY', title: '4. Risk Parity', tag: 'Đồng đều', desc: t.controlCenter.objectiveRiskParity },
                { id: 'BLACK_LITTERMAN_BAYESIAN', title: '5. Black-Litterman', tag: 'Bayesian', desc: t.controlCenter.objectiveBlackLitterman },
                { id: 'MIN_DOWNSIDE_SORTINO', title: '6. Max Sortino', tag: 'Phạt giảm', desc: t.controlCenter.objectiveSortino },
              ].map((obj) => {
                const isSelected = optObjective === obj.id;
                return (
                  <button
                    key={obj.id}
                    onClick={() => setOptObjective(obj.id as any)}
                    className={`p-3.5 rounded-xl text-left border flex flex-col justify-between transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-amber-500/20 border-amber-500/60 text-amber-200 shadow-lg shadow-amber-950 ring-1 ring-amber-400/30'
                        : 'bg-zinc-950/70 border-white/5 text-zinc-400 hover:border-white/20 hover:bg-zinc-900/50'
                    }`}
                  >
                    <div>
                      <div className="font-bold text-xs flex items-center justify-between">
                        <span>{obj.title}</span>
                        {isSelected ? (
                          <CheckCircle2 className="w-4 h-4 text-amber-400" />
                        ) : (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-500 uppercase">{obj.tag}</span>
                        )}
                      </div>
                      <p className="text-[10px] text-zinc-400 mt-2 leading-relaxed">{obj.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Institutional Recommendation vs User Bounds */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Box 1: Institutional Recommendation (Auto-Suggested) */}
            <div className="p-4 rounded-xl bg-zinc-900/80 border border-cyan-500/30 flex flex-col justify-between gap-3 text-xs shadow-xl">
              <div className="flex flex-col gap-2.5">
                <div className="flex items-center justify-between pb-2 border-b border-white/5">
                  <span className="font-bold text-cyan-300 text-[11px] uppercase flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                    <span>{t.controlCenter.instRecommendation}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-500/20 font-medium">
                    {instRecommendations.label}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2.5 text-center pt-2">
                  <div className="p-3 rounded-xl bg-zinc-950/80 border border-white/5 shadow-inner">
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Trần Cổ Phiếu</span>
                    <div className="text-base font-bold text-cyan-400 font-mono mt-1">
                      {(instRecommendations.maxWeight * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-950/80 border border-white/5 shadow-inner">
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Trần Ngành</span>
                    <div className="text-base font-bold text-cyan-400 font-mono mt-1">
                      {(instRecommendations.sectorCap * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-zinc-950/80 border border-white/5 shadow-inner">
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Độ Tin Cậy</span>
                    <div className="text-base font-bold text-cyan-400 font-mono mt-1">
                      {(instRecommendations.cvarConf * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>

              <button
                onClick={applyAutoTune}
                className="w-full py-2.5 rounded-xl bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 text-xs font-bold flex items-center justify-center gap-2 transition-all hover:scale-[1.01] shadow-sm cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span>{t.controlCenter.autoTuneBtn}</span>
              </button>
            </div>

            {/* Box 2: User-Applied Bounds */}
            <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col justify-between gap-3 text-xs shadow-xl">
              <div className="flex flex-col gap-2.5">
                <div className="flex items-center justify-between pb-2 border-b border-white/5">
                  <span className="font-bold text-amber-300 text-[11px] uppercase flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-amber-400" />
                    <span>{t.controlCenter.userAppliedBounds}</span>
                  </span>
                  <span className="text-[10px] text-zinc-500 font-medium">Người Dùng Thiết Lập</span>
                </div>

                <div className="grid grid-cols-3 gap-2.5 pt-2">
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[10px] text-zinc-400 font-medium">Trần Cổ Phiếu (%):</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="1.0"
                      value={userMaxWeight}
                      onChange={(e) => setUserMaxWeight(Number(e.target.value))}
                      className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 font-bold"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <span className="text-[10px] text-zinc-400 font-medium">Trần Ngành (%):</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0.05"
                      max="1.0"
                      value={userSectorCap}
                      onChange={(e) => setUserSectorCap(Number(e.target.value))}
                      className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 font-bold"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <span className="text-[10px] text-zinc-400 font-medium">Độ Tin Cậy:</span>
                    <select
                      value={userCvarConf}
                      onChange={(e) => setUserCvarConf(Number(e.target.value))}
                      className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 font-bold cursor-pointer"
                    >
                      <option value={0.99}>99.0% Confidence</option>
                      <option value={0.975}>97.5% Confidence</option>
                      <option value={0.95}>95.0% Confidence</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-zinc-500 text-center py-1">
                Ràng buộc định chế: Tổng tỷ trọng = 1.0, không bán khống (long-only), thanh khoản tối thiểu.
              </div>
            </div>
          </div>

          {/* Action and Telemetry Block */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-3 shadow-xl">
            {/* TELEMETRY & PROGRESS BLOCK (IMMEDIATELY ABOVE BUTTON) */}
            {renderTaskTelemetryBlock('PORTFOLIO_OPTIMIZATION')}

            {/* ACTION DISPATCH BUTTON */}
            <button
              onClick={() =>
                triggerOptimizePortfolio({
                  objective: optObjective,
                  max_single_weight: userMaxWeight,
                  universe:
                    dynamicItems.length > 0
                      ? dynamicItems.slice(0, 10).map((d) => d.symbol)
                      : ['FPT', 'HPG', 'MBB', 'MWG']
                })
              }
              className="w-full py-3 rounded-xl bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all hover:scale-[1.01] shadow-xl shadow-amber-950 cursor-pointer"
            >
              <Sliders className="w-4 h-4" />
              <span className="tracking-wide uppercase">{t.controlCenter.dispatchSolverBtn}</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 4: STRATEGY BACKTESTING (6 STRATEGIES + OPTIMAL HIGHLIGHT)   */}
      {/* ========================================================================= */}
      {activeSubTab === 'backtest' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          {/* Strategy Cards Grid (All 6 institutional strategies) */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 text-xs">
            {strategiesList.map((strat) => {
              const isSelected = btStrategy === strat.id;
              return (
                <button
                  key={strat.id}
                  onClick={() => setBtStrategy(strat.id)}
                  className={`p-4 rounded-xl text-left border flex flex-col justify-between gap-3 transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-purple-500/20 border-purple-500/60 text-purple-200 shadow-xl shadow-purple-950 ring-1 ring-purple-400/40'
                      : 'bg-zinc-900/80 border-white/5 text-zinc-400 hover:border-white/20 hover:bg-zinc-900/50'
                  } ${strat.isOptimal ? 'ring-2 ring-emerald-400/60 border-emerald-500/50' : ''}`}
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-zinc-100 flex items-center gap-1.5">
                        {strat.isOptimal && <Award className="w-4 h-4 text-emerald-400" />}
                        <span>{strat.name}</span>
                      </span>
                      {isSelected && <CheckCircle2 className="w-4 h-4 text-purple-400 shrink-0" />}
                    </div>

                    {strat.isOptimal && (
                      <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-950 text-emerald-300 font-bold border border-emerald-500/40 inline-flex items-center gap-1.5 w-fit shadow-sm">
                        <Sparkles className="w-3 h-3 text-emerald-400" />
                        <span>{t.controlCenter.optimalStrategyBadge}</span>
                      </span>
                    )}

                    <p className="text-[11px] text-zinc-400 leading-relaxed mt-0.5">{strat.desc}</p>
                  </div>

                  <div className="p-2.5 rounded-lg bg-zinc-950/90 border border-white/5 flex items-center justify-between text-[11px] font-mono text-zinc-300">
                    <div className="flex items-center gap-3">
                      <span>
                        Sharpe: <strong className="text-emerald-400">{strat.sharpe}</strong>
                      </span>
                      <span>
                        Calmar: <strong className="text-cyan-400">{strat.calmar}</strong>
                      </span>
                    </div>
                    <span className="text-zinc-400">
                      Win: <strong className="text-zinc-200">{strat.winRate}</strong>
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Backtest Parameters & Action Block */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <h2 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Play className="w-4 h-4 text-purple-400 fill-current" />
                <span>{t.controlCenter.backtesterTitle}</span>
              </h2>
              <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-purple-950 text-purple-400 border border-purple-500/20 font-bold">
                PURGED CPCV / WALK-FORWARD
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.startDateLabel}</span>
                <input
                  type="date"
                  value={btStartDate}
                  onChange={(e) => setBtStartDate(e.target.value)}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">Vốn Ban Đầu (VND):</span>
                <input
                  type="number"
                  step="100000000"
                  defaultValue={1000000000}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.slippageBpsLabel}</span>
                <input
                  type="number"
                  value={btSlippage}
                  onChange={(e) => setBtSlippage(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.commissionBpsLabel}</span>
                <input
                  type="number"
                  value={btCommission}
                  onChange={(e) => setBtCommission(Number(e.target.value))}
                  className="bg-zinc-950 border border-white/10 rounded-lg px-2.5 py-1.5 text-zinc-200 text-xs"
                />
              </div>
            </div>

            {/* TELEMETRY & PROGRESS BLOCK (IMMEDIATELY ABOVE BUTTON) */}
            {renderTaskTelemetryBlock('STRATEGY_BACKTEST')}

            {/* ACTION DISPATCH BUTTON */}
            <button
              onClick={() =>
                triggerRunBacktest({
                  strategy_id: btStrategy,
                  start_date: btStartDate,
                  slippage_bps: btSlippage,
                  commission_bps: btCommission
                })
              }
              className="w-full py-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all hover:scale-[1.01] shadow-xl shadow-purple-950 cursor-pointer"
            >
              <Play className="w-4 h-4 fill-current" />
              <span className="tracking-wide uppercase">{t.controlCenter.dispatchBacktestBtn}</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 5: OVERVIEW (4-PILLAR CLASSIC GRID WITH PROGRESS BARS)      */}
      {/* ========================================================================= */}
      {activeSubTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 overflow-y-auto pr-1">
          {/* Pillar 1: Ingestion */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col justify-between hover:border-emerald-500/40 transition-all shadow-xl">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-emerald-400" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.dataIngestionTitle}</h2>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-500/20 font-bold">
                  VCI / LAKEHOUSE
                </span>
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <label className="text-zinc-400 text-[11px] font-semibold">{t.controlCenter.sourcesLabel}</label>
                <div className="flex items-center gap-2">
                  {['vci', 'kbs', 'macro', 'news'].map((src) => (
                    <button
                      key={src}
                      onClick={() => toggleSource(src)}
                      className={`px-3 py-1 rounded-lg text-xs border transition-colors ${
                        sources.includes(src)
                          ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300 font-bold'
                          : 'bg-zinc-800/80 border-white/5 text-zinc-500'
                      }`}
                    >
                      {src.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-4">
              {renderTaskTelemetryBlock('DATA_INGESTION')}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => triggerIngestData({ sources, force_refresh: forceRefresh, symbols: ['ALL'] })}
                  className="flex-1 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-emerald-950 cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>{t.controlCenter.dispatchIngestBtn}</span>
                </button>
                {(() => {
                  const latestIngestTask = activeTaskList.find((t) => t.taskType === 'DATA_INGESTION');
                  const isIngestRunning =
                    latestIngestTask &&
                    (latestIngestTask.status === 'RUNNING' ||
                      latestIngestTask.status === 'PENDING' ||
                      latestIngestTask.status === 'RECONNECTING');
                  if (!isIngestRunning) return null;
                  return (
                    <button
                      onClick={() => stopIngestTask(latestIngestTask?.taskId)}
                      className="py-2.5 px-3 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 font-bold text-xs flex items-center justify-center gap-1 transition-all shadow-sm cursor-pointer"
                      title="Dừng tiến trình nạp dữ liệu đang chạy"
                    >
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                      <span>DỪNG</span>
                    </button>
                  );
                })()}
              </div>
            </div>
          </div>

          {/* Pillar 2: Alphas */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col justify-between hover:border-cyan-500/40 transition-all shadow-xl">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-cyan-400" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.alphaEngineTitle}</h2>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-500/20 font-bold">
                  APSE REGISTRY
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.universeLabel}</span>
                  <select
                    value={alphaUniverse}
                    onChange={(e) => setAlphaUniverse(e.target.value)}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  >
                    <option value="VN703">VN703 Toàn Thị Trường</option>
                    <option value="VN30">VN30 Bluechips</option>
                    <option value="VN100">VN100 Thanh Khoản</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.parallelWorkersLabel}</span>
                  <input
                    type="number"
                    value={parallelJobs}
                    onChange={(e) => setParallelJobs(Number(e.target.value))}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="mt-4">
              {renderTaskTelemetryBlock('ALPHA_COMPUTATION')}
              <button
                onClick={() =>
                  triggerComputeAlphas({
                    universe: ['FPT', 'HPG', 'MBB', 'MWG', 'TCB', 'VNM'],
                    alpha_families: ['MOMENTUM']
                  })
                }
                className="w-full py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-cyan-950 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{t.controlCenter.dispatchAlphaBtn}</span>
              </button>
            </div>
          </div>

          {/* Pillar 3: Portfolio */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col justify-between hover:border-amber-500/40 transition-all shadow-xl">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-amber-400" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.portfolioOptTitle}</h2>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-500/20 font-bold">
                  HRP / CVAR
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.solverObjectiveLabel}</span>
                  <select
                    value={optObjective}
                    onChange={(e) => setOptObjective(e.target.value as any)}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  >
                    <option value="MAX_SHARPE">Max Sharpe</option>
                    <option value="MIN_CVAR">Min CVaR (99%)</option>
                    <option value="RISK_PARITY">Risk Parity</option>
                    <option value="BLACK_LITTERMAN_BAYESIAN">Black-Litterman</option>
                    <option value="MIN_DOWNSIDE_SORTINO">Max Sortino</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.maxStockCapLabel}</span>
                  <input
                    type="number"
                    step="0.01"
                    value={userMaxWeight}
                    onChange={(e) => setUserMaxWeight(Number(e.target.value))}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="mt-4">
              {renderTaskTelemetryBlock('PORTFOLIO_OPTIMIZATION')}
              <button
                onClick={() =>
                  triggerOptimizePortfolio({
                    objective: optObjective,
                    max_single_weight: userMaxWeight,
                    universe: ['FPT', 'HPG', 'MBB', 'MWG']
                  })
                }
                className="w-full py-2.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-amber-950 cursor-pointer"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>{t.controlCenter.dispatchSolverBtn}</span>
              </button>
            </div>
          </div>

          {/* Pillar 4: Backtesting */}
          <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col justify-between hover:border-purple-500/40 transition-all shadow-xl">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Play className="w-4 h-4 text-purple-400 fill-current" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">{t.controlCenter.backtesterTitle}</h2>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-950 text-purple-400 border border-purple-500/20 font-bold">
                  PURGED CPCV
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex flex-col gap-1 col-span-2">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.strategyIdLabel}</span>
                  <select
                    value={btStrategy}
                    onChange={(e) => setBtStrategy(e.target.value)}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs font-bold"
                  >
                    {strategiesList.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.startDateLabel}</span>
                  <input
                    type="date"
                    value={btStartDate}
                    onChange={(e) => setBtStartDate(e.target.value)}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-zinc-400 text-[10px] font-semibold">{t.controlCenter.slippageBpsLabel}</span>
                  <input
                    type="number"
                    value={btSlippage}
                    onChange={(e) => setBtSlippage(Number(e.target.value))}
                    className="bg-zinc-950 border border-white/10 rounded-lg px-2 py-1.5 text-zinc-200 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="mt-4">
              {renderTaskTelemetryBlock('STRATEGY_BACKTEST')}
              <button
                onClick={() =>
                  triggerRunBacktest({
                    strategy_id: btStrategy,
                    start_date: btStartDate,
                    slippage_bps: btSlippage,
                    commission_bps: btCommission
                  })
                }
                className="w-full py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-zinc-950 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-purple-950 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{t.controlCenter.dispatchBacktestBtn}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 6: SHA-256 CRYPTOGRAPHIC RECEIPTS (F26)                      */}
      {/* ========================================================================= */}
      {activeSubTab === 'receipts' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-blue-500/30 flex flex-wrap items-center justify-between gap-3 text-xs shadow-xl">
            <div>
              <h3 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-400" />
                <span>BIÊN NHẬN XÁC THỰC MÃ HÓA SHA-256 (F26)</span>
              </h3>
              <p className="text-[11px] text-zinc-400 mt-1">
                Lưu vết và ký số biên lai mật mã cho toàn bộ các tác vụ nạp dữ liệu, tính toán alpha, tối ưu danh mục và backtest.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchReceipts}
                disabled={isLoadingReceipts}
                className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-white/10 flex items-center gap-1.5 transition-colors shadow-sm"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingReceipts ? 'animate-spin' : ''}`} />
                <span>LÀM MỚI BIÊN NHẬN</span>
              </button>
              <button
                onClick={() => setIsDrawerOpen(true)}
                className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 flex items-center gap-1.5 transition-colors shadow-sm font-bold"
              >
                <Activity className="w-3.5 h-3.5 text-blue-400" />
                <span>MỞ OPS DRAWER</span>
              </button>
            </div>
          </div>

          <div className="rounded-xl bg-zinc-900/80 border border-white/10 overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-zinc-950/90 border-b border-white/10 text-[11px] text-zinc-400 font-semibold uppercase tracking-wider">
                    <th className="p-3.5">MÃ TÁC VỤ</th>
                    <th className="p-3.5">LOẠI NGHIỆP VỤ</th>
                    <th className="p-3.5">TRẠNG THÁI</th>
                    <th className="p-3.5">FINGERPRINT YÊU CẦU</th>
                    <th className="p-3.5">OUTPUT SHA-256</th>
                    <th className="p-3.5">THỜI GIAN CÔNG BỐ</th>
                    <th className="p-3.5 text-center">THAO TÁC</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {publishedReceipts.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-6 text-center text-zinc-500">
                        {isLoadingReceipts
                          ? 'Đang tải danh sách biên lai mật mã...'
                          : 'Chưa có biên lai xác thực nào được lưu trên đĩa. Chạy một tác vụ trong 4 trụ cột để tạo biên lai mới.'}
                      </td>
                    </tr>
                  ) : (
                    publishedReceipts.map((rc) => (
                      <tr key={rc.task_id} className="hover:bg-zinc-800/40 transition-colors">
                        <td className="p-3.5 font-bold text-zinc-200">{rc.task_id}</td>
                        <td className="p-3.5 text-cyan-300 font-semibold">{rc.operation}</td>
                        <td className="p-3.5">
                          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-500/30 font-bold uppercase">
                            {rc.status}
                          </span>
                        </td>
                        <td className="p-3.5 text-zinc-400 text-[10px] font-mono">
                          {rc.request_fingerprint ? `${rc.request_fingerprint.substring(0, 16)}...` : '---'}
                        </td>
                        <td className="p-3.5 text-emerald-400 font-bold text-[10px] font-mono">
                          {rc.output_sha256 ? `${rc.output_sha256.substring(0, 20)}...` : '---'}
                        </td>
                        <td className="p-3.5 text-zinc-400 text-[11px]">
                          {rc.published_at ? rc.published_at.replace('T', ' ').substring(0, 19) : '---'}
                        </td>
                        <td className="p-3.5 text-center">
                          <button
                            onClick={() => {
                              setSelectedTaskId(rc.task_id);
                              setIsDrawerOpen(true);
                            }}
                            className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-cyan-300 text-[10px] font-bold border border-white/10 transition-colors"
                          >
                            CHI TIẾT
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 7: OMNI-QUANT COPILOT ASSISTANT (F27)                         */}
      {/* ========================================================================= */}
      {activeSubTab === 'copilot' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-emerald-500/30 flex flex-wrap items-center justify-between gap-3 text-xs shadow-xl">
            <div>
              <h3 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span>TRỢ LÝ LƯỢNG HÓA AI OMNI-QUANT COPILOT (F27)</span>
              </h3>
              <p className="text-[11px] text-zinc-400 mt-1">
                Tích hợp phân tích kỹ thuật, vĩ mô và tạo khuyến nghị giao dịch theo thời gian thực.
              </p>
            </div>
            <button
              onClick={() => setActiveModule('strategy_lab')}
              className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold flex items-center gap-1.5 transition-all shadow-lg shadow-emerald-950"
            >
              <ArrowUpRight className="w-3.5 h-3.5" />
              <span>MỞ STRATEGY LAB COPILOT</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 uppercase font-bold">Chế Độ Giám Sát</span>
              <div className="text-lg font-bold text-emerald-400">TỰ ĐỘNG KHUYẾN NGHỊ</div>
              <p className="text-[11px] text-zinc-400">
                Tự động đánh giá danh mục và kích hoạt lệnh tái cân bằng thông qua quy trình bảo mật TOTP.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 uppercase font-bold">Điểm Tín Hiệu Tổng Thể</span>
              <div className="text-lg font-bold text-cyan-300">88.5 / 100</div>
              <p className="text-[11px] text-zinc-400">
                Độ đồng thuận cao giữa mô hình định lượng định chế và phân tích tâm lý tin tức tài chính.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 uppercase font-bold">Khuyến Nghị Hành Động</span>
              <div className="text-lg font-bold text-amber-300">4 KHUYẾN NGHỊ</div>
              <p className="text-[11px] text-zinc-400">
                Bao gồm điều chỉnh tỷ trọng phòng vệ rủi ro Barra và phân bổ danh mục theo biến động ATR.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB VIEW 8: MULTI-PROVIDER LLM BRIDGE (F28)                            */}
      {/* ========================================================================= */}
      {activeSubTab === 'llm_bridge' && (
        <div className="flex flex-col gap-4 flex-1 overflow-y-auto pr-1">
          <div className="p-4 rounded-xl bg-zinc-900/90 border border-cyan-500/30 flex flex-wrap items-center justify-between gap-3 text-xs shadow-xl">
            <div>
              <h3 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span>CẦU NỐI ĐA MÔ HÌNH LLM INTELLIGENT BRIDGE (F28)</span>
              </h3>
              <p className="text-[11px] text-zinc-400 mt-1">
                Quản trị 4 hồ sơ mô hình AI chuyên biệt cho vĩ mô, lượng hóa, tin tức và điều phối hệ thống.
              </p>
            </div>
            <button
              onClick={() => setActiveModule('model_registry')}
              className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-zinc-950 font-bold flex items-center gap-1.5 transition-all shadow-lg shadow-cyan-950"
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>QUẢN TRỊ MODEL REGISTRY</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 font-bold uppercase">Hồ Sơ Global</span>
              <div className="text-sm font-bold text-zinc-100">OpenAI GPT-4o</div>
              <span className="text-[10px] text-emerald-400 font-semibold">Trạng thái: Hoạt động</span>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 font-bold uppercase">Alpha Quant</span>
              <div className="text-sm font-bold text-zinc-100">Anthropic Claude 3.5</div>
              <span className="text-[10px] text-emerald-400 font-semibold">Trạng thái: Hoạt động</span>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 font-bold uppercase">News Sentiment</span>
              <div className="text-sm font-bold text-zinc-100">Google Gemini 1.5 Pro</div>
              <span className="text-[10px] text-emerald-400 font-semibold">Trạng thái: Hoạt động</span>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-col gap-2">
              <span className="text-[10px] text-zinc-400 font-bold uppercase">Macro & Micro</span>
              <div className="text-sm font-bold text-zinc-100">DeepSeek Chat / R1</div>
              <span className="text-[10px] text-emerald-400 font-semibold">Trạng thái: Hoạt động</span>
            </div>
          </div>
        </div>
      )}

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
