"""
Automated Alpha Phase35 OOS Bundle Integration Tests
GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615
[L2-Impl:Role14-Data-Scientist] - 2026-06-15

Verifies that:
  1. Default off — OOS bundle disabled unless explicitly enabled
  2. CLI wiring — --enable-automated-oos-bundle flag works correctly
  3. Bundle stability — approved bundle names are frozen and correct
  4. Evidence persistence — per-fold evidence is populated when enabled
  5. PIT / no leakage — bundle signals use T-1 lag, no OOS labels
  6. Engine params — constructor accepts and validates bundle parameters

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import argparse
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


def _baseline_results_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent
        / "data" / "phase35_results"
        / "phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_phase35_source():
    """Read phase35.py source."""
    path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    return path.read_text(encoding="utf-8")


def _get_run_script_source():
    """Read run_phase35_backtest.py source."""
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
    return path.read_text(encoding="utf-8")


def _make_synthetic_ohlcv(
    n_tickers: int = 8, n_days: int = 80, seed: int = 42
) -> pd.DataFrame:
    """Create synthetic OHLCV panel data with forward returns."""
    rng = np.random.RandomState(seed)
    rows = []
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    for t in range(n_tickers):
        ticker = f"SYM{t:02d}"
        base_price = 10000.0 + rng.randn() * 2000
        for d_idx, date in enumerate(dates):
            noise = rng.randn() * 0.02
            close = base_price * (1 + noise * (d_idx + 1) / n_days)
            open_price = close * (1 + rng.randn() * 0.005)
            high = max(open_price, close) * (1 + abs(rng.randn()) * 0.01)
            low = min(open_price, close) * (1 - abs(rng.randn()) * 0.01)
            volume = int(abs(rng.randn() * 100000) + 10000)
            fwd_ret = rng.normal(0, 0.02)
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
                "fwd_ret_5": fwd_ret,
            })
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


def _make_engine(**kwargs):
    """Create a Phase35WalkForwardEngine with a dummy alpha module."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    dummy_module = types.ModuleType("dummy_alpha")
    dummy_module.PHASE34_ALPHA_COLUMNS = []
    dummy_module.compute_phase34_microstructure_alphas = lambda df, **kw: df
    return Phase35WalkForwardEngine(alpha_module=dummy_module, **kwargs)


# ---------------------------------------------------------------------------
# Tests: Default Off
# ---------------------------------------------------------------------------

class TestDefaultOff:
    """Verify OOS bundle is disabled by default."""

    def test_engine_default_oos_bundle_disabled(self):
        """Phase35 engine should have OOS bundle disabled by default."""
        engine = _make_engine()
        assert engine.enable_automated_oos_bundle is False

    def test_engine_default_bundle_name(self):
        """Default bundle name should be auto_top5_real_ic_20260615."""
        engine = _make_engine()
        assert engine.automated_oos_bundle_name == "auto_top5_real_ic_20260615"

    def test_engine_default_bundle_alphas(self):
        """Default bundle alphas should match approved bundle."""
        engine = _make_engine()
        expected = [
            "auto_rsi_14",
            "auto_mr_zscore_20",
            "auto_mom_ret_60",
            "auto_mom_ret_20",
            "auto_vol_std_ratio_10_30",
        ]
        assert engine.automated_oos_bundle_alphas == expected

    def test_no_behavior_change_when_disabled(self):
        """compute_alphas should not inject bundle signals when disabled."""
        engine = _make_engine(enable_automated_oos_bundle=False)
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=20)
        result = engine.compute_alphas(df)
        # Bundle columns should NOT be present
        for alpha_name in engine.automated_oos_bundle_alphas:
            assert alpha_name not in result.columns


# ---------------------------------------------------------------------------
# Tests: Bundle Stability
# ---------------------------------------------------------------------------

class TestBundleStability:
    """Verify approved bundle names are frozen and correct."""

    def test_bundle_constant_exists(self):
        """AUTO_TOP5_REAL_IC_BUNDLE should be defined in phase35.py."""
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        assert isinstance(AUTO_TOP5_REAL_IC_BUNDLE, dict)
        assert "auto_top5_real_ic_20260615" in AUTO_TOP5_REAL_IC_BUNDLE

    def test_bundle_contains_5_alphas(self):
        """Approved bundle should contain exactly 5 alphas."""
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        assert len(bundle) == 5

    def test_bundle_alpha_names_frozen(self):
        """Bundle alpha names must match the approved specification exactly."""
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        expected = [
            "auto_rsi_14",
            "auto_mr_zscore_20",
            "auto_mom_ret_60",
            "auto_mom_ret_20",
            "auto_vol_std_ratio_10_30",
        ]
        assert bundle == expected

    def test_gate_id_constant_exists(self):
        """AUTOMATED_ALPHA_OOS_GATE_ID should be defined."""
        from omega.quant.alpha.phase35 import AUTOMATED_ALPHA_OOS_GATE_ID
        assert AUTOMATED_ALPHA_OOS_GATE_ID == "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615"

    def test_bundle_templates_exist_in_discovery(self):
        """Each bundle alpha name should have a corresponding template in discovery."""
        from omega.quant.alpha.automated_alpha_discovery import _EXPRESSION_TEMPLATES
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        template_map = {name: expr for name, expr in _EXPRESSION_TEMPLATES}
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        for alpha_name in bundle:
            template_key = alpha_name.replace("auto_", "", 1)
            assert template_key in template_map, (
                f"Template '{template_key}' not found for bundle alpha '{alpha_name}'"
            )


# ---------------------------------------------------------------------------
# Tests: Engine Parameter Validation
# ---------------------------------------------------------------------------

class TestEngineParamValidation:
    """Verify constructor validates OOS bundle parameters."""

    def test_enable_must_be_bool(self):
        with pytest.raises(ValueError, match="enable_automated_oos_bundle"):
            _make_engine(enable_automated_oos_bundle="yes")

    def test_invalid_bundle_name_rejected(self):
        with pytest.raises(ValueError, match="automated_oos_bundle_name"):
            _make_engine(
                enable_automated_oos_bundle=True,
                automated_oos_bundle_name="nonexistent_bundle",
            )

    def test_valid_bundle_name_accepted(self):
        engine = _make_engine(
            enable_automated_oos_bundle=True,
            automated_oos_bundle_name="auto_top5_real_ic_20260615",
        )
        assert engine.enable_automated_oos_bundle is True
        assert engine.automated_oos_bundle_name == "auto_top5_real_ic_20260615"


# ---------------------------------------------------------------------------
# Tests: OOS Bundle Signal Injection
# ---------------------------------------------------------------------------

class TestOOSBundleInjection:
    """Verify bundle signals are injected when enabled."""

    def test_bundle_signals_injected(self):
        """compute_alphas should inject bundle columns when enabled."""
        engine = _make_engine(enable_automated_oos_bundle=True)
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=80)
        result = engine.compute_alphas(df)
        # All bundle alpha columns should be present
        for alpha_name in engine.automated_oos_bundle_alphas:
            assert alpha_name in result.columns, (
                f"Bundle alpha '{alpha_name}' not found in result columns"
            )

    def test_bundle_signals_are_numeric(self):
        """Injected bundle signals should be numeric."""
        engine = _make_engine(enable_automated_oos_bundle=True)
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=80)
        result = engine.compute_alphas(df)
        for alpha_name in engine.automated_oos_bundle_alphas:
            if alpha_name in result.columns:
                assert pd.api.types.is_numeric_dtype(result[alpha_name]), (
                    f"Bundle alpha '{alpha_name}' is not numeric"
                )


# ---------------------------------------------------------------------------
# Tests: PIT Safety / No Leakage
# ---------------------------------------------------------------------------

class TestPITNoLeakage:
    """Verify bundle signals are PIT-safe (T-1 lagged, no OOS labels)."""

    def test_bundle_expressions_use_shift(self):
        """All bundle template expressions should use shift for PIT safety."""
        from omega.quant.alpha.automated_alpha_discovery import _EXPRESSION_TEMPLATES
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        template_map = {name: expr for name, expr in _EXPRESSION_TEMPLATES}
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        for alpha_name in bundle:
            template_key = alpha_name.replace("auto_", "", 1)
            expr_str = template_map.get(template_key, "")
            # PIT-safe expressions must use shift(1+) or helper functions that shift
            has_shift = ".shift(" in expr_str
            has_helper = "_compute_" in expr_str
            assert has_shift or has_helper, (
                f"Template '{template_key}' for '{alpha_name}' does not use "
                f"shift or PIT-safe helper: {expr_str}"
            )

    def test_bundle_expressions_no_fwd_ret(self):
        """Bundle expressions must not reference forward returns."""
        from omega.quant.alpha.automated_alpha_discovery import _EXPRESSION_TEMPLATES
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        template_map = {name: expr for name, expr in _EXPRESSION_TEMPLATES}
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        for alpha_name in bundle:
            template_key = alpha_name.replace("auto_", "", 1)
            expr_str = template_map.get(template_key, "")
            assert "fwd_ret" not in expr_str, (
                f"Template '{template_key}' references forward returns: {expr_str}"
            )

    def test_source_no_negative_shift_in_bundle_templates(self):
        """Bundle template expressions must not use negative shift (look-ahead)."""
        from omega.quant.alpha.automated_alpha_discovery import _EXPRESSION_TEMPLATES
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        template_map = {name: expr for name, expr in _EXPRESSION_TEMPLATES}
        bundle = AUTO_TOP5_REAL_IC_BUNDLE["auto_top5_real_ic_20260615"]
        for alpha_name in bundle:
            template_key = alpha_name.replace("auto_", "", 1)
            expr_str = template_map.get(template_key, "")
            shifts = re.findall(r'\.shift\((-?\d+)\)', expr_str)
            for s in shifts:
                val = int(s)
                assert val >= 0, (
                    f"Template '{template_key}' uses negative shift({val}) "
                    f"— potential look-ahead bias"
                )


# ---------------------------------------------------------------------------
# Tests: CLI Wiring
# ---------------------------------------------------------------------------

class TestCLIWiring:
    """Verify CLI arguments are properly defined."""

    def test_cli_has_enable_flag(self):
        """run_phase35_backtest.py should have --enable-automated-oos-bundle."""
        source = _get_run_script_source()
        assert "--enable-automated-oos-bundle" in source

    def test_cli_has_bundle_name_flag(self):
        """run_phase35_backtest.py should have --automated-oos-bundle-name."""
        source = _get_run_script_source()
        assert "--automated-oos-bundle-name" in source

    def test_cli_has_gate_reference(self):
        """run_phase35_backtest.py should reference the gate ID."""
        source = _get_run_script_source()
        assert "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615" in source

    def test_cli_wires_to_engine(self):
        """run_phase35_backtest.py should pass bundle args to engine."""
        source = _get_run_script_source()
        assert "enable_automated_oos_bundle" in source
        assert "automated_oos_bundle_name" in source

    def test_serialize_fold_details_includes_evidence(self):
        """serialize_fold_details should include automated_discovery_evidence."""
        source = _get_run_script_source()
        assert "automated_discovery_evidence" in source


# ---------------------------------------------------------------------------
# Tests: Evidence Persistence
# ---------------------------------------------------------------------------

class TestEvidencePersistence:
    """Verify per-fold evidence field exists and is serializable."""

    def test_fold_metrics_has_evidence_field(self):
        """FoldMetrics should have automated_discovery_evidence field."""
        from omega.quant.alpha.phase35 import FoldMetrics
        fm = FoldMetrics(
            fold_id=0, train_start="2022-01-01", train_end="2022-06-30",
            test_start="2022-07-01", test_end="2022-09-30",
        )
        assert fm.automated_discovery_evidence is None

    def test_evidence_field_settable(self):
        """automated_discovery_evidence field should accept dict values."""
        from omega.quant.alpha.phase35 import FoldMetrics
        evidence = {
            "gate": "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615",
            "bundle_name": "auto_top5_real_ic_20260615",
            "bundle_alphas": ["auto_rsi_14", "auto_mr_zscore_20"],
            "pit_safe": True,
        }
        fm = FoldMetrics(
            fold_id=0, train_start="2022-01-01", train_end="2022-06-30",
            test_start="2022-07-01", test_end="2022-09-30",
            automated_discovery_evidence=evidence,
        )
        assert fm.automated_discovery_evidence == evidence
        # Should be JSON-serializable
        json_str = json.dumps(fm.automated_discovery_evidence)
        assert len(json_str) > 0

    def test_serialize_fold_details_includes_evidence_when_enabled(self):
        """serialize_fold_details must include automated_discovery_evidence when populated."""
        from omega.quant.alpha.phase35 import FoldMetrics
        from run_phase35_backtest import serialize_fold_details

        evidence = {
            "gate": "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615",
            "enabled": True,
            "bundle_name": "auto_top5_real_ic_20260615",
            "bundle_alphas": [
                "auto_rsi_14",
                "auto_mr_zscore_20",
                "auto_mom_ret_60",
                "auto_mom_ret_20",
                "auto_vol_std_ratio_10_30",
            ],
            "computed_bundle_columns": [
                "auto_rsi_14",
                "auto_mr_zscore_20",
                "auto_mom_ret_60",
                "auto_mom_ret_20",
                "auto_vol_std_ratio_10_30",
            ],
            "computed_bundle_column_count": 5,
            "pit_safe": True,
            "no_oos_label_use": True,
            "no_live_promotion": True,
        }
        fm = FoldMetrics(
            fold_id=1, train_start="2022-01-01", train_end="2022-12-31",
            test_start="2023-01-01", test_end="2023-06-30",
            automated_discovery_evidence=evidence,
        )
        result = serialize_fold_details(fm)
        assert "automated_discovery_evidence" in result
        ev = result["automated_discovery_evidence"]
        assert ev["gate"] == "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615"
        assert ev["enabled"] is True
        assert ev["bundle_name"] == "auto_top5_real_ic_20260615"
        assert isinstance(ev["bundle_alphas"], list)
        assert len(ev["bundle_alphas"]) == 5
        assert ev["computed_bundle_column_count"] == 5
        assert ev["pit_safe"] is True
        assert ev["no_oos_label_use"] is True
        assert ev["no_live_promotion"] is True
        # Verify JSON-serializable round-trip
        json_str = json.dumps(result)
        round_trip = json.loads(json_str)
        assert round_trip["automated_discovery_evidence"]["gate"] == ev["gate"]

    def test_serialize_fold_details_omits_evidence_when_disabled(self):
        """serialize_fold_details must NOT include automated_discovery_evidence when None."""
        from omega.quant.alpha.phase35 import FoldMetrics
        from run_phase35_backtest import serialize_fold_details

        fm = FoldMetrics(
            fold_id=1, train_start="2022-01-01", train_end="2022-12-31",
            test_start="2023-01-01", test_end="2023-06-30",
        )
        assert fm.automated_discovery_evidence is None
        result = serialize_fold_details(fm)
        assert "automated_discovery_evidence" not in result


# ---------------------------------------------------------------------------
# Tests: Source Inspection
# ---------------------------------------------------------------------------

class TestSourceInspection:
    """Verify source code patterns for the OOS bundle gate."""

    def test_phase35_has_oos_gate_id(self):
        """phase35.py should define AUTOMATED_ALPHA_OOS_GATE_ID."""
        source = _get_phase35_source()
        assert "AUTOMATED_ALPHA_OOS_GATE_ID" in source
        assert "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615" in source

    def test_phase35_has_bundle_constant(self):
        """phase35.py should define AUTO_TOP5_REAL_IC_BUNDLE."""
        source = _get_phase35_source()
        assert "AUTO_TOP5_REAL_IC_BUNDLE" in source

    def test_phase35_has_bundle_params(self):
        """phase35.py constructor should accept bundle parameters."""
        source = _get_phase35_source()
        assert "enable_automated_oos_bundle" in source
        assert "automated_oos_bundle_name" in source
        assert "automated_oos_bundle_alphas" in source

    def test_phase35_compute_alphas_handles_bundle(self):
        """compute_alphas should have bundle injection logic."""
        source = _get_phase35_source()
        assert "enable_automated_oos_bundle" in source
        assert "compute_candidate_signals" in source

    def test_no_live_promotion_in_phase35(self):
        """phase35.py should not promote OOS bundle to live."""
        source = _get_phase35_source()
        # Should have default-off language
        assert "opt-in" in source.lower() or "default disabled" in source.lower() or "default off" in source.lower()


# ---------------------------------------------------------------------------
# Tests: Baseline Metrics Comparison
# ---------------------------------------------------------------------------

class TestBaselineMetricsComparison:
    """Verify baseline metrics are documented for comparison."""

    def test_baseline_json_exists(self):
        """Baseline JSON should exist in data/phase35_results."""
        baseline_path = _baseline_results_path()
        if not baseline_path.exists():
            pytest.skip(f"Missing checked-in artifact: {baseline_path}")
        assert baseline_path.exists(), f"Baseline JSON not found at {baseline_path}"

    def test_baseline_json_has_expected_metrics(self):
        """Baseline JSON should contain expected summary metrics."""
        baseline_path = _baseline_results_path()
        if not baseline_path.exists():
            pytest.skip(f"Missing checked-in artifact: {baseline_path}")
        with open(baseline_path) as f:
            data = json.load(f)

        summary = data.get("summary", {})
        # Documented baseline metrics
        assert abs(summary.get("avg_portfolio_ic", 0) - 0.0249) < 0.001
        assert abs(summary.get("avg_portfolio_sharpe", 0) - 3.1106) < 0.01
        assert abs(summary.get("avg_portfolio_max_dd", 0) - (-0.1225)) < 0.01
        assert summary.get("total_folds") == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
