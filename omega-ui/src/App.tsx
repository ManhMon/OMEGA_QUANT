import React, { useEffect, useRef } from 'react';
import { LandingDatabaseHub } from './modules/macro_cockpit/LandingDatabaseHub';
import { MacroNewsHubView } from './modules/macro_news/MacroNewsHubView';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';
import { SideDock, type ModuleType } from './layout/SideDock';
import { FundamentalMatrixView } from './modules/fundamental_matrix/FundamentalMatrixView';
import { BarraRiskTcaAnalyticsView } from './modules/barra_risk_tca/BarraRiskTcaAnalyticsView';
import { ChartStationView } from './modules/chart_station/ChartStationView';
import { ExecutionBlotterView } from './modules/execution_blotter/ExecutionBlotterView';
import { QuantControlCenter } from './modules/control_center/QuantControlCenter';
import { PipelineOrchestrationConsole } from './modules/pipeline_console/PipelineOrchestrationConsole';
import { ModelRegistryView } from './modules/model_registry/ModelRegistryView';
import { StrategyLabView } from './modules/strategy_lab/StrategyLabView';
import { AlphaFactoryDiscoveryStation } from './modules/alpha_factory/AlphaFactoryDiscoveryStation';
import { AlphaPortfolioStationView } from './modules/alpha_portfolio/AlphaPortfolioStationView';
import { OmniQuantCopilotDrawer } from './modules/copilot/OmniQuantCopilotDrawer';
import { LLMConfigModal, containModalFocus } from './modules/copilot/LLMConfigModal';
import { TopNavBar } from './layout/TopNavBar';
import { useUiStore } from './store/uiStore';
import { useRealtimeStream } from './hooks/useRealtimeStream';
import { useControlOps } from './hooks/useControlOps';
import { en } from './i18n/en';
import { vi } from './i18n/vi';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 60000
    }
  }
});

const getModuleTitle = (module: ModuleType, t: typeof en): { title: string; tag: string } => {
  switch (module) {
    case 'pipeline_console':
      return { title: t.pipelineConsole.title, tag: 'IN_PROCESS_EXEC' };
    case 'control_center':
      return { title: t.controlCenter.title, tag: 'OPS_DISPATCH' };
    case 'model_registry':
      return { title: t.nav.modelRegistry, tag: 'MODEL_GOVERNANCE' };
    case 'alpha_factory':
      return { title: t.alphaFactory.title, tag: 'AST_DISCOVERY' };
    case 'strategy_lab':
      return { title: t.strategyLab.title, tag: 'STRATEGY_LAB' };
    case 'macro_cockpit':
      return { title: t.nav.macroCockpit, tag: 'MACRO_REGIME' };
    case 'macro_news_hub':
      return { title: t.macroNews.title, tag: 'LLM_SENTIMENT' };
    case 'fundamental_matrix':
      return { title: t.nav.fundamentalMatrix, tag: 'FUNDAMENTAL_EQUITY' };
    case 'alpha_portfolio':
      return { title: t.nav.alphaPortfolio, tag: 'BARRA_HRP_PORTFOLIO' };
    case 'barra_risk_tca':
      return { title: t.barraRiskTca.headerTitle, tag: 'RISK_TCA_ANALYTICS' };
    case 'chart_station':
      return { title: t.nav.chartStation, tag: 'TA_ORDERFLOW' };
    case 'execution_blotter':
      return { title: t.nav.executionBlotter, tag: 'OMS_SMART_EXEC' };
    default:
      return { title: t.workspace.defaultTitle, tag: 'OMEGA' };
  }
};

const DashboardContent: React.FC = () => {
  const activeModule = useUiStore((state) => state.activeModule);
  const setActiveModule = useUiStore((state) => state.setActiveModule);
  const isSideDockCollapsed = useUiStore((state) => state.isSideDockCollapsed);
  const toggleSideDockCollapse = useUiStore((state) => state.toggleSideDockCollapse);
  const toasts = useUiStore((state) => state.toasts);
  const removeToast = useUiStore((state) => state.removeToast);
  const isCopilotDrawerOpen = useUiStore((state) => state.isCopilotDrawerOpen);
  const setIsCopilotDrawerOpen = useUiStore((state) => state.setIsCopilotDrawerOpen);
  const digitShortcutsEnabled = useUiStore((state) => state.digitShortcutsEnabled);
  const isConfigModalOpen = useUiStore((state) => state.isConfigModalOpen);
  const setIsConfigModalOpen = useUiStore((state) => state.setIsConfigModalOpen);
  const {
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    isDrawerOpen,
    setIsDrawerOpen
  } = useControlOps();
  const opsDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = opsDialogRef.current;
    const previousFocus = document.activeElement;
    if (isDrawerOpen) dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (isDrawerOpen && previousFocus instanceof HTMLElement && previousFocus.isConnected && !dialog?.contains(previousFocus)) {
        previousFocus.focus();
      }
    };
  }, [isDrawerOpen]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const isInteractive = (target: EventTarget | null) => target instanceof Element && (
        (target instanceof HTMLElement && target.isContentEditable) ||
        target.closest('button, a, input, textarea, select, [contenteditable]:not([contenteditable="false"]), dialog, [role="dialog"], [aria-modal="true"], [data-drawer]') !== null
      );
      const isInputActive = isInteractive(document.activeElement) || isInteractive(event.target);
      const hasOverlayOpen = isCopilotDrawerOpen || isConfigModalOpen || isDrawerOpen ||
        document.querySelector('dialog[open], [role="dialog"], [role="menu"], [role="listbox"], [aria-modal="true"]') !== null;

      if (
        !digitShortcutsEnabled || isInputActive || event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey ||
        event.altKey || event.shiftKey || hasOverlayOpen || event.repeat ||
        !/^[1-9]$/.test(event.key)
      ) return;

      const module = [
        'pipeline_console', 'control_center', 'model_registry', 'alpha_factory',
        'strategy_lab', 'macro_cockpit', 'macro_news_hub', 'fundamental_matrix',
        'alpha_portfolio',
      ][Number(event.key) - 1] as ModuleType | undefined;

      if (module) setActiveModule(module);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [digitShortcutsEnabled, isCopilotDrawerOpen, isConfigModalOpen, isDrawerOpen, setActiveModule]);

  const locale = useUiStore((state) => state.locale);
  const t = locale === 'vi' ? vi : en;

  // Initialize background live event stream
  const stream = useRealtimeStream({ enabled: true });

  const renderModule = () => {
    switch (activeModule) {
      case 'pipeline_console':
        return <PipelineOrchestrationConsole />;
      case 'control_center':
        return <QuantControlCenter />;
      case 'model_registry':
        return <ModelRegistryView />;
      case 'alpha_factory':
        return <AlphaFactoryDiscoveryStation />;
      case 'strategy_lab':
        return <StrategyLabView />;
      case 'macro_cockpit':
        return <LandingDatabaseHub />;
      case 'macro_news_hub':
        return <MacroNewsHubView />;
      case 'fundamental_matrix':
        return <FundamentalMatrixView />;
      case 'alpha_portfolio':
        return <AlphaPortfolioStationView />;
      case 'barra_risk_tca':
        return <BarraRiskTcaAnalyticsView />;
      case 'chart_station':
        return <ChartStationView />;
      case 'execution_blotter':
        return <ExecutionBlotterView />;
      default:
        return <QuantControlCenter />;
    }
  };

  const moduleHeader = getModuleTitle(activeModule, t);

  return (
    <div className="flex flex-col h-screen w-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans select-none">
      {/* 1. Institutional Top Navigation */}
      <div className="shrink-0 overflow-x-auto [&>header]:min-w-max sm:[&>header]:min-w-0"><TopNavBar /></div>

      {/* 2. Main Workstation Shell: Side Dock + Workspace Grid */}
      <div className="flex flex-col sm:flex-row flex-1 min-h-0 overflow-hidden relative">
        <SideDock
          activeModule={activeModule}
          onSelectModule={setActiveModule}
          isCollapsed={isSideDockCollapsed}
          onToggleCollapse={toggleSideDockCollapse}
        />

        <main aria-label={moduleHeader.title} className="flex-1 min-w-0 min-h-0 overflow-auto bg-zinc-950 p-2 sm:p-4 font-mono flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2 px-2 sm:px-4 py-2.5 rounded-xl border border-white/10 bg-zinc-900/80 backdrop-blur-md shadow-sm">
            <div className="flex flex-wrap items-center gap-3 min-w-0">
              <span className="w-1.5 h-4 bg-emerald-400 rounded-sm inline-block shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
              <h2 className="text-xs font-bold text-zinc-100 tracking-wider uppercase">{moduleHeader.title}</h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono tracking-wider bg-zinc-800/90 text-emerald-300 border border-emerald-500/20">{moduleHeader.tag}</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400">
              <span className="hidden sm:inline text-zinc-500">ENGINE: <span className="text-cyan-400 font-bold">OMEGA_PRO</span></span>
              <span className="hidden sm:inline text-zinc-500">|</span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-zinc-300 font-bold">{activeModule === 'macro_cockpit' ? 'PIT_CUTOFF' : activeModule === 'macro_news_hub' ? 'PROVENANCE_UNVERIFIED' : 'PIT_SAFE'}</span>
              </span>
            </div>
          </div>
          {stream?.isExhausted && <p role="status" className="text-xs text-amber-300">Live stream unavailable after 3 retries. Reload to reconnect.</p>}
          <div className="flex-1 min-h-0 overflow-auto">
            {renderModule()}
          </div>
        </main>
      </div>

      {/* Global Ops Drawer */}
      {isDrawerOpen && <dialog ref={opsDialogRef} onKeyDown={containModalFocus} aria-modal="true" aria-label={t.topNav.ops} data-drawer onCancel={(event) => { event.preventDefault(); setIsDrawerOpen(false); }} className="fixed inset-y-0 left-auto right-0 m-0 h-screen max-h-screen w-full max-w-lg overflow-y-auto bg-zinc-950/95 text-zinc-100 p-5 backdrop:bg-black/70 backdrop:backdrop-blur-sm border-l border-white/10 shadow-2xl font-mono flex flex-col gap-4">
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">{t.controlCenter.taskProgressLabel}</h2>
          </div>
          <button type="button" onClick={() => setIsDrawerOpen(false)} className="px-3 py-1 rounded-lg border border-white/10 bg-zinc-900 hover:bg-zinc-800 text-xs font-bold text-zinc-300 hover:text-white transition-colors">{t.common.close}</button>
        </div>
        {Object.values(tasks).length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-zinc-500 gap-2">
            <p role="status" className="text-xs">{t.common.standby}</p>
          </div>
        )}
        {Object.values(tasks).map((task) => (
          <section key={task.taskId} className="border border-white/10 rounded-xl p-4 bg-zinc-900/60 flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <button type="button" aria-pressed={selectedTaskId === task.taskId} onClick={() => setSelectedTaskId(task.taskId)} className="text-xs font-bold text-cyan-300 hover:underline text-left">
                {task.taskType}: <span className={task.status === 'FAILED' ? 'text-rose-400' : task.status === 'COMPLETED' ? 'text-emerald-400' : 'text-amber-400'}>{task.status}</span>
              </button>
              <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-white/5">{task.taskId}</span>
            </div>
            <p className="text-xs text-zinc-400">{t.controlCenter.currentStageLabel} <span className="text-zinc-200 font-bold">{task.stage}</span></p>
            <div className="flex items-center gap-3">
              <progress aria-label={`${t.controlCenter.taskProgressLabel}: ${task.taskId}`} max={100} value={task.progress} className="flex-1 h-2 rounded-full overflow-hidden bg-zinc-800 accent-cyan-400" />
              <span className="text-xs font-bold text-zinc-300">{task.progress}%</span>
            </div>
            <p role={task.status === 'FAILED' ? 'alert' : 'status'} className="text-xs text-zinc-400">{task.message}</p>
            {task.errorCode && <p className="text-xs text-rose-400 font-bold">{task.errorCode}</p>}
          </section>
        ))}
      </dialog>}

      {/* Phase 11: Omni-Quant AI Copilot Drawer & Floating Trigger */}
      <OmniQuantCopilotDrawer
        isOpen={isCopilotDrawerOpen}
        onClose={() => setIsCopilotDrawerOpen(false)}
        onOpenConfigModal={() => setIsConfigModalOpen(true)}
      />

      {/* Phase 12: LLM Multi-Profile Configuration Modal */}
      <LLMConfigModal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
      />

      <button type="button" className="fixed bottom-6 left-6 z-40 px-4 py-2 rounded-full border border-emerald-500/40 bg-zinc-900/90 hover:bg-zinc-800 text-emerald-300 shadow-2xl backdrop-blur-md flex items-center gap-2 text-xs font-mono font-bold hover:scale-105 hover:border-emerald-400 transition-all cursor-pointer" onClick={() => setIsCopilotDrawerOpen(true)}>{t.topNav.copilot}</button>

      {/* Global Actionable Toast Feedback Container */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none max-w-sm font-mono text-xs select-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto p-3.5 rounded-xl border shadow-xl backdrop-blur-md flex items-start justify-between gap-3 animate-in slide-in-from-bottom-3 duration-200 ${
              toast.type === 'success'
                ? 'bg-emerald-950/90 border-emerald-500/40 text-emerald-200'
                : toast.type === 'warning'
                ? 'bg-amber-950/90 border-amber-500/40 text-amber-200'
                : toast.type === 'error'
                ? 'bg-rose-950/90 border-rose-500/40 text-rose-200'
                : 'bg-zinc-900/90 border-cyan-500/40 text-cyan-200'
            }`}
          >
            <div className="flex items-start gap-2.5">
              {toast.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />}
              {toast.type === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />}
              {toast.type === 'error' && <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />}
              {toast.type === 'info' && <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />}
              <div>
                <div className="font-bold text-zinc-100">{toast.title}</div>
                {toast.message && <div className="text-[11px] text-zinc-400 mt-0.5">{toast.message}</div>}
              </div>
            </div>
            <button
              aria-label={t.common.close}
              onClick={() => removeToast(toast.id)}
              className="p-1 rounded hover:bg-white/10 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardContent />
    </QueryClientProvider>
  );
};

export default App;

