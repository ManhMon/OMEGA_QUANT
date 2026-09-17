from __future__ import annotations

import warnings

import pandas as pd
import pytest

from omega.quant.evolution.alpha_to_execution_bridge import (
    CANONICAL_METRIC_KEY,
    resolve_metric_cli,
    resolve_metric_config,
)
from omega.quant.evolution.continuous_learning import ContinuousLearningEngine
from scripts.run_weekly_evolution import evaluate_and_promote, parse_args


def test_metric_reader_prefers_signal_pnl_score():
    metric, warning_messages = resolve_metric_config({CANONICAL_METRIC_KEY: "alpha", "sharpe": "beta"})
    assert metric == "alpha"
    assert warning_messages


def test_metric_reader_maps_legacy_sharpe():
    metric, warning_messages = resolve_metric_config({"sharpe": "alpha"})
    assert metric == "alpha"
    assert warning_messages == []


def test_metric_reader_warns_on_conflicting_dual_keys():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        metric, _ = resolve_metric_config({CANONICAL_METRIC_KEY: "alpha", "sharpe": "beta"})
    assert metric == "alpha"
    assert any("overrides" in str(item.message) for item in caught)


def test_cli_alias_conflict_resolution_raises_value_error():
    with pytest.raises(ValueError):
        resolve_metric_cli(signal_pnl_score="alpha", sharpe="beta")


def test_cli_alias_equivalent_values_do_not_raise():
    assert resolve_metric_cli(signal_pnl_score="alpha", sharpe="alpha") == "alpha"


def test_continuous_learning_reads_canonical_metric():
    engine = ContinuousLearningEngine()
    should_promote, _ = engine.champion_vs_challenger(
        {CANONICAL_METRIC_KEY: 1.0, "sharpe": 0.1, "ic": 0.1},
        {CANONICAL_METRIC_KEY: 1.1, "sharpe": 0.1, "ic": 0.2},
    )
    assert should_promote is True


class _DummyTree:
    def to_string(self) -> str:
        return "alpha"


class _DummyIndividual:
    def __init__(self, value: float):
        self.tree = _DummyTree()
        self.fitness = value
        self._value = value

    def _execute_tree(self, tree, features):
        target = features["target_h5"]
        return target * self._value


def test_weekly_evolution_promotes_using_canonical_metric_key():
    test_df = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
            "target": [1.0, 2.0, 1.0, 2.0],
            "target_h3": [1.0, 2.0, 1.0, 2.0],
            "target_h5": [1.0, 2.0, 1.0, 2.0],
            "target_h10": [1.0, 2.0, 1.0, 2.0],
            "ticker": ["AAA", "AAA", "AAA", "AAA"],
        }
    )
    promoted = evaluate_and_promote([_DummyIndividual(1.0)], test_df, pd.Timestamp("2026-06-20"))
    assert len(promoted) == 1
    assert promoted[0][CANONICAL_METRIC_KEY] > 0.08
    assert promoted[0]["sharpe"] == promoted[0][CANONICAL_METRIC_KEY]


def test_run_weekly_evolution_flips_negative_ic_alpha_before_promotion():
    test_df = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
            "target": [1.0, 2.0, 1.0, 2.0],
            "target_h3": [1.0, 2.0, 1.0, 2.0],
            "target_h5": [1.0, 2.0, 1.0, 2.0],
            "target_h10": [1.0, 2.0, 1.0, 2.0],
            "ticker": ["AAA", "AAA", "AAA", "AAA"],
        }
    )

    promoted = evaluate_and_promote([_DummyIndividual(-1.0)], test_df, pd.Timestamp("2026-06-20"))

    assert len(promoted) == 1
    assert promoted[0]["formula"] == "neg(alpha)"
    assert promoted[0]["ic"] > 0.0
    assert promoted[0][CANONICAL_METRIC_KEY] > 0.08
    assert promoted[0]["sharpe"] == promoted[0][CANONICAL_METRIC_KEY]


def test_weekly_evolution_threshold_cli_resolution_and_promotion_thresholds():
    with pytest.raises(ValueError):
        parse_args(["--min-oos-signal-pnl-score", "0.08", "--min-oos-sharpe", "0.09"])

    with pytest.raises(ValueError):
        parse_args(["--min-oos-signal-pnl-score=0.08", "--min-oos-sharpe=0.09"])

    matching_args = parse_args(["--min-oos-signal-pnl-score", "0.08", "--min-oos-sharpe", "0.08", "--min-oos-ic", "0.02"])
    assert matching_args.min_oos_score == pytest.approx(0.08)
    assert matching_args.min_oos_ic == pytest.approx(0.02)

    single_alias_args = parse_args(["--min-oos-sharpe", "0.11"])
    assert single_alias_args.min_oos_score == pytest.approx(0.11)

    test_df = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
            "target": [1.0, 2.0, 1.0, 2.0],
            "target_h3": [1.0, 2.0, 1.0, 2.0],
            "target_h5": [1.0, 2.0, 1.0, 2.0],
            "target_h10": [1.0, 2.0, 1.0, 2.0],
            "ticker": ["AAA", "AAA", "AAA", "AAA"],
        }
    )

    blocked = evaluate_and_promote(
        [_DummyIndividual(1.0)],
        test_df,
        pd.Timestamp("2026-06-20"),
        min_oos_ic=0.02,
        min_oos_score=2.1,
    )
    assert blocked == []

    promoted = evaluate_and_promote(
        [_DummyIndividual(1.0)],
        test_df,
        pd.Timestamp("2026-06-20"),
        min_oos_ic=matching_args.min_oos_ic,
        min_oos_score=matching_args.min_oos_score,
    )
    assert len(promoted) == 1
    assert promoted[0][CANONICAL_METRIC_KEY] > matching_args.min_oos_score
