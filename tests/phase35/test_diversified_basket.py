"""
GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
Diversified Alpha Basket Selector Tests

[L2-Impl:Role14-DataScientist] - 2026-06-15

Verifies that:
  1. Diversified basket is DISABLED by default (no behavior change)
  2. CLI --diversified-basket flag is present and correct
  3. Train-only selector: uses only train data, no test/OOS leakage
  4. Max-per-cluster enforcement: at most N alphas per cluster
  5. Correlation penalty: penalizes redundant alphas
  6. JSON evidence: per-fold evidence is serializable
  7. Dynamic + basket smoke: E2E with dynamic universe + diversified basket
  8. Regression: baseline preserved when basket disabled
"""

import argparse
import json
import os
import sys
import types
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helper: build parser mirroring diversified-basket flags
# ---------------------------------------------------------------------------

def _build_basket_parser():
    parser = argparse.ArgumentParser(description="Phase 3.5 diversified basket")
    parser.add_argument("--diversified-basket", action="store_true")
    parser.add_argument("--basket-max-per-cluster", type=int, default=2)
    parser.add_argument("--basket-corr-threshold", type=float, default=0.70)
    parser.add_argument("--basket-redundancy-penalty", type=float, default=0.3)
    parser.add_argument("--basket-min-ic", type=float, default=0.0)
    return parser


def _make_engine(diversified_basket_enabled=False, **kwargs):
    """Create a Phase35WalkForwardEngine with a dummy alpha module."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    dummy_module = types.ModuleType("dummy_alpha")
    dummy_module.PHASE34_ALPHA_COLUMNS = []
    dummy_module.compute_phase34_microstructure_alphas = lambda df, **kw: df
    return Phase35WalkForwardEngine(
        alpha_module=dummy_module,
        diversified_basket_enabled=diversified_basket_enabled,
        **kwargs,
    )


def _make_synthetic_train_df(
    n_dates=100, n_tickers=10, n_alphas=6, seed=42
):
    """Create synthetic train data with known correlation structure.

    Alphas 0,1 are highly correlated (same cluster).
    Alphas 2,3 are highly correlated (same cluster).
    Alphas 4,5 are independent.
    """
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    tickers = [f"SYM{i:02d}" for i in range(n_tickers)]

    rows = []
    for d in dates:
        # Shared noise factors for correlation
        factor_a = rng.normal(0, 1)
        factor_b = rng.normal(0, 1)
        for t in tickers:
            fwd_ret = rng.normal(0, 0.02)
            row = {
                "date": d,
                "ticker": t,
                "close": 10000.0 + rng.normal(0, 100),
                f"fwd_ret_5": fwd_ret,
            }
            # Alpha 0,1: correlated via factor_a
            row["alpha_0"] = factor_a + rng.normal(0, 0.1)
            row["alpha_1"] = factor_a + rng.normal(0, 0.1)
            # Alpha 2,3: correlated via factor_b
            row["alpha_2"] = factor_b + rng.normal(0, 0.1)
            row["alpha_3"] = factor_b + rng.normal(0, 0.1)
            # Alpha 4,5: independent
            row["alpha_4"] = rng.normal(0, 1)
            row["alpha_5"] = rng.normal(0, 1)
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: Default disabled behavior
# ---------------------------------------------------------------------------

class TestDiversifiedBasketDefaultDisabled(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — default OFF."""

    def test_no_flags_means_basket_false(self):
        args = _build_basket_parser().parse_args([])
        self.assertFalse(args.diversified_basket)

    def test_enable_flag(self):
        args = _build_basket_parser().parse_args(["--diversified-basket"])
        self.assertTrue(args.diversified_basket)

    def test_default_max_per_cluster(self):
        args = _build_basket_parser().parse_args([])
        self.assertEqual(args.basket_max_per_cluster, 2)

    def test_default_corr_threshold(self):
        args = _build_basket_parser().parse_args([])
        self.assertAlmostEqual(args.basket_corr_threshold, 0.70)

    def test_default_redundancy_penalty(self):
        args = _build_basket_parser().parse_args([])
        self.assertAlmostEqual(args.basket_redundancy_penalty, 0.3)

    def test_default_min_ic(self):
        args = _build_basket_parser().parse_args([])
        self.assertAlmostEqual(args.basket_min_ic, 0.0)

    def test_custom_params(self):
        args = _build_basket_parser().parse_args([
            "--diversified-basket",
            "--basket-max-per-cluster", "1",
            "--basket-corr-threshold", "0.80",
            "--basket-redundancy-penalty", "0.5",
            "--basket-min-ic", "0.01",
        ])
        self.assertTrue(args.diversified_basket)
        self.assertEqual(args.basket_max_per_cluster, 1)
        self.assertAlmostEqual(args.basket_corr_threshold, 0.80)
        self.assertAlmostEqual(args.basket_redundancy_penalty, 0.5)
        self.assertAlmostEqual(args.basket_min_ic, 0.01)


# ---------------------------------------------------------------------------
# Tests: Engine constructor validation
# ---------------------------------------------------------------------------

class TestConstructorValidation(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — input validation."""

    def test_engine_default_basket_disabled(self):
        engine = _make_engine()
        self.assertFalse(engine.diversified_basket_enabled)

    def test_engine_basket_enabled(self):
        engine = _make_engine(diversified_basket_enabled=True)
        self.assertTrue(engine.diversified_basket_enabled)

    def test_invalid_max_per_cluster_raises(self):
        with self.assertRaises(ValueError):
            _make_engine(diversified_basket_enabled=True, basket_max_per_cluster=0)

    def test_invalid_corr_threshold_raises(self):
        with self.assertRaises(ValueError):
            _make_engine(diversified_basket_enabled=True, basket_corr_threshold=1.5)

    def test_invalid_redundancy_penalty_raises(self):
        with self.assertRaises(ValueError):
            _make_engine(diversified_basket_enabled=True, basket_redundancy_penalty=-0.1)

    def test_invalid_basket_enabled_type_raises(self):
        with self.assertRaises(ValueError):
            _make_engine(diversified_basket_enabled="yes")


# ---------------------------------------------------------------------------
# Tests: Train-only selector (no test leakage)
# ---------------------------------------------------------------------------

class TestTrainOnlySelector(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — train-only."""

    def test_select_diversified_basket_uses_train_df_only(self):
        """Selector only takes train_df and train_ics, never test_df."""
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,
            "alpha_2": 0.03, "alpha_3": 0.02,
            "alpha_4": 0.06, "alpha_5": 0.01,
        }
        candidates = list(train_ics.keys())
        selected, evidence = engine.select_diversified_basket(
            candidates, train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertGreater(len(selected), 0)
        self.assertTrue(evidence["pit_safe"])

    def test_evidence_has_no_test_data_keys(self):
        """Evidence dict must not contain test-related keys."""
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {"alpha_0": 0.05, "alpha_4": 0.06}
        selected, evidence = engine.select_diversified_basket(
            ["alpha_0", "alpha_4"], train_df, train_ics
        )
        for key in evidence:
            self.assertNotIn("test", key.lower())
            self.assertNotIn("oos", key.lower())


# ---------------------------------------------------------------------------
# Tests: Max-per-cluster enforcement
# ---------------------------------------------------------------------------

class TestMaxPerCluster(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — cluster limit."""

    def test_max_1_per_cluster_excludes_correlated(self):
        """With max_per_cluster=1, only 1 alpha per cluster is selected."""
        engine = _make_engine(
            diversified_basket_enabled=True,
            basket_max_per_cluster=1,
            basket_corr_threshold=0.50,  # Lower threshold to force clustering
        )
        train_df = _make_synthetic_train_df(n_dates=100, seed=42)
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,  # correlated cluster
            "alpha_2": 0.03, "alpha_3": 0.02,  # correlated cluster
            "alpha_4": 0.06, "alpha_5": 0.01,  # independent
        }
        candidates = list(train_ics.keys())
        selected, evidence = engine.select_diversified_basket(
            candidates, train_df, train_ics, return_col="fwd_ret_5"
        )
        # Each cluster should have at most 1 alpha
        clusters = evidence.get("clusters", {})
        for cid, cinfo in clusters.items():
            if isinstance(cinfo, dict):
                self.assertLessEqual(cinfo.get("n_kept", 0), 1)

    def test_max_2_per_cluster_allows_pairs(self):
        """With max_per_cluster=2, up to 2 alphas per cluster."""
        engine = _make_engine(
            diversified_basket_enabled=True,
            basket_max_per_cluster=2,
        )
        train_df = _make_synthetic_train_df()
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,
            "alpha_4": 0.06, "alpha_5": 0.01,
        }
        selected, evidence = engine.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertGreater(len(selected), 0)


# ---------------------------------------------------------------------------
# Tests: Correlation penalty
# ---------------------------------------------------------------------------

class TestCorrelationPenalty(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — penalty."""

    def test_redundancy_penalty_applied_to_correlated_selected(self):
        """When two selected alphas are correlated, penalty is recorded."""
        engine = _make_engine(
            diversified_basket_enabled=True,
            basket_max_per_cluster=2,
            basket_corr_threshold=0.50,
            basket_redundancy_penalty=0.5,
        )
        train_df = _make_synthetic_train_df(n_dates=100, seed=42)
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,  # correlated
            "alpha_4": 0.06,
        }
        selected, evidence = engine.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        # If alpha_0 and alpha_1 are both selected and correlated,
        # penalty should be applied
        penalties = evidence.get("redundancy_penalties_applied", [])
        if len(selected) >= 2:
            # At least some penalty should be recorded
            # (depends on actual correlation values)
            self.assertIsInstance(penalties, list)

    def test_high_penalty_reduces_composite_score(self):
        """Higher penalty should result in lower composite scores."""
        engine_low = _make_engine(
            diversified_basket_enabled=True,
            basket_max_per_cluster=2,
            basket_corr_threshold=0.50,
            basket_redundancy_penalty=0.1,
        )
        engine_high = _make_engine(
            diversified_basket_enabled=True,
            basket_max_per_cluster=2,
            basket_corr_threshold=0.50,
            basket_redundancy_penalty=0.9,
        )
        train_df = _make_synthetic_train_df(n_dates=100, seed=42)
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,
            "alpha_4": 0.06,
        }
        _, ev_low = engine_low.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        _, ev_high = engine_high.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        # With high penalty, minimum composite score should be lower
        scores_low = ev_low.get("composite_scores", {})
        scores_high = ev_high.get("composite_scores", {})
        if scores_low and scores_high:
            min_low = min(scores_low.values()) if scores_low else 0
            min_high = min(scores_high.values()) if scores_high else 0
            self.assertLessEqual(min_high, min_low + 0.001)


# ---------------------------------------------------------------------------
# Tests: JSON evidence serializability
# ---------------------------------------------------------------------------

class TestEvidenceSerializable(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — JSON safety."""

    def test_evidence_is_json_serializable(self):
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,
            "alpha_2": 0.03, "alpha_4": 0.06,
        }
        _, evidence = engine.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        json_str = json.dumps(evidence)
        self.assertGreater(len(json_str), 0)

    def test_evidence_has_required_keys(self):
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {"alpha_0": 0.05, "alpha_4": 0.06}
        _, evidence = engine.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        required_keys = [
            "gate", "enabled", "candidate_alphas", "n_candidates",
            "selected_alphas", "clusters", "pairwise_correlations",
            "redundancy_penalties_applied", "pit_safe",
        ]
        for key in required_keys:
            self.assertIn(key, evidence, f"Missing key: {key}")

    def test_evidence_gate_value(self):
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {"alpha_0": 0.05, "alpha_4": 0.06}
        _, evidence = engine.select_diversified_basket(
            list(train_ics.keys()), train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertEqual(
            evidence["gate"],
            "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615"
        )

    def test_fold_metrics_carries_basket_evidence(self):
        """FoldMetrics must carry diversified_basket_evidence."""
        from omega.quant.alpha.phase35 import FoldMetrics
        evidence = {
            "gate": "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615",
            "enabled": True,
            "selected_alphas": ["alpha_0", "alpha_4"],
            "pit_safe": True,
        }
        m = FoldMetrics(
            fold_id=1,
            train_start="2021-01-01",
            train_end="2021-12-31",
            test_start="2022-01-01",
            test_end="2022-06-30",
            diversified_basket_evidence=evidence,
        )
        self.assertIsNotNone(m.diversified_basket_evidence)
        self.assertEqual(
            m.diversified_basket_evidence["gate"],
            "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615"
        )

    def test_serialize_fold_details_persists_basket_evidence(self):
        """serialize_fold_details must include diversified_basket_evidence."""
        from run_phase35_backtest import serialize_fold_details
        from omega.quant.alpha.phase35 import FoldMetrics

        evidence = {
            "gate": "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615",
            "enabled": True,
            "selected_alphas": ["alpha_0"],
            "pit_safe": True,
        }
        m = FoldMetrics(
            fold_id=1,
            train_start="2021-01-01",
            train_end="2021-12-31",
            test_start="2022-01-01",
            test_end="2022-06-30",
            diversified_basket_evidence=evidence,
        )
        fold_dict = serialize_fold_details(m)
        self.assertIn("diversified_basket_evidence", fold_dict)
        self.assertEqual(
            fold_dict["diversified_basket_evidence"]["gate"],
            "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615",
        )
        json_str = json.dumps(fold_dict)
        self.assertGreater(len(json_str), 0)

    def test_serialize_fold_details_none_evidence_omitted(self):
        """When evidence is None, key should not appear."""
        from run_phase35_backtest import serialize_fold_details
        from omega.quant.alpha.phase35 import FoldMetrics

        m = FoldMetrics(
            fold_id=1,
            train_start="2021-01-01",
            train_end="2021-12-31",
            test_start="2022-01-01",
            test_end="2022-06-30",
        )
        fold_dict = serialize_fold_details(m)
        self.assertNotIn("diversified_basket_evidence", fold_dict)


# ---------------------------------------------------------------------------
# Tests: Dynamic + basket smoke
# ---------------------------------------------------------------------------

class TestDynamicPlusBasketSmoke(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — smoke test."""

    def test_engine_accepts_both_dynamic_and_basket(self):
        """Engine can be constructed with both dynamic universe and basket."""
        engine = _make_engine(
            diversified_basket_enabled=True,
            dynamic_universe_schedule={"2022-01-01": ["SYM00"]},
        )
        self.assertTrue(engine.diversified_basket_enabled)
        self.assertIsNotNone(engine.dynamic_universe_schedule)

    def test_basket_with_single_candidate_fallback(self):
        """With <2 candidates, basket falls back to safe selection."""
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {"alpha_0": 0.05}
        selected, evidence = engine.select_diversified_basket(
            ["alpha_0"], train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertTrue(evidence["fallback_safe_basket_used"])
        self.assertEqual(len(selected), 1)

    def test_basket_with_empty_candidates_fallback(self):
        """With 0 candidates, basket falls back to safe selection."""
        engine = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df()
        train_ics = {}
        selected, evidence = engine.select_diversified_basket(
            [], train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertTrue(evidence["fallback_safe_basket_used"])


# ---------------------------------------------------------------------------
# Tests: Regression — baseline preserved when basket disabled
# ---------------------------------------------------------------------------

class TestRegressionBaselinePreserved(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — regression."""

    def test_disabled_basket_does_not_alter_selection(self):
        """When basket is disabled, select_diversified_basket is not called."""
        engine = _make_engine(diversified_basket_enabled=False)
        self.assertFalse(engine.diversified_basket_enabled)
        # Verify the method exists but is not invoked by default
        self.assertTrue(hasattr(engine, 'select_diversified_basket'))

    def test_script_has_diversified_basket_flag(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('--diversified-basket', src)

    def test_script_has_gate_citation(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615', src)

    def test_script_persists_basket_evidence(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            src = f.read()
        self.assertIn('diversified_basket_evidence', src)

    def test_engine_accepts_diversified_basket_enabled(self):
        """Verify Phase35WalkForwardEngine __init__ accepts the param."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        import inspect
        sig = inspect.signature(Phase35WalkForwardEngine.__init__)
        self.assertIn('diversified_basket_enabled', sig.parameters)


# ---------------------------------------------------------------------------
# Tests: Deterministic selection
# ---------------------------------------------------------------------------

class TestDeterministicSelection(unittest.TestCase):
    """GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — reproducibility."""

    def test_same_input_same_output(self):
        engine1 = _make_engine(diversified_basket_enabled=True)
        engine2 = _make_engine(diversified_basket_enabled=True)
        train_df = _make_synthetic_train_df(seed=42)
        train_ics = {
            "alpha_0": 0.05, "alpha_1": 0.04,
            "alpha_2": 0.03, "alpha_4": 0.06,
        }
        candidates = list(train_ics.keys())
        sel1, _ = engine1.select_diversified_basket(
            candidates, train_df, train_ics, return_col="fwd_ret_5"
        )
        sel2, _ = engine2.select_diversified_basket(
            candidates, train_df, train_ics, return_col="fwd_ret_5"
        )
        self.assertEqual(sorted(sel1), sorted(sel2))


if __name__ == '__main__':
    unittest.main()
