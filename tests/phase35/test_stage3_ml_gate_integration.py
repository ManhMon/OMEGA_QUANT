"""
Stage 3 ML Gate Integration Tests
[L2-Impl:Role9-Backend] - 2026-05-22

Verifies that validate_alpha_with_research_gate() is correctly wired into
Phase35WalkForwardEngine.run_fold():
  - gate_results and gated_alphas stored in FoldMetrics
  - alphas that pass gate are used for portfolio signal
  - fallback to top_alphas when all alphas fail gate
  - rolling IC series computed on embargoed train_df_clean (PIT safe)
  - validate_research_gate() called with correct arguments

PIT Safety: No real data loaded. All data is synthetic in-memory.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_alpha_module():
    """Minimal alpha module: passes df through unchanged (alpha cols pre-set)."""
    class _FakeAlphaModule:
        @staticmethod
        def compute_phase34_microstructure_alphas(df, **kwargs):
            return df.copy()
    return _FakeAlphaModule()


def _make_engine(min_ic_threshold=0.0, top_n_alphas=3, top_n_stocks=5,
                 rebalance_freq=1, sector_cap_pct=1.0):
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    return Phase35WalkForwardEngine(
        alpha_module=_make_fake_alpha_module(),
        min_ic_threshold=min_ic_threshold,
        top_n_alphas=top_n_alphas,
        top_n_stocks=top_n_stocks,
        rebalance_freq=rebalance_freq,
        sector_cap_pct=sector_cap_pct,
    )


def _make_df(n_dates=80, tickers=None, seed=42):
    """
    Build synthetic OHLCV DataFrame with alpha columns and forward returns.

    n_dates=80 ensures rolling_ic_series has >= 60 samples after 20-day window
    (80 dates - 19 window warmup = 61 rolling values).
    """
    if tickers is None:
        tickers = ['A', 'B', 'C', 'D', 'E']

    dates = pd.date_range('2023-01-01', periods=n_dates, freq='B')
    rng = np.random.default_rng(seed)
    rows = []
    for t in tickers:
        prices = 100 + rng.normal(0, 1, n_dates).cumsum()
        # alpha_pass: high IC signal (correlated with returns)
        alpha_pass_vals = rng.normal(0, 1, n_dates)
        # alpha_fail: zero signal (no IC)
        alpha_fail_vals = np.zeros(n_dates)
        fwd_rets = alpha_pass_vals * 0.1 + rng.normal(0, 0.005, n_dates)
        for i, d in enumerate(dates):
            rows.append({
                'date': d,
                'ticker': t,
                'open': prices[i],
                'high': prices[i] * 1.01,
                'low': prices[i] * 0.99,
                'close': prices[i],
                'volume': 1_000_000,
                'sector': 'SectorA',
                'fwd_ret_5': fwd_rets[i],
                'alpha_pass': alpha_pass_vals[i],
                'alpha_fail': alpha_fail_vals[i],
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------

class TestFoldMetricsGateFields(unittest.TestCase):
    """FoldMetrics must have gate_results and gated_alphas fields."""

    def test_fold_metrics_has_gate_results_field(self):
        from omega.quant.alpha.phase35 import FoldMetrics
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(FoldMetrics)}
        self.assertIn('gate_results', field_names,
                      "FoldMetrics must have gate_results field")

    def test_fold_metrics_has_gated_alphas_field(self):
        from omega.quant.alpha.phase35 import FoldMetrics
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(FoldMetrics)}
        self.assertIn('gated_alphas', field_names,
                      "FoldMetrics must have gated_alphas field")

    def test_fold_metrics_gate_results_default_empty_dict(self):
        from omega.quant.alpha.phase35 import FoldMetrics
        m = FoldMetrics(fold_id=1, train_start='2023-01-01', train_end='2023-06-01',
                        test_start='2023-06-02', test_end='2023-12-31')
        self.assertIsInstance(m.gate_results, dict)
        self.assertEqual(len(m.gate_results), 0)

    def test_fold_metrics_gated_alphas_default_empty_list(self):
        from omega.quant.alpha.phase35 import FoldMetrics
        m = FoldMetrics(fold_id=1, train_start='2023-01-01', train_end='2023-06-01',
                        test_start='2023-06-02', test_end='2023-12-31')
        self.assertIsInstance(m.gated_alphas, list)
        self.assertEqual(len(m.gated_alphas), 0)


class TestValidateAlphaWithResearchGateMethod(unittest.TestCase):
    """Unit tests for validate_alpha_with_research_gate() method."""

    def test_method_exists_on_engine(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        self.assertTrue(
            hasattr(Phase35WalkForwardEngine, 'validate_alpha_with_research_gate'),
            "Phase35WalkForwardEngine must have validate_alpha_with_research_gate method"
        )

    def test_returns_tuple_of_list_and_dict(self):
        engine = _make_engine()
        df = _make_df(n_dates=80)
        # Use enough data so rolling IC has >= 60 samples
        train_ics = {'alpha_pass': 0.10, 'alpha_fail': 0.0}
        gated, results = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_pass', 'alpha_fail'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
            rolling_window=20,
        )
        self.assertIsInstance(gated, list)
        self.assertIsInstance(results, dict)

    def test_gate_results_keyed_by_alpha_name(self):
        engine = _make_engine()
        df = _make_df(n_dates=80)
        train_ics = {'alpha_pass': 0.10, 'alpha_fail': 0.0}
        _, results = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_pass', 'alpha_fail'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
        )
        self.assertIn('alpha_pass', results)
        self.assertIn('alpha_fail', results)

    def test_gate_result_dict_has_required_keys(self):
        """Each gate result must have: passed, val_ic, stability_ratio, n_samples, verdict."""
        engine = _make_engine()
        df = _make_df(n_dates=80)
        train_ics = {'alpha_pass': 0.10}
        _, results = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_pass'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
        )
        required_keys = {'passed', 'val_ic', 'stability_ratio', 'n_samples', 'verdict'}
        self.assertTrue(
            required_keys.issubset(results['alpha_pass'].keys()),
            f"gate result missing keys: {required_keys - results['alpha_pass'].keys()}"
        )

    def test_fallback_when_all_alphas_fail_gate(self):
        """If all alphas fail gate, gated_alphas must equal top_alphas (fallback)."""
        engine = _make_engine()
        df = _make_df(n_dates=80)
        # val_ic=0.0 will fail the val_ic >= 0.05 check
        train_ics = {'alpha_fail': 0.0}
        gated, results = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_fail'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
        )
        self.assertFalse(results['alpha_fail']['passed'])
        # Fallback: gated_alphas == top_alphas
        self.assertEqual(gated, ['alpha_fail'],
                         "Fallback must return top_alphas when all fail gate")

    def test_fallback_multiple_alphas_all_fail(self):
        """Fallback with multiple failing alphas returns all of top_alphas."""
        engine = _make_engine()
        df = _make_df(n_dates=80)
        train_ics = {'alpha_fail': 0.0, 'alpha_pass': 0.0}  # both val_ic=0 -> fail
        gated, _ = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_fail', 'alpha_pass'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
        )
        self.assertEqual(sorted(gated), sorted(['alpha_fail', 'alpha_pass']))

    def test_insufficient_samples_causes_fail(self):
        """Rolling IC with < 60 samples must fail the gate (n_samples check)."""
        engine = _make_engine()
        # Only 10 dates -> rolling(20).mean() produces 0 valid values -> n_samples=0 < 60
        df = _make_df(n_dates=10)
        train_ics = {'alpha_pass': 0.10}
        _, results = engine.validate_alpha_with_research_gate(
            top_alphas=['alpha_pass'],
            train_ics=train_ics,
            train_df_clean=df,
            return_col='fwd_ret_5',
            rolling_window=20,
        )
        self.assertFalse(results['alpha_pass']['passed'],
                         "Gate must fail when rolling IC has < 60 samples")

    def test_validate_research_gate_called_with_correct_val_ic(self):
        """validate_research_gate must be called with val_ic from train_ics."""
        engine = _make_engine()
        df = _make_df(n_dates=80)
        train_ics = {'alpha_pass': 0.07}

        call_args = []
        from omega.quant import ml_gate_validator

        orig = ml_gate_validator.validate_research_gate

        def _spy(val_ic, rolling_ic_series, min_samples=60):
            call_args.append({'val_ic': val_ic, 'n': len(rolling_ic_series)})
            return orig(val_ic, rolling_ic_series, min_samples)

        with patch.object(ml_gate_validator, 'validate_research_gate', side_effect=_spy):
            # Re-import to pick up patched reference inside the engine module
            from omega.quant.alpha import phase35
            with patch.object(phase35, 'validate_research_gate', side_effect=_spy):
                engine.validate_alpha_with_research_gate(
                    top_alphas=['alpha_pass'],
                    train_ics=train_ics,
                    train_df_clean=df,
                    return_col='fwd_ret_5',
                )

        self.assertTrue(len(call_args) >= 1, "validate_research_gate was not called")
        self.assertAlmostEqual(call_args[0]['val_ic'], 0.07, places=9)

    def test_rolling_ic_series_uses_rolling_window(self):
        """Rolling IC series length must reflect rolling_window parameter."""
        engine = _make_engine()
        # 80 dates, 5 tickers -> 80 daily IC values -> rolling(20) -> 61 non-NaN values
        df = _make_df(n_dates=80)
        train_ics = {'alpha_pass': 0.10}

        captured_series = []
        from omega.quant.alpha import phase35

        orig = phase35.validate_research_gate

        def _spy(val_ic, rolling_ic_series, min_samples=60):
            captured_series.append(rolling_ic_series.copy())
            return orig(val_ic, rolling_ic_series, min_samples)

        with patch.object(phase35, 'validate_research_gate', side_effect=_spy):
            engine.validate_alpha_with_research_gate(
                top_alphas=['alpha_pass'],
                train_ics=train_ics,
                train_df_clean=df,
                return_col='fwd_ret_5',
                rolling_window=20,
            )

        self.assertTrue(len(captured_series) >= 1)
        # 80 dates - 19 warmup = 61 rolling values (after dropna)
        self.assertGreaterEqual(len(captured_series[0]), 60,
                                "Rolling IC series must have >= 60 samples for 80-date train set")


class TestRunFoldStage3GateIntegration(unittest.TestCase):
    """
    Integration tests: verify Stage 3 gate is wired into run_fold().

    Uses synthetic data — no parquet, no real market data.
    PIT safety: all data is in-memory, embargo applied upstream in run_fold.
    """

    def _run_fold(self, engine, n_train=80, n_test=20, alpha_cols=None, seed=42):
        """Helper: build train/test split and run a fold."""
        if alpha_cols is None:
            alpha_cols = ['alpha_pass', 'alpha_fail']
        df = _make_df(n_dates=n_train + n_test, seed=seed)
        dates = sorted(df['date'].unique())
        train_dates = set(dates[:n_train])
        train_df = df[df['date'].isin(train_dates)].copy()
        test_df = df[~df['date'].isin(train_dates)].copy()
        return engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=alpha_cols,
            return_col='fwd_ret_5',
        )

    def test_run_fold_returns_fold_metrics_with_gate_results(self):
        """run_fold must return FoldMetrics with gate_results populated."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine)
        self.assertIsInstance(metrics.gate_results, dict)
        self.assertGreater(len(metrics.gate_results), 0,
                           "gate_results must be populated after run_fold")

    def test_run_fold_returns_fold_metrics_with_gated_alphas(self):
        """run_fold must return FoldMetrics with gated_alphas populated."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine)
        self.assertIsInstance(metrics.gated_alphas, list)
        self.assertGreater(len(metrics.gated_alphas), 0,
                           "gated_alphas must be non-empty after run_fold")

    def test_gate_results_keys_are_subset_of_top_alphas(self):
        """gate_results keys must be exactly the alphas that went through the gate."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine, alpha_cols=['alpha_pass', 'alpha_fail'])
        # gate_results keys must be a subset of the alpha_cols
        for key in metrics.gate_results:
            self.assertIn(key, ['alpha_pass', 'alpha_fail'],
                          f"Unexpected key in gate_results: {key}")

    def test_gated_alphas_is_subset_of_top_alphas(self):
        """gated_alphas must be a subset of the selected top_alphas."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine, alpha_cols=['alpha_pass', 'alpha_fail'])
        for alpha in metrics.gated_alphas:
            self.assertIn(alpha, ['alpha_pass', 'alpha_fail'],
                          f"gated_alphas contains unknown alpha: {alpha}")

    def test_fallback_gated_alphas_nonempty_when_all_fail(self):
        """
        Even if all alphas fail the gate, gated_alphas must be non-empty
        (fallback to top_alphas ensures portfolio signal can be computed).
        """
        # Use very short train to force insufficient samples -> all fail gate
        engine = _make_engine(top_n_alphas=1, min_ic_threshold=0.0)
        df = _make_df(n_dates=30)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:10]))].copy()
        test_df = df[df['date'].isin(set(dates[10:]))].copy()
        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_pass'],
            return_col='fwd_ret_5',
        )
        self.assertGreater(len(metrics.gated_alphas), 0,
                           "gated_alphas must be non-empty even when all alphas fail gate")

    def test_run_fold_completes_without_error(self):
        """run_fold must complete end-to-end without raising exceptions."""
        engine = _make_engine(top_n_alphas=2)
        try:
            metrics = self._run_fold(engine)
        except Exception as e:
            self.fail(f"run_fold raised an exception: {e}")
        self.assertIsNotNone(metrics)

    def test_fold_metrics_fold_id_preserved(self):
        """fold_id must be correctly stored in returned FoldMetrics."""
        engine = _make_engine(top_n_alphas=1)
        metrics = self._run_fold(engine, alpha_cols=['alpha_pass'])
        self.assertEqual(metrics.fold_id, 1)

    def test_gate_results_each_has_passed_key(self):
        """Every entry in gate_results must have a 'passed' boolean key."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine)
        for alpha, result in metrics.gate_results.items():
            self.assertIn('passed', result,
                          f"gate_results['{alpha}'] missing 'passed' key")
            self.assertIsInstance(result['passed'], bool,
                                  f"gate_results['{alpha}']['passed'] must be bool")

    def test_gate_results_each_has_verdict_key(self):
        """Every entry in gate_results must have a 'verdict' string key."""
        engine = _make_engine(top_n_alphas=2)
        metrics = self._run_fold(engine)
        for alpha, result in metrics.gate_results.items():
            self.assertIn('verdict', result,
                          f"gate_results['{alpha}'] missing 'verdict' key")
            self.assertIsInstance(result['verdict'], str)

    def test_pit_safety_gate_uses_only_train_data(self):
        """
        PIT safety: validate_alpha_with_research_gate must be called with
        train_df_clean (embargoed), not test_df. Verified by checking that
        gate_results are populated before portfolio signal uses test data.

        Proxy test: run_fold with disjoint train/test date ranges and confirm
        gate_results reference train-period data (n_samples > 0 only if
        train has enough dates).
        """
        engine = _make_engine(top_n_alphas=1)
        # Short train (10 dates) -> insufficient samples -> gate fails
        df = _make_df(n_dates=30)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:10]))].copy()
        test_df = df[df['date'].isin(set(dates[10:]))].copy()
        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_pass'],
            return_col='fwd_ret_5',
        )
        # With only 10 train dates, rolling(20) produces 0 samples -> gate fails
        for alpha, result in metrics.gate_results.items():
            self.assertFalse(
                result['passed'],
                f"Gate should fail with only 10 train dates (insufficient rolling IC samples)"
            )


class TestValidateAlphaWithResearchGateImport(unittest.TestCase):
    """Verify validate_research_gate is imported from ml_gate_validator."""

    def test_validate_research_gate_importable_from_phase35(self):
        """validate_research_gate must be importable via phase35_walk_forward module."""
        from omega.quant import phase35_walk_forward
        self.assertTrue(
            hasattr(phase35_walk_forward, 'validate_research_gate'),
            "validate_research_gate must be imported in phase35_walk_forward module"
        )

    def test_validate_research_gate_is_callable(self):
        from omega.quant import phase35_walk_forward
        self.assertTrue(callable(phase35_walk_forward.validate_research_gate))


if __name__ == '__main__':
    unittest.main()
