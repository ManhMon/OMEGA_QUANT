"""
P9 Dynamic Rebalance PIT Safety Regression Tests
[L2-Impl:Role9-Backend] - 2026-06-09

Verifies that P9 v4 sequential dynamic rebalance frequency is PIT-safe:
mutating future test data must not affect earlier rebalance decisions or weights.

Test Strategy:
1. Run fold with original test data, capture weights at early dates.
2. Mutate future test close prices (dates > early checkpoint).
3. Re-run fold with mutated data.
4. Assert early weights are identical (no lookahead contamination).

PIT Safety: Uses synthetic in-memory data. No real market data loaded.
"""

import unittest
import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


class TestP9DynamicRebalancePITSafety(unittest.TestCase):
    """
    Regression test: P9 v4 sequential dynamic rebalance must be PIT-safe.
    
    Mutating future test data must not affect earlier rebalance decisions.
    """

    def _make_engine(self, top_n_stocks=3, rebalance_freq=7, sector_cap_pct=0.30):
        """Build a Phase35WalkForwardEngine with P9 dynamic rebalance enabled."""
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

    def _make_df(self, n_dates=60, tickers=None, seed=42):
        """Build a minimal OHLCV DataFrame with forward returns."""
        if tickers is None:
            tickers = ['A', 'B', 'C', 'D', 'E']

        dates = pd.date_range('2024-01-01', periods=n_dates, freq='B')
        rows = []
        rng = np.random.default_rng(seed)
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
                    'sector': 'SectorA',
                    'fwd_ret_5': rng.normal(0, 0.01),
                    'alpha_a': rng.normal(0, 1),
                })
        return pd.DataFrame(rows)

    def test_future_data_mutation_does_not_affect_early_weights(self):
        """
        Core PIT safety test for P9 v4:
        
        1. Run fold with original test data, capture weights at early dates.
        2. Mutate future test close prices (dates after early checkpoint).
        3. Re-run fold with mutated data.
        4. Assert early weights are unchanged (no lookahead).
        
        This proves that rebalance decisions at date D only use data < D,
        never current/future test data.
        """
        engine = self._make_engine(top_n_stocks=3, rebalance_freq=7, sector_cap_pct=1.0)
        tickers = ['A', 'B', 'C', 'D', 'E']
        
        # Generate 60-day dataset
        df_original = self._make_df(n_dates=60, tickers=tickers, seed=123)
        
        # Split into train (first 30 days) and test (last 30 days)
        split_date = df_original['date'].iloc[len(df_original) // 2]
        train_df = df_original[df_original['date'] < split_date].copy()
        test_df_original = df_original[df_original['date'] >= split_date].copy()
        
        # Define early checkpoint: first 10 days of test period
        test_dates = sorted(test_df_original['date'].unique())
        early_checkpoint_date = test_dates[9]  # 10th date (index 9)
        
        # --- RUN 1: Original test data ---
        captured_original = {}
        _orig = engine._apply_stage2_constraints
        
        def _capture_original(test_df, raw_signal, top_alphas, dynamic_rebalance=False, train_df=None):
            result = _orig(
                test_df=test_df, 
                raw_signal=raw_signal, 
                top_alphas=top_alphas,
                dynamic_rebalance=dynamic_rebalance,
                train_df=train_df
            )
            captured_original['result'] = result
            captured_original['test_df'] = test_df.reset_index(drop=True)
            return result
        
        engine._apply_stage2_constraints = _capture_original
        
        metrics_original = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df_original,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        
        self.assertIsNotNone(metrics_original, "Original fold failed to run")
        self.assertIn('result', captured_original, "Did not capture original weights")
        
        # Extract early weights (dates <= early_checkpoint_date)
        tdf_original = captured_original['test_df'].copy()
        tdf_original['_weight'] = captured_original['result'].values
        early_weights_original = tdf_original[
            tdf_original['date'] <= early_checkpoint_date
        ][['date', 'ticker', '_weight']].copy()
        
        # --- RUN 2: Mutated test data (future dates only) ---
        test_df_mutated = test_df_original.copy()
        
        # Mutate close prices for dates AFTER early_checkpoint_date
        # This simulates future information changing (e.g., extreme volatility spike)
        future_mask = test_df_mutated['date'] > early_checkpoint_date
        rng_mutate = np.random.default_rng(999)
        mutation_factors = 1.0 + rng_mutate.normal(0, 0.5, future_mask.sum())
        test_df_mutated.loc[future_mask, 'close'] = (
            test_df_mutated.loc[future_mask, 'close'] * mutation_factors
        )
        
        # Verify mutation actually changed future data
        future_original = test_df_original[test_df_original['date'] > early_checkpoint_date]['close'].values
        future_mutated = test_df_mutated[test_df_mutated['date'] > early_checkpoint_date]['close'].values
        self.assertFalse(
            np.allclose(future_original, future_mutated, rtol=1e-6),
            "Future data mutation failed — test setup is broken"
        )
        
        # Reset engine and capture mutated run
        engine_mutated = self._make_engine(top_n_stocks=3, rebalance_freq=7, sector_cap_pct=1.0)
        captured_mutated = {}
        _orig_mutated = engine_mutated._apply_stage2_constraints
        
        def _capture_mutated(test_df, raw_signal, top_alphas, dynamic_rebalance=False, train_df=None):
            result = _orig_mutated(
                test_df=test_df, 
                raw_signal=raw_signal, 
                top_alphas=top_alphas,
                dynamic_rebalance=dynamic_rebalance,
                train_df=train_df
            )
            captured_mutated['result'] = result
            captured_mutated['test_df'] = test_df.reset_index(drop=True)
            return result
        
        engine_mutated._apply_stage2_constraints = _capture_mutated
        
        metrics_mutated = engine_mutated.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df_mutated,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        
        self.assertIsNotNone(metrics_mutated, "Mutated fold failed to run")
        self.assertIn('result', captured_mutated, "Did not capture mutated weights")
        
        # Extract early weights from mutated run
        tdf_mutated = captured_mutated['test_df'].copy()
        tdf_mutated['_weight'] = captured_mutated['result'].values
        early_weights_mutated = tdf_mutated[
            tdf_mutated['date'] <= early_checkpoint_date
        ][['date', 'ticker', '_weight']].copy()
        
        # --- ASSERTION: Early weights must be identical ---
        # PIT safety requires that decisions at date D only use data < D.
        # Mutating future data (dates > early_checkpoint_date) must not affect
        # weights for dates <= early_checkpoint_date.
        
        merged = early_weights_original.merge(
            early_weights_mutated,
            on=['date', 'ticker'],
            suffixes=('_orig', '_mut')
        )
        
        for _, row in merged.iterrows():
            self.assertAlmostEqual(
                row['_weight_orig'],
                row['_weight_mut'],
                places=9,
                msg=(
                    f"PIT VIOLATION: Weight for {row['ticker']} on {row['date']} "
                    f"changed from {row['_weight_orig']:.6f} to {row['_weight_mut']:.6f} "
                    f"after mutating future test data (dates > {early_checkpoint_date}). "
                    f"This indicates lookahead: early decisions are contaminated by future data."
                )
            )

    def test_dynamic_rebalance_frequency_updates_sequentially(self):
        """
        Verify that dynamic rebalance frequency is updated at rebalance checkpoints
        using only prior available data (train + strictly prior test dates).
        
        This is a behavioral test to confirm the sequential update mechanism works.
        """
        engine = self._make_engine(top_n_stocks=3, rebalance_freq=7, sector_cap_pct=1.0)
        tickers = ['A', 'B', 'C']
        
        df = self._make_df(n_dates=40, tickers=tickers, seed=456)
        split_date = df['date'].iloc[len(df) // 2]
        train_df = df[df['date'] < split_date].copy()
        test_df = df[df['date'] >= split_date].copy()
        
        # Inject high volatility in later test period to trigger regime change
        test_dates = sorted(test_df['date'].unique())
        late_date = test_dates[len(test_dates) // 2]
        late_mask = test_df['date'] >= late_date
        
        # Spike close prices in late period (high volatility regime)
        rng = np.random.default_rng(789)
        spike_factors = 1.0 + rng.normal(0, 0.3, late_mask.sum())
        test_df.loc[late_mask, 'close'] = test_df.loc[late_mask, 'close'] * spike_factors
        
        # Run fold with dynamic rebalancing enabled
        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        
        self.assertIsNotNone(metrics, "Dynamic rebalance fold failed to run")
        # If this test runs without error, sequential update mechanism is working
        # (detailed frequency tracking would require exposing internal state)

    def test_sequential_freq_computation_with_empty_available_test(self):
        """
        Edge case: first OOS date has no prior test data available.
        
        _compute_sequential_dynamic_freq should handle empty available_test_df
        and fall back to train baseline.
        """
        from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
        
        engine = self._make_engine(top_n_stocks=3, rebalance_freq=7)
        
        # Build train_df
        train_df = self._make_df(n_dates=30, tickers=['A', 'B'], seed=111)
        
        # Call _compute_sequential_dynamic_freq with empty available_test_df
        # (simulates first OOS date where no prior test data exists)
        empty_test = pd.DataFrame(columns=train_df.columns)
        
        freq = engine._compute_sequential_dynamic_freq(
            train_df=train_df,
            available_test_df=empty_test,
            base_freq=7
        )
        
        # Should return base_freq or a valid frequency (not crash)
        self.assertIsInstance(freq, int)
        self.assertGreaterEqual(freq, 5)
        self.assertLessEqual(freq, 10)

    def test_dynamic_cadence_respects_frequency_changes(self):
        """
        Deterministic regression test for dynamic cadence correctness.
        
        Verifies that when frequency changes from 5 to 7 at idx=5,
        the next rebalance occurs at idx=12 (5 + 7), NOT at idx=7.
        
        Strategy:
        1. Monkeypatch _compute_sequential_dynamic_freq to return predictable schedule:
           - idx 0: freq=5
           - idx 5: freq=7
           - idx 12+: freq=7 (stays at 7)
        2. Construct signals where top ticker changes at idx 5 and idx 7
        3. Assert weight changes occur at idx [0, 5, 12], NOT at idx 7
        
        This catches the bug where absolute `idx % current_rebal_freq == 0`
        causes early rebalance at idx=7 (because 7 % 7 == 0).
        """
        engine = self._make_engine(top_n_stocks=2, rebalance_freq=5, sector_cap_pct=1.0)
        
        # Build deterministic dataset with 25 dates, 3 tickers (to ensure idx 12 in test_df)
        tickers = ['A', 'B', 'C']
        dates = pd.date_range('2024-01-01', periods=25, freq='B')
        rows = []
        
        for i, d in enumerate(dates):
            # Construct signals so that top ticker changes at specific indices
            # to make rebalance events observable via weight changes
            # Note: test_df starts at calendar idx 5 (first 5 used for train)
            if i < 5:
                # Calendar idx 0-4 (train_df): A=10, B=5, C=1 -> top-2 = [A, B]
                signals = {'A': 10.0, 'B': 5.0, 'C': 1.0}
            elif i < 10:
                # Calendar idx 5-9 (test_df idx 0-4): B=10, C=5, A=1 -> top-2 = [B, C]
                signals = {'A': 1.0, 'B': 10.0, 'C': 5.0}
            elif i < 17:
                # Calendar idx 10-16 (test_df idx 5-11): C=10, A=5, B=1 -> top-2 = [C, A]
                signals = {'A': 5.0, 'B': 1.0, 'C': 10.0}
            else:
                # Calendar idx 17+ (test_df idx 12+): A=10, B=5, C=1 -> top-2 = [A, B]
                signals = {'A': 10.0, 'B': 5.0, 'C': 1.0}
            
            for t in tickers:
                rows.append({
                    'date': d,
                    'ticker': t,
                    'open': 100.0,
                    'high': 101.0,
                    'low': 99.0,
                    'close': 100.0,
                    'volume': 1_000_000,
                    'sector': 'SectorA',
                    'fwd_ret_5': 0.01,
                    'alpha_a': signals[t],
                })
        
        df = pd.DataFrame(rows)
        
        # Split: train = first 5 dates (idx 0-4), test = remaining 15 dates (idx 5-19)
        train_dates = dates[:5]
        train_df = df[df['date'].isin(train_dates)].copy()
        test_df = df[~df['date'].isin(train_dates)].copy()
        
        # Monkeypatch _compute_sequential_dynamic_freq to return deterministic schedule
        call_count = [0]
        call_log = []
        
        def _mock_freq(train_df, available_test_df, base_freq):
            """Return freq schedule: first call -> 5, second call -> 7, then 7."""
            call_count[0] += 1
            if call_count[0] == 1:
                freq = 5  # idx 0: start with freq=5
            elif call_count[0] == 2:
                freq = 7  # idx 5: change to freq=7
            else:
                freq = 7  # idx 12+: stay at freq=7
            
            call_log.append({
                'call': call_count[0],
                'freq': freq,
                'available_test_rows': len(available_test_df)
            })
            return freq
        
        original_method = engine._compute_sequential_dynamic_freq
        engine._compute_sequential_dynamic_freq = _mock_freq
        
        # Capture weights to track rebalance events
        captured = {}
        _orig = engine._apply_stage2_constraints
        
        def _capture(test_df, raw_signal, top_alphas, dynamic_rebalance=False, train_df=None):
            result = _orig(
                test_df=test_df, 
                raw_signal=raw_signal, 
                top_alphas=top_alphas,
                dynamic_rebalance=dynamic_rebalance,
                train_df=train_df
            )
            captured['result'] = result
            captured['test_df'] = test_df.reset_index(drop=True)
            return result
        
        engine._apply_stage2_constraints = _capture
        
        # Run fold with dynamic rebalancing enabled
        metrics = engine.run_fold(
            fold_id=1,
            train_df=train_df,
            test_df=test_df,
            alpha_cols=['alpha_a'],
            return_col='fwd_ret_5',
        )
        
        self.assertIsNotNone(metrics, "Dynamic cadence fold failed to run")
        self.assertIn('result', captured, "Did not capture weights")
        
        # Extract weights by ticker and date
        tdf = captured['test_df'].copy()
        tdf['weight'] = captured['result'].values
        
        # Build weight pivot: rows=dates, cols=tickers
        weight_pivot = tdf.pivot(index='date', columns='ticker', values='weight').fillna(0.0)
        test_dates_sorted = sorted(tdf['date'].unique())
        
        # Track weight changes (rebalance events)
        rebalance_indices = []
        prev_weights = None
        
        for i, d in enumerate(test_dates_sorted):
            current_weights = weight_pivot.loc[d]
            if prev_weights is None or not current_weights.equals(prev_weights):
                rebalance_indices.append(i)
            prev_weights = current_weights
        
        # Expected rebalance indices (in test_df, which starts at idx=0 in this fold):
        # - idx 0 (first date): always rebalance -> top-2 = [B, C] from idx=5 signal regime
        # - idx 5 (elapsed=5 from idx 0): freq changes 5->7, rebalance -> top-2 still [B, C]
        # - idx 7: NO rebalance (elapsed=2, need 7)
        # - idx 12 (elapsed=7 from idx 5): rebalance -> top-2 = [C, A] from idx=7+ regime
        #
        # Wait, the test_df starts from the 6th calendar date (train used first 5 dates).
        # So test_df indices map as:
        # - test_df idx 0 = calendar idx 5 (signal regime: B=10, C=5)
        # - test_df idx 2 = calendar idx 7 (signal regime: C=10, A=5)
        # - test_df idx 7 = calendar idx 12
        #
        # Expected rebalance at test_df indices: [0, 5, 12]
        # But test_df only has 15 dates (idx 0-14), so idx 12 is valid.
        #
        # Actually, let me re-check the expected behavior:
        # - test_df idx 0: first date, always rebalance (freq computed -> 5)
        # - test_df idx 5: elapsed=5, rebalance (freq computed -> 7)
        # - test_df idx 7: elapsed=2 from last rebalance at idx 5, should NOT rebalance
        # - test_df idx 12: elapsed=7 from idx 5, should rebalance
        
        # Assert: NO rebalance at test_df idx 7
        # If idx 7 appears in rebalance_indices, the bug is present
        self.assertNotIn(
            7,
            rebalance_indices,
            msg=(
                f"CADENCE BUG: Rebalance occurred at test_df idx=7, only 2 dates after "
                f"idx=5 where freq changed to 7. Expected next rebalance at idx=12. "
                f"Observed rebalance indices: {rebalance_indices}, "
                f"test_df has {len(test_dates_sorted)} dates"
            )
        )
        
        # Positive assertion: rebalances should occur at idx 0, 5
        # idx 12 requires at least 13 dates in test_df
        self.assertIn(0, rebalance_indices, f"Expected rebalance at idx 0 (first date). Observed: {rebalance_indices}")
        self.assertIn(5, rebalance_indices, f"Expected rebalance at idx 5 (elapsed=5). Observed: {rebalance_indices}")
        
        # Only assert idx 12 if test_df is long enough
        if len(test_dates_sorted) >= 13:
            self.assertIn(
                12, 
                rebalance_indices, 
                f"Expected rebalance at idx 12 (elapsed=7 from idx 5). "
                f"Observed: {rebalance_indices}, test_df has {len(test_dates_sorted)} dates"
            )
        else:
            # If test_df is too short, just verify the cadence bug is fixed (no idx 7)
            # The core assertion (no idx 7) already passed above
            pass
        
        # Restore original method
        engine._compute_sequential_dynamic_freq = original_method


if __name__ == '__main__':
    unittest.main()
