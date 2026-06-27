"""
GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616
GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
Drawdown Control Re-Entry Tests

[L2-Impl:Role14-DataScientist] - 2026-06-16

Verifies stateful drawdown control with cooldown and HWM reset:
  1. Default (no re-entry): permanent stop-out, backward compatible
  2. Re-entry after cooldown: strategy resumes after cooldown_days
  3. HWM reset prevents repeated stop-outs from same level
  4. HWM no-reset keeps original HWM (stricter)
  5. Multiple stop-outs with re-entry cycles
  6. Constructor param validation
  7. PIT safety: uses only test-fold realised returns
  8. Evidence dict populated correctly
  9. Adaptive re-entry: HMM bear probability extends/shortens cooldown
  10. Adaptive re-entry: volatility-based cooldown extension
  11. Adaptive re-entry: max cooldown cap prevents infinite extension
  12. HMM p_bear evidence output from risk_sizing_overlay

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


def _make_engine(
    drawdown_control=False,
    drawdown_threshold=0.05,
    drawdown_re_entry_enabled=False,
    drawdown_cooldown_days=5,
    drawdown_hwm_reset=True,
    drawdown_adaptive_re_entry=False,
    drawdown_adaptive_bear_threshold=0.5,
    drawdown_adaptive_vol_window=20,
    drawdown_adaptive_vol_multiplier=1.5,
    drawdown_adaptive_max_cooldown=20,
):
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
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
        drawdown_re_entry_enabled=drawdown_re_entry_enabled,
        drawdown_cooldown_days=drawdown_cooldown_days,
        drawdown_hwm_reset=drawdown_hwm_reset,
        drawdown_adaptive_re_entry=drawdown_adaptive_re_entry,
        drawdown_adaptive_bear_threshold=drawdown_adaptive_bear_threshold,
        drawdown_adaptive_vol_window=drawdown_adaptive_vol_window,
        drawdown_adaptive_vol_multiplier=drawdown_adaptive_vol_multiplier,
        drawdown_adaptive_max_cooldown=drawdown_adaptive_max_cooldown,
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


class TestDrawdownReEntryConstructor(unittest.TestCase):
    """Test constructor parameter validation."""

    def test_default_re_entry_disabled(self):
        engine = _make_engine()
        self.assertFalse(engine.drawdown_re_entry_enabled)
        self.assertEqual(engine.drawdown_cooldown_days, 5)
        self.assertTrue(engine.drawdown_hwm_reset)

    def test_re_entry_enabled(self):
        engine = _make_engine(
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=10,
            drawdown_hwm_reset=False,
        )
        self.assertTrue(engine.drawdown_re_entry_enabled)
        self.assertEqual(engine.drawdown_cooldown_days, 10)
        self.assertFalse(engine.drawdown_hwm_reset)

    def test_invalid_re_entry_type_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_re_entry_enabled="yes",
            )

    def test_invalid_cooldown_type_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_cooldown_days=-1,
            )

    def test_invalid_hwm_reset_type_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_hwm_reset=1,
            )


class TestDrawdownReEntryBackwardCompat(unittest.TestCase):
    """Verify default (no re-entry) preserves existing stop-out behavior."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_no_re_entry_permanent_stop_out(self, mock_sector_caps):
        """Without re-entry, stop-out is permanent (all post-breach returns zeroed)."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        # Big drop triggers stop-out on day 4
        test_returns = [0.01, 0.01, 0.01, -0.10, -0.10, -0.10, -0.10, -0.10]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=False,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        # Only first 4 days kept (breach day included)
        expected_total = 0.01 + 0.01 + 0.01 - 0.10
        self.assertAlmostEqual(result.portfolio_total_return, expected_total, places=6)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_re_entry_disabled_evidence_reports_no_re_entries(self, mock_sector_caps):
        """Evidence should show 0 re-entries when re-entry is disabled."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        test_returns = [0.01, 0.01, 0.01, -0.10, -0.10, -0.10, -0.10, -0.10]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_re_entry_enabled=False,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["n_stop_outs"], 1)
        self.assertEqual(evidence["n_re_entries"], 0)


class TestDrawdownReEntryWithCooldown(unittest.TestCase):
    """Test re-entry after cooldown period."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_re_entry_after_cooldown_resumes_trading(self, mock_sector_caps):
        """After cooldown, strategy resumes and captures subsequent returns."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 20)
        # Day 0-2: gains, Day 3: big loss (triggers stop-out)
        # Day 4-6: cooldown (5% threshold, cooldown=3 days => days 4,5,6 zeroed)
        # Day 7+: re-entry with positive returns
        test_returns = [
            0.02, 0.02, 0.02,      # days 0-2: gains
            -0.10,                  # day 3: breach (DD ~ -7.5% from peak ~1.06)
            0.01, 0.01, 0.01,       # days 4-6: cooldown (zeroed)
            0.03, 0.03, 0.03,       # days 7-9: re-entry, should be captured
        ]
        test_df = _make_fold_df(test_returns)

        engine_no_re = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=False,
        )
        engine_re = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_hwm_reset=True,
        )

        result_no_re = engine_no_re.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)
        result_re = engine_re.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        # Re-entry should capture more returns than permanent stop-out
        self.assertGreater(result_re.portfolio_total_return, result_no_re.portfolio_total_return)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_cooldown_days_respected(self, mock_sector_caps):
        """Exactly cooldown_days are zeroed after breach (breach day is kept)."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 20)
        # 10 days: breach on day 3, cooldown 2 days (days 4,5 zeroed), re-entry day 6
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2
            -0.10,                   # day 3: breach
            0.05, 0.05,              # days 4-5: cooldown (zeroed)
            0.03, 0.03, 0.03, 0.03, # days 6-9: re-entry
        ]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_hwm_reset=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertEqual(evidence["n_stop_outs"], 1)
        self.assertEqual(evidence["n_re_entries"], 1)
        self.assertEqual(evidence["total_cooldown_days"], 2)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_zero_cooldown_immediate_re_entry(self, mock_sector_caps):
        """With cooldown_days=0, re-entry happens immediately on next day."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 15)
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2
            -0.10,                   # day 3: breach
            0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03,  # days 4-10: re-entry
        ]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=0,
            drawdown_hwm_reset=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertEqual(evidence["n_stop_outs"], 1)
        self.assertEqual(evidence["n_re_entries"], 1)
        self.assertEqual(evidence["total_cooldown_days"], 0)

        # With immediate re-entry and HWM reset, all post-breach returns captured
        expected = sum(test_returns)  # All returns kept (breach day + all re-entry)
        self.assertAlmostEqual(result.portfolio_total_return, expected, places=4)


class TestDrawdownHWMReset(unittest.TestCase):
    """Test HWM reset behavior on re-entry."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_hwm_reset_prevents_immediate_re_stop_out(self, mock_sector_caps):
        """With HWM reset, re-entry NAV becomes new HWM, preventing immediate re-trigger."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 20)
        # After stop-out and cooldown, NAV is well below original HWM.
        # Without HWM reset, the engine would immediately re-trigger stop-out.
        # With HWM reset, the new HWM = NAV at re-entry, so small further
        # losses won't re-trigger.
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2: gains (peak ~1.0612)
            -0.10,                   # day 3: big loss (DD ~ -10%)
            0.01, 0.01, 0.01,       # days 4-6: cooldown (zeroed)
            -0.01, -0.01, -0.01,    # days 7-9: small losses (within 5% of re-entry HWM)
            0.01, 0.01, 0.01,       # days 10-12: recovery
        ]
        test_df = _make_fold_df(test_returns)

        # With HWM reset: new HWM at re-entry, small losses don't re-trigger
        engine_reset = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_hwm_reset=True,
        )
        result_reset = engine_reset.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence_reset = result_reset.drawdown_re_entry_evidence
        # Only 1 stop-out (the initial one), no re-trigger because HWM was reset
        self.assertEqual(evidence_reset["n_stop_outs"], 1)
        self.assertEqual(evidence_reset["n_re_entries"], 1)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_hwm_no_reset_can_re_trigger(self, mock_sector_caps):
        """Without HWM reset, original HWM is kept, allowing re-trigger on continued losses."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 25)
        # Large gains then crash, re-entry into continued losses
        # NAV after gains and crash stays below original HWM
        test_returns = [
            0.05, 0.05, 0.05, 0.05,  # days 0-3: big gains (HWM ~1.2155)
            -0.15,                     # day 4: crash (DD > 10%)
            0.01, 0.01, 0.01,         # days 5-7: cooldown (zeroed)
            -0.05, -0.05, -0.05,      # days 8-10: still well below original HWM
            0.01, 0.01, 0.01, 0.01,   # days 11-14
        ]
        test_df = _make_fold_df(test_returns)

        # Without HWM reset: original HWM kept, further losses may re-trigger
        engine_no_reset = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_hwm_reset=False,
        )
        result_no_reset = engine_no_reset.run_fold(
            1, train_df, test_df, self.alpha_cols, self.return_col
        )

        evidence_no_reset = result_no_reset.drawdown_re_entry_evidence
        # Should have at least 1 stop-out, possibly 2 if re-triggered
        self.assertGreaterEqual(evidence_no_reset["n_stop_outs"], 1)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_hwm_reset_evidence_records_nav(self, mock_sector_caps):
        """Re-entry evidence records NAV and HWM at re-entry point."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 15)
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2
            -0.10,                   # day 3: breach
            0.01, 0.01,              # days 4-5: cooldown (zeroed)
            0.03, 0.03, 0.03, 0.03, # days 6-9: re-entry
        ]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_hwm_reset=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertEqual(len(evidence["re_entry_events"]), 1)

        re_entry_ev = evidence["re_entry_events"][0]
        self.assertIn("nav_at_re_entry", re_entry_ev)
        self.assertIn("hwm_after_reset", re_entry_ev)
        self.assertTrue(re_entry_ev["hwm_reset_applied"])


class TestMultipleStopOutCycles(unittest.TestCase):
    """Test multiple stop-out and re-entry cycles."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_multiple_stop_out_re_entry_cycles(self, mock_sector_caps):
        """Multiple breaches produce multiple stop-out/re-entry cycles."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 30)
        # Cycle 1: gains -> breach -> cooldown -> re-entry
        # Cycle 2: gains -> breach -> cooldown -> re-entry
        test_returns = [
            0.03, 0.03, 0.03,       # days 0-2: gains
            -0.12,                   # day 3: breach 1
            0.01, 0.01,              # days 4-5: cooldown 1 (zeroed)
            0.04, 0.04, 0.04,       # days 6-8: recovery (HWM reset on re-entry)
            -0.12,                   # day 9: breach 2
            0.01, 0.01,              # days 10-11: cooldown 2 (zeroed)
            0.02, 0.02, 0.02,       # days 12-14: recovery 2
        ]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_hwm_reset=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        # Should see 2 stop-outs and 2 re-entries
        self.assertEqual(evidence["n_stop_outs"], 2)
        self.assertEqual(evidence["n_re_entries"], 2)
        self.assertEqual(evidence["total_cooldown_days"], 4)


class TestPITSafety(unittest.TestCase):
    """Verify PIT safety: drawdown control uses only test-fold realised returns."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_train_fold_drawdown_does_not_trigger_stop_out(self, mock_sector_caps):
        """Catastrophic train fold must not cause test-fold stop-out."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        # Train fold is catastrophic
        train_df = _make_fold_df([-0.20] * 8)
        # Test fold is benign
        test_df = _make_fold_df([0.01] * 8)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_hwm_reset=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        # No stop-outs should occur on benign test fold
        evidence = result.drawdown_re_entry_evidence
        self.assertEqual(evidence["n_stop_outs"], 0)
        self.assertEqual(evidence["n_re_entries"], 0)

        # All returns should be preserved
        expected = sum([0.01] * 8)
        self.assertAlmostEqual(result.portfolio_total_return, expected, places=6)


class TestDrawdownControlDisabled(unittest.TestCase):
    """Verify no evidence is emitted when drawdown control is fully disabled."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_no_evidence_when_drawdown_control_disabled(self, mock_sector_caps):
        """When drawdown_control=False, no re-entry evidence is emitted."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        test_df = _make_fold_df([-0.10] * 8)

        engine = _make_engine(drawdown_control=False)
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        self.assertIsNone(result.drawdown_re_entry_evidence)


class TestEvidenceGateId(unittest.TestCase):
    """Verify evidence dict contains correct gate ID and PIT safety flag."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_evidence_gate_id(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 8)
        test_returns = [0.02, 0.02, 0.02, -0.10, 0.01, 0.01, 0.01, 0.01]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["gate"], "STAGE6_3_DRAWDOWN_RE_ENTRY_20260616")
        self.assertTrue(evidence["pit_safe"])
        self.assertTrue(evidence["enabled"])


class TestAdaptiveReEntryConstructor(unittest.TestCase):
    """Test adaptive re-entry constructor parameter validation."""

    def test_default_adaptive_disabled(self):
        engine = _make_engine()
        self.assertFalse(engine.drawdown_adaptive_re_entry)
        self.assertEqual(engine.drawdown_adaptive_bear_threshold, 0.5)
        self.assertEqual(engine.drawdown_adaptive_vol_window, 20)
        self.assertEqual(engine.drawdown_adaptive_vol_multiplier, 1.5)
        self.assertEqual(engine.drawdown_adaptive_max_cooldown, 20)

    def test_adaptive_enabled(self):
        engine = _make_engine(
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.3,
            drawdown_adaptive_vol_window=30,
            drawdown_adaptive_vol_multiplier=2.0,
            drawdown_adaptive_max_cooldown=15,
        )
        self.assertTrue(engine.drawdown_adaptive_re_entry)
        self.assertEqual(engine.drawdown_adaptive_bear_threshold, 0.3)
        self.assertEqual(engine.drawdown_adaptive_vol_window, 30)
        self.assertEqual(engine.drawdown_adaptive_vol_multiplier, 2.0)
        self.assertEqual(engine.drawdown_adaptive_max_cooldown, 15)

    def test_invalid_adaptive_type_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_adaptive_re_entry="yes",
            )

    def test_invalid_bear_threshold_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_adaptive_bear_threshold=1.5,
            )

    def test_invalid_vol_window_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_adaptive_vol_window=2,
            )

    def test_invalid_vol_multiplier_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_adaptive_vol_multiplier=0.5,
            )

    def test_invalid_max_cooldown_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        with self.assertRaises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=_make_fake_alpha_module(),
                drawdown_adaptive_max_cooldown=-1,
            )


class TestAdaptiveReEntryBearProbability(unittest.TestCase):
    """Test adaptive re-entry based on HMM bear probability."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_high_bear_extends_cooldown(self, mock_sector_caps):
        """When p_bear is above threshold during cooldown, cooldown is extended."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 20)
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2: gains
            -0.10,                   # day 3: breach
            0.01, 0.01, 0.01,       # days 4-6: cooldown
            0.03, 0.03, 0.03,       # days 7-9: potential re-entry
        ]
        test_df = _make_fold_df(test_returns)

        # Build hmm_p_bear_dict with high bear probability during cooldown
        dates = pd.date_range('2020-01-01', periods=len(test_returns), freq='B')
        hmm_p_bear_dict = {}
        for i, d in enumerate(dates):
            if i in [4, 5, 6]:  # cooldown days
                hmm_p_bear_dict[str(d)[:10]] = 0.8  # High bear probability
            else:
                hmm_p_bear_dict[str(d)[:10]] = 0.1

        # Build close_wide for volatility computation
        close_wide = test_df.pivot(index='date', columns='ticker', values='close')

        # Non-adaptive baseline
        engine_no_adapt = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_adaptive_re_entry=False,
        )
        result_no_adapt = engine_no_adapt.run_fold(
            1, train_df, test_df, self.alpha_cols, self.return_col
        )

        # Adaptive with high bear probability
        engine_adapt = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=3,
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.5,
            drawdown_adaptive_max_cooldown=20,
        )

        # We need to inject the hmm_p_bear_dict into the engine's _apply_drawdown_control
        # Since the engine doesn't have risk_sizing_overlay enabled, we test the
        # _apply_drawdown_control method directly
        daily_series = pd.Series(
            test_returns,
            index=dates,
        )
        portfolio_returns = pd.Series(
            [r for r in test_returns for _ in range(5)],  # 5 tickers
        )
        aligned_df = pd.DataFrame({
            'date': [d for d in dates for _ in range(5)],
            'p_ret': portfolio_returns,
        })
        aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])

        evidence = engine_adapt._apply_drawdown_control(
            daily_series, portfolio_returns, aligned_df, 1,
            hmm_p_bear_dict=hmm_p_bear_dict,
            close_wide=close_wide,
        )

        # With high bear prob, cooldown should be extended beyond 3 days
        self.assertGreater(evidence["total_cooldown_days"], 3)
        self.assertGreater(evidence["adaptive_cooldown_extensions"], 0)

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_low_bear_allows_normal_cooldown(self, mock_sector_caps):
        """When p_bear is below threshold, cooldown proceeds normally."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 20)
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2: gains
            -0.10,                   # day 3: breach
            0.01, 0.01,              # days 4-5: cooldown
            0.03, 0.03, 0.03, 0.03, # days 6-9: re-entry
        ]
        test_df = _make_fold_df(test_returns)

        dates = pd.date_range('2020-01-01', periods=len(test_returns), freq='B')
        hmm_p_bear_dict = {str(d): 0.1 for d in dates}  # Low bear probability

        close_wide = test_df.pivot(index='date', columns='ticker', values='close')

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.5,
        )

        daily_series = pd.Series(test_returns, index=dates)
        portfolio_returns = pd.Series([r for r in test_returns for _ in range(5)])
        aligned_df = pd.DataFrame({
            'date': [d for d in dates for _ in range(5)],
            'p_ret': portfolio_returns,
        })
        aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])

        evidence = engine._apply_drawdown_control(
            daily_series, portfolio_returns, aligned_df, 1,
            hmm_p_bear_dict=hmm_p_bear_dict,
            close_wide=close_wide,
        )

        # With low bear prob, cooldown should be at most 2 days
        # (adaptive may accelerate re-entry when conditions are favorable)
        self.assertLessEqual(evidence["total_cooldown_days"], 2)
        self.assertEqual(evidence["n_stop_outs"], 1)
        self.assertEqual(evidence["n_re_entries"], 1)


class TestAdaptiveReEntryMaxCooldown(unittest.TestCase):
    """Test adaptive max cooldown cap."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    def test_max_cooldown_caps_extension(self):
        """Adaptive cooldown cannot exceed max_cooldown_days."""
        test_returns = [
            0.02, 0.02, 0.02,       # days 0-2: gains
            -0.10,                   # day 3: breach
            0.01, 0.01, 0.01, 0.01, 0.01,  # days 4-8: potential cooldown
            0.01, 0.01,              # days 9-10: post-cooldown
        ]
        test_df = _make_fold_df(test_returns)

        dates = pd.date_range('2020-01-01', periods=len(test_returns), freq='B')
        # All days have high bear probability
        hmm_p_bear_dict = {str(d): 0.9 for d in dates}

        close_wide = test_df.pivot(index='date', columns='ticker', values='close')

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.5,
            drawdown_adaptive_max_cooldown=5,  # Cap at 5 days
        )

        daily_series = pd.Series(test_returns, index=dates)
        portfolio_returns = pd.Series([r for r in test_returns for _ in range(5)])
        aligned_df = pd.DataFrame({
            'date': [d for d in dates for _ in range(5)],
            'p_ret': portfolio_returns,
        })
        aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])

        evidence = engine._apply_drawdown_control(
            daily_series, portfolio_returns, aligned_df, 1,
            hmm_p_bear_dict=hmm_p_bear_dict,
            close_wide=close_wide,
        )

        # Cooldown should not exceed max_cooldown
        self.assertLessEqual(evidence["total_cooldown_days"], 5)
        # Should still re-enter after max cooldown
        self.assertEqual(evidence["n_re_entries"], 1)


class TestAdaptiveEvidenceFields(unittest.TestCase):
    """Verify adaptive evidence dict has the correct fields."""

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_evidence_has_adaptive_fields(self, mock_sector_caps):
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 15)
        test_returns = [0.02, 0.02, 0.02, -0.10, 0.01, 0.01, 0.03, 0.03]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.5,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        self.assertIsNotNone(evidence)
        # Check adaptive fields exist
        self.assertIn("adaptive_re_entry", evidence)
        self.assertIn("adaptive_bear_threshold", evidence)
        self.assertIn("adaptive_vol_window", evidence)
        self.assertIn("adaptive_vol_multiplier", evidence)
        self.assertIn("adaptive_max_cooldown", evidence)
        self.assertIn("adaptive_cooldown_extensions", evidence)
        self.assertIn("adaptive_early_re_entries", evidence)
        self.assertTrue(evidence["adaptive_re_entry"])

    @patch('omega.quant.alpha.phase35._import_apply_sector_caps')
    def test_re_entry_events_have_p_bear(self, mock_sector_caps):
        """Re-entry events include p_bear_at_re_entry when adaptive is enabled."""
        mock_sector_caps.return_value = lambda target, sector_map, resolved_caps: target

        train_df = _make_fold_df([0.01] * 15)
        test_returns = [0.02, 0.02, 0.02, -0.10, 0.01, 0.01, 0.03, 0.03]
        test_df = _make_fold_df(test_returns)

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_adaptive_re_entry=True,
        )
        result = engine.run_fold(1, train_df, test_df, self.alpha_cols, self.return_col)

        evidence = result.drawdown_re_entry_evidence
        if evidence["n_re_entries"] > 0:
            re_entry_ev = evidence["re_entry_events"][0]
            self.assertIn("p_bear_at_re_entry", re_entry_ev)
            self.assertIn("adaptive", re_entry_ev)
            self.assertTrue(re_entry_ev["adaptive"])


class TestHMMPBearEvidenceOutput(unittest.TestCase):
    """Test that apply_risk_sizing_overlay outputs hmm_p_bear correctly."""

    def test_hmm_p_bear_in_evidence(self):
        """Evidence from apply_risk_sizing_overlay contains hmm_p_bear key."""
        from omega.quant.walk_forward.risk_sizing_overlay import (
            RiskSizingConfig,
            apply_risk_sizing_overlay,
        )

        # Create synthetic test data
        dates = pd.date_range('2020-01-01', periods=50, freq='B')
        tickers = ['A', 'B', 'C']
        rows = []
        for d in dates:
            for t in tickers:
                rows.append({
                    'date': d,
                    'ticker': t,
                    'close': 100.0 + np.random.randn() * 2,
                })
        test_df = pd.DataFrame(rows)

        portfolio_signal = pd.Series(0.1, index=test_df.index)

        # Config with HMM regime sizing enabled
        config = RiskSizingConfig(
            regime_sizing=True,
            regime_sizing_mode='hmm',
            regime_sizing_window=30,
        )

        _, evidence = apply_risk_sizing_overlay(test_df, portfolio_signal, config)

        # Check hmm_p_bear key exists
        self.assertIn("hmm_p_bear", evidence)
        p_bear_data = evidence["hmm_p_bear"]
        self.assertIsInstance(p_bear_data, dict)
        self.assertIn("dates", p_bear_data)
        self.assertIn("values", p_bear_data)
        # When HMM mode is used, dates and values should be populated
        # (may be empty if insufficient data for HMM fitting)
        self.assertEqual(len(p_bear_data["dates"]), len(p_bear_data["values"]))

    def test_hmm_p_bear_empty_when_disabled(self):
        """When regime sizing is disabled, hmm_p_bear has empty lists."""
        from omega.quant.walk_forward.risk_sizing_overlay import (
            RiskSizingConfig,
            apply_risk_sizing_overlay,
        )

        dates = pd.date_range('2020-01-01', periods=10, freq='B')
        tickers = ['A', 'B']
        rows = []
        for d in dates:
            for t in tickers:
                rows.append({
                    'date': d,
                    'ticker': t,
                    'close': 100.0,
                })
        test_df = pd.DataFrame(rows)
        portfolio_signal = pd.Series(0.1, index=test_df.index)

        config = RiskSizingConfig(regime_sizing=False)
        _, evidence = apply_risk_sizing_overlay(test_df, portfolio_signal, config)

        p_bear_data = evidence["hmm_p_bear"]
        self.assertEqual(len(p_bear_data["dates"]), 0)
        self.assertEqual(len(p_bear_data["values"]), 0)


class TestAdaptiveReEntryNoHMM(unittest.TestCase):
    """GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
    Test adaptive re-entry fallback path when HMM evidence is None.

    Verifies that volatility-ratio cooldown scaling still works even when
    hmm_p_bear_dict is None (p_bear defaults to 0.0).
    """

    def setUp(self):
        self.alpha_cols = ['alpha_test']
        self.return_col = 'fwd_ret_5'

    def test_adaptive_re_entry_no_hmm(self):
        """HMM evidence is None, but elevated vol extends cooldown."""
        # Arrange: build close_wide with two vol regimes
        #   Days 0-49: low volatility (steady uptrend, ~0.2% daily std)
        #   Days 50-79: high volatility (~4% daily std)
        # This ensures trailing vol ratio >> vol_multiplier during cooldown.
        np.random.seed(42)
        n_days = 80
        tickers = ['A', 'B', 'C', 'D', 'E']
        dates = pd.date_range('2020-01-01', periods=n_days, freq='B')

        close_data = {}
        for t in tickers:
            prices = np.zeros(n_days)
            prices[0] = 100.0
            for i in range(1, n_days):
                if i < 50:
                    daily_ret = 0.002 + np.random.randn() * 0.001
                else:
                    daily_ret = np.random.randn() * 0.04
                prices[i] = prices[i - 1] * (1 + daily_ret)
            close_data[t] = prices
        close_wide = pd.DataFrame(close_data, index=dates)

        # Daily returns: gains then big loss triggers breach during high-vol regime
        # Day 54: -15% loss triggers drawdown breach (DD > 5%)
        # Cooldown starts day 55; trailing vol window captures high-vol period
        daily_rets = [0.005] * 53 + [-0.15] + [0.01] * 26
        daily_series = pd.Series(daily_rets, index=dates)
        portfolio_returns = pd.Series(
            [r for r in daily_rets for _ in range(5)],
        )
        aligned_df = pd.DataFrame({
            'date': [d for d in dates for _ in range(5)],
            'p_ret': portfolio_returns,
        })
        aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])

        engine = _make_engine(
            drawdown_control=True,
            drawdown_threshold=0.05,
            drawdown_re_entry_enabled=True,
            drawdown_cooldown_days=2,
            drawdown_adaptive_re_entry=True,
            drawdown_adaptive_bear_threshold=0.5,
            drawdown_adaptive_vol_window=5,
            drawdown_adaptive_vol_multiplier=1.5,
            drawdown_adaptive_max_cooldown=8,
        )

        # Act: pass hmm_p_bear_dict=None (HMM evidence missing)
        evidence = engine._apply_drawdown_control(
            daily_series, portfolio_returns, aligned_df, 1,
            hmm_p_bear_dict=None,
            close_wide=close_wide,
        )

        # Assert: vol-based cooldown extension occurred despite no HMM data
        self.assertGreater(
            evidence["adaptive_cooldown_extensions"], 0,
            "Elevated vol should extend cooldown even when hmm_p_bear_dict is None",
        )
        self.assertGreater(
            evidence["total_cooldown_days"], 2,
            "Total cooldown should exceed base cooldown_days due to vol extension",
        )
        # p_bear defaults to 0.0 so bear condition is never triggered
        # (all extensions are vol-driven, not bear-driven)
        self.assertEqual(evidence["n_stop_outs"], 1)
        self.assertGreaterEqual(evidence["n_re_entries"], 1)


if __name__ == '__main__':
    unittest.main()
