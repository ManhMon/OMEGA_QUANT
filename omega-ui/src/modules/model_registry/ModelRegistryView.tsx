import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Layers,
  RefreshCw,
  RotateCcw,
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
  ResourceGovernorStateResponse,
  ModelCategory
} from '../../api/advancedQuant';
import { DriftMonitorPanel, ConceptDriftPanel, getRegistryEvidence, registryIdentity, registryObject, registryNumber, registryTime } from './DriftMonitorPanel';
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

const MODEL_ID = /^[A-Za-z0-9_-]{1,128}$/;
const MODEL_VERSION = /^v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}$/;
const metricValue = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12 ? value : '—';

export function validateModelCatalog(value: unknown) {
  const data = registryObject(value);
  if (data.status !== 'success' || !Array.isArray(data.models) || data.models.length > 4096 || data.count !== data.models.length) throw new Error('Invalid model catalog');
  const seen = new Set<string>();
  data.models.forEach((raw: unknown) => {
    const model = registryObject(raw);
    if (typeof model.model_name !== 'string' || !MODEL_ID.test(model.model_name) || seen.has(model.model_name)) throw new Error('Invalid model identity');
    seen.add(model.model_name);
    if (model.category != null && !TAXONOMY_CATEGORIES.some((cat) => cat.id !== 'ALL' && cat.id === model.category)) throw new Error('Invalid model category');
    ['framework', 'description', 'source_path', 'implementation_symbol'].forEach((field) => {
      if (model[field] != null && (typeof model[field] !== 'string' || model[field].length > 4096)) throw new Error('Invalid model metadata');
    });
    if (!Number.isInteger(registryNumber(model.total_versions, 0, 4096))) throw new Error('Invalid version count');
    Object.values(registryObject(model.active_versions)).forEach((version) => { if (version !== null && (typeof version !== 'string' || !MODEL_VERSION.test(version))) throw new Error('Invalid active version'); });
    if (model.latest_version != null && (typeof model.latest_version !== 'string' || !MODEL_VERSION.test(model.latest_version))) throw new Error('Invalid latest version');
    if (model.last_updated != null) registryTime(model.last_updated);
  });
  if (data.selected_category != null && !TAXONOMY_CATEGORIES.some((cat) => cat.id !== 'ALL' && cat.id === data.selected_category)) throw new Error('Invalid selected category');
  if (data.categories != null && (!Array.isArray(data.categories) || new Set(data.categories).size !== data.categories.length || data.categories.some((category: unknown) => !TAXONOMY_CATEGORIES.some((cat) => cat.id !== 'ALL' && cat.id === category)))) throw new Error('Invalid taxonomy');
  if (data.category_counts != null) Object.entries(registryObject(data.category_counts)).forEach(([category, count]) => {
    if (!TAXONOMY_CATEGORIES.some((cat) => cat.id !== 'ALL' && cat.id === category) || !Number.isInteger(registryNumber(count, 0, 4096))) throw new Error('Invalid category count');
  });
  return data as unknown as { models: ModelSummaryItem[]; category_counts?: Record<string, number>; selected_category?: string | null };
}

export function validateModelVersions(value: unknown, model: string): ModelVersionItem[] {
  const data = registryObject(value);
  if (data.status !== 'success' || data.model_name !== model || !Array.isArray(data.versions) || data.versions.length > 4096) throw new Error('Invalid version response');
  const seen = new Set<string>();
  data.versions.forEach((raw: unknown) => {
    const item = registryObject(raw);
    if (typeof item.version !== 'string' || !MODEL_VERSION.test(item.version) || seen.has(item.version) || !['STAGING', 'VALIDATED', 'PRODUCTION', 'ARCHIVED', 'DEPRECATED'].includes(item.status)) throw new Error('Invalid version');
    seen.add(item.version); registryTime(item.registered_at); registryObject(item.metadata);
  });
  return data.versions;
}

interface LineageNode {
  version: string;
  parent_versions: string[];
  dataset_snapshot: { dataset_id: string; version: string; content_hash: string; as_of: string; available_at: string } | null;
  training_run: { run_id: string; trained_at: string } | null;
  git_commit: string | null;
  deployment_receipt: { receipt_id: string; version: string; deployed_at: string } | null;
}
interface LineageEvidence { nodes: LineageNode[]; evidence_status: 'recorded' | 'incomplete' }

export function validateModelLineage(value: unknown, model: string, version: string): LineageEvidence {
  const data = registryIdentity(value, model, version);
  if (!['recorded', 'incomplete'].includes(data.evidence_status) || !Array.isArray(data.nodes) || !data.nodes.length || data.nodes.length > 4096) throw new Error('Invalid lineage nodes');
  const nodes = new Map<string, LineageNode>();
  data.nodes.forEach((raw: unknown) => {
    const node = registryObject(raw);
    if (typeof node.version !== 'string' || !MODEL_VERSION.test(node.version) || nodes.has(node.version) || !Array.isArray(node.parent_versions) || node.parent_versions.length > 128 || new Set(node.parent_versions).size !== node.parent_versions.length || node.parent_versions.some((parent: unknown) => typeof parent !== 'string' || !MODEL_VERSION.test(parent) || parent === node.version)) throw new Error('Invalid lineage edges');
    if (node.git_commit !== null && (typeof node.git_commit !== 'string' || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(node.git_commit))) throw new Error('Invalid lineage commit');
    if (node.dataset_snapshot !== null) {
      const snapshot = registryObject(node.dataset_snapshot);
      if (![snapshot.dataset_id, snapshot.version].every((id) => typeof id === 'string' && MODEL_ID.test(id)) || typeof snapshot.content_hash !== 'string' || !/^[0-9a-f]{64}$/.test(snapshot.content_hash) || registryTime(snapshot.as_of) > registryTime(snapshot.available_at)) throw new Error('Invalid dataset snapshot');
    }
    if (node.training_run !== null) {
      const run = registryObject(node.training_run);
      if (typeof run.run_id !== 'string' || !MODEL_ID.test(run.run_id)) throw new Error('Invalid training run');
      const trained = registryTime(run.trained_at);
      if (node.dataset_snapshot && registryTime(node.dataset_snapshot.available_at) > trained) throw new Error('Dataset unavailable at training');
    }
    if (node.deployment_receipt !== null) {
      const receipt = registryObject(node.deployment_receipt);
      if (typeof receipt.receipt_id !== 'string' || !MODEL_ID.test(receipt.receipt_id) || receipt.version !== node.version) throw new Error('Invalid deployment receipt');
      const deployed = registryTime(receipt.deployed_at);
      if (node.training_run && registryTime(node.training_run.trained_at) > deployed) throw new Error('Deployment precedes training');
    }
    [node.dataset_snapshot?.available_at, node.training_run?.trained_at, node.deployment_receipt?.deployed_at].forEach((time) => {
      if (time != null && registryTime(time) > Date.now()) throw new Error('Future lineage evidence');
    });
    nodes.set(node.version, node as LineageNode);
  });
  const visited = new Set<string>(), active = new Set<string>();
  // Iterative traversal bounds stack use for deep recorded lineage.
  if (!nodes.has(version)) throw new Error('Missing selected lineage version');
  const stack = [...nodes.keys()].map((nodeVersion) => ({ version: nodeVersion, exit: false }));
  while (stack.length) {
    const frame = stack.pop()!;
    if (frame.exit) { active.delete(frame.version); visited.add(frame.version); continue; }
    if (active.has(frame.version)) throw new Error('Cyclic lineage');
    if (visited.has(frame.version)) continue;
    const node = nodes.get(frame.version);
    if (!node) throw new Error('Missing lineage parent');
    active.add(frame.version); stack.push({ version: frame.version, exit: true });
    node.parent_versions.forEach((parent) => stack.push({ version: parent, exit: false }));
  }
  const complete = data.nodes.every((node: LineageNode) => node.dataset_snapshot && node.training_run && node.git_commit && node.deployment_receipt);
  if ((data.evidence_status === 'recorded') !== complete) throw new Error('Invalid lineage completeness');
  return data as unknown as LineageEvidence;
}

const ModelLineagePanel: React.FC<{ modelName: string; version: string | null; refreshKey: number }> = ({ modelName, version, refreshKey }) => {
  const key = `${modelName}/${version}/${refreshKey}`;
  const [state, setState] = useState<{ key: string; data?: LineageEvidence; error?: string }>({ key: '' });
  useEffect(() => {
    const controller = new AbortController();
    if (modelName && version) {
      setState({ key });
      getRegistryEvidence(modelName, version, 'lineage', controller.signal)
        .then((raw) => validateModelLineage(raw, modelName, version))
        .then((data) => { if (!controller.signal.aborted) setState({ key, data }); })
        .catch((error) => { if (!controller.signal.aborted) setState({ key, error: error.message }); });
    }
    return () => controller.abort();
  }, [modelName, version, refreshKey, key]);
  const data = state.key === key ? state.data : undefined;
  return <section aria-label="Model lineage tree" className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 text-sm text-zinc-200 space-y-3">
    <h2 className="font-bold">Model lineage tree • {version || 'No version selected'}</h2>
    <p>Registry-recorded evidence, unverified. Automated retrain and deploy disabled.</p>
    {!version ? <p role="status">Select a registered version to inspect lineage.</p> : !data ? <p role={state.error && state.key === key ? 'alert' : 'status'}>{state.key === key && state.error ? `Lineage unavailable: ${state.error}` : 'Loading lineage...'}</p> : <>
      <p>Evidence: {data.evidence_status}</p>
      <ul aria-label="Version ancestry" className="space-y-3">{data.nodes.map((node) => <li key={node.version} className="border-l-2 border-zinc-600 pl-3 break-words">
        <strong>{node.version}</strong><p>Parents: {node.parent_versions.join(', ') || 'Root'}</p>
        <details><summary className="cursor-pointer focus-visible:outline focus-visible:outline-2">Dataset, training, commit, deployment evidence</summary>
          <dl className="space-y-1 pt-2"><dt>Dataset snapshot</dt><dd>{node.dataset_snapshot ? `${node.dataset_snapshot.dataset_id} / ${node.dataset_snapshot.version} • as of ${node.dataset_snapshot.as_of} • available ${node.dataset_snapshot.available_at} • SHA-256 ${node.dataset_snapshot.content_hash}` : 'Not recorded'}</dd><dt>Training run</dt><dd>{node.training_run ? `${node.training_run.run_id} • ${node.training_run.trained_at}` : 'Not recorded'}</dd><dt>Git commit</dt><dd>{node.git_commit || 'Not recorded'}</dd><dt>Deployment receipt</dt><dd>{node.deployment_receipt ? `${node.deployment_receipt.receipt_id} • ${node.deployment_receipt.deployed_at}` : 'Not recorded'}</dd></dl>
        </details>
      </li>)}</ul>
    </>}
  </section>;
};

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
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [evidenceRefresh, setEvidenceRefresh] = useState(0);
  const [versionRecords, setVersions] = useState<ModelVersionItem[]>([]);
  const [versionsModel, setVersionsModel] = useState('');
  const versions = versionsModel === selectedModel ? versionRecords : [];
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const inspectionVersion = versions.some((record) => record.version === selectedVersion) ? selectedVersion : null;
  const [governorState, setGovernorState] = useState<ResourceGovernorStateResponse | null>(null);
  const [serverCategoryCounts, setServerCategoryCounts] = useState<Record<string, number> | null>(null);

  const [isLoadingModels, setIsLoadingModels] = useState<boolean>(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [isUpdatingGovernor, setIsUpdatingGovernor] = useState<boolean>(false);

  // Modal states
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState<boolean>(false);
  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState<boolean>(false);
  const [targetPromoteStatus, setTargetPromoteStatus] = useState<'VALIDATED' | 'PRODUCTION'>('VALIDATED');
  const [targetRollbackVersion, setTargetRollbackVersion] = useState<string>('');

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
      setCatalogError(null);
      setModels([]);
      setServerCategoryCounts(null);
      const res = validateModelCatalog(await advancedQuantApi.getModelList(queryCat, controller.signal));
      if (queryCat && (res.selected_category != null && res.selected_category !== queryCat || res.models.some((model) => model.category !== queryCat))) throw new Error('Catalog category mismatch');

      // Eliminate race condition: only commit if this request is latest and not aborted
      if (requestSeq === modelsRequestSeqRef.current && !controller.signal.aborted) {
        setModels(res.models);
        setServerCategoryCounts(res.category_counts || null);
        setSelectedModel((prev) => res.models.some((m) => m.model_name === prev) ? prev : res.models[0]?.model_name || '');
      }
    } catch (err: any) {
      if (controller.signal.aborted || requestSeq !== modelsRequestSeqRef.current) {
        return;
      }
      setCatalogError('Model catalog unavailable or invalid. Refresh to retry.');
      setSelectedModel('');
      addToast({ type: 'error', title: 'Model Registry Fetch Failed', message: 'Model catalog unavailable or invalid' });
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
    setIsPromoteModalOpen(false);
    setIsRollbackModalOpen(false);
    setDetailError(null);
    setEvidenceRefresh((value) => value + 1);
    setIsLoadingDetails(Boolean(modelName));
    if (!modelName) return;

    debounceTimerRef.current = setTimeout(() => {
      const controller = new AbortController();
      detailAbortControllerRef.current = controller;

      rafRef.current = requestAnimationFrame(async () => {
        try {
          const versRes = await advancedQuantApi.getModelVersions(modelName, controller.signal);
          const records = validateModelVersions(versRes, modelName);
          if (!controller.signal.aborted) {
            setVersions(records);
            setVersionsModel(modelName);
            setSelectedVersion(records.find((record) => record.version === versRes.active_versions?.PRODUCTION)?.version || records[0]?.version || null);
          }
        } catch (err: any) {
          if (!controller.signal.aborted) {
            setDetailError('Model versions unavailable or invalid. Refresh to retry.');
            addToast({ type: 'error', title: 'Model Details Error', message: 'Model versions unavailable or invalid' });
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
    fetchModelDetails(selectedModel);
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
    if (!selectedModel || !inspectionVersion || isLoadingModels || isLoadingDetails) return;
    try {
      const res = await advancedQuantApi.promoteModelVersion(selectedModel, inspectionVersion, {
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
    if (!selectedModel || !versions.some((record) => record.version === targetRollbackVersion) || isLoadingModels || isLoadingDetails) return;
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
        setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || '');
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
    <div className="flex flex-col h-full min-w-0 w-full gap-4 font-mono select-none overflow-y-auto p-1">
      {/* Header Strip & Resource Governor Bar */}
      <div className="p-4 rounded-xl bg-zinc-900/80 border border-white/10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
            <Layers className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
                {locale === 'vi' ? 'Sổ Đăng Ký & Quản Trị Mô Hình' : 'Model Registry & Governance'}
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-semibold">
                UNVERIFIED REGISTRY EVIDENCE
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/30 font-semibold">
                6 TAXONOMY CATEGORIES
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              {locale === 'vi'
                ? 'Danh mục mô hình định lượng động, kiểm tra sai lệch (Drift), thăng cấp 2FA & điều phối tài nguyên'
                : 'Dynamic model catalog, recorded lineage, concept drift, 2FA promotion & resource governor'}
            </p>
          </div>
        </div>

        {/* Dynamic Resource Governor Controls */}
        <div className="flex flex-wrap items-center gap-3 bg-zinc-950/80 p-2.5 rounded-lg border border-white/10 text-xs">
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
        className="flex flex-wrap items-center gap-1.5 p-1 rounded-lg bg-zinc-950/80 border border-white/10 text-xs"
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
            setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || '');
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
              onClick={() => { setSelectedCategory(cat.id); setSelectedModel(''); }}
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
      <div className="min-h-0 lg:flex-1 lg:overflow-hidden">
        {/* SUBTAB 1: REGISTRY (Default Lineage & Models Catalog) */}
        {activeSubTab === 'registry' && (
          <div
            id="model-registry-panel-registry"
            role="tabpanel"
            aria-labelledby="model-registry-tab-registry"
            className="grid min-w-0 grid-cols-1 lg:grid-cols-12 gap-4 lg:h-full lg:overflow-hidden"
          >
            {/* Left Column: Model Catalog List (4 Cols) */}
            <div className="lg:col-span-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col overflow-hidden">
              <div className="p-3 border-b border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold text-zinc-200 uppercase">
                  <Database className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{locale === 'vi' ? 'Mô Hình Định Lượng' : 'Registered Models'} ({filteredModels.length})</span>
                </div>
                <button
                  onClick={() => { fetchModels(selectedCategory); fetchModelDetails(selectedModel); }}
                  className="p-1 rounded hover:bg-white/5 text-zinc-400 hover:text-zinc-200 transition-colors"
                  title="Refresh models"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoadingModels ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                {catalogError ? <p role="alert" className="p-4 text-sm text-zinc-200">{catalogError}</p> : isLoadingModels ? (
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
                      aria-pressed={isSelected}
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
                            {m.category || 'Not recorded'}
                          </span>
                        </div>
                        {m.description && (
                          <p className="text-[11px] text-zinc-400 line-clamp-1">{m.description}</p>
                        )}
                        <div className="flex items-center justify-between text-[11px] text-zinc-400 pt-1 border-t border-white/5">
                          <span>PROD: <strong className="text-emerald-400 font-bold">{prodVer}</strong></span>
                          <span>LATEST: <strong className="text-cyan-400">{m.latest_version || '—'}</strong></span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right Column: Model Inspection & Lineage Table (8 Cols) */}
            <div className="lg:col-span-8 min-w-0 flex flex-col gap-4 lg:overflow-y-auto pr-1">
              <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-white/5">
                  <div className="flex min-w-0 items-center gap-2 break-words">
                    <GitBranch className="w-4 h-4 text-cyan-400" />
                    <h2 className="text-xs font-bold text-zinc-100 uppercase">
                      {selectedModel} • {locale === 'vi' ? 'Lịch Sử Phiên Bản' : 'Version Lineage'}
                    </h2>
                  </div>

                  {/* 2FA Action Buttons */}
                  <div className="flex flex-wrap items-center gap-2">
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
                        setTargetRollbackVersion(versions.find((v) => v.version !== selectedVersion)?.version || '');
                        setIsRollbackModalOpen(true);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 font-bold text-xs flex items-center gap-1.5"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>{locale === 'vi' ? 'Rollback Khẩn Cấp' : 'Rollback (TOTP)'}</span>
                    </button>
                  </div>
                </div>

              {detailError && <p role="alert" className="text-sm text-zinc-200">{detailError}</p>}
              {/* Model Metadata Card */}
                {models.find((m) => m.model_name === selectedModel) && (
                  <div className="p-3 rounded-lg bg-zinc-950/80 border border-white/5 flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Framework:</span>
                      <span className="font-bold text-cyan-300">
                        {models.find((m) => m.model_name === selectedModel)?.framework || 'Not recorded'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Category:</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-mono font-bold ${getCategoryBadge(models.find((m) => m.model_name === selectedModel)?.category)}`}>
                        {models.find((m) => m.model_name === selectedModel)?.category || 'Not recorded'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400">Total Versions:</span>
                      <span className="font-bold text-emerald-400 font-mono">
                        {models.find((m) => m.model_name === selectedModel)?.total_versions ?? 'Not recorded'}
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
                                    className={`cursor-pointer transition-colors ${
                                isSelected ? 'bg-emerald-500/10 text-emerald-300 font-semibold' : 'hover:bg-white/5 text-zinc-300'
                              }`}
                            >
                              <td className="py-2 px-2 font-bold flex items-center gap-1.5">
                                {isSelected && <ChevronRight className="w-3 h-3 text-emerald-400" />}
                                <button type="button" aria-pressed={isSelected} onClick={() => setSelectedVersion(v.version)} className="min-h-11 px-2 focus-visible:outline focus-visible:outline-2">{v.version}</button>
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
                              <td className="py-2 px-2 text-zinc-200">{metricValue(metrics.sharpe)}</td>
                              <td className="py-2 px-2 text-zinc-200">{metricValue(metrics.ic)}</td>
                              <td className="py-2 px-2 text-zinc-200">{metricValue(metrics.turnover)}</td>
                              <td className="py-2 px-2 text-zinc-500 text-[11px]">
                                {v.registered_at.split('T')[0]}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <ModelLineagePanel modelName={selectedModel} version={inspectionVersion} refreshKey={evidenceRefresh} />
              <ConceptDriftPanel modelName={selectedModel} version={inspectionVersion} refreshKey={evidenceRefresh} />
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
            <DriftMonitorPanel onRefresh={() => fetchModelDetails(selectedModel)} />

            <ConceptDriftPanel modelName={selectedModel} version={inspectionVersion} refreshKey={evidenceRefresh} />
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
