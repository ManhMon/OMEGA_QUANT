"""
Unit Tests: Phase 15 OOS Validation Framework — Temporal Boundary / Leakage Guard

Tests verify:
1. assert_no_leakage() raises TemporalBoundaryError on leaking data
2. assert_no_leakage() passes cleanly on valid OOS data
3. assert_no_leakage() respects embargo_days buffer
4. XGBoostAlphaEnsemble.predict() blocks leaking prediction data
5. XGBoostAlphaEnsemble.predict() allows valid OOS prediction data
6. Phase35WalkForwardEngine.run_fold() raises on overlapping train/test dates
7. Phase35WalkForwardEngine.run_fold() passes on non-overlapping train/test dates
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

from omega.quant.alpha_ensemble_xgboost import (
    XGBoostAlphaEnsemble,
    TemporalBoundaryError,
    assert_no_leakage,
)
from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_multiindex_df(start: str, periods: int, symbols=("A", "B", "C")) -> pd.DataFrame:
    """Build a minimal MultiIndex ['date','symbol'] DataFrame with alpha cols."""
    np.random.seed(0)
    dates = pd.date_range(start, periods=periods)
    idx = pd.MultiIndex.from_product([dates, list(symbols)], names=["date", "symbol"])
    df = pd.DataFrame(index=idx)
    df["close"] = 50.0 + np.random.randn(len(idx)).cumsum()
    for i in range(1, 6):
        df[f"alpha_{i:02d}"] = np.random.randn(len(idx))
    return df


def _make_flat_df(start: str, periods: int, tickers=("A", "B", "C")) -> pd.DataFrame:
    """Build a minimal flat DataFrame with 'date' and 'ticker' columns."""
    np.random.seed(1)
    dates = pd.date_range(start, periods=periods)
    rows = []
    for d in dates:
        for t in tickers:
            rows.append({"date": d, "ticker": t,
                         "open": 50.0, "high": 51.0, "low": 49.0,
                         "close": 50.0 + np.random.randn(),
                         "volume": 1_000_000.0,
                         "fwd_ret_5": np.random.randn() * 0.01})
    df = pd.DataFrame(rows)
    for i in range(1, 6):
        df[f"alpha_{i:02d}"] = np.random.randn(len(df))
    return df


# ---------------------------------------------------------------------------
# 1-3: assert_no_leakage() unit tests
# ---------------------------------------------------------------------------

class TestAssertNoLeakage:

    def test_raises_when_all_dates_in_training_window(self):
        """All prediction dates <= cutoff → must raise."""
        cutoff = pd.Timestamp("2023-06-30")
        df = _make_multiindex_df("2023-01-01", 30)  # dates well before cutoff
        with pytest.raises(TemporalBoundaryError, match="OOS leakage detected"):
            assert_no_leakage(cutoff, df, embargo_days=0)

    def test_raises_when_some_dates_in_training_window(self):
        """Mixed dates: some before cutoff, some after → must raise."""
        cutoff = pd.Timestamp("2023-03-15")
        # 30 days starting 2023-03-01 → first 14 days are <= cutoff
        df = _make_multiindex_df("2023-03-01", 30)
        with pytest.raises(TemporalBoundaryError, match="OOS leakage detected"):
            assert_no_leakage(cutoff, df, embargo_days=0)

    def test_passes_when_all_dates_strictly_after_cutoff(self):
        """All prediction dates > cutoff → no error."""
        cutoff = pd.Timestamp("2023-06-30")
        df = _make_multiindex_df("2023-07-01", 20)
        # Should not raise
        assert_no_leakage(cutoff, df, embargo_days=0)

    def test_embargo_days_extends_boundary(self):
        """Dates after cutoff but within embargo window → must raise."""
        cutoff = pd.Timestamp("2023-06-30")
        # 2023-07-03 is 3 days after cutoff — within embargo=5
        df = _make_multiindex_df("2023-07-01", 5)
        with pytest.raises(TemporalBoundaryError, match="OOS leakage detected"):
            assert_no_leakage(cutoff, df, embargo_days=5)

    def test_embargo_days_passes_beyond_buffer(self):
        """Dates strictly beyond cutoff + embargo → no error."""
        cutoff = pd.Timestamp("2023-06-30")
        # Start 10 days after cutoff, embargo=5 → boundary=2023-07-05, data starts 2023-07-10
        df = _make_multiindex_df("2023-07-10", 10)
        assert_no_leakage(cutoff, df, embargo_days=5)

    def test_flat_df_with_date_column(self):
        """Works on flat DataFrame with a 'date' column."""
        cutoff = pd.Timestamp("2023-06-30")
        df = _make_flat_df("2023-01-01", 10)  # all dates before cutoff
        with pytest.raises(TemporalBoundaryError):
            assert_no_leakage(cutoff, df, embargo_days=0, date_level="date")

    def test_flat_df_valid_oos(self):
        """Flat DataFrame with all dates after cutoff → no error."""
        cutoff = pd.Timestamp("2023-06-30")
        df = _make_flat_df("2023-07-01", 10)
        assert_no_leakage(cutoff, df, embargo_days=0, date_level="date")

    def test_raises_on_exact_cutoff_date(self):
        """Date exactly equal to cutoff is still leakage (boundary is inclusive)."""
        cutoff = pd.Timestamp("2023-06-30")
        dates = pd.date_range("2023-06-30", periods=3)
        symbols = ["A"]
        idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
        df = pd.DataFrame({"close": 1.0}, index=idx)
        with pytest.raises(TemporalBoundaryError):
            assert_no_leakage(cutoff, df, embargo_days=0)


# ---------------------------------------------------------------------------
# 4-5: XGBoostAlphaEnsemble.predict() leakage guard
# ---------------------------------------------------------------------------

class TestXGBoostEnsembleLeakageGuard:

    @pytest.fixture
    def trained_ensemble(self):
        """Train a minimal ensemble with cutoff 2023-06-30."""
        df = _make_multiindex_df("2023-01-01", 120)
        alpha_cols = [f"alpha_{i:02d}" for i in range(1, 6)]
        ensemble = XGBoostAlphaEnsemble(min_ic_threshold=-1.0)
        ensemble.train(df, alpha_cols, cutoff_date="2023-06-30", embargo_days=0)
        return ensemble, alpha_cols

    def test_predict_raises_on_training_period_data(self, trained_ensemble):
        """predict() on data from the training window must raise TemporalBoundaryError."""
        ensemble, alpha_cols = trained_ensemble
        # Data entirely within training window
        leaking_df = _make_multiindex_df("2023-03-01", 10)
        with pytest.raises(TemporalBoundaryError, match="OOS leakage detected"):
            ensemble.predict(leaking_df, alpha_cols)

    def test_predict_raises_on_mixed_period_data(self, trained_ensemble):
        """predict() on data spanning train+test boundary must raise."""
        ensemble, alpha_cols = trained_ensemble
        # Spans 2023-06-25 to 2023-07-10 — some rows are in training window
        mixed_df = _make_multiindex_df("2023-06-25", 15)
        with pytest.raises(TemporalBoundaryError):
            ensemble.predict(mixed_df, alpha_cols)

    def test_predict_passes_on_valid_oos_data(self, trained_ensemble):
        """predict() on strictly OOS data must succeed and return a Series."""
        ensemble, alpha_cols = trained_ensemble
        oos_df = _make_multiindex_df("2023-07-01", 20)
        preds = ensemble.predict(oos_df, alpha_cols)
        assert isinstance(preds, pd.Series)
        assert len(preds) == len(oos_df)
        assert not preds.isnull().all()

    def test_predict_untrained_skips_leakage_check(self):
        """Untrained ensemble returns mean signal without leakage check."""
        ensemble = XGBoostAlphaEnsemble()
        alpha_cols = [f"alpha_{i:02d}" for i in range(1, 6)]
        # Even leaking data should not raise when untrained
        leaking_df = _make_multiindex_df("2022-01-01", 10)
        preds = ensemble.predict(leaking_df, alpha_cols)
        assert isinstance(preds, pd.Series)

    def test_train_persists_cutoff_and_embargo(self):
        """After train(), _train_cutoff and _embargo_days are set correctly."""
        df = _make_multiindex_df("2023-01-01", 60)
        alpha_cols = [f"alpha_{i:02d}" for i in range(1, 6)]
        ensemble = XGBoostAlphaEnsemble(min_ic_threshold=-1.0)
        ensemble.train(df, alpha_cols, cutoff_date="2023-03-31", embargo_days=7)
        assert ensemble._train_cutoff == pd.Timestamp("2023-03-31")
        assert ensemble._embargo_days == 7


# ---------------------------------------------------------------------------
# 6-7: Phase35WalkForwardEngine.run_fold() temporal boundary guard
# ---------------------------------------------------------------------------

class TestPhase35TemporalBoundary:

    @pytest.fixture
    def engine(self):
        """Minimal engine with a mock alpha_module."""
        mock_module = MagicMock()
        # compute_phase34_microstructure_alphas returns df unchanged
        mock_module.compute_phase34_microstructure_alphas.side_effect = lambda df, **kw: df
        return Phase35WalkForwardEngine(
            alpha_module=mock_module,
            min_ic_threshold=0.0,
            top_n_alphas=3,
            top_n_stocks=3,
            rebalance_freq=5,
        )

    def _make_fold_pair(self, train_start, train_end, test_start, test_end, tickers=("A", "B", "C")):
        """Build (train_df, test_df) flat DataFrames for run_fold()."""
        def _build(start, end):
            dates = pd.date_range(start, end)
            rows = []
            for d in dates:
                for t in tickers:
                    rows.append({
                        "date": d, "ticker": t,
                        "open": 50.0, "high": 51.0, "low": 49.0,
                        "close": 50.0 + np.random.randn(),
                        "volume": 1_000_000.0,
                        "fwd_ret_5": np.random.randn() * 0.01,
                        "alpha_01": np.random.randn(),
                        "alpha_02": np.random.randn(),
                        "alpha_03": np.random.randn(),
                    })
            return pd.DataFrame(rows)

        np.random.seed(42)
        return _build(train_start, train_end), _build(test_start, test_end)

    def test_run_fold_raises_when_test_overlaps_train(self, engine):
        """test_min_date <= train_max_date must raise TemporalBoundaryError."""
        train_df, _ = self._make_fold_pair("2023-01-01", "2023-06-30",
                                           "2023-07-01", "2023-09-30")
        # Construct a test_df that starts BEFORE train ends (overlap)
        _, test_df = self._make_fold_pair("2023-01-01", "2023-06-30",
                                          "2023-06-01", "2023-09-30")
        alpha_cols = ["alpha_01", "alpha_02", "alpha_03"]
        with pytest.raises(TemporalBoundaryError, match="temporal boundary violation"):
            engine.run_fold(1, train_df, test_df, alpha_cols, return_col="fwd_ret_5")

    def test_run_fold_raises_when_test_starts_on_train_end(self, engine):
        """test_min_date == train_max_date is also a violation (not strictly after)."""
        train_df, _ = self._make_fold_pair("2023-01-01", "2023-06-30",
                                           "2023-07-01", "2023-09-30")
        # test starts exactly on train_max_date
        _, test_df = self._make_fold_pair("2023-01-01", "2023-06-30",
                                          "2023-06-30", "2023-09-30")
        alpha_cols = ["alpha_01", "alpha_02", "alpha_03"]
        with pytest.raises(TemporalBoundaryError, match="temporal boundary violation"):
            engine.run_fold(1, train_df, test_df, alpha_cols, return_col="fwd_ret_5")

    def test_run_fold_passes_when_test_strictly_after_train(self, engine):
        """test_min_date > train_max_date → no TemporalBoundaryError raised."""
        alpha_cols = ["alpha_01", "alpha_02", "alpha_03"]
        train_df, test_df = self._make_fold_pair(
            "2023-01-01", "2023-06-30",
            "2023-07-01", "2023-09-30",
        )
        # Should not raise TemporalBoundaryError
        # (may raise other errors from missing infrastructure — that's fine)
        try:
            engine.run_fold(1, train_df, test_df, alpha_cols, return_col="fwd_ret_5")
        except TemporalBoundaryError:
            pytest.fail("run_fold() raised TemporalBoundaryError on valid non-overlapping fold")
        except Exception:
            pass  # Other errors (missing alpha cols, etc.) are acceptable here

    def test_run_walk_forward_raises_on_bad_split(self, engine):
        """run_walk_forward() propagates TemporalBoundaryError from a bad split."""
        alpha_cols = ["alpha_01", "alpha_02", "alpha_03"]
        train_df, _ = self._make_fold_pair("2023-01-01", "2023-06-30",
                                           "2023-07-01", "2023-09-30")
        # Overlapping test
        _, test_df = self._make_fold_pair("2023-01-01", "2023-06-30",
                                          "2023-05-01", "2023-09-30")
        splits = [(train_df, test_df)]
        with pytest.raises(TemporalBoundaryError):
            engine.run_walk_forward(splits, alpha_cols, return_col="fwd_ret_5")
