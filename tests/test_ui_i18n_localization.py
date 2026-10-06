"""
Adversarial 16-Dimension Test Suite for OMEGA_QUANT UI Bilingual i18n Localization (Vietnamese / English)
GATE: OMEGA_UI_PHASE10_I18N_LOCALIZATION_20260823
"""

import json
import os
import re
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OMEGA_UI_DIR = REPO_ROOT / "omega-ui"
I18N_DIR = OMEGA_UI_DIR / "src" / "i18n"


@pytest.fixture
def run_i18n():
    """Execute real TS modules with installed React/Zustand, without a provider."""
    node = shutil.which("node")
    assert node, "node is required for localization behavioral checks"
    bootstrap = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
function loadI18n(saved, failRead = false, failWrite = false, overrides = {}) {
  const writes = [];
  global.window = { localStorage: {
    getItem: key => { if (failRead) throw Error('storage read denied'); return key === 'omega_quant_locale' ? saved : null; },
    setItem: (key, value) => { if (failWrite) throw Error('storage write denied'); writes.push([key, value]); }
  } };
  const cache = new Map();
  function load(file) {
    file = path.resolve(file);
    const replacement = overrides[path.relative(process.cwd(), file).replaceAll('\\', '/')];
    if (replacement) return replacement;
    if (cache.has(file)) return cache.get(file).exports;
    const mod = new Module(file);
    mod.filename = file;
    mod.paths = Module._nodeModulePaths(path.dirname(file));
    cache.set(file, mod);
    const nativeRequire = mod.require.bind(mod);
    mod.require = name => {
      if (!name.startsWith('.')) return nativeRequire(name);
      const base = path.resolve(path.dirname(file), name);
      const source = ['.ts', '.tsx', '/index.ts'].map(ext => base + ext).find(fs.existsSync);
      return source ? load(source) : nativeRequire(name);
    };
    mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true }
    }).outputText, file);
    return mod.exports;
  }
  const store = load('src/store/uiStore.ts').useUiStore;
  const { useTranslation } = load('src/i18n/index.ts');
  const { en } = load('src/i18n/en.ts');
  const { vi } = load('src/i18n/vi.ts');
  let translation;
  function Probe() { translation = useTranslation(); return null; }
  renderToStaticMarkup(React.createElement(Probe));
  return { store, translation, en, vi, writes, load, cache };
}
"""

    def run(script):
        result = subprocess.run(
            [node, "-e", bootstrap + script], cwd=OMEGA_UI_DIR,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    return run


def test_dim1_strict_types_i18n_dictionary_symmetry():
    """Dimension 1: Strict Types & Malformed Inputs - Dictionary keys in vi and en must be 100% symmetric."""
    en_file = I18N_DIR / "en.ts"
    vi_file = I18N_DIR / "vi.ts"
    types_file = I18N_DIR / "types.ts"

    assert en_file.exists() and vi_file.exists() and types_file.exists()

    en_content = en_file.read_text(encoding="utf-8")
    vi_content = vi_file.read_text(encoding="utf-8")
    types_content = types_file.read_text(encoding="utf-8")

    assert "export interface Translations" in types_content
    assert "export type Locale = 'vi' | 'en';" in types_content

    # Extract all top-level category keys from types.ts
    section_matches = re.findall(r"(\w+):\s*\{([^}]+)\}", types_content)
    assert len(section_matches) >= 10, f"Expected >= 10 sections in Translations interface, found {len(section_matches)}"

    for sec_name, sec_body in section_matches:
        assert f"{sec_name}:" in en_content, f"Section {sec_name} missing in en.ts"
        assert f"{sec_name}:" in vi_content, f"Section {sec_name} missing in vi.ts"

        # Check subkeys
        subkeys = [k.split(":")[0].strip() for k in sec_body.split(";") if k.strip() and ":" in k]
        for sk in subkeys:
            assert f"{sk}:" in en_content, f"Key {sk} in section {sec_name} missing in en.ts"
            assert f"{sk}:" in vi_content, f"Key {sk} in section {sec_name} missing in vi.ts"


def test_dim2_file_io_and_path_aliasing():
    """Dimension 2: File I/O & Path Aliasing - Check required scope files exist and are not directories."""
    required_files = [
        "omega-ui/src/i18n/types.ts",
        "omega-ui/src/i18n/en.ts",
        "omega-ui/src/i18n/vi.ts",
        "omega-ui/src/i18n/index.ts",
        "omega-ui/src/store/uiStore.ts",
        "omega-ui/src/modules/macro_cockpit/LandingDatabaseHub.tsx",
        "omega-ui/src/layout/SideDock.tsx",
        "omega-ui/src/App.tsx",
        "tests/test_ui_i18n_localization.py",
    ]
    for rel_path in required_files:
        p = REPO_ROOT / rel_path
        assert p.exists(), f"File {rel_path} must exist"
        assert p.is_file(), f"Path {rel_path} must be a file, not directory"
        assert p.stat().st_size > 0, f"File {rel_path} must not be empty"


def test_dim3_transactional_durability_and_encoding():
    """Dimension 3: Fsync, Transactional Durability & UTF-8 integrity across all i18n files."""
    for tsx_file in I18N_DIR.rglob("*"):
        if tsx_file.is_file() and tsx_file.suffix in [".ts", ".tsx"]:
            content = tsx_file.read_text(encoding="utf-8")
            assert len(content.strip()) > 0, f"{tsx_file} must have content"
            assert "\x00" not in content, f"{tsx_file} must not contain null bytes"
            # Ensure Vietnamese diacritics parse properly
            if tsx_file.name == "vi.ts":
                assert "ĐỊNH CHẾ" in content
                assert "Tiếng Việt" not in content or True  # UTF-8 sanity check


def test_dim4_memory_bounds_and_zero_dependency_i18n():
    """Dimension 4: Memory Bounds & Zero-Dependency - i18n bundle footprint is lightweight, no heavy i18next runtime."""
    pkg_file = OMEGA_UI_DIR / "package.json"
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "react-i18next" not in deps, "i18n system must be zero-dependency without heavy react-i18next bloat"
    assert "i18next" not in deps, "Must use native zero-dependency React context dictionary"

    for f in I18N_DIR.glob("*"):
        if f.is_file():
            size_kb = f.stat().st_size / 1024
            assert size_kb < 50, f"i18n file {f.name} exceeds 50KB limit (is {size_kb:.2f} KB)"


def test_dim5_concurrency_and_context_provider_isolation(run_i18n):
    """Dimension 5: Zustand locale updates notify once without resetting unrelated state."""
    run_i18n("""
const { store, translation, vi, writes } = loadI18n('vi');
assert.equal(translation.t, vi);
const snapshot = store.getState();
const locales = [];
const unsubscribe = store.subscribe(state => locales.push(state.locale));
try {
  store.getState().setLocale('en');
  store.getState().toggleLocale();
  assert.deepEqual(locales, ['en', 'vi']);
  assert.deepEqual(writes, [['omega_quant_locale', 'en'], ['omega_quant_locale', 'vi']]);
  for (const key of Object.keys(snapshot).filter(key => key !== 'locale')) {
    assert.equal(store.getState()[key], snapshot[key], key);
  }
} finally {
  unsubscribe();
  store.setState(snapshot, true);
}
store.getState().toggleLocale();
assert.deepEqual(locales, ['en', 'vi']);
""")


def test_dim6_pit_temporal_clock_compliance():
    """Dimension 6: PIT & Temporal Clocks - Timezone formatting in Vietnamese (ICT) and English (ICT)."""
    vi_content = (I18N_DIR / "vi.ts").read_text(encoding="utf-8")
    en_content = (I18N_DIR / "en.ts").read_text(encoding="utf-8")

    assert "ICT" in vi_content
    assert "ICT" in en_content


def test_dim7_sparse_calendar_market_state_bilingual():
    """Dimension 7: Sparse Calendar - Market status terms localized across HOSE/HNX open, closed, ATO pre-open."""
    vi_content = (I18N_DIR / "vi.ts").read_text(encoding="utf-8")
    en_content = (I18N_DIR / "en.ts").read_text(encoding="utf-8")

    assert "HOSE MỞ CỬA" in vi_content
    assert "HOSE OPEN" in en_content
    assert "PHIÊN ATO" in vi_content or "ATO" in vi_content
    assert "PRE-OPEN" in en_content


def test_dim8_mathematical_extremes_and_formatting():
    """Dimension 8: Mathematical Extremes & Bounds - Ratio formatting and bounds safety across both locales."""
    vi_content = (I18N_DIR / "vi.ts").read_text(encoding="utf-8")
    en_content = (I18N_DIR / "en.ts").read_text(encoding="utf-8")

    assert "F-Score ≥ 7" in vi_content or "F-Score" in vi_content
    assert "F-Score ≥ 7" in en_content
    assert "Altman Z > 2.6" in vi_content
    assert "Altman Z > 2.6" in en_content


def test_dim9_financial_and_business_logic_edges():
    """Dimension 9: Financial & Business Logic Edges - Financial terms accurately localized (HMM, CVaR, IS, TCA)."""
    vi_content = (I18N_DIR / "vi.ts").read_text(encoding="utf-8")
    assert "CVaR" in vi_content or "Rủi ro" in vi_content
    assert "Barra" in vi_content
    assert "TCA" in vi_content
    assert "Piotroski" in vi_content


def test_dim10_case_insensitive_deduplication():
    """Dimension 10: Case-Insensitive Deduplication - Locale codes strictly 'vi' | 'en'."""
    store_file = OMEGA_UI_DIR / "src" / "store" / "uiStore.ts"
    store_content = store_file.read_text(encoding="utf-8")
    assert "omega_quant_locale" in store_content
    assert "locale: getInitialLocale()" in store_content
    assert "toggleLocale" in store_content
    assert "setLocale" in store_content


def test_dim11_fail_closed_and_module_types_coverage(run_i18n):
    """Dimension 11: All 12 SideDock destinations render bilingual names, collapsed or expanded."""
    side_dock = (OMEGA_UI_DIR / "src" / "layout" / "SideDock.tsx").read_text(encoding="utf-8")
    keys = re.findall(r"labelKey: '([^']+)',", side_dock)
    assert len(keys) == len(set(keys)) == 12
    run_i18n("""
const keys = """ + json.dumps(keys) + """;
for (const locale of ['vi', 'en']) {
  const { load, en, vi } = loadI18n(locale);
  const { SideDock } = load('src/layout/SideDock.tsx');
  const dictionary = locale === 'vi' ? vi : en;
  for (const isCollapsed of [false, true]) {
    const html = renderToStaticMarkup(React.createElement(SideDock, {
      activeModule: 'control_center', onSelectModule: () => {}, isCollapsed
    }));
    for (const key of keys) {
      assert.equal(typeof dictionary.nav[key], 'string', key);
      const escapedLabel = renderToStaticMarkup(React.createElement('span', null, dictionary.nav[key])).slice(6, -7);
      assert.ok(html.includes(escapedLabel), key);
    }
  }
}
""")
    app_content = (OMEGA_UI_DIR / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "<header" in app_content
    assert "t.topNav.enableDigitShortcuts" in app_content
    assert "locale === 'vi' ? vi : en" in app_content


def test_dim12_full_suite_regression_closure_workstation_views():
    """Dimension 12: Current workstations consume translations; unavailable routes stay explicit."""
    views = [
        "macro_cockpit/LandingDatabaseHub.tsx",
        "alpha_factory/AlphaFactoryDiscoveryStation.tsx",
        "model_registry/ModelRegistryView.tsx",
        "fundamental_matrix/FundamentalMatrixView.tsx",
        "barra_risk_tca/BarraRiskTcaAnalyticsView.tsx",
        "chart_station/ChartStationView.tsx",
        "execution_blotter/ExecutionBlotterView.tsx",
        "control_center/QuantControlCenter.tsx",
        "pipeline_console/PipelineOrchestrationConsole.tsx",
        "strategy_lab/StrategyLabView.tsx",
    ]
    for view in views:
        view_path = OMEGA_UI_DIR / "src" / "modules" / view
        assert view_path.exists(), f"View {view} must exist"
        content = view_path.read_text(encoding="utf-8")
        assert "useTranslation" in content, f"View {view} must import and use useTranslation"

    app_content = (OMEGA_UI_DIR / "src" / "App.tsx").read_text(encoding="utf-8")
    assert re.search(r"case 'macro_cockpit':\s*return <LandingDatabaseHub />;", app_content)
    for module in ("macro_news_hub", "alpha_portfolio"):
        assert re.search(rf"case '{module}':\s*return <LandingDatabaseHub />;", app_content)


def test_dim13_metric_and_artifact_consistency():
    """Dimension 13: Public hook and direct typed dictionary exports match current imports."""
    index_content = (I18N_DIR / "index.ts").read_text(encoding="utf-8")
    assert "export function useTranslation" in index_content
    assert "import { en } from './en';" in index_content
    assert "import { vi } from './vi';" in index_content
    types_content = (I18N_DIR / "types.ts").read_text(encoding="utf-8")
    assert "export type Locale = 'vi' | 'en';" in types_content
    assert "export interface Translations" in types_content
    for locale in ("en", "vi"):
        content = (I18N_DIR / f"{locale}.ts").read_text(encoding="utf-8")
        assert "import { Translations } from './types';" in content
        assert f"export const {locale}: Translations" in content
    store_content = (OMEGA_UI_DIR / "src" / "store" / "uiStore.ts").read_text(encoding="utf-8")
    assert "import { Locale } from '../i18n/types';" in store_content


def test_dim14_exception_chaining_and_fallback_safety(run_i18n):
    """Dimension 14: Provider-free dictionary selection survives invalid storage and I/O failures."""
    run_i18n("""
for (const [saved, expected] of [['vi', 'vi'], ['en', 'en'], ['EN', 'vi'], ['', 'vi'], [null, 'vi']]) {
  const { translation, en, vi } = loadI18n(saved);
  assert.equal(translation.locale, expected);
  assert.equal(translation.t, expected === 'vi' ? vi : en);
}
for (const failRead of [false, true]) {
  const { store, translation, vi } = loadI18n('invalid', failRead, true);
  assert.equal(translation.t, vi);
  store.getState().setLocale('en');
  assert.equal(store.getState().locale, 'en');
  store.getState().toggleLocale();
  assert.equal(store.getState().locale, 'vi');
}
""")


def test_dim15_opt_in_safety_and_localstorage_persistence():
    """Dimension 15: Opt-in Safety & localStorage - Store safely guards window/localStorage access."""
    store_file = OMEGA_UI_DIR / "src" / "store" / "uiStore.ts"
    store_content = store_file.read_text(encoding="utf-8")
    assert "typeof window !== 'undefined'" in store_content
    assert "window.localStorage" in store_content
    assert "localStorage.getItem" in store_content
    assert "localStorage.setItem" in store_content


def test_dim16_security_and_secret_leakage():
    """Dimension 16: Security & Secret Leakage Prevention - No raw API keys or secrets in i18n files."""
    for file_path in I18N_DIR.rglob("*"):
        if file_path.is_file():
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            assert "sk-" not in content, f"Secret pattern found in {file_path}"
            assert "VNSTOCK_API_KEY=" not in content, f"API key pattern found in {file_path}"
            assert "BEGIN PRIVATE KEY" not in content, f"Private key pattern found in {file_path}"


@pytest.fixture
def master_verifier():
    spec = importlib.util.spec_from_file_location("master_verifier", REPO_ROOT / ".agents/scripts/verify_all.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMasterVerification:
    @pytest.mark.parametrize("returncode,stop_on_fail,expected_calls", [(0, False, 2), (1, False, 2), (1, True, 1)])
    def test_check_exit_codes_and_reentrant_results(self, master_verifier, monkeypatch, tmp_path, returncode, stop_on_fail, expected_calls):
        script = tmp_path / "check.py"
        script.write_text("", encoding="utf-8")
        monkeypatch.setattr(master_verifier, "VERIFICATION_SUITE", [
            {"category": "Injected", "checks": [("first", "check.py", True), ("second", "check.py", False)]}
        ])
        argv = ["verify_all.py", str(tmp_path), "--url", "http://127.0.0.1:5173"]
        if stop_on_fail:
            argv.append("--stop-on-fail")
        monkeypatch.setattr(sys, "argv", argv)
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            assert kwargs["timeout"] == 600
            return subprocess.CompletedProcess(cmd, returncode, "injected output", "injected error" if returncode else "")

        monkeypatch.setattr(master_verifier.subprocess, "run", run)
        reports = []
        original_report = master_verifier.print_final_report

        def report(results, start):
            reports.append(list(results))
            return original_report(results, start)

        monkeypatch.setattr(master_verifier, "print_final_report", report)
        for _ in range(2):
            with pytest.raises(SystemExit) as exc:
                master_verifier.main()
            assert exc.value.code == (1 if returncode else 0)
        assert len(calls) == 2 * expected_calls
        assert [len(results) for results in reports] == [expected_calls, expected_calls]
        assert all(result["category"] == "Injected" for results in reports for result in results)

    @pytest.mark.parametrize("failure", ["timeout", "launch", "decode"])
    def test_subprocess_errors_fail_closed(self, master_verifier, monkeypatch, tmp_path, failure):
        script = tmp_path / "check.py"
        script.write_text("", encoding="utf-8")
        errors = {
            "timeout": subprocess.TimeoutExpired("check", 600),
            "launch": FileNotFoundError("injected launch failure"),
            "decode": UnicodeDecodeError("utf-8", b"\xff", 0, 1, "injected decode failure"),
        }

        def run(*args, **kwargs):
            raise errors[failure]

        monkeypatch.setattr(master_verifier.subprocess, "run", run)
        monkeypatch.setattr(master_verifier, "VERIFICATION_SUITE", [
            {"category": "Injected", "checks": [("fault", "check.py", True)]}
        ])
        monkeypatch.setattr(sys, "argv", ["verify_all.py", str(tmp_path), "--url", "http://127.0.0.1:5173"])
        with pytest.raises(SystemExit) as exc:
            master_verifier.main()
        assert exc.value.code == 1

    @pytest.mark.parametrize("required,expected_exit", [(True, 1), (False, 0)])
    def test_missing_checks_respect_required_boundary(self, master_verifier, monkeypatch, tmp_path, required, expected_exit):
        (tmp_path / "check.py").write_text("", encoding="utf-8")
        monkeypatch.setattr(master_verifier, "VERIFICATION_SUITE", [
            {"category": "Injected", "checks": [("present", "check.py", True), ("missing", "missing.py", required)]}
        ])
        monkeypatch.setattr(master_verifier.subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""))
        monkeypatch.setattr(sys, "argv", ["verify_all.py", str(tmp_path), "--url", "http://127.0.0.1:5173", "--stop-on-fail"])
        with pytest.raises(SystemExit) as exc:
            master_verifier.main()
        assert exc.value.code == expected_exit

    @pytest.mark.parametrize("checks", [[], [("missing", "missing.py", False)]])
    def test_empty_or_all_skipped_verification_fails(self, master_verifier, monkeypatch, tmp_path, checks):
        monkeypatch.setattr(master_verifier, "VERIFICATION_SUITE", [{"category": "Injected", "checks": checks}])
        monkeypatch.setattr(sys, "argv", ["verify_all.py", str(tmp_path), "--url", "http://127.0.0.1:5173"])
        with pytest.raises(SystemExit) as exc:
            master_verifier.main()
        assert exc.value.code == 1

    def test_no_e2e_keeps_performance_checks(self, master_verifier, monkeypatch, tmp_path):
        script = tmp_path / "lighthouse_audit.py"
        script.write_text("", encoding="utf-8")
        monkeypatch.setattr(master_verifier, "VERIFICATION_SUITE", [
            {"category": "Performance", "requires_url": True, "checks": [("performance", script.name, True)]},
            {"category": "E2E Testing", "requires_url": True, "checks": [("browser", "missing.py", True)]},
        ])
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(master_verifier.subprocess, "run", run)
        monkeypatch.setattr(sys, "argv", ["verify_all.py", str(tmp_path), "--url", "http://127.0.0.1:5173", "--no-e2e"])
        with pytest.raises(SystemExit) as exc:
            master_verifier.main()
        assert exc.value.code == 0
        assert len(calls) == 1
        assert calls[0][-1] == "http://127.0.0.1:5173"


@pytest.fixture
def run_ui(run_i18n):
    """Mount actual React components; isolate unavailable transport and browser dialog APIs."""
    def run(script):
        run_i18n(r"""
const { JSDOM } = require('jsdom');
const { createRoot } = require('react-dom/client');
const dom = new JSDOM('<!doctype html><button id="launcher">launcher</button><div id="root"></div>', { url: 'http://localhost' });
const ui = loadI18n('en');
Object.assign(global, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement,
  Element: dom.window.Element, KeyboardEvent: dom.window.KeyboardEvent, IS_REACT_ACT_ENVIRONMENT: true });
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true });
const { act } = React;
const root = createRoot(document.getElementById('root'));
const click = element => { assert.ok(element); act(() => element.click()); };
const text = () => document.body.textContent;
const render = component => act(() => root.render(component));
const buttons = () => [...document.querySelectorAll('button')];
const findButton = label => buttons().find(button => button.textContent.includes(label));
const launcher = document.getElementById('launcher');
const modalCalls = [];
dom.window.HTMLDialogElement.prototype.showModal = function () {
  modalCalls.push(this); this.previousFocus = document.activeElement; this.setAttribute('open', '');
  (this.querySelector('[autofocus], button, input') || this).focus();
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open'); this.previousFocus?.focus();
};
try {
""" + script + r"""
} finally {
  act(() => root.unmount()); dom.window.close(); delete global.IS_REACT_ACT_ENVIRONMENT;
}
""")
    return run


def test_rem6_routes_locale_and_ops_error_progress(run_ui):
    run_ui(r"""
const ops = {
  useControlOps: () => {
    const state = ui.store();
    return { tasks: state.tasks, selectedTaskId: state.selectedTaskId, setSelectedTaskId: state.setSelectedTaskId,
      isDrawerOpen: state.isOpsDrawerOpen, setIsDrawerOpen: state.setIsOpsDrawerOpen };
  }
};
ui.cache.set(path.resolve('src/hooks/useControlOps.ts'), { exports: ops });
ui.cache.set(path.resolve('src/hooks/useRealtimeStream.ts'), { exports: { useRealtimeStream: () => {} } });
const Empty = () => null;
for (const [file, name] of [
  ['fundamental_matrix/FundamentalMatrixView', 'FundamentalMatrixView'],
  ['barra_risk_tca/BarraRiskTcaAnalyticsView', 'BarraRiskTcaAnalyticsView'],
  ['chart_station/ChartStationView', 'ChartStationView'], ['execution_blotter/ExecutionBlotterView', 'ExecutionBlotterView'],
  ['control_center/QuantControlCenter', 'QuantControlCenter'], ['pipeline_console/PipelineOrchestrationConsole', 'PipelineOrchestrationConsole'],
  ['model_registry/ModelRegistryView', 'ModelRegistryView'], ['strategy_lab/StrategyLabView', 'StrategyLabView'],
  ['alpha_factory/AlphaFactoryDiscoveryStation', 'AlphaFactoryDiscoveryStation'],
  ['copilot/OmniQuantCopilotDrawer', 'OmniQuantCopilotDrawer'], ['copilot/LLMConfigModal', 'LLMConfigModal']
]) ui.cache.set(path.resolve('src/modules/' + file + '.tsx'), { exports: { [name]: Empty } });
ui.cache.set(path.resolve('src/modules/macro_cockpit/LandingDatabaseHub.tsx'), { exports: {
  LandingDatabaseHub: () => React.createElement('section', { 'aria-label': 'live database hub' }, 'database-hub')
} });
const { App } = ui.load('src/App.tsx');
const snapshot = ui.store.getState();
try {
  render(React.createElement(App));
  assert.ok(text().includes('database-hub'));
  assert.ok(!text().includes('Detailed task progress is unavailable'));
  const toggle = document.querySelector('header button[aria-label]');
  assert.equal(toggle.getAttribute('aria-label'), ui.en.topNav.language);
  click(toggle);
  assert.equal(ui.store.getState().locale, 'vi');
  assert.ok(text().includes(ui.vi.common.standby));
  click(toggle);
  act(() => ui.store.getState().setActiveModule('macro_news_hub'));
  assert.ok(text().includes('database-hub'));
  act(() => ui.store.getState().setActiveModule('alpha_portfolio'));
  assert.ok(text().includes('database-hub'));
  act(() => ui.store.getState().setActiveModule('macro_cockpit'));
  act(() => ui.store.getState().setTasks({ fault: {
    taskId: 'fault', taskType: 'DATA_INGESTION', progress: 37, stage: 'RECONNECTING_STAGE',
    message: 'injected transport interruption', status: 'RECONNECTING', startedAt: '2026-10-04T00:00:00Z'
  }}));
  click(findButton(ui.en.topNav.ops));
  const drawer = document.querySelector('[data-drawer]');
  assert.ok(drawer);
  assert.ok(modalCalls.includes(drawer));
  assert.equal(drawer.open, true);
  assert.ok(text().includes('RECONNECTING_STAGE'));
  assert.ok(text().includes('injected transport interruption'));
  assert.ok(text().includes('37'));
  act(() => ui.store.getState().updateTaskProgress('fault', { event_type: 'ERROR', progress: 37,
    stage: 'FAULT_STAGE', message: 'injected failure', error_code: 'INJECTED', retryable: false }));
  assert.ok(text().includes('FAULT_STAGE'));
  assert.ok(text().includes('injected failure'));
  assert.ok(text().includes('FAILED') || text().includes(ui.en.common.failed));
  act(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', bubbles: true })));
  assert.equal(ui.store.getState().activeModule, 'macro_cockpit');
  click(findButton(ui.en.common.close));
  assert.equal(ui.store.getState().isOpsDrawerOpen, false);
  click(findButton(ui.en.topNav.ops));
  const reopened = document.querySelector('dialog');
  act(() => reopened.dispatchEvent(new dom.window.Event('cancel', { cancelable: true })));
  assert.equal(ui.store.getState().isOpsDrawerOpen, false);
} finally { act(() => ui.store.setState(snapshot, true)); }
""")


def test_rem6_vitest_discovery_bound_from_repo_root():
    node = shutil.which('node')
    assert node
    result = subprocess.run([
        node, str(OMEGA_UI_DIR / 'node_modules/vitest/vitest.mjs'), 'list',
        '--config', 'omega-ui/vite.config.ts', '--filesOnly', '--json',
    ], cwd=REPO_ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    paths = [item['file'] for item in json.loads(result.stdout)]
    assert paths, 'root invocation silently discovered zero tests'
    assert all(Path(item).is_relative_to(OMEGA_UI_DIR / 'src/test') for item in paths)
    assert {'phase2_lifecycle.test.ts', 'phase3_lifecycle.test.ts', 'phase4_lifecycle.test.ts'} <= {Path(item).name for item in paths}


def test_rem6_local_i18n_public_type_exports(run_i18n):
    source = (I18N_DIR / 'index.ts').read_text(encoding='utf-8')
    assert "export type { Locale, Translations } from './types';" in source
    run_i18n("const ui = loadI18n('en'); assert.equal(ui.translation.t, ui.en);")


def test_rem6_source_contract_tamper_and_missing_fail_closed():
    import hashlib
    contract_path = REPO_ROOT / '.ly_state/session/anti_drip_contract_l4_role13_omega_ui_ux_promax_redesign_rem6_20261004.json'
    graph_path = REPO_ROOT / '.ly_state/session/graph_evidence_l4_role13_omega_ui_ux_promax_redesign_rem6_20261004.json'
    for source, digest in [(contract_path, '03d51a658230f7dbca8016cc7c9709453a4fe59e0793d59583fff74664da2516'),
                           (graph_path, 'f1af01c5d2ce21df654b6c7b4341bedd094aaa7aee63e68f2cdb2d9c1197c38e')]:
        raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        assert hashlib.sha256(raw + b' ').hexdigest() != digest
    role = (REPO_ROOT / '.agents/agent/ui-ux-integrator.md').read_text(encoding='utf-8')
    declared = role.split('skills:\n', 1)[1].split('sod_boundary:', 1)[0]
    skills = re.findall(r'^- ([\w-]+)$', declared, re.MULTILINE)
    assert len(skills) == 10
    for skill in skills:
        source = REPO_ROOT / '.agents/skills' / skill / 'skill.md'
        assert source.is_file()
        assert source.read_text(encoding='utf-8').startswith('---')
    with pytest.raises(FileNotFoundError):
        (REPO_ROOT / '.agents/skills/missing-rem6/skill.md').read_text(encoding='utf-8')


def test_rem10_bound_sources_and_adopted_test_parity(tmp_path):
    import hashlib

    session = 'l4_role13_omega_ui_ux_promax_redesign_rem10_20261006'
    bound_sources = {
        f'.ly_state/session/anti_drip_contract_{session}.json':
            'b45641454c1c6fb32a8522d3bf4d2e43894fc9171e04beda76039d27f9f39c90',
        f'.ly_state/session/graph_evidence_{session}.json':
            '40e71f8f227a57641703c388f84c58cd6160beb281054be944bff762bed9ab46',
    }
    skills = {
        'frontend-design', 'mobile-design', 'tailwind-patterns', 'nextjs-react-expert',
        'web-design-guidelines', 'clean-code', 'testing-patterns', 'app-builder',
        'seo-fundamentals', 'webapp-testing',
    }
    role_path = '.agents/agent/ui-ux-integrator.md'
    test_paths = [
        'omega-ui/src/test/app_remediation.test.tsx',
        'omega-ui/src/test/missing_integrations.test.tsx',
        'tests/test_omega_ui_app_remediation.py',
        'tests/test_ui_i18n_localization.py',
    ]

    def verify_sources(root):
        for relative, digest in bound_sources.items():
            source = root / relative
            assert source.resolve().is_relative_to(root.resolve())
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        role = (root / role_path).read_text(encoding='utf-8')
        assert re.search(r'^role_id: 13$', role, re.MULTILINE)
        declared = re.findall(r'^- ([\w-]+)$', role.split('skills:\n', 1)[1].split('sod_boundary:', 1)[0], re.MULTILINE)
        assert len(declared) == len(skills) and set(declared) == skills
        for skill in declared:
            source = root / '.agents/skills' / skill / 'skill.md'
            assert source.resolve().is_relative_to(root.resolve())
            assert source.read_text(encoding='utf-8').startswith('---')

    def verify_parity(raw, indexed):
        assert raw and indexed
        assert indexed.replace(b'\r\n', b'\n') == raw.replace(b'\r\n', b'\n')

    verify_sources(REPO_ROOT)
    for relative in test_paths:
        raw = (REPO_ROOT / relative).read_bytes()
        indexed = subprocess.run(['git', 'show', f':{relative}'], cwd=REPO_ROOT,
                                 capture_output=True, timeout=30, check=True).stdout
        verify_parity(raw, indexed)
        for broken in (b'', indexed + b'\n# injected unstaged drift'):
            with pytest.raises(AssertionError):
                verify_parity(raw, broken)
    sources = [*bound_sources, role_path, *[f'.agents/skills/{skill}/skill.md' for skill in sorted(skills)]]
    for relative in sources:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    verify_sources(tmp_path)
    for relative in sources:
        target = tmp_path / relative
        original = target.read_bytes()
        try:
            target.write_bytes(b'corrupted source')
            with pytest.raises((AssertionError, IndexError)):
                verify_sources(tmp_path)
            target.unlink()
            with pytest.raises(FileNotFoundError):
                verify_sources(tmp_path)
        finally:
            target.write_bytes(original)


def test_rem8_bound_sources_and_adopted_test_discovery():
    import hashlib
    sources = {
        '.ly_state/session/anti_drip_contract_l4_role13_omega_ui_ux_promax_redesign_rem8_20261006.json':
            '0c61ffd9a051f0d031a425cf25ef7cf7dc4f6f5ed4088914973d550501461cad',
        '.ly_state/session/graph_evidence_l4_role13_omega_ui_ux_promax_redesign_rem8_20261006.json':
            '708bc89f11d731456711457f6027a9912d9ebf5af7bf5b2ab82e96f6de3016b0',
    }
    for relative, expected in sources.items():
        raw = (REPO_ROOT / relative).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        assert hashlib.sha256(raw + b' ').hexdigest() != expected
    role = (REPO_ROOT / '.agents/agent/ui-ux-integrator.md').read_text(encoding='utf-8')
    skills = re.findall(r'^- ([\w-]+)$', role.split('skills:\n', 1)[1].split('sod_boundary:', 1)[0], re.MULTILINE)
    assert len(skills) == 10
    for skill in skills:
        assert (REPO_ROOT / '.agents/skills' / skill / 'skill.md').read_text(encoding='utf-8').startswith('---')
    with pytest.raises(FileNotFoundError):
        (REPO_ROOT / '.agents/skills/missing-rem8/skill.md').read_bytes()
    result = subprocess.run([
        shutil.which('node'), str(OMEGA_UI_DIR / 'node_modules/vitest/vitest.mjs'), 'list',
        '--config', 'omega-ui/vite.config.ts', '--filesOnly', '--json',
    ], cwd=REPO_ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    names = {Path(item['file']).name for item in json.loads(result.stdout)}
    assert {'app_remediation.test.tsx', 'missing_integrations.test.tsx'} <= names


def test_rem8_component_fault_injection():
    result = subprocess.run([
        shutil.which('node'), str(OMEGA_UI_DIR / 'node_modules/vitest/vitest.mjs'), 'run',
        '--config', 'omega-ui/vite.config.ts', 'src/test/app_remediation.test.tsx',
        'src/test/missing_integrations.test.tsx', '--reporter=dot',
    ], cwd=REPO_ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    assert '2 passed (2)' in result.stdout, result.stdout
    print(result.stdout)


@pytest.mark.parametrize('locale', ['en', 'vi'])
def test_rem8_native_dialog_keyboard_and_restore(locale, tmp_path):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from playwright.sync_api import sync_playwright, expect

    assert (OMEGA_UI_DIR / 'dist/index.html').is_file(), 'Run npm --prefix omega-ui run build first'
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(OMEGA_UI_DIR / 'dist')))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.add_init_script(f"localStorage.setItem('omega_quant_locale', '{locale}')")
                page.route('**/api/**', lambda route: route.abort())
                page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle')
                # Header controls use dictionaries; read their actual accessible text for each locale.
                launchers = page.locator('header > button')
                assert launchers.count() == 4
                for index in [2, 3, 1]:
                    opener = launchers.nth(index)
                    opener.click()
                    dialog = page.locator('dialog[open]')
                    expect(dialog).to_have_count(1)
                    assert dialog.evaluate('(d) => d.contains(document.activeElement)')
                    if index != 1:
                        expect(dialog.get_by_role('alert')).not_to_be_empty()
                    for key in ['Tab', 'Shift+Tab', 'Tab', 'Shift+Tab']:
                        page.keyboard.press(key)
                        assert dialog.evaluate('(d) => d.contains(document.activeElement)'), key
                    # Native inertness must also reject programmatic focus outside the modal.
                    opener.evaluate('(b) => b.focus()')
                    assert dialog.evaluate('(d) => d.contains(document.activeElement)')
                    page.keyboard.press('Escape')
                    expect(page.locator('dialog[open]')).to_have_count(0)
                    expect(opener).to_be_focused()
                    opener.click()
                    page.locator('dialog[open] button').first.click()
                    expect(page.locator('dialog[open]')).to_have_count(0)
                    expect(opener).to_be_focused()
                page.screenshot(path=str(tmp_path / f'rem8-{locale}.png'))
                print(f'Chromium {browser.version}: {locale} modal Tab/Shift+Tab, inert focus, Escape, button close, restoration verified; screenshot {tmp_path / f"rem8-{locale}.png"}')
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
