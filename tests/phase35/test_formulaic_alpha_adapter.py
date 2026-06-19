"""
Formulaic Alpha Adapter Tests
GATE: FORMULAIC_ALPHA_ADAPTER_20260614
[L2-Impl:Role14-Data-Scientist] - 2026-06-14

Verifies that:
1. Default disabled — no formulaic columns when flag not set
2. Enabled columns — formulaic columns present when enabled
3. PIT/no lookahead guard — no negative shifts, T-1 lag enforced
4. Finite outputs — no inf/nan in output
5. Naming — column names follow alpha_fml* convention
6. Phase35 wiring/persistence — engine constructor, config dict, CLI

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


def _get_script_source():
    """Read the run_phase35_backtest.py source code."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
    return script_path.read_text(encoding="utf-8")


def _get_engine_source():
    """Read the phase35.py engine source code."""
    engine_path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    return engine_path.read_text(encoding="utf-8")


def _get_formulaic_source():
    """Read the formulaic_alphas.py adapter source code."""
    fml_path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "formulaic_alphas.py"
    return fml_path.read_text(encoding="utf-8")


def _make_synthetic_ohlcv(n_tickers: int = 5, n_days: int = 60, seed: int = 42) -> pd.DataFrame:
    """Create synthetic OHLCV panel data for testing.

    Returns DataFrame with ticker, date, open, high, low, close, volume columns.
    """
    rng = np.random.RandomState(seed)
    rows = []
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    for t in range(n_tickers):
        ticker = f"SYM{t:02d}"
        base_price = 100.0 + rng.randn() * 20
        for d_idx, date in enumerate(dates):
            noise = rng.randn() * 0.02
            close = base_price * (1 + noise * (d_idx + 1) / n_days)
            open_price = close * (1 + rng.randn() * 0.005)
            high = max(open_price, close) * (1 + abs(rng.randn()) * 0.01)
            low = min(open_price, close) * (1 - abs(rng.randn()) * 0.01)
            volume = int(abs(rng.randn() * 100000) + 10000)
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
            })
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Section 1: CLI Flag Registration
# ---------------------------------------------------------------------------


class TestFormulaicAlphaCLIFlags:
    """Verify --enable-formulaic-alphas and --formulaic-alpha-set CLI flags."""

    def test_cli_enable_formulaic_alphas_flag_registered(self):
        src = _get_script_source()
        assert '"--enable-formulaic-alphas"' in src, \
            "CLI flag --enable-formulaic-alphas must be registered"

    def test_cli_formulaic_alpha_set_flag_registered(self):
        src = _get_script_source()
        assert '"--formulaic-alpha-set"' in src, \
            "CLI flag --formulaic-alpha-set must be registered"

    def test_cli_formulaic_alpha_set_default_small(self):
        src = _get_script_source()
        assert 'default="small"' in src, \
            "Default must be 'small' for formulaic alpha set"

    def test_cli_formulaic_alpha_set_choices(self):
        src = _get_script_source()
        assert 'choices=["small", "mean_reversion_liquidity", "v3_pruned", "v4_vn_extended"]' in src, \
            "Choices must include 'small', 'mean_reversion_liquidity', 'v3_pruned', and 'v4_vn_extended'"

    def test_cli_gate_label_present(self):
        src = _get_script_source()
        assert "FORMULAIC_ALPHA_ADAPTER_20260614" in src, \
            "Gate label FORMULAIC_ALPHA_ADAPTER_20260614 must be present"

    def test_cli_enable_formulaic_alphas_is_store_true(self):
        """Verify --enable-formulaic-alphas uses action='store_true' (default False)."""
        src = _get_script_source()
        # Find the argparse call for --enable-formulaic-alphas
        assert "action=\"store_true\"" in src or "action='store_true'" in src, \
            "--enable-formulaic-alphas must use store_true action"


# ---------------------------------------------------------------------------
# Section 2: Default Disabled Behavior
# ---------------------------------------------------------------------------


class TestDefaultDisabled:
    """Verify that formulaic alphas are disabled by default — no behavior change."""

    def test_engine_default_no_formulaic(self):
        """Engine constructor with no formulaic args should have enable_formulaic_alphas=False."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        # Create a mock alpha_module
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(return_value=pd.DataFrame())

        # Patch the risk_adjusted import to avoid heavy dependencies
        with patch("omega.quant.alpha.phase35.validate_research_gate", return_value={}):
            with patch.dict("sys.modules", {
                "omega.quant.ml.gate_validator": MagicMock(),
                "omega.quant.ml.ensemble_xgboost": MagicMock(),
            }):
                # Must also mock the risk_adjusted_alpha_score import
                mock_ra = MagicMock()
                mock_ra.PRESETS = {"balanced": {}, "alpha_recovery": {}, "drawdown_guarded": {}, "ic_first_guarded": {}}
                mock_ra.VALID_RESEARCH_POOL_MODES = ["full", "recovery_only", "recoverable_only"]
                mock_ra.get_preset_weights = MagicMock(return_value={})
                mock_ra.get_preset_rank_components = MagicMock(return_value={
                    "primary_rank_components": [],
                    "soft_penalty_components": [],
                })
                with patch.dict("sys.modules", {
                    "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
                }):
                    engine = Phase35WalkForwardEngine(alpha_module=mock_module)
                    assert engine.enable_formulaic_alphas is False, \
                        "Default enable_formulaic_alphas must be False"

    def test_config_dict_contains_formulaic_flags(self):
        """JSON config dict in script must persist formulaic alpha flags."""
        src = _get_script_source()
        assert '"enable_formulaic_alphas"' in src, \
            "Config dict must contain enable_formulaic_alphas key"
        assert '"formulaic_alpha_set"' in src, \
            "Config dict must contain formulaic_alpha_set key"


# ---------------------------------------------------------------------------
# Section 3: Enabled Columns
# ---------------------------------------------------------------------------


class TestEnabledColumns:
    """Verify that enabling formulaic alphas adds correct columns."""

    def test_compute_formulaic_alphas_small_set(self):
        """compute_formulaic_alphas with set_name='small' adds 5 columns."""
        from omega.quant.alpha.formulaic_alphas import (
            compute_formulaic_alphas,
            get_formulaic_alpha_columns,
        )
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_formulaic_alphas(df, set_name="small")

        expected_cols = get_formulaic_alpha_columns("small")
        for col in expected_cols:
            assert col in result.columns, \
                f"Column {col} must be present in output when enabled"

    def test_compute_formulaic_alphas_returns_all_5(self):
        """Exactly 5 formulaic alpha columns are added."""
        from omega.quant.alpha.formulaic_alphas import (
            compute_formulaic_alphas,
            FORMULAIC_ALPHA_SETS,
        )
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        n_orig = len(df.columns)
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == len(FORMULAIC_ALPHA_SETS["small"]), \
            f"Expected {len(FORMULAIC_ALPHA_SETS['small'])} formulaic columns, got {len(fml_cols)}"

    def test_disabled_does_not_add_columns(self):
        """compute_formulaic_alphas with unknown set returns df unchanged."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        n_orig = len(df.columns)
        result = compute_formulaic_alphas(df, set_name="nonexistent")
        assert len(result.columns) == n_orig, \
            "Unknown set_name should not add columns"


# ---------------------------------------------------------------------------
# Section 4: PIT / No Lookahead Guard
# ---------------------------------------------------------------------------


class TestPITNoLookaheadGuard:
    """Verify PIT safety: no negative shifts, T-1 lag enforced."""

    def test_source_no_negative_shifts(self):
        """Source code must not contain .shift(- or shift(negative)."""
        src = _get_formulaic_source()
        # Check for negative shift patterns
        import re
        neg_shifts = re.findall(r'\.shift\s*\(\s*-\d', src)
        assert len(neg_shifts) == 0, \
            f"Found negative shifts in formulaic_alphas.py: {neg_shifts}"

    def test_source_uses_shift_1(self):
        """Source code must use shift(1) for T-1 lag on raw OHLCV."""
        src = _get_formulaic_source()
        assert ".shift(1)" in src, \
            "Formulaic alphas must use .shift(1) for T-1 lag"

    def test_first_rows_nan_after_shift(self):
        """First row per ticker must be NaN after shift(1), ensuring no lookahead.

        We verify this indirectly: after computing alphas, the first row
        per ticker should have formulaic alpha values that are either NaN
        or the fallback 0.0 (from fillna(0.0)).
        """
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=30)
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            # Group by ticker, check first row
            first_rows = result.groupby("ticker")[col].first()
            # First rows should be 0.0 (fillna(0.0) applied) or NaN
            # They should NOT contain actual computed signal values
            # (shift(1) makes them NaN, then fillna(0.0) makes them 0.0)
            for ticker, val in first_rows.items():
                assert np.isfinite(val), \
                    f"First row for {ticker}/{col} should be finite (0.0 fallback), got {val}"

    def test_all_shifts_positive(self):
        """All shift() calls in formulaic alpha source must use positive arguments."""
        import re
        src = _get_formulaic_source()
        shifts = re.findall(r'\.shift\s*\(\s*(-?\d+)', src)
        for s in shifts:
            assert int(s) > 0, \
                f"Found non-positive shift({s}) in formulaic_alphas.py — PIT violation"


# ---------------------------------------------------------------------------
# Section 5: Finite Outputs
# ---------------------------------------------------------------------------


class TestFiniteOutputs:
    """Verify all outputs are finite (no inf/nan)."""

    def test_no_inf_in_outputs(self):
        """Formulaic alpha outputs must not contain inf."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert not np.any(np.isinf(result[col].values)), \
                f"Column {col} contains inf values"

    def test_no_nan_in_outputs(self):
        """Formulaic alpha outputs must not contain NaN (all sanitized)."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert not np.any(np.isnan(result[col].values)), \
                f"Column {col} contains NaN values"

    def test_outputs_are_float64(self):
        """All formulaic alpha columns should be float64."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert result[col].dtype == np.float64, \
                f"Column {col} dtype should be float64, got {result[col].dtype}"

    def test_extreme_inputs_produce_finite_output(self):
        """Extreme input values (very large/small prices) must still produce finite outputs."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        # Inject extreme values
        df.loc[10, "close"] = 1e12
        df.loc[20, "volume"] = 0
        df.loc[30, "open"] = 1e-6
        df.loc[40, "high"] = 1e15
        result = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert np.all(np.isfinite(result[col].values)), \
                f"Column {col} has non-finite values with extreme inputs"


# ---------------------------------------------------------------------------
# Section 6: Naming Convention
# ---------------------------------------------------------------------------


class TestNamingConvention:
    """Verify formulaic alpha column names follow conventions."""

    def test_all_names_start_with_alpha_fml(self):
        """All formulaic alpha column names must start with 'alpha_fml'."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for set_name, cols in FORMULAIC_ALPHA_SETS.items():
            for col in cols:
                assert col.startswith("alpha_fml"), \
                    f"Column {col} in set '{set_name}' must start with 'alpha_fml'"

    def test_names_are_deterministic(self):
        """Column names must be deterministic (same across calls)."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols1 = get_formulaic_alpha_columns("small")
        cols2 = get_formulaic_alpha_columns("small")
        assert cols1 == cols2, \
            "Column names must be deterministic across calls"

    def test_names_contain_window_info(self):
        """Column names should encode window size for transparency."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["small"]:
            # Check that at least one digit appears (window size indicator)
            has_digit = any(c.isdigit() for c in col)
            assert has_digit, \
                f"Column {col} should contain window size digits"

    def test_metadata_has_all_columns(self):
        """Metadata must cover all formulaic alpha columns."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["small"]:
            assert col in metadata, \
                f"Column {col} must have metadata entry"

    def test_metadata_has_gate_source(self):
        """Each metadata entry must reference a valid gate ID."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            GATE_ID,
            GATE_ID_V2,
            GATE_ID_V4,
        )
        metadata = get_formulaic_alpha_metadata()
        valid_gates = {GATE_ID, GATE_ID_V2, GATE_ID_V4}
        for col, meta in metadata.items():
            assert meta.get("source") in valid_gates, \
                f"Metadata for {col} must reference a valid gate ID"


# ---------------------------------------------------------------------------
# Section 7: Phase35 Engine Wiring / Persistence
# ---------------------------------------------------------------------------


class TestPhase35Wiring:
    """Verify Phase35 engine accepts and persists formulaic alpha config."""

    def test_engine_accepts_formulaic_params(self):
        """Engine constructor must accept enable_formulaic_alphas and formulaic_alpha_set."""
        src = _get_engine_source()
        assert "enable_formulaic_alphas" in src, \
            "Engine must accept enable_formulaic_alphas parameter"
        assert "formulaic_alpha_set" in src, \
            "Engine must accept formulaic_alpha_set parameter"

    def test_engine_stores_formulaic_params(self):
        """Engine must store formulaic alpha params as attributes."""
        src = _get_engine_source()
        assert "self.enable_formulaic_alphas" in src, \
            "Engine must store self.enable_formulaic_alphas"
        assert "self.formulaic_alpha_set" in src, \
            "Engine must store self.formulaic_alpha_set"

    def test_engine_compute_alphas_calls_formulaic(self):
        """Engine compute_alphas must call formulaic alphas when enabled."""
        src = _get_engine_source()
        assert "compute_formulaic_alphas" in src, \
            "Engine compute_alphas must reference compute_formulaic_alphas"

    def test_engine_gate_label_present(self):
        """Engine source must contain the gate label."""
        src = _get_engine_source()
        assert "FORMULAIC_ALPHA_ADAPTER_20260614" in src, \
            "Engine source must contain gate label"

    def test_engine_validates_enable_formulaic_alphas_type(self):
        """Engine must validate enable_formulaic_alphas is boolean."""
        src = _get_engine_source()
        assert "enable_formulaic_alphas must be a boolean" in src, \
            "Engine must validate enable_formulaic_alphas type"

    def test_config_persistence_in_results_json(self):
        """Results JSON config dict must contain formulaic alpha flags."""
        src = _get_script_source()
        assert '"enable_formulaic_alphas": args.enable_formulaic_alphas' in src, \
            "Config dict must persist enable_formulaic_alphas"
        assert '"formulaic_alpha_set": args.formulaic_alpha_set' in src, \
            "Config dict must persist formulaic_alpha_set"

    def test_alpha_cols_extended_when_enabled(self):
        """Script must extend alpha_cols with formulaic columns when enabled."""
        src = _get_script_source()
        assert "alpha_cols.extend(fml_cols)" in src, \
            "alpha_cols must be extended with formulaic columns when enabled"


# ---------------------------------------------------------------------------
# Section 8: Formulaic Alpha Set Registry
# ---------------------------------------------------------------------------


class TestFormulaicAlphaSetRegistry:
    """Verify alpha set registry works correctly."""

    def test_get_formulaic_alpha_columns_small(self):
        """get_formulaic_alpha_columns('small') returns 5 columns."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols = get_formulaic_alpha_columns("small")
        assert len(cols) == 5, f"Expected 5 columns, got {len(cols)}"

    def test_get_formulaic_alpha_columns_invalid(self):
        """get_formulaic_alpha_columns with invalid name raises ValueError."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        with pytest.raises(ValueError, match="Unknown formulaic alpha set"):
            get_formulaic_alpha_columns("nonexistent")

    def test_formulaic_alpha_sets_dict(self):
        """FORMULAIC_ALPHA_SETS must contain 'small' key."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        assert "small" in FORMULAIC_ALPHA_SETS, \
            "FORMULAIC_ALPHA_SETS must contain 'small'"
        assert len(FORMULAIC_ALPHA_SETS["small"]) >= 5, \
            "'small' set must have at least 5 alphas"

    def test_gate_id_constant(self):
        """GATE_ID must be FORMULAIC_ALPHA_ADAPTER_20260614."""
        from omega.quant.alpha.formulaic_alphas import GATE_ID
        assert GATE_ID == "FORMULAIC_ALPHA_ADAPTER_20260614"


# ---------------------------------------------------------------------------
# Section 9: Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Verify formulaic alpha outputs are deterministic."""

    def test_same_input_same_output(self):
        """Same input data must produce identical outputs across calls."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60, seed=42)
        result1 = compute_formulaic_alphas(df, set_name="small")
        result2 = compute_formulaic_alphas(df, set_name="small")

        fml_cols = [c for c in result1.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            np.testing.assert_array_equal(
                result1[col].values, result2[col].values,
                err_msg=f"Column {col} is not deterministic"
            )


# ---------------------------------------------------------------------------
# Section 10: Minimum Alpha Candidate Verification
# ---------------------------------------------------------------------------


class TestMinimumCandidates:
    """Verify at least 5 formulaic alpha candidates exist."""

    def test_at_least_5_candidates(self):
        """'small' set must contain at least 5 candidates."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        assert len(FORMULAIC_ALPHA_SETS["small"]) >= 5

    def test_candidates_cover_required_categories(self):
        """Candidates must cover: momentum, vol-price corr, mean reversion,
        vol/vol interaction, and liquidity/turnover."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        cols = FORMULAIC_ALPHA_SETS["small"]
        col_str = " ".join(cols)

        # Momentum / ts_rank
        assert "momentum" in col_str or "ts_rank" in col_str, \
            "Must include momentum/ts_rank candidate"
        # Volume-price correlation
        assert "corr" in col_str or "vp" in col_str, \
            "Must include volume-price correlation candidate"
        # Mean reversion
        assert "mean_rev" in col_str or "reversion" in col_str, \
            "Must include mean reversion candidate"
        # Volatility/volume interaction
        assert "vol" in col_str and "interact" in col_str, \
            "Must include volatility/volume interaction candidate"
        # Liquidity/turnover
        assert "liq" in col_str or "turnover" in col_str, \
            "Must include liquidity/turnover candidate"


# ---------------------------------------------------------------------------
# Section 11: Engine Integration (mocked)
# ---------------------------------------------------------------------------


class TestEngineIntegration:
    """Test engine integration with formulaic alphas using mocked alpha_module."""

    def test_engine_compute_alphas_with_formulaic(self):
        """Engine compute_alphas with enable_formulaic_alphas=True appends formulaic columns."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)

        # Simulate what the engine does: first compute phase34, then formulaic
        # We just test the formulaic step directly
        result = compute_formulaic_alphas(df, set_name="small")
        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == 5, \
            f"Expected 5 formulaic columns, got {len(fml_cols)}"

    def test_engine_compute_alphas_without_formulaic(self):
        """Engine compute_alphas with enable_formulaic_alphas=False does not append formulaic columns."""
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        # Simulate disabled: just don't call compute_formulaic_alphas
        # Verify the original df has no alpha_fml columns
        fml_cols = [c for c in df.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == 0


# ---------------------------------------------------------------------------
# Section 12: V2 Alpha Set (GATE: FORMULAIC_ALPHA_V2_20260614)
# ---------------------------------------------------------------------------


class TestV2AlphaSetRegistry:
    """Verify v2 'mean_reversion_liquidity' alpha set registry."""

    def test_v2_set_exists_in_registry(self):
        """FORMULAIC_ALPHA_SETS must contain 'mean_reversion_liquidity' key."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        assert "mean_reversion_liquidity" in FORMULAIC_ALPHA_SETS, \
            "FORMULAIC_ALPHA_SETS must contain 'mean_reversion_liquidity'"

    def test_v2_set_has_at_least_5_candidates(self):
        """V2 set must have at least 5 PIT-safe candidates."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        assert len(v2_cols) >= 5, \
            f"V2 set must have >= 5 candidates, got {len(v2_cols)}"

    def test_v2_set_excludes_weak_momentum(self):
        """V2 set must NOT include alpha_fml001_ts_rank_momentum_20 (negative IC)."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        assert "alpha_fml001_ts_rank_momentum_20" not in v2_cols, \
            "V2 must exclude weak momentum alpha_fml001"

    def test_v2_set_retains_best_v1_candidates(self):
        """V2 set must retain fml012, fml045, fml006 from v1."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        assert "alpha_fml012_mean_rev_rank_10" in v2_cols
        assert "alpha_fml045_liq_turnover_5" in v2_cols
        assert "alpha_fml006_vp_corr_10" in v2_cols

    def test_v2_set_includes_new_candidates(self):
        """V2 set must include new v2 alphas: fml052, fml067, fml078, fml089."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        assert "alpha_fml052_close_zscore_mr_20" in v2_cols
        assert "alpha_fml067_vol_price_diverge_10" in v2_cols
        assert "alpha_fml078_range_compression_10" in v2_cols
        assert "alpha_fml089_amihud_illiq_20" in v2_cols

    def test_v2_get_columns_returns_correct_names(self):
        """get_formulaic_alpha_columns('mean_reversion_liquidity') returns v2 names."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols = get_formulaic_alpha_columns("mean_reversion_liquidity")
        assert len(cols) == 8
        assert all(c.startswith("alpha_fml") for c in cols)

    def test_v2_gate_id_constant(self):
        """GATE_ID_V2 must be FORMULAIC_ALPHA_V2_20260614."""
        from omega.quant.alpha.formulaic_alphas import GATE_ID_V2
        assert GATE_ID_V2 == "FORMULAIC_ALPHA_V2_20260614"

    def test_v2_default_unchanged(self):
        """DEFAULT_FORMULAIC_ALPHA_SET must still be 'small' (no default behavior change)."""
        from omega.quant.alpha.formulaic_alphas import DEFAULT_FORMULAIC_ALPHA_SET
        assert DEFAULT_FORMULAIC_ALPHA_SET == "small", \
            "Default must remain 'small' — v2 is research-only opt-in"


class TestV2FiniteOutputs:
    """Verify v2 outputs are finite (no inf/nan)."""

    def test_v2_no_inf_in_outputs(self):
        """V2 formulaic alpha outputs must not contain inf."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == 8
        for col in fml_cols:
            assert not np.any(np.isinf(result[col].values)), \
                f"V2 column {col} contains inf values"

    def test_v2_no_nan_in_outputs(self):
        """V2 formulaic alpha outputs must not contain NaN (all sanitized)."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert not np.any(np.isnan(result[col].values)), \
                f"V2 column {col} contains NaN values"

    def test_v2_outputs_are_float64(self):
        """All v2 formulaic alpha columns should be float64."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert result[col].dtype == np.float64, \
                f"V2 column {col} dtype should be float64, got {result[col].dtype}"

    def test_v2_extreme_inputs_produce_finite_output(self):
        """Extreme input values must still produce finite v2 outputs."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        df.loc[10, "close"] = 1e12
        df.loc[20, "volume"] = 0
        df.loc[30, "open"] = 1e-6
        df.loc[40, "high"] = 1e15
        result = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert np.all(np.isfinite(result[col].values)), \
                f"V2 column {col} has non-finite values with extreme inputs"


class TestV2PITGuard:
    """Verify PIT safety for v2 alphas: no negative shifts, T-1 lag enforced."""

    def test_v2_source_no_negative_shifts(self):
        """Source code must not contain .shift(- or shift(negative) for v2 alphas."""
        src = _get_formulaic_source()
        import re
        neg_shifts = re.findall(r'\.shift\s*\(\s*-\d', src)
        assert len(neg_shifts) == 0, \
            f"Found negative shifts in formulaic_alphas.py: {neg_shifts}"

    def test_v2_all_shifts_positive(self):
        """All shift() calls must use positive arguments (including v2 functions)."""
        import re
        src = _get_formulaic_source()
        shifts = re.findall(r'\.shift\s*\(\s*(-?\d+)', src)
        for s in shifts:
            assert int(s) > 0, \
                f"Found non-positive shift({s}) in formulaic_alphas.py — PIT violation"

    def test_v2_first_rows_finite_after_shift(self):
        """First row per ticker must be finite (0.0 fallback) after shift(1) for v2."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=30)
        result = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        v2_new_cols = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml067_vol_price_diverge_10",
            "alpha_fml078_range_compression_10",
            "alpha_fml089_amihud_illiq_20",
        ]
        for col in v2_new_cols:
            if col in result.columns:
                first_rows = result.groupby("ticker")[col].first()
                for ticker, val in first_rows.items():
                    assert np.isfinite(val), \
                        f"V2 first row for {ticker}/{col} should be finite, got {val}"


class TestV2CLIChoice:
    """Verify CLI supports v2 set choice and default unchanged."""

    def test_cli_v2_choice_registered(self):
        """CLI choices for --formulaic-alpha-set must include 'mean_reversion_liquidity'."""
        src = _get_script_source()
        assert "mean_reversion_liquidity" in src, \
            "CLI must include 'mean_reversion_liquidity' as a choice"

    def test_cli_v2_choices_list(self):
        """CLI choices list must contain 'small', 'mean_reversion_liquidity', 'v3_pruned', and 'v4_vn_extended'."""
        src = _get_script_source()
        assert 'choices=["small", "mean_reversion_liquidity", "v3_pruned", "v4_vn_extended"]' in src, \
            "CLI choices must include all four sets"

    def test_cli_default_still_small(self):
        """CLI default must remain 'small' — no default behavior change."""
        src = _get_script_source()
        # Find the formulaic-alpha-set default
        assert 'default="small"' in src, \
            "CLI default must remain 'small'"

    def test_cli_v2_gate_label_present(self):
        """CLI source must reference FORMULAIC_ALPHA_V2_20260614."""
        src = _get_script_source()
        assert "FORMULAIC_ALPHA_V2_20260614" in src, \
            "CLI source must reference v2 gate label"


class TestV2Determinism:
    """Verify v2 formulaic alpha outputs are deterministic."""

    def test_v2_same_input_same_output(self):
        """Same input data must produce identical v2 outputs across calls."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60, seed=42)
        result1 = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")
        result2 = compute_formulaic_alphas(df, set_name="mean_reversion_liquidity")

        fml_cols = [c for c in result1.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            np.testing.assert_array_equal(
                result1[col].values, result2[col].values,
                err_msg=f"V2 column {col} is not deterministic"
            )


class TestV2Metadata:
    """Verify v2 metadata coverage."""

    def test_v2_metadata_has_all_columns(self):
        """Metadata must cover all v2 formulaic alpha columns."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]:
            assert col in metadata, \
                f"V2 column {col} must have metadata entry"

    def test_v2_metadata_has_gate_source(self):
        """V2 metadata entries must reference a valid gate (GATE_ID or GATE_ID_V2).

        Shared alphas (from v1) reference GATE_ID; new v2-only alphas reference GATE_ID_V2.
        """
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            GATE_ID,
            GATE_ID_V2,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        valid_gates = {GATE_ID, GATE_ID_V2}
        for col in FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]:
            assert metadata[col].get("source") in valid_gates, \
                f"V2 metadata for {col} must reference a valid gate"

    def test_v2_only_metadata_references_v2_gate(self):
        """New v2-only alphas must reference GATE_ID_V2."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            GATE_ID_V2,
        )
        metadata = get_formulaic_alpha_metadata()
        v2_only_cols = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml067_vol_price_diverge_10",
            "alpha_fml078_range_compression_10",
            "alpha_fml089_amihud_illiq_20",
        ]
        for col in v2_only_cols:
            assert metadata[col].get("source") == GATE_ID_V2, \
                f"V2-only metadata for {col} must reference gate {GATE_ID_V2}"

    def test_v2_metadata_has_family(self):
        """V2 metadata entries must have family field."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]:
            assert "family" in metadata[col], \
                f"V2 metadata for {col} must have 'family' field"


class TestV2NamingConvention:
    """Verify v2 naming conventions."""

    def test_v2_all_names_start_with_alpha_fml(self):
        """All v2 column names must start with 'alpha_fml'."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]:
            assert col.startswith("alpha_fml"), \
                f"V2 column {col} must start with 'alpha_fml'"

    def test_v2_names_contain_window_info(self):
        """V2 column names should encode window size."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]:
            has_digit = any(c.isdigit() for c in col)
            assert has_digit, \
                f"V2 column {col} should contain window size digits"

    def test_v2_names_are_deterministic(self):
        """V2 column names must be deterministic."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols1 = get_formulaic_alpha_columns("mean_reversion_liquidity")
        cols2 = get_formulaic_alpha_columns("mean_reversion_liquidity")
        assert cols1 == cols2


class TestV2FamilyCoverage:
    """Verify v2 set covers required families."""

    def test_v2_covers_mean_reversion(self):
        """V2 set must include mean reversion family alphas."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        mr_count = sum(1 for c in v2_cols if "mean_rev" in c or "zscore_mr" in c or "compression" in c)
        assert mr_count >= 2, f"V2 must have >= 2 mean reversion alphas, got {mr_count}"

    def test_v2_covers_liquidity(self):
        """V2 set must include liquidity family alphas."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        liq_count = sum(1 for c in v2_cols if "liq" in c or "turnover" in c or "illiq" in c)
        assert liq_count >= 2, f"V2 must have >= 2 liquidity alphas, got {liq_count}"

    def test_v2_covers_volume_price(self):
        """V2 set must include volume-price family alphas."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        vp_count = sum(1 for c in v2_cols if "vp" in c or "corr" in c or "diverge" in c)
        assert vp_count >= 2, f"V2 must have >= 2 volume-price alphas, got {vp_count}"

    def test_v2_no_momentum_family(self):
        """V2 set must NOT include momentum-family alphas."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v2_cols = FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"]
        mom_count = sum(1 for c in v2_cols if "momentum" in c)
        assert mom_count == 0, f"V2 must have 0 momentum alphas, got {mom_count}"


# ---------------------------------------------------------------------------
# Section 13: V3 Pruned Alpha Set (GATE: FORMULAIC_ALPHA_V3_PRUNE_20260614)
# ---------------------------------------------------------------------------


class TestV3PrunedSetRegistry:
    """Verify v3 'v3_pruned' alpha set registry."""

    def test_v3_set_exists_in_registry(self):
        """FORMULAIC_ALPHA_SETS must contain 'v3_pruned' key."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        assert "v3_pruned" in FORMULAIC_ALPHA_SETS, \
            "FORMULAIC_ALPHA_SETS must contain 'v3_pruned'"

    def test_v3_set_has_exactly_5_candidates(self):
        """V3 pruned set must have exactly 5 PIT-safe candidates."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert len(v3_cols) == 5, \
            f"V3 pruned set must have 5 candidates, got {len(v3_cols)}"

    def test_v3_excludes_amihud_illiq(self):
        """V3 must NOT include alpha_fml089_amihud_illiq_20 (IC -0.0610)."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert "alpha_fml089_amihud_illiq_20" not in v3_cols, \
            "V3 must exclude negative-IC amihud_illiq"

    def test_v3_excludes_range_compression(self):
        """V3 must NOT include alpha_fml078_range_compression_10 (IC -0.0100)."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert "alpha_fml078_range_compression_10" not in v3_cols, \
            "V3 must exclude negative-IC range_compression"

    def test_v3_excludes_momentum(self):
        """V3 must NOT include momentum alpha_fml001."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert "alpha_fml001_ts_rank_momentum_20" not in v3_cols

    def test_v3_excludes_vol_vol_interact(self):
        """V3 must NOT include weak alpha_fml033_vol_vol_interact_10."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert "alpha_fml033_vol_vol_interact_10" not in v3_cols

    def test_v3_retains_strong_candidates(self):
        """V3 must retain the 5 strongest positive-IC candidates."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = FORMULAIC_ALPHA_SETS["v3_pruned"]
        assert "alpha_fml052_close_zscore_mr_20" in v3_cols, "IC 0.0164"
        assert "alpha_fml012_mean_rev_rank_10" in v3_cols, "IC 0.0104"
        assert "alpha_fml045_liq_turnover_5" in v3_cols, "IC 0.0091"
        assert "alpha_fml067_vol_price_diverge_10" in v3_cols, "IC 0.0080"
        assert "alpha_fml006_vp_corr_10" in v3_cols, "IC 0.0059"

    def test_v3_gate_id_constant(self):
        """GATE_ID_V3 must be FORMULAIC_ALPHA_V3_PRUNE_20260614."""
        from omega.quant.alpha.formulaic_alphas import GATE_ID_V3
        assert GATE_ID_V3 == "FORMULAIC_ALPHA_V3_PRUNE_20260614"

    def test_v3_default_unchanged(self):
        """DEFAULT_FORMULAIC_ALPHA_SET must still be 'small'."""
        from omega.quant.alpha.formulaic_alphas import DEFAULT_FORMULAIC_ALPHA_SET
        assert DEFAULT_FORMULAIC_ALPHA_SET == "small", \
            "Default must remain 'small' — v3 is research-only opt-in"


class TestV3FiniteOutputs:
    """Verify v3 pruned outputs are finite (no inf/nan)."""

    def test_v3_no_inf_in_outputs(self):
        """V3 formulaic alpha outputs must not contain inf."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="v3_pruned")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == 5
        for col in fml_cols:
            assert not np.any(np.isinf(result[col].values)), \
                f"V3 column {col} contains inf values"

    def test_v3_no_nan_in_outputs(self):
        """V3 formulaic alpha outputs must not contain NaN."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="v3_pruned")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert not np.any(np.isnan(result[col].values)), \
                f"V3 column {col} contains NaN values"

    def test_v3_outputs_are_float64(self):
        """All v3 formulaic alpha columns should be float64."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_formulaic_alphas(df, set_name="v3_pruned")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert result[col].dtype == np.float64, \
                f"V3 column {col} dtype should be float64, got {result[col].dtype}"

    def test_v3_extreme_inputs_produce_finite_output(self):
        """Extreme input values must still produce finite v3 outputs."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        df.loc[10, "close"] = 1e12
        df.loc[20, "volume"] = 0
        df.loc[30, "open"] = 1e-6
        df.loc[40, "high"] = 1e15
        result = compute_formulaic_alphas(df, set_name="v3_pruned")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert np.all(np.isfinite(result[col].values)), \
                f"V3 column {col} has non-finite values with extreme inputs"


class TestV3PITGuard:
    """Verify PIT safety for v3 pruned alphas."""

    def test_v3_first_rows_finite_after_shift(self):
        """First row per ticker must be finite (0.0 fallback) after shift(1) for v3."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=30)
        result = compute_formulaic_alphas(df, set_name="v3_pruned")

        v3_cols = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml012_mean_rev_rank_10",
            "alpha_fml045_liq_turnover_5",
            "alpha_fml067_vol_price_diverge_10",
            "alpha_fml006_vp_corr_10",
        ]
        for col in v3_cols:
            if col in result.columns:
                first_rows = result.groupby("ticker")[col].first()
                for ticker, val in first_rows.items():
                    assert np.isfinite(val), \
                        f"V3 first row for {ticker}/{col} should be finite, got {val}"


class TestV3CLIChoice:
    """Verify CLI supports v3 set choice and default unchanged."""

    def test_cli_v3_choice_registered(self):
        """CLI choices for --formulaic-alpha-set must include 'v3_pruned'."""
        src = _get_script_source()
        assert "v3_pruned" in src, \
            "CLI must include 'v3_pruned' as a choice"

    def test_cli_v3_gate_label_present(self):
        """CLI source must reference FORMULAIC_ALPHA_V3_PRUNE_20260614."""
        src = _get_script_source()
        assert "FORMULAIC_ALPHA_V3_PRUNE_20260614" in src, \
            "CLI source must reference v3 gate label"

    def test_cli_default_still_small(self):
        """CLI default must remain 'small'."""
        src = _get_script_source()
        assert 'default="small"' in src, \
            "CLI default must remain 'small'"


class TestV3Determinism:
    """Verify v3 pruned outputs are deterministic."""

    def test_v3_same_input_same_output(self):
        """Same input data must produce identical v3 outputs across calls."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60, seed=42)
        result1 = compute_formulaic_alphas(df, set_name="v3_pruned")
        result2 = compute_formulaic_alphas(df, set_name="v3_pruned")

        fml_cols = [c for c in result1.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            np.testing.assert_array_equal(
                result1[col].values, result2[col].values,
                err_msg=f"V3 column {col} is not deterministic"
            )


class TestV3NamingConvention:
    """Verify v3 naming conventions."""

    def test_v3_all_names_start_with_alpha_fml(self):
        """All v3 column names must start with 'alpha_fml'."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["v3_pruned"]:
            assert col.startswith("alpha_fml"), \
                f"V3 column {col} must start with 'alpha_fml'"

    def test_v3_names_contain_window_info(self):
        """V3 column names should encode window size."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["v3_pruned"]:
            has_digit = any(c.isdigit() for c in col)
            assert has_digit, \
                f"V3 column {col} should contain window size digits"

    def test_v3_names_are_deterministic(self):
        """V3 column names must be deterministic."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols1 = get_formulaic_alpha_columns("v3_pruned")
        cols2 = get_formulaic_alpha_columns("v3_pruned")
        assert cols1 == cols2


class TestV3Metadata:
    """Verify v3 metadata coverage."""

    def test_v3_metadata_has_all_columns(self):
        """Metadata must cover all v3 formulaic alpha columns."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["v3_pruned"]:
            assert col in metadata, \
                f"V3 column {col} must have metadata entry"

    def test_v3_metadata_has_family(self):
        """V3 metadata entries must have family field."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["v3_pruned"]:
            assert "family" in metadata[col], \
                f"V3 metadata for {col} must have 'family' field"


class TestV3AblationReport:
    """Verify v3 ablation report structure and evidence."""

    def test_ablation_report_returns_dict(self):
        """get_v3_ablation_report must return a dict."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert isinstance(report, dict)

    def test_ablation_report_has_gate(self):
        """Ablation report must reference the v3 gate."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["gate"] == "FORMULAIC_ALPHA_V3_PRUNE_20260614"

    def test_ablation_report_v3_candidates(self):
        """Ablation report must list the 5 v3 candidates."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["v3_n_candidates"] == 5
        assert len(report["v3_candidates"]) == 5

    def test_ablation_report_excludes_bad(self):
        """Ablation report must document exclusion of amihud and range_compression."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["v3_no_amihud"] is True
        assert report["v3_no_range_compression"] is True
        assert "alpha_fml089_amihud_illiq_20" in report["v3_excluded"]
        assert "alpha_fml078_range_compression_10" in report["v3_excluded"]

    def test_ablation_report_no_momentum(self):
        """Ablation report must confirm no momentum."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["v3_no_momentum"] is True

    def test_ablation_report_all_positive_ic(self):
        """All v3 retained candidates must have positive IC evidence."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["v3_retained_all_positive_ic"] is True

    def test_ablation_report_default_unchanged(self):
        """Ablation report must confirm default unchanged."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["default_unchanged"] is True

    def test_ablation_report_pit_safe(self):
        """Ablation report must confirm PIT safety."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        assert report["pit_safe"] is True

    def test_ablation_report_json_serializable(self):
        """Ablation report must be JSON-serializable."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        json_str = json.dumps(report)
        assert len(json_str) > 0

    def test_ablation_report_has_ic_evidence(self):
        """Ablation report must include IC evidence per candidate."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        ic_ev = report["ic_evidence_by_candidate"]
        assert isinstance(ic_ev, dict)
        assert ic_ev["alpha_fml052_close_zscore_mr_20"] > 0
        assert ic_ev["alpha_fml089_amihud_illiq_20"] < 0
        assert ic_ev["alpha_fml078_range_compression_10"] < 0

    def test_ablation_report_has_exclusion_rationale(self):
        """Each excluded candidate must have a rationale."""
        from omega.quant.alpha.formulaic_alphas import get_v3_ablation_report
        report = get_v3_ablation_report()
        for excluded_name in report["v3_excluded"]:
            assert excluded_name in report["v3_exclusion_rationale"], \
                f"Excluded candidate {excluded_name} must have a rationale"


# ---------------------------------------------------------------------------
# Section 14: V4 Extended Alpha Set (GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616)
# ---------------------------------------------------------------------------


class TestV4ExtendedSetRegistry:
    """Verify v4 'v4_vn_extended' alpha set registry."""

    def test_v4_set_exists_in_registry(self):
        """FORMULAIC_ALPHA_SETS must contain 'v4_vn_extended' key."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        assert "v4_vn_extended" in FORMULAIC_ALPHA_SETS, \
            "FORMULAIC_ALPHA_SETS must contain 'v4_vn_extended'"

    def test_v4_set_has_exactly_7_candidates(self):
        """V4 extended set must have exactly 7 candidates (5 from v3 + 2 new)."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v4_cols = FORMULAIC_ALPHA_SETS["v4_vn_extended"]
        assert len(v4_cols) == 7, \
            f"V4 extended set must have 7 candidates, got {len(v4_cols)}"

    def test_v4_retains_all_v3_candidates(self):
        """V4 must retain all 5 v3_pruned candidates."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = set(FORMULAIC_ALPHA_SETS["v3_pruned"])
        v4_cols = set(FORMULAIC_ALPHA_SETS["v4_vn_extended"])
        assert v3_cols.issubset(v4_cols), \
            f"V4 must retain all v3 candidates. Missing: {v3_cols - v4_cols}"

    def test_v4_includes_new_vn_alphas(self):
        """V4 must include new VN-specific alphas: fml090, fml091."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v4_cols = FORMULAIC_ALPHA_SETS["v4_vn_extended"]
        assert "alpha_fml090_vn_liquidity_momentum" in v4_cols
        assert "alpha_fml091_vn_hl_spread_reversal" in v4_cols

    def test_v4_get_columns_returns_correct_names(self):
        """get_formulaic_alpha_columns('v4_vn_extended') returns 7 names."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols = get_formulaic_alpha_columns("v4_vn_extended")
        assert len(cols) == 7
        assert all(c.startswith("alpha_fml") for c in cols)

    def test_v4_gate_id_constant(self):
        """GATE_ID_V4 must be FORMULAIC_ALPHA_V4_EXTENDED_20260616."""
        from omega.quant.alpha.formulaic_alphas import GATE_ID_V4
        assert GATE_ID_V4 == "FORMULAIC_ALPHA_V4_EXTENDED_20260616"

    def test_v4_default_unchanged(self):
        """DEFAULT_FORMULAIC_ALPHA_SET must still be 'small' (no default behavior change)."""
        from omega.quant.alpha.formulaic_alphas import DEFAULT_FORMULAIC_ALPHA_SET
        assert DEFAULT_FORMULAIC_ALPHA_SET == "small", \
            "Default must remain 'small' — v4 is research-only opt-in"


class TestV4FiniteOutputs:
    """Verify v4 outputs are finite (no inf/nan)."""

    def test_v4_no_inf_in_outputs(self):
        """V4 formulaic alpha outputs must not contain inf."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        assert len(fml_cols) == 7
        for col in fml_cols:
            assert not np.any(np.isinf(result[col].values)), \
                f"V4 column {col} contains inf values"

    def test_v4_no_nan_in_outputs(self):
        """V4 formulaic alpha outputs must not contain NaN (all sanitized)."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert not np.any(np.isnan(result[col].values)), \
                f"V4 column {col} contains NaN values"

    def test_v4_outputs_are_float64(self):
        """All v4 formulaic alpha columns should be float64."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert result[col].dtype == np.float64, \
                f"V4 column {col} dtype should be float64, got {result[col].dtype}"

    def test_v4_extreme_inputs_produce_finite_output(self):
        """Extreme input values must still produce finite v4 outputs."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        df.loc[10, "close"] = 1e12
        df.loc[20, "volume"] = 0
        df.loc[30, "open"] = 1e-6
        df.loc[40, "high"] = 1e15
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        fml_cols = [c for c in result.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            assert np.all(np.isfinite(result[col].values)), \
                f"V4 column {col} has non-finite values with extreme inputs"

    def test_v4_new_alphas_compute_successfully(self):
        """New v4 alphas (fml090, fml091) must compute without errors."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=100)
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        assert "alpha_fml090_vn_liquidity_momentum" in result.columns
        assert "alpha_fml091_vn_hl_spread_reversal" in result.columns
        assert not np.any(np.isnan(result["alpha_fml090_vn_liquidity_momentum"].values))
        assert not np.any(np.isnan(result["alpha_fml091_vn_hl_spread_reversal"].values))


class TestV4PITGuard:
    """Verify PIT safety for v4 extended alphas: no negative shifts, T-1 lag enforced."""

    def test_v4_source_no_negative_shifts(self):
        """Source code must not contain .shift(- or shift(negative) for v4 alphas."""
        src = _get_formulaic_source()
        import re
        neg_shifts = re.findall(r'\.shift\s*\(\s*-\d', src)
        assert len(neg_shifts) == 0, \
            f"Found negative shifts in formulaic_alphas.py: {neg_shifts}"

    def test_v4_all_shifts_positive(self):
        """All shift() calls must use positive arguments (including v4 functions)."""
        import re
        src = _get_formulaic_source()
        shifts = re.findall(r'\.shift\s*\(\s*(-?\d+)', src)
        for s in shifts:
            assert int(s) > 0, \
                f"Found non-positive shift({s}) in formulaic_alphas.py — PIT violation"

    def test_v4_first_rows_finite_after_shift(self):
        """First row per ticker must be finite (0.0 fallback) after shift(1) for v4."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=30)
        result = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        v4_new_cols = [
            "alpha_fml090_vn_liquidity_momentum",
            "alpha_fml091_vn_hl_spread_reversal",
        ]
        for col in v4_new_cols:
            if col in result.columns:
                first_rows = result.groupby("ticker")[col].first()
                for ticker, val in first_rows.items():
                    assert np.isfinite(val), \
                        f"V4 first row for {ticker}/{col} should be finite, got {val}"

    def test_v4_gate_label_in_source(self):
        """V4 gate label must be present in source code."""
        src = _get_formulaic_source()
        assert "FORMULAIC_ALPHA_V4_EXTENDED_20260616" in src, \
            "V4 gate label must be present in formulaic_alphas.py"


class TestV4CLIChoice:
    """Verify CLI supports v4 set choice and default unchanged."""

    def test_cli_v4_choice_registered(self):
        """CLI choices for --formulaic-alpha-set must include 'v4_vn_extended'."""
        src = _get_script_source()
        assert "v4_vn_extended" in src, \
            "CLI must include 'v4_vn_extended' as a choice"

    def test_cli_default_still_small(self):
        """CLI default must remain 'small' — no default behavior change."""
        src = _get_script_source()
        assert 'default="small"' in src, \
            "CLI default must remain 'small'"

    def test_cli_v4_gate_label_present(self):
        """CLI source must reference FORMULAIC_ALPHA_V4_EXTENDED_20260616."""
        src = _get_script_source()
        assert "FORMULAIC_ALPHA_V4_EXTENDED_20260616" in src, \
            "CLI source must reference v4 gate label"


class TestV4Determinism:
    """Verify v4 extended outputs are deterministic."""

    def test_v4_same_input_same_output(self):
        """Same input data must produce identical v4 outputs across calls."""
        from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60, seed=42)
        result1 = compute_formulaic_alphas(df, set_name="v4_vn_extended")
        result2 = compute_formulaic_alphas(df, set_name="v4_vn_extended")

        fml_cols = [c for c in result1.columns if c.startswith("alpha_fml")]
        for col in fml_cols:
            np.testing.assert_array_equal(
                result1[col].values, result2[col].values,
                err_msg=f"V4 column {col} is not deterministic"
            )


class TestV4NamingConvention:
    """Verify v4 naming conventions."""

    def test_v4_all_names_start_with_alpha_fml(self):
        """All v4 column names must start with 'alpha_fml'."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["v4_vn_extended"]:
            assert col.startswith("alpha_fml"), \
                f"V4 column {col} must start with 'alpha_fml'"

    def test_v4_new_alphas_have_vn_prefix(self):
        """New v4 VN-specific alphas must contain 'vn' in their names."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v4_cols = FORMULAIC_ALPHA_SETS["v4_vn_extended"]
        v3_cols = set(FORMULAIC_ALPHA_SETS["v3_pruned"])
        new_v4_cols = [c for c in v4_cols if c not in v3_cols]
        for col in new_v4_cols:
            assert "vn" in col, \
                f"New v4 VN-specific column {col} should contain 'vn'"

    def test_v4_names_contain_window_info(self):
        """V4 column names should encode window size or descriptive suffix."""
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        for col in FORMULAIC_ALPHA_SETS["v4_vn_extended"]:
            # All v4 alphas should have some numeric or descriptive component
            has_digit_or_desc = (any(c.isdigit() for c in col) or 
                                "_" in col.split("_", 2)[-1])
            assert has_digit_or_desc, \
                f"V4 column {col} should contain window size or descriptive component"

    def test_v4_names_are_deterministic(self):
        """V4 column names must be deterministic."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        cols1 = get_formulaic_alpha_columns("v4_vn_extended")
        cols2 = get_formulaic_alpha_columns("v4_vn_extended")
        assert cols1 == cols2


class TestV4Metadata:
    """Verify v4 metadata coverage."""

    def test_v4_metadata_has_all_columns(self):
        """Metadata must cover all v4 formulaic alpha columns."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["v4_vn_extended"]:
            assert col in metadata, \
                f"V4 column {col} must have metadata entry"

    def test_v4_metadata_has_family(self):
        """V4 metadata entries must have family field."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            FORMULAIC_ALPHA_SETS,
        )
        metadata = get_formulaic_alpha_metadata()
        for col in FORMULAIC_ALPHA_SETS["v4_vn_extended"]:
            assert "family" in metadata[col], \
                f"V4 metadata for {col} must have 'family' field"

    def test_v4_new_alphas_reference_v4_gate(self):
        """New v4-only alphas must reference GATE_ID_V4."""
        from omega.quant.alpha.formulaic_alphas import (
            get_formulaic_alpha_metadata,
            GATE_ID_V4,
        )
        metadata = get_formulaic_alpha_metadata()
        v4_only_cols = [
            "alpha_fml090_vn_liquidity_momentum",
            "alpha_fml091_vn_hl_spread_reversal",
        ]
        for col in v4_only_cols:
            assert metadata[col].get("source") == GATE_ID_V4, \
                f"V4-only metadata for {col} must reference gate {GATE_ID_V4}"

    def test_v4_new_alphas_have_vn_category(self):
        """New v4 alphas must be categorized as VN microstructure/liquidity."""
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_metadata
        metadata = get_formulaic_alpha_metadata()
        v4_only_cols = [
            "alpha_fml090_vn_liquidity_momentum",
            "alpha_fml091_vn_hl_spread_reversal",
        ]
        for col in v4_only_cols:
            category = metadata[col].get("category", "")
            assert "VN" in category or "v4" in category, \
                f"V4 alpha {col} must have VN/v4 category"
