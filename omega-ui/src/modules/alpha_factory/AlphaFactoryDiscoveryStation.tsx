import React, { useState, useMemo, useEffect, useRef } from 'react';
import {
  Code,
  Sparkles,
  Dna,
  Play,
  CheckCircle2,
  AlertTriangle,
  Zap,
  TrendingDown,
  Layers,
  Database,
  Filter,
  Search,
  Activity,
  Terminal,
  Compass,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';
import { useAlphaFactory } from '../../hooks/useAlphaFactory';
import { advancedQuantApi, AlphaEvaluationResponse, AlphaDecayProfileResponse } from '../../api/advancedQuant';
import { useTranslation } from '../../i18n';

const PRESET_FORMULAS = [
  { label: 'Momentum 5D Reversal', formula: 'ts_rank(close / delay(close, 5) - 1, 10)' },
  { label: 'Volume Cross Rank', formula: 'cross_rank(volume) * zscore(close - vwap)' },
  { label: 'Volatility Squeeze', formula: '-1 * (stddev(close, 20) / sma(close, 20)) * ts_rank(close, 10)' },
  { label: 'Quality Residual', formula: 'cross_rank(piotroski_f) - cross_rank(pe_ratio)' },
  { label: 'Orderbook Imbalance', formula: 'decay_linear(obi_depth_10, 5) - decay_linear(obi_depth_10, 20)' },
  { label: 'Cash Flow Momentum', formula: 'ts_rank(fcf_yield, 60) * decay_linear(ret_20, 10)' },
  { label: 'Hybrid Quant-LLM Fusion', formula: '0.6 * ts_rank(close / delay(close, 10), 20) + 0.4 * zscore(llm_sentiment_score, 10)' },
  { label: 'Vietstock Sentiment Delta', formula: 'decay_linear(vsi_sentiment_delta, 5) * cross_rank(volume)' },
];

const CATEGORIES = ['ALL', 'MOMENTUM', 'REVERSAL', 'VOLATILITY', 'QUALITY', 'VALUE', 'MICROSTRUCTURE', 'LIQUIDITY', 'HYBRID', 'LLM_SENTIMENT'];
const STATUSES = ['ALL', 'ACTIVE', 'CANDIDATE', 'DECAYED', 'INCUBATING'];

export const AlphaFactoryDiscoveryStation: React.FC = () => {
  const {
    expression,
    setExpression,
    selectedCategory,
    setSelectedCategory,
    selectedStatus,
    setSelectedStatus,
    searchQuery,
    setSearchQuery,
    selectedAlphaId,
    setSelectedAlphaId,
    arsenalSignals,
    totalArsenalCount,
    isArsenalLoading,
    discoveryState,
    isDiscovering,
    handleStartDiscovery,
  } = useAlphaFactory();

  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'AST_STUDIO' | 'ARSENAL_703' | 'GENETIC_EVOLUTION'>('AST_STUDIO');
  const [generations, setGenerations] = useState<number>(10);
  const [popSize, setPopSize] = useState<number>(50);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [localEvalResult, setLocalEvalResult] = useState<AlphaEvaluationResponse | null>(null);
  const [isLocalEvaluating, setIsLocalEvaluating] = useState<boolean>(false);
  const [localDecayProfile, setLocalDecayProfile] = useState<AlphaDecayProfileResponse | null>(null);
  const [isLocalDecayLoading, setIsLocalDecayLoading] = useState<boolean>(false);

  const pageSize = 50;
  const abortControllerRef = useRef<AbortController | null>(null);
  const rafIdRef = useRef<number | null>(null);

  // Debounced AST formula auto-evaluator & Decay fetcher with setData(null) clearing & RAF
  useEffect(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLocalDecayProfile(null);
    if (selectedAlphaId) {
      setIsLocalDecayLoading(true);
      const timer = setTimeout(async () => {
        try {
          const profile = await advancedQuantApi.getAlphaDecayProfile(selectedAlphaId, controller.signal);
          if (!controller.signal.aborted) {
            if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
            rafIdRef.current = requestAnimationFrame(() => {
              setLocalDecayProfile(profile);
              setIsLocalDecayLoading(false);
            });
          }
        } catch (err) {
          if (!controller.signal.aborted) {
            setIsLocalDecayLoading(false);
          }
        }
      }, 500);

      return () => {
        clearTimeout(timer);
        controller.abort();
        if (rafIdRef.current) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
        }
      };
    }
  }, [selectedAlphaId]);

  const handleEvaluateLocal = async () => {
    if (!expression.trim()) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLocalEvaluating(true);
    setLocalEvalResult(null);
    try {
      const res = await advancedQuantApi.evaluateAlphaAst({
        expression: expression.trim(),
        universe: 'VN703',
      }, controller.signal);
      if (!controller.signal.aborted) {
        if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = requestAnimationFrame(() => {
          setLocalEvalResult(res);
          setIsLocalEvaluating(false);
        });
      }
    } catch (err: unknown) {
      if (!controller.signal.aborted) {
        setIsLocalEvaluating(false);
        setLocalEvalResult({
          status: 'error',
          expression,
          is_valid: false,
          ast_type: 'Unknown',
          ic_estimate: 0,
          ir_estimate: 0,
          turnover_estimate_pct: 0,
          complexity_score: 1,
          error: err instanceof Error ? err.message : 'Evaluation error',
        });
      }
    }
  };

  const totalPages = Math.ceil(arsenalSignals.length / pageSize) || 1;
  const validCurrentPage = Math.min(Math.max(currentPage, 1), totalPages);

  const paginatedArsenalSignals = useMemo(() => {
    const startIdx = (validCurrentPage - 1) * pageSize;
    return arsenalSignals.slice(startIdx, startIdx + pageSize);
  }, [arsenalSignals, validCurrentPage, pageSize]);

  return (
    <div className="flex flex-col h-full w-full bg-zinc-950 text-zinc-100 overflow-hidden font-mono text-xs">
      {/* 1. Header Navigation Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-900/90 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-emerald-400">
            <Compass className="w-4 h-4 text-emerald-400" />
            <span className="font-bold text-sm tracking-wide text-zinc-100">{t.alphaFactory.title}</span>
          </div>
          <span className="bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded text-[10px] font-bold border border-emerald-500/30">
            {t.alphaFactory.arsenalBadge}
          </span>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-white/5">
          <button
            onClick={() => setActiveTab('AST_STUDIO')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md font-semibold text-xs transition-all ${
              activeTab === 'AST_STUDIO'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Code className="w-3.5 h-3.5" />
            {t.alphaFactory.tabStudio}
          </button>

          <button
            onClick={() => setActiveTab('ARSENAL_703')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md font-semibold text-xs transition-all ${
              activeTab === 'ARSENAL_703'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            {t.alphaFactory.tabArsenal}
            <span className="text-[10px] bg-cyan-900/60 text-cyan-200 px-1.5 py-0.2 rounded font-mono ml-1">
              {totalArsenalCount || 703}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('GENETIC_EVOLUTION')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md font-semibold text-xs transition-all ${
              activeTab === 'GENETIC_EVOLUTION'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Dna className="w-3.5 h-3.5" />
            {t.alphaFactory.tabGenetic}
            {isDiscovering && (
              <span className="w-2 h-2 rounded-full bg-purple-400 animate-ping inline-block ml-1" />
            )}
          </button>
        </div>
      </div>

      {/* 2. Main Tab View Content */}
      <div className="flex-1 overflow-auto p-4 bg-zinc-950">
        {/* TAB 1: AST Formula Studio */}
        {activeTab === 'AST_STUDIO' && (
          <div className="grid grid-cols-12 gap-4 h-full">
            {/* Left: Code Editor & Presets */}
            <div className="col-span-12 lg:col-span-7 flex flex-col gap-3">
              {/* Formula Editor Box */}
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-emerald-400" />
                    <span className="font-bold text-zinc-200 text-xs uppercase tracking-wider">
                      {t.alphaFactory.astEditorTitle}
                    </span>
                  </div>
                  <span className="text-[10px] text-zinc-300 bg-zinc-800 px-2 py-0.5 rounded">
                    {t.alphaFactory.sandboxGuaranteed}
                  </span>
                </div>

                <div className="relative">
                  <textarea
                    value={expression}
                    onChange={(e) => setExpression(e.target.value)}
                    rows={4}
                    placeholder={t.alphaFactory.formulaPlaceholder}
                    className="w-full bg-zinc-950 text-emerald-300 border border-white/10 rounded-lg p-3 font-mono text-xs focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 resize-none"
                  />
                </div>

                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-300 text-[11px]">{t.alphaFactory.universeLabel}</span>
                    <select
                      aria-label="Universe Selection"
                      className="bg-zinc-800 border border-white/10 text-zinc-200 rounded px-2 py-1 text-xs focus:outline-none"
                    >
                      <option value="VN703">VN703 All-Share</option>
                      <option value="VN30">VN30 Large-Cap</option>
                      <option value="VNMID">VNMID Mid-Cap</option>
                    </select>
                  </div>

                  <button
                    onClick={handleEvaluateLocal}
                    disabled={isLocalEvaluating || !expression.trim()}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg shadow-md transition-all active:scale-95"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    {isLocalEvaluating ? t.alphaFactory.evaluatingBtn : t.alphaFactory.evaluateBtn}
                  </button>
                </div>
              </div>

              {/* Preset Formulas Library */}
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-2">
                <div className="flex items-center gap-2 text-zinc-300 mb-1">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  <span className="font-bold text-xs uppercase tracking-wider">{t.alphaFactory.templatesTitle}</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {PRESET_FORMULAS.map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => setExpression(item.formula)}
                      className="flex flex-col text-left p-2.5 rounded-lg bg-zinc-950/60 hover:bg-zinc-800/80 border border-white/5 hover:border-emerald-500/40 transition-all group"
                    >
                      <span className="text-[11px] font-bold text-zinc-300 group-hover:text-emerald-300 mb-1">
                        {item.label}
                      </span>
                      <code className="text-[10px] text-zinc-300 group-hover:text-zinc-300 truncate">
                        {item.formula}
                      </code>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right: Validation & AST Projection Cards */}
            <div className="col-span-12 lg:col-span-5 flex flex-col gap-3">
              {localEvalResult ? (
                <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                  <div className="flex items-center justify-between border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2">
                      {localEvalResult.is_valid ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400" />
                      )}
                      <span className="font-bold text-zinc-200">
                        {localEvalResult.is_valid ? t.alphaFactory.validationVerified : t.alphaFactory.validationRejected}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                        localEvalResult.is_valid
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {localEvalResult.ast_type}
                    </span>
                  </div>

                  {localEvalResult.error && (
                    <div className="bg-rose-950/40 border border-rose-500/30 p-2.5 rounded text-rose-300 text-xs">
                      {localEvalResult.error}
                    </div>
                  )}

                  {/* Quantitative Metrics Grid */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                      <span className="text-zinc-300 text-[10px]">{t.alphaFactory.icMean}</span>
                      <span className="text-emerald-400 font-bold text-base mt-0.5">
                        +{localEvalResult.ic_estimate.toFixed(3)}
                      </span>
                    </div>

                    <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                      <span className="text-zinc-300 text-[10px]">{t.alphaFactory.irAnnual}</span>
                      <span className="text-cyan-400 font-bold text-base mt-0.5">
                        {localEvalResult.ir_estimate.toFixed(2)}
                      </span>
                    </div>

                    <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                      <span className="text-zinc-300 text-[10px]">{t.alphaFactory.turnoverEst}</span>
                      <span className="text-amber-400 font-bold text-base mt-0.5">
                        {localEvalResult.turnover_estimate_pct.toFixed(1)}% / day
                      </span>
                    </div>

                    <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col">
                      <span className="text-zinc-300 text-[10px]">{t.alphaFactory.astComplexity}</span>
                      <span className="text-purple-400 font-bold text-base mt-0.5">
                        {localEvalResult.complexity_score} nodes
                      </span>
                    </div>
                  </div>

                  {/* Sample Vector Results */}
                  {localEvalResult.sample_result && (
                    <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 flex flex-col gap-1.5">
                      <span className="text-zinc-300 text-[10px] uppercase font-bold">{t.alphaFactory.sampleVector}</span>
                      <div className="flex items-center gap-1.5 overflow-x-auto py-1">
                        {localEvalResult.sample_result.map((val, idx) => (
                          <span
                            key={idx}
                            className="bg-zinc-800 text-zinc-200 px-2 py-0.5 rounded text-[10px] font-mono shrink-0"
                          >
                            [{idx}]: {val.toFixed(3)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-zinc-900/40 border border-white/5 rounded-xl p-8 flex flex-col items-center justify-center text-center gap-2 text-zinc-300">
                  <Zap className="w-8 h-8 text-zinc-300" />
                  <span className="font-bold text-zinc-300">{t.alphaFactory.noFormula}</span>
                  <p className="text-[11px] max-w-xs text-zinc-300">
                    {t.alphaFactory.noFormulaDesc}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: 703 Alpha Arsenal Matrix */}
        {activeTab === 'ARSENAL_703' && (
          <div className="grid grid-cols-12 gap-4 h-full">
            {/* Left: Signals List & Filters */}
            <div className="col-span-12 lg:col-span-8 flex flex-col gap-3">
              {/* Filter controls */}
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                  <Search className="w-4 h-4 text-zinc-300 shrink-0" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setCurrentPage(1);
                    }}
                    placeholder={t.alphaFactory.searchPlaceholder}
                    className="w-full bg-zinc-950 border border-white/10 text-zinc-200 rounded px-2.5 py-1 text-xs focus:outline-none focus:border-cyan-500/60"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Filter className="w-3.5 h-3.5 text-zinc-300" />
                  <select
                    aria-label={t.alphaFactory.filterCategory}
                    value={selectedCategory}
                    onChange={(e) => {
                      setSelectedCategory(e.target.value === 'ALL' ? '' : e.target.value);
                      setCurrentPage(1);
                    }}
                    className="bg-zinc-950 border border-white/10 text-zinc-200 rounded px-2 py-1 text-xs focus:outline-none"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c === 'ALL' ? '' : c}>
                        {c}
                      </option>
                    ))}
                  </select>

                  <select
                    aria-label={t.alphaFactory.filterStatus}
                    value={selectedStatus}
                    onChange={(e) => {
                      setSelectedStatus(e.target.value === 'ALL' ? '' : e.target.value);
                      setCurrentPage(1);
                    }}
                    className="bg-zinc-950 border border-white/10 text-zinc-200 rounded px-2 py-1 text-xs focus:outline-none"
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s === 'ALL' ? '' : s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Signals Grid / Table */}
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl overflow-hidden flex flex-col flex-1 max-h-[520px]">
                <div className="grid grid-cols-12 bg-zinc-950 px-3 py-2 text-[10px] text-zinc-300 font-bold uppercase tracking-wider border-b border-white/10">
                  <div className="col-span-2">Alpha ID</div>
                  <div className="col-span-3">Category / Name</div>
                  <div className="col-span-4">Formula</div>
                  <div className="col-span-1 text-right">IC</div>
                  <div className="col-span-1 text-right">IR</div>
                  <div className="col-span-1 text-center">Status</div>
                </div>

                <div className="overflow-y-auto flex-1 divide-y divide-white/5">
                  {isArsenalLoading ? (
                    <div className="p-8 text-center text-zinc-300">Loading Alpha Arsenal...</div>
                  ) : paginatedArsenalSignals.length === 0 ? (
                    <div className="p-8 text-center text-zinc-300">No alpha signals matching filter.</div>
                  ) : (
                    paginatedArsenalSignals.map((item) => {
                      const isSelected = selectedAlphaId === item.alpha_id;
                      return (
                        <div
                          key={item.alpha_id}
                          onClick={() => setSelectedAlphaId(item.alpha_id)}
                          className={`grid grid-cols-12 px-3 py-2 text-xs items-center cursor-pointer transition-all ${
                            isSelected
                              ? 'bg-cyan-500/15 text-cyan-200 border-l-2 border-cyan-400 font-semibold'
                              : 'hover:bg-white/5 text-zinc-300'
                          }`}
                        >
                          <div className="col-span-2 font-mono text-[11px] text-zinc-300">{item.alpha_id}</div>
                          <div className="col-span-3 truncate">
                            <span className="text-[10px] bg-zinc-800 text-zinc-300 px-1 py-0.2 rounded mr-1">
                              {item.category}
                            </span>
                            <span className="truncate">{item.name}</span>
                          </div>
                          <div className="col-span-4 font-mono text-[10px] text-zinc-300 truncate" title={item.formula}>
                            {item.formula}
                          </div>
                          <div className="col-span-1 text-right font-mono text-emerald-400">
                            {item.ic_mean.toFixed(3)}
                          </div>
                          <div className="col-span-1 text-right font-mono text-cyan-400">
                            {item.ir_annualized.toFixed(2)}
                          </div>
                          <div className="col-span-1 text-center">
                            <span
                              className={`text-[9px] px-1 py-0.2 rounded font-mono font-bold ${
                                item.status === 'ACTIVE'
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : item.status === 'CANDIDATE'
                                  ? 'bg-amber-500/20 text-amber-300'
                                  : item.status === 'INCUBATING'
                                  ? 'bg-purple-500/20 text-purple-300'
                                  : 'bg-zinc-800 text-zinc-300'
                              }`}
                            >
                              {item.status}
                            </span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Pagination Controls */}
                <div className="p-2.5 bg-zinc-950 border-t border-white/10 flex items-center justify-between text-xs font-mono text-zinc-400">
                  <div className="flex items-center gap-1.5 text-[11px]">
                    <span>Showing</span>
                    <span className="text-zinc-100 font-bold">
                      {arsenalSignals.length === 0 ? 0 : (validCurrentPage - 1) * pageSize + 1}-
                      {Math.min(validCurrentPage * pageSize, arsenalSignals.length)}
                    </span>
                    <span>of</span>
                    <span className="text-zinc-100 font-bold">{arsenalSignals.length}</span>
                    <span>alphas</span>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      title="First Page"
                      aria-label="First Page"
                      disabled={validCurrentPage <= 1}
                      onClick={() => setCurrentPage(1)}
                      className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300 transition-colors"
                    >
                      <ChevronsLeft className="w-3.5 h-3.5" />
                    </button>
                    <button
                      title="Previous Page"
                      aria-label="Previous Page"
                      disabled={validCurrentPage <= 1}
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300 transition-colors"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" />
                    </button>
                    <span className="text-zinc-300 px-2 py-0.5 text-[11px] font-mono bg-zinc-900/80 rounded border border-white/5">
                      {validCurrentPage} / {totalPages}
                    </span>
                    <button
                      title="Next Page"
                      aria-label="Next Page"
                      disabled={validCurrentPage >= totalPages}
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300 transition-colors"
                    >
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      title="Last Page"
                      aria-label="Last Page"
                      disabled={validCurrentPage >= totalPages}
                      onClick={() => setCurrentPage(totalPages)}
                      className="p-1 rounded bg-zinc-900 border border-white/10 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed text-zinc-300 transition-colors"
                    >
                      <ChevronsRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Decay Profile & Deep Dive */}
            <div className="col-span-12 lg:col-span-4 flex flex-col gap-3">
              {localDecayProfile && !isLocalDecayLoading ? (
                <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                  <div className="flex items-center justify-between border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2">
                      <TrendingDown className="w-4 h-4 text-cyan-400" />
                      <span className="font-bold text-zinc-200">{t.alphaFactory.decayTitle}</span>
                    </div>
                    <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-bold">
                      {localDecayProfile.decay_regime}
                    </span>
                  </div>

                  <div className="flex items-center justify-between bg-zinc-950 p-3 rounded-lg border border-white/5">
                    <div>
                      <span className="text-zinc-300 text-[10px]">Selected Alpha</span>
                      <div className="text-zinc-100 font-bold text-xs mt-0.5">{localDecayProfile.name}</div>
                    </div>
                    <div className="text-right">
                      <span className="text-zinc-300 text-[10px]">{t.alphaFactory.halfLife}</span>
                      <div className="text-cyan-400 font-bold text-xs mt-0.5">{localDecayProfile.half_life_days} Days</div>
                    </div>
                  </div>

                  {/* Decay Table Profile */}
                  <div className="flex flex-col gap-1">
                    <span className="text-zinc-300 text-[10px] uppercase font-bold">Lag-Day Predictive Decay</span>
                    <div className="bg-zinc-950 rounded-lg border border-white/5 divide-y divide-white/5 overflow-hidden">
                      <div className="grid grid-cols-4 px-2 py-1.5 text-[9px] text-zinc-300 uppercase font-bold">
                        <div>Lag</div>
                        <div className="text-right">IC</div>
                        <div className="text-right">IR</div>
                        <div className="text-right">Corr %</div>
                      </div>
                      {localDecayProfile.profile.slice(0, 8).map((p) => (
                        <div key={p.lag_days} className="grid grid-cols-4 px-2 py-1 text-[10px] font-mono">
                          <div className="text-zinc-300">T+{p.lag_days}</div>
                          <div className="text-right text-emerald-400">{p.ic.toFixed(3)}</div>
                          <div className="text-right text-cyan-400">{p.ir.toFixed(2)}</div>
                          <div className="text-right text-zinc-300">
                            {Math.round(p.correlation_decay * 100)}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      const sel = arsenalSignals.find((s) => s.alpha_id === selectedAlphaId);
                      if (sel) {
                        setExpression(sel.formula);
                        setActiveTab('AST_STUDIO');
                      }
                    }}
                    className="w-full flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 py-2 rounded-lg border border-white/10 font-bold transition-all text-xs"
                  >
                    <Layers className="w-3.5 h-3.5" />
                    {t.alphaFactory.loadStudio}
                  </button>
                </div>
              ) : (
                <div className="p-8 text-center text-zinc-300">{t.alphaFactory.selectAlphaInspect}</div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: Genetic Evolution Visualizer */}
        {activeTab === 'GENETIC_EVOLUTION' && (
          <div className="grid grid-cols-12 gap-4 h-full">
            {/* Left: Evolution Config & Controls */}
            <div className="col-span-12 lg:col-span-4 flex flex-col gap-3">
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                <div className="flex items-center gap-2 text-purple-400 border-b border-white/5 pb-2">
                  <Dna className="w-4 h-4" />
                  <span className="font-bold text-zinc-200">{t.alphaFactory.geneticTitle}</span>
                </div>

                <div className="flex flex-col gap-2">
                  <div>
                    <label className="text-zinc-300 text-[10px] block mb-1">{t.alphaFactory.generationsCount}</label>
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={generations}
                      onChange={(e) => setGenerations(Number(e.target.value))}
                      className="w-full bg-zinc-950 border border-white/10 text-zinc-200 rounded p-2 text-xs focus:outline-none focus:border-purple-500/60"
                    />
                  </div>

                  <div>
                    <label className="text-zinc-300 text-[10px] block mb-1">{t.alphaFactory.populationSize}</label>
                    <input
                      type="number"
                      min={10}
                      max={200}
                      value={popSize}
                      onChange={(e) => setPopSize(Number(e.target.value))}
                      className="w-full bg-zinc-950 border border-white/10 text-zinc-200 rounded p-2 text-xs focus:outline-none focus:border-purple-500/60"
                    />
                  </div>
                </div>

                <button
                  onClick={() => handleStartDiscovery({ generations, population_size: popSize })}
                  disabled={isDiscovering}
                  className="flex items-center justify-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold py-2.5 rounded-lg shadow-md transition-all active:scale-95"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  {isDiscovering ? t.alphaFactory.evolvingPopulation : t.alphaFactory.launchGeneticBtn}
                </button>
              </div>

              {/* Status Box */}
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-300 text-[10px]">{t.alphaFactory.sessionStatus}</span>
                  <span
                    className={`text-[9px] px-2 py-0.5 rounded font-bold ${
                      discoveryState.status === 'RUNNING'
                        ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                        : discoveryState.status === 'COMPLETED'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-zinc-800 text-zinc-300'
                    }`}
                  >
                    {discoveryState.status}
                  </span>
                </div>

                <div className="w-full bg-zinc-950 h-2 rounded-full overflow-hidden border border-white/5 my-1">
                  <div
                    className="bg-purple-500 h-full transition-all duration-300"
                    style={{ width: `${discoveryState.progress}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[10px] text-zinc-300">
                  <span>Progress: {discoveryState.progress.toFixed(1)}%</span>
                  <span>
                    Gen: {discoveryState.generation} / {discoveryState.maxGenerations}
                  </span>
                </div>
              </div>
            </div>

            {/* Right: Evolution Live Feed & Best Alpha Genome */}
            <div className="col-span-12 lg:col-span-8 flex flex-col gap-3">
              <div className="bg-zinc-900/70 border border-white/10 rounded-xl p-4 flex flex-col gap-3 shadow-md flex-1">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-purple-400" />
                    <span className="font-bold text-zinc-200">{t.alphaFactory.fittestDiscovered}</span>
                  </div>
                  {discoveryState.bestFitness > 0 && (
                    <span className="text-purple-300 font-mono font-bold text-xs">
                      Fitness: {discoveryState.bestFitness.toFixed(2)}
                    </span>
                  )}
                </div>

                {discoveryState.bestFormula ? (
                  <div className="bg-zinc-950 p-3 rounded-lg border border-purple-500/30 flex flex-col gap-2">
                    <span className="text-zinc-300 text-[10px] uppercase font-bold">{t.alphaFactory.candidateExpr}</span>
                    <code className="text-xs text-purple-300 font-mono bg-zinc-900 p-2 rounded">
                      {discoveryState.bestFormula}
                    </code>
                    <div className="flex items-center justify-end">
                      <button
                        onClick={() => {
                          setExpression(discoveryState.bestFormula);
                          setActiveTab('AST_STUDIO');
                        }}
                        className="text-[10px] bg-purple-600/30 hover:bg-purple-600/50 text-purple-200 border border-purple-500/40 px-2.5 py-1 rounded transition-all"
                      >
                        {t.alphaFactory.sendToStudio}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 bg-zinc-950 rounded-lg text-center text-zinc-300 text-xs">
                    Start genetic search to observe evolving alpha candidates.
                  </div>
                )}

                {/* History Log */}
                <div className="flex flex-col gap-1.5 flex-1">
                  <span className="text-zinc-300 text-[10px] uppercase font-bold">Evolutionary Generation History</span>
                  <div className="bg-zinc-950 p-2.5 rounded-lg border border-white/5 overflow-y-auto max-h-[260px] flex flex-col gap-1 divide-y divide-white/5 font-mono text-[10px]">
                    {discoveryState.history.length === 0 ? (
                      <span className="text-zinc-300 py-2">No generations recorded yet.</span>
                    ) : (
                      discoveryState.history.map((ev, idx) => (
                        <div key={idx} className="py-1 flex items-center justify-between text-zinc-300">
                          <span className="text-purple-400 font-bold">
                            Gen {ev.generation}/{ev.max_generations}
                          </span>
                          <span className="truncate max-w-[280px] text-zinc-300">{ev.best_formula}</span>
                          <span className="text-emerald-400">Fit: {ev.best_fitness.toFixed(2)}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

