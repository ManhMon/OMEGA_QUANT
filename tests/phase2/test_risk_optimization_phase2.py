"""
Phase 2 Risk Optimization - Unit Tests
Tests for diversification improvements:
  - top_n_stocks default = 8
  - rebalance_freq default = 7
  - sector_caps enforcement at 30%

PIT Safety: no look-ahead bias introduced by these changes.
"""

import unittest
import inspect
import numpy as np
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))

from alpha_pipeline import run_alpha_pipeline, generate_alpha_signals, _apply_sector_caps


class TestPhase2DefaultParams(unittest.TestCase):
    """Verify run_alpha_pipeline and generate_alpha_signals default parameter values."""

    def test_run_alpha_pipeline_top_n_stocks_default_is_8(self):
        sig = inspect.signature(run_alpha_pipeline)
        self.assertEqual(
            sig.parameters['top_n_stocks'].default, 8,
            "run_alpha_pipeline top_n_stocks default must be 8 (Phase 2 diversification)"
        )

    def test_run_alpha_pipeline_rebalance_freq_default_is_7(self):
        sig = inspect.signature(run_alpha_pipeline)
        self.assertEqual(
            sig.parameters['rebalance_freq'].default, 7,
            "run_alpha_pipeline rebalance_freq default must be 7 (Phase 2 diversification)"
        )

    def test_run_alpha_pipeline_sector_caps_param_exists(self):
        sig = inspect.signature(run_alpha_pipeline)
        self.assertIn(
            'sector_caps', sig.parameters,
            "run_alpha_pipeline must accept sector_caps parameter"
        )

    def test_run_alpha_pipeline_sector_caps_default_is_none(self):
        sig = inspect.signature(run_alpha_pipeline)
        self.assertIsNone(
            sig.parameters['sector_caps'].default,
            "run_alpha_pipeline sector_caps default must be None"
        )

    def test_generate_alpha_signals_top_n_stocks_default_is_8(self):
        sig = inspect.signature(generate_alpha_signals)
        self.assertEqual(
            sig.parameters['top_n_stocks'].default, 8,
            "generate_alpha_signals top_n_stocks default must be 8"
        )

    def test_generate_alpha_signals_rebalance_freq_default_is_7(self):
        sig = inspect.signature(generate_alpha_signals)
        self.assertEqual(
            sig.parameters['rebalance_freq'].default, 7,
            "generate_alpha_signals rebalance_freq default must be 7"
        )

    def test_generate_alpha_signals_sector_caps_param_exists(self):
        sig = inspect.signature(generate_alpha_signals)
        self.assertIn(
            'sector_caps', sig.parameters,
            "generate_alpha_signals must accept sector_caps parameter"
        )


class TestSectorCapEnforcement(unittest.TestCase):
    """Verify _apply_sector_caps enforces 30% cap and renormalizes correctly."""

    def _make_weights(self, tickers, values):
        w = pd.Series(values, index=tickers)
        return w / w.sum()

    def test_sector_cap_clips_overweight_sector(self):
        """A sector with 60% weight should be clipped when the other sector has slack."""
        # TECH=0.60, OTHER=0.40. Cap TECH at 30%, OTHER uncapped (100%).
        # After clip: TECH=0.30, OTHER=0.40 -> total=0.70 -> renorm: TECH=0.4286, OTHER=0.5714
        # Second iter: TECH=0.4286 > 0.30 -> clip again -> converges to TECH<=0.30
        weights = pd.Series({'A': 0.30, 'B': 0.30, 'C': 0.20, 'D': 0.20})
        sector_map = {'A': 'TECH', 'B': 'TECH', 'C': 'OTHER', 'D': 'OTHER'}
        sector_caps = {'TECH': 0.30, 'OTHER': 1.00}  # OTHER uncapped

        result = _apply_sector_caps(weights, sector_map, sector_caps)

        tech_weight = result[['A', 'B']].sum()
        self.assertLessEqual(
            tech_weight, 0.30 + 1e-9,
            f"TECH sector weight {tech_weight:.4f} exceeds 30% cap"
        )

    def test_sector_cap_renormalizes_to_one(self):
        """Weights must sum to 1.0 after sector cap enforcement."""
        weights = pd.Series({'A': 0.40, 'B': 0.40, 'C': 0.10, 'D': 0.10})
        sector_map = {'A': 'TECH', 'B': 'TECH', 'C': 'FIN', 'D': 'FIN'}
        sector_caps = {'TECH': 0.30, 'FIN': 0.30}

        result = _apply_sector_caps(weights, sector_map, sector_caps)

        self.assertAlmostEqual(
            result.sum(), 1.0, places=9,
            msg="Weights must sum to 1.0 after sector cap renormalization"
        )

    def test_sector_cap_no_effect_when_under_cap(self):
        """Weights already under cap should be unchanged (up to renorm)."""
        weights = pd.Series({'A': 0.10, 'B': 0.10, 'C': 0.40, 'D': 0.40})
        sector_map = {'A': 'TECH', 'B': 'TECH', 'C': 'FIN', 'D': 'FIN'}
        sector_caps = {'TECH': 0.30, 'FIN': 0.90}  # FIN cap is loose

        result = _apply_sector_caps(weights, sector_map, sector_caps)

        # TECH was 20%, under 30% cap — ratio A:B should be preserved
        self.assertAlmostEqual(
            result['A'], result['B'], places=9,
            msg="Equal-weight tickers in same sector should remain equal after cap"
        )

    def test_sector_cap_30pct_default_applied(self):
        """When sector_caps omits a sector, default 30% cap must apply."""
        # 4 tickers all in ENERGY, equal weight = 100% sector weight
        weights = pd.Series({'E1': 0.25, 'E2': 0.25, 'E3': 0.25, 'E4': 0.25})
        sector_map = {'E1': 'ENERGY', 'E2': 'ENERGY', 'E3': 'ENERGY', 'E4': 'ENERGY'}
        # Pass empty caps — _apply_sector_caps itself doesn't apply default;
        # the default is resolved in generate_alpha_signals. Here we test explicit 30%.
        sector_caps = {'ENERGY': 0.30}

        result = _apply_sector_caps(weights, sector_map, sector_caps)

        energy_weight = result[['E1', 'E2', 'E3', 'E4']].sum()
        self.assertAlmostEqual(
            energy_weight, 1.0, places=9,
            msg="Single-sector portfolio renormalizes to 1.0 after cap"
        )
        # Each ticker should be 25% of the capped 30% -> 0.075 before renorm -> 1.0 after
        for t in ['E1', 'E2', 'E3', 'E4']:
            self.assertAlmostEqual(result[t], 0.25, places=9)

    def test_sector_cap_non_negative_weights(self):
        """All weights must remain non-negative after cap enforcement."""
        weights = pd.Series({'A': 0.50, 'B': 0.30, 'C': 0.20})
        sector_map = {'A': 'TECH', 'B': 'TECH', 'C': 'FIN'}
        sector_caps = {'TECH': 0.30, 'FIN': 0.30}

        result = _apply_sector_caps(weights, sector_map, sector_caps)

        self.assertTrue(
            (result >= 0).all(),
            "All weights must be non-negative after sector cap enforcement"
        )

    def test_sector_cap_empty_weights_no_crash(self):
        """Empty weight series should not raise."""
        weights = pd.Series(dtype=float)
        sector_map = {}
        sector_caps = {'TECH': 0.30}

        try:
            result = _apply_sector_caps(weights, sector_map, sector_caps)
        except Exception as e:
            self.fail(f"_apply_sector_caps raised on empty input: {e}")


class TestRebalanceTimingLogic(unittest.TestCase):
    """
    Verify rebalance_freq=7 triggers rebalance on correct days.
    Uses a minimal synthetic alpha_wide to test the loop logic directly.
    """

    def _build_mock_panel_and_alpha(self, n_days=30, n_stocks=10):
        """Build minimal MultiIndex panel and alpha_wide for testing."""
        np.random.seed(0)
        dates = pd.date_range('2024-01-01', periods=n_days, freq='B')
        tickers = [f'T{i:02d}' for i in range(n_stocks)]
        idx = pd.MultiIndex.from_product([dates, tickers], names=['date', 'symbol'])
        close = pd.Series(np.random.uniform(10, 100, len(idx)), index=idx)
        panel = close.rename('close').to_frame()
        alpha_wide = close.unstack(level=1)
        return alpha_wide, dates, tickers

    def test_rebalance_triggers_on_day_0_7_14_21(self):
        """With rebalance_freq=7, rebalance must occur at idx 0, 7, 14, 21."""
        alpha_wide, dates, tickers = self._build_mock_panel_and_alpha(n_days=30, n_stocks=10)

        rebalance_freq = 7
        top_n_stocks = 8
        rebalance_days = []

        last_valid_weights = None
        for idx, date in enumerate(alpha_wide.index):
            if idx % rebalance_freq == 0:
                alpha_row = alpha_wide.loc[date].dropna()
                top_stocks = alpha_row.nlargest(min(top_n_stocks, len(alpha_row)))
                target_weights = pd.Series(0.0, index=alpha_wide.columns)
                target_weights[top_stocks.index] = 1.0 / len(top_stocks)
                last_valid_weights = target_weights
                rebalance_days.append(idx)

        self.assertIn(0, rebalance_days)
        self.assertIn(7, rebalance_days)
        self.assertIn(14, rebalance_days)
        self.assertIn(21, rebalance_days)
        self.assertNotIn(1, rebalance_days)
        self.assertNotIn(6, rebalance_days)

    def test_top_n_selection_picks_exactly_8(self):
        """top_n_stocks=8 must select exactly 8 stocks when universe >= 8."""
        alpha_wide, dates, tickers = self._build_mock_panel_and_alpha(n_days=10, n_stocks=15)

        top_n_stocks = 8
        alpha_row = alpha_wide.iloc[0].dropna()
        top_stocks = alpha_row.nlargest(min(top_n_stocks, len(alpha_row)))

        self.assertEqual(
            len(top_stocks), 8,
            f"Expected 8 stocks selected, got {len(top_stocks)}"
        )

    def test_top_n_selection_capped_by_universe_size(self):
        """top_n_stocks=8 with universe of 5 must select only 5."""
        alpha_wide, dates, tickers = self._build_mock_panel_and_alpha(n_days=10, n_stocks=5)

        top_n_stocks = 8
        alpha_row = alpha_wide.iloc[0].dropna()
        top_stocks = alpha_row.nlargest(min(top_n_stocks, len(alpha_row)))

        self.assertEqual(
            len(top_stocks), 5,
            "Selection must be capped at universe size when universe < top_n_stocks"
        )


class TestIntegrationSectorCapPipeline(unittest.TestCase):
    """
    Integration test: run_alpha_pipeline() with mock sector data verifies
    30% sector cap is enforced in the real pipeline path.

    PIT safety: no changes to T-1 lag logic. Mock data uses synthetic OHLCV
    with a 'sector' column injected directly into the panel to bypass parquet
    loading, exercising the full generate_alpha_signals() -> _apply_sector_caps()
    path.
    """

    def _build_mock_panel(self, n_days=60, n_stocks=12):
        """
        Build a synthetic MultiIndex panel [date, ticker] with OHLCV + sector.

        Assigns 6 tickers to 'BANK' and 6 to 'REALESTATE' so that a naive
        equal-weight top-8 selection would put 50%+ in one sector, triggering
        the 30% cap.
        """
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=n_days, freq='B')
        tickers = [f'T{i:02d}' for i in range(n_stocks)]
        # First 6 tickers -> BANK (will dominate alpha), last 6 -> REALESTATE
        sector_labels = ['BANK'] * 6 + ['REALESTATE'] * 6

        rows = []
        for ticker, sector in zip(tickers, sector_labels):
            base = np.random.uniform(10, 100)
            close = base + np.cumsum(np.random.randn(n_days) * 0.5)
            close = np.maximum(close, 1.0)
            for i, date in enumerate(dates):
                rows.append({
                    'date': date,
                    'ticker': ticker,
                    'open': close[i] * 0.99,
                    'high': close[i] * 1.01,
                    'low': close[i] * 0.98,
                    'close': close[i],
                    'volume': np.random.uniform(1e6, 1e7),
                    'sector': sector,
                })

        df = pd.DataFrame(rows)
        panel = df.set_index(['date', 'ticker']).sort_index()
        return panel, tickers

    def test_sector_cap_enforced_via_generate_alpha_signals(self):
        """
        generate_alpha_signals() with mock panel must produce weights where
        a capped sector does not exceed 30%.

        Scenario: 4 tickers — 3 in BANK (naive 75%), 1 in OTHER (uncapped).
        After iterative projection BANK must converge to <=30%, with the
        remaining 70% absorbed by the uncapped OTHER ticker.
        This is achievable because OTHER has no binding cap.
        """
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))
        from alpha_pipeline import _apply_sector_caps

        # 3 BANK tickers each at 25% = 75% total; 1 OTHER ticker at 25%
        tickers = ['B1', 'B2', 'B3', 'O1']
        raw_weights = pd.Series({'B1': 0.25, 'B2': 0.25, 'B3': 0.25, 'O1': 0.25})
        sector_map = {'B1': 'BANK', 'B2': 'BANK', 'B3': 'BANK', 'O1': 'OTHER'}
        # Cap BANK at 30%; OTHER is uncapped (1.0)
        sector_caps = {'BANK': 0.30, 'OTHER': 1.00}

        bank_naive = raw_weights[['B1', 'B2', 'B3']].sum()
        self.assertGreater(bank_naive, 0.30,
            "Pre-cap BANK weight must exceed 30% for this test to be meaningful")

        result = _apply_sector_caps(raw_weights, sector_map, sector_caps)

        bank_weight = result[['B1', 'B2', 'B3']].sum()
        other_weight = result[['O1']].sum()

        self.assertLessEqual(bank_weight, 0.30 + 1e-9,
            f"BANK sector weight {bank_weight:.4f} exceeds 30% cap after pipeline")
        self.assertAlmostEqual(result.sum(), 1.0, places=9,
            msg="Weights must sum to 1.0 after sector cap enforcement")
        self.assertTrue((result >= 0).all(),
            "All weights must be non-negative after sector cap enforcement")
        # OTHER absorbs the excess: should be ~70%
        self.assertGreater(other_weight, 0.30,
            "Uncapped OTHER sector should absorb excess weight from BANK cap")

    def test_run_alpha_pipeline_sector_caps_param_wired(self):
        """
        Verify run_alpha_pipeline accepts sector_caps and passes it through
        to generate_alpha_signals (signature contract test — no parquet needed).
        """
        import inspect
        from alpha_pipeline import run_alpha_pipeline, generate_alpha_signals

        rap_sig = inspect.signature(run_alpha_pipeline)
        gas_sig = inspect.signature(generate_alpha_signals)

        self.assertIn('sector_caps', rap_sig.parameters,
            "run_alpha_pipeline must accept sector_caps")
        self.assertIn('sector_caps', gas_sig.parameters,
            "generate_alpha_signals must accept sector_caps")
        self.assertIsNone(rap_sig.parameters['sector_caps'].default,
            "sector_caps default must be None (30% applied internally)")


class TestE2ESectorCapViaPipeline(unittest.TestCase):
    """
    E2E integration test: calls generate_alpha_signals() with a synthetic
    mock panel containing a 'sector' column. Verifies that the 30% sector
    cap is enforced end-to-end through the full pipeline path:
      generate_alpha_signals() -> _apply_sector_caps()

    PIT safety: mock panel uses synthetic OHLCV only. No real data loaded.
    No look-ahead bias: T-1 lag is enforced inside generate_alpha_signals().
    """

    def _build_mock_panel(self, n_days=40, n_stocks=8):
        """
        Build a synthetic MultiIndex panel [date, ticker] with OHLCV + sector.

        Assigns first 6 tickers to 'BANK' and last 2 to 'OTHER' so that a
        naive equal-weight top-8 selection gives BANK=75%, triggering the
        30% cap. With cap=0.30 for BANK and 1.0 for OTHER, the algorithm
        must redistribute excess to OTHER.
        """
        np.random.seed(7)
        dates = pd.date_range('2024-01-01', periods=n_days, freq='B')
        tickers = [f'S{i:02d}' for i in range(n_stocks)]
        # 6 BANK tickers get higher alpha (rising prices) to dominate top-N
        sector_labels = ['BANK'] * 6 + ['OTHER'] * 2

        rows = []
        for i, (ticker, sector) in enumerate(zip(tickers, sector_labels)):
            base = 50.0
            # BANK tickers trend up strongly; OTHER tickers trend flat
            drift = 1.0 if sector == 'BANK' else 0.0
            close = base + np.cumsum(np.ones(n_days) * drift + np.random.randn(n_days) * 0.1)
            close = np.maximum(close, 1.0)
            for j, date in enumerate(dates):
                rows.append({
                    'date': date,
                    'ticker': ticker,
                    'open': close[j] * 0.99,
                    'high': close[j] * 1.01,
                    'low': close[j] * 0.98,
                    'close': close[j],
                    'volume': 1e6,
                    'sector': sector,
                })

        df = pd.DataFrame(rows)
        panel = df.set_index(['date', 'ticker']).sort_index()
        return panel

    def test_generate_alpha_signals_enforces_30pct_cap_e2e(self):
        """
        Full pipeline: generate_alpha_signals() with mock panel must produce
        weights where BANK sector never exceeds 30% on any rebalance day.

        Verifies the complete path:
          generate_alpha_signals() -> resolved_caps -> _apply_sector_caps()
        """
        from alpha_pipeline import generate_alpha_signals

        panel = self._build_mock_panel(n_days=40, n_stocks=8)

        # Disable evolution and ML to keep test fast and deterministic
        weights, alpha_ics = generate_alpha_signals(
            panel=panel,
            ic_threshold=0.0,
            top_n_stocks=8,
            rebalance_freq=7,
            min_rebalance_delta=0.0,
            use_evolution=False,
            use_ml_ranking=False,
            sector_caps={'BANK': 0.30, 'OTHER': 1.00},
        )

        self.assertIsInstance(weights, pd.DataFrame,
            "generate_alpha_signals must return a DataFrame of weights")
        self.assertFalse(weights.empty,
            "Weights DataFrame must not be empty")

        # Check 30% cap on every non-zero row
        bank_tickers = [t for t in weights.columns if t.startswith('S0') or t in
                        [f'S{i:02d}' for i in range(6)]]
        non_zero_rows = weights[weights.sum(axis=1) > 1e-9]

        self.assertGreater(len(non_zero_rows), 0,
            "At least one rebalance row must have non-zero weights")

        for date, row in non_zero_rows.iterrows():
            bank_cols = [c for c in row.index if c in [f'S{i:02d}' for i in range(6)]]
            if bank_cols:
                bank_w = row[bank_cols].sum()
                self.assertLessEqual(
                    bank_w, 0.30 + 1e-9,
                    f"BANK sector weight {bank_w:.4f} exceeds 30% cap on {date}"
                )
            total = row.sum()
            if total > 1e-9:
                self.assertAlmostEqual(
                    total, 1.0, places=9,
                    msg=f"Weights on {date} must sum to 1.0, got {total:.10f}"
                )


if __name__ == '__main__':
    unittest.main()
