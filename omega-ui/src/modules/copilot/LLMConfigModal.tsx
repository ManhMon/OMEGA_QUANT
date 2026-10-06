import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  Settings,
  Key,
  Eye,
  EyeOff,
  Activity,
  Check,
  AlertCircle,
  Copy,
  Save,
  Sparkles,
  Cpu,
  Globe,
  TrendingUp,
  CheckCircle2,
  RefreshCw,
  Search,
  ChevronDown,
  Zap,
  Database
} from 'lucide-react';
import { useLLMConfig } from '../../hooks/useLLMConfig';
import { useTranslation } from '../../i18n';
import { LLMProfileItem, MultiProfileLLMConfigPayload, LLMModelItem } from '../../api/client';

export const containModalFocus = (event: React.KeyboardEvent<HTMLDialogElement>) => {
  if (event.key !== 'Tab') return;
  const dialog = event.currentTarget;
  const controls = Array.from(dialog.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]'))
    .filter((element) => element.tabIndex >= 0 && !element.matches(':disabled') && element.getClientRects().length > 0);
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (!first || !dialog.contains(document.activeElement) ||
      (event.shiftKey ? document.activeElement === first : document.activeElement === last)) {
    event.preventDefault();
    (event.shiftKey ? last : first)?.focus();
    if (!first) dialog.focus();
  }
};

interface LLMConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabKey = 'global_profile' | 'alpha_quant' | 'news_sentiment' | 'macro_micro';

// Curated instant offline model definitions per provider to prevent network lag on tab switch
const CURATED_LOCAL_MODELS: Record<string, LLMModelItem[]> = {
  openai: [
    { id: 'gpt-4o', name: 'GPT-4o Omnimodal', category: 'FRONTIER', context_window: 128000, description: 'Flagship multivariant model for cross-domain synthesis and reasonings' },
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini Fast', category: 'FAST', context_window: 128000, description: 'High-speed, cost-effective model for high-throughput news sentiment analysis' },
    { id: 'o1', name: 'OpenAI o1 Reasoning', category: 'INSTITUTIONAL', context_window: 128000, description: 'Deep chain-of-thought model for complex quantitative proofs and formulations' },
    { id: 'o3-mini', name: 'OpenAI o3 Mini', category: 'INSTITUTIONAL', context_window: 128000, description: 'STEM/Math-optimized reasoning model for formula synthesis & verification' },
    { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', category: 'LEGACY', context_window: 128000, description: 'Legacy GPT-4 Turbo preview' },
  ],
  anthropic: [
    { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet v2', category: 'FRONTIER', context_window: 200000, description: 'Top-tier code and AST mathematical formula generation' },
    { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku', category: 'FAST', context_window: 200000, description: 'Ultra-low latency inference for live real-time sentiment stream filtering' },
    { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', category: 'INSTITUTIONAL', context_window: 200000, description: 'Deep financial report extraction and sector contagion analysis' },
  ],
  gemini: [
    { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', category: 'FAST', context_window: 1048576, description: 'Real-time multi-modal streaming and high-speed telemetry reasoning' },
    { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', category: 'INSTITUTIONAL', context_window: 2097152, description: '2M context window for multi-year regulatory filings and historical matrix ingestion' },
    { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', category: 'FAST', context_window: 1048576, description: 'Lightweight fast query answering model' },
  ],
  local: [
    { id: 'deepseek-r1:14b', name: 'DeepSeek R1 Distill 14B', category: 'LOCAL', context_window: 64000, description: 'Local offline quantitative reasoning model via Ollama' },
    { id: 'qwen2.5-coder:14b', name: 'Qwen 2.5 Coder 14B', category: 'LOCAL', context_window: 64000, description: 'Local Python and quant formula synthesis engine' },
    { id: 'llama3.3:70b', name: 'Llama 3.3 70B', category: 'LOCAL', context_window: 128000, description: 'High-capacity local hedge-fund level offline reasoning' },
  ],
  custom: [
    { id: 'custom-quant-model', name: 'Custom Proxy Model', category: 'GENERAL', context_window: 32768, description: 'Custom institutional upstream LLM server' },
  ]
};

export const LLMConfigModal: React.FC<LLMConfigModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const { config, isLoading, isError, saveConfig, isSaving, testProbe, fetchModels, isFetchingModels } = useLLMConfig();

  const [activeTab, setActiveTab] = useState<TabKey>('global_profile');
  const [showApiKey, setShowApiKey] = useState<Record<TabKey, boolean>>({
    global_profile: false,
    alpha_quant: false,
    news_sentiment: false,
    macro_micro: false,
  });

  const modelCatalogRef = useRef<Record<string, {
    models: LLMModelItem[];
    source: string;
    lastFetched?: string;
  }>>({});

  const customProviderCacheRef = useRef<Record<TabKey, { base_url?: string; model?: string }>>({
    global_profile: {},
    alpha_quant: {},
    news_sentiment: {},
    macro_micro: {},
  });

  const mouseDownTargetRef = useRef<EventTarget | null>(null);
  const initialLoadedRef = useRef<boolean>(false);

  const [formData, setFormData] = useState<MultiProfileLLMConfigPayload>({
    global_profile: {
      provider: 'openai',
      model: 'gpt-4o',
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.2,
      max_tokens: 4096,
      timeout_seconds: 30,
      enabled: true,
    },
    alpha_quant: {
      provider: 'openai',
      model: 'gpt-4o-mini',
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.1,
      max_tokens: 4096,
      timeout_seconds: 30,
      enabled: true,
    },
    news_sentiment: {
      provider: 'openai',
      model: 'gpt-4o-mini',
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.2,
      max_tokens: 4096,
      timeout_seconds: 30,
      enabled: true,
    },
    macro_micro: {
      provider: 'openai',
      model: 'gpt-4o',
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.2,
      max_tokens: 4096,
      timeout_seconds: 30,
      enabled: true,
    },
  });

  // Dynamic model catalogs per provider with state sync (preloaded with curated models to eliminate modal lag)
  const [modelCatalog, setModelCatalog] = useState<Record<string, {
    models: LLMModelItem[];
    source: string;
    lastFetched?: string;
  }>>(() => {
    const initial: Record<string, { models: LLMModelItem[]; source: string }> = {};
    Object.keys(CURATED_LOCAL_MODELS).forEach((prov) => {
      initial[prov] = {
        models: CURATED_LOCAL_MODELS[prov],
        source: 'curated_fallback',
      };
    });
    return initial;
  });

  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [modelSearchQuery, setModelSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [pingStatus, setPingStatus] = useState<Record<TabKey, {
    testing: boolean;
    success?: boolean;
    latency_ms?: number;
    message?: string;
  }>>({
    global_profile: { testing: false },
    alpha_quant: { testing: false },
    news_sentiment: { testing: false },
    macro_micro: { testing: false },
  });

  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Reset and sync fresh config on modal reopen, reset local UI state
  useEffect(() => {
    if (isOpen && config && !initialLoadedRef.current) {
      setFormData({
        global_profile: { ...config.global_profile },
        alpha_quant: { ...config.alpha_quant },
        news_sentiment: { ...config.news_sentiment },
        macro_micro: { ...config.macro_micro },
      });
      initialLoadedRef.current = true;
      setIsDropdownOpen(false);
      setModelSearchQuery('');
      setNotification(null);
    }
  }, [isOpen, config]);

  // Reset initialLoadedRef on modal close
  useEffect(() => {
    if (!isOpen) {
      initialLoadedRef.current = false;
    }
  }, [isOpen]);

  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    if (isOpen) dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (isOpen && previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [isOpen, !!config, isError]);

  // Click outside to close combobox dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentProf = formData[activeTab];
  const currentProvider = currentProf.provider || 'openai';

  // Auto-probe provider models if not cached in modelCatalogRef
  useEffect(() => {
    if (isOpen && !modelCatalogRef.current[currentProvider]) {
      handleFetchModels(activeTab, false);
    }
  }, [currentProvider, isOpen, activeTab]);

  const handleFieldChange = (tab: TabKey, field: keyof LLMProfileItem, value: any) => {
    setFormData((prev) => ({
      ...prev,
      [tab]: {
        ...prev[tab],
        [field]: value,
      },
    }));
  };

  const handleProviderChange = (tab: TabKey, newProv: string) => {
    const prevProf = formData[tab];
    if (prevProf.provider === 'custom') {
      customProviderCacheRef.current[tab] = {
        base_url: prevProf.base_url,
        model: prevProf.model,
      };
    }

    let defaultBaseUrl = 'https://api.openai.com/v1';
    let defaultModel = 'gpt-4o';

    if (newProv === 'openai') {
      defaultBaseUrl = 'https://api.openai.com/v1';
      defaultModel = 'gpt-4o';
    } else if (newProv === 'anthropic') {
      defaultBaseUrl = 'https://api.anthropic.com/v1';
      defaultModel = 'claude-3-5-sonnet-20241022';
    } else if (newProv === 'gemini') {
      defaultBaseUrl = 'https://generativelanguage.googleapis.com/v1beta';
      defaultModel = 'gemini-2.0-flash';
    } else if (newProv === 'local') {
      defaultBaseUrl = 'http://localhost:11434/v1';
      defaultModel = 'deepseek-r1:14b';
    } else if (newProv === 'custom') {
      const cached = customProviderCacheRef.current[tab];
      defaultBaseUrl = cached?.base_url ?? 'https://api.openai.com/v1';
      defaultModel = cached?.model ?? 'custom-quant-model';
    }

    setFormData((prev) => ({
      ...prev,
      [tab]: {
        ...prev[tab],
        provider: newProv,
        base_url: defaultBaseUrl,
        model: defaultModel,
      },
    }));
    setIsDropdownOpen(false);
  };

  const toggleShowKey = (tab: TabKey) => {
    setShowApiKey((prev) => ({ ...prev, [tab]: !prev[tab] }));
  };

  const handleFetchModels = async (tab: TabKey, showToast = true) => {
    const prof = formData[tab];
    try {
      const res = await fetchModels({
        provider: prof.provider,
        base_url: prof.base_url || undefined,
        api_key: prof.api_key || undefined,
        profile_key: tab,
        timeout_seconds: 8,
      });

      const catalogEntry = {
        models: res.models,
        source: res.source,
        lastFetched: new Date().toLocaleTimeString(),
      };
      modelCatalogRef.current[prof.provider] = catalogEntry;
      setModelCatalog((prev) => ({
        ...prev,
        [prof.provider]: catalogEntry,
      }));

      if (showToast) {
        setNotification({
          type: res.status === 'success' ? 'success' : 'error',
          message: res.status === 'success'
            ? `${res.models.length} ${t.copilot.modelsFoundCount} (${t.copilot.sourceLive}).`
            : `${res.message} ${t.copilot.sourceCurated}`,
        });
        setTimeout(() => setNotification(null), 3000);
      }
    } catch {
      if (showToast) {
        setNotification({
          type: 'error',
          message: t.copilot.modelCatalogFailed,
        });
        setTimeout(() => setNotification(null), 4000);
      }
    }
  };

  const handleTestConnection = async (tab: TabKey) => {
    const prof = formData[tab];
    setPingStatus((prev) => ({
      ...prev,
      [tab]: { testing: true },
    }));

    try {
      const res = await testProbe({
        profile_key: tab,
        provider: prof.provider,
        model: prof.model,
        api_key: prof.api_key || undefined,
        base_url: prof.base_url || undefined,
        temperature: prof.temperature,
        timeout_seconds: prof.timeout_seconds,
      });

      const isSuccess = res.status === 'success';
      setPingStatus((prev) => ({
        ...prev,
        [tab]: {
          testing: false,
          success: isSuccess,
          latency_ms: res.latency_ms,
          message: res.message,
        },
      }));
    } catch {
      setPingStatus((prev) => ({
        ...prev,
        [tab]: {
          testing: false,
          success: false,
          message: t.copilot.probeFailed,
        },
      }));
    }
  };

  const handleApplyToAll = () => {
    const src = formData[activeTab];
    setFormData({
      global_profile: { ...src },
      alpha_quant: { ...src },
      news_sentiment: { ...src },
      macro_micro: { ...src },
    });
    setNotification({
      type: 'success',
      message: t.copilot.profilesSynchronized,
    });
    setTimeout(() => setNotification(null), 4000);
  };

  const handleSave = async () => {
    try {
      await saveConfig(formData);
      setNotification({
        type: 'success',
        message: t.copilot.saveSuccess,
      });
      setTimeout(() => {
        setNotification(null);
        onClose();
      }, 1200);
    } catch {
      setNotification({
        type: 'error',
        message: t.copilot.saveFailed,
      });
    }
  };

  const currentPing = pingStatus[activeTab];
  const activeCatalog = modelCatalog[currentProvider]?.models || modelCatalogRef.current[currentProvider]?.models || CURATED_LOCAL_MODELS[currentProvider] || CURATED_LOCAL_MODELS.openai || [];
  const activeCatalogSource = modelCatalog[currentProvider]?.source || modelCatalogRef.current[currentProvider]?.source || 'curated_fallback';

  const filteredModels = useMemo(() => {
    const query = modelSearchQuery.toLowerCase();
    return activeCatalog.filter((m) => {
      const matchSearch = m.id.toLowerCase().includes(query) ||
                          m.name.toLowerCase().includes(query) ||
                          (m.description && m.description.toLowerCase().includes(query));
      const matchCat = selectedCategory === 'ALL' || m.category === selectedCategory;
      return matchSearch && matchCat;
    });
  }, [activeCatalog, modelSearchQuery, selectedCategory]);

  const getCategoryBadgeClass = (category: string) => {
    switch (category) {
      case 'FRONTIER':
        return 'bg-purple-950/80 text-purple-300 border-purple-500/30';
      case 'INSTITUTIONAL':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-500/30';
      case 'FAST':
        return 'bg-cyan-950/80 text-cyan-300 border-cyan-500/30';
      case 'LOCAL':
        return 'bg-amber-950/80 text-amber-300 border-amber-500/30';
      case 'LEGACY':
        return 'bg-zinc-800 text-zinc-400 border-zinc-700';
      default:
        return 'bg-zinc-900 text-zinc-300 border-zinc-700';
    }
  };

  if (!isOpen) return null;
  if (!config || isError) return (
    <dialog ref={dialogRef} onKeyDown={containModalFocus} aria-modal="true" aria-label={t.copilot.configModalTitle}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="bg-zinc-950 text-zinc-100 p-4 backdrop:bg-black/75">
      <p role="alert">{t.common.integrationUnavailable}</p>
      <button type="button" autoFocus onClick={onClose}>{t.common.cancel}</button>
    </dialog>
  );

  return (
    <dialog ref={dialogRef} onKeyDown={containModalFocus} aria-modal="true" aria-label={t.copilot.configModalTitle}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onMouseDown={(e) => {
        mouseDownTargetRef.current = e.target;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && mouseDownTargetRef.current === e.currentTarget) {
          onClose();
        }
      }}
      className="fixed inset-0 m-0 h-screen max-h-screen w-screen max-w-none z-50 flex items-center justify-center bg-transparent text-zinc-100 backdrop:bg-black/75 backdrop:backdrop-blur-sm p-4 animate-in fade-in duration-200"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-3xl bg-zinc-950 border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-zinc-900/80">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Settings className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-zinc-100 font-mono">
                  {t.copilot.configModalTitle}
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-500/30">
                  SOD MASKED
                </span>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  DYNAMIC CATALOG
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                {t.copilot.configModalSubtitle}
              </p>
            </div>
          </div>

          <button
            autoFocus aria-label={t.common.close}
            onClick={onClose}
            className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 4 Modular Profile Tabs */}
        <div className="grid grid-cols-4 border-b border-white/10 bg-zinc-900/40 p-1.5 gap-1.5">
          <button
            key="tab_global_profile"
            onClick={() => { setActiveTab('global_profile'); setIsDropdownOpen(false); }}
            className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'global_profile'
                ? 'bg-zinc-800 text-emerald-400 font-bold border border-emerald-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            <span className="truncate">{t.copilot.tabGlobal}</span>
          </button>

          <button
            key="tab_alpha_quant"
            onClick={() => { setActiveTab('alpha_quant'); setIsDropdownOpen(false); }}
            className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'alpha_quant'
                ? 'bg-zinc-800 text-purple-400 font-bold border border-purple-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span className="truncate">{t.copilot.tabAlpha}</span>
          </button>

          <button
            key="tab_news_sentiment"
            onClick={() => { setActiveTab('news_sentiment'); setIsDropdownOpen(false); }}
            className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'news_sentiment'
                ? 'bg-zinc-800 text-cyan-400 font-bold border border-cyan-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="truncate">{t.copilot.tabNews}</span>
          </button>

          <button
            key="tab_macro_micro"
            onClick={() => { setActiveTab('macro_micro'); setIsDropdownOpen(false); }}
            className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-mono transition-colors ${
              activeTab === 'macro_micro'
                ? 'bg-zinc-800 text-amber-400 font-bold border border-amber-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span className="truncate">{t.copilot.tabMacro}</span>
          </button>
        </div>

        {/* Modal Body Form */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4 font-sans text-xs">
          {notification && (
            <div className={`p-3 rounded-xl flex items-center gap-2 font-mono text-xs ${
              notification.type === 'success' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40' : 'bg-red-950/80 text-red-300 border border-red-500/40'
            }`}>
              {notification.type === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> : <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />}
              <span>{notification.message}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Provider Selection */}
            <div className="space-y-1.5">
              <label className="text-zinc-400 font-mono flex items-center justify-between">
                <span>{t.copilot.providerLabel}</span>
                <span className="text-[10px] text-zinc-500">openai / anthropic / gemini / local</span>
              </label>
              <select
                value={currentProf.provider}
                onChange={(e) => handleProviderChange(activeTab, e.target.value)}
                className="w-full bg-zinc-900 border border-white/10 rounded-lg px-3 py-2 text-zinc-100 focus:outline-none focus:border-cyan-500 font-mono text-xs"
              >
                <option value="openai">OpenAI (GPT-4o, o1, o3-mini)</option>
                <option value="anthropic">Anthropic (Claude 3.5 Sonnet / Haiku)</option>
                <option value="gemini">Google Gemini (Flash 2.0, Pro 1.5)</option>
                <option value="local">Local Ollama / vLLM (Qwen, DeepSeek)</option>
                <option value="custom">Custom Proxy Endpoint</option>
              </select>
            </div>

            {/* Upgraded Searchable Combobox Model Dropdown with Live Fetch Button */}
            <div className="space-y-1.5 relative" ref={dropdownRef}>
              <div className="flex items-center justify-between">
                <label className="text-zinc-400 font-mono flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                  <span>{t.copilot.modelLabel}</span>
                </label>
                <button
                  type="button"
                  onClick={() => handleFetchModels(activeTab, true)}
                  disabled={isFetchingModels}
                  className="flex items-center gap-1 text-[10px] font-mono text-cyan-400 hover:text-cyan-300 disabled:opacity-50"
                  title="Discover models from endpoint"
                >
                  <RefreshCw className={`w-3 h-3 ${isFetchingModels ? 'animate-spin' : ''}`} />
                  <span>{isFetchingModels ? t.copilot.fetchingModelsBtn : t.copilot.fetchModelsBtn}</span>
                </button>
              </div>

              {/* Input container with combobox toggle */}
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={currentProf.model}
                  onChange={(e) => {
                    handleFieldChange(activeTab, 'model', e.target.value);
                  }}
                  onFocus={() => setIsDropdownOpen(true)}
                  placeholder="e.g. gpt-4o, claude-3-5-sonnet-20241022"
                  className="w-full bg-zinc-900 border border-white/10 rounded-lg pl-3 pr-8 py-2 text-zinc-100 focus:outline-none focus:border-cyan-500 font-mono text-xs"
                />
                <button
                  type="button"
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  className="absolute right-2 text-zinc-400 hover:text-zinc-200"
                >
                  <ChevronDown className={`w-4 h-4 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
                </button>
              </div>

              {/* Combobox Dropdown Menu */}
              {isDropdownOpen && (
                <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-zinc-900 border border-white/15 rounded-xl shadow-2xl overflow-hidden p-2 space-y-2 max-h-72 flex flex-col">
                  {/* Search Bar within Dropdown */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-zinc-400" />
                    <input
                      type="text"
                      value={modelSearchQuery}
                      onChange={(e) => setModelSearchQuery(e.target.value)}
                      placeholder={t.copilot.searchModelPlaceholder}
                      className="w-full bg-zinc-950 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-zinc-200 font-mono text-[11px] focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  {/* Category Filter Pills */}
                  <div className="flex items-center gap-1 overflow-x-auto pb-1 text-[10px] font-mono scrollbar-none">
                    {['ALL', 'FRONTIER', 'INSTITUTIONAL', 'FAST', 'LOCAL'].map((cat) => (
                      <button
                        key={`cat_filter_${cat}`}
                        type="button"
                        onClick={() => setSelectedCategory(cat)}
                        className={`px-2 py-0.5 rounded-md transition-colors ${
                          selectedCategory === cat
                            ? 'bg-cyan-600 text-white font-bold'
                            : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                        }`}
                      >
                        {cat === 'ALL' ? t.copilot.categoryAll :
                         cat === 'FRONTIER' ? t.copilot.categoryFrontier :
                         cat === 'INSTITUTIONAL' ? t.copilot.categoryInstitutional :
                         cat === 'FAST' ? t.copilot.categoryFast : t.copilot.categoryLocal}
                      </button>
                    ))}
                  </div>

                  {/* Model Items List */}
                  <div className="overflow-y-auto flex-1 space-y-1 pr-1">
                    {filteredModels.length === 0 ? (
                      <div className="p-3 text-center text-zinc-500 font-mono text-[11px]">
                        {t.copilot.customModelInputPrompt}
                      </div>
                    ) : (
                      filteredModels.map((m) => (
                        <button
                          key={`m_${currentProvider}_${m.id}_${m.category}`}
                          type="button"
                          onClick={() => {
                            handleFieldChange(activeTab, 'model', m.id);
                            setIsDropdownOpen(false);
                          }}
                          className={`w-full text-left p-2 rounded-lg transition-colors flex items-start justify-between gap-2 ${
                            currentProf.model === m.id
                              ? 'bg-cyan-950/60 border border-cyan-500/40 text-cyan-200'
                              : 'bg-zinc-950/40 hover:bg-zinc-800/80 text-zinc-300'
                          }`}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono font-bold text-xs truncate">{m.id}</span>
                              <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded border ${getCategoryBadgeClass(m.category)}`}>
                                {m.category}
                              </span>
                            </div>
                            {m.description && (
                              <p className="text-[10px] text-zinc-400 mt-0.5 line-clamp-1">{m.description}</p>
                            )}
                          </div>
                          {currentProf.model === m.id && (
                            <Check className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
                          )}
                        </button>
                      ))
                    )}
                  </div>

                  {/* Catalog Source Indicator */}
                  <div className="pt-1 border-t border-white/5 flex items-center justify-between text-[10px] font-mono text-zinc-500">
                    <span>{filteredModels.length} models</span>
                    <span className="text-cyan-400/80">
                      {activeCatalogSource === 'live_provider' ? t.copilot.sourceLive : t.copilot.sourceCurated}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Quick Categorized Model Chips Across All Profiles */}
          <div className="space-y-1.5 pt-1">
            <label className="text-[11px] font-mono text-zinc-400 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span>{t.copilot.quickChips}:</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {activeCatalog.slice(0, 5).map((m) => (
                <button
                  key={`m_${currentProvider}_${m.id}_${m.category}`}
                  type="button"
                  onClick={() => handleFieldChange(activeTab, 'model', m.id)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-colors border flex items-center gap-1.5 ${
                    currentProf.model === m.id
                      ? 'bg-cyan-900/60 border-cyan-500 text-cyan-200 font-bold shadow-sm shadow-cyan-500/20'
                      : 'bg-zinc-900/80 border-white/10 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                  }`}
                >
                  <span>{m.id}</span>
                  <span className={`text-[8px] px-1 py-0.2 rounded border ${getCategoryBadgeClass(m.category)}`}>
                    {m.category}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* API Key Input with Mask Toggle */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-zinc-400 font-mono flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-cyan-400" />
                <span>{t.copilot.apiKeyLabel}</span>
              </label>
              <span className="text-[10px] font-mono text-emerald-400">
                {currentProf.has_key || currentProf.api_key ? t.copilot.hasKeySet : t.copilot.noKeySet}
              </span>
            </div>
            <div className="relative flex items-center">
              <input
                type={showApiKey[activeTab] ? 'text' : 'password'}
                value={currentProf.api_key || ''}
                onChange={(e) => handleFieldChange(activeTab, 'api_key', e.target.value)}
                placeholder={t.copilot.apiKeyPlaceholder}
                className="w-full bg-zinc-900 border border-white/10 rounded-lg pl-3 pr-10 py-2 text-zinc-100 focus:outline-none focus:border-cyan-500 font-mono text-xs tracking-wider"
              />
              <button
                type="button"
                onClick={() => toggleShowKey(activeTab)}
                className="absolute right-3 text-zinc-400 hover:text-zinc-200 transition-colors"
                title={showApiKey[activeTab] ? 'Hide API Key' : 'Show API Key'}
              >
                {showApiKey[activeTab] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Base URL */}
          <div className="space-y-1.5">
            <label className="text-zinc-400 font-mono">
              {t.copilot.baseUrlLabel}
            </label>
            <input
              type="text"
              value={currentProf.base_url || ''}
              onChange={(e) => handleFieldChange(activeTab, 'base_url', e.target.value)}
              placeholder={t.copilot.baseUrlPlaceholder}
              className="w-full bg-zinc-900 border border-white/10 rounded-lg px-3 py-2 text-zinc-100 focus:outline-none focus:border-cyan-500 font-mono text-xs"
            />
          </div>

          {/* Advanced Sliders & Values */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            {/* Temperature */}
            <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 space-y-2">
              <div className="flex justify-between text-zinc-400 font-mono">
                <span>{t.copilot.temperatureLabel}</span>
                <span className="text-emerald-400 font-bold">{currentProf.temperature}</span>
              </div>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={currentProf.temperature}
                onChange={(e) => handleFieldChange(activeTab, 'temperature', parseFloat(e.target.value))}
                className="w-full accent-emerald-500 cursor-pointer"
              />
            </div>

            {/* Max Tokens */}
            <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 space-y-2">
              <div className="flex justify-between text-zinc-400 font-mono">
                <span>{t.copilot.maxTokensLabel}</span>
                <span className="text-cyan-400 font-bold">{currentProf.max_tokens}</span>
              </div>
              <input
                type="number"
                min="128"
                max="32768"
                step="256"
                value={currentProf.max_tokens}
                onChange={(e) => handleFieldChange(activeTab, 'max_tokens', parseInt(e.target.value, 10))}
                className="w-full bg-zinc-900 border border-white/10 rounded-md px-2 py-1 text-zinc-100 font-mono text-xs"
              />
            </div>

            {/* Timeout */}
            <div className="p-3 rounded-xl bg-zinc-900/60 border border-white/5 space-y-2">
              <div className="flex justify-between text-zinc-400 font-mono">
                <span>{t.copilot.timeoutLabel}</span>
                <span className="text-amber-400 font-bold">{currentProf.timeout_seconds}s</span>
              </div>
              <input
                type="number"
                min="5"
                max="180"
                step="5"
                value={currentProf.timeout_seconds}
                onChange={(e) => handleFieldChange(activeTab, 'timeout_seconds', parseInt(e.target.value, 10))}
                className="w-full bg-zinc-900 border border-white/10 rounded-md px-2 py-1 text-zinc-100 font-mono text-xs"
              />
            </div>
          </div>

          {/* Test Probe Live Result Badge */}
          {currentPing.message && (
            <div className={`p-3 rounded-xl border flex items-center justify-between font-mono text-xs ${
              currentPing.success
                ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300'
                : 'bg-red-950/60 border-red-500/40 text-red-300'
            }`}>
              <div className="flex items-center gap-2">
                {currentPing.success ? <Check className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4 text-red-400" />}
                <span>{currentPing.message}</span>
              </div>
              {currentPing.latency_ms !== undefined && (
                <span className="px-2 py-0.5 rounded bg-emerald-900/80 text-emerald-300 font-bold text-[10px]">
                  {currentPing.latency_ms} ms
                </span>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-white/10 bg-zinc-900/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleTestConnection(activeTab)}
              disabled={currentPing.testing || isLoading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-cyan-300 border border-cyan-500/30 text-xs font-mono font-semibold transition-colors disabled:opacity-50"
            >
              <Activity className={`w-3.5 h-3.5 ${currentPing.testing ? 'animate-spin' : ''}`} />
              <span>{currentPing.testing ? t.copilot.testingConnectionBtn : t.copilot.testConnectionBtn}</span>
            </button>

            <button
              onClick={handleApplyToAll}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-white/10 text-xs font-mono transition-colors"
              title="Copy current profile configuration to all 4 tabs"
            >
              <Copy className="w-3.5 h-3.5 text-zinc-400" />
              <span>{t.copilot.applyToAllBtn}</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono transition-colors"
            >
              {t.common.cancel}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-mono font-bold transition-colors shadow-md shadow-emerald-600/20"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{isSaving ? t.copilot.savingConfigBtn : t.copilot.saveConfigBtn}</span>
            </button>
          </div>
        </div>
      </div>
    </dialog>
  );
};
