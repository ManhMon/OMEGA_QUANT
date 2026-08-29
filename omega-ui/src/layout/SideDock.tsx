import React from 'react';
import {
  Globe,
  Table2,
  TrendingUp,
  CandlestickChart,
  ReceiptText,
  ShieldAlert,
  ChevronLeft,
  ChevronRight,
  Sliders,
  FlaskConical,
  Compass,
  Newspaper,
  GitFork,
  Layers
} from 'lucide-react';
import { useTranslation } from '../i18n';

export type ModuleType =
  | 'pipeline_console'
  | 'control_center'
  | 'model_registry'
  | 'alpha_factory'
  | 'strategy_lab'
  | 'macro_cockpit'
  | 'macro_news_hub'
  | 'fundamental_matrix'
  | 'alpha_portfolio'
  | 'barra_risk_tca'
  | 'chart_station'
  | 'execution_blotter';

interface SideDockProps {
  activeModule: ModuleType;
  onSelectModule: (module: ModuleType) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface NavItemConfig {
  id: ModuleType;
  labelKey: 'pipelineConsole' | 'controlCenter' | 'modelRegistry' | 'alphaFactory' | 'strategyLab' | 'macroCockpit' | 'macroNewsHub' | 'fundamentalMatrix' | 'alphaPortfolio' | 'barraRiskTca' | 'chartStation' | 'executionBlotter';
  shortLabel: string;
  icon: React.ComponentType<{ className?: string }>;
  tag: string;
}

const NAV_CONFIGS: NavItemConfig[] = [
  {
    id: 'pipeline_console',
    labelKey: 'pipelineConsole',
    shortLabel: 'DAG',
    icon: GitFork,
    tag: 'REAL-ENGINE'
  },
  {
    id: 'control_center',
    labelKey: 'controlCenter',
    shortLabel: 'OPS',
    icon: Sliders,
    tag: 'CONTROL'
  },
  {
    id: 'model_registry',
    labelKey: 'modelRegistry',
    shortLabel: 'MODELS',
    icon: Layers,
    tag: 'GOVERNANCE'
  },
  {
    id: 'alpha_factory',
    labelKey: 'alphaFactory',
    shortLabel: 'FACTORY',
    icon: Compass,
    tag: 'DISCOVERY'
  },
  {
    id: 'strategy_lab',
    labelKey: 'strategyLab',
    shortLabel: 'LAB',
    icon: FlaskConical,
    tag: 'RESEARCH'
  },
  {
    id: 'macro_cockpit',
    labelKey: 'macroCockpit',
    shortLabel: 'MACRO',
    icon: Globe,
    tag: 'REGIME'
  },
  {
    id: 'macro_news_hub',
    labelKey: 'macroNewsHub',
    shortLabel: 'NEWS/LLM',
    icon: Newspaper,
    tag: 'SENTIMENT'
  },
  {
    id: 'fundamental_matrix',
    labelKey: 'fundamentalMatrix',
    shortLabel: 'FUND',
    icon: Table2,
    tag: 'SCREEN'
  },
  {
    id: 'alpha_portfolio',
    labelKey: 'alphaPortfolio',
    shortLabel: 'ALPHA',
    icon: TrendingUp,
    tag: 'BARRA'
  },
  {
    id: 'barra_risk_tca',
    labelKey: 'barraRiskTca',
    shortLabel: 'RISK/TCA',
    icon: ShieldAlert,
    tag: 'ANALYTICS'
  },
  {
    id: 'chart_station',
    labelKey: 'chartStation',
    shortLabel: 'CHART',
    icon: CandlestickChart,
    tag: 'TA'
  },
  {
    id: 'execution_blotter',
    labelKey: 'executionBlotter',
    shortLabel: 'BLOTTER',
    icon: ReceiptText,
    tag: 'OMS'
  }
];

export const SideDock: React.FC<SideDockProps> = ({
  activeModule,
  onSelectModule,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const { t } = useTranslation();

  return (
    <aside
      className={`h-[calc(100vh-3.5rem)] border-r border-white/10 bg-zinc-950/90 backdrop-blur-md flex flex-col justify-between transition-all duration-200 z-30 select-none ${
        isCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Navigation Modules */}
      <div className="p-3 flex flex-col gap-1.5 overflow-y-auto">
        <div className="px-2 py-1.5 text-[10px] uppercase font-mono tracking-wider text-zinc-300 font-semibold flex items-center justify-between">
          <span>{!isCollapsed && t.nav.quantModules}</span>
          <span className="text-[9px] bg-zinc-800 text-zinc-300 px-1 py-0.2 rounded font-mono">{t.nav.activeCount}</span>
        </div>

        {NAV_CONFIGS.map((item) => {
          const Icon = item.icon;
          const isActive = activeModule === item.id;
          const label = t.nav[item.labelKey];

          return (
            <button
              key={item.id}
              onClick={() => onSelectModule(item.id)}
              title={isCollapsed ? label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-mono transition-all duration-150 relative group ${
                isActive
                  ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-sm shadow-emerald-500/10 font-semibold'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5 border border-transparent'
              }`}
            >
              <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-emerald-400' : 'text-zinc-400 group-hover:text-zinc-200'}`} />

              {!isCollapsed && (
                <div className="flex-1 flex items-center justify-between overflow-hidden">
                  <span className="truncate">{label}</span>
                  <span className={`text-[9px] px-1 py-0.2 rounded font-mono ${
                    isActive ? 'bg-emerald-400/20 text-emerald-300' : 'bg-zinc-800/80 text-zinc-300'
                  }`}>
                    {item.tag}
                  </span>
                </div>
              )}

              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-emerald-400 rounded-r" />
              )}
            </button>
          );
        })}
      </div>

      {/* Footer controls & Collapse */}
      <div className="p-3 border-t border-white/5 flex flex-col gap-2">
        <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'justify-between'} px-1 text-xs text-zinc-400 font-mono`}>
          {!isCollapsed && (
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-[11px] text-zinc-400">{t.nav.pitSafeEngine}</span>
            </div>
          )}
          {onToggleCollapse && (
            <button
              onClick={onToggleCollapse}
              aria-label="Toggle SideDock Collapse"
              className="p-1 rounded hover:bg-white/5 text-zinc-400 hover:text-zinc-200"
            >
              {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
};
