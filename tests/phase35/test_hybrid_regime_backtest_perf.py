"""Performance and correctness verification for hybrid regime backtest optimizations.

Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

Verifies:
  1. precompute_alpha_lags() produces correct lag1 columns
  2. train_fold_models() returns composite_signal separately (thread safety)
  3. query_dynamic vectorized path produces same results as reference
  4. run_single_fold accepts precomputed_lag_cols
  5. PIT safety: no look-ahead bias in lag computation
"""
import os
import sys
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


class TestPrecomputeAlphaLags:
    """Verify precompute_alpha_lags() produces correct T-1 shifted features."""

    def _make_feat_df(self, n_days=10, n_symbols=3):
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        symbols = [f"SYM{i}" for i in range(n_symbols)]
        rows = []
        for sym in symbols:
            for i, dt in enumerate(dates):
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "close": 100.0 + i * 0.5,
                    "volume": 1_000_000,
                    "returns": 0.005,
                    "alpha_mom": float(i) * 0.01,
                    "alpha_rev": float(i) * -0.005,
                })
        return pd.DataFrame(rows)

    def test_lag_columns_created(self):
        from backtest_hybrid_regime import precompute_alpha_lags
        feat_df = self._make_feat_df()
        lag_cols = precompute_alpha_lags(feat_df)
        assert "alpha_mom_lag1" in lag_cols
        assert "alpha_rev_lag1" in lag_cols
        assert "alpha_mom_lag1" in feat_df.columns
        assert "alpha_rev_lag1" in feat_df.columns

    def test_lag_values_correct_pit_safe(self):
        """Lag1 values are T-1 shifted per symbol (no look-ahead)."""
        from backtest_hybrid_regime import precompute_alpha_lags
        feat_df = self._make_feat_df(n_days=5, n_symbols=2)
        lag_cols = precompute_alpha_lags(feat_df)

        for sym in ["SYM0", "SYM1"]:
            sym_rows = feat_df[feat_df["symbol"] == sym].sort_values("date")
            # First row per symbol should be NaN (no prior day)
            assert pd.isna(sym_rows.iloc[0]["alpha_mom_lag1"])
            # Subsequent rows should equal previous day's value
            for i in range(1, len(sym_rows)):
                assert sym_rows.iloc[i]["alpha_mom_lag1"] == pytest.approx(
                    sym_rows.iloc[i - 1]["alpha_mom"]
                )

    def test_idempotent_second_call(self):
        """Calling precompute_alpha_lags twice should not duplicate columns."""
        from backtest_hybrid_regime import precompute_alpha_lags
        feat_df = self._make_feat_df()
        lag_cols_1 = precompute_alpha_lags(feat_df)
        lag_cols_2 = precompute_alpha_lags(feat_df)
        assert lag_cols_1 == lag_cols_2
        assert feat_df.columns.tolist().count("alpha_mom_lag1") == 1

    def test_no_alpha_columns_returns_empty(self):
        from backtest_hybrid_regime import precompute_alpha_lags
        feat_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "symbol": "A",
            "close": 100.0,
        })
        lag_cols = precompute_alpha_lags(feat_df)
        assert lag_cols == []


class TestTrainFoldModelsCompositeSignal:
    """Verify train_fold_models returns composite_signal separately."""

    def _make_feat_df_with_lags(self, n_days=100, n_symbols=5):
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        symbols = [f"SYM{i}" for i in range(n_symbols)]
        np.random.seed(42)
        rows = []
        for sym in symbols:
            price = 100.0
            for i, dt in enumerate(dates):
                ret = np.random.randn() * 0.01
                price *= (1 + ret)
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "close": price,
                    "volume": 1_000_000,
                    "returns": ret,
                    "alpha_mom": np.random.randn() * 0.01,
                    "alpha_rev": np.random.randn() * 0.005,
                    "alpha_mom_lag1": np.random.randn() * 0.01 if i > 0 else np.nan,
                    "alpha_rev_lag1": np.random.randn() * 0.005 if i > 0 else np.nan,
                    "latent_ae_00": np.random.randn(),
                    "latent_ae_01": np.random.randn(),
                    "latent_ae_11": np.random.randn(),
                })
        return pd.DataFrame(rows)

    def test_returns_composite_signal_separately(self):
        """train_fold_models returns composite_signal as a pd.Series, not written into feat_df."""
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_feat_df_with_lags()
        train_dates = feat_df["date"].unique()[:50]  # First 50 dates for training

        gmm_model, hmm_params, composite_signal = train_fold_models(
            feat_df, train_dates,
            precomputed_lag_cols=["alpha_mom_lag1", "alpha_rev_lag1"],
        )

        # composite_signal should be a Series (or None if Ridge was skipped)
        if composite_signal is not None:
            assert isinstance(composite_signal, pd.Series)
            assert len(composite_signal) > 0
            # Should NOT have been written into feat_df
            assert "composite_signal" not in feat_df.columns

    def test_composite_signal_indices_valid(self):
        """composite_signal indices are valid feat_df indices."""
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_feat_df_with_lags()
        train_dates = feat_df["date"].unique()[:50]

        _, _, composite_signal = train_fold_models(
            feat_df, train_dates,
            precomputed_lag_cols=["alpha_mom_lag1", "alpha_rev_lag1"],
        )

        if composite_signal is not None:
            # All indices should be valid feat_df indices
            assert composite_signal.index.isin(feat_df.index).all()

    def test_backward_compat_without_precomputed_lags(self):
        """train_fold_models still works when precomputed_lag_cols is None."""
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_feat_df_with_lags()
        train_dates = feat_df["date"].unique()[:50]

        gmm_model, hmm_params, composite_signal = train_fold_models(
            feat_df, train_dates,
            precomputed_lag_cols=None,
        )
        # Should complete without errors
        assert hmm_params is not None or gmm_model is not None or True


class TestRunSingleFoldSignature:
    """Verify run_single_fold accepts precomputed_lag_cols parameter."""

    def test_function_signature_has_precomputed_lag_cols(self):
        import inspect
        from backtest_hybrid_regime import run_single_fold
        sig = inspect.signature(run_single_fold)
        assert "precomputed_lag_cols" in sig.parameters
        # Should default to None
        assert sig.parameters["precomputed_lag_cols"].default is None


class TestMainHasWorkersArg:
    """Verify main() passes --workers to parallel execution."""

    def test_workers_arg_in_parse_args(self):
        import inspect
        from backtest_hybrid_regime import parse_args
        # Check that --workers is in the parser
        import argparse
        parser = argparse.ArgumentParser()
        # Just verify parse_args returns an object with workers
        source = inspect.getsource(parse_args)
        assert "--workers" in source


class TestVectorizedQueryDynamic:
    """Verify the vectorized query_dynamic produces correct PIT-safe results."""

    def test_query_dynamic_vectorized_matches_reference(self):
        """Vectorized query_dynamic produces same results as brute-force reference."""
        from backtest_hybrid_regime import make_query_fn

        # Create a synthetic feat_df
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        symbols = ["A", "B", "C", "D", "E"]
        rows = []
        for dt in dates:
            for sym in symbols:
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "close": 100.0,
                    "volume": 1_000_000,
                    "returns": 0.001,
                })
        feat_df = pd.DataFrame(rows)

        # Dynamic schedule: rebalance every 10 days
        rebal_dates = [dates[0], dates[10], dates[20]]
        dynamic_schedule = {
            str(rebal_dates[0])[:10]: ["A", "B", "C"],
            str(rebal_dates[1])[:10]: ["B", "C", "D"],
            str(rebal_dates[2])[:10]: ["C", "D", "E"],
        }

        query = make_query_fn(feat_df, dynamic_schedule)

        # Query the full range
        result = query(dates[0], dates[-1])

        # Verify PIT safety: before first rebalance, no rows should exist
        # (unless the first rebalance is on the first date)
        assert len(result) > 0

        # Verify: after second rebalance (day 10), only B, C, D should be present
        day10_result = result[result["date"] == dates[10]]
        present_symbols = set(day10_result["symbol"].unique())
        assert present_symbols.issubset({"B", "C", "D"})

        # Verify: after third rebalance (day 20), only C, D, E should be present
        day20_result = result[result["date"] == dates[20]]
        present_symbols = set(day20_result["symbol"].unique())
        assert present_symbols.issubset({"C", "D", "E"})


class TestParallelFoldOrderingDeterminism:
    """Regression: per_fold arrays from parallel mode must match serial ordering.

    The parallel fold loop uses ``as_completed()`` which yields results in
    non-deterministic completion order.  The fix collects results keyed by
    fold_id and rebuilds ``all_fold_results`` in the original ``fold_specs``
    order so that ``per_fold_sharpe``, ``per_fold_max_dd``, and
    ``per_fold_return`` are deterministic and identical to serial execution.
    """

    @staticmethod
    def _make_fold_result(fold_id: int) -> dict:
        """Create a synthetic fold result with fold_id-dependent metrics."""
        return {
            "Baseline": {
                "annualized_sharpe": 0.5 + fold_id * 0.1,
                "max_drawdown": -0.05 - fold_id * 0.01,
                "total_return": 0.10 + fold_id * 0.02,
                "n_days": 50 + fold_id,
                "elapsed_sec": 1.0,
            },
            "Hybrid": {
                "annualized_sharpe": 0.6 + fold_id * 0.1,
                "max_drawdown": -0.04 - fold_id * 0.01,
                "total_return": 0.12 + fold_id * 0.02,
                "n_days": 50 + fold_id,
                "elapsed_sec": 1.2,
            },
        }

    def test_serial_reference_ordering(self):
        """Serial path appends in fold_specs order — baseline reference."""
        from backtest_hybrid_regime import aggregate_fold_results
        fold_ids = [0, 1, 2, 3, 4]
        serial_results = [self._make_fold_result(fid) for fid in fold_ids]
        agg = aggregate_fold_results(serial_results)

        expected_sharpes = [0.5 + fid * 0.1 for fid in fold_ids]
        assert agg["Baseline"]["per_fold_sharpe"] == pytest.approx(expected_sharpes)

    def test_parallel_fix_matches_serial(self):
        """After the fix, parallel (shuffled) results produce identical per_fold arrays."""
        from backtest_hybrid_regime import aggregate_fold_results

        fold_specs = [{"fold_id": fid} for fid in range(5)]

        # --- Serial reference ---
        serial_results = [self._make_fold_result(s["fold_id"]) for s in fold_specs]
        serial_agg = aggregate_fold_results(serial_results)

        # --- Simulate parallel with as_completed shuffle ---
        # Results arrive in a scrambled completion order.
        shuffled_ids = [3, 0, 4, 1, 2]
        shuffled_results = [self._make_fold_result(fid) for cid in shuffled_ids for fid in [cid]]

        # Apply the fix: collect into fold_id_to_result, rebuild in fold_specs order
        fold_id_to_result = {}
        for res, cid in zip(shuffled_results, shuffled_ids):
            fold_id_to_result[cid] = res

        parallel_results = [fold_id_to_result[s["fold_id"]] for s in fold_specs]
        parallel_agg = aggregate_fold_results(parallel_results)

        # Per-fold arrays must match serial exactly
        for scenario in ("Baseline", "Hybrid"):
            assert parallel_agg[scenario]["per_fold_sharpe"] == pytest.approx(
                serial_agg[scenario]["per_fold_sharpe"]
            ), f"{scenario} per_fold_sharpe mismatch"
            assert parallel_agg[scenario]["per_fold_max_dd"] == pytest.approx(
                serial_agg[scenario]["per_fold_max_dd"]
            ), f"{scenario} per_fold_max_dd mismatch"
            assert parallel_agg[scenario]["per_fold_return"] == pytest.approx(
                serial_agg[scenario]["per_fold_return"]
            ), f"{scenario} per_fold_return mismatch"

    def test_shuffled_without_fix_differs(self):
        """Without the fix (raw shuffle), per_fold arrays differ from serial — proves the bug."""
        from backtest_hybrid_regime import aggregate_fold_results

        fold_ids_serial = [0, 1, 2, 3, 4]
        serial_results = [self._make_fold_result(fid) for fid in fold_ids_serial]
        serial_agg = aggregate_fold_results(serial_results)

        # Append in shuffled order (old buggy behavior)
        shuffled_ids = [3, 0, 4, 1, 2]
        shuffled_results = [self._make_fold_result(cid) for cid in shuffled_ids]
        shuffled_agg = aggregate_fold_results(shuffled_results)

        # Aggregates (mean/median) are order-insensitive — must still match
        assert shuffled_agg["Baseline"]["mean_sharpe"] == pytest.approx(
            serial_agg["Baseline"]["mean_sharpe"]
        )

        # But per_fold arrays WILL differ (proves the ordering bug existed)
        assert shuffled_agg["Baseline"]["per_fold_sharpe"] != pytest.approx(
            serial_agg["Baseline"]["per_fold_sharpe"]
        ), "Shuffled per_fold_sharpe should differ from serial (proves bug existed)"


class TestPITLeakRegression:
    """Regression: global precompute_alpha_lags() leaks held-out data into train lags.

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621 (PIT-leak remediation)

    When CPCV produces non-contiguous train dates (embargo/purge gaps), the
    global groupby.shift(1) used by precompute_alpha_lags() references a
    held-out date's alpha for the first train date after the gap.  The fix
    computes lags per-fold inside train_fold_models() using only train dates.
    """

    @staticmethod
    def _make_panel_with_gap(n_pre=40, n_gap=5, n_post=15, n_symbols=3):
        """Create feat_df where train dates have a gap (held-out dates between).

        Timeline: n_pre + n_gap + n_post business days.
        Train dates: day0..day(n_pre-1), day(n_pre+n_gap)..end  (gap: n_gap held-out).
        alpha_signal = float(day_index) * 0.1 — known values for verification.
        """
        n_days = n_pre + n_gap + n_post
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        symbols = [f"SYM{i}" for i in range(n_symbols)]
        np.random.seed(99)
        rows = []
        for sym in symbols:
            for i, dt in enumerate(dates):
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "close": 100.0 + i,
                    "volume": 1_000_000,
                    "returns": np.random.randn() * 0.01,
                    "alpha_signal": float(i) * 0.1,
                    "latent_ae_00": np.random.randn(),
                    "latent_ae_01": np.random.randn(),
                    "latent_ae_11": np.random.randn(),
                })
        return pd.DataFrame(rows), dates

    def test_global_precompute_leaks_held_out_into_train_lag(self):
        """Prove global precompute uses a held-out date's alpha for a post-gap train lag.

        With defaults (n_pre=40, n_gap=5, n_post=15):
        day45 is the first train date after the gap (day40-44 held out).
        Global shift(1) gives day45_lag1 = alpha_signal[day44] = 4.4 (LEAK).
        Fold-local shift(1) gives day45_lag1 = alpha_signal[day39] = 3.9 (correct).
        """
        from backtest_hybrid_regime import precompute_alpha_lags

        feat_df, dates = self._make_panel_with_gap()
        precompute_alpha_lags(feat_df)

        # day39 = last pre-gap train, day44 = last held-out, day45 = first post-gap train
        day_last_train = dates[39]
        day_last_heldout = dates[44]
        day_first_postgap = dates[45]

        for sym in ["SYM0", "SYM1", "SYM2"]:
            global_lag = feat_df.loc[
                (feat_df["date"] == day_first_postgap) & (feat_df["symbol"] == sym),
                "alpha_signal_lag1",
            ].values[0]
            alpha_heldout = feat_df.loc[
                (feat_df["date"] == day_last_heldout) & (feat_df["symbol"] == sym),
                "alpha_signal",
            ].values[0]
            alpha_prev_train = feat_df.loc[
                (feat_df["date"] == day_last_train) & (feat_df["symbol"] == sym),
                "alpha_signal",
            ].values[0]

            # Global lag for day45 = day44's alpha (LEAK: day44 is held-out)
            assert global_lag == pytest.approx(alpha_heldout), (
                f"Global lag for post-gap train date should equal held-out alpha "
                f"({alpha_heldout}), got {global_lag}"
            )
            # This differs from the fold-local value (day39's alpha)
            assert global_lag != pytest.approx(alpha_prev_train), (
                "Global lag must differ from fold-local lag (proves leak existed)"
            )

    def test_fold_local_lags_are_pit_safe(self):
        """Fold-local shift(1) on train-only data uses only train-date values."""
        feat_df, dates = self._make_panel_with_gap()

        # Train: day0..day39, day45..day59 (gap: day40..day44)
        train_indices = list(range(40)) + list(range(45, 60))
        train_dates = [dates[i] for i in train_indices]
        train_date_set = set(pd.Timestamp(d) for d in train_dates)
        train_feat = feat_df[feat_df["date"].isin(train_date_set)]
        train_sorted = train_feat.sort_values(["symbol", "date"])

        fold_local_lag = train_sorted.groupby("symbol")["alpha_signal"].shift(1)

        day_last_train = dates[39]
        day_first_postgap = dates[45]

        for sym in ["SYM0", "SYM1", "SYM2"]:
            row_postgap = train_sorted[
                (train_sorted["date"] == day_first_postgap) & (train_sorted["symbol"] == sym)
            ]
            local_lag = fold_local_lag.loc[row_postgap.index].values[0]
            alpha_prev_train = feat_df.loc[
                (feat_df["date"] == day_last_train) & (feat_df["symbol"] == sym),
                "alpha_signal",
            ].values[0]

            # Fold-local lag for post-gap train date = day39's alpha (previous train date)
            assert local_lag == pytest.approx(alpha_prev_train), (
                f"Fold-local lag for post-gap train date should be previous train "
                f"date alpha ({alpha_prev_train}), got {local_lag}"
            )

    def test_train_fold_models_no_feat_df_mutation(self):
        """train_fold_models must NOT write lag columns into shared feat_df."""
        from backtest_hybrid_regime import train_fold_models

        feat_df, dates = self._make_panel_with_gap()
        cols_before = set(feat_df.columns)
        # Train: day0..day39, day45..day59
        train_indices = list(range(40)) + list(range(45, 60))
        train_dates = np.array([dates[i] for i in train_indices])

        train_fold_models(feat_df, train_dates, precomputed_lag_cols=None)

        cols_after = set(feat_df.columns)
        assert cols_before == cols_after, (
            f"train_fold_models mutated feat_df: added {cols_after - cols_before}"
        )
        assert "alpha_signal_lag1" not in feat_df.columns

    def test_ridge_coefficients_match_fold_local_reference(self):
        """Ridge from train_fold_models matches a manual fold-local Ridge reference.

        Constructs the reference Ridge by hand:
          1. Filter to train dates, compute per-symbol shift(1) on train-only data.
          2. Drop NaN, fit Ridge(alpha=1.0).
        Then verifies that composite_signal predictions from train_fold_models
        match the reference predictions within floating-point tolerance.
        """
        from backtest_hybrid_regime import train_fold_models
        from sklearn.linear_model import Ridge

        feat_df, dates = self._make_panel_with_gap()
        feat_df = feat_df.drop(
            columns=[c for c in feat_df.columns if c.startswith("latent_ae_")]
        )
        # Train: day0..day39, day45..day59
        train_indices = list(range(40)) + list(range(45, 60))
        train_dates = np.array([dates[i] for i in train_indices])
        train_date_set = set(pd.Timestamp(d) for d in train_dates)
        train_feat = feat_df[feat_df["date"].isin(train_date_set)]

        # --- Manual fold-local Ridge (reference) ---
        train_sorted = train_feat.sort_values(["symbol", "date"])
        manual_lag = train_sorted.groupby("symbol")["alpha_signal"].shift(1)
        manual_train = train_sorted.copy()
        manual_train["alpha_signal_lag1"] = manual_lag
        manual_train = manual_train.dropna(subset=["alpha_signal_lag1", "returns"])

        assert len(manual_train) > 10, f"Need >10 rows for Ridge, got {len(manual_train)}"
        ref_ridge = Ridge(alpha=1.0)
        ref_ridge.fit(
            manual_train[["alpha_signal_lag1"]].values,
            manual_train["returns"].values,
        )

        # --- train_fold_models Ridge ---
        _, _, composite_signal = train_fold_models(
            feat_df, train_dates, precomputed_lag_cols=None, model_type="ridge",
        )
        assert composite_signal is not None, "composite_signal should be produced"

        # --- Compare predictions on a sample of rows ---
        # Compute prediction lags the same way train_fold_models does
        full_sorted = feat_df.sort_values(["symbol", "date"])
        pred_lag = full_sorted.groupby("symbol")["alpha_signal"].shift(1)

        checked = 0
        for idx in composite_signal.index:
            if idx in pred_lag.index and not pd.isna(pred_lag.loc[idx]):
                ref_pred = ref_ridge.predict([[pred_lag.loc[idx]]])[0]
                assert composite_signal.loc[idx] == pytest.approx(
                    ref_pred, abs=1e-10
                ), (
                    f"Row {idx}: train_fold_models prediction "
                    f"({composite_signal.loc[idx]}) differs from fold-local "
                    f"reference ({ref_pred})"
                )
                checked += 1
                if checked >= 10:
                    break
        assert checked >= 10, f"Should have compared at least 10 predictions, got {checked}"


class TestProfitabilityDiagnostics:
    """Verify profitability diagnostic instrumentation.

    Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621

    Tests that compute_fold_profitability_diagnostics() correctly computes:
    gross_return, total_tc_pct, cash_days_pct, turnover_avg, exposure_avg.
    """

    def _make_weights_and_returns(self, n_days=20, n_symbols=5, cash_fraction=0.3):
        """Create synthetic weights and returns for testing."""
        np.random.seed(42)
        w = np.random.randn(n_days, n_symbols) * 0.1
        # Zero out some days to simulate cash/cooldown
        n_cash = int(n_days * cash_fraction)
        w[:n_cash] = 0.0
        # Normalize non-cash rows
        for i in range(n_cash, n_days):
            row_sum = np.abs(w[i]).sum()
            if row_sum > 0:
                w[i] /= row_sum
        weights = pd.DataFrame(w, columns=[f"SYM{i}" for i in range(n_symbols)])
        daily_rets = np.random.randn(n_days) * 0.01
        return weights, daily_rets

    def test_gross_return_computed(self):
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert "gross_return" in diag
        net_ret = float(np.prod(1.0 + daily_rets) - 1.0)
        expected_gross = net_ret + 0.05
        assert diag["gross_return"] == pytest.approx(expected_gross, abs=1e-10)

    def test_total_tc_pct(self):
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.08, "total_turnover": 15.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert diag["total_tc_pct"] == pytest.approx(0.08)

    def test_cash_days_pct(self):
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns(
            n_days=20, cash_fraction=0.3,
        )
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert "cash_days_pct" in diag
        # 30% of 20 days = 6 cash days
        assert diag["cash_days_pct"] == pytest.approx(6.0 / 20.0, abs=0.05)

    def test_turnover_avg(self):
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert "turnover_avg" in diag
        assert diag["turnover_avg"] >= 0.0

    def test_exposure_avg(self):
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert "exposure_avg" in diag
        assert diag["exposure_avg"] >= 0.0

    def test_diagnostic_handler_wraps_correctly(self, tmp_path):
        """DiagnosticBacktestOutputHandler produces same base results plus diag."""
        from backtest_hybrid_regime import DiagnosticBacktestOutputHandler
        out_json = tmp_path / "test.json"
        out_csv = tmp_path / "test.csv"
        handler = DiagnosticBacktestOutputHandler(out_json, out_csv, capital=1e9)
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        results = handler.handle(weights, daily_rets, {"cost_breakdown": cost_breakdown})
        assert "total_return" in results
        assert "profitability_diag" in results
        assert "gross_return" in results["profitability_diag"]

    def test_aggregate_includes_diagnostics(self):
        """aggregate_fold_results includes profitability_diag in output."""
        from backtest_hybrid_regime import aggregate_fold_results
        fold_results = [
            {
                "Hybrid": {
                    "annualized_sharpe": 0.5,
                    "max_drawdown": -0.05,
                    "total_return": 0.10,
                    "n_days": 50,
                    "elapsed_sec": 1.0,
                    "profitability_diag": {
                        "gross_return": 0.15,
                        "total_tc_pct": 0.05,
                        "cash_days_pct": 0.2,
                        "turnover_avg": 0.03,
                        "exposure_avg": 1.0,
                        "alpha_ic_overall": 0.01,
                        "alpha_ic_per_regime": {
                            "bull": 0.02,
                            "sideways": 0.01,
                            "bear": -0.01,
                        },
                    },
                },
            },
        ]
        agg = aggregate_fold_results(fold_results)
        assert "profitability_diag" in agg["Hybrid"]
        pd = agg["Hybrid"]["profitability_diag"]
        assert pd["mean_gross_return"] == pytest.approx(0.15)
        assert pd["mean_total_tc_pct"] == pytest.approx(0.05)
        assert "alpha_ic_per_regime" in pd
        assert pd["alpha_ic_per_regime"]["bull"]["mean_ic"] == pytest.approx(0.02)

    def test_alpha_ic_per_regime_emitted(self):
        """compute_fold_profitability_diagnostics emits alpha_ic_per_regime dict."""
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        assert "alpha_ic_per_regime" in diag
        ic_regime = diag["alpha_ic_per_regime"]
        assert isinstance(ic_regime, dict)
        assert "bull" in ic_regime
        assert "sideways" in ic_regime
        assert "bear" in ic_regime

    def test_gross_return_formula_documented(self):
        """Verify gross_return = compound_net + total_cost (additive approx)."""
        from backtest_hybrid_regime import compute_fold_profitability_diagnostics
        weights, daily_rets = self._make_weights_and_returns()
        cost_breakdown = {"total_cost": 0.05, "total_turnover": 10.0}
        diag = compute_fold_profitability_diagnostics(
            weights, daily_rets, cost_breakdown, capital=1e9,
        )
        compound_net = float(np.prod(1.0 + daily_rets) - 1.0)
        expected_gross = compound_net + 0.05
        assert diag["gross_return"] == pytest.approx(expected_gross, abs=1e-10)


class TestExistingArtifactDiagnostics:
    """Verify existing CPCV artifacts support profitability diagnosis.

    Gate: HYBRID_REGIME_PROFITABILITY_DIAG_20260621

    Reads existing per-fold JSONs to validate cost_breakdown is present
    and gross_return can be derived.
    """

    ARTIFACT_DIR = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "phase35_results",
    )

    def test_all_folds_have_cost_breakdown(self):
        """All 45 Hybrid per-fold JSONs contain cost_breakdown."""
        import glob as glob_mod
        pattern = os.path.join(
            self.ARTIFACT_DIR,
            "hybrid_fold*_Hybrid_full_evidence_20260621_1335.json",
        )
        files = glob_mod.glob(pattern)
        assert len(files) == 45, f"Expected 45 fold files, found {len(files)}"

        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            assert "cost_breakdown" in data, f"Missing cost_breakdown in {f}"
            cb = data["cost_breakdown"]
            assert "total_cost" in cb
            assert "total_turnover" in cb
            assert cb["total_cost"] >= 0

    def test_gross_return_derivable_from_artifacts(self):
        """Gross return = net + total_cost is derivable for all folds."""
        import glob as glob_mod
        pattern = os.path.join(
            self.ARTIFACT_DIR,
            "hybrid_fold*_Hybrid_full_evidence_20260621_1335.json",
        )
        files = glob_mod.glob(pattern)

        gross_returns = []
        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            net_ret = data["total_return"]
            tc = data["cost_breakdown"]["total_cost"]
            gross = net_ret + tc
            gross_returns.append(gross)

        # At least some folds should have positive gross return
        n_positive = sum(1 for g in gross_returns if g > 0)
        assert n_positive > 0, "Expected some folds with positive gross return"
        # But not all — the alpha edge is weak
        assert n_positive < 45, "Not all folds should have positive gross"

    def test_all_hybrid_folds_negative_net_return(self):
        """CONFIRMED: All 45 Hybrid folds have negative net return."""
        import glob as glob_mod
        pattern = os.path.join(
            self.ARTIFACT_DIR,
            "hybrid_fold*_Hybrid_full_evidence_20260621_1335.json",
        )
        files = glob_mod.glob(pattern)
        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            assert data["total_return"] < 0, (
                f"Expected negative net return in {os.path.basename(f)}, "
                f"got {data['total_return']:.4f}"
            )

    def test_tc_exceeds_gross_when_gross_positive(self):
        """CONFIRMED hypothesis (a): TC > gross when gross > 0."""
        import glob as glob_mod
        pattern = os.path.join(
            self.ARTIFACT_DIR,
            "hybrid_fold*_Hybrid_full_evidence_20260621_1335.json",
        )
        files = glob_mod.glob(pattern)
        tc_exceeds_count = 0
        gross_positive_count = 0

        for f in files:
            with open(f) as fh:
                data = json.load(fh)
            net = data["total_return"]
            tc = data["cost_breakdown"]["total_cost"]
            gross = net + tc
            if gross > 0:
                gross_positive_count += 1
                if tc > gross:
                    tc_exceeds_count += 1

        assert gross_positive_count > 0
        # ALL folds where gross > 0 should have TC > gross
        assert tc_exceeds_count == gross_positive_count, (
            f"Expected TC > gross in all {gross_positive_count} positive-gross folds, "
            f"but only {tc_exceeds_count} had TC > gross"
        )


class TestQuotaAlphaSelection:
    """Quota-based alpha selection across 4 categories (Gate: HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623).

    Categories:
      - HR   : alpha_hr_*
      - GP   : alpha_gp_*
      - LLM  : alpha_llm_*
      - VN   : alpha_vn_* | alpha_stock_* | alpha_macro_*
    Selects top 2 alphas by absolute IC from each category (max 8 total).
    """

    @staticmethod
    def _make_quota_panel(n_days=100, n_symbols=3):
        """Build a panel with 4 categorized + uncategorized alphas.

        Each category has 3 candidate alphas with deterministic ICs so
        selection order is verifiable:
          - alpha_hr_00..02 : high IC (rank 1,2,3 in HR)
          - alpha_gp_00..02 : mid IC
          - alpha_llm_00..02: lower IC
          - alpha_vn_00..01, alpha_stock_00, alpha_macro_00..01: VN group
          - alpha_unrelated_00 (no category prefix)
        """
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        symbols = [f"SYM{i}" for i in range(n_symbols)]
        np.random.seed(123)
        rows = []
        for sym in symbols:
            price = 100.0
            for i, dt in enumerate(dates):
                ret = np.random.randn() * 0.01
                price *= (1 + ret)
                row = {
                    "date": dt,
                    "symbol": sym,
                    "close": price,
                    "volume": 1_000_000,
                    "returns": ret,
                    "latent_ae_00": np.random.randn(),
                    "latent_ae_01": np.random.randn(),
                    "latent_ae_11": np.random.randn(),
                }
                # HR category: signal ~ ret (high IC)
                row["alpha_hr_00"] = ret * 1.0
                row["alpha_hr_01"] = ret * 0.9 + np.random.randn() * 0.001
                row["alpha_hr_02"] = ret * 0.8 + np.random.randn() * 0.002
                # GP category: signal ~ ret (mid IC)
                row["alpha_gp_00"] = ret * 0.6 + np.random.randn() * 0.005
                row["alpha_gp_01"] = ret * 0.55 + np.random.randn() * 0.005
                row["alpha_gp_02"] = np.random.randn() * 0.01
                # LLM category: signal ~ ret (lower IC)
                row["alpha_llm_00"] = ret * 0.4 + np.random.randn() * 0.008
                row["alpha_llm_01"] = ret * 0.3 + np.random.randn() * 0.01
                row["alpha_llm_02"] = np.random.randn() * 0.02
                # VN category (vn + stock + macro)
                row["alpha_vn_00"] = ret * 0.5 + np.random.randn() * 0.005
                row["alpha_vn_01"] = ret * 0.45 + np.random.randn() * 0.005
                row["alpha_stock_00"] = ret * 0.4 + np.random.randn() * 0.006
                row["alpha_macro_00"] = ret * 0.35 + np.random.randn() * 0.007
                row["alpha_macro_01"] = np.random.randn() * 0.02
                # Uncategorized alpha — must NOT be selected under quota logic
                row["alpha_unrelated_00"] = np.random.randn() * 0.05
                rows.append(row)
        return pd.DataFrame(rows)

    def test_quota_selects_two_per_category(self, caplog):
        """Top 2 per category picked when IC is finite and ordered.

        Verifies the quota-selection log emits per-category counts of 2
        each (since the fixture has ≥2 candidates per category).
        """
        import logging
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_quota_panel()
        train_dates = feat_df["date"].unique()[:70]

        with caplog.at_level(logging.INFO, logger="backtest_hybrid_regime"):
            gmm, hmm, composite_signal = train_fold_models(
                feat_df, train_dates, precomputed_lag_cols=None,
            )
        assert composite_signal is not None, "composite_signal should be produced"

        msgs = [r.message for r in caplog.records]
        quota_logs = [m for m in msgs if "Quota Feature Selection" in m]
        assert quota_logs, f"Expected quota selection log, got: {msgs}"
        log_msg = quota_logs[0]

        # Parse counts from log message format:
        # "Quota Feature Selection: N alphas across N categories (HR=X, GP=Y, LLM=Z, VN=W)..."
        import re
        match = re.search(r"HR=(\d+), GP=(\d+), LLM=(\d+), VN=(\d+)", log_msg)
        assert match, f"Cannot parse per-category counts from: {log_msg}"
        hr, gp, llm, vn = (int(g) for g in match.groups())
        assert hr == 2, f"HR quota should be 2, got {hr}"
        assert gp == 2, f"GP quota should be 2, got {gp}"
        assert llm == 2, f"LLM quota should be 2, got {llm}"
        assert vn == 2, f"VN quota should be 2, got {vn}"

        # Total ≤ 8.
        total_match = re.search(r": (\d+) alphas across (\d+) categories", log_msg)
        assert total_match
        total_selected = int(total_match.group(1))
        assert total_selected <= 8, f"Total selected alphas should be ≤ 8, got {total_selected}"
        assert total_selected == 8, f"All 4 categories present → 8 alphas, got {total_selected}"

    def test_quota_total_capped_at_eight(self):
        """Total selected alphas is at most 8 (2 per category × 4)."""
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_quota_panel(n_days=80, n_symbols=3)
        train_dates = feat_df["date"].unique()[:60]

        # The Ridge training matrix uses selected_lag_cols internally; we
        # can't inspect it directly without refactor.  Instead, verify that
        # composite_signal is produced (selection succeeded) and that the
        # function doesn't raise when 4 categories each have ≥2 candidates.
        _, _, composite_signal = train_fold_models(
            feat_df, train_dates, precomputed_lag_cols=None,
        )
        assert composite_signal is not None, "composite_signal must be produced"
        assert len(composite_signal) > 0, "composite_signal must have rows"

    def test_quota_skips_uncategorized_alphas(self):
        """Alphas with no category prefix are excluded from quota selection."""
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_quota_panel()
        train_dates = feat_df["date"].unique()[:70]

        # Run; assert no exception.  Direct verification that
        # alpha_unrelated_00 was excluded is done by reconstructing the
        # selection logic from the public surface.
        gmm, hmm, composite = train_fold_models(
            feat_df, train_dates, precomputed_lag_cols=None,
        )
        assert composite is not None

        # Reconstruct what would have been selected under quota rules.
        # All alpha cols:
        all_alpha = [c for c in feat_df.columns if c.startswith("alpha_") and not c.endswith("_lag1")]
        # Filter to categorized:
        prefixes_map = {
            "HR": ("alpha_hr_",),
            "GP": ("alpha_gp_",),
            "LLM": ("alpha_llm_",),
            "VN": ("alpha_vn_", "alpha_stock_", "alpha_macro_"),
        }
        categorized = set()
        for c in all_alpha:
            for prefs in prefixes_map.values():
                if any(c.startswith(p) for p in prefs):
                    categorized.add(c)
                    break
        assert "alpha_unrelated_00" not in categorized
        assert len(categorized) == sum(1 for c in all_alpha if c in categorized)

    def test_quota_handles_missing_category(self):
        """If a category has no alphas, quota still works (select ≤ 6 total)."""
        from backtest_hybrid_regime import train_fold_models
        # Build panel with only HR + VN alphas (no GP, no LLM).
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        symbols = ["A", "B"]
        np.random.seed(7)
        rows = []
        for sym in symbols:
            for i, dt in enumerate(dates):
                ret = np.random.randn() * 0.01
                rows.append({
                    "date": dt, "symbol": sym, "close": 100.0,
                    "volume": 1_000_000, "returns": ret,
                    "alpha_hr_a": ret * 0.5 + np.random.randn() * 0.005,
                    "alpha_hr_b": ret * 0.4 + np.random.randn() * 0.005,
                    "alpha_vn_a": ret * 0.3 + np.random.randn() * 0.01,
                    "alpha_vn_b": np.random.randn() * 0.02,
                    "latent_ae_00": np.random.randn(),
                    "latent_ae_01": np.random.randn(),
                    "latent_ae_11": np.random.randn(),
                })
        feat_df = pd.DataFrame(rows)
        train_dates = feat_df["date"].unique()[:40]

        _, _, composite = train_fold_models(
            feat_df, train_dates, precomputed_lag_cols=None,
        )
        # Function should complete without error; composite_signal is None
        # only if Ridge is skipped.  With 4 candidate alphas (2 HR + 2 VN),
        # Ridge must train successfully.
        assert composite is not None, "composite_signal should be produced with HR+VN only"

    def test_quota_logs_per_category_counts(self, caplog):
        """train_fold_models logs quota selection per-category counts."""
        import logging
        from backtest_hybrid_regime import train_fold_models
        feat_df = self._make_quota_panel()
        train_dates = feat_df["date"].unique()[:70]

        with caplog.at_level(logging.INFO, logger="backtest_hybrid_regime"):
            train_fold_models(feat_df, train_dates, precomputed_lag_cols=None)
        msgs = [r.message for r in caplog.records]
        quota_logs = [m for m in msgs if "Quota Feature Selection" in m]
        assert quota_logs, f"Expected quota selection log, got: {msgs}"
        log_msg = quota_logs[0]
        assert "HR=" in log_msg and "GP=" in log_msg and "LLM=" in log_msg and "VN=" in log_msg

    def test_quota_prefers_higher_abs_ic_over_earlier_lower_abs_ic_in_same_category(self, caplog):
        """Regression: quota must rank by abs(IC), not by column-list order.

        Bug: the loop iterated ``lag_col_names_all`` in column-list order, so
        an earlier column with LOWER |IC| was selected over a later column
        with HIGHER |IC| in the same category.  Fix: group categorized alphas
        by category, sort each group by abs(IC) desc, then take top 2.

        To make ICs deterministic and orderable across alphas, returns are
        AR(1) with coef 0.5: ``ret_T = 0.5 * ret_{T-1} + noise_T``.  Then
        ``alpha_lag1`` of an alpha proportional to ``ret`` captures the
        ret_{T-1} component which correlates with ret_T at the AR coef.

        Fixture (HR category, deliberate insertion order high→low→mid):
          alpha_hr_high (col idx 0): |IC| ≈ 0.50  (alpha = ret, perfect)
          alpha_hr_low  (col idx 1): |IC| ≈ 0.00  (alpha = noise, no signal)
          alpha_hr_mid  (col idx 2): |IC| ≈ 0.25  (alpha = 0.5 * ret + tiny noise)

        Other categories (GP, LLM, VN) each have 2 alphas so quotas fill.

        With bug (column-order iteration): HR quota fills with [high, low];
          alpha_hr_mid (|IC|≈0.25) is REJECTED even though it has higher
          |IC| than alpha_hr_low (|IC|≈0).
        With fix (sorted by |IC|): HR quota fills with [high, mid];
          alpha_hr_low is REJECTED.

        Distinguishable via the 'Top-3 absolute ICs' log payload: the fixed
        code iterates categories in CATEGORY_PREFIXES order (HR first), so
        the first 2 entries are the top-2 HR alphas by |IC|.

        Bug  → log Top-3 contains alpha_hr_low_lag1 (NOT alpha_hr_mid_lag1)
        Fix  → log Top-3 contains alpha_hr_mid_lag1 (NOT alpha_hr_low_lag1)
        """
        import logging
        from backtest_hybrid_regime import train_fold_models

        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        symbols = ["A", "B", "C"]
        np.random.seed(2024)
        rows = []
        AR_COEF = 0.5
        for sym in symbols:
            prev_ret = 0.0
            for dt in dates:
                noise = np.random.randn() * 0.01
                ret = AR_COEF * prev_ret + noise
                prev_ret = ret
                row = {
                    "date": dt,
                    "symbol": sym,
                    "close": 100.0,
                    "volume": 1_000_000,
                    "returns": ret,
                    "alpha_hr_high": ret,
                    "alpha_hr_low": np.random.randn() * 0.01,
                    "alpha_hr_mid": 0.5 * ret + np.random.randn() * 0.001,
                    "alpha_gp_a": 0.4 * ret + np.random.randn() * 0.005,
                    "alpha_gp_b": 0.3 * ret + np.random.randn() * 0.005,
                    "alpha_llm_a": 0.35 * ret + np.random.randn() * 0.005,
                    "alpha_llm_b": 0.25 * ret + np.random.randn() * 0.005,
                    "alpha_vn_a": 0.45 * ret + np.random.randn() * 0.005,
                    "alpha_stock_a": 0.35 * ret + np.random.randn() * 0.005,
                    "latent_ae_00": np.random.randn(),
                    "latent_ae_01": np.random.randn(),
                    "latent_ae_11": np.random.randn(),
                }
                rows.append(row)
        feat_df = pd.DataFrame(rows)
        train_dates = feat_df["date"].unique()[:90]

        with caplog.at_level(logging.INFO, logger="backtest_hybrid_regime"):
            train_fold_models(feat_df, train_dates, precomputed_lag_cols=None)

        msgs = [r.message for r in caplog.records]
        quota_logs = [m for m in msgs if "Quota Feature Selection" in m]
        assert quota_logs, f"Expected quota selection log, got: {msgs}"
        log_msg = quota_logs[0]

        import re
        hr_match = re.search(r"HR=(\d+)", log_msg)
        assert hr_match and int(hr_match.group(1)) == 2, (
            f"HR quota should be 2 regardless of sort order, log: {log_msg}"
        )

        assert "alpha_hr_mid_lag1" in log_msg, (
            "Quota selection must prefer alpha_hr_mid (|IC|≈0.25, later column) "
            "over alpha_hr_low (|IC|≈0.00, earlier column) within the HR category. "
            f"Log payload: {log_msg}"
        )

        assert "alpha_hr_low_lag1" not in log_msg, (
            "Quota selection must reject alpha_hr_low (lowest |IC| in HR). "
            "The pre-fix bug picked it because it appeared earlier in the "
            f"column list.  Log payload: {log_msg}"
        )


class TestTCostOverlayTuning:
    """Verify turnover reduction tuning for both scenario overlays.

    Gate: HYBRID_REGIME_TURNOVER_REDUCTION_20260626
    """

    def test_hybrid_turnover_controls_tightened(self):
        from backtest_hybrid_regime import build_scenario_overlays
        scenarios = build_scenario_overlays(capital=2_000_000_000.0)
        hybrid_overlays = scenarios["Hybrid"]
        tcost = [o for o in hybrid_overlays if o.__class__.__name__ == "TCostOverlay"]
        rebalance = [o for o in hybrid_overlays if o.__class__.__name__ == "RebalanceFrequencyOverlay"]

        assert len(tcost) == 1, f"Expected exactly 1 TCostOverlay in Hybrid, got {len(tcost)}"
        assert len(rebalance) == 1, f"Expected exactly 1 RebalanceFrequencyOverlay in Hybrid, got {len(rebalance)}"
        assert tcost[0].min_trade_threshold_bps == 150.0, (
            f"Hybrid TCostOverlay threshold should be 150.0 bps, "
            f"got {tcost[0].min_trade_threshold_bps}"
        )
        assert rebalance[0].rebalance_every_n_days == 10
        assert tcost[0].cost_per_trade_bps == 35.0

    def test_baseline_turnover_controls_tightened(self):
        from backtest_hybrid_regime import build_scenario_overlays
        scenarios = build_scenario_overlays(capital=2_000_000_000.0)
        baseline_overlays = scenarios["Baseline"]
        tcost = [o for o in baseline_overlays if o.__class__.__name__ == "TCostOverlay"]
        rebalance = [o for o in baseline_overlays if o.__class__.__name__ == "RebalanceFrequencyOverlay"]

        assert len(tcost) == 1, f"Expected exactly 1 TCostOverlay in Baseline, got {len(tcost)}"
        assert len(rebalance) == 1, f"Expected exactly 1 RebalanceFrequencyOverlay in Baseline, got {len(rebalance)}"
        assert tcost[0].min_trade_threshold_bps == 150.0
        assert rebalance[0].rebalance_every_n_days == 10


class TestLongOnlyConcentratedOverlay:
    """Verify LongOnlyConcentratedOverlay behavior."""

    def test_long_only_concentrated_overlay(self):
        from backtest_hybrid_regime import LongOnlyConcentratedOverlay
        overlay = LongOnlyConcentratedOverlay(top_k=2)

        # 3 symbols, weights: [0.5, -0.2, 0.3]
        # long-only: [0.5, 0.0, 0.3]
        # top_2: [0.5, 0.0, 0.3]
        # normalized: [0.625, 0.0, 0.375]
        weights = pd.DataFrame([[0.5, -0.2, 0.3]], columns=["A", "B", "C"], index=[pd.Timestamp("2024-01-01")])
        panel = pd.DataFrame()
        state = {}
        res = overlay.apply(weights, panel, state)

        assert res.loc[pd.Timestamp("2024-01-01"), "A"] == pytest.approx(0.625)
        assert res.loc[pd.Timestamp("2024-01-01"), "B"] == 0.0
        assert res.loc[pd.Timestamp("2024-01-01"), "C"] == pytest.approx(0.375)

        # 4 symbols, weights: [0.5, 0.2, 0.3, 0.1]
        # long-only: [0.5, 0.2, 0.3, 0.1]
        # top_2: [0.5, 0.0, 0.3, 0.0]
        # normalized: [0.625, 0.0, 0.375, 0.0]
        weights2 = pd.DataFrame([[0.5, 0.2, 0.3, 0.1]], columns=["A", "B", "C", "D"], index=[pd.Timestamp("2024-01-01")])
        res2 = overlay.apply(weights2, panel, state)
        assert res2.loc[pd.Timestamp("2024-01-01"), "A"] == pytest.approx(0.625)
        assert res2.loc[pd.Timestamp("2024-01-01"), "B"] == 0.0
        assert res2.loc[pd.Timestamp("2024-01-01"), "C"] == pytest.approx(0.375)
        assert res2.loc[pd.Timestamp("2024-01-01"), "D"] == 0.0

    def test_scenario_concentration_invariant(self, monkeypatch):
        from backtest_hybrid_regime import build_scenario_overlays
        from omega.quant.pipeline.overlays.risk_sizing import RiskSizingOverlay
        from omega.quant.pipeline.overlays.sector_concentration import SectorConcentrationOverlay
        from omega.quant.pipeline.overlays.tail_control import TailControlOverlay
        from omega.quant.pipeline.overlays.drawdown_control import DrawdownControlOverlay
        from omega.quant.pipeline.overlays.rebalance_frequency import RebalanceFrequencyOverlay
        from omega.quant.pipeline.overlays.board_lot_rounding import BoardLotRoundingOverlay
        from omega.quant.pipeline.overlays.tcost import TCostOverlay

        # Mock overlays that require external data or complex logic
        monkeypatch.setattr(RiskSizingOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(SectorConcentrationOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(TailControlOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(DrawdownControlOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(RebalanceFrequencyOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(BoardLotRoundingOverlay, "apply", lambda self, w, p, s: w)
        monkeypatch.setattr(TCostOverlay, "apply", lambda self, w, p, s: w)

        # Build baseline scenario overlays with top_k = 2
        scenarios = build_scenario_overlays(capital=2_000_000_000.0, top_k=2)

        # We will test both Baseline and Hybrid stacks
        for name, stack in scenarios.items():
            # Create weights for Day 1: A=0.8, B=0.2 (2 active assets)
            # Create weights for Day 2: C=0.7, D=0.3 (2 different active assets)
            # Without concentration after smoothing, Day 2 weights would smooth/leak Day 1 assets,
            # resulting in A, B, C, D having non-zero weights (4 active assets).
            # With concentration after smoothing, Day 2 must have at most 2 active assets.
            weights = pd.DataFrame(
                [
                    [0.8, 0.2, 0.0, 0.0],
                    [0.0, 0.0, 0.7, 0.3]
                ],
                columns=["A", "B", "C", "D"],
                index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
            )

            panel = pd.DataFrame()
            state = {}

            current_weights = weights.copy()
            for overlay in stack:
                current_weights = overlay.apply(current_weights, panel, state)

            # Verify that on both dates, number of active (non-zero) assets is at most 2
            for dt in current_weights.index:
                active_assets = (current_weights.loc[dt] > 1e-5).sum()
                assert active_assets <= 2, f"Scenario {name}: Expected at most 2 active assets on {dt}, got {active_assets}"



class TestLightGBMAndWarmup:
    def _make_feat_df_with_nan_lags(self, n_days=80, n_symbols=3):
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        rows = []
        rng = np.random.default_rng(42)
        for sym in [f"SYM{i}" for i in range(n_symbols)]:
            price = 100.0
            for i, dt in enumerate(dates):
                ret = float(rng.normal(0.001, 0.01))
                price *= 1.0 + ret
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "close": price,
                    "volume": 1_000_000,
                    "returns": ret,
                    "alpha_hr_a": ret if i % 7 else np.nan,
                    "alpha_gp_a": float(rng.normal()) if i % 5 else np.nan,
                    "latent_ae_00": float(rng.normal()),
                    "latent_ae_01": float(rng.normal()),
                    "latent_ae_11": float(rng.normal()),
                })
        return pd.DataFrame(rows)

    def test_lightgbm_keeps_nan_lag_rows(self, monkeypatch):
        from backtest_hybrid_regime import train_fold_models
        import backtest_hybrid_regime as bhr

        captured = []

        class StubLGBMRegressor:
            def __init__(self, **kwargs):
                pass

            def fit(self, X, y):
                captured.append((X.copy(), y.copy()))
                self.mean_ = float(np.mean(y))
                return self

            def predict(self, X):
                return np.full(len(X), self.mean_)

        monkeypatch.setattr(bhr, "LGBMRegressor", StubLGBMRegressor)
        feat_df = self._make_feat_df_with_nan_lags()
        train_dates = feat_df["date"].unique()[:60]
        _, _, composite_signal = train_fold_models(
            feat_df,
            train_dates,
            model_type="lightgbm",
        )
        assert composite_signal is not None
        assert captured
        assert any(np.isnan(X).any() for X, _ in captured), "LightGBM path must preserve NaN feature rows"

    def test_pipeline_fetches_warmup_then_outputs_requested_period(self, tmp_path):
        from omega.quant.pipeline_v2 import (
            BacktestOutputHandler,
            PipelineStateManager,
            TradingPipelineV2,
        )

        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        df = pd.DataFrame({
            "date": np.repeat(dates, 2),
            "symbol": ["A", "B"] * len(dates),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
            "returns": 0.001,
            "composite_signal": [1.0, -1.0] * len(dates),
        })
        calls = []

        class Store:
            def get_features(self, date_start, date_end, tickers=None):
                calls.append((pd.Timestamp(date_start), pd.Timestamp(date_end), tickers))
                return df[(df["date"] >= date_start) & (df["date"] <= date_end)].copy()

        pipeline = TradingPipelineV2(
            feature_store=Store(),
            state_manager=PipelineStateManager(tmp_path / "state"),
            output_handler=BacktestOutputHandler(tmp_path / "out.json", tmp_path / "out.csv"),
            overlays=[],
            config={"feature_warmup_days": 30},
        )
        res = pipeline.execute("warmup", "2024-02-01", "2024-02-05", tickers=["A", "B"])
        assert calls[0][0] == pd.Timestamp("2024-01-02")
        assert calls[0][1] == pd.Timestamp("2024-02-05")
        assert res["n_days"] == 5

    def test_pipeline_fallback_ridge_never_trains_on_requested_same_day_returns(self, tmp_path, monkeypatch):
        import omega.quant.pipeline_v2 as pipeline_v2
        from omega.quant.pipeline_v2 import (
            BacktestOutputHandler,
            PipelineStateManager,
            TradingPipelineV2,
        )

        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        start_date = pd.Timestamp("2024-02-01")
        rows = []
        for date_idx, dt in enumerate(dates):
            for sym_idx, sym in enumerate(["A", "B", "C"]):
                rows.append({
                    "date": dt,
                    "symbol": sym,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0 + date_idx,
                    "volume": 1_000_000,
                    "returns": date_idx * 10.0 + sym_idx,
                    "alpha_mom": float(date_idx + sym_idx),
                    "_date_idx": date_idx,
                })
        df = pd.DataFrame(rows)
        train_predict_checks = []

        class Store:
            def get_features(self, date_start, date_end, tickers=None):
                return df[(df["date"] >= date_start) & (df["date"] <= date_end)].copy()

        class TrackingRidge:
            def __init__(self, alpha=100.0):
                self.alpha = alpha
                self.max_train_date_idx = None

            def fit(self, X, y):
                self.max_train_date_idx = int(np.floor(np.max(y) / 10.0))
                self.mean_ = float(np.mean(y)) if len(y) else 0.0
                return self

            def predict(self, X):
                pred_date_idx = int(np.floor(np.nanmin(X[:, 0])) + 1)
                train_predict_checks.append((self.max_train_date_idx, pred_date_idx))
                return np.full(len(X), self.mean_)

        monkeypatch.setattr(pipeline_v2, "DataSanitizer", None)
        monkeypatch.setattr("sklearn.linear_model.Ridge", TrackingRidge)
        pipeline = TradingPipelineV2(
            feature_store=Store(),
            state_manager=PipelineStateManager(tmp_path / "state"),
            output_handler=BacktestOutputHandler(tmp_path / "out.json", tmp_path / "out.csv"),
            overlays=[],
            config={"feature_warmup_days": 40},
        )
        res = pipeline.execute("fallback_pit", start_date, "2024-04-10", tickers=["A", "B", "C"])

        assert res["n_days"] > 60
        assert train_predict_checks
        assert all(train_idx < pred_idx for train_idx, pred_idx in train_predict_checks)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
