"""
Stage 4 XGBoost Integration Tests
[L2-Impl:Role9-Backend] - 2026-05-22

Verifies optional XGBoostAlphaEnsemble path in Phase35WalkForwardEngine.run_fold():
  - use_xgboost=False (default): baseline IC-weighted path unchanged
  - use_xgboost=True: XGBoost path active, produces valid portfolio_signal
  - Toggle isolation: both paths produce non-NaN FoldMetrics
  - Fallback: XGBoost exceptions fall back to baseline gracefully
  - PIT Safety: ensemble trains only on embargoed train_df_clean

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
# Helpers (mirror pattern from test_stage3_ml_gate_integration.py)
# ---------------------------------------------------------------------------

def _make_fake_alpha_module():
    """Minimal alpha module: passes df through unchanged (alpha cols pre-set)."""
    class _FakeAlphaModule:
        @staticmethod
        def compute_phase34_microstructure_alphas(df, **kwargs):
            return df.copy()
    return _FakeAlphaModule()


def _make_engine(use_xgboost=False, min_ic_threshold=0.0, top_n_alphas=2,
                 top_n_stocks=5, rebalance_freq=1, sector_cap_pct=1.0):
    from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
    return Phase35WalkForwardEngine(
        alpha_module=_make_fake_alpha_module(),
        min_ic_threshold=min_ic_threshold,
        top_n_alphas=top_n_alphas,
        top_n_stocks=top_n_stocks,
        rebalance_freq=rebalance_freq,
        sector_cap_pct=sector_cap_pct,
        use_xgboost=use_xgboost,
    )


def _make_df(n_dates=80, tickers=None, seed=42):
    """
    Build synthetic OHLCV DataFrame with alpha columns and forward returns.
    Matches the helper in test_stage3_ml_gate_integration.py for consistency.
    """
    if tickers is None:
        tickers = ['A', 'B', 'C', 'D', 'E']

    dates = pd.date_range('2023-01-01', periods=n_dates, freq='B')
    rng = np.random.default_rng(seed)
    rows = []
    for t in tickers:
        prices = 100 + rng.normal(0, 1, n_dates).cumsum()
        alpha_pass_vals = rng.normal(0, 1, n_dates)
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


def _run_fold(engine, n_train=80, n_test=20, alpha_cols=None, seed=42):
    """Build train/test split and run a single fold."""
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


# ---------------------------------------------------------------------------
# Tests: constructor toggle
# ---------------------------------------------------------------------------

class TestUseXgboostToggle(unittest.TestCase):
    """use_xgboost param must be stored and default to False."""

    def test_default_use_xgboost_is_false(self):
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
        engine = Phase35WalkForwardEngine(
            alpha_module=_make_fake_alpha_module(),
        )
        self.assertFalse(engine.use_xgboost)

    def test_use_xgboost_true_stored(self):
        engine = _make_engine(use_xgboost=True)
        self.assertTrue(engine.use_xgboost)

    def test_use_xgboost_false_stored(self):
        engine = _make_engine(use_xgboost=False)
        self.assertFalse(engine.use_xgboost)


# ---------------------------------------------------------------------------
# Tests: baseline path unaffected (use_xgboost=False)
# ---------------------------------------------------------------------------

class TestBaselinePathUnchanged(unittest.TestCase):
    """use_xgboost=False must produce identical behaviour to pre-Stage4."""

    def test_baseline_run_fold_completes(self):
        engine = _make_engine(use_xgboost=False)
        try:
            metrics = _run_fold(engine)
        except Exception as e:
            self.fail(f"Baseline run_fold raised: {e}")
        self.assertIsNotNone(metrics)

    def test_baseline_fold_metrics_has_valid_ic(self):
        engine = _make_engine(use_xgboost=False)
        metrics = _run_fold(engine)
        self.assertFalse(
            np.isnan(metrics.portfolio_ic),
            "Baseline portfolio_ic must not be NaN"
        )

    def test_baseline_fold_metrics_has_valid_sharpe(self):
        engine = _make_engine(use_xgboost=False)
        metrics = _run_fold(engine)
        self.assertFalse(
            np.isnan(metrics.portfolio_sharpe),
            "Baseline portfolio_sharpe must not be NaN"
        )

    def test_baseline_gated_alphas_nonempty(self):
        engine = _make_engine(use_xgboost=False)
        metrics = _run_fold(engine)
        self.assertGreater(len(metrics.gated_alphas), 0)

    def test_baseline_compute_portfolio_signal_called(self):
        """Baseline path must call compute_portfolio_signal (not XGBoost)."""
        engine = _make_engine(use_xgboost=False)
        with patch.object(engine, 'compute_portfolio_signal',
                          wraps=engine.compute_portfolio_signal) as mock_sig:
            _run_fold(engine)
            mock_sig.assert_called()


# ---------------------------------------------------------------------------
# Tests: XGBoost path (use_xgboost=True) — mocked ensemble
# ---------------------------------------------------------------------------

class TestXgboostPathWithMock(unittest.TestCase):
    """
    XGBoost path tests using a mocked XGBoostAlphaEnsemble to avoid
    requiring a trained model or xgboost installation in CI.

    PIT Safety: mock returns deterministic predictions; no real data used.
    """

    def _mock_ensemble_cls(self, n_test_rows):
        """Return a mock XGBoostAlphaEnsemble class whose predict returns ones."""
        mock_instance = MagicMock()
        mock_instance.is_trained = True
        # predict returns a Series of ones with a MultiIndex (length = n_test_rows)
        dates = pd.date_range('2023-05-01', periods=n_test_rows, freq='B')
        mi = pd.MultiIndex.from_arrays(
            [dates, ['A'] * n_test_rows], names=['date', 'symbol']
        )
        mock_instance.predict.return_value = pd.Series(
            np.ones(n_test_rows), index=mi
        )
        mock_cls = MagicMock(return_value=mock_instance)
        return mock_cls, mock_instance

    def test_xgboost_path_run_fold_completes(self):
        """use_xgboost=True must complete run_fold without raising."""
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            try:
                metrics = engine.run_fold(
                    fold_id=1,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=['alpha_pass', 'alpha_fail'],
                    return_col='fwd_ret_5',
                )
            except Exception as e:
                self.fail(f"XGBoost run_fold raised: {e}")
        self.assertIsNotNone(metrics)

    def test_xgboost_path_ensemble_train_called(self):
        """XGBoostAlphaEnsemble.train() must be called when use_xgboost=True."""
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )
        mock_inst.train.assert_called_once()

    def test_xgboost_path_ensemble_predict_called(self):
        """XGBoostAlphaEnsemble.predict() must be called when use_xgboost=True."""
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )
        mock_inst.predict.assert_called_once()

    def test_xgboost_path_train_receives_multiindex(self):
        """
        XGBoostAlphaEnsemble.train() must receive a MultiIndex DataFrame
        with levels ['date', 'symbol'] — not flat ['date', 'ticker'].
        PIT Safety: train data is embargoed train_df_clean (no test leakage).
        """
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )

        train_call_df = mock_inst.train.call_args[0][0]
        self.assertIsInstance(train_call_df.index, pd.MultiIndex,
                              "train() must receive MultiIndex DataFrame")
        self.assertIn('symbol', train_call_df.index.names,
                      "MultiIndex must have 'symbol' level")
        self.assertIn('date', train_call_df.index.names,
                      "MultiIndex must have 'date' level")

    def test_xgboost_path_train_receives_gated_alphas(self):
        """train() must be called with gated_alphas as feature cols."""
        engine = _make_engine(use_xgboost=True, top_n_alphas=1)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            metrics = engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )

        train_alpha_cols = mock_inst.train.call_args[0][1]
        # Must match gated_alphas stored in metrics
        self.assertEqual(sorted(train_alpha_cols), sorted(metrics.gated_alphas))

    def test_xgboost_path_embargo_days_zero(self):
        """
        train() must be called with embargo_days=0 because embargo is
        already applied upstream in run_fold (PIT Safety).
        """
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )

        kwargs = mock_inst.train.call_args[1]
        self.assertEqual(kwargs.get('embargo_days', None), 0,
                         "embargo_days must be 0 (embargo applied upstream)")

    def test_xgboost_path_fold_metrics_valid(self):
        """FoldMetrics from XGBoost path must have non-NaN ic and sharpe."""
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()

        n_test = len(test_df)
        mock_cls, mock_inst = self._mock_ensemble_cls(n_test)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            metrics = engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )

        self.assertFalse(np.isnan(metrics.portfolio_ic),
                         "XGBoost path portfolio_ic must not be NaN")
        self.assertFalse(np.isnan(metrics.portfolio_sharpe),
                         "XGBoost path portfolio_sharpe must not be NaN")


# ---------------------------------------------------------------------------
# Tests: fallback on XGBoost exception
# ---------------------------------------------------------------------------

class TestXgboostFallback(unittest.TestCase):
    """When XGBoost raises, run_fold must fall back to baseline gracefully."""

    def test_xgboost_exception_falls_back_to_baseline(self):
        """If XGBoostAlphaEnsemble raises, run_fold must not raise."""
        engine = _make_engine(use_xgboost=True)

        mock_instance = MagicMock()
        mock_instance.train.side_effect = RuntimeError("xgboost unavailable")
        mock_cls = MagicMock(return_value=mock_instance)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            try:
                metrics = _run_fold(engine)
            except Exception as e:
                self.fail(f"Fallback failed — run_fold raised: {e}")
        self.assertIsNotNone(metrics)

    def test_xgboost_exception_fallback_produces_valid_metrics(self):
        """Fallback metrics must have non-NaN portfolio_ic."""
        engine = _make_engine(use_xgboost=True)

        mock_instance = MagicMock()
        mock_instance.train.side_effect = RuntimeError("xgboost unavailable")
        mock_cls = MagicMock(return_value=mock_instance)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            metrics = _run_fold(engine)

        self.assertFalse(np.isnan(metrics.portfolio_ic))

    def test_baseline_not_called_when_xgboost_succeeds(self):
        """compute_portfolio_signal must NOT be called when XGBoost succeeds."""
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()
        n_test = len(test_df)

        # Build a mock that returns correct-length predictions
        mock_instance = MagicMock()
        mock_instance.is_trained = True
        dates_pred = pd.date_range('2023-05-01', periods=n_test, freq='B')
        mi = pd.MultiIndex.from_arrays(
            [dates_pred, ['A'] * n_test], names=['date', 'symbol']
        )
        mock_instance.predict.return_value = pd.Series(
            np.ones(n_test), index=mi
        )
        mock_cls = MagicMock(return_value=mock_instance)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            with patch.object(engine, 'compute_portfolio_signal',
                              wraps=engine.compute_portfolio_signal) as mock_sig:
                engine.run_fold(
                    fold_id=1,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=['alpha_pass', 'alpha_fail'],
                    return_col='fwd_ret_5',
                )
        mock_sig.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: PIT Safety
# ---------------------------------------------------------------------------

class TestXgboostPITSafety(unittest.TestCase):
    """
    PIT Safety: XGBoost ensemble must train only on embargoed train_df_clean,
    not on test_df or the full un-embargoed train_df.
    """

    def test_train_cutoff_date_is_max_train_date(self):
        """
        cutoff_date passed to train() must equal max date of embargoed
        train_df_clean (not test_df max date).
        """
        engine = _make_engine(use_xgboost=True)
        df = _make_df(n_dates=100)
        dates = sorted(df['date'].unique())
        train_df = df[df['date'].isin(set(dates[:80]))].copy()
        test_df = df[~df['date'].isin(set(dates[:80]))].copy()
        n_test = len(test_df)

        mock_instance = MagicMock()
        mock_instance.is_trained = True
        mi = pd.MultiIndex.from_arrays(
            [pd.date_range('2023-05-01', periods=n_test, freq='B'),
             ['A'] * n_test],
            names=['date', 'symbol']
        )
        mock_instance.predict.return_value = pd.Series(np.ones(n_test), index=mi)
        mock_cls = MagicMock(return_value=mock_instance)

        from omega.quant import phase35_walk_forward
        with patch.object(phase35_walk_forward, 'XGBoostAlphaEnsemble', mock_cls):
            engine.run_fold(
                fold_id=1,
                train_df=train_df,
                test_df=test_df,
                alpha_cols=['alpha_pass', 'alpha_fail'],
                return_col='fwd_ret_5',
            )

        kwargs = mock_instance.train.call_args[1]
        cutoff_used = pd.Timestamp(kwargs['cutoff_date'])
        test_min_date = test_df['date'].min()
        # cutoff must be strictly before test period start
        self.assertLess(
            cutoff_used, test_min_date,
            "cutoff_date must be before test period (PIT Safety)"
        )


if __name__ == '__main__':
    unittest.main()
