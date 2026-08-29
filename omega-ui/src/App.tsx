import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';
import { TopNavBar } from './layout/TopNavBar';
import { SideDock, ModuleType } from './layout/SideDock';
import { WorkspaceGrid } from './layout/WorkspaceGrid';
import { MacroCockpitView } from './modules/macro_cockpit/MacroCockpitView';
import { FundamentalMatrixView } from './modules/fundamental_matrix/FundamentalMatrixView';
import { AlphaPortfolioView } from './modules/alpha_portfolio/AlphaPortfolioView';
import { BarraRiskTcaAnalyticsView } from './modules/barra_risk_tca/BarraRiskTcaAnalyticsView';
import { ChartStationView } from './modules/chart_station/ChartStationView';
import { ExecutionBlotterView } from './modules/execution_blotter/ExecutionBlotterView';
import { QuantControlCenter } from './modules/control_center/QuantControlCenter';
import { PipelineOrchestrationConsole } from './modules/pipeline_console/PipelineOrchestrationConsole';
import { ModelRegistryView } from './modules/model_registry/ModelRegistryView';
import { StrategyLabView } from './modules/strategy_lab/StrategyLabView';
import { AlphaFactoryDiscoveryStation } from './modules/alpha_factory/AlphaFactoryDiscoveryStation';
import { MacroNewsSentimentHub } from './modules/macro_news/MacroNewsSentimentHub';
import { OpsProgressDrawer } from './modules/ops_drawer/OpsProgressDrawer';
import { OmniQuantCopilotDrawer } from './modules/copilot/OmniQuantCopilotDrawer';
import { LLMConfigModal } from './modules/copilot/LLMConfigModal';
import { FloatingCopilotTrigger } from './modules/copilot/FloatingCopilotTrigger';
import { useUiStore } from './store/uiStore';
import { useRealtimeStream } from './hooks/useRealtimeStream';
import { useControlOps } from './hooks/useControlOps';
import { I18nProvider, useTranslation } from './i18n';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 60000
    }
  }
});

const getModuleTitle = (module: ModuleType, t: ReturnType<typeof useTranslation>['t']): { title: string; tag: string } => {
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

  const { t } = useTranslation();
  const [isCopilotDrawerOpen, setIsCopilotDrawerOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const {
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    isDrawerOpen,
    setIsDrawerOpen
  } = useControlOps();

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
        return <MacroCockpitView />;
      case 'macro_news_hub':
        return <MacroNewsSentimentHub />;
      case 'fundamental_matrix':
        return <FundamentalMatrixView />;
      case 'alpha_portfolio':
        return <AlphaPortfolioView />;
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
      <TopNavBar
        systemStatus={isStreamingConnected ? 'ONLINE' : 'STANDBY'}
        activeEngineCount={12}
        onOpenOpsDrawer={() => setIsDrawerOpen(true)}
        onOpenCopilotDrawer={() => setIsCopilotDrawerOpen(true)}
        onOpenConfigModal={() => setIsConfigModalOpen(true)}
        activeTaskCount={Object.keys(tasks).length}
        pendingRecommendationsCount={4}
      />

      {/* 2. Main Workstation Shell: Side Dock + Workspace Grid */}
      <div className="flex flex-1 overflow-hidden relative">
        <SideDock
          activeModule={activeModule}
          onSelectModule={setActiveModule}
          isCollapsed={isSideDockCollapsed}
          onToggleCollapse={toggleSideDockCollapse}
        />

        <WorkspaceGrid
          activeModuleName={moduleHeader.title}
          activeModuleTag={moduleHeader.tag}
        >
          {renderModule()}
        </WorkspaceGrid>
      </div>

      {/* Global Ops Drawer */}
      <OpsProgressDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        tasks={tasks}
        selectedTaskId={selectedTaskId}
        onSelectTask={setSelectedTaskId}
      />

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

      <FloatingCopilotTrigger
        onClick={() => setIsCopilotDrawerOpen(true)}
        pendingRecommendationsCount={4}
      />

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
      <I18nProvider>
        <DashboardContent />
      </I18nProvider>
    </QueryClientProvider>
  );
};

export default App;
