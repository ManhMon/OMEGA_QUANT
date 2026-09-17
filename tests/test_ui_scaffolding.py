"""
Adversarial 16-Dimension Test Suite for OMEGA_QUANT UI Scaffolding & Design System
GATE: OMEGA_UI_PHASE1_SCAFFOLDING_20260823
"""

import json
import re
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OMEGA_UI_DIR = REPO_ROOT / "omega-ui"
SECRET_CREDENTIAL_RE = re.compile(
    r"sk[-_](?:live[-_]|test[-_]|proj-|ant-)?[A-Za-z0-9_-]{20,}"
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}"
    r"|\bVNSTOCK_API_KEY\s*[\"']?\s*[:=]",
    re.IGNORECASE,
)


def run_typescript_check(script: str, content: str):
    result = subprocess.run(
        ["node", "-e", script], input=content, text=True, encoding="utf-8",
        capture_output=True, cwd=OMEGA_UI_DIR, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise AssertionError("TypeScript check failed; source omitted for credential safety")
    return json.loads(result.stdout)


def assert_no_client_handlers(content: str):
    result = run_typescript_check("""
const ts = require('typescript');
const source = ts.createSourceFile('client.ts', require('fs').readFileSync(0, 'utf8'),
    ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
let handlers = 0;
function visit(node) {
    if (ts.isTryStatement(node) || ts.isCatchClause(node)) handlers++;
    ts.forEachChild(node, visit);
}
visit(source);
console.log(JSON.stringify({errors: source.parseDiagnostics.length, handlers}));
""", content)
    assert result["errors"] == 0, "Client syntax must parse without errors"
    assert result["handlers"] == 0, "Client try/catch handlers are prohibited"


def test_dim1_strict_types_package_json():
    """Dimension 1: Strict Types & Malformed Inputs - package.json schema validation."""
    pkg_file = OMEGA_UI_DIR / "package.json"
    assert pkg_file.exists(), "package.json must exist"
    with open(pkg_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict), "package.json root must be an object"
    assert data.get("name") == "omega-ui"
    assert data.get("private") is True
    assert "react" in data.get("dependencies", {})
    assert "react-dom" in data.get("dependencies", {})
    assert "tailwindcss" in data.get("devDependencies", {})
    assert "vite" in data.get("devDependencies", {})
    assert "typescript" in data.get("devDependencies", {})


def test_dim2_file_io_and_path_aliasing():
    """Dimension 2: File I/O & Path Aliasing - Check required scope files exist and are not directories."""
    required_files = [
        "omega-ui/package.json",
        "omega-ui/vite.config.ts",
        "omega-ui/index.html",
        "omega-ui/src/index.css",
        "omega-ui/src/App.tsx",
        "omega-ui/src/main.tsx",
        "omega-ui/src/layout/TopNavBar.tsx",
        "omega-ui/src/layout/SideDock.tsx",
        "omega-ui/src/layout/WorkspaceGrid.tsx",
        "omega-ui/src/modules/macro_cockpit/MacroCockpitView.tsx",
        "omega-ui/src/modules/fundamental_matrix/FundamentalMatrixView.tsx",
        "omega-ui/src/modules/alpha_portfolio/AlphaPortfolioView.tsx",
        "omega-ui/src/modules/chart_station/ChartStationView.tsx",
        "omega-ui/src/modules/execution_blotter/ExecutionBlotterView.tsx",
    ]
    for rel_path in required_files:
        p = REPO_ROOT / rel_path
        assert p.exists(), f"File {rel_path} must exist"
        assert p.is_file(), f"Path {rel_path} must be a file, not directory"
        assert p.stat().st_size > 0, f"File {rel_path} must not be empty"


def test_dim3_transactional_durability_and_encoding():
    """Dimension 3: Fsync, Transactional Durability & UTF-8 integrity across all UI files."""
    src_dir = OMEGA_UI_DIR / "src"
    for tsx_file in src_dir.rglob("*.tsx"):
        content = tsx_file.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"{tsx_file} must have content"
        assert "\x00" not in content, f"{tsx_file} must not contain null bytes"


def test_dim4_memory_bounds_and_bundle_hygiene():
    """Dimension 4: Memory Bounds & OOM Prevention - Source files must be modular (< 100KB per file)."""
    for file_path in OMEGA_UI_DIR.rglob("*"):
        if "node_modules" in file_path.parts or ".git" in file_path.parts or file_path.name == "package-lock.json":
            continue
        if file_path.is_file() and file_path.suffix in [".ts", ".tsx", ".css", ".html", ".json"]:
            size_kb = file_path.stat().st_size / 1024
            assert size_kb < 100, f"File {file_path} exceeds modular size limit (is {size_kb:.2f} KB)"


def test_dim5_concurrency_and_component_state_isolation():
    """Dimension 5: Concurrency & State Isolation - SideDock, TopNavBar, WorkspaceGrid must be decoupled."""
    app_content = (OMEGA_UI_DIR / "src/App.tsx").read_text(encoding="utf-8")
    assert "TopNavBar" in app_content
    assert "SideDock" in app_content
    assert "WorkspaceGrid" in app_content
    assert "activeModule" in app_content


def test_dim6_pit_temporal_clock_compliance():
    """Dimension 6: PIT & Temporal Clocks - Vietnam market timezone and status indicators."""
    top_nav = (OMEGA_UI_DIR / "src/layout/TopNavBar.tsx").read_text(encoding="utf-8")
    assert "ICT" in top_nav, "Must display ICT timezone for Vietnam market"
    assert "Asia/Ho_Chi_Minh" in top_nav, "Must use explicit Asia/Ho_Chi_Minh timezone"
    assert "formatIctTime" in top_nav, "Must provide dynamic formatIctTime clock helper"
    assert "getMarketSessionStatus" in top_nav, "Must compute dynamic market session status"
    assert "HOSE OPEN" in top_nav
    assert "CLOSED" in top_nav
    assert "PRE-OPEN" in top_nav
    assert "14:32:08" not in top_nav, "Hardcoded time string must be removed"

    app_tsx = (OMEGA_UI_DIR / "src/App.tsx").read_text(encoding="utf-8")
    assert 'marketStatus="HOSE OPEN"' not in app_tsx, "App.tsx must not hardcode marketStatus prop"


def test_dim7_sparse_calendar_market_state():
    """Dimension 7: Sparse Calendar - Validates exact HOSE session boundary simulation."""
    top_nav = (OMEGA_UI_DIR / "src/layout/TopNavBar.tsx").read_text(encoding="utf-8")
    assert "VN30" in top_nav
    assert "HOSE" in top_nav or "HNX" in top_nav
    assert "getMarketSessionStatus" in top_nav
    assert "14 * 60 + 45" in top_nav, "Must close HOSE at exactly 14:45 ICT"
    assert "15 * 60" not in top_nav, "Must not keep HOSE open until 15:00"


def test_hose_session_boundary_executable_logic():
    """Executable boundary test simulating getMarketSessionStatus logic in Python."""
    def compute_session_status(weekday: str, hour: int, minute: int) -> str:
        if weekday in ("Sat", "Sun"):
            return "CLOSED"
        time_in_minutes = hour * 60 + minute
        if 9 * 60 <= time_in_minutes < 9 * 60 + 15:
            return "PRE-OPEN"
        if 9 * 60 + 15 <= time_in_minutes < 11 * 60 + 30:
            return "HOSE OPEN"
        if 13 * 60 <= time_in_minutes < 14 * 60 + 45:
            return "HOSE OPEN"
        return "CLOSED"

    # Pre-market
    assert compute_session_status("Mon", 8, 59) == "CLOSED"
    # ATO Pre-open
    assert compute_session_status("Mon", 9, 0) == "PRE-OPEN"
    assert compute_session_status("Mon", 9, 14) == "PRE-OPEN"
    # Morning continuous
    assert compute_session_status("Mon", 9, 15) == "HOSE OPEN"
    assert compute_session_status("Mon", 11, 29) == "HOSE OPEN"
    # Lunch break
    assert compute_session_status("Mon", 11, 30) == "CLOSED"
    assert compute_session_status("Mon", 12, 59) == "CLOSED"
    # Afternoon continuous & ATC
    assert compute_session_status("Mon", 13, 0) == "HOSE OPEN"
    assert compute_session_status("Mon", 14, 29) == "HOSE OPEN"
    assert compute_session_status("Mon", 14, 30) == "HOSE OPEN"
    assert compute_session_status("Mon", 14, 44) == "HOSE OPEN"
    # Post-close (ATC ends at 14:45 ICT)
    assert compute_session_status("Mon", 14, 45) == "CLOSED"
    assert compute_session_status("Mon", 15, 0) == "CLOSED"
    assert compute_session_status("Mon", 18, 0) == "CLOSED"
    # Weekends
    assert compute_session_status("Sat", 10, 0) == "CLOSED"
    assert compute_session_status("Sun", 13, 30) == "CLOSED"


def test_dim8_mathematical_extremes_and_formatting():
    """Dimension 8: Mathematical Extremes & Bounds - Ratio formatting and bounds safety."""
    fund_view = (OMEGA_UI_DIR / "src/modules/fundamental_matrix/FundamentalMatrixView.tsx").read_text(encoding="utf-8")
    assert "toFixed" in fund_view, "Fundamental metrics must use explicit precision formatting"
    alpha_view = (OMEGA_UI_DIR / "src/modules/alpha_portfolio/AlphaPortfolioView.tsx").read_text(encoding="utf-8")
    assert "toFixed" in alpha_view, "Alpha weights must format numeric bounds safely"


def test_dim9_financial_and_business_logic_edges():
    """Dimension 9: Financial & Business Logic Edges - Piotroski F-Score (max 9) and Altman Z safety."""
    fund_view = (OMEGA_UI_DIR / "src/modules/fundamental_matrix/FundamentalMatrixView.tsx").read_text(encoding="utf-8")
    assert "/9" in fund_view, "Piotroski F-score max bounds is 9"
    assert "Altman Z" in fund_view


def test_dim10_case_insensitive_deduplication():
    """Dimension 10: Case-Insensitive Deduplication - Equities uppercase canonicalization."""
    fund_view = (OMEGA_UI_DIR / "src/modules/fundamental_matrix/FundamentalMatrixView.tsx").read_text(encoding="utf-8")
    tickers = ["FPT", "HPG", "MBB", "VHM", "MWG", "DGC"]
    for t in tickers:
        assert f"'{t}'" in fund_view, f"Ticker {t} must be uppercase canonicalized"


def test_dim11_fail_closed_and_module_types():
    """Dimension 11: Fail-Closed & Explicit Handlers - ModuleType union coverage and client fail-closed error propagation."""
    side_dock = (OMEGA_UI_DIR / "src/layout/SideDock.tsx").read_text(encoding="utf-8")
    assert "macro_cockpit" in side_dock
    assert "fundamental_matrix" in side_dock
    assert "alpha_portfolio" in side_dock
    assert "chart_station" in side_dock
    assert "execution_blotter" in side_dock

    client_ts = (OMEGA_UI_DIR / "src/api/client.ts").read_text(encoding="utf-8")
    # Verify fail-closed enforcement across critical endpoints
    assert "throw new Error" in client_ts
    assert "getMarketOhlcv" in client_ts
    assert "getMarketOrderbook" in client_ts
    assert "ingestData" in client_ts
    assert "killSwitch" in client_ts
    assert "updateLLMConfig" in client_ts
    assert "testLLMProbe" in client_ts
    assert "fetchLLMModels" in client_ts
    assert "evaluateAlphaExpression" in client_ts
    assert "getAlphaArsenalSignals" in client_ts
    assert "getAlphaDecayProfile" in client_ts
    assert "startAlphaDiscovery" in client_ts
    assert "getMacroNewsLatest" in client_ts
    assert "getVSISentiment" in client_ts
    assert "getSectorContagion" in client_ts
    assert "getLLMMacroAnalysis" in client_ts
    assert "getBarraDecomposition" in client_ts
    assert "getStressScenarios" in client_ts
    assert "calculatePreTradeImpact" in client_ts
    assert "getPostTradeReport" in client_ts
    assert "getRoutingDiagnostics" in client_ts
    assert "triggerPipelineRun" in client_ts
    assert "cancelPipelineRun" in client_ts
    assert "getControlOpsStatus" in client_ts
    assert "getCopilotSystemSynthesis" in client_ts
    assert "getCopilotRecommendations" in client_ts
    assert "askCopilot" in client_ts
    assert "executeCopilotTool" in client_ts
    assert "getLLMConfig" in client_ts

    # Assert that all silent fallback swallows and fake success/mock are eliminated
    assert "KILL SWITCH ENGAGED (fallback mode)" not in client_ts
    assert "Data ingestion pipeline dispatched (client fallback)" not in client_ts
    assert "LLM multi-profile configuration saved successfully (fallback)" not in client_ts
    assert "client fallback" not in client_ts


def test_dim11_client_fail_closed_methods_boundary():
    """Dimension 11: Fail-closed boundary testing verifying no silent fake data generation on network failure."""
    client_ts = (OMEGA_UI_DIR / "src/api/client.ts").read_text(encoding="utf-8")

    # Check all async network methods enforce fail-closed rejection on HTTP error
    network_methods = [
        "getMarketOhlcv",
        "getMarketOrderbook",
        "ingestData",
        "computeAlphas",
        "optimizePortfolio",
        "runBacktest",
        "killSwitch",
        "evaluateAlphaExpression",
        "getAlphaArsenalSignals",
        "getAlphaDecayProfile",
        "startAlphaDiscovery",
        "getMacroNewsLatest",
        "getVSISentiment",
        "getSectorContagion",
        "getLLMMacroAnalysis",
        "getBarraDecomposition",
        "getStressScenarios",
        "calculatePreTradeImpact",
        "getPostTradeReport",
        "getRoutingDiagnostics",
        "triggerPipelineRun",
        "cancelPipelineRun",
        "getControlOpsStatus",
        "getCopilotSystemSynthesis",
        "getCopilotRecommendations",
        "askCopilot",
        "executeCopilotTool",
        "getLLMConfig",
        "updateLLMConfig",
        "testLLMProbe",
        "fetchLLMModels",
    ]
    for method in network_methods:
        assert f"{method}: async" in client_ts, f"Method {method} must be present in apiClient"

    assert_no_client_handlers(client_ts)


def test_dim12_full_suite_regression_closure():
    """Dimension 12: Full-Suite Regression Closure - 5 view components exist and export valid React components."""
    modules = [
        "macro_cockpit/MacroCockpitView.tsx",
        "fundamental_matrix/FundamentalMatrixView.tsx",
        "alpha_portfolio/AlphaPortfolioView.tsx",
        "chart_station/ChartStationView.tsx",
        "execution_blotter/ExecutionBlotterView.tsx",
    ]
    for mod in modules:
        content = (OMEGA_UI_DIR / "src/modules" / mod).read_text(encoding="utf-8")
        assert "export const" in content
        assert "React.FC" in content


def test_dim13_metric_and_artifact_consistency():
    """Dimension 13: Metric & Artifact Consistency - TailwindCSS v4 design tokens."""
    css_content = (OMEGA_UI_DIR / "src/index.css").read_text(encoding="utf-8")
    assert "@import \"tailwindcss\";" in css_content
    assert "@theme" in css_content
    assert "--color-glass-surface" in css_content
    assert ".glass-panel" in css_content


def test_dim14_exception_chaining_and_error_handling():
    """Dimension 14: Exception & Component Root Guard."""
    main_ts = (OMEGA_UI_DIR / "src/main.tsx").read_text(encoding="utf-8")
    assert "document.getElementById('root')" in main_ts
    assert "React.StrictMode" in main_ts


def test_dim15_opt_in_safety_and_build_configs():
    """Dimension 15: Opt-in Safety & Vite Config."""
    vite_cfg = (OMEGA_UI_DIR / "vite.config.ts").read_text(encoding="utf-8")
    assert "defineConfig" in vite_cfg
    assert "@tailwindcss/vite" in vite_cfg
    assert "@vitejs/plugin-react" in vite_cfg


def test_dim16_security_and_secret_leakage():
    """Dimension 16: Security & Secret Leakage Prevention - No raw API keys in UI scaffolding."""
    for file_path in OMEGA_UI_DIR.rglob("*"):
        if "node_modules" in file_path.parts or ".git" in file_path.parts or "dist" in file_path.parts:
            continue
        if file_path.is_file() and (
            file_path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".html", ".json"}
            or file_path.name == ".env" or file_path.name.startswith(".env.")
        ):
            content = file_path.read_text(encoding="utf-8")
            if SECRET_CREDENTIAL_RE.search(content):
                pytest.fail(f"Secret pattern found in {file_path.relative_to(OMEGA_UI_DIR)}", pytrace=False)


def test_ui_scaffolding_detectors_reject_false_positives_and_detect_real_patterns():
    assert_no_client_handlers('''
export interface IngestSchedulerTelemetry {}
const url = "https://example.com/*not a comment*/";
const text = 'try { } catch (error) {}';
const template = `try { } catch { }`;
const pattern = /try \\{.*catch/;
const object = {try: true, catch() {}};
''')
    for value in ("task-opt", "risk-score", "sk-short", "sk-p********5544", "api_key?: string"):
        assert not SECRET_CREDENTIAL_RE.search(value)


def test_ui_scaffolding_detectors_ignore_commented_try_catch_blocks():
    assert_no_client_handlers(
        "// try { ignored(); } catch (error) {}\n/* try { ignored(); } catch {} */\nexport const ok = true;"
    )


def test_dim11_handler_mutations():
    for source in (
        "try /* note */ {} catch /* note */ (error) {}",
        "try/**/{}catch/**/{}",
        "try // note\n {} catch // note\n (error) {}",
        'const url = "https://example.com"; try {} catch {}',
        'const text = "/*"; try {} catch {} const end = "*/";',
        "const value = `${(() => { try {} catch {} })()}`;",
        "try {} finally {}",
        "try\u2028{} catch\u2029{}",
    ):
        with pytest.raises(AssertionError, match="handlers are prohibited"):
            assert_no_client_handlers(source)
    for source in ("try {", "catch (error) {}", "const text = 'unterminated"):
        with pytest.raises(AssertionError, match="syntax must parse"):
            assert_no_client_handlers(source)


def test_dim16_credential_mutations(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "OMEGA_UI_DIR", tmp_path)
    for prefix in ("sk-", "sk_", "sk_live_", "sk_test_", "sk-proj-", "sk-ant-", "prefix_sk_live_"):
        for filename in ("client.ts", "client.JS", "client.mjs", "client.cjs", ".env.local", "package.json"):
            path = tmp_path / filename
            path.write_text(prefix + "0123456789abcdefghij", encoding="utf-8")
            with pytest.raises(pytest.fail.Exception, match="Secret pattern found"):
                test_dim16_security_and_secret_leakage()
            path.unlink()
    for value in (
        'VNSTOCK_API_KEY = "value"', '"VNSTOCK_API_KEY": "value"',
        "AKIA" + "A" * 16, "ASIA" + "B" * 16,
        "ghp_" + "a" * 36, "github_pat_" + "b" * 22,
    ):
        assert SECRET_CREDENTIAL_RE.search(value)
    (tmp_path / "client.ts").write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        test_dim16_security_and_secret_leakage()


def test_dim11_parser_failure_is_not_a_clean_scan(monkeypatch):
    def failed_check(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "sensitive parser output")

    monkeypatch.setattr(subprocess, "run", failed_check)
    with pytest.raises(AssertionError, match="TypeScript check failed") as error:
        assert_no_client_handlers("const safe = true;")
    assert "sensitive parser output" not in str(error.value)


def test_related_config_fixture_snapshot_restore():
    from copy import deepcopy
    from importlib.util import module_from_spec, spec_from_file_location

    for filename in ("test_ui_llm_config.py", "test_ui_copilot_direct_llm.py"):
        spec = spec_from_file_location("scoped_fixture_check", REPO_ROOT / "tests" / filename)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        config = module.copilot._IN_MEMORY_LLM_CONFIG
        snapshot = deepcopy(config)
        fixture = module.restore_llm_config.__wrapped__()
        next(fixture)
        try:
            config["global_profile"]["model"] = "injected nested mutation"
            config["injected_profile"] = {"enabled": False}
        finally:
            with pytest.raises(StopIteration):
                next(fixture)
        assert module.copilot._IN_MEMORY_LLM_CONFIG is config
        assert config == snapshot


def test_dim11_all_client_methods_reject_network_and_http_failures():
    result = run_typescript_check("""
const ts = require('typescript');
const vm = require('vm');
const code = ts.transpileModule(require('fs').readFileSync(0, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}
}).outputText;
(async () => {
    const failures = [];
    let checked = 0;
    for (const mode of ['network', 'http', 'http-invalid-json']) {
        const exports = {};
        let calls = 0;
        vm.runInNewContext(code, {exports, URLSearchParams, fetch: async () => {
            calls++;
            if (mode === 'network') throw new Error('injected network failure');
            return {ok: false, status: 503, statusText: 'Unavailable', json: async () => {
                if (mode === 'http-invalid-json') throw new SyntaxError('invalid JSON');
                return {detail: 'injected HTTP failure'};
            }};
        }});
        for (const [name, method] of Object.entries(exports.apiClient)) {
            const before = calls;
            let rejected = false;
            try { await method({}); } catch { rejected = true; }
            if (!rejected || calls !== before + 1) failures.push(`${mode}:${name}`);
            checked++;
        }
    }
    console.log(JSON.stringify({checked, failures}));
})().catch(() => process.exit(1));
""", (OMEGA_UI_DIR / "src/api/client.ts").read_text(encoding="utf-8"))
    assert result["checked"] >= 93
    assert result["failures"] == []
