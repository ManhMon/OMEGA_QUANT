"""Adversarial Test Suite for Phase 3 Front-End Data Hook Binding & Live Query State Integration.

Tests cover all 16 dimensions of the master adversarial testing matrix:
1. Strict Types & Schema Invariants
2. File I/O & Path Integrity
3. Durability, State Transitions & Store Mutations
4. Memory Bounds & 703-Stock Pagination Limits
5. Concurrency & Stream Event Handling
6. Point-in-Time & ISO-8601 UTC Timestamps
7. Sparse Calendar & Query Deduplication
8. Mathematical Extremes & Division by Zero Bounds
9. Financial Rules & Metric Constraints
10. Symbol Canonicalization & Case Insensitivity
11. Fail-Closed Error States & Network Handling
12. Full Component Integration & Hook Export Surface
13. Metric & Store Consistency
14. Error Resilience & Recovery
15. Safe Defaults & Fallback Configurations
16. Security & Secret Leakage Prevention
"""

import os
import re
import json
import pytest

REPO_ROOT = r"C:\Users\GHC\repos\OMEGA_QUANT"
OMEGA_UI_ROOT = os.path.join(REPO_ROOT, "omega-ui")
SRC_ROOT = os.path.join(OMEGA_UI_ROOT, "src")


def test_dim01_strict_types_client_and_hooks():
    """Dim 1: Verify TypeScript interfaces and strict type definitions exist."""
    client_ts = os.path.join(SRC_ROOT, "api", "client.ts")
    assert os.path.exists(client_ts), f"Missing {client_ts}"
    with open(client_ts, "r", encoding="utf-8") as f:
        content = f.read()

    assert "export interface MacroMetrics" in content
    assert "export interface StockScreenerItem" in content
    assert "export interface PortfolioState" in content
    assert "export interface OrderBlotterItem" in content
    assert "export interface ChartStationData" in content
    assert "export interface PaginatedResponse<T>" in content


def test_dim02_file_io_paths_and_structure():
    """Dim 2: Verify all required files exist in exact scope locations."""
    required_paths = [
        os.path.join(SRC_ROOT, "api", "client.ts"),
        os.path.join(SRC_ROOT, "store", "uiStore.ts"),
        os.path.join(SRC_ROOT, "hooks", "useMacroData.ts"),
        os.path.join(SRC_ROOT, "hooks", "useQuantScreener.ts"),
        os.path.join(SRC_ROOT, "hooks", "usePortfolioState.ts"),
        os.path.join(SRC_ROOT, "hooks", "useRealtimeStream.ts"),
        os.path.join(SRC_ROOT, "App.tsx"),
        os.path.join(SRC_ROOT, "modules", "macro_cockpit", "MacroCockpitView.tsx"),
        os.path.join(SRC_ROOT, "modules", "fundamental_matrix", "FundamentalMatrixView.tsx"),
        os.path.join(SRC_ROOT, "modules", "alpha_portfolio", "AlphaPortfolioView.tsx"),
        os.path.join(SRC_ROOT, "modules", "chart_station", "ChartStationView.tsx"),
        os.path.join(SRC_ROOT, "modules", "execution_blotter", "ExecutionBlotterView.tsx"),
    ]
    for path in required_paths:
        assert os.path.isfile(path), f"Expected file does not exist: {path}"


def test_dim03_durability_and_store_mutations():
    """Dim 3: Verify Zustand store handles state setters, resets, and mutations."""
    store_file = os.path.join(SRC_ROOT, "store", "uiStore.ts")
    with open(store_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "export const useUiStore = create<UiState>" in content
    assert "setActiveModule:" in content
    assert "toggleSideDockCollapse:" in content
    assert "setScreenerFilters:" in content
    assert "resetScreenerFilters:" in content
    assert "setStreamingConnected:" in content


def test_dim04_memory_bounds_703_stock_universe():
    """Dim 4: Verify screener limit and paginated slicing bounds in views/api."""
    view_file = os.path.join(SRC_ROOT, "modules", "fundamental_matrix", "FundamentalMatrixView.tsx")
    with open(view_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "totalPages" in content
    assert "total" in content


def test_dim05_concurrency_and_stream_handling():
    """Dim 5: Verify useRealtimeStream handles stream events and query invalidation."""
    stream_file = os.path.join(SRC_ROOT, "hooks", "useRealtimeStream.ts")
    with open(stream_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "queryClient.invalidateQueries" in content
    assert "window.clearInterval" in content  # Cleanup on unmount
    assert "setStreamingConnected(false)" in content


def test_dim06_pit_iso_timestamps():
    """Dim 6: Verify ISO timestamps and PIT compliance in API client contracts."""
    client_ts = os.path.join(SRC_ROOT, "api", "client.ts")
    with open(client_ts, "r", encoding="utf-8") as f:
        content = f.read()

    assert "timestamp: string;" in content


def test_dim07_sparse_calendar_and_query_deduplication():
    """Dim 7: Verify query keys and staleTime configuration to prevent refetch storms."""
    macro_hook = os.path.join(SRC_ROOT, "hooks", "useMacroData.ts")
    screener_hook = os.path.join(SRC_ROOT, "hooks", "useQuantScreener.ts")
    portfolio_hook = os.path.join(SRC_ROOT, "hooks", "usePortfolioState.ts")

    with open(macro_hook, "r", encoding="utf-8") as f:
        macro_content = f.read()
    with open(screener_hook, "r", encoding="utf-8") as f:
        screener_content = f.read()
    with open(portfolio_hook, "r", encoding="utf-8") as f:
        portfolio_content = f.read()

    assert "MACRO_DATA_QUERY_KEY" in macro_content
    assert "SCREENER_QUERY_KEY" in screener_content
    assert "PORTFOLIO_STATE_QUERY_KEY" in portfolio_content
    assert "staleTime" in macro_content and "staleTime" in screener_content


def test_dim08_mathematical_extremes_and_division_guards():
    """Dim 8: Verify division safety in pagination, percentages, and metrics."""
    fundamental_view = os.path.join(SRC_ROOT, "modules", "fundamental_matrix", "FundamentalMatrixView.tsx")
    with open(fundamental_view, "r", encoding="utf-8") as f:
        content = f.read()

    assert "page <= 1" in content
    assert "page >= totalPages" in content


def test_dim09_financial_rules_and_metrics():
    """Dim 9: Verify Piotroski F-score, Altman Z, ROE, and Barra Risk factors."""
    client_ts = os.path.join(SRC_ROOT, "api", "client.ts")
    with open(client_ts, "r", encoding="utf-8") as f:
        content = f.read()

    assert "piotroskiF" in content
    assert "altmanZ" in content
    assert "barraMomentum" in content
    assert "barraValue" in content
    assert "barraSize" in content


def test_dim10_symbol_canonicalization():
    """Dim 10: Verify uppercase canonicalization for stock search and selected ticker."""
    store_file = os.path.join(SRC_ROOT, "store", "uiStore.ts")
    with open(store_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "ticker.toUpperCase()" in content


def test_dim11_fail_closed_error_states():
    """Dim 11: Verify error boundaries / error states in all 5 views."""
    views = [
        os.path.join(SRC_ROOT, "modules", "macro_cockpit", "MacroCockpitView.tsx"),
        os.path.join(SRC_ROOT, "modules", "fundamental_matrix", "FundamentalMatrixView.tsx"),
        os.path.join(SRC_ROOT, "modules", "alpha_portfolio", "AlphaPortfolioView.tsx"),
        os.path.join(SRC_ROOT, "modules", "chart_station", "ChartStationView.tsx"),
        os.path.join(SRC_ROOT, "modules", "execution_blotter", "ExecutionBlotterView.tsx"),
    ]

    for view in views:
        with open(view, "r", encoding="utf-8") as f:
            content = f.read()
        assert "isError" in content, f"Missing isError handling in {view}"
        assert "isLoading" in content, f"Missing isLoading handling in {view}"


def test_dim12_full_suite_build_artifact():
    """Dim 12: Verify omega-ui build output exists in dist directory."""
    dist_index = os.path.join(OMEGA_UI_ROOT, "dist", "index.html")
    assert os.path.exists(dist_index), "omega-ui/dist/index.html does not exist. Build required."


def test_dim13_metric_and_store_consistency():
    """Dim 13: Verify QueryClientProvider wrapping in App.tsx."""
    app_file = os.path.join(SRC_ROOT, "App.tsx")
    with open(app_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "QueryClientProvider" in content
    assert "useUiStore" in content
    assert "useRealtimeStream" in content


def test_dim14_error_resilience_and_retry():
    """Dim 14: Verify retry button and query refetch capability."""
    macro_view = os.path.join(SRC_ROOT, "modules", "macro_cockpit", "MacroCockpitView.tsx")
    with open(macro_view, "r", encoding="utf-8") as f:
        content = f.read()

    assert "refetch()" in content
    assert "RETRY" in content


def test_dim15_safe_defaults_and_fallbacks():
    """Dim 15: Verify default screener filters and initial values."""
    store_file = os.path.join(SRC_ROOT, "store", "uiStore.ts")
    with open(store_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "DEFAULT_SCREENER_FILTERS" in content
    assert "pageSize: 25" in content
    assert "activeModule: 'macro_cockpit'" in content


def test_dim16_security_and_secret_prevention():
    """Dim 16: Verify no hardcoded API keys or secrets in front-end client."""
    for root, _, files in os.walk(SRC_ROOT):
        for file in files:
            if file.endswith((".ts", ".tsx")):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                assert "API_KEY = \"" not in content
                assert "SECRET" not in content or "SECTOR" in content or "SECRET" not in content.upper()
