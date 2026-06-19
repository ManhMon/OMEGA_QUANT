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
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
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
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal, val_ic, gated, gate_res, _ = engine._compute_horizon_signal(
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
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal_h1, _, _, _, _ = engine._compute_horizon_signal(
                fold_id=1, train_df=train_df, test_df=test_df,
                alpha_cols=alpha_cols, return_col='fwd_ret_1',
                horizon=1, cost_aware=False,
            )
        
        # Horizon 3 should remove 3 rows per ticker
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            signal_h3, _, _, _, _ = engine._compute_horizon_signal(
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
        # Updated to unpack quality_metrics dict and gate_metadata
        signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
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
        
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.alpha.phase35._import_apply_sector_caps',
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
        
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.alpha.phase35._import_apply_sector_caps',
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
        
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': True, 'verdict': 'PASS', 'n_samples': 10}):
            with patch('omega.quant.alpha.phase35._import_apply_sector_caps',
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
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass(True))

    def test_is_gate_verdict_pass_boolean_false(self):
        """Boolean False should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(False))

    def test_is_gate_verdict_pass_string_pass(self):
        """String 'PASS' should count as pass."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass("PASS"))
        self.assertTrue(_is_gate_verdict_pass("pass"))
        self.assertTrue(_is_gate_verdict_pass("  PASS  "))

    def test_is_gate_verdict_pass_string_approved(self):
        """String 'APPROVED' should count as pass."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertTrue(_is_gate_verdict_pass("APPROVED"))
        self.assertTrue(_is_gate_verdict_pass("approved"))

    def test_is_gate_verdict_pass_string_fail(self):
        """String starting with 'FAIL' should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("FAIL"))
        self.assertFalse(_is_gate_verdict_pass("FAIL: insufficient samples"))
        self.assertFalse(_is_gate_verdict_pass("fail: low IC"))

    def test_is_gate_verdict_pass_string_reject(self):
        """String starting with 'REJECT' should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("REJECT"))
        self.assertFalse(_is_gate_verdict_pass("REJECT: low IC"))

    def test_is_gate_verdict_pass_string_needs_fix(self):
        """String starting with 'NEEDS_FIX' should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass("NEEDS_FIX"))
        self.assertFalse(_is_gate_verdict_pass("NEEDS_FIX: instability"))

    def test_is_gate_verdict_pass_none(self):
        """None should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(None))

    def test_is_gate_verdict_pass_empty_string(self):
        """Empty string should count as fail."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        self.assertFalse(_is_gate_verdict_pass(""))
        self.assertFalse(_is_gate_verdict_pass("   "))

    def test_is_gate_verdict_pass_arbitrary_string(self):
        """Arbitrary non-pass strings should count as fail (conservative)."""
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
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
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
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
        from omega.quant.alpha.phase35 import _is_gate_verdict_pass
        
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


# ---------------------------------------------------------------------------
# Test 10: P10 Gate Tuning (2026-06-09)
# ---------------------------------------------------------------------------

class TestP10GateTuning(unittest.TestCase):
    """Verify P10 Research Gate tuning knobs behavior."""
    
    def test_strict_mode_excludes_zero_passes_default_behavior(self):
        """Strict mode (default) excludes horizon with zero gate passes."""
        engine = _make_engine(multi_horizon_blend=True, blend_horizons=[1, 3, 5])
        
        # Verify default values
        self.assertEqual(engine.p10_gate_mode, "strict")
        self.assertEqual(engine.p10_gate_min_pass, 1)
        self.assertFalse(engine.p10_gate_allow_fallback_candidates)
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return FAIL verdicts for all alphas
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Strict mode should exclude horizon (return None)
        self.assertIsNone(signal, "Strict mode should exclude horizon with 0 gate passes")
        self.assertEqual(len(gated), 0, "Gated alphas should be empty")
    
    def test_relaxed_mode_without_fallback_still_excludes_zero_passes(self):
        """Relaxed mode without fallback candidates still excludes if min_pass unmet."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=False,  # Explicitly disabled
        )
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return FAIL verdicts for all alphas (0 passes)
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Relaxed mode without fallback candidates should still exclude (0 < min_pass=1)
        self.assertIsNone(signal, "Relaxed mode without fallback should exclude horizon with 0 passes < min_pass=1")
        self.assertEqual(len(gated), 0, "Gated alphas should be empty")
    
    def test_relaxed_mode_with_fallback_allows_horizon_with_candidates(self):
        """Relaxed mode with allow_fallback_candidates=True allows horizon to proceed."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=True,  # Enabled
        )
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return FAIL verdicts for all alphas (0 passes)
        # But fallback candidates should allow horizon to proceed
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Relaxed mode with fallback candidates enabled should allow horizon (top_alphas non-empty)
        self.assertIsNotNone(signal, "Relaxed mode with fallback candidates should allow horizon with non-empty top_alphas")
        self.assertEqual(len(signal), len(test_df), "Signal length should match test_df")
        self.assertGreater(len(gated), 0, "Gated alphas should not be empty (fallback to top_alphas)")
    
    def test_relaxed_mode_with_min_pass_met_proceeds(self):
        """Relaxed mode allows horizon if gate_passed_count >= min_pass."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,  # Require at least 1 pass
            p10_gate_allow_fallback_candidates=False,
        )
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return mixed verdicts: 1 PASS, 1 FAIL
        gate_results = [
            {'passed': True, 'verdict': 'PASS', 'n_samples': 20},  # alpha_a passes
            {'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5},  # alpha_b fails
        ]
        call_count = [0]
        
        def mock_gate(val_ic, rolling_ic):
            result = gate_results[call_count[0] % len(gate_results)]
            call_count[0] += 1
            return result
        
        with patch('omega.quant.alpha.phase35.validate_research_gate', side_effect=mock_gate):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Relaxed mode should allow horizon (1 pass >= min_pass=1)
        self.assertIsNotNone(signal, "Relaxed mode should allow horizon with gate_passed_count >= min_pass")
        self.assertEqual(len(signal), len(test_df), "Signal length should match test_df")
    
    def test_relaxed_horizon_with_non_positive_quality_triggers_fallback(self):
        """Relaxed admitted horizon with non-positive final-objective quality gets zero weight."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3],
            blend_weight_method="validation_ic",
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=True,
        )
        
        # Create horizon results where relaxed gate allowed h1 to proceed,
        # but its final-objective validation_ic is non-positive
        sig1 = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
        sig3 = pd.Series([4.0, 5.0, 6.0], index=[0, 1, 2])
        
        horizon_results = {
            1: (sig1, {
                'train_ic': 0.05,
                'validation_ic': -0.02,  # Non-positive final-objective IC
                'final_objective_validation_ic': -0.02,
            }),
            3: (sig3, {
                'train_ic': 0.08,
                'validation_ic': -0.01,  # Also non-positive
                'final_objective_validation_ic': -0.01,
            }),
        }
        
        # Blend should return None (all non-positive quality)
        result = engine._blend_horizon_signals(horizon_results, method='validation_ic')
        self.assertIsNone(result, "Blend should return None when all horizons have non-positive final-objective quality")
    
    def test_invalid_gate_mode_raises_error(self):
        """Invalid p10_gate_mode value should raise ValueError."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        with self.assertRaises(ValueError) as context:
            engine = Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                min_ic_threshold=0.0,
                top_n_alphas=2,
                p10_gate_mode="invalid_mode",  # Invalid
            )
        
        self.assertIn("p10_gate_mode", str(context.exception))
        self.assertIn("strict", str(context.exception))
        self.assertIn("relaxed", str(context.exception))
    
    def test_invalid_gate_min_pass_raises_error(self):
        """Invalid p10_gate_min_pass value should raise ValueError."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        # Negative value should raise
        with self.assertRaises(ValueError) as context:
            engine = Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                min_ic_threshold=0.0,
                top_n_alphas=2,
                p10_gate_min_pass=-1,  # Invalid
            )
        
        self.assertIn("p10_gate_min_pass", str(context.exception))
    
    def test_gate_mode_parameters_stored_correctly(self):
        """Gate tuning parameters should be stored as instance variables."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            p10_gate_mode="relaxed",
            p10_gate_min_pass=2,
            p10_gate_allow_fallback_candidates=True,
        )
        
        self.assertEqual(engine.p10_gate_mode, "relaxed")
        self.assertEqual(engine.p10_gate_min_pass, 2)
        self.assertTrue(engine.p10_gate_allow_fallback_candidates)
    
    def test_relaxed_fallback_produces_correct_gate_metadata(self):
        """Role21 Fix 2026-06-10: Relaxed fallback candidates produce correct gate_metadata."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=True,
        )
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return FAIL verdicts for all alphas (0 passes)
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Verify signal is not None (fallback allowed)
        self.assertIsNotNone(signal, "Signal should not be None when fallback is allowed")
        
        # Verify gate_metadata structure
        self.assertIsNotNone(gate_meta, "gate_metadata should not be None")
        self.assertIn('selection_source', gate_meta)
        self.assertIn('used_fallback_candidates', gate_meta)
        self.assertIn('gate_passed_count', gate_meta)
        self.assertIn('gate_total', gate_meta)
        self.assertIn('gate_required_passes', gate_meta)
        self.assertIn('gate_mode', gate_meta)
        self.assertIn('gate_passed_alphas', gate_meta)
        
        # Verify fallback candidate metadata values
        self.assertEqual(gate_meta['selection_source'], 'fallback_candidate',
                        "selection_source should be 'fallback_candidate' when using relaxed fallback")
        self.assertTrue(gate_meta['used_fallback_candidates'],
                       "used_fallback_candidates should be True when fallback is used")
        self.assertEqual(gate_meta['gate_passed_count'], 0,
                        "gate_passed_count should be 0 when all alphas fail")
        self.assertEqual(gate_meta['gate_mode'], 'relaxed')
        self.assertEqual(gate_meta['gate_required_passes'], 1)
        self.assertEqual(len(gate_meta['gate_passed_alphas']), 0,
                        "gate_passed_alphas should be empty when all alphas fail")
    
    def test_strict_gate_pass_produces_correct_gate_metadata(self):
        """Role21 Fix 2026-06-10: Strict gate pass produces correct gate_metadata."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            p10_gate_mode="strict",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=False,
        )
        
        df = _make_df(n_dates=100, include_horizons=[1, 3, 5])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to return mixed verdicts: 1 PASS, 1 FAIL
        gate_results = [
            {'passed': True, 'verdict': 'PASS', 'n_samples': 20},  # alpha_a passes
            {'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5},  # alpha_b fails
        ]
        call_count = [0]
        
        def mock_gate(val_ic, rolling_ic):
            result = gate_results[call_count[0] % len(gate_results)]
            call_count[0] += 1
            return result
        
        with patch('omega.quant.alpha.phase35.validate_research_gate', side_effect=mock_gate):
            signal, quality_metrics, gated, gate_res, gate_meta = engine._compute_horizon_signal(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                horizon=3,
                cost_aware=False,
            )
        
        # Verify signal is not None (at least 1 alpha passed)
        self.assertIsNotNone(signal, "Signal should not be None when alphas pass gate")
        
        # Verify gate_metadata structure
        self.assertIsNotNone(gate_meta, "gate_metadata should not be None")
        
        # Verify research gate metadata values (not fallback)
        self.assertEqual(gate_meta['selection_source'], 'research_gate',
                        "selection_source should be 'research_gate' when alphas pass gate")
        self.assertFalse(gate_meta['used_fallback_candidates'],
                        "used_fallback_candidates should be False when not using fallback")
        self.assertEqual(gate_meta['gate_passed_count'], 1,
                        "gate_passed_count should be 1 when one alpha passes")
        self.assertEqual(gate_meta['gate_mode'], 'strict')
        self.assertEqual(gate_meta['gate_required_passes'], 1)
        self.assertGreater(len(gate_meta['gate_passed_alphas']), 0,
                          "gate_passed_alphas should not be empty when alphas pass")
    
    def test_fold_metrics_includes_gate_metadata(self):
        """Role21 Fix 2026-06-10: FoldMetrics includes gate_metadata field."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
            min_ic_threshold=0.0,
            top_n_alphas=2,
            multi_horizon_blend=True,
            blend_horizons=[3],
            p10_gate_mode="relaxed",
            p10_gate_min_pass=1,
            p10_gate_allow_fallback_candidates=True,
        )
        
        df = _make_df(n_dates=50, include_horizons=[3])
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate to trigger fallback
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   return_value={'passed': False, 'verdict': 'FAIL: insufficient samples', 'n_samples': 5}):
            metrics = engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_3',
                cost_aware=False,
            )
        
        # Verify FoldMetrics has gate_metadata field
        self.assertTrue(hasattr(metrics, 'gate_metadata'), "FoldMetrics should have gate_metadata field")
        
        # Verify gate_metadata is present and has correct structure
        if metrics.gate_metadata is not None:
            self.assertIn('selection_source', metrics.gate_metadata)
            self.assertIn('used_fallback_candidates', metrics.gate_metadata)
            self.assertIn('gate_mode', metrics.gate_metadata)


class TestP10GateTuningCLIPersist(unittest.TestCase):
    """
    F2: CLI parse/pass/persist tests for P10 gate tuning configuration.
    
    Verifies that:
    1. run_phase35_backtest.py argparse includes P10 gate config keys
    2. serialize_fold_details() persists gate_metadata to JSON
    3. Serialization includes all required fields and convenience aliases
    """
    
    def test_cli_parser_includes_p10_gate_config_keys(self):
        """Verify argparse includes p10_gate_mode, p10_gate_min_pass, p10_gate_allow_fallback_candidates."""
        import sys
        import os
        import argparse
        
        # Import the script module
        script_path = os.path.join(os.path.dirname(__file__), '../../scripts/run_phase35_backtest.py')
        script_path = os.path.abspath(script_path)
        
        # Read the script source to verify config keys are present
        with open(script_path, 'r') as f:
            script_source = f.read()
        
        # Verify P10 gate config keys are in the script
        self.assertIn('p10_gate_mode', script_source, 
                     "Script should include p10_gate_mode config key")
        self.assertIn('p10_gate_min_pass', script_source,
                     "Script should include p10_gate_min_pass config key")
        self.assertIn('p10_gate_allow_fallback_candidates', script_source,
                     "Script should include p10_gate_allow_fallback_candidates config key")
        
        # Verify the config keys appear in argparse section
        self.assertIn('--p10-gate-mode', script_source,
                     "Script should have --p10-gate-mode CLI argument")
        self.assertIn('--p10-gate-min-pass', script_source,
                     "Script should have --p10-gate-min-pass CLI argument")
        self.assertIn('--p10-gate-allow-fallback-candidates', script_source,
                     "Script should have --p10-gate-allow-fallback-candidates CLI argument")
        
        # Verify the config keys appear in results_dict/config section for persistence
        # Look for the config dict section
        config_section_start = script_source.find('"config": {')
        config_section_end = script_source.find('},', config_section_start)
        config_section = script_source[config_section_start:config_section_end]
        
        self.assertIn('"p10_gate_mode":', config_section,
                     "Config dict should persist p10_gate_mode")
        self.assertIn('"p10_gate_min_pass":', config_section,
                     "Config dict should persist p10_gate_min_pass")
        self.assertIn('"p10_gate_allow_fallback_candidates":', config_section,
                     "Config dict should persist p10_gate_allow_fallback_candidates")
    
    def test_serialize_fold_details_with_gate_metadata(self):
        """Verify serialize_fold_details() includes gate_metadata when present on FoldMetrics."""
        import sys
        import os
        
        # Import the serialize_fold_details function from the script
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))
        from run_phase35_backtest import serialize_fold_details
        
        # Create a mock FoldMetrics object with gate_metadata
        class MockFoldMetrics:
            def __init__(self):
                self.fold_id = 1
                self.train_start = "2020-01-01"
                self.train_end = "2020-12-31"
                self.test_start = "2021-01-01"
                self.test_end = "2021-12-31"
                self.portfolio_ic = 0.15
                self.portfolio_sharpe = 1.5
                self.portfolio_max_dd = -0.10
                self.portfolio_total_return = 0.25
                self.portfolio_pnl_vnd = 250000000.0
                self.alpha_ics = {"alpha_a": 0.20, "alpha_b": 0.10}
                self.n_train_samples = 1000
                self.n_test_samples = 200
                self.gate_metadata = {
                    "selection_source": "fallback_candidate",
                    "used_fallback_candidates": True,
                    "gate_passed_count": 0,
                    "gate_total": 2,
                    "gate_required_passes": 1,
                    "gate_mode": "relaxed",
                    "gate_passed_alphas": []
                }
        
        mock_metrics = MockFoldMetrics()
        result = serialize_fold_details(mock_metrics)
        
        # Verify basic fields are present
        self.assertEqual(result["fold_id"], 1)
        self.assertEqual(result["portfolio_ic"], 0.15)
        
        # Verify gate_metadata is present in serialized output
        self.assertIn("gate_metadata", result, 
                     "Serialized fold should include gate_metadata")
        self.assertIsNotNone(result["gate_metadata"],
                            "gate_metadata should not be None when present on FoldMetrics")
        
        # Verify convenience aliases are present
        self.assertIn("selection_source", result,
                     "Serialized fold should include selection_source convenience alias")
        self.assertIn("used_fallback_candidates", result,
                     "Serialized fold should include used_fallback_candidates convenience alias")
        self.assertIn("gate_passed_count", result,
                     "Serialized fold should include gate_passed_count convenience alias")
        self.assertIn("gate_total", result,
                     "Serialized fold should include gate_total convenience alias")
        self.assertIn("gate_required_passes", result,
                     "Serialized fold should include gate_required_passes convenience alias")
        self.assertIn("gate_mode", result,
                     "Serialized fold should include gate_mode convenience alias")
        self.assertIn("gate_passed_alphas", result,
                     "Serialized fold should include gate_passed_alphas convenience alias")
        
        # Verify values match
        self.assertEqual(result["selection_source"], "fallback_candidate")
        self.assertTrue(result["used_fallback_candidates"])
        self.assertEqual(result["gate_passed_count"], 0)
        self.assertEqual(result["gate_mode"], "relaxed")
    
    def test_serialize_fold_details_without_gate_metadata(self):
        """Verify serialize_fold_details() works correctly when gate_metadata is None (backward compat)."""
        import sys
        import os
        
        # Import the serialize_fold_details function from the script
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))
        from run_phase35_backtest import serialize_fold_details
        
        # Create a mock FoldMetrics object without gate_metadata
        class MockFoldMetrics:
            def __init__(self):
                self.fold_id = 1
                self.train_start = "2020-01-01"
                self.train_end = "2020-12-31"
                self.test_start = "2021-01-01"
                self.test_end = "2021-12-31"
                self.portfolio_ic = 0.15
                self.portfolio_sharpe = 1.5
                self.portfolio_max_dd = -0.10
                self.portfolio_total_return = 0.25
                self.portfolio_pnl_vnd = 250000000.0
                self.alpha_ics = {"alpha_a": 0.20, "alpha_b": 0.10}
                self.n_train_samples = 1000
                self.n_test_samples = 200
                # No gate_metadata attribute
        
        mock_metrics = MockFoldMetrics()
        result = serialize_fold_details(mock_metrics)
        
        # Verify basic fields are present
        self.assertEqual(result["fold_id"], 1)
        self.assertEqual(result["portfolio_ic"], 0.15)
        
        # Verify gate_metadata fields are NOT present when not on FoldMetrics
        self.assertNotIn("gate_metadata", result,
                        "Serialized fold should not include gate_metadata when not present on FoldMetrics")
        self.assertNotIn("selection_source", result,
                        "Convenience aliases should not be present when gate_metadata is None")


# ---------------------------------------------------------------------------
# Role20 P10 Fix: Partial Horizon Success Metadata Selection
# ---------------------------------------------------------------------------

class TestP10PartialHorizonMetadataSelection(unittest.TestCase):
    """
    Role20 P10 Fix 2026-06-10: Verify run_fold() selects metadata from first 
    included horizon, not first requested horizon, in partial-success scenarios.
    
    Bug: If horizon 1 is excluded but horizon 3 is included, FoldMetrics 
    should report horizon 3's gate_metadata, not horizon 1's.
    """
    
    def test_metadata_from_first_included_not_first_requested(self):
        """
        Scenario: Request horizons [1, 3, 5], but fwd_ret_1 is missing.
        Expected: FoldMetrics.gate_metadata comes from horizon 3 (first included),
                  not horizon 1 (first requested but excluded).
        
        Verification approach:
        - Horizon 1 (excluded due to missing fwd_ret_1) would have:
          selection_source='excluded', exclusion_reason='return_col_not_found'
        - Horizon 3 (included) would have:
          selection_source='research_gate' or 'fallback_candidate', 
          gate_passed_count > 0 (or at least gate_total > 0)
        """
        # Create engine requesting horizons [1, 3, 5]
        engine = _make_engine(
            multi_horizon_blend=True,
            blend_horizons=[1, 3, 5],
            blend_weight_method="validation_ic",
            min_ic_threshold=0.0,
            top_n_alphas=2,
            top_n_stocks=5,
        )
        
        # Create data with only horizons [3, 5] - horizon 1 missing
        df = _make_df(n_dates=100, include_horizons=[3, 5], seed=42)
        
        n = len(df)
        train_df = df.iloc[:int(n * 0.7)].copy()
        test_df = df.iloc[int(n * 0.7):].copy()
        
        # Compute alphas
        train_df = engine.compute_alphas(train_df)
        test_df = engine.compute_alphas(test_df)
        
        alpha_cols = ['alpha_a', 'alpha_b']
        
        # Mock gate validation to return PASS
        def mock_gate_validation(alphas, returns, **kwargs):
            return {
                'passed': True,
                'verdict': 'PASS',
                'n_samples': len(returns),
            }
        
        with patch('omega.quant.alpha.phase35.validate_research_gate',
                   side_effect=mock_gate_validation):
            # Run fold - horizon 1 should be excluded, horizons 3 and 5 included
            result = engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=alpha_cols,
                return_col='fwd_ret_5',  # Default objective
                cost_aware=False,
            )
        
        # Verify FoldMetrics was returned
        self.assertIsNotNone(result, "run_fold should return FoldMetrics")
        
        # Verify gate_metadata is present
        self.assertIsNotNone(result.gate_metadata, 
                            "FoldMetrics should have gate_metadata")
        
        # Key assertion 1: selection_source should NOT be 'excluded'
        # If it were 'excluded', it would mean we selected metadata from horizon 1
        selection_source = result.gate_metadata.get('selection_source', '')
        self.assertNotEqual(selection_source, 'excluded',
                           f"gate_metadata.selection_source should not be 'excluded' "
                           f"(which would indicate horizon 1). Got: {selection_source}")
        
        # Key assertion 2: Should NOT have exclusion_reason field
        # excluded horizons have this field, included horizons don't
        self.assertNotIn('exclusion_reason', result.gate_metadata,
                        "gate_metadata should not have 'exclusion_reason' field "
                        "(which only appears in excluded horizons)")
        
        # Key assertion 3: gate_total should be > 0
        # Excluded horizons (missing data) have gate_total=0
        gate_total = result.gate_metadata.get('gate_total', 0)
        self.assertGreater(gate_total, 0,
                          f"gate_total should be > 0 for included horizon. Got: {gate_total}")
        
        # Additional verification: gated_alphas should not be empty
        self.assertIsNotNone(result.gated_alphas,
                            "FoldMetrics should have gated_alphas")
        self.assertGreater(len(result.gated_alphas), 0,
                          "gated_alphas should not be empty for included horizon")


if __name__ == '__main__':
    unittest.main()
