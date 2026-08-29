import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  Database
} from 'lucide-react';
import {
  advancedQuantApi,
  ModelSummaryItem,
  ModelVersionItem,
  ModelDriftResponse,
  ResourceGovernorStateResponse
} from '../../api/advancedQuant';
import { TotpRebalanceModal } from '../execution_blotter/TotpRebalanceModal';
import { useUiStore } from '../../store/uiStore';
import { useTranslation } from '../../i18n';

export const ModelRegistryView: React.FC = () => {
  const { locale } = useTranslation();
  const addToast = useUiStore((state) => state.addToast);

  const [models, setModels] = useState<ModelSummaryItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('ALPHA_XGBOOST_V2');
  const [versions, setVersions] = useState<ModelVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [driftData, setDriftData] = useState<ModelDriftResponse | null>(null);
  const [governorState, setGovernorState] = useState<ResourceGovernorStateResponse | null>(null);

  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState<boolean>(false);

  // Modal states
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState<boolean>(false);
  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState<boolean>(false);
  const [targetPromoteStatus, setTargetPromoteStatus] = useState<'VALIDATED' | 'PRODUCTION'>('VALIDATED');
  const [targetRollbackVersion, setTargetRollbackVersion] = useState<string>('v1.0.0');

  // Concurrency & debounce refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const rafRef = useRef<number | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Fetch Model Catalog
  const fetchModels = useCallback(async () => {
    try {
      setIsLoadingModels(true);
      const res = await advancedQuantApi.getModelList();
      if (res && res.models) {
        setModels(res.models);
        if (res.models.length > 0 && !res.models.some((m) => m.model_name === selectedModel)) {
          setSelectedModel(res.models[0].model_name);
        }
      }
    } catch (err: any) {
      addToast({
        type: 'error',
        title: 'Model Registry Fetch Failed',
        message: err?.message || 'Unable to retrieve models list'
      });
    } finally {
      setIsLoadingModels(false);
    }
  }, [selectedModel, addToast]);

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
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Reset data on model switch to avoid stale rendering
    setVersions([]);
    setSelectedVersion(null);
    setDriftData(null);
    setIsLoadingDetails(true);

    debounceTimerRef.current = setTimeout(() => {
      const controller = new AbortController();
      abortControllerRef.current = controller;

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
    fetchModels();
    fetchGovernor();
  }, [fetchModels, fetchGovernor]);

  useEffect(() => {
    if (selectedModel) {
      fetchModelDetails(selectedModel);
    }
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [selectedModel, fetchModelDetails]);

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
      fetchModels();
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
      fetchModels();
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
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {locale === 'vi'
                ? 'Kiểm soát phiên bản, kiểm tra sai lệch (Drift), thăng cấp 2FA TOTP & điều phối tài nguyên'
                : 'Semantic versioning, drift detection, 2FA promotion workflow & dynamic resource governor'}
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

      {/* Main 2-Column Workstation Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 overflow-hidden">
        {/* Left Column: Model Catalog List (4 Cols) */}
        <div className="lg:col-span-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col overflow-hidden">
          <div className="p-3 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold text-zinc-200 uppercase">
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              <span>{locale === 'vi' ? 'Danh Mục Mô Hình' : 'Registered Models'} ({models.length})</span>
            </div>
            <button
              onClick={fetchModels}
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
            ) : models.length === 0 ? (
              <div className="p-8 text-center text-xs text-zinc-500 italic">
                No registered models in catalog.
              </div>
            ) : (
              models.map((m) => {
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
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-300">
                        {m.total_versions} VERSIONS
                      </span>
                    </div>
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

        {/* Right Column: Active Model Inspection, Drift & Governance Workflow (8 Cols) */}
        <div className="lg:col-span-8 flex flex-col gap-4 overflow-y-auto pr-1">
          {/* Top Panel: Model Version History & Promotion Workflow */}
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

          {/* Bottom Panel: Statistical Drift & Performance Degradation Detector */}
          <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-amber-400" />
                <h2 className="text-xs font-bold text-zinc-100 uppercase">
                  {locale === 'vi' ? 'Giám Sát Sai Lệch Mô Hình (Drift Detector)' : 'Model Concept & Performance Drift'}
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
