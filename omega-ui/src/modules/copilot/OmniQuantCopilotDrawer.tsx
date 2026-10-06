import React, { useState, useRef, useEffect, memo } from 'react';
import {
  X,
  Sparkles,
  Send,
  Terminal,
  Zap,
  Layers,
  Cpu,
  Activity,
  TrendingUp,
  DollarSign,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Info,
  Bot,
  Settings
} from 'lucide-react';
import { useCopilot, ChatMessage } from '../../hooks/useCopilot';
import { useTranslation } from '../../i18n';
import { containModalFocus } from './LLMConfigModal';
import { RecommendationActionItem, CopilotStreamEvent } from '../../api/client';

interface OmniQuantCopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenConfigModal?: () => void;
}

// 1. Isolated Chat Message List Component to prevent re-render jitter & preserve scroll position
const ChatMessageList = memo(({
  chatHistory,
  isAsking,
  locale,
  onSendAction,
}: {
  chatHistory: ChatMessage[];
  isAsking: boolean;
  locale: string;
  onSendAction: (action: string) => void;
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatHistory.length, isAsking]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-1 max-h-[50vh] scroll-smooth">
      {chatHistory.map((msg) => (
        <div
          key={msg.id}
          className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
        >
          <div
            className={`max-w-[85%] rounded-xl p-3 text-xs leading-relaxed ${
              msg.sender === 'user'
                ? 'bg-emerald-600 text-white rounded-br-none shadow-md'
                : 'bg-zinc-900 border border-white/10 text-zinc-200 rounded-bl-none'
            }`}
          >
            <div className="flex items-center gap-1.5 mb-1 font-mono text-[10px] text-zinc-400 opacity-70">
              {msg.sender === 'user' ? (
                <span>OPERATOR</span>
              ) : (
                <span className="flex items-center gap-1 text-emerald-400">
                  <Bot className="w-3 h-3" />
                  OMNI_QUANT_COPILOT
                </span>
              )}
              <span>•</span>
              <span>{msg.timestamp ? msg.timestamp.split('T')[1]?.slice(0, 8) : ''}</span>
            </div>
            <p className="font-sans whitespace-pre-wrap">
              {locale === 'vi' ? msg.textVi : msg.textEn}
            </p>

            {/* Executed Autonomous Tools Badges */}
            {msg.executedTools && msg.executedTools.length > 0 && (
              <div className="mt-2.5 pt-2 border-t border-emerald-500/20 flex flex-col gap-1">
                <span className="text-[10px] font-mono text-emerald-400 font-semibold flex items-center gap-1">
                  <Zap className="w-3 h-3 text-emerald-400 animate-pulse" />
                  HÀNH ĐỘNG TỰ ĐỘNG (AUTONOMOUS DISPATCH):
                </span>
                <div className="flex flex-wrap gap-1.5 mt-0.5">
                  {msg.executedTools.map((tItem: any, tIdx: number) => {
                    let label = tItem.tool_name;
                    if (tItem.tool_name === 'navigate_ui') {
                      label = `Đã chuyển tab: ${tItem.target || tItem.parameters?.module}`;
                    } else if (tItem.tool_name === 'set_focus_ticker') {
                      label = `Đã chọn mã: ${tItem.target || tItem.parameters?.ticker}`;
                    } else if (tItem.tool_name === 'filter_screener') {
                      label = `Đã áp dụng bộ lọc Screener (ROE/Piotroski)`;
                    } else if (tItem.tool_name === 'set_timeframe') {
                      label = `Đã đổi khung: ${tItem.target || tItem.parameters?.timeframe || tItem.parameters?.interval || '1D'}`;
                    } else if (tItem.tool_name === 'set_theme') {
                      label = `Đã đổi theme: ${tItem.target || tItem.parameters?.theme || 'dark'}`;
                    } else if (tItem.tool_name === 'update_market_data') {
                      label = tItem.status === 'error' ? `Lỗi đồng bộ dữ liệu: ${tItem.target}` : `Đã đồng bộ dữ liệu: ${tItem.target || 'Live Data'}`;
                    } else if (tItem.tool_name === 'execute_quant_script') {
                      label = tItem.status === 'error' ? `Lỗi chạy AST Alpha` : `Đã xác thực & chạy Alpha AST`;
                    } else if (tItem.tool_name === 'trigger_backtest') {
                      label = tItem.status === 'error' ? `Lỗi kích hoạt Backtest` : `Đã chạy Backtest ${tItem.target || 'Strategy'}`;
                    }

                    const isError = tItem.status === 'error';
                    return (
                      <span
                        key={tIdx}
                        className={`text-[10px] font-mono px-2 py-0.5 rounded border flex items-center gap-1 shadow-sm ${
                          isError
                            ? 'bg-red-950/80 border-red-500/40 text-red-300'
                            : 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300'
                        }`}
                      >
                        {isError ? (
                          <AlertTriangle className="w-2.5 h-2.5 text-red-400" />
                        ) : (
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                        )}
                        {label}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Attached Suggested Actions */}
            {msg.suggestedActions && msg.suggestedActions.length > 0 && (
              <div className="mt-2.5 pt-2 border-t border-white/10 flex flex-wrap gap-1.5">
                {msg.suggestedActions.map((action, aIdx) => (
                  <button
                    key={aIdx}
                    onClick={() => onSendAction(action)}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-cyan-300 border border-cyan-500/30 transition-colors"
                  >
                    {action}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      {isAsking && (
        <div className="flex items-center gap-2 text-xs font-mono text-zinc-400 p-2">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-400" />
          <span>Omni-Quant is processing multi-engine telemetry...</span>
        </div>
      )}
    </div>
  );
});
ChatMessageList.displayName = 'ChatMessageList';

// 2. Isolated SSE Stream Feeder Component to prevent parent re-render jitter
const SseTelemetryFeed = memo(({ streamEvents }: { streamEvents: CopilotStreamEvent[] }) => (
  <div className="p-3 rounded-lg bg-zinc-900/40 border border-white/5 space-y-2">
    <div className="flex items-center justify-between text-xs font-mono text-zinc-400">
      <span className="flex items-center gap-1">
        <Terminal className="w-3.5 h-3.5 text-cyan-400" />
        LIVE SSE STREAM EVENTS
      </span>
      <span className="text-[10px] text-zinc-500">{streamEvents.length} events received</span>
    </div>
    <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
      {streamEvents.length === 0 ? (
        <p className="text-xs text-zinc-500 font-mono italic">Waiting for real-time telemetry stream...</p>
      ) : (
        streamEvents.map((ev, i) => (
          <div key={i} className="p-2 rounded bg-zinc-950/60 border border-white/5 flex items-start gap-2 text-xs font-mono">
            {ev.severity === 'WARNING' ? (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
            ) : ev.severity === 'SUCCESS' ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <Info className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-zinc-200 truncate">{ev.title}</span>
                <span className="text-[10px] text-zinc-500">{ev.timestamp ? ev.timestamp.split('T')[1]?.slice(0, 8) : ''}</span>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  </div>
));
SseTelemetryFeed.displayName = 'SseTelemetryFeed';

export const OmniQuantCopilotDrawer: React.FC<OmniQuantCopilotDrawerProps> = ({ isOpen, onClose, onOpenConfigModal }) => {
  const { t, locale } = useTranslation();
  const [activeTab, setActiveTab] = useState<'synthesis' | 'recommendations' | 'chat'>('synthesis');
  const [inputPrompt, setInputPrompt] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);

  const {
    synthesis,
    isSynthesisLoading,
    refetchSynthesis,
    recommendations,
    chatHistory,
    isAsking,
    sendQuery,
    clearChat,
    dispatchAction,
    executingActionId,
    streamEvents,
    isSseConnected,
    isUnavailable,
  } = useCopilot(isOpen);

  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    if (isOpen) dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (isOpen && previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [isOpen, isUnavailable]);

  if (!isOpen) return null;
  if (isUnavailable) return (
    <dialog ref={dialogRef} onKeyDown={containModalFocus} aria-modal="true" aria-label={t.copilot.drawerTitle} data-drawer
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="bg-zinc-950 text-zinc-100 p-4 backdrop:bg-black/60">
      <p role="alert">{t.common.integrationUnavailable}</p>
      <button type="button" autoFocus onClick={onClose}>{t.common.cancel}</button>
    </dialog>
  );

  const quickPrompts = [
    locale === 'vi' ? '🔍 Chuyển sang Sàng lọc và lọc cổ phiếu ROE > 20%' : '🔍 Switch to Screener and filter ROE > 20%',
    locale === 'vi' ? '🚀 Chuyển sang Alpha Factory và kiểm tra tín hiệu' : '🚀 Navigate to Alpha Factory',
    locale === 'vi' ? '📊 Cập nhật dữ liệu thị trường cho FPT & HPG' : '📊 Update market telemetry for FPT & HPG',
    locale === 'vi' ? '🧪 Chạy Backtest chiến lược Alpha HRP v2' : '🧪 Trigger Alpha HRP v2 Backtest',
    locale === 'vi' ? 'Đánh giá rủi ro danh mục và CVaR 99%' : 'Assess portfolio risk & 99% CVaR',
    locale === 'vi' ? 'Phân tích định giá cơ bản và P/E mã MBB' : 'Analyze fundamental valuation & P/E for MBB',
  ];

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputPrompt.trim() || isAsking) return;
    sendQuery(inputPrompt);
    setInputPrompt('');
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const getImpactBadge = (level: string) => {
    switch (level) {
      case 'CRITICAL':
        return 'bg-red-500/10 text-red-400 border-red-500/30';
      case 'HIGH':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      case 'MEDIUM':
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30';
      default:
        return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/30';
    }
  };

  return (
    <dialog ref={dialogRef} onKeyDown={containModalFocus} aria-modal="true" aria-label={t.copilot.drawerTitle} data-drawer
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="fixed inset-0 m-0 h-screen max-h-screen w-screen max-w-none z-50 flex justify-end bg-transparent text-zinc-100 backdrop:bg-black/60 backdrop:backdrop-blur-sm transition-all duration-300">
      {/* Backdrop click to close */}
      <div className="flex-1" onClick={onClose} />

      {/* Slide-over Container */}
      <div className="w-full max-w-2xl h-full bg-zinc-950 border-l border-white/10 shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-zinc-900/70">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-emerald-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-zinc-100 tracking-wide font-mono">
                  {t.copilot.drawerTitle}
                </h2>
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/30">
                  AI v2.9
                </span>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded flex items-center gap-1 ${isSseConnected ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-800 text-zinc-400'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${isSseConnected ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-500'}`} />
                  {isSseConnected ? t.copilot.liveSseConnected : t.copilot.liveSseStandby}
                </span>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                {t.copilot.drawerSubtitle}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onOpenConfigModal && (
              <button
                onClick={onOpenConfigModal}
                className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-cyan-300 transition-colors"
                title={t.copilot.configModalTitle}
              >
                <Settings className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => refetchSynthesis()}
              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
              title={t.common.refresh}
            >
              <RefreshCw className={`w-4 h-4 ${isSynthesisLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              autoFocus aria-label={t.common.close}
              onClick={onClose}
              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10 bg-zinc-900/40 px-4 gap-2 pt-2">
          <button
            onClick={() => setActiveTab('synthesis')}
            className={`flex items-center gap-2 px-3 py-2 text-xs font-mono rounded-t-md transition-colors border-b-2 ${
              activeTab === 'synthesis'
                ? 'border-emerald-400 text-emerald-400 bg-zinc-900 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>{t.copilot.synthesisTab}</span>
          </button>

          <button
            onClick={() => setActiveTab('recommendations')}
            className={`flex items-center gap-2 px-3 py-2 text-xs font-mono rounded-t-md transition-colors border-b-2 relative ${
              activeTab === 'recommendations'
                ? 'border-emerald-400 text-emerald-400 bg-zinc-900 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            <span>{t.copilot.recommendationsTab}</span>
            {recommendations.length > 0 && (
              <span className="h-4 px-1.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] flex items-center justify-center font-bold">
                {recommendations.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-2 px-3 py-2 text-xs font-mono rounded-t-md transition-colors border-b-2 ${
              activeTab === 'chat'
                ? 'border-emerald-400 text-emerald-400 bg-zinc-900 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>{t.copilot.chatTab}</span>
          </button>
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 font-sans text-sm">
          {/* TAB 1: SYSTEM SYNTHESIS */}
          {activeTab === 'synthesis' && (
            <div className="space-y-4">
              {/* Executive Quant Verdict Banner */}
              <div className="p-3.5 rounded-xl bg-gradient-to-r from-emerald-950/60 to-cyan-950/40 border border-emerald-500/30 relative overflow-hidden">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-mono font-bold tracking-wider text-emerald-400 uppercase flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    {t.copilot.systemVerdict}
                  </span>
                  <span className="px-2 py-0.5 rounded text-xs font-bold font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                    {synthesis?.holistic_verdict || 'ACCUMULATE_BULLISH'}
                  </span>
                </div>
                <p className="text-xs text-zinc-200 leading-relaxed font-sans">
                  {locale === 'vi' ? synthesis?.verdict_reasoning_vi : synthesis?.verdict_reasoning_en}
                </p>
                <div className="mt-3 pt-2 border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>SCORE: <strong className="text-emerald-400">{synthesis?.executive_quant_score || 88.5}/100</strong></span>
                  <span>FOCUS: <strong className="text-cyan-400">{synthesis?.focus_symbol || 'FPT'}</strong></span>
                </div>
              </div>

              {/* 5-Engine Synthesis Live Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* 1. Macro & VSI */}
                <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-mono text-cyan-400 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <TrendingUp className="w-3.5 h-3.5" />
                      {t.copilot.macroVsiCii}
                    </span>
                    <span className="text-[10px] text-zinc-400">{synthesis?.macro?.regime || 'EXPANSION'}</span>
                  </div>
                  <div className="text-xs text-zinc-300 font-mono space-y-0.5">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">VSI Sentiment:</span>
                      <span className="text-emerald-400 font-bold">{synthesis?.macro?.vsi_sentiment_score || 64.5} ({synthesis?.macro?.vsi_sentiment_level || 'GREED'})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">SBV OMO Net:</span>
                      <span className="text-zinc-200">+{synthesis?.macro?.sbv_omo_injection_billion_vnd || 4500}B VND</span>
                    </div>
                  </div>
                </div>

                {/* 2. Alpha Arsenal & AST */}
                <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-mono text-purple-400 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5" />
                      {t.copilot.alphaArsenal}
                    </span>
                    <span className="text-[10px] text-zinc-400">{synthesis?.alpha?.active_alphas_count || 52}/703 ACTIVE</span>
                  </div>
                  <div className="text-xs text-zinc-300 font-mono space-y-0.5">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Mean IC (t-stat):</span>
                      <span className="text-emerald-400 font-bold">{synthesis?.alpha?.mean_ic || 0.084} ({synthesis?.alpha?.ic_tstat || 4.82})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Top Signal:</span>
                      <span className="text-zinc-200 truncate max-w-[140px]">{synthesis?.alpha?.top_active_signal?.name || 'OBI Trend'}</span>
                    </div>
                  </div>
                </div>

                {/* 3. Fundamental Screener */}
                <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-mono text-amber-400 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <DollarSign className="w-3.5 h-3.5" />
                      {t.copilot.fundamentalScreener}
                    </span>
                    <span className="text-[10px] text-zinc-400">{synthesis?.screener?.qualified_count || 48} QUALIFIED</span>
                  </div>
                  <div className="text-xs text-zinc-300 font-mono space-y-0.5">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Piotroski F / Altman Z:</span>
                      <span className="text-zinc-200">{synthesis?.screener?.target_ticker_profile?.piotroski_f || 8}/9 | {synthesis?.screener?.target_ticker_profile?.altman_z || 3.42}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">ROE:</span>
                      <span className="text-emerald-400 font-bold">{synthesis?.screener?.target_ticker_profile?.roe_pct || 26.5}%</span>
                    </div>
                  </div>
                </div>

                {/* 4. Barra Risk & TCA */}
                <div className="p-3 rounded-lg bg-zinc-900/60 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-mono text-emerald-400 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5" />
                      {t.copilot.riskTcaDecomp}
                    </span>
                    <span className="text-[10px] text-zinc-400">CVaR99: {synthesis?.risk_tca?.cvar_99_pct || 2.68}%</span>
                  </div>
                  <div className="text-xs text-zinc-300 font-mono space-y-0.5">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Factor / Spec Risk:</span>
                      <span className="text-zinc-200">{synthesis?.risk_tca?.factor_risk_pct || 11.25}% / {synthesis?.risk_tca?.specific_risk_pct || 3.57}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Fastest Gateway:</span>
                      <span className="text-zinc-200 truncate max-w-[140px]">{synthesis?.risk_tca?.fastest_gateway || 'VCI DMA 4.2ms'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Live Alerts Stream Feed */}
              <SseTelemetryFeed streamEvents={streamEvents} />
            </div>
          )}

          {/* TAB 2: ACTIONABLE RECOMMENDATIONS */}
          {activeTab === 'recommendations' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs font-mono text-zinc-400 px-1">
                <span>{t.copilot.actionDispatcherTitle}</span>
                <span>{recommendations.length} PENDING</span>
              </div>

              {recommendations.length === 0 ? (
                <div className="p-8 text-center text-zinc-500 font-mono text-xs">
                  {t.copilot.noRecommendations}
                </div>
              ) : (
                recommendations.map((rec: RecommendationActionItem) => {
                  const isExecuting = executingActionId === rec.id;
                  return (
                    <div
                      key={rec.id}
                      className="p-3.5 rounded-xl bg-zinc-900/70 border border-white/10 hover:border-emerald-500/40 transition-all space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border font-bold ${getImpactBadge(rec.impact_level)}`}>
                              {rec.impact_level}
                            </span>
                            <span className="text-xs font-bold text-zinc-200">
                              {rec.title}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-400 leading-relaxed font-sans">
                            {rec.description}
                          </p>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-white/5 flex items-center justify-between">
                        <div className="text-[11px] font-mono text-zinc-400">
                          <span>{t.copilot.confidence}: <strong className="text-emerald-400">{Math.round(rec.confidence_score * 100)}%</strong></span>
                          {rec.target_symbol && (
                            <span className="ml-3">MÃ: <strong className="text-cyan-400">{rec.target_symbol}</strong></span>
                          )}
                        </div>

                        <button
                          onClick={() => dispatchAction(rec)}
                          disabled={isExecuting}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-semibold transition-all shadow-md shadow-emerald-600/20 disabled:opacity-50"
                        >
                          {isExecuting ? (
                            <>
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              <span>{t.copilot.executingAction}</span>
                            </>
                          ) : (
                            <>
                              <Zap className="w-3.5 h-3.5" />
                              <span>{t.copilot.oneClickAction}</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* TAB 3: QUANT COPILOT CHAT & TERMINAL */}
          {activeTab === 'chat' && (
            <div className="flex flex-col h-full space-y-3">
              {/* Isolated Terminal Messages Scroll */}
              <ChatMessageList
                chatHistory={chatHistory}
                isAsking={isAsking}
                locale={locale}
                onSendAction={sendQuery}
              />

              {/* Quick Query Chips */}
              <div className="space-y-1.5 pt-2 border-t border-white/10">
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>{t.copilot.quickChips}:</span>
                  <button onClick={clearChat} className="text-zinc-500 hover:text-zinc-300 underline text-[10px]">
                    {t.copilot.clearChat}
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {quickPrompts.map((chip, idx) => (
                    <button
                      key={idx}
                      onClick={() => sendQuery(chip)}
                      className="text-[11px] px-2 py-1 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-white/10 hover:border-emerald-500/40 transition-colors text-left font-sans"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>

              {/* Input Form Box */}
              <form onSubmit={handleSend} className="flex gap-2 pt-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={inputPrompt}
                  onChange={(e) => setInputPrompt(e.target.value)}
                  placeholder={t.copilot.askPlaceholder}
                  className="flex-1 bg-zinc-900 border border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-emerald-500 font-sans"
                />
                <button
                  type="submit"
                  disabled={isAsking || !inputPrompt.trim()}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-mono font-bold flex items-center gap-1.5 transition-colors"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{t.copilot.sendBtn}</span>
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
};
