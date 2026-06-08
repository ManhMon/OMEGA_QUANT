"""
Stage 6.3 Active Drawdown Control Tests
[L2-Impl:Role9-Backend] - 2026-05-23

Verifies drawdown control in Phase35WalkForwardEngine:
  1. No-breach path leaves baseline behaviour unchanged
  2. Breach path stops out to cash after first breach date
  3. Breach-day return is preserved; zeroing starts next date
  4. Controlled path improves total return / max drawdown vs uncontrolled
  5. PIT Safety: control uses only in-fold realised test returns
  6. Sharpe and Max DD are computed from daily aggregated returns, not row-level
     (day-vs-row mismatch regression test)

PIT Safety: No real data loaded. All data is synthetic in-memory.
"""

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


def _make_fake_alpha_module():
    class _FakeAlphaModule:
        @staticmethod
        def compute_phase34_microstructure_alphas(df, **kwargs):
            return df.copy()
    return _FakeAlphaModule()


def _make_engine(drawdown_control=False, drawdown_threshold=0.05):
    from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
    return Phase35WalkForwardEngine(
        alpha_module=_make_fake_alpha_module(),
        min_ic_threshold=0.0,
        top_n_alphas=1,
        top_n_stocks=5,
        rebalance_freq=1,
        sector_cap_pct=1.0,
        use_xgboost=False,
        drawdown_control=drawdown_control,
        drawdown_threshold=drawdown_threshold,
        cost_per_turnover=0.0,
    )


def _make_fold_df(daily_returns, tickers=None):
    if tickers is None:
        tickers = ['A', 'B', 'C', 'D', 'E']

    dates = pd.date_range('2020-01-01', periods=len(daily_returns), freq='B')
    rows = []
    for date, day_ret in zip(dates, daily_returns):
        for ticker in tickers:
            rows.append(
                {
                    'date': date,
                    'ticker': ticker,
                    'open': 100.0,
                    'high': 101.0,
                    'low': 99.0,
                    'close': 100.0,
                    'volume': 1_000_000,
                    'sector': 'S1',
                    'alpha_test': 1.0,
                    'fwd_ret_5': day_ret,
                }
            )
    return pd.DataFrame(rows)


class TestStage63DrawdownControl(unittest.TestCase):

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.phase35_walk_forward._import_apply_sector_caps')
    def test_no_breach_keeps_baseline_behaviour(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        test_df = _make_fold_df([0.01] * 8)

        engine_base = _make_engine(drawdown_control=False)
        engine_ctrl = _make_engine(drawdown_control=True)

        base = engine_base.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)
        ctrl = engine_ctrl.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        self.assertAlmostEqual(base.portfolio_total_return, ctrl.portfolio_total_return, places=10)
        self.assertAlmostEqual(base.portfolio_max_dd, ctrl.portfolio_max_dd, places=10)
        self.assertAlmostEqual(base.portfolio_sharpe, ctrl.portfolio_sharpe, places=10)

    @patch('omega.quant.phase35_walk_forward._import_apply_sector_caps')
    def test_breach_stops_out_after_first_breach_date(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        # Positive first 3 days, then repeated losses. Threshold 5% should breach on day 4.
        shocked_returns = [0.01, 0.01, 0.01, -0.10, -0.10, -0.10, -0.10, -0.10]
        test_df = _make_fold_df(shocked_returns)

        engine_base = _make_engine(drawdown_control=False)
        engine_ctrl = _make_engine(drawdown_control=True)

        base = engine_base.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)
        ctrl = engine_ctrl.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        self.assertGreater(ctrl.portfolio_total_return, base.portfolio_total_return)
        self.assertGreater(ctrl.portfolio_max_dd, base.portfolio_max_dd)

    @patch('omega.quant.phase35_walk_forward._import_apply_sector_caps')
    def test_breach_day_return_is_preserved(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        shocked_returns = [0.01, 0.01, 0.01, -0.10, -0.10, -0.10, -0.10, -0.10]
        test_df = _make_fold_df(shocked_returns)

        engine_ctrl = _make_engine(drawdown_control=True)
        ctrl = engine_ctrl.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        # Equal weights across 5 names -> per-row contribution 0.2 * daily_return.
        # Total return after stop-out should keep first 4 days only:
        # 5 rows/day * 0.2 * r = 1.0 * r per day, so fold total is sum(day returns kept).
        expected_total_return = 0.01 + 0.01 + 0.01 - 0.10
        self.assertAlmostEqual(ctrl.portfolio_total_return, expected_total_return, places=10)

    @patch('omega.quant.phase35_walk_forward._import_apply_sector_caps')
    def test_control_uses_only_test_fold_realised_returns(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        # Train fold is catastrophic, but test fold is benign. Control must not stop out
        # based on train-period behaviour.
        train_df = _make_fold_df([-0.20] * 8)
        test_df = _make_fold_df([0.01] * 8)

        engine_ctrl = _make_engine(drawdown_control=True)
        ctrl = engine_ctrl.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        expected_total_return = sum([0.01] * 8)
        self.assertAlmostEqual(ctrl.portfolio_total_return, expected_total_return, places=10)

    @patch('omega.quant.phase35_walk_forward._import_apply_sector_caps')
    def test_sharpe_and_maxdd_use_daily_not_row_level_returns(self, mock_sector_caps):
        """Regression: Sharpe and Max DD must be computed from daily aggregated
        returns, not raw row-level (date×ticker) returns.

        With N tickers per day, row-level returns have N observations per day.
        Daily aggregation sums them to one observation per day.

        Verification strategy:
          - Build a fold with known daily returns and N=5 tickers.
          - Compute expected Sharpe and Max DD manually from the daily series.
          - Assert the engine matches the daily-aggregated values, not the
            row-level values (which would differ due to inflated n and wrong std).
        """
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        n_tickers = 5
        # 8 days: first 4 positive, last 4 negative — creates a clear drawdown
        daily_returns = [0.02, 0.02, 0.02, 0.02, -0.03, -0.03, -0.03, -0.03]
        train_df = _make_fold_df([0.01] * 8, tickers=[f'T{i}' for i in range(n_tickers)])
        test_df = _make_fold_df(daily_returns, tickers=[f'T{i}' for i in range(n_tickers)])

        engine = _make_engine(drawdown_control=False)
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        # Each day: equal weight 1/5 per ticker, fwd_ret_5 = day_ret for all tickers.
        # Daily portfolio return = sum(weight_i * ret_i) = 5 * (1/5) * day_ret = day_ret.
        expected_daily = pd.Series(daily_returns, dtype=float)

        # Expected Sharpe (annualised, 252 periods/year)
        mean_r = expected_daily.mean()
        std_r = expected_daily.std()
        expected_sharpe = (mean_r / std_r) * np.sqrt(252)

        # Expected Max DD from daily cumulative NAV
        cum = (1.0 + expected_daily).cumprod()
        running_max = cum.expanding().max()
        expected_max_dd = ((cum - running_max) / running_max).min()

        # Row-level values would differ: std computed over 40 rows (8 days × 5 tickers)
        # each with value day_ret/5, giving std = std(daily)/5 and sharpe *= 5.
        # Assert engine matches daily, not row-level.
        self.assertAlmostEqual(result.portfolio_sharpe, expected_sharpe, places=6)
        self.assertAlmostEqual(result.portfolio_max_dd, expected_max_dd, places=6)

        # Verify Max DD mismatch between daily-aggregated and row-level computation.
        # Row-level: 40 micro-returns (8 days × 5 tickers), each = weight_i * day_ret.
        # With equal weights (1/5) the per-row value is day_ret/5, so the row-level
        # cumulative NAV path is (1 + day_ret/5)^(5*t) per day t — different from
        # the daily path (1 + day_ret)^t, producing a different Max DD.
        row_level_returns = pd.Series(
            [r / n_tickers for r in daily_returns for _ in range(n_tickers)],
            dtype=float,
        )
        cum_row = (1.0 + row_level_returns).cumprod()
        running_max_row = cum_row.expanding().max()
        row_level_max_dd = ((cum_row - running_max_row) / running_max_row).min()

        # The two values must differ (confirming the engine uses daily, not row-level)
        self.assertFalse(
            abs(result.portfolio_max_dd - float(row_level_max_dd)) < 1e-6,
            "Max DD should NOT match row-level computation",
        )


if __name__ == '__main__':
    unittest.main()
