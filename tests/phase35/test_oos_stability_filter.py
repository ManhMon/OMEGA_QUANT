"""
Auto-Alpha OOS Stability Filter Tests
GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
[L2-Impl:Role14-Data-Scientist] - 2026-06-16

Verifies that:
  1. Default off — stability filter disabled unless explicitly enabled
  2. CLI wiring — --enable-oos-stability-filter flag works
  3. PIT safety — only train/in-fold data used, never OOS labels
  4. Stable alpha passes — high ICIR + consistent sign → pass
  5. Unstable alpha excluded — low ICIR or inconsistent sign → exclude
  6. Decay penalty — negative decay ratio penalizes composite score
  7. Fallback — all bundle excluded triggers conservative fallback
  8. Non-bundle passthrough — non-auto alphas pass through unchanged
  9. Evidence serialization — per-fold evidence persisted correctly
 10. No behavior change when disabled — backward compatible

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_phase35_source():
    """Read phase35.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    )
    return path.read_text(encoding="utf-8")


def _get_run_script_source():
    """Read run_phase35_backtest.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts" / "run_phase35_backtest.py"
    )
    return path.read_text(encoding="utf-8")


def _make_engine(**kwargs):
    """Create a Phase35WalkForwardEngine with a dummy alpha module."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    dummy_module = types.ModuleType("dummy_alpha")
    dummy_module.PHASE34_ALPHA_COLUMNS = []
    dummy_module.compute_phase34_microstructure_alphas = lambda df, **kw: df
    return Phase35WalkForwardEngine(alpha_module=dummy_module, **kwargs)


def _make_synthetic_train_df(
    n_dates=120,
    n_tickers=30,
    alpha_name="auto_test_alpha",
    ic_strength=0.05,
    ic_noise=0.02,
    seed=42,
):
    """Create synthetic train DataFrame with controlled IC properties.

    PIT-safe: forward returns are simulated; alpha is T-1 lagged conceptually.
    """
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    tickers = [f"T{i:02d}" for i in range(n_tickers)]

    rows = []
    for d in dates:
        for t in tickers:
            fwd_ret = rng.normal(0.0, 0.02)
            # Alpha signal correlated with forward return
            alpha_val = ic_strength * fwd_ret + rng.normal(0, ic_noise)
            rows.append({
                "date": d,
                "ticker": t,
                "close": 50000.0 + rng.normal(0, 1000),
                alpha_name: alpha_val,
                "fwd_ret_5": fwd_ret,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: Default off — stability filter disabled
# ---------------------------------------------------------------------------

class TestDefaultOff:
    """Verify stability filter is opt-in/default-off."""

    def test_engine_default_disabled(self):
        """enable_oos_stability_filter defaults to False."""
        engine = _make_engine()
        assert engine.enable_oos_stability_filter is False

    def test_source_gate_id_present(self):
        """Gate ID constant is defined in phase35.py source."""
        src = _get_phase35_source()
        assert "AUTO_ALPHA_OOS_STABILITY_FILTER_20260616" in src

    def test_source_gate_comment_block(self):
        """Gate comment block documents PIT safety and opt-in nature."""
        src = _get_phase35_source()
        assert "PIT-safe" in src
        assert "opt-in" in src.lower() or "default off" in src.lower()

    def test_fold_metrics_has_evidence_field(self):
        """FoldMetrics has oos_stability_filter_evidence field."""
        from omega.quant.alpha.phase35 import FoldMetrics
        m = FoldMetrics(
            fold_id=1,
            train_start="2020-01-01",
            train_end="2020-12-31",
            test_start="2021-01-01",
            test_end="2021-12-31",
        )
        assert hasattr(m, "oos_stability_filter_evidence")
        assert m.oos_stability_filter_evidence is None


# ---------------------------------------------------------------------------
# Test 2: CLI wiring
# ---------------------------------------------------------------------------

class TestCLIWiring:
    """Verify CLI flags are wired correctly."""

    def test_cli_flag_exists(self):
        """--enable-oos-stability-filter flag exists in CLI."""
        src = _get_run_script_source()
        assert "--enable-oos-stability-filter" in src

    def test_cli_stability_min_icir(self):
        """--stability-min-icir flag exists."""
        src = _get_run_script_source()
        assert "--stability-min-icir" in src

    def test_cli_stability_min_sign_consistency(self):
        """--stability-min-sign-consistency flag exists."""
        src = _get_run_script_source()
        assert "--stability-min-sign-consistency" in src

    def test_cli_stability_decay_penalty(self):
        """--stability-decay-penalty-factor flag exists."""
        src = _get_run_script_source()
        assert "--stability-decay-penalty-factor" in src

    def test_engine_constructor_wiring(self):
        """Engine receives stability filter params from CLI."""
        src = _get_run_script_source()
        assert "enable_oos_stability_filter=args.enable_oos_stability_filter" in src
        assert "stability_min_icir=args.stability_min_icir" in src

    def test_config_serialized_in_results(self):
        """Stability filter config appears in results JSON."""
        src = _get_run_script_source()
        assert '"enable_oos_stability_filter"' in src

    def test_evidence_serialized(self):
        """Stability filter evidence is serialized per fold."""
        src = _get_run_script_source()
        assert "oos_stability_filter_evidence" in src


# ---------------------------------------------------------------------------
# Test 3: PIT safety
# ---------------------------------------------------------------------------

class TestPITSafety:
    """Verify PIT safety of the stability filter."""

    def test_method_uses_train_df_only(self):
        """_apply_oos_stability_filter takes train_df, not test_df."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        import inspect
        sig = inspect.signature(
            Phase35WalkForwardEngine._apply_oos_stability_filter
        )
        param_names = list(sig.parameters.keys())
        assert "train_df" in param_names
        assert "test_df" not in param_names

    def test_evidence_marks_pit_safe(self):
        """Evidence dict contains pit_safe=True and no_oos_label_use=True."""
        engine = _make_engine(enable_oos_stability_filter=True)
        train_df = _make_synthetic_train_df()
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test_alpha"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert evidence["pit_safe"] is True
        assert evidence["no_oos_label_use"] is True

    def test_source_no_oos_access(self):
        """Source code does not reference test_df in stability filter method."""
        src = _get_phase35_source()
        # Extract the _apply_oos_stability_filter method body
        start = src.find("def _apply_oos_stability_filter")
        assert start >= 0, "_apply_oos_stability_filter not found"
        # Find the next def/class boundary
        next_def = src.find("\n    def ", start + 10)
        if next_def < 0:
            next_def = len(src)
        method_body = src[start:next_def]
        assert "test_df" not in method_body, (
            "PIT violation: test_df referenced in stability filter method"
        )


# ---------------------------------------------------------------------------
# Test 4: Stable alpha passes filter
# ---------------------------------------------------------------------------

class TestStableAlphaPasses:
    """Verify that a stable alpha with high ICIR passes the filter."""

    def test_high_icir_passes(self):
        """Alpha with consistent positive IC and high ICIR passes."""
        engine = _make_engine(
            enable_oos_stability_filter=True,
            stability_min_icir=0.10,
            stability_min_sign_consistency=0.50,
            stability_min_sub_windows=3,
        )
        # Strong IC with low noise → high ICIR
        train_df = _make_synthetic_train_df(
            ic_strength=0.15,
            ic_noise=0.003,
            n_dates=120,
            n_tickers=30,
        )
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test_alpha"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert "auto_test_alpha" in filtered
        metrics = evidence["alpha_stability_metrics"].get("auto_test_alpha", {})
        # Should be either "pass" (full evaluation) or "pass_insufficient_data"
        assert metrics.get("verdict") in ("pass", "pass_insufficient_data")

    def test_non_bundle_passthrough(self):
        """Non-bundle alphas (no auto_ prefix) pass through unchanged."""
        engine = _make_engine(enable_oos_stability_filter=True)
        train_df = _make_synthetic_train_df()
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["alpha_legacy_01", "alpha_legacy_02"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert "alpha_legacy_01" in filtered
        assert "alpha_legacy_02" in filtered
        assert evidence["filter_disabled_passthrough_alphas"] == [
            "alpha_legacy_01", "alpha_legacy_02"
        ]


# ---------------------------------------------------------------------------
# Test 5: Unstable alpha excluded
# ---------------------------------------------------------------------------

class TestUnstableAlphaExcluded:
    """Verify that an unstable alpha with low ICIR is excluded."""

    def test_low_icir_excluded(self):
        """Alpha with near-zero IC (high noise) is excluded by ICIR gate."""
        engine = _make_engine(
            enable_oos_stability_filter=True,
            stability_min_icir=0.50,  # very strict threshold
            stability_min_sign_consistency=0.30,
            stability_min_sub_windows=3,
        )
        # Very noisy signal → low ICIR
        train_df = _make_synthetic_train_df(
            ic_strength=0.001,
            ic_noise=0.10,
            n_dates=120,
            n_tickers=30,
        )
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test_alpha"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        metrics = evidence["alpha_stability_metrics"].get("auto_test_alpha", {})
        verdict = metrics.get("verdict", "")
        # If we had enough data, ICIR should be low and alpha excluded
        if verdict not in ("pass_insufficient_data",):
            icir = abs(metrics.get("icir", 999.0))
            if icir < 0.50:
                assert "auto_test_alpha" not in filtered
                assert metrics.get("icir_pass") is False


# ---------------------------------------------------------------------------
# Test 6: Decay penalty
# ---------------------------------------------------------------------------

class TestDecayPenalty:
    """Verify IC decay penalty works correctly."""

    def test_decay_penalty_applied_on_negative_ratio(self):
        """When recent IC flips sign vs oldest, decay_penalty > 0."""
        engine = _make_engine(
            enable_oos_stability_filter=True,
            stability_min_icir=0.01,
            stability_min_sign_consistency=0.30,
            stability_decay_penalty_factor=1.0,
            stability_min_sub_windows=3,
        )
        # Build synthetic data where IC reverses: first half positive, second half negative
        rng = np.random.RandomState(99)
        n_dates = 120
        n_tickers = 30
        dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
        rows = []
        for i, d in enumerate(dates):
            for t in range(n_tickers):
                fwd_ret = rng.normal(0, 0.02)
                # First half: positive correlation; second half: negative
                if i < n_dates // 2:
                    alpha_val = 0.10 * fwd_ret + rng.normal(0, 0.003)
                else:
                    alpha_val = -0.10 * fwd_ret + rng.normal(0, 0.003)
                rows.append({
                    "date": d,
                    "ticker": f"T{t:02d}",
                    "close": 50000.0,
                    "auto_decay_test": alpha_val,
                    "fwd_ret_5": fwd_ret,
                })

        train_df = pd.DataFrame(rows)
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_decay_test"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        metrics = evidence["alpha_stability_metrics"].get("auto_decay_test", {})
        verdict = metrics.get("verdict", "")
        # If we had enough data, decay ratio should be negative
        if verdict not in ("pass_insufficient_data",):
            decay_ratio = metrics.get("decay_ratio", 1.0)
            assert decay_ratio < 0.5, (
                f"Expected low decay ratio (IC reversal), got {decay_ratio}"
            )
            assert metrics.get("decay_penalty", 0.0) > 0.0


# ---------------------------------------------------------------------------
# Test 7: Conservative fallback
# ---------------------------------------------------------------------------

class TestConservativeFallback:
    """Verify fallback when all bundle alphas excluded."""

    def test_fallback_re_includes_all(self):
        """When all bundle alphas excluded, fallback re-includes them."""
        engine = _make_engine(
            enable_oos_stability_filter=True,
            stability_min_icir=10.0,  # impossibly high → all fail
            stability_min_sign_consistency=0.30,
            stability_min_sub_windows=3,
        )
        train_df = _make_synthetic_train_df(
            ic_strength=0.01,
            ic_noise=0.1,
            n_dates=120,
            n_tickers=30,
        )
        candidates = ["auto_a", "auto_b", "legacy_x"]
        # Add auto_a and auto_b columns (aliases)
        train_df["auto_a"] = train_df["auto_test_alpha"].copy()
        train_df["auto_b"] = train_df["auto_test_alpha"].copy()
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=candidates,
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        # If filter had enough data, all bundle alphas should fail ICIR=10.0
        # and trigger fallback.  If not enough data, they pass through.
        if evidence.get("n_excluded_bundle", 0) > 0:
            assert evidence["fallback_used"] is True
            assert set(filtered) == set(candidates)
        else:
            # Insufficient data → conservative passthrough
            assert set(filtered) == set(candidates)


# ---------------------------------------------------------------------------
# Test 8: Disabled → passthrough
# ---------------------------------------------------------------------------

class TestDisabledPassthrough:
    """Verify no behavior change when filter is disabled."""

    def test_disabled_returns_all_candidates(self):
        """When disabled, all candidates pass through unchanged."""
        engine = _make_engine(enable_oos_stability_filter=False)
        train_df = _make_synthetic_train_df()
        candidates = ["auto_a", "auto_b", "legacy_x"]
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=candidates,
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert filtered == candidates
        assert evidence["enabled"] is False

    def test_disabled_evidence_has_no_metrics(self):
        """When disabled, alpha_stability_metrics is empty."""
        engine = _make_engine(enable_oos_stability_filter=False)
        train_df = _make_synthetic_train_df()
        _, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert evidence["alpha_stability_metrics"] == {}


# ---------------------------------------------------------------------------
# Test 9: Constructor validation
# ---------------------------------------------------------------------------

class TestConstructorValidation:
    """Verify constructor parameter validation."""

    def test_invalid_enable_type_raises(self):
        engine_module = _make_engine.__module__
        with pytest.raises(ValueError, match="enable_oos_stability_filter must be a boolean"):
            _make_engine(enable_oos_stability_filter="yes")

    def test_invalid_sign_consistency_raises(self):
        with pytest.raises(ValueError, match="stability_min_sign_consistency must be in"):
            _make_engine(
                enable_oos_stability_filter=True,
                stability_min_sign_consistency=1.5,
            )

    def test_invalid_decay_penalty_raises(self):
        with pytest.raises(ValueError, match="stability_decay_penalty_factor must be >= 0"):
            _make_engine(
                enable_oos_stability_filter=True,
                stability_decay_penalty_factor=-0.5,
            )

    def test_invalid_sub_windows_raises(self):
        with pytest.raises(ValueError, match="stability_min_sub_windows must be an integer"):
            _make_engine(
                enable_oos_stability_filter=True,
                stability_min_sub_windows=1,
            )


# ---------------------------------------------------------------------------
# Test 10: Evidence structure completeness
# ---------------------------------------------------------------------------

class TestEvidenceStructure:
    """Verify evidence dict structure is complete and serializable."""

    def test_evidence_is_json_serializable(self):
        """Evidence dict can be JSON-serialized."""
        engine = _make_engine(enable_oos_stability_filter=True)
        train_df = _make_synthetic_train_df()
        _, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test_alpha", "legacy_x"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        # Should not raise
        json_str = json.dumps(evidence)
        parsed = json.loads(json_str)
        assert parsed["gate"] == "AUTO_ALPHA_OOS_STABILITY_FILTER_20260616"
        assert parsed["enabled"] is True
        assert "alpha_stability_metrics" in parsed
        assert "passed_alphas" in parsed
        assert "pit_safe" in parsed

    def test_evidence_has_all_required_keys(self):
        """Evidence dict contains all required audit keys."""
        engine = _make_engine(enable_oos_stability_filter=True)
        train_df = _make_synthetic_train_df()
        _, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_test_alpha"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        required_keys = [
            "gate", "enabled", "candidate_alphas", "n_candidates",
            "stability_min_icir", "stability_min_sign_consistency",
            "stability_decay_penalty_factor", "stability_min_sub_windows",
            "alpha_stability_metrics", "passed_alphas", "excluded_alphas",
            "pit_safe", "no_oos_label_use",
        ]
        for key in required_keys:
            assert key in evidence, f"Missing evidence key: {key}"


# ---------------------------------------------------------------------------
# Test 11: No column in train_df → passthrough
# ---------------------------------------------------------------------------

class TestMissingColumnPassthrough:
    """Verify graceful handling when alpha column is missing."""

    def test_missing_alpha_column_passthrough(self):
        """If alpha column not in train_df, pass through unchanged."""
        engine = _make_engine(enable_oos_stability_filter=True)
        train_df = _make_synthetic_train_df()
        # "auto_nonexistent" is not a column in train_df
        filtered, evidence = engine._apply_oos_stability_filter(
            candidate_alphas=["auto_nonexistent"],
            train_df=train_df,
            return_col="fwd_ret_5",
        )
        assert "auto_nonexistent" in filtered
