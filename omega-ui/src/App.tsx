import React, { useEffect, useRef, useState } from 'react';
import { LandingDatabaseHub } from './modules/macro_cockpit/LandingDatabaseHub';
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
import { OmniQuantCopilotDrawer } from './modules/copilot/OmniQuantCopilotDrawer';
import { LLMConfigModal, containModalFocus } from './modules/copilot/LLMConfigModal';
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
      return { title: t.macroCockpit.title, tag: 'MACRO_REGIME' };
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
  const isStreamingConnected = useUiStore((state) => state.isStreamingConnected);
  const toasts = useUiStore((state) => state.toasts);
  const removeToast = useUiStore((state) => state.removeToast);
  const [isCopilotDrawerOpen, setIsCopilotDrawerOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [digitShortcutsEnabled, setDigitShortcutsEnabled] = useState(true);
  const {
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    isDrawerOpen,
    setIsDrawerOpen
  } = useControlOps();
  const toggleLocale = useUiStore((state) => state.toggleLocale);
  const opsDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = opsDialogRef.current;
    const previousFocus = document.activeElement;
    if (isDrawerOpen) dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (isDrawerOpen && previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
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
  useRealtimeStream({ enabled: true });

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
        return <LandingDatabaseHub />;
      case 'fundamental_matrix':
        return <FundamentalMatrixView />;
      case 'alpha_portfolio':
        return <LandingDatabaseHub />;
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
      <header className="flex flex-wrap items-center gap-4 p-3 border-b border-white/10">
        <h1>OMEGA</h1>
        <label>
          <input type="checkbox" checked={digitShortcutsEnabled} onChange={(event) => setDigitShortcutsEnabled(event.target.checked)} />
          {t.topNav.enableDigitShortcuts}
        </label>
        <span role="status">{isStreamingConnected ? t.common.online : t.common.standby}</span>
        <button type="button" aria-label={t.topNav.language} onClick={toggleLocale} className="rounded px-3 py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
          <span lang="vi">{t.topNav.langVi}</span> / <span lang="en">{t.topNav.langEn}</span>: {locale.toUpperCase()}
        </button>
        <button type="button" aria-expanded={isDrawerOpen} onClick={() => setIsDrawerOpen(true)}>{t.topNav.ops} ({Object.keys(tasks).length})</button>
        <button type="button" onClick={() => setIsCopilotDrawerOpen(true)}>{t.topNav.copilot}</button>
        <button type="button" onClick={() => setIsConfigModalOpen(true)}>{t.topNav.configuration}</button>
      </header>

      {/* 2. Main Workstation Shell: Side Dock + Workspace Grid */}
      <div className="flex flex-1 overflow-hidden relative">
        <SideDock
          activeModule={activeModule}
          onSelectModule={setActiveModule}
          isCollapsed={isSideDockCollapsed}
          onToggleCollapse={toggleSideDockCollapse}
        />

        <main aria-label={moduleHeader.title} className="flex-1 overflow-auto p-4">
          <h2>{moduleHeader.title}</h2>
          <span>{moduleHeader.tag}</span>
          {renderModule()}
        </main>
      </div>

      {/* Global Ops Drawer */}
      {isDrawerOpen && <dialog ref={opsDialogRef} onKeyDown={containModalFocus} aria-label={t.topNav.ops} data-drawer onCancel={(event) => { event.preventDefault(); setIsDrawerOpen(false); }} className="fixed inset-y-0 left-auto right-0 m-0 h-screen max-h-screen w-full max-w-lg overflow-y-auto bg-zinc-900 text-zinc-100 p-4 backdrop:bg-black/60">
        <h2>{t.controlCenter.taskProgressLabel}</h2>
        <button type="button" autoFocus onClick={() => setIsDrawerOpen(false)}>{t.common.close}</button>
        {Object.values(tasks).length === 0 && <p role="status">{t.common.standby}</p>}
        {Object.values(tasks).map((task) => (
          <section key={task.taskId} className="border-b border-white/10 py-3">
            <button type="button" aria-pressed={selectedTaskId === task.taskId} onClick={() => setSelectedTaskId(task.taskId)}>
              {task.taskType}: {task.status}
            </button>
            <p>{t.controlCenter.currentStageLabel} {task.stage}</p>
            <progress aria-label={`${t.controlCenter.taskProgressLabel}: ${task.taskId}`} max={100} value={task.progress} />
            <span>{task.progress}%</span>
            <p role={task.status === 'FAILED' ? 'alert' : 'status'}>{task.message}</p>
            {task.errorCode && <p>{task.errorCode}</p>}
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

      <button type="button" className="fixed bottom-6 left-6" onClick={() => setIsCopilotDrawerOpen(true)}>{t.topNav.copilot}</button>

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
