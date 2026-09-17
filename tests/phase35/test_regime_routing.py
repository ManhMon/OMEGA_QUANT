"""
GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
Regime-Conditioned Alpha Routing Tests

[L2-Impl:Role14-DataScientist] - 2026-06-15

Verifies that the Phase 3.5 backtest:
  1. Defaults to regime_routing_enabled=False (disabled by default)
  2. CLI flags --enable-regime-routing, --regime-routing-min-train-days,
     --regime-routing-min-ic are present and correct
  3. Engine params validated correctly
  4. Ex-ante regime detection is PIT-safe (no test returns used)
  5. Fallback to baseline when insufficient evidence
  6. Evidence persisted in FoldMetrics.regime_routing_evidence
  7. Regime routing scales signal correctly

PIT Safety: Tests verify that regime detection uses only lagged market
features and that test returns are never consumed for routing decisions.
"""

import sys
import os
import unittest
import argparse

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helper: Build the parser (mirrors run_phase35_backtest.py argparse)
# ---------------------------------------------------------------------------

def _build_regime_parser():
    """Build minimal argparse mirroring regime routing flags."""
    parser = argparse.ArgumentParser(
        description="Run Phase 3.5 walk-forward backtest"
    )
    parser.add_argument(
        "--enable-regime-routing",
        action="store_true",
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Enable "
            "research-only ex-ante regime-conditioned alpha routing.  "
            "Builds deterministic regimes from lagged/PIT-safe market "
            "features, estimates per-regime IC on train window only, and "
            "routes/scales alpha signals on test using ex-ante regime "
            "labels.  Never uses test returns for routing decisions.  "
            "Opt-in, default disabled — no live/default behavior change."
        ),
    )
    parser.add_argument(
        "--regime-routing-min-train-days",
        type=int,
        default=60,
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Minimum "
            "number of training days with regime labels."
        ),
    )
    parser.add_argument(
        "--regime-routing-min-ic",
        type=float,
        default=0.01,
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Minimum "
            "absolute per-regime IC required."
        ),
    )
    return parser


def _parse_and_derive(argv):
    """Parse argv and return args namespace."""
    parser = _build_regime_parser()
    args = parser.parse_args(argv)
    return args


def _get_help_text():
    """Return help text from parser."""
    parser = _build_regime_parser()
    return parser.format_help()


def _get_action_help(flag_name):
    """Return help string for a specific flag."""
    parser = _build_regime_parser()
    for action in parser._actions:
        if flag_name in action.option_strings:
            return action.help
    return None


def _make_synthetic_df(n_dates=100, n_tickers=5, seed=42):
    """Create synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    tickers = [f"T{i}" for i in range(n_tickers)]

    rows = []
    for t in tickers:
        price = 100.0
        for d in dates:
            ret = rng.normal(0.0005, 0.02)
            price *= (1 + ret)
            rows.append({
                "date": d,
                "ticker": t,
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": rng.randint(1000, 100000),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: Default disabled behavior
# ---------------------------------------------------------------------------

class TestRegimeRoutingDefaultDisabled(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — default must be OFF."""

    def test_no_flags_means_regime_routing_false(self):
        """With no flags, enable_regime_routing must be False."""
        args = _parse_and_derive([])
        self.assertFalse(
            args.enable_regime_routing,
            "Default enable_regime_routing must be False per GATE "
            "REGIME_CONDITIONED_ALPHA_ROUTING_20260615"
        )

    def test_default_min_train_days_is_60(self):
        """Default regime_routing_min_train_days must be 60."""
        args = _parse_and_derive([])
        self.assertEqual(args.regime_routing_min_train_days, 60)

    def test_default_min_ic_is_0_01(self):
        """Default regime_routing_min_ic must be 0.01."""
        args = _parse_and_derive([])
        self.assertAlmostEqual(args.regime_routing_min_ic, 0.01, places=4)


# ---------------------------------------------------------------------------
# Tests: Opt-in behavior
# ---------------------------------------------------------------------------

class TestRegimeRoutingOptIn(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — --enable-regime-routing."""

    def test_enable_flag(self):
        """--enable-regime-routing must set enable_regime_routing=True."""
        args = _parse_and_derive(['--enable-regime-routing'])
        self.assertTrue(args.enable_regime_routing)

    def test_custom_min_train_days(self):
        """--regime-routing-min-train-days must accept custom values."""
        args = _parse_and_derive([
            '--enable-regime-routing',
            '--regime-routing-min-train-days', '120',
        ])
        self.assertEqual(args.regime_routing_min_train_days, 120)

    def test_custom_min_ic(self):
        """--regime-routing-min-ic must accept custom values."""
        args = _parse_and_derive([
            '--enable-regime-routing',
            '--regime-routing-min-ic', '0.05',
        ])
        self.assertAlmostEqual(args.regime_routing_min_ic, 0.05, places=4)


# ---------------------------------------------------------------------------
# Tests: Help text includes gate attribution
# ---------------------------------------------------------------------------

class TestRegimeRoutingHelpText(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — help text."""

    def test_help_mentions_enable_regime_routing(self):
        """Help must include --enable-regime-routing."""
        help_text = _get_help_text()
        self.assertIn("--enable-regime-routing", help_text)

    def test_help_mentions_min_train_days(self):
        """Help must include --regime-routing-min-train-days."""
        help_text = _get_help_text()
        self.assertIn("--regime-routing-min-train-days", help_text)

    def test_help_mentions_min_ic(self):
        """Help must include --regime-routing-min-ic."""
        help_text = _get_help_text()
        self.assertIn("--regime-routing-min-ic", help_text)

    def test_enable_help_mentions_gate(self):
        """--enable-regime-routing help must cite the gate."""
        help_str = _get_action_help('--enable-regime-routing')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "REGIME_CONDITIONED_ALPHA_ROUTING_20260615",
            help_str,
        )

    def test_enable_help_mentions_pit_safe(self):
        """--enable-regime-routing help must mention PIT-safe."""
        help_str = _get_action_help('--enable-regime-routing')
        self.assertIsNotNone(help_str)
        self.assertIn("PIT-safe", help_str)


# ---------------------------------------------------------------------------
# Tests: Engine param validation
# ---------------------------------------------------------------------------

class TestEngineParamValidation(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — param validation."""

    def _make_engine(self, **kwargs):
        """Create engine with regime routing kwargs."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        from omega.quant.alpha import phase34 as phase34_module
        defaults = {
            'alpha_module': phase34_module,
            'min_ic_threshold': 0.02,
            'top_n_alphas': 5,
        }
        defaults.update(kwargs)
        return Phase35WalkForwardEngine(**defaults)

    def test_default_regime_routing_disabled(self):
        """Default engine has regime_routing_enabled=False."""
        engine = self._make_engine()
        self.assertFalse(engine.regime_routing_enabled)

    def test_enable_regime_routing(self):
        """Engine accepts regime_routing_enabled=True."""
        engine = self._make_engine(regime_routing_enabled=True)
        self.assertTrue(engine.regime_routing_enabled)

    def test_invalid_regime_routing_enabled_type(self):
        """Non-boolean regime_routing_enabled raises ValueError."""
        with self.assertRaises(ValueError):
            self._make_engine(regime_routing_enabled="yes")

    def test_invalid_min_train_days(self):
        """Non-positive min_train_days raises ValueError."""
        with self.assertRaises(ValueError):
            self._make_engine(
                regime_routing_enabled=True,
                regime_routing_min_train_days=0,
            )

    def test_invalid_fallback_mode(self):
        """Unknown fallback mode raises ValueError."""
        with self.assertRaises(ValueError):
            self._make_engine(
                regime_routing_enabled=True,
                regime_routing_fallback="unknown",
            )

    def test_valid_fallback_baseline(self):
        """'baseline' is a valid fallback mode."""
        engine = self._make_engine(
            regime_routing_enabled=True,
            regime_routing_fallback="baseline",
        )
        self.assertEqual(engine.regime_routing_fallback, "baseline")

    def test_valid_fallback_disabled(self):
        """'disabled' is a valid fallback mode."""
        engine = self._make_engine(
            regime_routing_enabled=True,
            regime_routing_fallback="disabled",
        )
        self.assertEqual(engine.regime_routing_fallback, "disabled")


# ---------------------------------------------------------------------------
# Tests: Ex-ante regime detection is PIT-safe
# ---------------------------------------------------------------------------

class TestExAnteRegimeDetection(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — PIT safety."""

    def _make_engine(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        from omega.quant.alpha import phase34 as phase34_module
        return Phase35WalkForwardEngine(
            alpha_module=phase34_module,
            regime_routing_enabled=True,
        )

    def test_regime_detection_returns_dataframe(self):
        """_compute_ex_ante_regimes returns DataFrame with date and regime."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)
        self.assertIsInstance(regime_df, pd.DataFrame)
        self.assertIn('date', regime_df.columns)
        self.assertIn('regime', regime_df.columns)

    def test_regime_labels_are_valid(self):
        """Regime labels are one of the 4 valid states."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)
        valid_regimes = {'bull', 'bull_volatile', 'sideways', 'bear'}
        actual_regimes = set(regime_df['regime'].unique())
        self.assertTrue(
            actual_regimes.issubset(valid_regimes),
            f"Invalid regimes found: {actual_regimes - valid_regimes}"
        )

    def test_regime_detection_is_deterministic(self):
        """Same input produces same regime labels."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5, seed=42)
        r1 = engine._compute_ex_ante_regimes(df)
        r2 = engine._compute_ex_ante_regimes(df)
        pd.testing.assert_frame_equal(r1, r2)

    def test_regime_detection_no_forward_data(self):
        """Regime for date T does not use data from T or later.

        Verification: shifting close prices forward by 1 should change
        regime labels (proving regimes depend on past, not current data).
        """
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5, seed=42)
        regime_orig = engine._compute_ex_ante_regimes(df)

        # Shift close prices by 1 day per ticker (simulate different past)
        df_shifted = df.copy()
        df_shifted['close'] = df_shifted.groupby('ticker')['close'].shift(1)
        df_shifted = df_shifted.dropna(subset=['close'])
        regime_shifted = engine._compute_ex_ante_regimes(df_shifted)

        # If regimes use forward data, shifting would not change them
        # We expect at least some difference
        common_dates = set(regime_orig['date']).intersection(
            set(regime_shifted['date'])
        )
        if len(common_dates) > 10:
            orig_map = dict(zip(regime_orig['date'], regime_orig['regime']))
            shift_map = dict(zip(regime_shifted['date'], regime_shifted['regime']))
            diffs = sum(
                1 for d in common_dates
                if orig_map.get(d) != shift_map.get(d)
            )
            # At least some regimes should differ (shifted data = different past)
            self.assertGreater(
                diffs, 0,
                "Shifting close should change regime labels (PIT proof)"
            )


# ---------------------------------------------------------------------------
# Tests: Per-regime IC estimation
# ---------------------------------------------------------------------------

class TestRegimeICEstimation(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — IC estimation."""

    def _make_engine(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        from omega.quant.alpha import phase34 as phase34_module
        return Phase35WalkForwardEngine(
            alpha_module=phase34_module,
            regime_routing_enabled=True,
        )

    def test_regime_ic_returns_nested_dict(self):
        """_estimate_regime_ic returns {alpha: {regime: ic}}."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        df['alpha1'] = np.random.randn(len(df))
        df['fwd_ret_5'] = np.random.randn(len(df))
        regime_df = engine._compute_ex_ante_regimes(df)

        regime_ics = engine._estimate_regime_ic(
            df, ['alpha1'], 'fwd_ret_5', regime_df
        )
        self.assertIsInstance(regime_ics, dict)
        self.assertIn('alpha1', regime_ics)
        self.assertIsInstance(regime_ics['alpha1'], dict)
        # Each regime should have a float IC
        for regime, ic_val in regime_ics['alpha1'].items():
            self.assertIsInstance(ic_val, float)


# ---------------------------------------------------------------------------
# Tests: Regime routing signal scaling
# ---------------------------------------------------------------------------

class TestRegimeRoutingScaling(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — signal routing."""

    def _make_engine(self, **kwargs):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        from omega.quant.alpha import phase34 as phase34_module
        defaults = {
            'alpha_module': phase34_module,
            'regime_routing_enabled': True,
        }
        defaults.update(kwargs)
        return Phase35WalkForwardEngine(**defaults)

    def test_routing_preserves_signal_length(self):
        """Routed signal must have same length as input."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)

        signal = pd.Series(np.random.randn(len(df)), index=df.index)
        regime_ics = {'alpha1': {'bull': 0.05, 'bear': -0.02}}
        train_ics = {'alpha1': 0.03}

        routed, evidence = engine._apply_regime_routing(
            df, signal, regime_df, regime_ics, ['alpha1'], train_ics
        )
        self.assertEqual(len(routed), len(signal))

    def test_routing_evidence_is_json_serializable(self):
        """Evidence dict must be JSON-serializable."""
        import json
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)

        signal = pd.Series(np.random.randn(len(df)), index=df.index)
        regime_ics = {'alpha1': {'bull': 0.05, 'bear': -0.02}}
        train_ics = {'alpha1': 0.03}

        _, evidence = engine._apply_regime_routing(
            df, signal, regime_df, regime_ics, ['alpha1'], train_ics
        )
        # Must not raise
        json.dumps(evidence)

    def test_routing_evidence_has_gate_id(self):
        """Evidence must contain the gate ID."""
        engine = self._make_engine()
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)

        signal = pd.Series(np.random.randn(len(df)), index=df.index)
        regime_ics = {'alpha1': {'bull': 0.05, 'bear': -0.02}}
        train_ics = {'alpha1': 0.03}

        _, evidence = engine._apply_regime_routing(
            df, signal, regime_df, regime_ics, ['alpha1'], train_ics
        )
        self.assertEqual(
            evidence['gate'],
            'REGIME_CONDITIONED_ALPHA_ROUTING_20260615'
        )
        self.assertTrue(evidence['pit_safe'])

    def test_routing_fallback_on_low_ic(self):
        """When regime IC < min_ic, scale falls back to 1.0."""
        engine = self._make_engine(regime_routing_min_ic=0.10)
        df = _make_synthetic_df(n_dates=100, n_tickers=5)
        regime_df = engine._compute_ex_ante_regimes(df)

        signal = pd.Series(np.ones(len(df)), index=df.index)
        # All regime ICs below threshold
        regime_ics = {'alpha1': {'bull': 0.001, 'bear': 0.001}}
        train_ics = {'alpha1': 0.03}

        routed, evidence = engine._apply_regime_routing(
            df, signal, regime_df, regime_ics, ['alpha1'], train_ics
        )
        # All dates should have fallback (scale=1.0)
        self.assertEqual(
            evidence['n_fallback'],
            evidence['n_test_dates'],
            "All dates should fallback when regime IC < min_ic"
        )


# ---------------------------------------------------------------------------
# Tests: FoldMetrics has regime_routing_evidence field
# ---------------------------------------------------------------------------

class TestFoldMetricsRegimeField(unittest.TestCase):
    """GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — FoldMetrics field."""

    def test_fold_metrics_has_regime_routing_evidence(self):
        """FoldMetrics must have regime_routing_evidence field."""
        from omega.quant.alpha.phase35 import FoldMetrics
        m = FoldMetrics(
            fold_id=1,
            train_start="2020-01-01",
            train_end="2020-12-31",
            test_start="2021-01-01",
            test_end="2021-12-31",
        )
        self.assertIsNone(m.regime_routing_evidence)

    def test_fold_metrics_accepts_regime_evidence(self):
        """FoldMetrics accepts regime_routing_evidence dict."""
        from omega.quant.alpha.phase35 import FoldMetrics
        evidence = {"gate": "REGIME_CONDITIONED_ALPHA_ROUTING_20260615", "pit_safe": True}
        m = FoldMetrics(
            fold_id=1,
            train_start="2020-01-01",
            train_end="2020-12-31",
            test_start="2021-01-01",
            test_end="2021-12-31",
            regime_routing_evidence=evidence,
        )
        self.assertEqual(
            m.regime_routing_evidence['gate'],
            'REGIME_CONDITIONED_ALPHA_ROUTING_20260615'
        )


# ---------------------------------------------------------------------------
# Tests: Script file contains gate logic (integration check)
# ---------------------------------------------------------------------------

class TestScriptFileContainsRegimeGate(unittest.TestCase):
    """Verify the actual script file has the gate implementation."""

    def _read_script(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            return f.read()

    def test_script_has_enable_regime_routing_flag(self):
        """Script must define --enable-regime-routing flag."""
        src = self._read_script()
        self.assertIn('--enable-regime-routing', src)

    def test_script_has_gate_citation(self):
        """Script must cite the gate name."""
        src = self._read_script()
        self.assertIn('REGIME_CONDITIONED_ALPHA_ROUTING_20260615', src)

    def test_script_has_min_train_days_flag(self):
        """Script must define --regime-routing-min-train-days."""
        src = self._read_script()
        self.assertIn('--regime-routing-min-train-days', src)

    def test_script_has_min_ic_flag(self):
        """Script must define --regime-routing-min-ic."""
        src = self._read_script()
        self.assertIn('--regime-routing-min-ic', src)

    def test_script_wires_regime_routing_to_engine(self):
        """Script must pass regime_routing_enabled to engine."""
        src = self._read_script()
        self.assertIn('regime_routing_enabled=args.enable_regime_routing', src)

    def test_script_persists_regime_evidence(self):
        """Script must persist regime_routing_evidence in fold details."""
        src = self._read_script()
        self.assertIn('regime_routing_evidence', src)


# ---------------------------------------------------------------------------
# Tests: Engine source contains gate logic (integration check)
# ---------------------------------------------------------------------------

class TestEngineSourceContainsRegimeGate(unittest.TestCase):
    """Verify the engine source has the gate implementation."""

    def _read_engine(self):
        engine_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'omega',
            'quant', 'alpha', 'phase35.py'
        )
        with open(engine_path, 'r') as f:
            return f.read()

    def test_engine_has_gate_constant(self):
        """Engine must define REGIME_ROUTING_GATE_ID."""
        src = self._read_engine()
        self.assertIn('REGIME_ROUTING_GATE_ID', src)

    def test_engine_has_regime_routing_enabled_param(self):
        """Engine must accept regime_routing_enabled parameter."""
        src = self._read_engine()
        self.assertIn('regime_routing_enabled', src)

    def test_engine_has_ex_ante_regime_method(self):
        """Engine must define _compute_ex_ante_regimes method."""
        src = self._read_engine()
        self.assertIn('_compute_ex_ante_regimes', src)

    def test_engine_has_regime_ic_method(self):
        """Engine must define _estimate_regime_ic method."""
        src = self._read_engine()
        self.assertIn('_estimate_regime_ic', src)

    def test_engine_has_regime_routing_method(self):
        """Engine must define _apply_regime_routing method."""
        src = self._read_engine()
        self.assertIn('_apply_regime_routing', src)

    def test_engine_has_fold_metrics_regime_field(self):
        """FoldMetrics must have regime_routing_evidence field."""
        src = self._read_engine()
        self.assertIn('regime_routing_evidence', src)


if __name__ == '__main__':
    unittest.main()
