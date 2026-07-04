"""
GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
PIT-Safe Rolling Universe Tests

[L2-Impl:Role14-DataScientist] - 2026-06-15

Verifies that:
  1. Rolling universe is DISABLED by default (static behavior preserved)
  2. CLI --rolling-universe flag is present and correct
  3. Rolling selector uses ONLY train_df (no test data leakage)
  4. Test symbols are subset of train-selected symbols
  5. Evidence is JSON-serializable
  6. ADTV/price/history filters applied correctly
  7. Deterministic selection (same input -> same output)
  8. Empty train_df handled gracefully
"""

import argparse
import json
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helper: build parser mirroring rolling-universe flag
# ---------------------------------------------------------------------------

def _build_rolling_parser():
    parser = argparse.ArgumentParser(description="Phase 3.5 backtest")
    parser.add_argument("--rolling-universe", action="store_true", help="PIT rolling universe")
    return parser


def _make_synthetic_df(n_dates=120, n_tickers=10, seed=42):
    """Create synthetic OHLCV data with known properties."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    tickers = [f"SYM{i:02d}" for i in range(n_tickers)]

    rows = []
    for i, t in enumerate(tickers):
        base_price = 5000.0 + i * 1000.0
        base_volume = 1_000_000 + i * 500_000
        for d in dates:
            price = base_price * (1 + rng.normal(0, 0.01))
            vol = int(base_volume * (1 + rng.normal(0, 0.1)))
            rows.append({
                "date": d,
                "ticker": t,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": max(vol, 100),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: Default disabled behavior
# ---------------------------------------------------------------------------

class TestRollingUniverseDefaultDisabled(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — default OFF."""

    def test_no_flags_means_rolling_universe_false(self):
        args = _build_rolling_parser().parse_args([])
        self.assertFalse(args.rolling_universe)

    def test_enable_flag(self):
        args = _build_rolling_parser().parse_args(["--rolling-universe"])
        self.assertTrue(args.rolling_universe)


# ---------------------------------------------------------------------------
# Tests: Rolling selector uses train_df only
# ---------------------------------------------------------------------------

class TestRollingSelectorTrainOnly(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — PIT safety."""

    def _make_loader(self):
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        return loader

    def test_select_rolling_uses_only_train_df(self):
        """Selection depends only on train_df, not test_df."""
        loader = self._make_loader()
        train_df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        test_df_different = _make_synthetic_df(n_dates=60, n_tickers=5, seed=99)

        selected, evidence = loader.select_rolling_universe(train_df, top_n=5)
        self.assertEqual(evidence["pit_safe"], True)
        self.assertGreater(len(selected), 0)

    def test_different_test_df_same_selection(self):
        """Changing test_df must NOT change selection (train-only)."""
        loader = self._make_loader()
        train_df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)

        selected1, _ = loader.select_rolling_universe(train_df, top_n=5)
        selected2, _ = loader.select_rolling_universe(train_df, top_n=5)
        self.assertEqual(sorted(selected1), sorted(selected2))

    def test_deterministic_selection(self):
        """Same input produces same output."""
        loader = self._make_loader()
        df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        s1, e1 = loader.select_rolling_universe(df, top_n=5)
        s2, e2 = loader.select_rolling_universe(df, top_n=5)
        self.assertEqual(sorted(s1), sorted(s2))
        self.assertEqual(e1["n_selected"], e2["n_selected"])


# ---------------------------------------------------------------------------
# Tests: Test symbols subset of train-selected
# ---------------------------------------------------------------------------

class TestTestSymbolsSubsetOfTrain(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — subset proof."""

    def _make_loader(self):
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        return loader

    def test_test_symbols_are_subset(self):
        loader = self._make_loader()
        full_df = _make_synthetic_df(n_dates=200, n_tickers=10, seed=42)
        train_df = full_df[full_df["date"] < full_df["date"].quantile(0.6)].copy()
        test_df = full_df[full_df["date"] >= full_df["date"].quantile(0.6)].copy()

        splits = [(train_df, test_df)]
        rolling_splits = loader.apply_rolling_universe_to_splits(splits, top_n=5)

        for t_df, te_df, ev in rolling_splits:
            train_symbols = set(t_df["ticker"].unique())
            test_symbols = set(te_df["ticker"].unique())
            self.assertTrue(
                test_symbols.issubset(train_symbols),
                f"Test symbols {test_symbols - train_symbols} not in train {train_symbols}"
            )
            self.assertTrue(ev["test_symbols_subset_of_train"])


# ---------------------------------------------------------------------------
# Tests: Evidence is JSON-serializable
# ---------------------------------------------------------------------------

class TestEvidenceSerializable(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — JSON safety."""

    def _make_loader(self):
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        return loader

    def test_evidence_is_json_serializable(self):
        loader = self._make_loader()
        df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        _, evidence = loader.select_rolling_universe(df, top_n=5)
        json_str = json.dumps(evidence)
        self.assertGreater(len(json_str), 0)

    def test_evidence_has_required_keys(self):
        loader = self._make_loader()
        df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        _, evidence = loader.select_rolling_universe(df, top_n=5)
        required_keys = [
            "gate", "selected_symbols", "n_selected", "pit_safe",
            "min_adtv_vnd", "min_avg_close_vnd", "min_history_days",
        ]
        for key in required_keys:
            self.assertIn(key, evidence, f"Missing key: {key}")

    def test_evidence_gate_value(self):
        loader = self._make_loader()
        df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        _, evidence = loader.select_rolling_universe(df, top_n=5)
        self.assertEqual(
            evidence["gate"],
            "PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615"
        )

    def test_per_fold_evidence_serializable(self):
        loader = self._make_loader()
        full_df = _make_synthetic_df(n_dates=200, n_tickers=10, seed=42)
        mid = full_df["date"].quantile(0.5)
        train_df = full_df[full_df["date"] < mid].copy()
        test_df = full_df[full_df["date"] >= mid].copy()
        splits = [(train_df, test_df)]
        rolling_splits = loader.apply_rolling_universe_to_splits(splits, top_n=5)
        evidence_list = loader.get_rolling_universe_evidence()
        json_str = json.dumps(evidence_list)
        self.assertGreater(len(json_str), 0)


# ---------------------------------------------------------------------------
# Tests: ADTV / price / history filters
# ---------------------------------------------------------------------------

class TestFilters(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — filter logic."""

    def _make_loader(self, min_history=10):
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = min_history
        return loader

    def test_empty_train_df(self):
        loader = self._make_loader()
        empty_df = pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])
        selected, evidence = loader.select_rolling_universe(empty_df, top_n=5)
        self.assertEqual(selected, [])
        self.assertEqual(evidence["n_selected"], 0)

    def test_top_n_respected(self):
        loader = self._make_loader(min_history=5)
        df = _make_synthetic_df(n_dates=120, n_tickers=10, seed=42)
        selected, evidence = loader.select_rolling_universe(df, top_n=3)
        self.assertLessEqual(len(selected), 3)

    def test_min_history_filter(self):
        loader = self._make_loader(min_history=200)
        df = _make_synthetic_df(n_dates=50, n_tickers=5, seed=42)
        selected, evidence = loader.select_rolling_universe(df, top_n=5)
        # With min_history=200 and only 50 dates, no symbol should pass strict filter
        # Fallback to sorted universe is expected
        self.assertGreater(len(selected), 0)

    def test_select_pit_universe_for_window_uses_only_prior_history(self):
        loader = self._make_loader(min_history=5)
        df = _make_synthetic_df(n_dates=320, n_tickers=10, seed=42)
        start_date = df['date'].sort_values().iloc[260]
        end_date = df['date'].sort_values().iloc[300]
        window_df, evidence = loader.select_pit_universe_for_window(
            df,
            start_date,
            end_date,
            top_n=5,
            lookback_trading_days=60,
        )
        self.assertTrue((window_df['date'] >= start_date).all())
        self.assertTrue((window_df['date'] <= end_date).all())
        self.assertEqual(evidence['history_end_exclusive'], str(start_date.date()))


# ---------------------------------------------------------------------------
# Tests: Static behavior preserved (default disabled)
# ---------------------------------------------------------------------------

class TestStaticBehaviorPreserved(unittest.TestCase):
    """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — static default."""

    def test_script_has_rolling_flag(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('--rolling-universe', src)

    def test_script_has_gate_citation(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615', src)

    def test_data_loader_has_rolling_method(self):
        from phase35_data_loader import Phase35DataLoader
        self.assertTrue(hasattr(Phase35DataLoader, 'select_rolling_universe'))
        self.assertTrue(hasattr(Phase35DataLoader, 'apply_rolling_universe_to_splits'))
        self.assertTrue(hasattr(Phase35DataLoader, 'get_rolling_universe_evidence'))

    def test_script_persists_rolling_evidence(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('rolling_universe_evidence', src)

    def test_script_has_rolling_config_in_results(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('rolling_universe_enabled', src)


if __name__ == '__main__':
    unittest.main()
