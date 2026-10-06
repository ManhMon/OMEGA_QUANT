import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../App';
import { useUiStore } from '../store/uiStore';
import type { ModuleType } from '../layout/SideDock';
import { useTranslation } from '../i18n';
import { useLLMConfig } from '../hooks/useLLMConfig';
import * as useLLMConfigModule from '../hooks/useLLMConfig';
import { usePreTradeImpact } from '../hooks/useBarraRiskTca';
import { useCopilot } from '../hooks/useCopilot';
import * as useCopilotModule from '../hooks/useCopilot';
import { unavailableMessage } from '../hooks/useUnavailableQuery';
import { en } from '../i18n/en';
import { vi as vietnamese } from '../i18n/vi';
import { LightweightChartContainer } from '../modules/chart_station/LightweightChartContainer';
import { OrderbookDepth } from '../modules/chart_station/OrderbookDepth';
import { OmniQuantCopilotDrawer } from '../modules/copilot/OmniQuantCopilotDrawer';
import { LLMConfigModal, containModalFocus } from '../modules/copilot/LLMConfigModal';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { MultiProfileLLMConfigPayload } from '../api/client';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const initialState = useUiStore.getState();
const originalDialogDescriptors = Object.getOwnPropertyDescriptors(HTMLDialogElement.prototype);
const originalFocus = HTMLElement.prototype.focus;
let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
let storageSnapshot: [string, string][];
const closed = vi.fn();

const mockConfigPayload: MultiProfileLLMConfigPayload = {
  global_profile: {
    provider: 'openai',
    model: 'gpt-4o',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  alpha_quant: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.1,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  news_sentiment: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
  macro_micro: {
    provider: 'openai',
    model: 'gpt-4o',
    api_key: 'sk-test-valid-key-alpha-omega',
    base_url: 'https://api.openai.com/v1',
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 30,
    enabled: true,
  },
};

const mockCopilotAvailable = {
  synthesis: {
    holistic_verdict: 'ACCUMULATE_BULLISH',
    verdict_reasoning_en: 'Bullish regime verified across multi-factor models',
    verdict_reasoning_vi: 'Nhận định tích cực dựa trên mô hình đa nhân tố',
    executive_quant_score: 92.5,
    focus_symbol: 'FPT',
    screener: {
      target_ticker_profile: {
        piotroski_f: 8,
        altman_z: 3.42,
        roe_pct: 26.5,
      },
    },
    risk_tca: {
      cvar_99_pct: 2.68,
      factor_risk_pct: 11.25,
      specific_risk_pct: 3.57,
      fastest_gateway: 'VNDIRECT_DMA',
    },
  } as any,
  isSynthesisLoading: false,
  isUnavailable: false,
  refetchSynthesis: vi.fn(),
  recommendations: [],
  chatHistory: [],
  isAsking: false,
  sendQuery: vi.fn(),
  clearChat: vi.fn(),
  dispatchAction: vi.fn(),
  executingActionId: null,
  streamEvents: [],
  isSseConnected: true,
};

beforeEach(() => {
  storageSnapshot = Object.entries(window.localStorage);
  vi.useFakeTimers();
  HTMLElement.prototype.focus = function (this: HTMLElement, ...args: any[]) {
    const dialog = this.closest('dialog');
    if (dialog && !dialog.open) {
      (dialog as any)._pendingAutoFocus = this;
      return;
    }
    return originalFocus.apply(this, args as any);
  };
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      writable: true,
      value: function (this: HTMLDialogElement) {
        this.open = true;
        const pending = (this as any)._pendingAutoFocus;
        delete (this as any)._pendingAutoFocus;
        const autoFocusTarget = pending || Array.from(this.querySelectorAll<HTMLElement>('*')).find(
          (el) => el.hasAttribute('autofocus') || (el as any).autofocus === true
        ) || this.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (autoFocusTarget) {
          autoFocusTarget.focus();
        } else {
          this.focus();
        }
        const onKeyDown = (e: KeyboardEvent) => {
          if (e.key === 'Escape' && this.open) {
            const cancelEvt = new Event('cancel', { cancelable: true });
            this.dispatchEvent(cancelEvt);
            if (!cancelEvt.defaultPrevented) {
              this.close();
            }
          }
        };
        if ((this as any)._cleanupKeyDown) {
          (this as any)._cleanupKeyDown();
        }
        this.addEventListener('keydown', onKeyDown);
        (this as any)._cleanupKeyDown = () => this.removeEventListener('keydown', onKeyDown);
      },
    },
    close: {
      configurable: true,
      writable: true,
      value: function (this: HTMLDialogElement) {
        this.open = false;
        if (typeof (this as any)._cleanupKeyDown === 'function') {
          (this as any)._cleanupKeyDown();
          delete (this as any)._cleanupKeyDown;
        }
        this.dispatchEvent(new Event('close'));
      },
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Injected offline failure')));
  vi.stubGlobal('EventSource', class {
    close = closed;
    addEventListener() {}
    removeEventListener() {}
  });
  useUiStore.setState({ ...initialState, locale: 'en', activeModule: 'pipeline_console', tasks: {}, toasts: [] }, true);
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.clear();
  }
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
  document.body.innerHTML = '';
  useUiStore.setState(initialState, true);
  window.localStorage.clear();
  for (const [key, value] of storageSnapshot) window.localStorage.setItem(key, value);
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  HTMLElement.prototype.focus = originalFocus;
  for (const key of ['showModal', 'close']) {
    if (originalDialogDescriptors[key]) {
      Object.defineProperty(HTMLDialogElement.prototype, key, originalDialogDescriptors[key]);
    } else {
      Reflect.deleteProperty(HTMLDialogElement.prototype, key);
    }
  }
});
const settle = async (ms = 50) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

it('mounts every real App route under network failure and closes streams', async () => {
  act(() => root.render(<App />));
  const modules: ModuleType[] = ['pipeline_console', 'control_center', 'model_registry', 'alpha_factory',
    'strategy_lab', 'macro_cockpit', 'macro_news_hub', 'fundamental_matrix', 'alpha_portfolio',
    'barra_risk_tca', 'chart_station', 'execution_blotter'];
  for (const module of modules) {
    act(() => useUiStore.getState().setActiveModule(module));
    await settle();
    expect(container.querySelector('main')?.textContent).not.toBe('');
    if (module === 'pipeline_console') {
      const section = container.querySelector('main section')!;
      expect(section.getAttribute('aria-label')).toBe('VALIDATED RESEARCH PIPELINE');
      expect(section.querySelector('[role="status"]')?.textContent).toBe('This module is unavailable in this build.');
      expect(section.querySelectorAll('button, form, progress')).toHaveLength(0);
      act(() => useUiStore.getState().setLocale('vi'));
      expect(section.getAttribute('aria-label')).toBe('PIPELINE NGHIÊN CỨU ĐÃ XÁC THỰC');
      act(() => useUiStore.getState().setLocale('en'));
    }
    if (module === 'barra_risk_tca') {
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(unavailableMessage);
      expect(container.textContent).not.toContain('BARRA_VN_V3');
    }
  }
  for (const label of ['Copilot', 'Configuration']) {
    act(() => Array.from(container.querySelectorAll('button')).find((button) => button.textContent === label)!.click());
    await settle();
    const dialog = container.querySelector('[aria-modal="true"]')!;
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);
    expect(dialog).toBeInstanceOf(HTMLDialogElement);
    expect((dialog as HTMLDialogElement).open).toBe(true);
    act(() => useUiStore.getState().setLocale('vi'));
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe(vietnamese.common.integrationUnavailable);
    expect(dialog.getAttribute('aria-label')).toBe(label === 'Configuration'
      ? vietnamese.copilot.configModalTitle : vietnamese.copilot.drawerTitle);
    act(() => dialog.dispatchEvent(new Event('cancel', { cancelable: true })));
    act(() => useUiStore.getState().setLocale('en'));
    expect(container.querySelector('[aria-modal="true"]')).toBeNull();
  }
  expect(useUiStore.getState().isStreamingConnected).toBe(false);
  act(() => root.render(null));
  expect(closed).toHaveBeenCalled();
});

it('rejects stub actions without network calls, success data or secret echo', async () => {
  let config!: ReturnType<typeof useLLMConfig>;
  let impact!: ReturnType<typeof usePreTradeImpact>;
  let copilot!: ReturnType<typeof useCopilot>;
  function Probe() {
    config = useLLMConfig();
    impact = usePreTradeImpact();
    copilot = useCopilot(true);
    const { t } = useTranslation();
    return <p>{t.common.retry}</p>;
  }
  act(() => root.render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>));
  await settle();
  expect(config.isError).toBe(true);
  const profile = { provider: 'custom', model: 'test', api_key: 'DO_NOT_ECHO', base_url: 'https://user:password@example.com',
    temperature: 0, max_tokens: 1, timeout_seconds: 1, enabled: true };
  await act(async () => {
    await expect(config.saveConfig({ global_profile: profile, alpha_quant: profile, news_sentiment: profile, macro_micro: profile })).rejects.toThrow(unavailableMessage);
    await expect(config.testProbe({ ...profile, profile_key: 'global_profile' })).rejects.toThrow(unavailableMessage);
    await expect(config.fetchModels(profile)).rejects.toThrow(unavailableMessage);
    await expect(impact.mutateAsync({ symbol: '', order_size: 0, average_daily_volume: 0, arrival_price: 0 })).rejects.toThrow(unavailableMessage);
    copilot.sendQuery('DO_NOT_ECHO');
    copilot.dispatchAction({ id: 'invalid' } as Parameters<typeof copilot.dispatchAction>[0]);
  });
  await settle();
  expect(impact.data).toBeUndefined();
  expect(config.config).toBeUndefined();
  expect(copilot.recommendations).toEqual([]);
  expect(copilot.chatHistory[0].textEn).toBe(unavailableMessage);
  expect(JSON.stringify(copilot.chatHistory)).not.toContain('DO_NOT_ECHO');
  expect(fetch).not.toHaveBeenCalled();
  act(() => useUiStore.getState().setLocale('vi'));
  expect(container.textContent).not.toBe('Retry');
});

it('wraps modal boundaries while ignoring disabled, hidden and negative tab stops', () => {
  const dialog = document.createElement('dialog');
  dialog.open = true;
  dialog.tabIndex = -1;
  dialog.innerHTML = '<button>first</button><button disabled>disabled</button><button hidden>hidden</button><button tabindex="-1">skip</button><button>last</button>';
  container.appendChild(dialog);
  const buttons = Array.from(dialog.querySelectorAll('button'));
  for (const button of buttons) vi.spyOn(button, 'getClientRects').mockReturnValue(button.hidden ? [] as unknown as DOMRectList : [{}] as unknown as DOMRectList);
  const key = (shiftKey = false, value = 'Tab') => {
    const preventDefault = vi.fn();
    containModalFocus({ key: value, shiftKey, currentTarget: dialog, preventDefault } as unknown as ReactKeyboardEvent<HTMLDialogElement>);
    return preventDefault;
  };
  buttons[0].focus();
  expect(key()).not.toHaveBeenCalled();
  expect(key(false, 'Escape')).not.toHaveBeenCalled();
  expect(key(true)).toHaveBeenCalled();
  expect(document.activeElement).toBe(buttons[4]);
  expect(key()).toHaveBeenCalled();
  expect(document.activeElement).toBe(buttons[0]);
  dialog.innerHTML = '';
  expect(key()).toHaveBeenCalled();
  expect(document.activeElement).toBe(dialog);
});

it('renders unavailable chart components without synthetic data claims', () => {
  act(() => root.render(<>
    <LightweightChartContainer symbol="FPT" candles={[]} showSMA showEMA showVolume alphaMarkers={[]} />
    <OrderbookDepth isLoading={false} />
  </>));
  expect(container.querySelectorAll('[role="status"]')).toHaveLength(2);
  expect(container.textContent).toBe(unavailableMessage.repeat(2));
});

it('manages native HTMLDialogElement lifecycle, showModal autofocus, cancel Escape forwarding and focus restoration in unavailable mode', async () => {
  const onClose = vi.fn();
  function Harness({ isOpen, isDrawer }: { isOpen: boolean; isDrawer: boolean }) {
    return (
      <QueryClientProvider client={client}>
        <div>
          <button type="button" id="trigger-btn">Trigger</button>
          {isDrawer ? (
            <OmniQuantCopilotDrawer isOpen={isOpen} onClose={onClose} />
          ) : (
            <LLMConfigModal isOpen={isOpen} onClose={onClose} />
          )}
        </div>
      </QueryClientProvider>
    );
  }

  // 1. Copilot Drawer unavailable lifecycle
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  const trigger = container.querySelector('#trigger-btn') as HTMLButtonElement;
  trigger.focus();
  expect(document.activeElement).toBe(trigger);

  act(() => root.render(<Harness isOpen={true} isDrawer={true} />));
  await settle();
  const copilotDialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(copilotDialog).toBeInstanceOf(HTMLDialogElement);
  expect(copilotDialog.open).toBe(true);

  // Initial focus modeled via showModal autofocus
  const cancelBtn = Array.from(copilotDialog.querySelectorAll('button')).find(
    (b) => (b as any).autofocus || b.hasAttribute('autofocus') || b.textContent === en.common.cancel
  ) as HTMLButtonElement;
  expect(cancelBtn).not.toBeNull();
  expect(document.activeElement).toBe(cancelBtn);

  // Escape keydown forwarding to cancel event
  act(() => {
    cancelBtn.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restoration after close
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
  expect(container.querySelector('dialog')).toBeNull();

  // 2. Config Modal unavailable lifecycle
  onClose.mockClear();
  trigger.focus();
  expect(document.activeElement).toBe(trigger);

  act(() => root.render(<Harness isOpen={true} isDrawer={false} />));
  await settle();
  const configDialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(configDialog.open).toBe(true);

  const configCancelBtn = Array.from(configDialog.querySelectorAll('button')).find(
    (b) => (b as any).autofocus || b.hasAttribute('autofocus') || b.textContent === en.common.cancel
  ) as HTMLButtonElement;
  expect(configCancelBtn).not.toBeNull();
  expect(document.activeElement).toBe(configCancelBtn);

  // Native cancel event triggers onClose
  act(() => {
    configDialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restored on close
  act(() => root.render(<Harness isOpen={false} isDrawer={false} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
  expect(container.querySelector('dialog')).toBeNull();
});

it('manages native HTMLDialogElement lifecycle, autofocus, Escape forwarding and focus restoration in available mode', async () => {
  vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue(mockCopilotAvailable);
  const fetchModelsMock = vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' });
  const testProbeMock = vi.fn().mockResolvedValue({ status: 'success', latency_ms: 20, message: 'OK' });
  const saveConfigMock = vi.fn().mockResolvedValue(mockConfigPayload);
  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: saveConfigMock,
    isSaving: false,
    testProbe: testProbeMock,
    fetchModels: fetchModelsMock,
    isFetchingModels: false,
  });

  const onClose = vi.fn();
  function Harness({ isOpen, isDrawer }: { isOpen: boolean; isDrawer: boolean }) {
    return (
      <QueryClientProvider client={client}>
        <div>
          <button type="button" id="trigger-btn">Trigger</button>
          {isDrawer ? (
            <OmniQuantCopilotDrawer isOpen={isOpen} onClose={onClose} />
          ) : (
            <LLMConfigModal isOpen={isOpen} onClose={onClose} />
          )}
        </div>
      </QueryClientProvider>
    );
  }

  // 1. Available Copilot Drawer
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  const trigger = container.querySelector('#trigger-btn') as HTMLButtonElement;
  trigger.focus();

  act(() => root.render(<Harness isOpen={true} isDrawer={true} />));
  await settle();
  const drawerDialog = container.querySelector('dialog[data-drawer]') as HTMLDialogElement;
  expect(drawerDialog.open).toBe(true);

  // Initial focus lands on close button with autofocus
  const drawerCloseBtn = drawerDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(drawerCloseBtn).not.toBeNull();
  expect(document.activeElement).toBe(drawerCloseBtn);

  // Escape keydown forwarding
  act(() => {
    drawerCloseBtn.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  // Focus restored on close
  act(() => root.render(<Harness isOpen={false} isDrawer={true} />));
  await settle();
  expect(document.activeElement).toBe(trigger);

  // 2. Available Config Modal
  onClose.mockClear();
  trigger.focus();

  act(() => root.render(<Harness isOpen={true} isDrawer={false} />));
  await settle();
  const configDialog = container.querySelector('dialog[aria-label="' + en.copilot.configModalTitle + '"]') as HTMLDialogElement;
  expect(configDialog.open).toBe(true);

  const configCloseBtn = configDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(configCloseBtn).not.toBeNull();
  expect(document.activeElement).toBe(configCloseBtn);

  // Dispatch cancel event
  act(() => {
    configDialog.dispatchEvent(new Event('cancel', { cancelable: true }));
  });
  expect(onClose).toHaveBeenCalledTimes(1);

  act(() => root.render(<Harness isOpen={false} isDrawer={false} />));
  await settle();
  expect(document.activeElement).toBe(trigger);
});

it('restores focus through nested config over copilot stack in App', async () => {
  vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue(mockCopilotAvailable);
  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: vi.fn().mockResolvedValue(mockConfigPayload),
    isSaving: false,
    testProbe: vi.fn().mockResolvedValue({ status: 'success', latency_ms: 10, message: 'OK' }),
    fetchModels: vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' }),
    isFetchingModels: false,
  });

  act(() => root.render(<App />));
  await settle();

  // Focus top-level copilot trigger
  const copilotBtn = Array.from(container.querySelectorAll('header button')).find(
    (btn) => btn.textContent === 'Copilot'
  ) as HTMLButtonElement;
  copilotBtn.focus();
  expect(document.activeElement).toBe(copilotBtn);

  // Open Copilot Drawer
  act(() => copilotBtn.click());
  await settle();
  const copilotDialog = container.querySelector('dialog[data-drawer]') as HTMLDialogElement;
  expect(copilotDialog.open).toBe(true);
  const copilotCloseBtn = copilotDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(document.activeElement).toBe(copilotCloseBtn);

  // Locate and focus nested Configuration button inside Copilot Drawer
  const configSettingsBtn = copilotDialog.querySelector('button[title="' + en.copilot.configModalTitle + '"]') as HTMLButtonElement;
  expect(configSettingsBtn).not.toBeNull();
  configSettingsBtn.focus();
  expect(document.activeElement).toBe(configSettingsBtn);

  // Open Configuration Modal over Copilot Drawer
  act(() => configSettingsBtn.click());
  await settle();

  const configDialog = Array.from(container.querySelectorAll('dialog')).find(
    (d) => d.getAttribute('aria-label') === en.copilot.configModalTitle
  ) as HTMLDialogElement;
  expect(configDialog.open).toBe(true);
  const configCloseBtn = configDialog.querySelector('button[aria-label="Close"]') as HTMLButtonElement;
  expect(document.activeElement).toBe(configCloseBtn);

  // Close nested Configuration Modal
  act(() => configCloseBtn.click());
  await settle();

  // Focus restored back to the Settings button inside Copilot Drawer
  expect(document.activeElement).toBe(configSettingsBtn);

  // Close Copilot Drawer
  act(() => copilotCloseBtn.click());
  await settle();

  // Focus restored back to the original Copilot header button
  expect(document.activeElement).toBe(copilotBtn);
  expect(container.querySelector('dialog[data-drawer]')).toBeNull();
});

it('handles branch transitions without leaving stranded open dialogs', async () => {
  const onClose = vi.fn();
  function TransitionHarness({ isUnavailable, isDrawer }: { isUnavailable: boolean; isDrawer: boolean }) {
    vi.spyOn(useCopilotModule, 'useCopilot').mockReturnValue({
      ...mockCopilotAvailable,
      isUnavailable,
    });
    vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
      config: isUnavailable ? undefined : mockConfigPayload,
      isLoading: false,
      isError: isUnavailable,
      saveConfig: vi.fn(),
      isSaving: false,
      testProbe: vi.fn(),
      fetchModels: vi.fn(),
      isFetchingModels: false,
    });
    return (
      <QueryClientProvider client={client}>
        {isDrawer ? (
          <OmniQuantCopilotDrawer isOpen={true} onClose={onClose} />
        ) : (
          <LLMConfigModal isOpen={true} onClose={onClose} />
        )}
      </QueryClientProvider>
    );
  }

  // 1. Drawer transition from available -> unavailable -> available
  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  act(() => root.render(<TransitionHarness isUnavailable={true} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);

  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={true} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  // 2. Config Modal transition from available -> unavailable -> available
  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();

  act(() => root.render(<TransitionHarness isUnavailable={true} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(en.common.integrationUnavailable);

  act(() => root.render(<TransitionHarness isUnavailable={false} isDrawer={false} />));
  await settle();
  expect(container.querySelectorAll('dialog[open]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it('cleans up dialogs and timers properly on unmount', async () => {
  const closeSpy = vi.spyOn(HTMLDialogElement.prototype, 'close');
  function UnmountHarness() {
    return <OmniQuantCopilotDrawer isOpen={true} onClose={vi.fn()} />;
  }
  act(() => root.render(<UnmountHarness />));
  await settle();
  const dialog = container.querySelector('dialog') as HTMLDialogElement;
  expect(dialog).not.toBeNull();
  expect(dialog.open).toBe(true);

  act(() => root.unmount());
  expect(closeSpy).toHaveBeenCalled();
  expect(container.querySelector('dialog')).toBeNull();
});

it('injects missing error message for model catalog and probe, and tests localized apply-to-all in EN and VI', async () => {
  const credentialErrorUrl = 'https://admin:SECRET_PASSWORD_1234@upstream.secure.bank.internal/api';
  const fetchModelsMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));
  const testProbeMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));
  const saveConfigMock = vi.fn().mockRejectedValue(new Error(credentialErrorUrl));

  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: mockConfigPayload,
    isLoading: false,
    isError: false,
    saveConfig: saveConfigMock,
    isSaving: false,
    testProbe: testProbeMock,
    fetchModels: fetchModelsMock,
    isFetchingModels: false,
  });

  function ConfigHarness() {
    return (
      <QueryClientProvider client={client}>
        <LLMConfigModal isOpen={true} onClose={vi.fn()} />
      </QueryClientProvider>
    );
  }

  // 1. English localized notifications and fallbacks
  useUiStore.setState({ locale: 'en' });
  act(() => root.render(<ConfigHarness />));
  await settle();

  // Model catalog probe error with injected credential URL
  const fetchBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.fetchModelsBtn)
  ) as HTMLButtonElement;
  expect(fetchBtnEn).not.toBeNull();
  act(() => fetchBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.modelCatalogFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Connection probe error with injected credential URL
  const testConnBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.testConnectionBtn)
  ) as HTMLButtonElement;
  expect(testConnBtnEn).not.toBeNull();
  act(() => testConnBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.probeFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Apply to all profiles notification
  const applyAllBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.applyToAllBtn)
  ) as HTMLButtonElement;
  expect(applyAllBtnEn).not.toBeNull();
  act(() => applyAllBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.profilesSynchronized);

  // Save config error with injected credential URL
  const saveBtnEn = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(en.copilot.saveConfigBtn)
  ) as HTMLButtonElement;
  expect(saveBtnEn).not.toBeNull();
  act(() => saveBtnEn.click());
  await settle();
  expect(container.textContent).toContain(en.copilot.saveFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // 2. Vietnamese localized notifications and fallbacks
  act(() => useUiStore.getState().setLocale('vi'));
  await settle();

  // Model catalog probe error fallback VI
  const fetchBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.fetchModelsBtn)
  ) as HTMLButtonElement;
  act(() => fetchBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.modelCatalogFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Connection probe error fallback VI
  const testConnBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.testConnectionBtn)
  ) as HTMLButtonElement;
  act(() => testConnBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.probeFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

  // Apply to all profiles notification VI
  const applyAllBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.applyToAllBtn)
  ) as HTMLButtonElement;
  act(() => applyAllBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.profilesSynchronized);

  // Save config error fallback VI
  const saveBtnVi = Array.from(container.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(vietnamese.copilot.saveConfigBtn)
  ) as HTMLButtonElement;
  expect(saveBtnVi).not.toBeNull();
  act(() => saveBtnVi.click());
  await settle();
  expect(container.textContent).toContain(vietnamese.copilot.saveFailed);
  expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');
});

it('strictly guards against backend secret echo across locales in copilot and config', async () => {
  const secretKey = 'CRITICAL_SECRET_KEY_NEVER_ECHO_TOKEN_999';
  const secretHost = 'https://admin:SECRET_PASSWORD_1234@upstream.secure.bank.vn';
  const sensitiveConfig: MultiProfileLLMConfigPayload = {
    global_profile: { ...mockConfigPayload.global_profile, api_key: secretKey, base_url: secretHost },
    alpha_quant: { ...mockConfigPayload.alpha_quant, api_key: secretKey, base_url: secretHost },
    news_sentiment: { ...mockConfigPayload.news_sentiment, api_key: secretKey, base_url: secretHost },
    macro_micro: { ...mockConfigPayload.macro_micro, api_key: secretKey, base_url: secretHost },
  };

  vi.spyOn(useLLMConfigModule, 'useLLMConfig').mockReturnValue({
    config: sensitiveConfig,
    isLoading: false,
    isError: false,
    saveConfig: vi.fn().mockResolvedValue(sensitiveConfig),
    isSaving: false,
    testProbe: vi.fn().mockResolvedValue({ status: 'success', latency_ms: 15, message: 'OK' }),
    fetchModels: vi.fn().mockResolvedValue({ status: 'success', models: [], source: 'live' }),
    isFetchingModels: false,
  });

  for (const loc of ['en', 'vi'] as const) {
    act(() => useUiStore.setState({ locale: loc }));
    act(() => root.render(
      <QueryClientProvider client={client}>
        <LLMConfigModal isOpen={true} onClose={vi.fn()} />
      </QueryClientProvider>
    ));
    await settle();

    // Verify raw secret key and embedded password are never echoed into DOM text
    expect(container.textContent).not.toContain(secretKey);
    expect(container.textContent).not.toContain('SECRET_PASSWORD_1234');

    // Input must be masked password type by default
    const keyInput = container.querySelector('input[type="password"]') as HTMLInputElement;
    expect(keyInput).not.toBeNull();

    // Verification of localized status indicator
    const expectedStatus = loc === 'vi' ? vietnamese.copilot.hasKeySet : en.copilot.hasKeySet;
    expect(container.textContent).toContain(expectedStatus);
  }
});
