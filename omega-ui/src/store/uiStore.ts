import { create } from 'zustand';
import { ModuleType } from '../layout/SideDock';
import { ScreenerFilters, TaskProgressEvent } from '../api/client';
import { Locale } from '../i18n/types';

export interface ActiveTask {
  taskId: string;
  taskType: 'DATA_INGESTION' | 'ALPHA_COMPUTATION' | 'PORTFOLIO_OPTIMIZATION' | 'STRATEGY_BACKTEST';
  progress: number;
  stage: string;
  message: string;
  status: 'PENDING' | 'RUNNING' | 'RECONNECTING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  startedAt: string;
  payload?: Record<string, unknown>;
  errorCode?: string;
  retryable?: boolean;
  originalTaskId?: string;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'info' | 'warning' | 'error';
  title: string;
  message?: string;
  timestamp: number;
}

export interface UiState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;

  theme: 'dark' | 'light';
  setTheme: (theme: 'dark' | 'light') => void;
  toggleTheme: () => void;

  activeModule: ModuleType;
  setActiveModule: (module: ModuleType) => void;

  activeSubTabs: Record<string, string>;
  activeFeatureId: string | null;
  setActiveSubTab: (module: string, subTab: string) => void;
  setActiveFeatureId: (featureId: string | null) => void;
  navigateToFeature: (module: ModuleType, subTab?: string, featureId?: string) => void;

  isSideDockCollapsed: boolean;
  toggleSideDockCollapse: () => void;
  setSideDockCollapsed: (collapsed: boolean) => void;

  selectedTicker: string;
  setSelectedTicker: (ticker: string) => void;

  chartInterval: string;
  setChartInterval: (interval: string) => void;
  setTimeframe: (timeframe: string) => void;

  screenerFilters: ScreenerFilters;
  setScreenerFilters: (filters: Partial<ScreenerFilters>) => void;
  resetScreenerFilters: () => void;

  isStreamingConnected: boolean;
  setStreamingConnected: (connected: boolean) => void;
  lastStreamMessageTimestamp: string | null;
  setLastStreamMessageTimestamp: (timestamp: string) => void;

  // Global Unified Ops Task & Drawer State
  tasks: Record<string, ActiveTask>;
  selectedTaskId: string | null;
  isOpsDrawerOpen: boolean;
  isTotpModalOpen: boolean;
  isKillSwitchEngaged: boolean;
  setTasks: (tasks: Record<string, ActiveTask> | ((prev: Record<string, ActiveTask>) => Record<string, ActiveTask>)) => void;
  upsertTask: (task: ActiveTask) => void;
  updateTaskProgress: (taskId: string, progressData: Partial<TaskProgressEvent>) => void;
  setSelectedTaskId: (taskId: string | null) => void;
  setIsOpsDrawerOpen: (open: boolean) => void;
  setIsTotpModalOpen: (open: boolean) => void;
  setIsKillSwitchEngaged: (engaged: boolean) => void;
  selectedJobId: string | null;
  selectedModelId: string | null;
  selectedPortfolioId: string | null;
  selectedOrderId: string | null;
  setSelectedJobId: (id: string | null) => void;
  setSelectedModelId: (id: string | null) => void;
  setSelectedPortfolioId: (id: string | null) => void;
  setSelectedOrderId: (id: string | null) => void;

  // Global Actionable Toast Notifications
  toasts: ToastMessage[];
  addToast: (toast: Omit<ToastMessage, 'id' | 'timestamp'>) => void;
  removeToast: (id: string) => void;
}

const DEFAULT_SCREENER_FILTERS: ScreenerFilters = {
  search: '',
  exchange: '',
  sector: '',
  minPiotroski: 0,
  minRoe: 0,
  minAltmanZ: 0,
  status: '',
  page: 1,
  pageSize: 25
};

const applyThemeToDom = (theme: 'dark' | 'light'): void => {
  if (typeof document !== 'undefined' && document.documentElement) {
    try {
      document.documentElement.setAttribute('data-theme', theme);
      if (theme === 'dark') {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
      } else {
        document.documentElement.classList.add('light');
        document.documentElement.classList.remove('dark');
      }
    } catch {
      // Ignore DOM access errors in non-browser environments
    }
  }
};

const getInitialLocale = (): Locale => {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      const saved = window.localStorage.getItem('omega_quant_locale');
      if (saved === 'vi' || saved === 'en') {
        return saved;
      }
    } catch {
      // Ignore storage access errors
    }
  }
  return 'vi'; // Default to Vietnamese for institutional Vietnam equities
};

const getInitialTheme = (): 'dark' | 'light' => {
  let theme: 'dark' | 'light' = 'dark';
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      const saved = window.localStorage.getItem('omega_quant_theme');
      if (saved === 'dark' || saved === 'light') {
        theme = saved;
      }
    } catch {
      // Ignore storage access errors
    }
  }
  applyThemeToDom(theme);
  return theme; // Default dark theme
};

export const useUiStore = create<UiState>((set) => ({
  locale: getInitialLocale(),
  setLocale: (locale) => {
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        window.localStorage.setItem('omega_quant_locale', locale);
      } catch {
        // Ignore storage access errors
      }
    }
    set({ locale });
  },
  toggleLocale: () =>
    set((state) => {
      const nextLocale: Locale = state.locale === 'vi' ? 'en' : 'vi';
      if (typeof window !== 'undefined' && window.localStorage) {
        try {
          window.localStorage.setItem('omega_quant_locale', nextLocale);
        } catch {
          // Ignore storage access errors
        }
      }
      return { locale: nextLocale };
    }),

  theme: getInitialTheme(),
  setTheme: (theme) => {
    applyThemeToDom(theme);
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        window.localStorage.setItem('omega_quant_theme', theme);
      } catch {
        // Ignore storage access errors
      }
    }
    set({ theme });
  },
  toggleTheme: () =>
    set((state) => {
      const nextTheme = state.theme === 'dark' ? 'light' : 'dark';
      applyThemeToDom(nextTheme);
      if (typeof window !== 'undefined' && window.localStorage) {
        try {
          window.localStorage.setItem('omega_quant_theme', nextTheme);
        } catch {
          // Ignore storage access errors
        }
      }
      return { theme: nextTheme };
    }),

  activeModule: 'macro_cockpit',
  setActiveModule: (module) => set({ activeModule: module }),

  activeSubTabs: {
    control_center: 'overview'
  },
  activeFeatureId: null,
  setActiveSubTab: (module, subTab) =>
    set((state) => ({
      activeSubTabs: {
        ...state.activeSubTabs,
        [module]: subTab
      }
    })),
  setActiveFeatureId: (activeFeatureId) => set({ activeFeatureId }),
  navigateToFeature: (module, subTab, featureId) =>
    set((state) => ({
      activeModule: module,
      activeSubTabs: subTab
        ? {
            ...state.activeSubTabs,
            [module]: subTab
          }
        : state.activeSubTabs,
      activeFeatureId: featureId ?? null
    })),

  isSideDockCollapsed: false,
  toggleSideDockCollapse: () => set((state) => ({ isSideDockCollapsed: !state.isSideDockCollapsed })),
  setSideDockCollapsed: (collapsed) => set({ isSideDockCollapsed: collapsed }),

  selectedTicker: 'FPT',
  setSelectedTicker: (ticker) => set({ selectedTicker: ticker.toUpperCase() }),

  chartInterval: '1D',
  setChartInterval: (interval) => set({ chartInterval: interval }),
  setTimeframe: (timeframe) => set({ chartInterval: timeframe }),

  screenerFilters: DEFAULT_SCREENER_FILTERS,
  setScreenerFilters: (newFilters) =>
    set((state) => ({
      screenerFilters: {
        ...state.screenerFilters,
        ...newFilters,
        // Reset page to 1 if filter parameters change without explicit page change
        page: newFilters.page !== undefined ? newFilters.page : 1
      }
    })),
  resetScreenerFilters: () => set({ screenerFilters: DEFAULT_SCREENER_FILTERS }),

  isStreamingConnected: false,
  setStreamingConnected: (connected) => set({ isStreamingConnected: connected }),
  lastStreamMessageTimestamp: null,
  setLastStreamMessageTimestamp: (timestamp) => set({ lastStreamMessageTimestamp: timestamp }),

  // Global Unified Ops Task & Drawer State
  tasks: {},
  selectedTaskId: null,
  isOpsDrawerOpen: false,
  isTotpModalOpen: false,
  isKillSwitchEngaged: false,
  setTasks: (tasksOrUpdater) =>
    set((state) => ({
      tasks: typeof tasksOrUpdater === 'function' ? tasksOrUpdater(state.tasks) : tasksOrUpdater
    })),
  upsertTask: (task) =>
    set((state) => ({
      tasks: { ...state.tasks, [task.taskId]: task }
    })),
  updateTaskProgress: (taskId, data) =>
    set((state) => {
      const current = state.tasks[taskId];
      if (!current) return state;
       if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(current.status)) return state;
       const receipt = data.payload?.receipt as { task_id?: string; status?: string; request_fingerprint?: string; output_sha256?: string } | undefined;
       const completed = data.event_type === 'COMPLETE' && receipt?.task_id === taskId && receipt.status === 'COMPLETED' && Boolean(receipt.request_fingerprint && receipt.output_sha256);
       const status = data.event_type === 'ERROR' ? 'FAILED' : data.event_type === 'CANCELLED' ? 'CANCELLED' : completed ? 'COMPLETED' : 'RUNNING';
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...current,
            progress: typeof data.progress === 'number' ? Math.max(0, Math.min(100, data.progress)) : current.progress,
            stage: data.stage || current.stage,
            message: data.message || current.message,
            status,
            payload: data.payload || current.payload,
            errorCode: typeof data.payload?.error_code === 'string' ? data.payload.error_code : current.errorCode,
            retryable: typeof data.payload?.retryable === 'boolean' ? data.payload.retryable : current.retryable
          }
        }
      };
    }),
  setSelectedTaskId: (taskId) => set({ selectedTaskId: taskId }),
  setIsOpsDrawerOpen: (open) => set({ isOpsDrawerOpen: open }),
  setIsTotpModalOpen: (open) => set({ isTotpModalOpen: open }),
  setIsKillSwitchEngaged: (engaged) => set({ isKillSwitchEngaged: engaged }),
  selectedJobId: null,
  selectedModelId: null,
  selectedPortfolioId: null,
  selectedOrderId: null,
  setSelectedJobId: (selectedJobId) => set({ selectedJobId }),
  setSelectedModelId: (selectedModelId) => set({ selectedModelId }),
  setSelectedPortfolioId: (selectedPortfolioId) => set({ selectedPortfolioId }),
  setSelectedOrderId: (selectedOrderId) => set({ selectedOrderId }),

  // Global Actionable Toast Notifications
  toasts: [],
  addToast: (toast) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const newToast: ToastMessage = {
      ...toast,
      id,
      timestamp: Date.now()
    };
    set((state) => ({
      toasts: [...state.toasts.slice(-4), newToast]
    }));
    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id)
      }));
    }, 4500);
  },
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id)
    }))
}));

// Self-contained Zustand subscriber to continuously sync data-theme to DOM
useUiStore.subscribe((state) => {
  applyThemeToDom(state.theme);
});
