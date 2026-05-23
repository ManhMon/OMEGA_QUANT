"""
Stage 2 Diversification Parameter Wiring Tests
[L2-Impl:Role9-Backend] - 2026-05-22

Verifies that Stage 2 diversification params (top_n_stocks=8, rebalance_freq=7,
sector_cap_pct=0.30) are explicitly wired into the Phase35WalkForwardEngine
executable path.

PIT Safety: No real data loaded. Signature and attribute contract tests only.
"""

import inspect
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../packages/quant/src')))


class TestPhase35EngineStage2Params(unittest.TestCase):
    """Verify Phase35WalkForwardEngine accepts and stores Stage 2 params."""

    def _get_engine_class(self):
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
        return Phase35WalkForwardEngine

    def test_engine_accepts_top_n_stocks(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertIn(
            'top_n_stocks', sig.parameters,
            "Phase35WalkForwardEngine.__init__ must accept top_n_stocks"
        )

    def test_engine_top_n_stocks_default_is_8(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertEqual(
            sig.parameters['top_n_stocks'].default, 8,
            "top_n_stocks default must be 8 (Stage 2 diversification)"
        )

    def test_engine_accepts_rebalance_freq(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertIn(
            'rebalance_freq', sig.parameters,
            "Phase35WalkForwardEngine.__init__ must accept rebalance_freq"
        )

    def test_engine_rebalance_freq_default_is_7(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertEqual(
            sig.parameters['rebalance_freq'].default, 7,
            "rebalance_freq default must be 7 (Stage 2 diversification)"
        )

    def test_engine_accepts_sector_cap_pct(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertIn(
            'sector_cap_pct', sig.parameters,
            "Phase35WalkForwardEngine.__init__ must accept sector_cap_pct"
        )

    def test_engine_sector_cap_pct_default_is_30pct(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        self.assertAlmostEqual(
            sig.parameters['sector_cap_pct'].default, 0.30, places=9,
            msg="sector_cap_pct default must be 0.30 (Stage 2 30% sector cap)"
        )

    def test_engine_stores_top_n_stocks_on_instance(self):
        """Engine must store top_n_stocks as instance attribute for runtime use."""
        cls = self._get_engine_class()
        engine = cls(alpha_module=None, top_n_stocks=8, rebalance_freq=7, sector_cap_pct=0.30)
        self.assertEqual(engine.top_n_stocks, 8)

    def test_engine_stores_rebalance_freq_on_instance(self):
        cls = self._get_engine_class()
        engine = cls(alpha_module=None, top_n_stocks=8, rebalance_freq=7, sector_cap_pct=0.30)
        self.assertEqual(engine.rebalance_freq, 7)

    def test_engine_stores_sector_cap_pct_on_instance(self):
        cls = self._get_engine_class()
        engine = cls(alpha_module=None, top_n_stocks=8, rebalance_freq=7, sector_cap_pct=0.30)
        self.assertAlmostEqual(engine.sector_cap_pct, 0.30, places=9)

    def test_engine_custom_stage2_params_stored(self):
        """Non-default values must be stored correctly (not silently overridden)."""
        cls = self._get_engine_class()
        engine = cls(alpha_module=None, top_n_stocks=10, rebalance_freq=5, sector_cap_pct=0.25)
        self.assertEqual(engine.top_n_stocks, 10)
        self.assertEqual(engine.rebalance_freq, 5)
        self.assertAlmostEqual(engine.sector_cap_pct, 0.25, places=9)


class TestRunPhase35BacktestStage2Constants(unittest.TestCase):
    """
    Verify run_phase35_backtest.py defines Stage 2 constants and passes them
    to Phase35WalkForwardEngine. Parses the script as source — no execution,
    no parquet needed.
    """

    def _get_script_source(self):
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../../scripts/run_phase35_backtest.py')
        )
        with open(script_path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_script_defines_stage2_top_n_stocks(self):
        src = self._get_script_source()
        self.assertIn(
            'STAGE2_TOP_N_STOCKS = 8', src,
            "run_phase35_backtest.py must define STAGE2_TOP_N_STOCKS = 8"
        )

    def test_script_defines_stage2_rebalance_freq(self):
        src = self._get_script_source()
        self.assertIn(
            'STAGE2_REBALANCE_FREQ = 7', src,
            "run_phase35_backtest.py must define STAGE2_REBALANCE_FREQ = 7"
        )

    def test_script_defines_stage2_sector_cap_pct(self):
        src = self._get_script_source()
        self.assertIn(
            'STAGE2_SECTOR_CAP_PCT = 0.30', src,
            "run_phase35_backtest.py must define STAGE2_SECTOR_CAP_PCT = 0.30"
        )

    def test_script_passes_top_n_stocks_to_engine(self):
        src = self._get_script_source()
        self.assertIn(
            'top_n_stocks=STAGE2_TOP_N_STOCKS', src,
            "run_phase35_backtest.py must pass top_n_stocks=STAGE2_TOP_N_STOCKS to engine"
        )

    def test_script_passes_rebalance_freq_to_engine(self):
        src = self._get_script_source()
        self.assertIn(
            'rebalance_freq=STAGE2_REBALANCE_FREQ', src,
            "run_phase35_backtest.py must pass rebalance_freq=STAGE2_REBALANCE_FREQ to engine"
        )

    def test_script_passes_sector_cap_pct_to_engine(self):
        src = self._get_script_source()
        self.assertIn(
            'sector_cap_pct=STAGE2_SECTOR_CAP_PCT', src,
            "run_phase35_backtest.py must pass sector_cap_pct=STAGE2_SECTOR_CAP_PCT to engine"
        )

    def test_script_includes_stage2_params_in_results_json(self):
        src = self._get_script_source()
        self.assertIn(
            '"stage2_top_n_stocks"', src,
            "results JSON config must include stage2_top_n_stocks"
        )
        self.assertIn(
            '"stage2_rebalance_freq"', src,
            "results JSON config must include stage2_rebalance_freq"
        )
        self.assertIn(
            '"stage2_sector_cap_pct"', src,
            "results JSON config must include stage2_sector_cap_pct"
        )


class TestRunFoldStage2BehavioralEnforcement(unittest.TestCase):
    """
    Behavioral tests: prove Stage 2 constraints are enforced inside run_fold.

    Uses synthetic in-memory data — no parquet, no real market data.
    PIT safety: forward returns are computed from test data only; no look-ahead.
    """

    def _make_engine(self, top_n_stocks=3, rebalance_freq=2, sector_cap_pct=0.30):
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine

        class _FakeAlphaModule:
            """Minimal alpha module: passes df through, adds a dummy alpha col."""
            @staticmethod
            def compute_phase34_microstructure_alphas(df, **kwargs):
                out = df.copy()
                if 'alpha_a' not in out.columns:
                    out['alpha_a'] = out.groupby('ticker')['close'].transform(
                        lambda s: s.pct_change().shift(1)
                    )
                return out

        return Phase35WalkForwardEngine(
            alpha_module=_FakeAlphaModule(),
            min_ic_threshold=0.0,   # accept all alphas in synthetic data
            top_n_alphas=1,
            top_n_stocks=top_n_stocks,
            rebalance_freq=rebalance_freq,
            sector_cap_pct=sector_cap_pct,
        )

    def _make_df(self, n_dates=10, tickers=None, sector_map=None):
        """Build a minimal OHLCV DataFrame with forward returns."""
        import pandas as pd
        import numpy as np

        if tickers is None:
            tickers = ['A', 'B', 'C', 'D', 'E']

        dates = pd.date_range('2024-01-01', periods=n_dates, freq='B')
        rows = []
        rng = np.random.default_rng(42)
        for t in tickers:
            prices = 100 + rng.normal(0, 1, n_dates).cumsum()
            for i, d in enumerate(dates):
                rows.append({
                    'date': d,
                    'ticker': t,
                    'open': prices[i],
                    'high': prices[i] * 1.01,
                    'low': prices[i] * 0.99,
                    'close': prices[i],
                    'volume': 1_000_000,
                    'sector': (sector_map or {}).get(t, 'SectorA'),
                    'fwd_ret_5': rng.normal(0, 0.01),
                    'alpha_a': rng.normal(0, 1),
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Test 1: top-N selection enforced — at most top_n_stocks get weight
    # ------------------------------------------------------------------
    def test_top_n_stocks_enforced_in_fold(self):
        """run_fold must assign non-zero weight to at most top_n_stocks tickers."""
        import pandas as pd
        import numpy as np

        top_n = 2
        engine = self._make_engine(top_n_stocks=top_n, rebalance_freq=1, sector_cap_pct=1.0)
        tickers = ['A', 'B', 'C', 'D', 'E']
        df = self._make_df(n_dates=20, tickers=tickers)

        # Give ticker A a very strong alpha signal so it always ranks top
        # Give ticker B second-strongest; C/D/E weaker
        rng = np.random.default_rng(0)
        for i, row in df.iterrows():
            if row['ticker'] == 'A':
                df.at[i, 'alpha_a'] = 10.0
            elif row['ticker'] == 'B':
                df.at[i, 'alpha_a'] = 5.0
            else:
                df.at[i, 'alpha_a'] = rng.normal(0, 0.1)

        train_df = df[df['date'] < df['date'].median()].copy()
        test_df = df[df['date'] >= df['date'].median()].copy()

        # Capture post-constraint weights from _apply_stage2_constraints
        captured = {}
        _orig = engine._apply_stage2_constraints

        def _patched(test_df, raw_signal, top_alphas):
            result = _orig(test_df=test_df, raw_signal=raw_signal, top_alphas=top_alphas)
            captured['result'] = result
            captured['test_df'] = test_df.reset_index(drop=True)
            return result

        engine._apply_stage2_constraints = _patched

        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )

        # Metrics object must be returned without error
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.fold_id, 1)

        # Behavioral assertion: on each rebalance date, at most top_n tickers
        # have non-zero weight (top-N selection is enforced)
        self.assertIn('result', captured, "Monkeypatch did not capture weights — _apply_stage2_constraints was not called")
        tdf = captured['test_df'].copy()
        tdf['_weight'] = captured['result'].values
        for date, grp in tdf.groupby('date'):
            nonzero_count = (grp['_weight'] > 1e-9).sum()
            self.assertLessEqual(
                nonzero_count,
                top_n,
                f"Date {date}: {nonzero_count} tickers have non-zero weight, expected <= {top_n}",
            )

    # ------------------------------------------------------------------
    # Test 2: rebalance cadence — weights only change on rebalance dates
    # ------------------------------------------------------------------
    def test_rebalance_cadence_respected_in_fold(self):
        """
        With rebalance_freq=3, weights on non-rebalance dates must equal
        the weights from the most recent rebalance date.
        """
        import pandas as pd
        import numpy as np
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine

        rebal_freq = 3
        engine = self._make_engine(top_n_stocks=2, rebalance_freq=rebal_freq, sector_cap_pct=1.0)
        tickers = ['A', 'B', 'C']
        df = self._make_df(n_dates=20, tickers=tickers)

        # Assign deterministic alpha so top-N is predictable
        for i, row in df.iterrows():
            df.at[i, 'alpha_a'] = {'A': 3.0, 'B': 2.0, 'C': 1.0}[row['ticker']]

        train_df = df[df['date'] < df['date'].median()].copy()
        test_df = df[df['date'] >= df['date'].median()].copy()

        # Patch _apply_stage2_constraints to capture weight_wide for inspection
        captured = {}
        _orig = engine._apply_stage2_constraints

        def _patched(test_df, raw_signal, top_alphas):
            result = _orig(test_df=test_df, raw_signal=raw_signal, top_alphas=top_alphas)
            captured['result'] = result
            captured['test_df'] = test_df.reset_index(drop=True)
            return result

        engine._apply_stage2_constraints = _patched

        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        self.assertIsNotNone(metrics)

        # Behavioral assertion: weights on non-rebalance dates must equal weights
        # from the most recent rebalance date (carry-forward behavior)
        self.assertIn('result', captured, "Monkeypatch did not capture weights — _apply_stage2_constraints was not called")
        tdf = captured['test_df'].copy()
        tdf['_weight'] = captured['result'].values

        # Pivot to wide format: rows=date, cols=ticker
        weight_wide = tdf.pivot(index='date', columns='ticker', values='_weight').fillna(0.0)
        sorted_dates = sorted(weight_wide.index)

        # Identify rebalance dates by position (idx % rebal_freq == 0)
        rebal_dates = {d for idx, d in enumerate(sorted_dates) if idx % rebal_freq == 0}

        # For each non-rebalance date, find most recent rebalance date and compare
        last_rebal_date = None
        for date in sorted_dates:
            if date in rebal_dates:
                last_rebal_date = date
            else:
                # Non-rebalance date: weights must equal last rebalance date's weights
                self.assertIsNotNone(
                    last_rebal_date,
                    f"Non-rebalance date {date} has no prior rebalance date",
                )
                for ticker in weight_wide.columns:
                    w_nonrebal = weight_wide.loc[date, ticker]
                    w_rebal = weight_wide.loc[last_rebal_date, ticker]
                    self.assertAlmostEqual(
                        w_nonrebal,
                        w_rebal,
                        places=9,
                        msg=(
                            f"Ticker {ticker} on non-rebalance date {date}: "
                            f"weight={w_nonrebal:.6f} != last rebalance date "
                            f"{last_rebal_date} weight={w_rebal:.6f}"
                        ),
                    )

    # ------------------------------------------------------------------
    # Test 3: sector cap enforced — no sector exceeds sector_cap_pct
    # ------------------------------------------------------------------
    def test_sector_cap_enforced_in_fold(self):
        """
        With sector_cap_pct=0.60 and two sectors, no sector should exceed 0.60
        of total weight on any rebalance date.

        Note: sector_cap must satisfy sum(caps) >= 1.0 to be feasible.
        With 2 sectors at 0.60 each, sum=1.20 >= 1.0 — valid constraint.
        """
        import pandas as pd
        import numpy as np
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine

        sector_cap = 0.60
        # 4 tickers: A,B in SectorX; C,D in SectorY
        sector_map = {'A': 'SectorX', 'B': 'SectorX', 'C': 'SectorY', 'D': 'SectorY'}
        tickers = list(sector_map.keys())

        engine = self._make_engine(top_n_stocks=4, rebalance_freq=1, sector_cap_pct=sector_cap)
        df = self._make_df(n_dates=20, tickers=tickers, sector_map=sector_map)

        # Give SectorX tickers a stronger alpha so they would dominate without cap
        # A=10, B=9 >> C=1, D=0.5 — without cap SectorX would take ~95% weight
        alpha_vals = {'A': 10.0, 'B': 9.0, 'C': 1.0, 'D': 0.5}
        for i in df.index:
            df.at[i, 'alpha_a'] = alpha_vals[df.at[i, 'ticker']]

        train_df = df[df['date'] < df['date'].median()].copy()
        test_df = df[df['date'] >= df['date'].median()].copy()

        # Capture weights from _apply_stage2_constraints
        captured = {}
        _orig = engine._apply_stage2_constraints

        def _patched(test_df, raw_signal, top_alphas):
            result = _orig(test_df=test_df, raw_signal=raw_signal, top_alphas=top_alphas)
            captured['result'] = result
            captured['test_df'] = test_df.reset_index(drop=True)
            return result

        engine._apply_stage2_constraints = _patched

        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        self.assertIsNotNone(metrics)

        if 'result' in captured:
            result = captured['result']
            tdf = captured['test_df']
            tdf = tdf.copy()
            tdf['_weight'] = result.values

            # For each date, compute sector weight sums and check cap
            for date, grp in tdf.groupby('date'):
                total_w = grp['_weight'].sum()
                if total_w < 1e-9:
                    continue  # skip zero-weight dates
                for sector, sg in grp.groupby('sector'):
                    sector_w = sg['_weight'].sum() / total_w
                    self.assertLessEqual(
                        sector_w,
                        sector_cap + 1e-6,
                        f"Sector {sector} weight {sector_w:.4f} exceeds cap {sector_cap:.2f} on {date}",
                    )

    # ------------------------------------------------------------------
    # Test 4: existing wiring tests still pass (smoke test)
    # ------------------------------------------------------------------
    def test_engine_stage2_params_still_stored(self):
        """Regression: Stage 2 params must still be stored after refactor."""
        engine = self._make_engine(top_n_stocks=8, rebalance_freq=7, sector_cap_pct=0.30)
        self.assertEqual(engine.top_n_stocks, 8)
        self.assertEqual(engine.rebalance_freq, 7)
        self.assertAlmostEqual(engine.sector_cap_pct, 0.30, places=9)


if __name__ == '__main__':
    unittest.main()
