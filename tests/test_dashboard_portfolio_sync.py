"""
Tests for scripts/update_dashboard_portfolio.py
Gate: DASHBOARD_PORTFOLIO_SYNC_20260618

Regression tests for the L3 [NEEDS_FIX] finding:
  _merge_risk_status must NOT overwrite signal-owned metrics
  (num_trades, exposure, regime_exposure, beta) with stale dashboard values.
  Only monitoring / circuit-breaker metrics survive a merge.
"""

import json
import os
import stat
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure scripts/ is importable
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from scripts.update_dashboard_portfolio import (
    MONITORING_METRICS,
    _merge_risk_status,
    _build_portfolio_section,
    _build_trades_section,
    _build_metrics_section,
    build_risk_status,
    build_pnl_latest,
    _load_json,
    _save_json,
    sync_dashboard_portfolio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_rmtree(path):
    """Remove directory tree with Windows ACL/permission error handling."""
    import shutil

    def _onerror(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception:
            pass
        try:
            func(fpath)
        except Exception:
            pass

    try:
        shutil.rmtree(str(path), onerror=_onerror)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SIGNAL = {
    "date": "2026-06-18",
    "gate": "DASHBOARD_PORTFOLIO_SYNC_20260618",
    "capital": 10_000_000_000.0,
    "total_exposure": 0.25,
    "n_positions": 1,
    "regime": {"state": "BULL", "exposure": 0.8},
    "alpha_sources": {"momentum": 0.6},
    "hrp_weights": {"VNM": 1.0},
    "positions": {
        "VNM": {
            "shares": 1000,
            "price": 25000.0,
            "value_vnd": 25_000_000.0,
            "weight": 0.25,
        }
    },
}


def _make_risk_status(**metric_overrides):
    """Build a minimal risk_status dict with optional metric overrides."""
    metrics = {
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown": 0.0,
        "total_return": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "num_trades": 0,
        "avg_trade": 0.0,
        "var_95": 0.0,
        "var_99": 0.0,
        "cvar_95": 0.0,
        "cvar_99": 0.0,
        "beta": 1.0,
        "volatility": 0.0,
        "exposure": 0.0,
        "regime_exposure": 0.0,
    }
    metrics.update(metric_overrides)
    return {"metrics": metrics, "breached": False, "breached_reasons": []}


# ---------------------------------------------------------------------------
# _merge_risk_status — REGRESSION: signal-owned metrics must NOT be overwritten
# ---------------------------------------------------------------------------

class TestMergeRiskStatusSignalOwnedMetrics(unittest.TestCase):
    """Regression: _merge_risk_status must not overwrite signal-owned metrics."""

    def test_num_trades_not_overwritten_by_stale_value(self):
        """num_trades from the new signal must survive merge."""
        existing = _make_risk_status(num_trades=8)
        new = _make_risk_status(num_trades=1)
        merged = _merge_risk_status(existing, new)
        self.assertEqual(merged["metrics"]["num_trades"], 1)

    def test_exposure_not_overwritten_by_stale_value(self):
        """exposure from the new signal must survive merge."""
        existing = _make_risk_status(exposure=0.4193)
        new = _make_risk_status(exposure=0.25)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["exposure"], 0.25)

    def test_regime_exposure_not_overwritten_by_stale_value(self):
        """regime_exposure from the new signal must survive merge."""
        existing = _make_risk_status(regime_exposure=0.95)
        new = _make_risk_status(regime_exposure=0.8)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["regime_exposure"], 0.8)

    def test_beta_not_overwritten_by_stale_value(self):
        """beta from the new signal must survive merge."""
        existing = _make_risk_status(beta=1.5)
        new = _make_risk_status(beta=1.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["beta"], 1.0)

    def test_all_signal_owned_metrics_fresh(self):
        """All signal-owned metrics come from the new payload, never stale."""
        existing = _make_risk_status(
            num_trades=50,
            exposure=0.99,
            regime_exposure=0.99,
            beta=2.0,
        )
        new = _make_risk_status(
            num_trades=3,
            exposure=0.30,
            regime_exposure=0.60,
            beta=0.9,
        )
        merged = _merge_risk_status(existing, new)
        self.assertEqual(merged["metrics"]["num_trades"], 3)
        self.assertAlmostEqual(merged["metrics"]["exposure"], 0.30)
        self.assertAlmostEqual(merged["metrics"]["regime_exposure"], 0.60)
        self.assertAlmostEqual(merged["metrics"]["beta"], 0.9)


# ---------------------------------------------------------------------------
# _merge_risk_status — monitoring-owned metrics MUST be preserved
# ---------------------------------------------------------------------------

class TestMergeRiskStatusMonitoringMetrics(unittest.TestCase):
    """Monitoring / circuit-breaker metrics with non-zero values must survive."""

    def test_var_95_preserved(self):
        existing = _make_risk_status(var_95=0.02)
        new = _make_risk_status(var_95=0.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["var_95"], 0.02)

    def test_var_99_preserved(self):
        existing = _make_risk_status(var_99=0.05)
        new = _make_risk_status(var_99=0.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["var_99"], 0.05)

    def test_max_drawdown_preserved(self):
        existing = _make_risk_status(max_drawdown=0.15)
        new = _make_risk_status(max_drawdown=0.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["max_drawdown"], 0.15)

    def test_sharpe_ratio_preserved(self):
        existing = _make_risk_status(sharpe_ratio=1.85)
        new = _make_risk_status(sharpe_ratio=0.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["sharpe_ratio"], 1.85)

    def test_zero_monitoring_metric_not_preserved(self):
        """A zero-valued monitoring metric does NOT override the new signal."""
        existing = _make_risk_status(var_95=0.0)
        new = _make_risk_status(var_95=0.0)
        merged = _merge_risk_status(existing, new)
        self.assertAlmostEqual(merged["metrics"]["var_95"], 0.0)

    def test_all_monitoring_metrics_preserved_when_nonzero(self):
        """Every metric in MONITORING_METRICS survives when non-zero."""
        overrides = {m: float(i + 1) * 0.01 for i, m in enumerate(sorted(MONITORING_METRICS))}
        existing = _make_risk_status(**overrides)
        new = _make_risk_status()
        merged = _merge_risk_status(existing, new)
        for metric, expected in overrides.items():
            self.assertAlmostEqual(
                merged["metrics"][metric], expected,
                msg=f"{metric} should be preserved from existing"
            )


# ---------------------------------------------------------------------------
# _merge_risk_status — breached state
# ---------------------------------------------------------------------------

class TestMergeRiskStatusBreachedState(unittest.TestCase):
    """Breached state from monitoring must survive merge."""

    def test_breached_preserved_when_true(self):
        existing = {"metrics": {}, "breached": True, "breached_reasons": ["DD_LIMIT"]}
        new = {"metrics": {}, "breached": False, "breached_reasons": []}
        merged = _merge_risk_status(existing, new)
        self.assertTrue(merged["breached"])
        self.assertEqual(merged["breached_reasons"], ["DD_LIMIT"])

    def test_breached_not_set_when_false(self):
        existing = {"metrics": {}, "breached": False, "breached_reasons": []}
        new = {"metrics": {}, "breached": False, "breached_reasons": []}
        merged = _merge_risk_status(existing, new)
        self.assertFalse(merged["breached"])


# ---------------------------------------------------------------------------
# MONITORING_METRICS whitelist correctness
# ---------------------------------------------------------------------------

class TestMonitoringMetricsWhitelist(unittest.TestCase):
    """Signal-owned metrics must NOT be in the MONITORING_METRICS whitelist."""

    def test_num_trades_not_in_whitelist(self):
        self.assertNotIn("num_trades", MONITORING_METRICS)

    def test_exposure_not_in_whitelist(self):
        self.assertNotIn("exposure", MONITORING_METRICS)

    def test_regime_exposure_not_in_whitelist(self):
        self.assertNotIn("regime_exposure", MONITORING_METRICS)

    def test_beta_not_in_whitelist(self):
        self.assertNotIn("beta", MONITORING_METRICS)

    def test_var_metrics_in_whitelist(self):
        for m in ("var_95", "var_99", "cvar_95", "cvar_99"):
            self.assertIn(m, MONITORING_METRICS)

    def test_drawdown_in_whitelist(self):
        self.assertIn("max_drawdown", MONITORING_METRICS)


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

class TestBuildMetricsSection(unittest.TestCase):
    """_build_metrics_section produces the correct schema."""

    def test_signal_owned_fields_present(self):
        metrics = _build_metrics_section(SAMPLE_SIGNAL)
        self.assertIn("num_trades", metrics)
        self.assertIn("exposure", metrics)
        self.assertIn("regime_exposure", metrics)
        self.assertIn("beta", metrics)

    def test_exposure_computed_from_signal(self):
        metrics = _build_metrics_section(SAMPLE_SIGNAL)
        self.assertAlmostEqual(metrics["exposure"], 0.25)
        self.assertAlmostEqual(metrics["regime_exposure"], 0.8)

    def test_num_trades_from_signal(self):
        metrics = _build_metrics_section(SAMPLE_SIGNAL)
        self.assertEqual(metrics["num_trades"], 1)


class TestBuildPortfolioSection(unittest.TestCase):
    """_build_portfolio_section builds correct holdings."""

    def test_holdings_count(self):
        section = _build_portfolio_section(SAMPLE_SIGNAL, {"VNM": "Consumer"})
        self.assertEqual(section["num_positions"], 1)
        self.assertEqual(len(section["holdings"]), 1)

    def test_sector_mapping_applied(self):
        section = _build_portfolio_section(SAMPLE_SIGNAL, {"VNM": "Consumer"})
        self.assertEqual(section["holdings"][0]["sector"], "Consumer")

    def test_unknown_sector_default(self):
        section = _build_portfolio_section(SAMPLE_SIGNAL, {})
        self.assertEqual(section["holdings"][0]["sector"], "Unknown")


class TestBuildTradesSection(unittest.TestCase):
    """_build_trades_section builds correct trade list."""

    def test_trade_count(self):
        trades = _build_trades_section(SAMPLE_SIGNAL)
        self.assertEqual(len(trades), 1)

    def test_trade_fields(self):
        trades = _build_trades_section(SAMPLE_SIGNAL)
        t = trades[0]
        self.assertEqual(t["symbol"], "VNM")
        self.assertEqual(t["side"], "BUY")
        self.assertEqual(t["date"], "2026-06-18")


# ---------------------------------------------------------------------------
# build_risk_status / build_pnl_latest integration
# ---------------------------------------------------------------------------

class TestBuildRiskStatus(unittest.TestCase):
    """build_risk_status produces a complete dashboard payload."""

    def test_top_level_keys(self):
        rs = build_risk_status(SAMPLE_SIGNAL, {})
        for key in ("timestamp", "system_state", "signal_date", "regime",
                     "metrics", "portfolio", "trades", "breached"):
            self.assertIn(key, rs)

    def test_signal_date(self):
        rs = build_risk_status(SAMPLE_SIGNAL, {})
        self.assertEqual(rs["signal_date"], "2026-06-18")

    def test_reconciliation_does_not_change_circuit_breaker(self):
        reconciliation = {"status": "critical", "aggregate_by_exchange": {"HOSE": {"critical": 1}}, "findings": []}
        rs = build_risk_status(SAMPLE_SIGNAL, {}, reconciliation)
        self.assertEqual(rs["market_data_reconciliation"], reconciliation)
        self.assertFalse(rs["breached"])


class TestBuildPnlLatest(unittest.TestCase):
    """build_pnl_latest produces a correct PnL snapshot."""

    def test_capital_and_exposure(self):
        pnl = build_pnl_latest(SAMPLE_SIGNAL)
        self.assertAlmostEqual(pnl["capital"], 10_000_000_000.0)
        self.assertAlmostEqual(pnl["total_exposure"], 0.25)

    def test_invested_and_cash(self):
        pnl = build_pnl_latest(SAMPLE_SIGNAL)
        expected_invested = round(0.25 * 10_000_000_000.0, 2)
        expected_cash = round(0.75 * 10_000_000_000.0, 2)
        self.assertAlmostEqual(pnl["invested_vnd"], expected_invested)
        self.assertAlmostEqual(pnl["cash_vnd"], expected_cash)


# ---------------------------------------------------------------------------
# End-to-end: sync_dashboard_portfolio with dry_run
# ---------------------------------------------------------------------------

class TestSyncDashboardPortfolioDryRun(unittest.TestCase):
    """sync_dashboard_portfolio in dry_run mode builds payloads without writing."""

    def test_dry_run_returns_success(self):
        """Dry-run with a real signal file should succeed."""
        signal_dir = Path(__file__).resolve().parent.parent / "data" / "paper_trading"
        candidates = sorted(signal_dir.glob("signals_*.json"), reverse=True)
        if not candidates:
            self.skipTest("No signal files in data/paper_trading/")
        ok, summary = sync_dashboard_portfolio(
            signal_file=str(candidates[0]),
            dry_run=True,
        )
        self.assertTrue(ok)
        self.assertTrue(summary.get("dry_run"))

    def test_missing_signal_file_returns_error(self):
        ok, summary = sync_dashboard_portfolio(
            signal_file="/nonexistent/path/signals_2099-01-01.json",
            dry_run=True,
        )
        self.assertFalse(ok)
        self.assertIn("error", summary)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

class TestJsonHelpers(unittest.TestCase):
    """_load_json / _save_json round-trip."""

    def test_save_and_load_round_trip(self):
        _repo_root = Path(__file__).resolve().parent.parent
        _repo_tmp = _repo_root / ".omega_test_tmp" / f"test_json_{uuid.uuid4().hex}"
        _repo_tmp.mkdir(parents=True, exist_ok=True)
        try:
            target = _repo_tmp / "test.json"
            data = {"key": "value", "num": 42}
            self.assertTrue(_save_json(target, data))
            loaded = _load_json(target)
            self.assertEqual(loaded["key"], "value")
            self.assertEqual(loaded["num"], 42)
        finally:
            _safe_rmtree(_repo_tmp)

    def test_load_nonexistent_returns_none(self):
        self.assertIsNone(_load_json(Path("/nonexistent/file.json")))


# ---------------------------------------------------------------------------
# Integration: merge after full build pipeline
# ---------------------------------------------------------------------------

class TestEndToEndMergeRegression(unittest.TestCase):
    """Full pipeline: build -> merge -> verify signal-owned metrics are fresh.

    This is the exact scenario from the L3 audit report:
    existing risk_status had num_trades=8, exposure=0.4193;
    new signal has num_trades=1, exposure=0.25.
    After merge, the new values must win.
    """

    def test_l3_regression_stale_metrics_not_overwriting(self):
        existing = _make_risk_status(
            num_trades=8,
            exposure=0.4193,
            regime_exposure=0.95,
            beta=1.2,
            var_95=0.02,
            max_drawdown=0.15,
        )
        new_signal = build_risk_status(SAMPLE_SIGNAL, {})
        merged = _merge_risk_status(existing, new_signal)

        m = merged["metrics"]
        # Signal-owned: must come from new
        self.assertEqual(m["num_trades"], 1, "num_trades overwritten by stale value")
        self.assertAlmostEqual(m["exposure"], 0.25, msg="exposure overwritten by stale value")
        self.assertAlmostEqual(m["regime_exposure"], 0.8, msg="regime_exposure overwritten")
        self.assertAlmostEqual(m["beta"], 1.0, msg="beta overwritten by stale value")

        # Monitoring-owned: must be preserved from existing
        self.assertAlmostEqual(m["var_95"], 0.02, msg="var_95 not preserved")
        self.assertAlmostEqual(m["max_drawdown"], 0.15, msg="max_drawdown not preserved")


if __name__ == "__main__":
    unittest.main()
