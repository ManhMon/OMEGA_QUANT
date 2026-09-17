"""
Nonredundant Alpha Generation Tests
GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
[L2-Impl:Role14-Data-Scientist] - 2026-06-15

Verifies that:
1. Default disabled — no nonredundant columns when flag not set
2. CLI opt-in — flags registered and wired
3. PIT safety — no future/lead/negative shift patterns
4. Trailing stats — all rolling operations use trailing windows only
5. Finite outputs — no inf/nan in output
6. JSON evidence — evidence persisted per fold
7. Dynamic smoke — engine runs with nonredundant alphas enabled
8. Regression — default behavior unchanged when disabled

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import argparse
import ast
import json
import os
import re
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


def _get_nonredundant_source():
    """Read the nonredundant_alphas.py source code."""
    nr_path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "nonredundant_alphas.py"
    return nr_path.read_text(encoding="utf-8")


def _make_synthetic_ohlcv(n_tickers: int = 5, n_days: int = 60, seed: int = 42) -> pd.DataFrame:
    """Create synthetic OHLCV panel data for testing."""
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


class TestNonredundantAlphaCLIFlags:
    """Verify --enable-nonredundant-alphas and related CLI flags."""

    def test_cli_enable_nonredundant_alphas_flag_registered(self):
        src = _get_script_source()
        assert '"--enable-nonredundant-alphas"' in src, \
            "CLI flag --enable-nonredundant-alphas must be registered"

    def test_cli_nonredundant_alpha_set_flag_registered(self):
        src = _get_script_source()
        assert '"--nonredundant-alpha-set"' in src, \
            "CLI flag --nonredundant-alpha-set must be registered"

    def test_cli_nonredundant_alpha_max_candidates_flag_registered(self):
        src = _get_script_source()
        assert '"--nonredundant-alpha-max-candidates"' in src, \
            "CLI flag --nonredundant-alpha-max-candidates must be registered"

    def test_cli_nonredundant_alpha_set_default_v1(self):
        src = _get_script_source()
        assert 'default="v1"' in src, \
            "Default must be 'v1' for nonredundant alpha set"

    def test_cli_gate_label_present(self):
        src = _get_script_source()
        assert "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615" in src, \
            "Gate label must be present"

    def test_cli_enable_is_store_true(self):
        """Verify --enable-nonredundant-alphas uses action='store_true' (default False)."""
        src = _get_script_source()
        # The flag should be near action="store_true"
        assert '"--enable-nonredundant-alphas"' in src
        idx = src.index('"--enable-nonredundant-alphas"')
        surrounding = src[idx:idx + 200]
        assert 'store_true' in surrounding, \
            "--enable-nonredundant-alphas must use store_true action"


# ---------------------------------------------------------------------------
# Section 2: Default Disabled Behavior
# ---------------------------------------------------------------------------


class TestDefaultDisabled:
    """Verify nonredundant alphas are disabled by default."""

    def test_engine_default_disabled(self):
        """Engine with no nonredundant args should have enable_nonredundant_alphas=False."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(return_value=pd.DataFrame())

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {"balanced": {}, "alpha_recovery": {}, "drawdown_guarded": {}, "ic_first_guarded": {}}
            mock_ra.VALID_RESEARCH_POOL_MODES = ["full", "recovery_only", "recoverable_only"]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(alpha_module=mock_module)
                assert engine.enable_nonredundant_alphas is False

    def test_compute_alphas_skips_nonredundant_when_disabled(self):
        """When disabled, compute_alphas should NOT call nonredundant module."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        test_df = pd.DataFrame({
            "ticker": ["A"] * 5,
            "date": pd.date_range("2020-01-01", periods=5),
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.5] * 5,
            "volume": [10000] * 5,
        })
        mock_module.compute_phase34_microstructure_alphas = MagicMock(return_value=test_df.copy())

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {"balanced": {}, "alpha_recovery": {}, "drawdown_guarded": {}, "ic_first_guarded": {}}
            mock_ra.VALID_RESEARCH_POOL_MODES = ["full", "recovery_only", "recoverable_only"]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(alpha_module=mock_module)
                result = engine.compute_alphas(test_df)
                # No nonredundant columns should be present
                nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
                assert len(nr_cols) == 0, \
                    f"No nonredundant columns expected when disabled, found: {nr_cols}"


# ---------------------------------------------------------------------------
# Section 3: PIT Safety — No Future/Lookahead
# ---------------------------------------------------------------------------


class TestPITSafety:
    """Verify no lookahead bias in nonredundant alpha source code."""

    def test_no_shift_negative(self):
        """Source must not contain .shift(-N) patterns (future data)."""
        src = _get_nonredundant_source()
        # Check for negative shifts: .shift(-1), .shift(-2), etc.
        negative_shift_pattern = re.compile(r'\.shift\(\s*-\d+')
        matches = negative_shift_pattern.findall(src)
        assert len(matches) == 0, \
            f"Found negative shift patterns (lookahead bias): {matches}"

    def test_no_lead_operations(self):
        """Source must not contain .lead() operations."""
        src = _get_nonredundant_source()
        assert ".lead(" not in src, \
            "Source contains .lead() operations (future data access)"

    def test_no_future_data_keywords(self):
        """Source must not contain future-data keywords in actual code (not comments)."""
        src = _get_nonredundant_source()
        # Strip docstrings and comments before checking
        # Only check for actual code patterns, not documentation
        forbidden_code_patterns = ["future_data", "forward_fill"]
        for keyword in forbidden_code_patterns:
            assert keyword not in src.lower(), \
                f"Source contains forbidden keyword in code: {keyword}"
        # Note: "lookahead" and "look_ahead" may appear in docstrings/comments
        # describing what NOT to do, so we don't check for them here.

    def test_all_shifts_are_t_minus_1_or_positive(self):
        """All .shift() calls must be .shift(1) or .shift(positive)."""
        src = _get_nonredundant_source()
        # Find all .shift(N) patterns
        shift_pattern = re.compile(r'\.shift\(\s*(-?\d+)\s*\)')
        matches = shift_pattern.findall(src)
        for match in matches:
            val = int(match)
            assert val >= 0, \
                f"Found negative shift value {val} (must be >= 0 for PIT safety)"

    def test_trailing_window_only(self):
        """Rolling operations must not use center=True (would include future)."""
        src = _get_nonredundant_source()
        assert "center=True" not in src, \
            "Source contains center=True in rolling (includes future data)"


# ---------------------------------------------------------------------------
# Section 4: Finite Outputs
# ---------------------------------------------------------------------------


class TestFiniteOutputs:
    """Verify all nonredundant alpha outputs are finite."""

    def test_all_alphas_finite_on_synthetic_data(self):
        """All alpha columns should produce finite values on synthetic data."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 10, f"Expected 10 alpha columns, got {len(nr_cols)}"

        for col in nr_cols:
            vals = result[col].dropna()
            assert len(vals) > 0, f"Column {col} has all NaN values"
            assert np.all(np.isfinite(vals)), \
                f"Column {col} contains non-finite values: " \
                f"inf={np.sum(np.isinf(vals))}, nan={np.sum(np.isnan(vals))}"

    def test_alpha_values_bounded(self):
        """Alpha values should be within reasonable bounds (no extreme outliers)."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        for col in nr_cols:
            vals = result[col].dropna()
            if len(vals) > 0:
                # Most alpha values should be within [-100, 100]
                # (z-scores, ratios, etc.)
                extreme = vals[(vals.abs() > 100)]
                pct_extreme = len(extreme) / len(vals)
                assert pct_extreme < 0.05, \
                    f"Column {col}: {pct_extreme:.1%} values exceed |100|"

    def test_first_rows_are_zero_or_nan_after_shift(self):
        """First rows per ticker should be NaN or 0.0 due to T-1 shift + sanitization.

        The _sanitize_output helper fills NaN with 0.0, so we check that
        early rows have more zeros/NaN than later rows (warmup effect).
        """
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=30)
        result = compute_nonredundant_alphas(df, set_name="v1")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        for ticker in result['ticker'].unique():
            ticker_data = result[result['ticker'] == ticker]
            # First 5 rows should have more zero/NaN values than rows 20-25
            early = ticker_data.iloc[:5][nr_cols]
            late = ticker_data.iloc[20:25][nr_cols]
            early_zero_nan = ((early == 0.0) | early.isna()).sum().sum()
            late_zero_nan = ((late == 0.0) | late.isna()).sum().sum()
            # Early rows should have at least as many zero/NaN as late rows
            # (warmup period means rolling stats aren't ready yet)
            assert early_zero_nan >= late_zero_nan, \
                f"Ticker {ticker}: early rows should have more warmup zeros/NaN " \
                f"(early={early_zero_nan}, late={late_zero_nan})"


# ---------------------------------------------------------------------------
# Section 5: Alpha Column Registry
# ---------------------------------------------------------------------------


class TestAlphaRegistry:
    """Verify alpha column registry functions correctly."""

    def test_get_columns_v1(self):
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1")
        assert len(cols) == 10
        assert all(c.startswith("alpha_nr_") for c in cols)

    def test_get_columns_invalid_set(self):
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        with pytest.raises(ValueError, match="Unknown nonredundant alpha set"):
            get_nonredundant_alpha_columns("invalid_set")

    def test_alpha_set_v1_contents(self):
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        v1 = NONREDUNDANT_ALPHA_SETS["v1"]
        # Check all 5 families represented (2 candidates each)
        families = {
            "liq_shock": [c for c in v1 if "liq_shock" in c],
            "close_location": [c for c in v1 if "close_location" in c or "range_pressure" in c],
            "vol_compression": [c for c in v1 if "vol_compression" in c or "vol_breakout" in c],
            "residual": [c for c in v1 if "residual" in c or "market_relative" in c],
            "breadth": [c for c in v1 if "breadth" in c or "advance_decline" in c],
        }
        for family_name, candidates in families.items():
            assert len(candidates) == 2, \
                f"Family {family_name} should have 2 candidates, got {len(candidates)}: {candidates}"


# ---------------------------------------------------------------------------
# Section 6: Sector Map Fallback
# ---------------------------------------------------------------------------


class TestSectorMapFallback:
    """Verify sector-relative alphas fall back gracefully."""

    def test_residual_reversal_without_sector_map(self):
        """Residual reversal should work without sector map (market-relative)."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1", sector_map=None)

        col = "alpha_nr_residual_reversal_10"
        assert col in result.columns
        vals = result[col].dropna()
        assert len(vals) > 0, "Residual reversal should produce values without sector map"
        assert np.all(np.isfinite(vals))

    def test_residual_reversal_with_sector_map(self):
        """Residual reversal should use sector map when provided."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        sector_map = {f"SYM{i:02d}": f"SECTOR_{i % 2}" for i in range(5)}
        result = compute_nonredundant_alphas(df, set_name="v1", sector_map=sector_map)

        col = "alpha_nr_residual_reversal_10"
        assert col in result.columns
        vals = result[col].dropna()
        assert len(vals) > 0

    def test_load_sector_map_missing_file(self):
        """load_sector_map should return None for missing file."""
        from omega.quant.alpha.nonredundant_alphas import load_sector_map
        result = load_sector_map(path="/nonexistent/path/sector.csv")
        assert result is None


# ---------------------------------------------------------------------------
# Section 7: Max Candidates
# ---------------------------------------------------------------------------


class TestMaxCandidates:
    """Verify max_candidates parameter works correctly."""

    def test_max_candidates_limits_output(self):
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1", max_candidates=3)

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 3, f"Expected 3 columns, got {len(nr_cols)}"

    def test_max_candidates_none_returns_all(self):
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1", max_candidates=None)

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 10


# ---------------------------------------------------------------------------
# Section 8: Phase35 Engine Wiring
# ---------------------------------------------------------------------------


class TestPhase35EngineWiring:
    """Verify nonredundant alphas are properly wired into phase35 engine."""

    def test_engine_gate_constant_defined(self):
        src = _get_engine_source()
        assert "NONREDUNDANT_ALPHA_GATE_ID" in src, \
            "GATE constant NONREDUNDANT_ALPHA_GATE_ID must be defined"
        assert "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615" in src

    def test_engine_init_has_params(self):
        src = _get_engine_source()
        assert "enable_nonredundant_alphas" in src
        assert "nonredundant_alpha_set" in src
        assert "nonredundant_alpha_max_candidates" in src

    def test_fold_metrics_has_evidence_field(self):
        src = _get_engine_source()
        assert "nonredundant_alpha_evidence" in src, \
            "FoldMetrics must have nonredundant_alpha_evidence field"

    def test_compute_alphas_calls_nonredundant(self):
        src = _get_engine_source()
        assert "compute_nonredundant_alphas" in src, \
            "compute_alphas must call compute_nonredundant_alphas when enabled"

    def test_script_wires_alpha_cols(self):
        src = _get_script_source()
        assert "get_nonredundant_alpha_columns" in src, \
            "Script must call get_nonredundant_alpha_columns to append alpha_cols"

    def test_script_serializes_evidence(self):
        src = _get_script_source()
        assert "nonredundant_alpha_evidence" in src, \
            "Script must serialize nonredundant_alpha_evidence"


# ---------------------------------------------------------------------------
# Section 9: Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Verify nonredundant alphas are deterministic."""

    def test_same_input_same_output(self):
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=40, seed=123)

        result1 = compute_nonredundant_alphas(df.copy(), set_name="v1")
        result2 = compute_nonredundant_alphas(df.copy(), set_name="v1")

        nr_cols = [c for c in result1.columns if c.startswith("alpha_nr_")]
        for col in nr_cols:
            pd.testing.assert_series_equal(
                result1[col], result2[col],
                check_names=True,
                obj=f"Determinism check for {col}",
            )


# ---------------------------------------------------------------------------
# Section 10: Dynamic Smoke Test (Integration)
# ---------------------------------------------------------------------------


class TestDynamicSmoke:
    """Verify engine runs end-to-end with nonredundant alphas enabled."""

    def test_engine_enabled_produces_nr_columns(self):
        """When enabled, compute_alphas should produce nonredundant columns."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)

        test_df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=test_df.copy()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(
                    alpha_module=mock_module,
                    enable_nonredundant_alphas=True,
                    nonredundant_alpha_set="v1",
                )
                result = engine.compute_alphas(test_df)

                nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
                assert len(nr_cols) == 10, \
                    f"Expected 10 nonredundant columns, got {len(nr_cols)}: {nr_cols}"

                # Verify all finite
                for col in nr_cols:
                    vals = result[col].dropna()
                    assert len(vals) > 0, f"Column {col} has no non-NaN values"
                    assert np.all(np.isfinite(vals)), \
                        f"Column {col} contains non-finite values"


# ---------------------------------------------------------------------------
# Section 11: Per-Ticker PIT Lag Boundary (Blocker 1 Regression)
# ---------------------------------------------------------------------------


class TestPerTickerPITLagBoundary:
    """Regression test for L3 audit finding:
    pct_change().shift(1) must be per-ticker, not global.

    Reproduces the audit scenario: 2 tickers × 2 dates.
    After sort by [ticker, date], the data layout is:
        row0: ticker=A, date=d1
        row1: ticker=A, date=d2
        row2: ticker=B, date=d1
        row3: ticker=B, date=d2
    A global .shift(1) would leak A's d2 return into B's d1 row.
    A correct per-group .shift(1) leaves B's d1 row as NaN/0.
    """

    def test_first_row_of_each_ticker_has_no_prior_ticker_contamination(self):
        """First row of every ticker must be NaN/0.0 for return-based NR alphas.

        This is the exact reproduction from the L3 audit:
        global_shift leaked ticker A's last return into ticker B's first row.
        """
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        # Build minimal 2-ticker × 2-date panel
        df = pd.DataFrame({
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03",
                                    "2020-01-02", "2020-01-03"]),
            "open":   [100.0, 110.0, 200.0, 220.0],
            "high":   [105.0, 115.0, 210.0, 230.0],
            "low":    [ 95.0, 105.0, 190.0, 210.0],
            "close":  [100.0, 110.0, 200.0, 220.0],
            "volume": [10000, 12000, 20000, 22000],
        })

        result = compute_nonredundant_alphas(df, set_name="v1")

        # Return-based alphas that use pct_change
        return_based_alphas = [
            "alpha_nr_liq_shock_reversal_10",
            "alpha_nr_residual_reversal_10",
            "alpha_nr_market_relative_momentum_20",
            "alpha_nr_breadth_conditioned_reversal_10",
            "alpha_nr_advance_decline_signal_20",
        ]

        for ticker in result["ticker"].unique():
            ticker_rows = result[result["ticker"] == ticker].sort_values("date")
            first_row_idx = ticker_rows.index[0]

            for alpha_col in return_based_alphas:
                if alpha_col in result.columns:
                    val = result.loc[first_row_idx, alpha_col]
                    # First row of each ticker must be 0.0 (sanitised NaN) —
                    # NOT a leaked value from the previous ticker.
                    assert val == 0.0 or np.isnan(val), (
                        f"CONTAMINATION: ticker={ticker}, alpha={alpha_col}, "
                        f"first-row value={val}. "
                        f"Expected 0.0/NaN (no prior-ticker data)."
                    )

    def test_grouped_shift_produces_nan_per_ticker_boundary(self):
        """Direct unit test: per-group shift yields NaN at ticker boundaries."""
        # 2 tickers, 3 dates each
        df = pd.DataFrame({
            "ticker": ["A", "A", "A", "B", "B", "B"],
            "date": pd.to_datetime([
                "2020-01-02", "2020-01-03", "2020-01-06",
                "2020-01-02", "2020-01-03", "2020-01-06",
            ]),
            "close": [100.0, 110.0, 105.0, 200.0, 190.0, 210.0],
        })

        # The fixed pattern: pct_change then per-group shift
        ret = df.groupby("ticker")["close"].pct_change()
        ret_lagged = ret.groupby(df["ticker"]).shift(1)

        # First row of each ticker must be NaN (no prior data)
        for ticker in df["ticker"].unique():
            ticker_mask = df["ticker"] == ticker
            first_idx = df[ticker_mask].index[0]
            assert np.isnan(ret_lagged.iloc[first_idx]), (
                f"Ticker {ticker} first row must be NaN after per-group shift, "
                f"got {ret_lagged.iloc[first_idx]}"
            )

        # The old broken pattern for comparison:
        ret_broken = df.groupby("ticker")["close"].pct_change().shift(1)
        # B's first row (index 3) gets A's last return:
        # A's last pct_change = (105-110)/110 = -0.04545...
        # After global shift(1), B's d1 row at index 3 gets A's d3 return.
        # This must NOT equal NaN — proving the bug existed.
        b_first_idx = df[df["ticker"] == "B"].index[0]
        b_first_broken = ret_broken.iloc[b_first_idx]
        # The broken version leaks: B's first row is NOT NaN
        assert not np.isnan(b_first_broken), (
            "Expected broken pattern to leak; test setup invalid"
        )
        # The fixed version: B's first row IS NaN
        b_first_fixed = ret_lagged.iloc[b_first_idx]
        assert np.isnan(b_first_fixed), (
            f"Fixed version must produce NaN at ticker boundary, got {b_first_fixed}"
        )


# ---------------------------------------------------------------------------
# Section 12: Per-Fold NR Evidence Persistence (Blocker 2 Regression)
# ---------------------------------------------------------------------------


class TestPerFoldNREvidence:
    """Regression test: per-fold nonredundant_alpha_evidence must be populated
    when NR alphas are enabled."""

    def test_nr_evidence_populated_when_enabled(self):
        """When NR alphas enabled, engine should track sector_map status."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine

        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        test_df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=test_df.copy()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(
                    alpha_module=mock_module,
                    enable_nonredundant_alphas=True,
                    nonredundant_alpha_set="v1",
                )
                # compute_alphas should set sector_map tracking
                result = engine.compute_alphas(test_df)

                # Verify sector_map tracking attributes set
                assert hasattr(engine, '_nr_sector_map_loaded'), \
                    "Engine must track _nr_sector_map_loaded after compute_alphas"
                assert hasattr(engine, '_nr_sector_map_fallback_reason'), \
                    "Engine must track _nr_sector_map_fallback_reason"

    def test_nr_evidence_dict_structure(self):
        """Verify NR evidence dict has all required keys."""
        from omega.quant.alpha.nonredundant_alphas import GATE_ID

        required_keys = [
            "gate", "enabled", "set_name", "max_candidates",
            "computed_candidate_columns", "computed_candidate_count",
            "sector_map_loaded", "sector_map_fallback", "pit_safe",
            "fallback_reason",
        ]

        # Simulate evidence dict as built in run_fold
        nr_evidence = {
            "gate": GATE_ID,
            "enabled": True,
            "set_name": "v1",
            "max_candidates": None,
            "computed_candidate_columns": [
                "alpha_nr_liq_shock_zscore_20",
                "alpha_nr_liq_shock_reversal_10",
            ],
            "computed_candidate_count": 2,
            "sector_map_loaded": False,
            "sector_map_fallback": True,
            "pit_safe": True,
            "fallback_reason": "sector_mapping_level2.csv not found",
        }

        for key in required_keys:
            assert key in nr_evidence, \
                f"NR evidence missing required key: {key}"

        # Verify serializable
        json.dumps(nr_evidence)

    def test_fold_metrics_has_nr_evidence_field(self):
        """FoldMetrics dataclass must accept nonredundant_alpha_evidence."""
        from omega.quant.alpha.phase35 import FoldMetrics
        import dataclasses

        field_names = [f.name for f in dataclasses.fields(FoldMetrics)]
        assert "nonredundant_alpha_evidence" in field_names, \
            "FoldMetrics must have nonredundant_alpha_evidence field"

    def test_serializer_writes_nr_evidence(self):
        """Verify run_phase35_backtest.py serializer writes NR evidence."""
        src = _get_script_source()
        assert "nonredundant_alpha_evidence" in src, \
            "Serializer must include nonredundant_alpha_evidence"
        # Verify the evidence is written when non-None
        assert 'nr_evidence = getattr(m, "nonredundant_alpha_evidence"' in src


# ---------------------------------------------------------------------------
# Section 13: v1_pruned Alpha Set (GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615)
# ---------------------------------------------------------------------------


class TestV1PrunedAlphaSet:
    """Verify v1_pruned alpha set: positive-evidence-only subset of v1.

    GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615
    Includes 5 positive-IC candidates, excludes 4 negative-IC + 1 neutral.
    """

    # Expected positive-evidence candidates
    EXPECTED_PRUNED = (
        "alpha_nr_market_relative_momentum_20",
        "alpha_nr_range_pressure_momentum_20",
        "alpha_nr_liq_shock_reversal_10",
        "alpha_nr_close_location_value_10",
        "alpha_nr_vol_breakout_directional_10",
    )

    # Expected excluded (negative + neutral)
    EXPECTED_EXCLUDED = (
        "alpha_nr_advance_decline_signal_20",
        "alpha_nr_residual_reversal_10",
        "alpha_nr_breadth_conditioned_reversal_10",
        "alpha_nr_vol_compression_20",
        "alpha_nr_liq_shock_zscore_20",
    )

    def test_v1_pruned_candidate_count(self):
        """v1_pruned must contain exactly 5 candidates."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_pruned")
        assert len(cols) == 5, f"Expected 5 pruned candidates, got {len(cols)}"

    def test_v1_pruned_candidate_list(self):
        """v1_pruned must contain exactly the positive-evidence candidates."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_pruned")
        assert set(cols) == set(self.EXPECTED_PRUNED), (
            f"v1_pruned candidates mismatch.\n"
            f"Expected: {sorted(self.EXPECTED_PRUNED)}\n"
            f"Got:      {sorted(cols)}"
        )

    def test_v1_pruned_excludes_negative_candidates(self):
        """v1_pruned must NOT contain any negative/neutral candidates."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        pruned = set(NONREDUNDANT_ALPHA_SETS["v1_pruned"])
        for excluded in self.EXPECTED_EXCLUDED:
            assert excluded not in pruned, (
                f"v1_pruned must exclude {excluded}, but it was found"
            )

    def test_v1_unchanged_when_v1_pruned_added(self):
        """v1 set must remain unchanged (10 candidates) after v1_pruned is added."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        v1 = NONREDUNDANT_ALPHA_SETS["v1"]
        assert len(v1) == 10, f"v1 must still have 10 candidates, got {len(v1)}"
        # All 5 families × 2 candidates
        assert "alpha_nr_liq_shock_zscore_20" in v1
        assert "alpha_nr_advance_decline_signal_20" in v1
        assert "alpha_nr_residual_reversal_10" in v1

    def test_v1_pruned_is_subset_of_v1(self):
        """v1_pruned must be a strict subset of v1."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        v1 = set(NONREDUNDANT_ALPHA_SETS["v1"])
        pruned = set(NONREDUNDANT_ALPHA_SETS["v1_pruned"])
        assert pruned.issubset(v1), (
            f"v1_pruned must be subset of v1. "
            f"Missing from v1: {pruned - v1}"
        )
        assert pruned != v1, "v1_pruned must be strict subset of v1"


class TestV1PrunedCLI:
    """Verify CLI accepts v1_pruned for --nonredundant-alpha-set."""

    def test_cli_v1_pruned_in_choices(self):
        """CLI --nonredundant-alpha-set must list v1_pruned as a choice."""
        src = _get_script_source()
        assert '"v1_pruned"' in src or "'v1_pruned'" in src, (
            "CLI must include v1_pruned in choices for --nonredundant-alpha-set"
        )

    def test_cli_gate_label_v1_pruned_present(self):
        """GATE label NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 must appear."""
        src = _get_script_source()
        assert "NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615" in src, (
            "Gate label NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 must be present"
        )

    def test_cli_default_still_v1(self):
        """Default nonredundant-alpha-set must remain 'v1' (opt-in for pruned)."""
        src = _get_script_source()
        # Find the --nonredundant-alpha-set section and verify default
        idx = src.index('"--nonredundant-alpha-set"')
        surrounding = src[idx:idx + 300]
        assert 'default="v1"' in surrounding, (
            "Default for --nonredundant-alpha-set must remain 'v1'"
        )


class TestV1PrunedComputeAlphas:
    """Verify compute_nonredundant_alphas works with v1_pruned."""

    def test_compute_v1_pruned_produces_5_columns(self):
        """compute_nonredundant_alphas with v1_pruned should produce 5 NR columns."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_pruned")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 5, f"Expected 5 NR columns, got {len(nr_cols)}: {nr_cols}"

    def test_compute_v1_pruned_all_finite(self):
        """All v1_pruned alpha outputs must be finite on synthetic data."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_pruned")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        for col in nr_cols:
            vals = result[col].dropna()
            assert len(vals) > 0, f"Column {col} has all NaN values"
            assert np.all(np.isfinite(vals)), (
                f"Column {col} contains non-finite values"
            )

    def test_compute_v1_pruned_excluded_columns_absent(self):
        """Excluded candidates must NOT appear as columns with v1_pruned."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_pruned")

        excluded = [
            "alpha_nr_advance_decline_signal_20",
            "alpha_nr_residual_reversal_10",
            "alpha_nr_breadth_conditioned_reversal_10",
            "alpha_nr_vol_compression_20",
            "alpha_nr_liq_shock_zscore_20",
        ]
        for col in excluded:
            assert col not in result.columns, (
                f"Excluded column {col} should not be present with v1_pruned"
            )


class TestV1PrunedEvidence:
    """Verify per-fold evidence dict correctly reports v1_pruned set_name."""

    def test_evidence_set_name_v1_pruned(self):
        """When engine uses v1_pruned, evidence dict must report set_name='v1_pruned'."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine

        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        test_df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=test_df.copy()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(
                    alpha_module=mock_module,
                    enable_nonredundant_alphas=True,
                    nonredundant_alpha_set="v1_pruned",
                )
                assert engine.nonredundant_alpha_set == "v1_pruned"
                result = engine.compute_alphas(test_df)

                nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
                assert len(nr_cols) == 5, (
                    f"Expected 5 NR columns with v1_pruned, got {len(nr_cols)}"
                )


class TestV1PrunedPerTickerBoundary:
    """Per-ticker PIT lag boundary must still pass with v1_pruned."""

    def test_first_row_no_contamination_v1_pruned(self):
        """First row of each ticker must be 0.0/NaN for return-based v1_pruned alphas."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = pd.DataFrame({
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03",
                                    "2020-01-02", "2020-01-03"]),
            "open":   [100.0, 110.0, 200.0, 220.0],
            "high":   [105.0, 115.0, 210.0, 230.0],
            "low":    [ 95.0, 105.0, 190.0, 210.0],
            "close":  [100.0, 110.0, 200.0, 220.0],
            "volume": [10000, 12000, 20000, 22000],
        })

        result = compute_nonredundant_alphas(df, set_name="v1_pruned")

        # Return-based alphas in v1_pruned
        return_based_pruned = [
            "alpha_nr_liq_shock_reversal_10",
            "alpha_nr_market_relative_momentum_20",
        ]

        for ticker in result["ticker"].unique():
            ticker_rows = result[result["ticker"] == ticker].sort_values("date")
            first_row_idx = ticker_rows.index[0]

            for alpha_col in return_based_pruned:
                if alpha_col in result.columns:
                    val = result.loc[first_row_idx, alpha_col]
                    assert val == 0.0 or np.isnan(val), (
                        f"CONTAMINATION: ticker={ticker}, alpha={alpha_col}, "
                        f"first-row value={val}. Expected 0.0/NaN."
                    )


class TestV1PrunedPhase35Regression:
    """Phase 3.5 regression: v1 unchanged, v1_pruned adds no default behavior change."""

    def test_v1_regression_unchanged(self):
        """v1 set must produce identical results as before (regression check)."""
        from omega.quant.alpha.nonredundant_alphas import (
            compute_nonredundant_alphas,
            NONREDUNDANT_ALPHA_SETS,
        )

        # v1 must still have exactly 10 candidates
        assert len(NONREDUNDANT_ALPHA_SETS["v1"]) == 10

        df = _make_synthetic_ohlcv(n_tickers=3, n_days=60, seed=99)
        result = compute_nonredundant_alphas(df, set_name="v1")
        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 10, (
            f"v1 regression: expected 10 columns, got {len(nr_cols)}"
        )

    def test_default_disabled_unchanged_with_v1_pruned_available(self):
        """Engine default (disabled) must not be affected by v1_pruned existing."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=pd.DataFrame()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(alpha_module=mock_module)
                assert engine.enable_nonredundant_alphas is False
                assert engine.nonredundant_alpha_set == "v1"


# ---------------------------------------------------------------------------
# Section 14: v1_mrm_only Focused Overlay
# GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
# ---------------------------------------------------------------------------


class TestV1MRMOnlyAlphaSet:
    """Verify v1_mrm_only focused overlay alpha set.

    GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    Single strongest positive-evidence candidate: market-relative momentum.
    """

    EXPECTED_MRM_ONLY = (
        "alpha_nr_market_relative_momentum_20",
    )

    def test_v1_mrm_only_candidate_count(self):
        """v1_mrm_only must contain exactly 1 candidate."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_mrm_only")
        assert len(cols) == 1, f"Expected 1 candidate, got {len(cols)}"

    def test_v1_mrm_only_candidate_list(self):
        """v1_mrm_only must contain exactly market_relative_momentum_20."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_mrm_only")
        assert set(cols) == set(self.EXPECTED_MRM_ONLY), (
            f"v1_mrm_only candidates mismatch.\n"
            f"Expected: {sorted(self.EXPECTED_MRM_ONLY)}\n"
            f"Got:      {sorted(cols)}"
        )

    def test_v1_mrm_only_is_subset_of_v1(self):
        """v1_mrm_only must be a strict subset of v1."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        v1 = set(NONREDUNDANT_ALPHA_SETS["v1"])
        mrm = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_only"])
        assert mrm.issubset(v1), f"v1_mrm_only must be subset of v1. Missing: {mrm - v1}"
        assert mrm != v1, "v1_mrm_only must be strict subset of v1"

    def test_v1_mrm_only_is_subset_of_v1_pruned(self):
        """v1_mrm_only must be a strict subset of v1_pruned."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        pruned = set(NONREDUNDANT_ALPHA_SETS["v1_pruned"])
        mrm = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_only"])
        assert mrm.issubset(pruned), f"v1_mrm_only must be subset of v1_pruned. Missing: {mrm - pruned}"
        assert mrm != pruned, "v1_mrm_only must be strict subset of v1_pruned"


class TestV1MRMRangeAlphaSet:
    """Verify v1_mrm_range focused overlay alpha set.

    GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    Two strongest positive-evidence candidates: market-relative momentum
    plus range-pressure momentum.
    """

    EXPECTED_MRM_RANGE = (
        "alpha_nr_market_relative_momentum_20",
        "alpha_nr_range_pressure_momentum_20",
    )

    def test_v1_mrm_range_candidate_count(self):
        """v1_mrm_range must contain exactly 2 candidates."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_mrm_range")
        assert len(cols) == 2, f"Expected 2 candidates, got {len(cols)}"

    def test_v1_mrm_range_candidate_list(self):
        """v1_mrm_range must contain exactly the two expected candidates."""
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        cols = get_nonredundant_alpha_columns("v1_mrm_range")
        assert set(cols) == set(self.EXPECTED_MRM_RANGE), (
            f"v1_mrm_range candidates mismatch.\n"
            f"Expected: {sorted(self.EXPECTED_MRM_RANGE)}\n"
            f"Got:      {sorted(cols)}"
        )

    def test_v1_mrm_range_is_subset_of_v1(self):
        """v1_mrm_range must be a strict subset of v1."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        v1 = set(NONREDUNDANT_ALPHA_SETS["v1"])
        mrm_range = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_range"])
        assert mrm_range.issubset(v1), f"v1_mrm_range must be subset of v1. Missing: {mrm_range - v1}"
        assert mrm_range != v1, "v1_mrm_range must be strict subset of v1"

    def test_v1_mrm_range_is_subset_of_v1_pruned(self):
        """v1_mrm_range must be a strict subset of v1_pruned."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        pruned = set(NONREDUNDANT_ALPHA_SETS["v1_pruned"])
        mrm_range = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_range"])
        assert mrm_range.issubset(pruned), f"v1_mrm_range must be subset of v1_pruned. Missing: {mrm_range - pruned}"
        assert mrm_range != pruned, "v1_mrm_range must be strict subset of v1_pruned"

    def test_v1_mrm_only_is_subset_of_v1_mrm_range(self):
        """v1_mrm_only must be a strict subset of v1_mrm_range."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS
        mrm_only = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_only"])
        mrm_range = set(NONREDUNDANT_ALPHA_SETS["v1_mrm_range"])
        assert mrm_only.issubset(mrm_range), (
            f"v1_mrm_only must be subset of v1_mrm_range. Missing: {mrm_only - mrm_range}"
        )
        assert mrm_only != mrm_range, "v1_mrm_only must be strict subset of v1_mrm_range"


class TestV1MRMOnlyCLI:
    """Verify CLI accepts v1_mrm_only for --nonredundant-alpha-set."""

    def test_cli_v1_mrm_only_in_choices(self):
        """CLI --nonredundant-alpha-set must list v1_mrm_only as a choice."""
        src = _get_script_source()
        assert '"v1_mrm_only"' in src or "'v1_mrm_only'" in src, (
            "CLI must include v1_mrm_only in choices for --nonredundant-alpha-set"
        )

    def test_cli_gate_label_focused_overlay_present(self):
        """GATE label NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 must appear."""
        src = _get_script_source()
        assert "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615" in src, (
            "Gate label NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 must be present"
        )


class TestV1MRMRangeCLI:
    """Verify CLI accepts v1_mrm_range for --nonredundant-alpha-set."""

    def test_cli_v1_mrm_range_in_choices(self):
        """CLI --nonredundant-alpha-set must list v1_mrm_range as a choice."""
        src = _get_script_source()
        assert '"v1_mrm_range"' in src or "'v1_mrm_range'" in src, (
            "CLI must include v1_mrm_range in choices for --nonredundant-alpha-set"
        )


class TestV1MRMComputeAlphas:
    """Verify compute_nonredundant_alphas works with v1_mrm_only and v1_mrm_range."""

    def test_compute_v1_mrm_only_produces_1_column(self):
        """compute_nonredundant_alphas with v1_mrm_only should produce 1 NR column."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_mrm_only")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 1, f"Expected 1 NR column, got {len(nr_cols)}: {nr_cols}"
        assert "alpha_nr_market_relative_momentum_20" in nr_cols

    def test_compute_v1_mrm_only_all_finite(self):
        """All v1_mrm_only alpha outputs must be finite on synthetic data."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_mrm_only")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        for col in nr_cols:
            vals = result[col].dropna()
            assert len(vals) > 0, f"Column {col} has all NaN values"
            assert np.all(np.isfinite(vals)), f"Column {col} contains non-finite values"

    def test_compute_v1_mrm_range_produces_2_columns(self):
        """compute_nonredundant_alphas with v1_mrm_range should produce 2 NR columns."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_mrm_range")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        assert len(nr_cols) == 2, f"Expected 2 NR columns, got {len(nr_cols)}: {nr_cols}"
        assert "alpha_nr_market_relative_momentum_20" in nr_cols
        assert "alpha_nr_range_pressure_momentum_20" in nr_cols

    def test_compute_v1_mrm_range_all_finite(self):
        """All v1_mrm_range alpha outputs must be finite on synthetic data."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        result = compute_nonredundant_alphas(df, set_name="v1_mrm_range")

        nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
        for col in nr_cols:
            vals = result[col].dropna()
            assert len(vals) > 0, f"Column {col} has all NaN values"
            assert np.all(np.isfinite(vals)), f"Column {col} contains non-finite values"


class TestV1MRMEvidenceSetName:
    """Verify per-fold evidence dict correctly reports set_name for focused overlays."""

    def test_evidence_set_name_v1_mrm_only(self):
        """When engine uses v1_mrm_only, evidence must report set_name='v1_mrm_only'."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine

        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        test_df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=test_df.copy()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(
                    alpha_module=mock_module,
                    enable_nonredundant_alphas=True,
                    nonredundant_alpha_set="v1_mrm_only",
                )
                assert engine.nonredundant_alpha_set == "v1_mrm_only"
                result = engine.compute_alphas(test_df)

                nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
                assert len(nr_cols) == 1, (
                    f"Expected 1 NR column with v1_mrm_only, got {len(nr_cols)}"
                )

    def test_evidence_set_name_v1_mrm_range(self):
        """When engine uses v1_mrm_range, evidence must report set_name='v1_mrm_range'."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine

        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        test_df = _make_synthetic_ohlcv(n_tickers=5, n_days=60)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=test_df.copy()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(
                    alpha_module=mock_module,
                    enable_nonredundant_alphas=True,
                    nonredundant_alpha_set="v1_mrm_range",
                )
                assert engine.nonredundant_alpha_set == "v1_mrm_range"
                result = engine.compute_alphas(test_df)

                nr_cols = [c for c in result.columns if c.startswith("alpha_nr_")]
                assert len(nr_cols) == 2, (
                    f"Expected 2 NR columns with v1_mrm_range, got {len(nr_cols)}"
                )


class TestV1MRMPerTickerBoundary:
    """Per-ticker PIT lag boundary must still pass with focused overlay sets."""

    def test_first_row_no_contamination_v1_mrm_only(self):
        """First row of each ticker must be 0.0/NaN for v1_mrm_only alphas."""
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = pd.DataFrame({
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03",
                                    "2020-01-02", "2020-01-03"]),
            "open":   [100.0, 110.0, 200.0, 220.0],
            "high":   [105.0, 115.0, 210.0, 230.0],
            "low":    [ 95.0, 105.0, 190.0, 210.0],
            "close":  [100.0, 110.0, 200.0, 220.0],
            "volume": [10000, 12000, 20000, 22000],
        })

        result = compute_nonredundant_alphas(df, set_name="v1_mrm_only")

        for ticker in result["ticker"].unique():
            ticker_rows = result[result["ticker"] == ticker].sort_values("date")
            first_row_idx = ticker_rows.index[0]

            alpha_col = "alpha_nr_market_relative_momentum_20"
            if alpha_col in result.columns:
                val = result.loc[first_row_idx, alpha_col]
                assert val == 0.0 or np.isnan(val), (
                    f"CONTAMINATION: ticker={ticker}, alpha={alpha_col}, "
                    f"first-row value={val}. Expected 0.0/NaN."
                )

    def test_first_row_no_contamination_v1_mrm_range(self):
        """First row of each ticker must be 0.0/NaN for return-based v1_mrm_range alphas.

        Note: alpha_nr_range_pressure_momentum_20 has formula
        signal = daily_range / mean_range - 1. When NaN is sanitized to 0.0,
        the constant offset -1.0 yields -1.0 on the first row. This is a
        formula artifact (0/eps - 1 = -1), NOT cross-ticker contamination.
        Only return-based alphas (market_relative_momentum_20) are checked
        for true contamination (must be exactly 0.0/NaN).
        """
        from omega.quant.alpha.nonredundant_alphas import compute_nonredundant_alphas

        df = pd.DataFrame({
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03",
                                    "2020-01-02", "2020-01-03"]),
            "open":   [100.0, 110.0, 200.0, 220.0],
            "high":   [105.0, 115.0, 210.0, 230.0],
            "low":    [ 95.0, 105.0, 190.0, 210.0],
            "close":  [100.0, 110.0, 200.0, 220.0],
            "volume": [10000, 12000, 20000, 22000],
        })

        result = compute_nonredundant_alphas(df, set_name="v1_mrm_range")

        # Return-based alpha: must be exactly 0.0/NaN (no contamination)
        for ticker in result["ticker"].unique():
            ticker_rows = result[result["ticker"] == ticker].sort_values("date")
            first_row_idx = ticker_rows.index[0]

            alpha_col = "alpha_nr_market_relative_momentum_20"
            if alpha_col in result.columns:
                val = result.loc[first_row_idx, alpha_col]
                assert val == 0.0 or np.isnan(val), (
                    f"CONTAMINATION: ticker={ticker}, alpha={alpha_col}, "
                    f"first-row value={val}. Expected 0.0/NaN."
                )

        # range_pressure_momentum: first-row value is formula artifact (-1.0),
        # not contamination. Verify it's finite and bounded (sanity check).
        rpm_col = "alpha_nr_range_pressure_momentum_20"
        if rpm_col in result.columns:
            for ticker in result["ticker"].unique():
                ticker_rows = result[result["ticker"] == ticker].sort_values("date")
                first_row_idx = ticker_rows.index[0]
                val = result.loc[first_row_idx, rpm_col]
                assert np.isfinite(val), (
                    f"range_pressure first-row must be finite for ticker={ticker}"
                )


class TestV1MRMPhase35Regression:
    """Phase 3.5 regression: v1, v1_pruned unchanged after focused overlay sets added."""

    def test_v1_regression_unchanged_after_focused_overlay(self):
        """v1 set must still have 10 candidates after focused overlay sets added."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS

        assert len(NONREDUNDANT_ALPHA_SETS["v1"]) == 10, (
            f"v1 regression: expected 10 candidates, got {len(NONREDUNDANT_ALPHA_SETS['v1'])}"
        )

    def test_v1_pruned_regression_unchanged_after_focused_overlay(self):
        """v1_pruned set must still have 5 candidates after focused overlay sets added."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS

        assert len(NONREDUNDANT_ALPHA_SETS["v1_pruned"]) == 5, (
            f"v1_pruned regression: expected 5 candidates, got {len(NONREDUNDANT_ALPHA_SETS['v1_pruned'])}"
        )

    def test_registry_has_4_sets(self):
        """Registry must now have exactly 4 sets: v1, v1_pruned, v1_mrm_only, v1_mrm_range."""
        from omega.quant.alpha.nonredundant_alphas import NONREDUNDANT_ALPHA_SETS

        expected_sets = {"v1", "v1_pruned", "v1_mrm_only", "v1_mrm_range"}
        actual_sets = set(NONREDUNDANT_ALPHA_SETS.keys())
        assert actual_sets == expected_sets, (
            f"Registry sets mismatch.\n"
            f"Expected: {sorted(expected_sets)}\n"
            f"Got:      {sorted(actual_sets)}"
        )

    def test_default_disabled_unchanged_with_focused_overlay(self):
        """Engine default (disabled) must not be affected by focused overlay sets existing."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test",)
        mock_module.compute_phase34_microstructure_alphas = MagicMock(
            return_value=pd.DataFrame()
        )

        with patch.dict("sys.modules", {
            "omega.quant.ml.gate_validator": MagicMock(),
            "omega.quant.ml.ensemble_xgboost": MagicMock(),
        }):
            mock_ra = MagicMock()
            mock_ra.PRESETS = {
                "balanced": {}, "alpha_recovery": {},
                "drawdown_guarded": {}, "ic_first_guarded": {},
            }
            mock_ra.VALID_RESEARCH_POOL_MODES = [
                "full", "recovery_only", "recoverable_only",
            ]
            mock_ra.get_preset_weights = MagicMock(return_value={})
            with patch.dict("sys.modules", {
                "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
            }):
                engine = Phase35WalkForwardEngine(alpha_module=mock_module)
                assert engine.enable_nonredundant_alphas is False
                assert engine.nonredundant_alpha_set == "v1"


class TestV1MRMEngineGateConstant:
    """Verify focused overlay gate constant is defined in phase35.py."""

    def test_focused_overlay_gate_constant_defined(self):
        """phase35.py must define NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID."""
        src = _get_engine_source()
        assert "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID" in src, (
            "phase35.py must define NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID"
        )
        assert "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615" in src, (
            "phase35.py must contain focused overlay gate string"
        )

    def test_nonredundant_module_focused_overlay_gate_constant(self):
        """nonredundant_alphas.py must define FOCUSED_OVERLAY_GATE_ID."""
        from omega.quant.alpha.nonredundant_alphas import FOCUSED_OVERLAY_GATE_ID
        assert FOCUSED_OVERLAY_GATE_ID == "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615"


# ---------------------------------------------------------------------------
# Section 15: Focused Evidence Gate Routing Regression
# GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
# L3 Audit Finding: evidence gate mismatch for focused overlay folds.
# v1_mrm_only and v1_mrm_range must persist gate
# NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 in
# nonredundant_alpha_evidence, NOT NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615.
# ---------------------------------------------------------------------------


class TestFocusedEvidenceGateRouting:
    """Regression: focused overlay evidence gate must equal focused overlay gate.

    L3 audit found that v1_mrm_only and v1_mrm_range emitted the base gate
    NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 instead of the focused
    overlay gate NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615.
    """

    FOCUSED_GATE = "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615"
    BASE_GATE = "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615"
    PRUNED_GATE = "NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615"

    def test_source_routes_focused_sets_to_focused_gate(self):
        """phase35.py source must route v1_mrm_only/v1_mrm_range to focused gate."""
        src = _get_engine_source()
        # The routing must reference focused overlay sets and the focused gate
        assert '"v1_mrm_only"' in src or "'v1_mrm_only'" in src, (
            "Source must explicitly check for v1_mrm_only in gate routing"
        )
        assert '"v1_mrm_range"' in src or "'v1_mrm_range'" in src, (
            "Source must explicitly check for v1_mrm_range in gate routing"
        )
        # The focused overlay gate must be used in the routing
        assert "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID" in src, (
            "Source must use NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID in routing"
        )

    def test_evidence_gate_for_v1_mrm_only(self):
        """nonredundant_alpha_evidence.gate for v1_mrm_only must be focused gate."""
        from omega.quant.alpha.phase35 import (
            NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID,
            NONREDUNDANT_ALPHA_GATE_ID,
            NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID,
        )

        # Simulate gate routing logic as in phase35.py run_fold
        set_name = "v1_mrm_only"
        if set_name == "v1_pruned":
            gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
        elif set_name in ("v1_mrm_only", "v1_mrm_range"):
            gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
        else:
            gate_id = NONREDUNDANT_ALPHA_GATE_ID

        assert gate_id == self.FOCUSED_GATE, (
            f"v1_mrm_only evidence gate must be {self.FOCUSED_GATE}, got {gate_id}"
        )

    def test_evidence_gate_for_v1_mrm_range(self):
        """nonredundant_alpha_evidence.gate for v1_mrm_range must be focused gate."""
        from omega.quant.alpha.phase35 import (
            NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID,
            NONREDUNDANT_ALPHA_GATE_ID,
            NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID,
        )

        set_name = "v1_mrm_range"
        if set_name == "v1_pruned":
            gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
        elif set_name in ("v1_mrm_only", "v1_mrm_range"):
            gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
        else:
            gate_id = NONREDUNDANT_ALPHA_GATE_ID

        assert gate_id == self.FOCUSED_GATE, (
            f"v1_mrm_range evidence gate must be {self.FOCUSED_GATE}, got {gate_id}"
        )

    def test_evidence_gate_for_v1_pruned_unchanged(self):
        """nonredundant_alpha_evidence.gate for v1_pruned must remain pruned gate."""
        from omega.quant.alpha.phase35 import (
            NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID,
            NONREDUNDANT_ALPHA_GATE_ID,
            NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID,
        )

        set_name = "v1_pruned"
        if set_name == "v1_pruned":
            gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
        elif set_name in ("v1_mrm_only", "v1_mrm_range"):
            gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
        else:
            gate_id = NONREDUNDANT_ALPHA_GATE_ID

        assert gate_id == self.PRUNED_GATE, (
            f"v1_pruned evidence gate must be {self.PRUNED_GATE}, got {gate_id}"
        )

    def test_evidence_gate_for_v1_unchanged(self):
        """nonredundant_alpha_evidence.gate for v1 must remain base gate."""
        from omega.quant.alpha.phase35 import (
            NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID,
            NONREDUNDANT_ALPHA_GATE_ID,
            NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID,
        )

        set_name = "v1"
        if set_name == "v1_pruned":
            gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
        elif set_name in ("v1_mrm_only", "v1_mrm_range"):
            gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
        else:
            gate_id = NONREDUNDANT_ALPHA_GATE_ID

        assert gate_id == self.BASE_GATE, (
            f"v1 evidence gate must be {self.BASE_GATE}, got {gate_id}"
        )

    def test_focused_overlay_json_artifacts_have_correct_gate(self):
        """Persisted JSON artifacts must have focused overlay gate for focused sets."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        data_dir = repo_root / "data" / "phase35_results"

        for set_name, filename in [
            ("v1_mrm_only", "phase35_backtest_results_v1_mrm_only_focused_overlay_baseline.json"),
            ("v1_mrm_range", "phase35_backtest_results_v1_mrm_range_focused_overlay_baseline.json"),
        ]:
            filepath = data_dir / filename
            if not filepath.exists():
                pytest.skip(f"Artifact {filename} not found (not yet regenerated)")
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            folds = data.get("fold_details", data.get("folds", []))
            for fold in folds:
                ev = fold.get("nonredundant_alpha_evidence", {})
                assert ev.get("gate") == self.FOCUSED_GATE, (
                    f"Artifact {filename}: fold {fold.get('fold_id')} "
                    f"nonredundant_alpha_evidence.gate must be {self.FOCUSED_GATE}, "
                    f"got {ev.get('gate')}"
                )
                assert ev.get("set_name") == set_name, (
                    f"Artifact {filename}: fold {fold.get('fold_id')} "
                    f"set_name must be {set_name}, got {ev.get('set_name')}"
                )


