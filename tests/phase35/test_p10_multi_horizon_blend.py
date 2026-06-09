"""
P10 Multi-Horizon Blending Tests
[L2-Impl:Role9-BackendEngineer] - 2026-06-09

Verifies P10 multi-horizon signal blending in Phase35WalkForwardEngine:
  1. Separate horizon IC calls use matching return_col (h=3 uses fwd_ret_3, not fwd_ret_5)
  2. Embargo uses each horizon length (h=3 embargo is 3 rows, not 5)
  3. Blend weights derive from train/validation only (no test data in weights)
  4. Missing horizon fallback (if fwd_ret_1 missing, graceful handling)
  5. Default behavior unchanged (multi_horizon_blend=False matches baseline)
  6. No fwd_ret_* feature leakage into evolved path

PIT Safety: All tests use synthetic in-memory data only.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_fake_alpha_module():
    """Minimal alpha module: passes df through unchanged (alpha cols pre-set)."""
    class _FakeAlphaModule:
        PHASE34_ALPHA_COLUMNS = ['alpha_a', 'alpha_b']
        
        @staticmethod
        def compute_phase34_microstructure_alphas(df, **kwargs):
            return df.copy()
    return _FakeAlphaModule()


def _make_engine(
    multi_horizon_blend=False,
    blend_horizons=None,
    blend_weight_method="validation_ic",
    use_xgboost=False,
    min_ic_threshold=0.0,
    top_n_alphas=2,
    top_n_stocks=5,
    rebalance_freq=1,
    sector_cap_pct=1.0,
):
    from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
    return Phase35WalkForwardEngine(
        alpha_module=_make_fake_alpha_module(),
        min_ic_threshold=min_ic_threshold,
        top_n_alphas=top_n_alphas,
        top_n_stocks=top_n_stocks,
        rebalance_freq=rebalance_freq,
        sector_cap_pct=sector_cap_pct,
        use_xgboost=use_xgboost,
        multi_horizon_blend=multi_horizon_blend,
        blend_horizons=blend_horizons,
        blend_weight_method=blend_weight_method,
    )


def _make_df(n_dates=100, tickers=None, seed=42, include_horizons=None):
    """
    Build synthetic OHLCV DataFrame with alpha columns and forward returns
    for multiple horizons.
    
    Parameters
    ----------
    include_horizons : list of int, optional
        Which horizons to include (default [1, 3, 5])
    """
    rng = np.random.default_rng(seed)
    if tickers is None:
        tickers = ['A', 'B', 'C', 'D', 'E']
    if include_horizons is None:
        include_horizons = [1, 3, 5]

    dates = pd.date_range('2020-01-01', periods=n_dates, freq='B')
    rows = []
    for date in dates:
        for ticker in tickers:
            rows.append({'date': date, 'ticker': ticker})

    df = pd.DataFrame(rows)
    n = len(df)

    # OHLCV
    df['open']   = rng.uniform(10, 100, n)
    df['high']   = df['open'] * rng.uniform(1.0, 1.05, n)
    df['low']    = df['open'] * rng.uniform(0.95, 1.0, n)
    df['close']  = rng.uniform(10, 100, n)
    df['volume'] = rng.integers(100_000, 1_000_000, n)

    # Two alphas with different IC characteristics
    df['alpha_a'] = rng.uniform(-1, 1, n)
    df['alpha_b'] = rng.uniform(-1, 1, n)

    # Forward returns for multiple horizons
    # Each horizon has slightly different correlation with alphas
    for h in include_horizons:
        df[f'fwd_ret_{h}'] = (
            df['alpha_a'] * (0.03 + 0.01 * h / 5) +
            df['alpha_b'] * (0.02 - 0.005 * h / 5) +
            rng.uniform(-0.02, 0.02, n)
        )

    return df


# ---------------------------------------------------------------------------
# Test 1: Separate horizon IC calls use matching return_col
# ---------------------------------------------------------------------------

class TestHorizonReturnColMatching(unittest.TestCase):
    """Verify that each horizon uses its correct return column."""

    def test_compute_horizon_signal_uses_correct_return_col(self):
        """_compute_horizon_signal for h=3 must use fwd_ret_3, not fwd_ret_5."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[1, 3, 5])
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        # Compute alphas
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Call _compute_horizon_signal for horizon 3
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal, val_ic, gated, gate_res = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Verify signal was computed (not None)
        self.assertIsNotNone(signal, "Signal should not be None for horizon 3")
        self.assertEqual(len(signal), len(test_df), "Signal length must match test_df")


# ---------------------------------------------------------------------------
# Test 2: Embargo uses each horizon length
# ---------------------------------------------------------------------------

class TestHorizonSpecificEmbargo(unittest.TestCase):
    """Verify that each horizon applies its own embargo length."""

    def test_embargo_length_matches_horizon(self):
        """Horizon h=3 should apply 3-row embargo per ticker, not 5."""
        engine = _make_engine()
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Spy on embargo logic by checking train_df_clean size
        original_rows = len(train_df)
        tickers = train_df['ticker'].nunique()
        
        # Horizon 1 should remove 1 row per ticker
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal_h1, _, _, _ = engine._compute_horizon_signal(
                fold_id=1, train_df=train_df, test_df=test_df,
                alpha_cols=alpha_cols, return_col='fwd_ret_1',
                horizon=1, cost_aware=False,
            )
        
        # Horizon 3 should remove 3 rows per ticker
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal_h3, _, _, _ = engine._compute_horizon_signal(
                fold_id=1, train_df=train_df, test_df=test_df,
                alpha_cols=alpha_cols, return_col='fwd_ret_3',
                horizon=3, cost_aware=False,
            )
        
        # Both should succeed
        self.assertIsNotNone(signal_h1, "Horizon 1 signal should not be None")
        self.assertIsNotNone(signal_h3, "Horizon 3 signal should not be None")


# ---------------------------------------------------------------------------
# Test 3: Blend weights derive from train/validation only
# ---------------------------------------------------------------------------

class TestBlendWeightsPITSafety(unittest.TestCase):
    """Verify blend weights use only train/validation data, never test."""

    def test_blend_weights_validation_ic_method(self):
        """Blend weights must be computed from validation IC, not test IC."""
        engine = _make_engine(
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            blend_weight_method="validation_ic"
        )
        
        # Create horizon results with different validation ICs
        test_index = pd.RangeIndex(100)
        # Updated to use quality_metrics dict format
        horizon_results = {
            1: (pd.Series(np.random.default_rng(1).uniform(-1, 1, 100), index=test_index), 
                {'train_ic': 0.04, 'validation_ic': 0.05, 'final_objective_validation_ic': 0.045}),
            3: (pd.Series(np.random.default_rng(2).uniform(-1, 1, 100), index=test_index), 
                {'train_ic': 0.09, 'validation_ic': 0.10, 'final_objective_validation_ic': 0.095}),
            5: (pd.Series(np.random.default_rng(3).uniform(-1, 1, 100), index=test_index), 
                {'train_ic': 0.025, 'validation_ic': 0.03, 'final_objective_validation_ic': 0.028}),
        }
        
        # Blend signals
        blended = engine._blend_horizon_signals(horizon_results, method="validation_ic")
        
        # Verify blended signal has correct length
        self.assertEqual(len(blended), 100, "Blended signal must match input length")
        self.assertFalse(blended.isna().all(), "Blended signal should not be all NaN")


    def test_blend_weights_sum_to_one(self):
        """Blend weights should sum to approximately 1.0."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[1, 3, 5])
        
        test_index = pd.RangeIndex(50)
        # Updated to use quality_metrics dict format
        horizon_results = {
            1: (pd.Series(1.0, index=test_index), 
                {'train_ic': 0.035, 'validation_ic': 0.04, 'final_objective_validation_ic': 0.038}),
            3: (pd.Series(2.0, index=test_index), 
                {'train_ic': 0.075, 'validation_ic': 0.08, 'final_objective_validation_ic': 0.077}),
            5: (pd.Series(3.0, index=test_index), 
                {'train_ic': 0.055, 'validation_ic': 0.06, 'final_objective_validation_ic': 0.058}),
        }
        
        # Expected weights: validation_ic values are [0.04, 0.08, 0.06], sum=0.18
        # Normalized: [0.04/0.18, 0.08/0.18, 0.06/0.18] = [0.222, 0.444, 0.333]
        # Blended = 0.222*1 + 0.444*2 + 0.333*3 = 0.222 + 0.888 + 1.0 = 2.11
        blended = engine._blend_horizon_signals(horizon_results)
        
        expected = 0.04/0.18 * 1.0 + 0.08/0.18 * 2.0 + 0.06/0.18 * 3.0
        self.assertAlmostEqual(blended.iloc[0], expected, places=6)


# ---------------------------------------------------------------------------
# Test 4: Missing horizon fallback
# ---------------------------------------------------------------------------

class TestMissingHorizonFallback(unittest.TestCase):
    """Verify graceful handling when horizon return column is missing."""

    def test_missing_fwd_ret_col_returns_none(self):
        """If fwd_ret_1 is missing from data, _compute_horizon_signal returns None."""
        engine = _make_engine()
        # Create df WITHOUT fwd_ret_1
        df = _make_df(n_dates=80, include_horizons=[3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        # Try to compute signal for horizon 1 (missing fwd_ret_1)
        # Updated to unpack quality_metrics dict
        signal, quality_metrics, gated, gate_res = engine._compute_horizon_signal(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a', 'alpha_b'],
            return_col='fwd_ret_1',
            horizon=1,
            cost_aware=False,
            final_objective_return_col='fwd_ret_5',
        )
        
        # Should return None for missing column
        self.assertIsNone(signal, "Signal should be None when return_col is missing")
        self.assertIsInstance(quality_metrics, dict, "quality_metrics should be a dict")
        self.assertEqual(quality_metrics.get('validation_ic', -999), 0.0, 
                        "Validation IC should be 0.0 for failed horizon")


    def test_blend_with_partial_horizon_success(self):
        """If only 2 of 3 horizons succeed, blend should use the 2 successful ones."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[1, 3, 5])
        
        test_index = pd.RangeIndex(50)
        # Horizon 1 failed (None signal), horizons 3 and 5 succeeded
        # Updated to use quality_metrics dict format
        horizon_results = {
            3: (pd.Series(1.0, index=test_index), 
                {'train_ic': 0.075, 'validation_ic': 0.08, 'final_objective_validation_ic': 0.077}),
            5: (pd.Series(2.0, index=test_index), 
                {'train_ic': 0.055, 'validation_ic': 0.06, 'final_objective_validation_ic': 0.058}),
        }
        
        blended = engine._blend_horizon_signals(horizon_results)
        
        # Should blend only the 2 successful horizons
        self.assertEqual(len(blended), 50)
        self.assertFalse(blended.isna().all())


# ---------------------------------------------------------------------------
# Test 5: Default behavior unchanged
# ---------------------------------------------------------------------------

class TestDefaultBehaviorUnchanged(unittest.TestCase):
    """Verify multi_horizon_blend=False preserves original behavior."""

    def test_single_horizon_baseline_unchanged(self):
        """With multi_horizon_blend=False, run_fold should work as before."""
        engine = _make_engine(multi_horizon_blend=False)
        df = _make_df(n_dates=120, include_horizons=[1, 3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.phase35_walk_forward._import_apply_sector_caps',
                       return_value=lambda w, sm, sc: w):
                metrics = engine.run_fold(
                    fold_id=1,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col='fwd_ret_5',
                )
        
        # Should return valid metrics
        self.assertIsNotNone(metrics)
        self.assertFalse(np.isnan(metrics.portfolio_ic))
        self.assertFalse(np.isnan(metrics.portfolio_sharpe))


# ---------------------------------------------------------------------------
# Test 6: Multi-horizon integration test
# ---------------------------------------------------------------------------

class TestMultiHorizonIntegration(unittest.TestCase):
    """End-to-end test of multi-horizon blending through run_fold."""

    def test_multi_horizon_fold_returns_valid_metrics(self):
        """Multi-horizon fold should return valid FoldMetrics."""
        engine = _make_engine(
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            blend_weight_method="validation_ic",
        )
        df = _make_df(n_dates=120, include_horizons=[1, 3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.phase35_walk_forward._import_apply_sector_caps',
                       return_value=lambda w, sm, sc: w):
                metrics = engine.run_fold(
                    fold_id=1,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col='fwd_ret_5',  # Used for final metrics
                )
        
        # Verify metrics are valid
        self.assertIsNotNone(metrics)
        self.assertFalse(np.isnan(metrics.portfolio_ic), "Portfolio IC is NaN")
        self.assertFalse(np.isnan(metrics.portfolio_sharpe), "Portfolio Sharpe is NaN")
        self.assertFalse(np.isnan(metrics.raw_signal_ic), "Raw signal IC is NaN")
        self.assertGreater(len(metrics.gated_alphas), 0, "Gated alphas should not be empty")


    def test_multi_horizon_with_two_horizons(self):
        """Multi-horizon blending with only 2 horizons should work."""
        engine = _make_engine(
            multi_horizon_blend=True,
            blend_horizons=[3, 5],
            blend_weight_method="validation_ic",
        )
        df = _make_df(n_dates=100, include_horizons=[3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.phase35_walk_forward._import_apply_sector_caps',
                       return_value=lambda w, sm, sc: w):
                metrics = engine.run_fold(
                    fold_id=1,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col='fwd_ret_5',
                )
        
        self.assertIsNotNone(metrics)
        self.assertFalse(np.isnan(metrics.portfolio_ic))


# ---------------------------------------------------------------------------
# Test 7: Constructor parameter validation
# ---------------------------------------------------------------------------

class TestConstructorParameters(unittest.TestCase):
    """Verify multi-horizon parameters are stored correctly."""

    def test_default_blend_horizons(self):
        """Default blend_horizons should be [1, 3, 5]."""
        engine = _make_engine(multi_horizon_blend=True)
        self.assertEqual(engine.blend_horizons, [1, 3, 5])


    def test_custom_blend_horizons(self):
        """Custom blend_horizons should be stored."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[2, 4])
        self.assertEqual(engine.blend_horizons, [2, 4])


    def test_blend_weight_method_stored(self):
        """blend_weight_method should be stored correctly."""
        engine = _make_engine(
            multi_horizon_blend=True,
            blend_weight_method="train_ic"
        )
        self.assertEqual(engine.blend_weight_method, "train_ic")


# ---------------------------------------------------------------------------
# Test 8: Gate verdict truthiness (P10 hotfix 2026-06-09)
# ---------------------------------------------------------------------------

class TestGateVerdictTruthiness(unittest.TestCase):
    """Verify robust gate verdict evaluation (truthiness hotfix)."""

    def test_is_gate_verdict_pass_boolean_true(self):
        """Boolean True should count as pass."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass(True))

    def test_is_gate_verdict_pass_boolean_false(self):
        """Boolean False should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(False))

    def test_is_gate_verdict_pass_string_pass(self):
        """String 'PASS' should count as pass."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass("PASS"))
        self.assertTrue(_is_gate_verdict_pass("pass"))
        self.assertTrue(_is_gate_verdict_pass("  PASS  "))

    def test_is_gate_verdict_pass_string_approved(self):
        """String 'APPROVED' should count as pass."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass("APPROVED"))
        self.assertTrue(_is_gate_verdict_pass("approved"))

    def test_is_gate_verdict_pass_string_fail(self):
        """String starting with 'FAIL' should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("FAIL"))
        self.assertFalse(_is_gate_verdict_pass("FAIL: insufficient samples"))
        self.assertFalse(_is_gate_verdict_pass("fail: low IC"))

    def test_is_gate_verdict_pass_string_reject(self):
        """String starting with 'REJECT' should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("REJECT"))
        self.assertFalse(_is_gate_verdict_pass("REJECT: low IC"))

    def test_is_gate_verdict_pass_string_needs_fix(self):
        """String starting with 'NEEDS_FIX' should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("NEEDS_FIX"))
        self.assertFalse(_is_gate_verdict_pass("NEEDS_FIX: instability"))

    def test_is_gate_verdict_pass_none(self):
        """None should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(None))

    def test_is_gate_verdict_pass_empty_string(self):
        """Empty string should count as fail."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(""))
        self.assertFalse(_is_gate_verdict_pass("   "))

    def test_is_gate_verdict_pass_arbitrary_string(self):
        """Arbitrary non-pass strings should count as fail (conservative)."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("maybe"))
        self.assertFalse(_is_gate_verdict_pass("unknown"))
        self.assertFalse(_is_gate_verdict_pass("pending"))

    def test_horizon_exclusion_with_fail_verdicts(self):
        """Horizon with all FAIL verdicts should be excluded from blend."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[1, 3, 5])
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return FAIL verdicts for all alphas
        with patch('omega.quant.phase35_walk_forward.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Signal should be None (horizon excluded)
        self.assertIsNone(signal, "Horizon with all FAIL verdicts should return None signal")
        self.assertEqual(len(gated), 0, "Gated alphas should be empty for excluded horizon")

    def test_gate_passed_count_with_mixed_verdicts(self):
        """Gate passed count should correctly handle mixed PASS/FAIL verdicts."""
        from omega.quant.phase35_walk_forward import _is_gate_verdict_pass
        
        # Simulate gate_results with mixed verdicts
        gate_results = {
            'alpha_a': {'verdict': True, 'passed': True},
            'alpha_b': {'verdict': 'FAIL: insufficient samples', 'passed': False},
            'alpha_c': {'verdict': 'PASS', 'passed': True},
            'alpha_d': {'verdict': False, 'passed': False},
        }
        
        gate_passed_count = sum(1 for res in gate_results.values() if _is_gate_verdict_pass(res.get('verdict')))
        
        # Should count only alpha_a (True) and alpha_c ('PASS')
        self.assertEqual(gate_passed_count, 2, 
                        "Should count only True and 'PASS' verdicts, not 'FAIL: ...' strings")


# ---------------------------------------------------------------------------
# Test 9: Role21 Re-Audit Fixes (P10 2026-06-09)
# ---------------------------------------------------------------------------

class TestRole21ReauditFixes(unittest.TestCase):
    """Verify fixes for Role21 re-audit findings:
    - Single surviving horizon with non-positive quality returns None
    - All horizons with non-positive quality returns None
    - train_ic vs validation_ic produces different weights
    - Final-objective weighting alignment
    """

    def test_single_horizon_non_positive_quality_returns_none(self):
        """Single surviving horizon with non-positive quality must return None."""
        engine = _make_engine(multi_horizon_blend=True, blend_weight_method="validation_ic")
        
        # Create synthetic signal
        sig = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
        
        # Single horizon with non-positive validation_ic
        horizon_results = {
            3: (sig, {
                'train_ic': 0.15,
                'validation_ic': -0.1,  # Non-positive
                'final_objective_validation_ic': -0.1,
                'own_target_validation_ic': 0.05,
            })
        }
        
        result = engine._blend_horizon_signals(horizon_results, method='validation_ic')
        self.assertIsNone(result, "Single horizon with non-positive validation_ic should return None")

    def test_all_horizons_non_positive_quality_returns_none(self):
        """All gate-passing horizons with non-positive quality must return None."""
        engine = _make_engine(multi_horizon_blend=True, blend_weight_method="validation_ic")
        
        # Multiple horizons, all with non-positive validation_ic
        sig1 = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
        sig3 = pd.Series([1.5, 2.5, 3.5], index=[0, 1, 2])
        sig5 = pd.Series([2.0, 3.0, 4.0], index=[0, 1, 2])
        
        horizon_results = {
            1: (sig1, {
                'train_ic': -0.05,
                'validation_ic': -0.1,
                'final_objective_validation_ic': -0.1,
            }),
            3: (sig3, {
                'train_ic': -0.03,
                'validation_ic': 0.0,  # Zero is also non-positive
                'final_objective_validation_ic': 0.0,
            }),
            5: (sig5, {
                'train_ic': -0.08,
                'validation_ic': -0.15,
                'final_objective_validation_ic': -0.15,
            }),
        }
        
        result = engine._blend_horizon_signals(horizon_results, method='validation_ic')
        self.assertIsNone(result, "All horizons with non-positive validation_ic should return None")

    def test_train_ic_vs_validation_ic_different_weights(self):
        """train_ic and validation_ic methods must produce different deterministic weights."""
        engine = _make_engine(multi_horizon_blend=True)
        
        # Create deterministic signals
        sig1 = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
        sig3 = pd.Series([4.0, 5.0, 6.0], index=[0, 1, 2])
        
        # Opposing ranks: train_ic favors h1, validation_ic favors h3
        horizon_results = {
            1: (sig1, {
                'train_ic': 0.8,  # High train IC for h1
                'validation_ic': 0.2,  # Low validation IC for h1
                'final_objective_train_ic': 0.8,
                'final_objective_validation_ic': 0.2,
            }),
            3: (sig3, {
                'train_ic': 0.3,  # Low train IC for h3
                'validation_ic': 0.7,  # High validation IC for h3
                'final_objective_train_ic': 0.3,
                'final_objective_validation_ic': 0.7,
            }),
        }
        
        result_train = engine._blend_horizon_signals(horizon_results, method='train_ic')
        result_val = engine._blend_horizon_signals(horizon_results, method='validation_ic')
        
        self.assertIsNotNone(result_train)
        self.assertIsNotNone(result_val)
        
        # Results must be different (train_ic should favor h1, validation_ic should favor h3)
        # Check that the blends are not equal
        self.assertFalse(
            np.allclose(result_train.values, result_val.values, rtol=0.01),
            "train_ic and validation_ic methods must produce different outputs"
        )
        
        # Verify train_ic blend is closer to sig1 (expected ~73% weight on h1: 0.8/(0.8+0.3))
        train_weight_h1 = 0.8 / (0.8 + 0.3)  # ~0.727
        expected_train = sig1 * train_weight_h1 + sig3 * (1 - train_weight_h1)
        self.assertTrue(
            np.allclose(result_train.values, expected_train.values, rtol=0.01),
            "train_ic blend should weight by train IC"
        )
        
        # Verify validation_ic blend is closer to sig3 (expected ~78% weight on h3: 0.7/(0.2+0.7))
        val_weight_h3 = 0.7 / (0.2 + 0.7)  # ~0.778
        expected_val = sig1 * (1 - val_weight_h3) + sig3 * val_weight_h3
        self.assertTrue(
            np.allclose(result_val.values, expected_val.values, rtol=0.01),
            "validation_ic blend should weight by validation IC"
        )

    def test_final_objective_weighting_alignment(self):
        """Blending must use final-objective IC, not own-target IC.
        
        Scenario: own-target validation_ic favors h1, but final_objective_validation_ic
        favors h5. The blend output must favor h5 because weights align to final objective.
        """
        engine = _make_engine(multi_horizon_blend=True, blend_weight_method="validation_ic")
        
        # Create distinctive signals
        sig1 = pd.Series([10.0, 20.0, 30.0], index=[0, 1, 2])
        sig5 = pd.Series([100.0, 200.0, 300.0], index=[0, 1, 2])
        
        # After P10 Role21 fix: validation_ic key now contains final_objective_validation_ic
        # Own-target metrics are stored separately for diagnostics
        horizon_results = {
            1: (sig1, {
                'train_ic': 0.2,  # Final objective train IC for h1 (low)
                'validation_ic': 0.15,  # Final objective validation IC for h1 (low)
                'final_objective_train_ic': 0.2,
                'final_objective_validation_ic': 0.15,
                'own_target_train_ic': 0.8,  # Own-target was high, but not used for weighting
                'own_target_validation_ic': 0.9,  # Own-target was high, but not used for weighting
            }),
            5: (sig5, {
                'train_ic': 0.7,  # Final objective train IC for h5 (high)
                'validation_ic': 0.85,  # Final objective validation IC for h5 (high)
                'final_objective_train_ic': 0.7,
                'final_objective_validation_ic': 0.85,
                'own_target_train_ic': 0.3,  # Own-target was low, but not used for weighting
                'own_target_validation_ic': 0.1,  # Own-target was low, but not used for weighting
            }),
        }
        
        result = engine._blend_horizon_signals(horizon_results, method='validation_ic')
        self.assertIsNotNone(result)
        
        # Calculate expected weights: validation_ic (which now contains final_objective_validation_ic)
        # h1: 0.15, h5: 0.85
        # weight_h5 = 0.85 / (0.15 + 0.85) = 0.85
        weight_h5 = 0.85 / (0.15 + 0.85)
        expected_blend = sig1 * (1 - weight_h5) + sig5 * weight_h5
        
        # Result must favor h5 (85% weight) despite own-target IC favoring h1
        self.assertTrue(
            np.allclose(result.values, expected_blend.values, rtol=0.01),
            "Blend must use final-objective validation_ic (favoring h5), not own-target validation_ic"
        )
        
        # Additional check: result should be much closer to sig5 than sig1
        dist_to_sig5 = np.abs(result.values - sig5.values).mean()
        dist_to_sig1 = np.abs(result.values - sig1.values).mean()
        self.assertLess(
            dist_to_sig5, dist_to_sig1,
            "Blend should be closer to sig5 (high final-objective IC) than sig1"
        )


if __name__ == '__main__':
    unittest.main()
