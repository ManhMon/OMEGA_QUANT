import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { useUiStore } from '../store/uiStore';
import type { ModuleType } from '../layout/SideDock';

vi.mock('../layout/SideDock', () => ({ SideDock: () => <nav aria-label="Modules" /> }));
vi.mock('../modules/macro_cockpit/LandingDatabaseHub', () => ({ LandingDatabaseHub: () => <p>LandingDatabaseHub mounted</p> }));
vi.mock('../modules/fundamental_matrix/FundamentalMatrixView', () => ({ FundamentalMatrixView: () => <p>fundamental_matrix mounted</p> }));
vi.mock('../modules/barra_risk_tca/BarraRiskTcaAnalyticsView', () => ({ BarraRiskTcaAnalyticsView: () => <p>barra_risk_tca mounted</p> }));
vi.mock('../modules/chart_station/ChartStationView', () => ({ ChartStationView: () => <p>chart_station mounted</p> }));
vi.mock('../modules/execution_blotter/ExecutionBlotterView', () => ({ ExecutionBlotterView: () => <p>execution_blotter mounted</p> }));
vi.mock('../modules/control_center/QuantControlCenter', () => ({ QuantControlCenter: () => <p>control_center mounted</p> }));
vi.mock('../modules/model_registry/ModelRegistryView', () => ({ ModelRegistryView: () => <p>model_registry mounted</p> }));
vi.mock('../modules/strategy_lab/StrategyLabView', () => ({ StrategyLabView: () => <p>strategy_lab mounted</p> }));
vi.mock('../modules/alpha_factory/AlphaFactoryDiscoveryStation', () => ({ AlphaFactoryDiscoveryStation: () => <p>alpha_factory mounted</p> }));
vi.mock('../modules/alpha_portfolio/AlphaPortfolioStationView', () => ({ AlphaPortfolioStationView: () => <p>alpha_portfolio mounted</p> }));
vi.mock('../modules/copilot/OmniQuantCopilotDrawer', () => ({ OmniQuantCopilotDrawer: ({ isOpen }: { isOpen: boolean }) => isOpen ? <aside data-drawer>Copilot open</aside> : null }));
vi.mock('../modules/copilot/LLMConfigModal', () => ({ containModalFocus: vi.fn(), LLMConfigModal: ({ isOpen }: { isOpen: boolean }) => isOpen ? <div role="dialog">Configuration open</div> : null }));
vi.mock('../hooks/useRealtimeStream', () => ({ useRealtimeStream: vi.fn() }));
vi.mock('../hooks/useControlOps', () => ({ useControlOps: () => ({
  tasks: useUiStore((state) => state.tasks),
  selectedTaskId: useUiStore((state) => state.selectedTaskId),
  setSelectedTaskId: useUiStore((state) => state.setSelectedTaskId),
  isDrawerOpen: useUiStore((state) => state.isOpsDrawerOpen),
  setIsDrawerOpen: useUiStore((state) => state.setIsOpsDrawerOpen),
}) }));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const modules: ModuleType[] = [
  'pipeline_console', 'control_center', 'model_registry', 'alpha_factory',
  'strategy_lab', 'macro_cockpit', 'macro_news_hub', 'fundamental_matrix', 'alpha_portfolio',
];
const initialState = useUiStore.getState();
let container: HTMLDivElement;
let root: Root;
let unmounted: boolean;
let dialogDescriptors: PropertyDescriptorMap;
const press = (key = '2', options: KeyboardEventInit = {}, target: EventTarget = window) => {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...options });
  act(() => { target.dispatchEvent(event); });
  return event;
};

beforeEach(() => {
  useUiStore.setState({ ...initialState, activeModule: 'pipeline_console', locale: 'en', toasts: [], tasks: {} }, true);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  unmounted = false;
  dialogDescriptors = Object.getOwnPropertyDescriptors(HTMLDialogElement.prototype);
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value: function () { this.open = true; } },
    close: { configurable: true, value: function () { this.open = false; } },
  });
  act(() => root.render(<App />));
});
afterEach(() => {
  if (!unmounted) act(() => root.unmount());
  for (const key of ['showModal', 'close']) {
    if (dialogDescriptors[key]) Object.defineProperty(HTMLDialogElement.prototype, key, dialogDescriptors[key]);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, key);
  }
  document.body.replaceChildren();
  useUiStore.setState(initialState, true);
  vi.restoreAllMocks();
});

describe('App remediation', () => {
  it('allows disabling character shortcuts without swallowing keys', () => {
    const toggle = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    act(() => toggle.click());
    expect(toggle.checked).toBe(false);
    for (let digit = 1; digit <= 9; digit++) expect(press(String(digit)).defaultPrevented).toBe(false);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
    act(() => toggle.click());
    press();
    expect(useUiStore.getState().activeModule).toBe('control_center');
  });

  it.each(['en', 'vi'] as const)('keeps shortcuts disabled after switching to %s with an accessible label', (locale) => {
    const toggle = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    act(() => toggle.click());
    act(() => useUiStore.getState().setLocale(locale));
    expect(toggle.labels?.[0]?.textContent?.trim()).toBe(locale === 'vi' ? 'Bật phím tắt chữ số' : 'Enable digit shortcuts');
    expect(toggle.checked).toBe(false);
    act(() => useUiStore.getState().setActiveModule('control_center'));
    act(() => useUiStore.getState().setActiveModule('pipeline_console'));
    expect(toggle.checked).toBe(false);
    expect(press().defaultPrevented).toBe(false);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each(modules)('routes digit shortcut to %s', (module) => {
    press(String(modules.indexOf(module) + 1));
    expect(useUiStore.getState().activeModule).toBe(module);
    expect(container.querySelector('main')?.textContent).not.toBe('');
  });

  it.each(['button', 'a', 'input', 'textarea', 'select'])('ignores window events while %s is focused', (tag) => {
    const element = document.createElement(tag);
    element.tabIndex = 0;
    document.body.appendChild(element);
    element.focus();
    expect(document.activeElement).toBe(element);
    expect(press().defaultPrevented).toBe(false);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each(['true', '', 'plaintext-only'])('ignores contenteditable=%s ancestors', (value) => {
    const editor = document.createElement('div');
    editor.setAttribute('contenteditable', value);
    const child = document.createElement('span');
    child.tabIndex = 0;
    editor.appendChild(child);
    document.body.appendChild(editor);
    child.focus();
    expect(document.activeElement).toBe(child);
    press();
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it('ignores bubbled SVG children inside buttons even without active focus', () => {
    const button = document.createElement('button');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    button.appendChild(svg);
    document.body.appendChild(button);
    press('2', {}, svg);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each(['dialog', '[role="dialog"]', '[aria-modal="true"]', '[data-drawer]'])('ignores focus inside %s', (selector) => {
    const overlay = document.createElement(selector === 'dialog' ? 'dialog' : 'div');
    if (selector === 'dialog') overlay.setAttribute('open', '');
    if (selector === '[role="dialog"]') overlay.setAttribute('role', 'dialog');
    if (selector === '[aria-modal="true"]') overlay.setAttribute('aria-modal', 'true');
    if (selector === '[data-drawer]') overlay.setAttribute('data-drawer', '');
    const child = document.createElement('span');
    child.tabIndex = 0;
    overlay.appendChild(child);
    document.body.appendChild(overlay);
    child.focus();
    expect(document.activeElement).toBe(child);
    press();
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each(['OPS (0)', 'Copilot', 'Configuration'])('blocks shortcuts when %s opens', (name) => {
    const button = Array.from(container.querySelectorAll('button')).find((item) => item.textContent === name)!;
    act(() => button.click());
    press();
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { repeat: true }, { isComposing: true }])('ignores protected event %j', (options) => {
    press('2', options);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it.each(['0', '10', 'a', 'Escape', ''])('ignores invalid key %s', (key) => {
    press(key);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it('respects events already handled by descendants', () => {
    const target = document.createElement('div');
    document.body.appendChild(target);
    target.addEventListener('keydown', (event) => event.preventDefault());
    press('2', {}, target);
    expect(useUiStore.getState().activeModule).toBe('pipeline_console');
  });

  it('allows navigation from explicitly non-editable content', () => {
    const element = document.createElement('div');
    element.setAttribute('contenteditable', 'false');
    element.tabIndex = 0;
    document.body.appendChild(element);
    element.focus();
    press();
    expect(useUiStore.getState().activeModule).toBe('control_center');
  });

  it('does not treat the closed operations dialog as open', () => {
    expect(container.querySelector('dialog[open]')).toBeNull();
    press();
    expect(useUiStore.getState().activeModule).toBe('control_center');
  });

  it('mounts the default branch for an unknown runtime module', () => {
    act(() => useUiStore.setState({ activeModule: 'unknown' as ModuleType }));
    expect(container.querySelector('main')?.textContent).toContain('control_center mounted');
  });

  it('resumes shortcuts after operations closes', () => {
    act(() => useUiStore.getState().setIsOpsDrawerOpen(true));
    const close = container.querySelector('dialog button') as HTMLButtonElement;
    act(() => close.click());
    press();
    expect(useUiStore.getState().activeModule).toBe('control_center');
  });

  it('cleans listeners on unmount', () => {
    const setModule = vi.spyOn(useUiStore.getState(), 'setActiveModule');
    act(() => root.unmount());
    unmounted = true;
    press();
    expect(setModule).not.toHaveBeenCalled();
  });

  it.each([...modules, 'barra_risk_tca', 'chart_station', 'execution_blotter'] as ModuleType[])('mounts App branch %s', (module) => {
    act(() => useUiStore.getState().setActiveModule(module));
    const content = container.querySelector('main')!;
    if (module === 'macro_news_hub') {
      expect(content.querySelector('[data-testid="macro-news-hub-view"]')).not.toBeNull();
      expect(content.textContent).toContain('PROVENANCE_UNVERIFIED');
      expect(content.textContent).not.toContain('LandingDatabaseHub mounted');
      expect(content.textContent).not.toContain('PIT_SAFE');
      expect(content.innerHTML).not.toMatch(/purple|violet|fuchsia/i);
    } else if (module === 'macro_cockpit') {
      expect(content.textContent).toContain('LandingDatabaseHub mounted');
      if (module === 'macro_cockpit') {
        expect(content.textContent).toContain('PIT_CUTOFF');
        expect(content.textContent).not.toContain('HMM');
      }
    } else if (module === 'pipeline_console') {
      expect(content.querySelector('section')?.getAttribute('aria-label')).toBe('VALIDATED RESEARCH PIPELINE');
      expect(content.querySelector('section h2')?.textContent).toBe('VALIDATED RESEARCH PIPELINE');
      expect(content.textContent).toContain('Awaiting server DAG telemetry.');
      expect(content.querySelector('form')).not.toBeNull();
    } else {
      expect(content.textContent).toContain(`${module} mounted`);
    }
  });

  it('selects real operation tasks without synthetic progress', () => {
    act(() => useUiStore.setState({ isOpsDrawerOpen: true, tasks: {
      task1: { taskId: 'task1', taskType: 'DATA_INGESTION', status: 'FAILED', progress: 0, stage: 'ERROR', message: 'failed', startedAt: '' },
    } }));
    const task = container.querySelector('button[aria-pressed]')!;
    expect(task.textContent).toContain('FAILED');
    act(() => (task as HTMLButtonElement).click());
    expect(useUiStore.getState().selectedTaskId).toBe('task1');
  });
});
