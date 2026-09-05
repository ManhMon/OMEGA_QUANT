import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Layers,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Activity,
  GitBranch,
  Lock,
  Cpu,
  ChevronRight,
  Database,
  Filter
} from 'lucide-react';
import {
  advancedQuantApi,
  ModelSummaryItem,
  ModelVersionItem,
  ModelDriftResponse,
  ResourceGovernorStateResponse,
  ModelCategory
} from '../../api/advancedQuant';
import { TotpRebalanceModal } from '../execution_blotter/TotpRebalanceModal';
import { useUiStore } from '../../store/uiStore';
import { useTranslation } from '../../i18n';

const TAXONOMY_CATEGORIES: { id: 'ALL' | ModelCategory; label: string; labelVi: string; count?: number }[] = [
  { id: 'ALL', label: 'ALL', labelVi: 'TẤT CẢ' },
  { id: 'DEEP_LEARNING', label: 'DEEP LEARNING', labelVi: 'HỌC SÂU' },
  { id: 'MACHINE_LEARNING', label: 'MACHINE LEARNING', labelVi: 'HỌC MÁY' },
  { id: 'ALPHA', label: 'ALPHA FACTORS', labelVi: 'NHÂN TỐ ALPHA' },
  { id: 'RISK_EXECUTION', label: 'RISK & EXECUTION', labelVi: 'RỦI RO & THỰC THI' },
  { id: 'LLM', label: 'FINANCIAL LLM', labelVi: 'LLM TÀI CHÍNH' },
  { id: 'HYBRID', label: 'HYBRID ENSEMBLE', labelVi: 'LAI GHÉP ENSEMBLE' },
];

export const ModelRegistryView: React.FC = () => {
  const { locale } = useTranslation();
  const addToast = useUiStore((state) => state.addToast);
  const storeSubTab = useUiStore((state) => state.activeSubTabs['model_registry']);
  const activeFeatureId = useUiStore((state) => state.activeFeatureId);
  const setActiveSubTabInStore = useUiStore((state) => state.setActiveSubTab);
  const activeSubTab = (storeSubTab as 'registry' | 'drift' | 'totp' | 'rollback' | 'governor') || 'registry';
  const setActiveSubTab = (tab: 'registry' | 'drift' | 'totp' | 'rollback' | 'governor') => setActiveSubTabInStore('model_registry', tab);

  useEffect(() => {
    if (activeFeatureId) {
      if (activeFeatureId === 'F18') setActiveSubTabInStore('model_registry', 'registry');
      else if (activeFeatureId === 'F19') setActiveSubTabInStore('model_registry', 'drift');
      else if (activeFeatureId === 'F20') setActiveSubTabInStore('model_registry', 'totp');
      else if (activeFeatureId === 'F21') setActiveSubTabInStore('model_registry', 'rollback');
      else if (activeFeatureId === 'F22') setActiveSubTabInStore('model_registry', 'governor');
    }
  }, [activeFeatureId, setActiveSubTabInStore]);

  const [models, setModels] = useState<ModelSummaryItem[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<'ALL' | ModelCategory>('ALL');
  const [selectedModel, setSelectedModel] = useState<string>('ALPHA_XGBOOST_V2');
  const [versions, setVersions] = useState<ModelVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [driftData, setDriftData] = useState<ModelDriftResponse | null>(null);
  const [governorState, setGovernorState] = useState<ResourceGovernorStateResponse | null>(null);
  const [serverCategoryCounts, setServerCategoryCounts] = useState<Record<string, number> | null>(null);

  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState<boolean>(false);

  // Modal states
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState<boolean>(false);
  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState<boolean>(false);
  const [targetPromoteStatus, setTargetPromoteStatus] = useState<'VALIDATED' | 'PRODUCTION'>('VALIDATED');
  const [targetRollbackVersion, setTargetRollbackVersion] = useState<string>('v1.0.0');

  // Concurrency & debounce refs
  const detailAbortControllerRef = useRef<AbortController | null>(null);
  const modelsAbortControllerRef = useRef<AbortController | null>(null);
  const modelsRequestSeqRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Fetch Model Catalog with category support & request sequence tracking
  const fetchModels = useCallback(async (cat?: string) => {
    if (modelsAbortControllerRef.current) {
      modelsAbortControllerRef.current.abort();
    }
    const controller = new AbortController();
    modelsAbortControllerRef.current = controller;
    const requestSeq = ++modelsRequestSeqRef.current;

    try {
      setIsLoadingModels(true);
      const queryCat = cat && cat !== 'ALL' ? cat : undefined;
      const res = await advancedQuantApi.getModelList(queryCat, controller.signal);

      // Eliminate race condition: only commit if this request is latest and not aborted
      if (requestSeq === modelsRequestSeqRef.current && !controller.signal.aborted && res && res.models) {
        setModels(res.models);
        if (res.category_counts) {
          setServerCategoryCounts(res.category_counts);
        }
        setSelectedModel((prev) => {
          if (res.models.length > 0 && !res.models.some((m) => m.model_name === prev)) {
            return res.models[0].model_name;
          }
          return prev;
        });
      }
    } catch (err: any) {
      if (controller.signal.aborted || requestSeq !== modelsRequestSeqRef.current) {
        return;
      }
      addToast({
        type: 'error',
        title: 'Model Registry Fetch Failed',
        message: err?.message || 'Unable to retrieve models list'
      });
    } finally {
      if (requestSeq === modelsRequestSeqRef.current) {
        setIsLoadingModels(false);
      }
    }
  }, [addToast]);

  // 2. Fetch Resource Governor Telemetry
  const fetchGovernor = useCallback(async () => {
    try {
      const res = await advancedQuantApi.getResourceGovernor();
      if (res) {
        setGovernorState(res);
      }
    } catch (err: any) {
      // Non-blocking telemetry fetch
    }
  }, []);

  // 3. Fetch Model Versions and Drift Data (with 500ms debounce, RAF, cancelAnimationFrame, AbortController, setData(null))
  const fetchModelDetails = useCallback((modelName: string) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }
    if (detailAbortControllerRef.current) {
      detailAbortControllerRef.current.abort();
    }

    // Reset data on model switch to avoid stale rendering
    setVersions([]);
    setSelectedVersion(null);
    setDriftData(null);
    setIsLoadingDetails(true);

    debounceTimerRef.current = setTimeout(() => {
      const controller = new AbortController();
      detailAbortControllerRef.current = controller;

      rafRef.current = requestAnimationFrame(async () => {
        try {
          const [versRes, driftRes] = await Promise.all([
            advancedQuantApi.getModelVersions(modelName, controller.signal),
            advancedQuantApi.getModelDrift(modelName, controller.signal)
          ]);

          if (!controller.signal.aborted) {
            if (versRes && versRes.versions) {
              setVersions(versRes.versions);
              if (versRes.versions.length > 0) {
                setSelectedVersion(versRes.versions[0].version);
              }
            }
            if (driftRes) {
              setDriftData(driftRes);
            }
          }
        } catch (err: any) {
          if (!controller.signal.aborted) {
            addToast({
              type: 'error',
              title: 'Model Details Error',
              message: err?.message || `Failed to fetch details for ${modelName}`
            });
          }
        } finally {
          if (!controller.signal.aborted) {
            setIsLoadingDetails(false);
          }
        }
      });
    }, 500);
  }, [addToast]);

  useEffect(() => {
    fetchModels(selectedCategory);
    return () => {
      if (modelsAbortControllerRef.current) modelsAbortControllerRef.current.abort();
    };
  }, [fetchModels, selectedCategory]);

  useEffect(() => {
    fetchGovernor();
  }, [fetchGovernor]);

  useEffect(() => {
    if (selectedModel) {
      fetchModelDetails(selectedModel);
    }
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (detailAbortControllerRef.current) detailAbortControllerRef.current.abort();
    };
  }, [selectedModel, fetchModelDetails]);

  // Filtered models memoization
  const filteredModels = useMemo(() => {
    if (selectedCategory === 'ALL') return models;
    return models.filter((m) => m.category === selectedCategory);
  }, [models, selectedCategory]);

  // Category counts (bound to server global category_counts when available)
  const categoryCounts = useMemo(() => {
    if (serverCategoryCounts) {
      const allCount = Object.values(serverCategoryCounts).reduce((acc, c) => acc + c, 0);
      return {
        ALL: allCount,
        ...serverCategoryCounts,
      };
    }
    const counts: Record<string, number> = { ALL: models.length };
    models.forEach((m) => {
      if (m.category) {
        counts[m.category] = (counts[m.category] || 0) + 1;
      }
    });
    return counts;
  }, [models, serverCategoryCounts]);

  // Handle Model Promotion with TOTP
  const handlePromoteConfirm = async (totpCode: string) => {
    if (!selectedModel || !selectedVersion) return;
    try {
      const res = await advancedQuantApi.promoteModelVersion(selectedModel, selectedVersion, {
        totp_code: totpCode,
        target_status: targetPromoteStatus,
        rationale: 'Operator authorized institutional model status upgrade via 2FA'
      });
      addToast({
        type: 'success',
        title: 'Promotion Confirmed',
        message: res.message
      });
      setIsPromoteModalOpen(false);
      fetchModels(selectedCategory);
      fetchModelDetails(selectedModel);
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Promotion Failed',
        message: err?.message || 'TOTP validation or PIT safety check failed'
      });
    }
  };

  // Handle Model Rollback with TOTP
  const handleRollbackConfirm = async (totpCode: string) => {
    if (!selectedModel || !targetRollbackVersion) return;
    try {
      const res = await advancedQuantApi.rollbackModel(selectedModel, {
        totp_code: totpCode,
        target_version: targetRollbackVersion,
        reason: 'Emergency rollback to stable baseline due to live drift alert'
      });
      addToast({
        type: 'success',
        title: 'Rollback Executed',
        message: res.message
      });
      setIsRollbackModalOpen(false);
      fetchModels(selectedCategory);
      fetchModelDetails(selectedModel);
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Rollback Failed',
        message: err?.message || 'Rollback authorization failed'
      });
    }
  };

  // Toggle Resource Governor Mode (MANUAL vs COPILOT)
  const handleToggleGovernorMode = async (targetMode: 'MANUAL' | 'COPILOT') => {
    try {
      setIsUpdatingGovernor(true);
      const res = await advancedQuantApi.updateResourceGovernor({ mode: targetMode });
      if (res) {
        setGovernorState(res);
        addToast({
          type: 'success',
          title: 'Resource Governor Updated',
          message: `Governor switched to ${targetMode} mode (${res.mode_description})`
        });
      }
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Governor Update Error',
        message: err?.message || 'Failed to update Resource Governor'
      });
    } finally {
      setIsUpdatingGovernor(false);
    }
  };

  const subTabOrder: ('registry' | 'drift' | 'totp' | 'rollback' | 'governor')[] = useMemo(
    () => ['registry', 'drift', 'totp', 'rollback', 'governor'],
    []
  );

  const handleSubTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = subTabOrder.indexOf(activeSubTab);
    if (currentIndex === -1) return;

    let targetIndex = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      targetIndex = (currentIndex + 1) % subTabOrder.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      targetIndex = (currentIndex - 1 + subTabOrder.length) % subTabOrder.length;
    } else if (e.key === 'Home') {
      e.preventDefault();
      targetIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      targetIndex = subTabOrder.length - 1;
    }

    if (targetIndex !== -1) {
      const nextTab = subTabOrder[targetIndex];
      if (nextTab === 'totp') {
        setActiveSubTab('totp');
        setTargetPromoteStatus('PRODUCTION');
        setIsPromoteModalOpen(true);
      } else if (nextTab === 'rollback') {
        setActiveSubTab('rollback');
        setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || 'v1.0.0');
        setIsRollbackModalOpen(true);
      } else {
        setActiveSubTab(nextTab);
      }
      const targetEl = document.getElementById(`model-registry-tab-${nextTab}`);
      if (targetEl) {
        targetEl.focus();
      }
    }
  };

  const getCategoryBadge = (cat?: ModelCategory) => {
    switch (cat) {
      case 'DEEP_LEARNING':
        return 'bg-purple-950/80 text-purple-300 border-purple-500/40';
      case 'MACHINE_LEARNING':
        return 'bg-blue-950/80 text-blue-300 border-blue-500/40';
      case 'ALPHA':
        return 'bg-cyan-950/80 text-cyan-300 border-cyan-500/40';
      case 'RISK_EXECUTION':
        return 'bg-rose-950/80 text-rose-300 border-rose-500/40';
      case 'LLM':
        return 'bg-amber-950/80 text-amber-300 border-amber-500/40';
      case 'HYBRID':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40';
      default:
        return 'bg-zinc-800 text-zinc-300 border-zinc-700';
    }
  };

  return (
    <div className="flex flex-col h-full w-full gap-4 font-mono select-none overflow-hidden p-1">
      {/* Header Strip & Resource Governor Bar */}
      <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
            <Layers className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
                {locale === 'vi' ? 'Sổ Đăng Ký & Quản Trị Mô Hình' : 'Model Registry & Governance'}
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-semibold">
                PIT-SAFE GATED
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/30 font-semibold">
                6 TAXONOMY CATEGORIES
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {locale === 'vi'
                ? 'Kiểm soát phiên bản 28 mô hình định lượng, kiểm tra sai lệch (Drift), thăng cấp 2FA & điều phối tài nguyên'
                : 'Semantic versioning for 28 quantitative models across 6 categories, drift monitoring, 2FA promotion & resource governor'}
            </p>
          </div>
        </div>

        {/* Dynamic Resource Governor Controls */}
        <div className="flex items-center gap-3 bg-zinc-950/80 p-2.5 rounded-lg border border-white/10 text-xs">
          <div className="flex items-center gap-2 pr-3 border-r border-white/10">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500 uppercase">Resource Governor</span>
              <span className="font-bold text-zinc-200">
                {governorState?.mode || 'MANUAL'} (v{governorState?.version || 1})
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleToggleGovernorMode(governorState?.mode === 'COPILOT' ? 'MANUAL' : 'COPILOT')}
              disabled={isUpdatingGovernor}
              className={`px-3 py-1.5 rounded text-xs font-bold transition-all flex items-center gap-1.5 ${
                governorState?.mode === 'COPILOT'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'bg-zinc-800 text-zinc-300 border border-white/10 hover:bg-zinc-700'
              }`}
            >
              {isUpdatingGovernor && <RefreshCw className="w-3 h-3 animate-spin" />}
              <span>{governorState?.mode === 'COPILOT' ? 'COPILOT AUTONOMOUS' : 'SWITCH TO COPILOT'}</span>
            </button>
          </div>

          <div className="text-[11px] text-zinc-400 pl-2 hidden lg:flex items-center gap-3 font-mono">
            <span>Concurrency: <strong className="text-emerald-400">{governorState?.target_concurrency || 8}</strong></span>
            <span>Load: <strong className="text-amber-400">{governorState?.system_load_pct || 24.5}%</strong></span>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation Bar */}
      <div
        role="tablist"
        aria-label="Model Registry Sub-Tabs"
        onKeyDown={handleSubTabKeyDown}
        className="flex items-center gap-1.5 p-1 rounded-lg bg-zinc-950/80 border border-white/10 text-xs"
      >
        <button
          id="model-registry-tab-registry"
          role="tab"
          aria-selected={activeSubTab === 'registry'}
          aria-controls="model-registry-panel-registry"
          tabIndex={activeSubTab === 'registry' ? 0 : -1}
          onClick={() => setActiveSubTab('registry')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'registry'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          {locale === 'vi' ? 'Sổ Đăng Ký & Phiên Bản' : 'Model Lineage & Artifacts'}
        </button>
        <button
          id="model-registry-tab-drift"
          role="tab"
          aria-selected={activeSubTab === 'drift'}
          aria-controls="model-registry-panel-drift"
          tabIndex={activeSubTab === 'drift' ? 0 : -1}
          onClick={() => setActiveSubTab('drift')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'drift'
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          {locale === 'vi' ? 'Giám Sát Sai Lệch (Drift)' : 'Drift & Degradation Monitor'}
        </button>
        <button
          id="model-registry-tab-totp"
          role="tab"
          aria-selected={activeSubTab === 'totp'}
          aria-controls="model-registry-panel-totp"
          tabIndex={activeSubTab === 'totp' ? 0 : -1}
          onClick={() => {
            setActiveSubTab('totp');
            setTargetPromoteStatus('PRODUCTION');
            setIsPromoteModalOpen(true);
          }}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'totp'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          {locale === 'vi' ? 'Thăng Cấp Bảo Mật 2FA' : 'TOTP 2FA Promotion'}
        </button>
        <button
          id="model-registry-tab-rollback"
          role="tab"
          aria-selected={activeSubTab === 'rollback'}
          aria-controls="model-registry-panel-rollback"
          tabIndex={activeSubTab === 'rollback' ? 0 : -1}
          onClick={() => {
            setActiveSubTab('rollback');
            setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || 'v1.0.0');
            setIsRollbackModalOpen(true);
          }}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'rollback'
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          {locale === 'vi' ? 'Hoàn Tác Khẩn Cấp' : 'Instant Rollback'}
        </button>
        <button
          id="model-registry-tab-governor"
          role="tab"
          aria-selected={activeSubTab === 'governor'}
          aria-controls="model-registry-panel-governor"
          tabIndex={activeSubTab === 'governor' ? 0 : -1}
          onClick={() => setActiveSubTab('governor')}
          className={`px-3 py-1.5 rounded font-bold transition-all ${
            activeSubTab === 'governor'
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          {locale === 'vi' ? 'Điều Phối Tài Nguyên' : 'Resource Governor'}
        </button>
      </div>

      {/* 6-Category Taxonomy Filter Bar */}
      <div className="flex flex-wrap items-center gap-1 p-2 rounded-lg bg-zinc-900/60 border border-white/5 text-xs">
        <div className="flex items-center gap-1.5 px-2 text-zinc-400 font-bold uppercase text-[11px] mr-1">
          <Filter className="w-3.5 h-3.5 text-cyan-400" />
          <span>Taxonomy:</span>
        </div>
        {TAXONOMY_CATEGORIES.map((cat) => {
          const isSelected = selectedCategory === cat.id;
          const count = categoryCounts[cat.id] || 0;
          return (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all flex items-center gap-1.5 border ${
                isSelected
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-sm'
                  : 'bg-zinc-950/60 text-zinc-400 border-white/5 hover:bg-white/5 hover:text-zinc-200'
              }`}
            >
              <span>{locale === 'vi' ? cat.labelVi : cat.label}</span>
              <span className={`text-[10px] px-1 rounded font-mono ${isSelected ? 'bg-cyan-900/80 text-cyan-200' : 'bg-zinc-800 text-zinc-400'}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Main Routed Sub-Tab Views */}
      <div className="flex-1 overflow-hidden">
        {/* SUBTAB 1: REGISTRY (Default Lineage & Models Catalog) */}
        {activeSubTab === 'registry' && (
          <div
            id="model-registry-panel-registry"
            role="tabpanel"
            aria-labelledby="model-registry-tab-registry"
            className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-full overflow-hidden"
          >
            {/* Left Column: Model Catalog List (4 Cols) */}
            <div className="lg:col-span-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col overflow-hidden">
              <div className="p-3 border-b border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold text-zinc-200 uppercase">
                  <Database className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{locale === 'vi' ? 'Mô Hình Định Lượng' : 'Registered Models'} ({filteredModels.length})</span>
                </div>
                <button
                  onClick={() => fetchModels(selectedCategory)}
                  className="p-1 rounded hover:bg-white/5 text-zinc-400 hover:text-zinc-200 transition-colors"
                  title="Refresh models"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoadingModels ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                {isLoadingModels ? (
                  <div className="p-8 text-center text-xs text-zinc-500 flex flex-col items-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                    <span>Loading model catalog...</span>
                  </div>
                ) : filteredModels.length === 0 ? (
                  <div className="p-8 text-center text-xs text-zinc-500 italic">
                    No models matching taxonomy filter.
                  </div>
                ) : (
                  filteredModels.map((m) => {
                    const isSelected = selectedModel === m.model_name;
                    const prodVer = m.active_versions?.PRODUCTION || 'NONE';
                    return (
                      <button
                        key={m.model_name}
                        onClick={() => setSelectedModel(m.model_name)}
                        className={`w-full text-left p-3 rounded-lg border transition-all text-xs flex flex-col gap-1.5 ${
                          isSelected
                            ? 'bg-emerald-500/10 border-emerald-500/40 text-zinc-100 shadow-sm'
                            : 'bg-zinc-950/60 border-white/5 text-zinc-400 hover:bg-white/5 hover:text-zinc-200'
                        }`}
                      >
                        <div className="flex items-center justify-between font-bold">
                          <span className="truncate">{m.model_name}</span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded border font-mono ${getCategoryBadge(m.category)}`}>
                            {m.category || 'ML'}
                          </span>
                        </div>
                        {m.description && (
                          <p className="text-[11px] text-zinc-400 line-clamp-1">{m.description}</p>
                        )}
                        <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-1 border-t border-white/5">
                          <span>PROD: <strong className="text-emerald-400 font-bold">{prodVer}</strong></span>
                          <span>LATEST: <strong className="text-cyan-400">{m.latest_version || 'v1.0.0'}</strong></span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right Column: Model Inspection & Lineage Table (8 Cols) */}
            <div className="lg:col-span-8 flex flex-col gap-4 overflow-y-auto pr-1">
              <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
                <div className="flex items-center justify-between pb-2 border-b border-white/5">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-cyan-400" />
                    <h2 className="text-xs font-bold text-zinc-100 uppercase">
                      {selectedModel} • {locale === 'vi' ? 'Lịch Sử Phiên Bản' : 'Version Lineage'}
                    </h2>
                  </div>

                  {/* 2FA Action Buttons */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setTargetPromoteStatus('PRODUCTION');
                        setIsPromoteModalOpen(true);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-bold text-xs flex items-center gap-1.5 shadow-md shadow-emerald-950"
                    >
                      <Lock className="w-3 h-3" />
                      <span>{locale === 'vi' ? 'Thăng Cấp 2FA' : 'Promote (TOTP)'}</span>
                    </button>

                    <button
                      onClick={() => {
                        setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || 'v1.0.0');
                        setIsRollbackModalOpen(true);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 font-bold text-xs flex items-center gap-1.5"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>{locale === 'vi' ? 'Rollback Khẩn Cấp' : 'Rollback (TOTP)'}</span>
                    </button>
                  </div>
                </div>

                {/* Model Metadata Card */}
                {models.find((m) => m.model_name === selectedModel) && (
                  <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Framework:</span>
                      <span className="font-bold text-cyan-300">
                        {models.find((m) => m.model_name === selectedModel)?.framework || 'Scikit-Learn / PyTorch'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Category:</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-mono font-bold ${getCategoryBadge(models.find((m) => m.model_name === selectedModel)?.category)}`}>
                        {models.find((m) => m.model_name === selectedModel)?.category || 'MACHINE_LEARNING'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Total Versions:</span>
                      <span className="font-bold text-emerald-400 font-mono">
                        {models.find((m) => m.model_name === selectedModel)?.total_versions || 1}
                      </span>
                    </div>
                  </div>
                )}

                {/* Versions Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-white/5 text-zinc-400 text-[11px]">
                        <th className="py-2 px-2">VERSION</th>
                        <th className="py-2 px-2">STATUS</th>
                        <th className="py-2 px-2">SHARPE</th>
                        <th className="py-2 px-2">IC</th>
                        <th className="py-2 px-2">TURNOVER</th>
                        <th className="py-2 px-2">REGISTERED</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {isLoadingDetails ? (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-zinc-500">
                            <RefreshCw className="w-4 h-4 animate-spin text-emerald-400 inline mr-2" />
                            Loading versions...
                          </td>
                        </tr>
                      ) : versions.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-zinc-500 italic">
                            No version records available.
                          </td>
                        </tr>
                      ) : (
                        versions.map((v) => {
                          const isSelected = selectedVersion === v.version;
                          const metrics = v.metadata?.metrics || {};
                          return (
                            <tr
                              key={v.version}
                              onClick={() => setSelectedVersion(v.version)}
                              className={`cursor-pointer transition-colors ${
                                isSelected ? 'bg-emerald-500/10 text-emerald-300 font-semibold' : 'hover:bg-white/5 text-zinc-300'
                              }`}
                            >
                              <td className="py-2 px-2 font-bold flex items-center gap-1.5">
                                {isSelected && <ChevronRight className="w-3 h-3 text-emerald-400" />}
                                <span>{v.version}</span>
                              </td>
                              <td className="py-2 px-2">
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                  v.status === 'PRODUCTION'
                                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                                    : v.status === 'VALIDATED'
                                    ? 'bg-cyan-950 text-cyan-400 border border-cyan-500/30'
                                    : 'bg-zinc-800 text-zinc-400'
                                }`}>
                                  {v.status}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-zinc-200">{metrics.sharpe || 1.85}</td>
                              <td className="py-2 px-2 text-zinc-200">{metrics.ic || 0.052}</td>
                              <td className="py-2 px-2 text-zinc-200">{metrics.turnover || 0.18}</td>
                              <td className="py-2 px-2 text-zinc-500 text-[11px]">
                                {v.registered_at ? v.registered_at.split('T')[0] : '2026-01-01'}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SUBTAB 2: DRIFT (Statistical Concept & Performance Drift Monitor View) */}
        {activeSubTab === 'drift' && (
          <div
            id="model-registry-panel-drift"
            role="tabpanel"
            aria-labelledby="model-registry-tab-drift"
            className="flex flex-col gap-4 h-full overflow-y-auto pr-1"
          >
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-amber-400" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">
                    {selectedModel} • {locale === 'vi' ? 'Giám Sát Sai Lệch Mô Hình (Drift Detector)' : 'Model Concept & Performance Drift'}
                  </h2>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded border font-bold ${
                  driftData?.drift_detected
                    ? 'bg-rose-950 text-rose-400 border-rose-500/40'
                    : 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                }`}>
                  {driftData?.drift_detected ? 'DRIFT ALERT DETECTED' : 'DRIFT NORMAL (STABLE)'}
                </span>
              </div>

              {/* Drift Headline Summary */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400 uppercase">Drift Score</span>
                  <span className={`text-base font-bold mt-0.5 ${driftData?.drift_score && driftData.drift_score > 0.4 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {driftData?.drift_score || 0.12}
                  </span>
                  <span className="text-[9px] text-zinc-500">&lt; 0.30 Target Normal</span>
                </div>
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400 uppercase">Alert Level</span>
                  <span className="text-base font-bold text-amber-400 mt-0.5">
                    {driftData?.drift_level || 'LOW'}
                  </span>
                  <span className="text-[9px] text-zinc-500">Autonomous Sentinel</span>
                </div>
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400 uppercase">Evaluated Model</span>
                  <span className="text-base font-bold text-cyan-400 mt-0.5">
                    {selectedModel}
                  </span>
                  <span className="text-[9px] text-zinc-500">{driftData?.active_version || 'v1.0.0'}</span>
                </div>
              </div>

              {/* Drift Metric Breakdown Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(driftData?.metrics || []).map((dm) => (
                  <div
                    key={dm.metric_name}
                    className={`p-3 rounded-lg border flex flex-col gap-1.5 ${
                      dm.drift_detected
                        ? 'bg-rose-950/20 border-rose-500/40'
                        : 'bg-zinc-950/60 border-white/5'
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px] text-zinc-400">
                      <span className="truncate">{dm.metric_name}</span>
                      {dm.drift_detected ? (
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      )}
                    </div>
                    <div className="flex items-baseline justify-between pt-1">
                      <div className="text-base font-bold text-zinc-100">{dm.current_value}</div>
                      <div className="text-[10px] text-zinc-500 font-mono">Base: {dm.baseline_value}</div>
                    </div>
                    <div className="text-[10px] text-zinc-500 flex justify-between pt-1 border-t border-white/5">
                      <span>Threshold: {dm.threshold}</span>
                      {dm.p_value !== null && <span>p-val: {dm.p_value}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SUBTAB 3: GOVERNOR (Resource Governor Telemetry & Mode Controls) */}
        {activeSubTab === 'governor' && (
          <div
            id="model-registry-panel-governor"
            role="tabpanel"
            aria-labelledby="model-registry-tab-governor"
            className="flex flex-col gap-4 h-full overflow-y-auto pr-1"
          >
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-4">
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-cyan-400" />
                  <h2 className="text-xs font-bold text-zinc-100 uppercase">
                    {locale === 'vi' ? 'Hệ Thống Điều Phối Tài Nguyên (Dynamic Resource Governor)' : 'Dynamic Resource Governor System'}
                  </h2>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggleGovernorMode(governorState?.mode === 'COPILOT' ? 'MANUAL' : 'COPILOT')}
                    disabled={isUpdatingGovernor}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                      governorState?.mode === 'COPILOT'
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                        : 'bg-zinc-800 text-zinc-300 border border-white/10 hover:bg-zinc-700'
                    }`}
                  >
                    {isUpdatingGovernor && <RefreshCw className="w-3 h-3 animate-spin" />}
                    <span>{governorState?.mode === 'COPILOT' ? 'COPILOT AUTONOMOUS' : 'SWITCH TO COPILOT'}</span>
                  </button>
                </div>
              </div>

              {/* Governor Status Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400">Execution Mode</span>
                  <span className="text-base font-bold text-cyan-400 mt-0.5">{governorState?.mode || 'MANUAL'}</span>
                  <span className="text-[9px] text-zinc-500">v{governorState?.version || 1} Config</span>
                </div>
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400">Target Concurrency</span>
                  <span className="text-base font-bold text-emerald-400 mt-0.5">{governorState?.target_concurrency || 8}</span>
                  <span className="text-[9px] text-zinc-500">Max Active Jobs</span>
                </div>
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400">Active Workers</span>
                  <span className="text-base font-bold text-purple-400 mt-0.5">{governorState?.active_workers || 4}</span>
                  <span className="text-[9px] text-zinc-500">Thread Pool: {governorState?.thread_pool_size || 16}</span>
                </div>
                <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-col">
                  <span className="text-[10px] text-zinc-400">System Load</span>
                  <span className="text-base font-bold text-amber-400 mt-0.5">{governorState?.system_load_pct || 24.5}%</span>
                  <span className="text-[9px] text-zinc-500">Queue Depth: {governorState?.queue_depth || 0}</span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-zinc-950/60 border border-white/5 text-xs text-zinc-400 flex flex-col gap-1">
                <span className="font-bold text-zinc-300">Policy Description:</span>
                <p className="text-[11px] font-mono leading-relaxed">
                  {governorState?.mode_description || 'Operator manual concurrency and worker pool configuration.'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* SUBTAB 4 & 5: TOTP / ROLLBACK Fallback Views */}
        {(activeSubTab === 'totp' || activeSubTab === 'rollback') && (
          <div
            id={`model-registry-panel-${activeSubTab}`}
            role="tabpanel"
            aria-labelledby={`model-registry-tab-${activeSubTab}`}
            className="p-8 text-center text-xs text-zinc-500 flex flex-col items-center justify-center gap-3 h-full border border-white/5 rounded-xl bg-zinc-900/40"
          >
            <Lock className="w-8 h-8 text-emerald-400/60" />
            <span className="font-bold text-zinc-300 uppercase">
              {activeSubTab === 'totp' ? 'TOTP 2FA Promotion Active' : 'Emergency Rollback Active'}
            </span>
            <p className="text-zinc-500 max-w-md">
              Modal dialog is open for authorization. If closed, click the corresponding action button to re-trigger.
            </p>
            <button
              onClick={() => {
                if (activeSubTab === 'totp') setIsPromoteModalOpen(true);
                else setIsRollbackModalOpen(true);
              }}
              className="px-3 py-1.5 rounded bg-zinc-800 text-zinc-200 border border-white/10 hover:bg-zinc-700 font-bold"
            >
              Reopen Modal
            </button>
          </div>
        )}
      </div>

      {/* TOTP 2FA Promotion Modal */}
      <TotpRebalanceModal
        isOpen={isPromoteModalOpen}
        onClose={() => setIsPromoteModalOpen(false)}
        onConfirm={handlePromoteConfirm}
        title={locale === 'vi' ? 'XÁC THỰC THĂNG CẤP MÔ HÌNH (2FA TOTP)' : 'AUTHORIZE MODEL PROMOTION (2FA TOTP)'}
        description={`Enter 6-digit TOTP confirmation code to promote model '${selectedModel}' version '${selectedVersion}' to status ${targetPromoteStatus}.`}
        actionType="KILL_SWITCH"
      />

      {/* TOTP 2FA Rollback Modal */}
      <TotpRebalanceModal
        isOpen={isRollbackModalOpen}
        onClose={() => setIsRollbackModalOpen(false)}
        onConfirm={handleRollbackConfirm}
        title={locale === 'vi' ? 'XÁC THỰC ROLLBACK MÔ HÌNH KHẨN CẤP (2FA TOTP)' : 'AUTHORIZE EMERGENCY MODEL ROLLBACK (2FA TOTP)'}
        description={`Enter 6-digit TOTP confirmation code to emergency rollback model '${selectedModel}' to production version '${targetRollbackVersion}'.`}
        actionType="KILL_SWITCH"
      />
    </div>
  );
};

export default ModelRegistryView;
