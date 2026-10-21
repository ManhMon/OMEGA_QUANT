"""Adversarial contracts for P6 evaluation, costs, and W7 shadow integration."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
import math
from pathlib import Path
import sqlite3
from unittest.mock import patch

import numpy as np
import omega.pipeline.shadow_pipeline as shadow_pipeline_module
import pandas as pd
import pytest

from omega.data.calendar import ICT, VNTradingCalendar
from omega.pipeline.shadow_pipeline import GATE, ROOT, ShadowPipeline
from omega.quant.strategy.unified_alpha_evaluator import (
    annotate_execution_costs,
    blend_features,
    evaluate_walk_forward,
)

STREAMS = ("direct_news", "spillover", "pead")
ZERO_WEIGHTS = dict.fromkeys(STREAMS, 0.0)
BLEND_WEIGHTS = {"direct_news": 0.04, "spillover": 0.03, "pead": 0.02}


def _blend_inputs(symbols=("AAA", "BBB", "CCC"), *, available="2026-09-29T15:30:00+07:00"):
    index = pd.Index(symbols, name="symbol")
    quant = pd.Series(np.linspace(-0.8, 0.8, len(index)), index=index, dtype=float)
    features = pd.DataFrame(
        {
            "direct_news": np.linspace(0.7, -0.3, len(index)),
            "spillover": [None] * len(index),
            "pead": np.linspace(-0.2, 0.5, len(index)),
            "feature_as_of": ["2026-09-29T15:00:00+07:00"] * len(index),
            "feature_available_at": [available] * len(index),
            "lineage": ["fixture-v1"] * len(index),
        },
        index=index,
    )
    return quant, features


def _sessions(count=36):
    current = date(2026, 7, 6)
    dates = []
    while len(dates) < count:
        if VNTradingCalendar.is_trading_day(datetime.combine(current, time(12), ICT)):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _stamp(day, hour=10, minute=0):
    return datetime.combine(day, time(hour, minute), ICT)


def _panel(*, last_decision=33, seed=90210):
    dates = _sessions()
    rng = np.random.default_rng(seed)
    rows = []
    symbols = ("AAA", "BBB", "CCC")
    ranks = np.array([-1.0, 0.0, 1.0])
    for session in range(last_decision + 1):
        # The session-4 group deliberately crosses into the first validation window.
        group = "E8" if session == 4 else f"E{session}"
        for rank, symbol in zip(ranks, symbols):
            end_session = session + 2
            rows.append(
                {
                    "symbol": symbol,
                    "session": session,
                    "decision_time": _stamp(dates[session]),
                    "execution_time": _stamp(dates[session + 1]),
                    "label_end_time": _stamp(dates[end_session], 14, 0),
                    "label_available_at": _stamp(dates[end_session], 15, 30),
                    "event_group": group,
                    "quant": rank * 0.8,
                    "direct_news": rank * 0.5,
                    "spillover": None,
                    "pead": rank * -0.2,
                    "feature_as_of": _stamp(dates[session - 1] if session else dates[0] - timedelta(days=1), 14, 0),
                    "feature_available_at": _stamp(dates[session - 1] if session else dates[0] - timedelta(days=1), 15, 30),
                    "lineage": "synthetic-v1",
                    "ret3": float(rank + rng.normal(0, 0.12)),
                    "ret5": float(-rank + rng.normal(0, 0.12)),
                }
            )
    return pd.DataFrame(rows)


def _trial(trial_id, ablation, score_col, return_col="ret3", weights=None):
    return {
        "trial_id": trial_id,
        "ablation": ablation,
        "score_col": score_col,
        "return_col": return_col,
        "label_horizon_sessions": 3,
        "validation_windows": [[8, 16], [16, 24]],
        "final_holdout": [24, 32],
        "weights": dict(ZERO_WEIGHTS if weights is None else weights),
    }


def _registry(*, trials=None):
    dates = _sessions()
    return {
        "schema_version": "p6/trials-v1",
        "session_calendar": [_stamp(day, 12).isoformat() for day in dates],
        "evaluation_time": _stamp(dates[-1], 16).isoformat(),
        "embargo_sessions": 3,
        "final_holdout": [24, 32],
        "trials": trials or [
            _trial("quant", "quant_only", "quant_score"),
            _trial("combined", "combined", "combined_score", weights=BLEND_WEIGHTS),
        ],
    }


def _evaluate(panel=None, registry=None):
    return evaluate_walk_forward(panel if panel is not None else _panel(), trial_registry=registry or _registry())


def _p6_advisory(request, *, macro=0.8, value=0.0):
    prior = "2026-09-29T14:00:00+07:00"
    available = "2026-09-29T15:30:00+07:00"
    return {
        "schema_version": "p6/v1",
        "features": [
            {
                "symbol": symbol,
                "direct_news": value,
                "spillover": None,
                "pead": None,
                "feature_as_of": prior,
                "feature_available_at": available,
                "lineage": "shadow-fixture-v1",
            }
            for symbol in request["universe"]
        ],
        "weights": dict(ZERO_WEIGHTS),
        "macro_multiplier": macro,
    }


def _w7_request():
    cutoff = "2026-09-30T10:00:00+07:00"
    observed = "2026-09-29T10:00:00+07:00"
    symbols = ["VCB", "VNM", "FPT"]
    return {
        "schema_version": "w7/v1",
        "gate_id": GATE,
        "run_id": "P6TEST",
        "decision_id": "D0",
        "arm": "B3",
        "cutoff": cutoff,
        "source_revision": "02bb5a7b41a5bbf4e9ff9cc1e3f61dea667044d7",
        "policy_version": "w7-v1",
        "calendar_digest": __import__("hashlib").sha256((ROOT / "config/vn_holidays.json").read_bytes()).hexdigest(),
        "universe": symbols,
        "initial_cash_vnd": 100_000_000,
        "risk_halt": False,
        "actions": [],
        "advisory": None,
        "signal": {
            "as_of": observed,
            "available_at": cutoff,
            "values": [0.03, 0.02, 0.01],
            "covariance": [[0.04, 0.0, 0.0], [0.0, 0.09, 0.0], [0.0, 0.0, 0.16]],
        },
        "market": [
            {
                "symbol": symbol,
                "exchange": "HOSE",
                "sector": f"S{i}",
                "status": "active",
                "as_of": cutoff,
                "available_at": cutoff,
                "open": 25000,
                "high": 26000,
                "low": 24000,
                "close": 25000,
                "volume": 1_000_000,
                "reference_price": 25000,
                "bid": 24950,
                "ask": 25050,
                "bid_quantity": 100000,
                "ask_quantity": 100000,
            }
            for i, symbol in enumerate(symbols)
        ],
    }


def _pipeline(tmp_path, mode="shadow", name="state.db"):
    state = tmp_path / name
    return ShadowPipeline(state.relative_to(ROOT).as_posix(), mode)


def test_blend_public_contract_missing_stream_masks_macro_and_immutable_inputs():
    quant, features = _blend_inputs(available="2026-09-30T15:30:00+07:00")
    # Decision at the inclusive statutory 15:30 availability boundary.
    decision = "2026-09-30T15:30:00+07:00"
    quant_before, features_before = quant.copy(deep=True), features.copy(deep=True)
    blended = blend_features(
        quant,
        features,
        weights=BLEND_WEIGHTS,
        decision_time=decision,
        macro_multiplier=0.5,
    )
    expected_raw = 0.91 * quant + 0.04 * features.direct_news + 0.02 * features.pead
    pd.testing.assert_series_equal(blended.score_before_macro, expected_raw, check_names=False)
    pd.testing.assert_series_equal(blended.score, expected_raw * 0.5, check_names=False)
    assert blended.spillover_valid.tolist() == [False] * len(quant)
    assert blended.quant.equals(quant)
    pd.testing.assert_series_equal(quant, quant_before)
    pd.testing.assert_frame_equal(features, features_before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("quant", True), ("quant", "0.2"), ("quant", float("inf")),
        ("direct_news", True), ("direct_news", "0.2"),
        ("spillover", float("inf")), ("pead", -1.01), ("quant", 1.01),
    ],
    ids=["bool-quant", "string-quant", "inf-quant", "bool-feature", "string-feature", "inf-feature", "low-feature", "high-quant"],
)
def test_blend_rejects_invalid_numeric_values(field, value):
    quant, features = _blend_inputs()
    if field == "quant":
        quant = quant.astype(object)
        quant.iloc[0] = value
    else:
        features[field] = features[field].astype(object)
        features.iloc[0, features.columns.get_loc(field)] = value
    with pytest.raises(ValueError):
        blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00")


@pytest.mark.parametrize(
    "weights",
    [None, {}, {"direct_news": 0.1}, {**ZERO_WEIGHTS, "other": 0.0},
     {"direct_news": True, "spillover": 0.0, "pead": 0.0},
     {"direct_news": -0.01, "spillover": 0.0, "pead": 0.0},
     {"direct_news": 0.101, "spillover": 0.0, "pead": 0.0},
     {"direct_news": 0.04, "spillover": 0.04, "pead": 0.04}],
    ids=["none", "missing", "partial", "extra", "bool", "negative", "single-too-large", "sum-too-large"],
)
def test_blend_rejects_invalid_weight_contract(weights):
    quant, features = _blend_inputs()
    with pytest.raises(ValueError):
        blend_features(quant, features, weights=weights, decision_time="2026-09-30T10:00:00+07:00")


@pytest.mark.parametrize("field", ["decision_time", "feature_as_of", "feature_available_at"])
def test_blend_rejects_naive_timestamps(field):
    quant, features = _blend_inputs()
    if field == "decision_time":
        decision = "2026-09-30T10:00:00"
    else:
        features[field] = "2026-09-30T09:00:00"
        decision = "2026-09-30T10:00:00+07:00"
    with pytest.raises(ValueError):
        blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time=decision)


def test_blend_rejects_index_schema_and_veto_errors():
    quant, features = _blend_inputs()
    with pytest.raises(TypeError):
        blend_features(list(quant), features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00")
    with pytest.raises(ValueError):
        blend_features(quant, features.iloc[::-1], weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00")
    with pytest.raises(ValueError):
        blend_features(quant, features.drop(columns="lineage"), weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00")
    with pytest.raises(ValueError):
        blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00", hard_veto=1)
    vetoed = blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00", macro_multiplier=0.0, hard_veto=True)
    assert vetoed.score.eq(0.0).all()
    assert vetoed.score_before_macro.eq(0.0).all()


def test_blend_null_quant_stays_null_and_macro_is_last():
    quant, features = _blend_inputs()
    quant.iloc[0] = np.nan
    out = blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00", macro_multiplier=0.25)
    assert math.isnan(out.loc["AAA", "score"])
    assert math.isnan(out.loc["AAA", "score_before_macro"])
    assert out.loc["BBB", "score"] == pytest.approx(out.loc["BBB", "score_before_macro"] * 0.25)
    for bad in (True, -0.01, 1.01, float("nan"), float("inf"), "0.5"):
        with pytest.raises(ValueError):
            blend_features(quant, features, weights=BLEND_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00", macro_multiplier=bad)


@pytest.mark.parametrize("value", [True, "0.2", float("inf"), -1.01, 1.01])
def test_quant_only_rejects_malformed_quant_values(value):
    panel = _panel()
    panel.loc[0, "quant"] = value
    with pytest.raises(ValueError):
        _evaluate(panel)


def test_annotate_execution_costs_round_trip_and_no_input_mutation():
    fills = pd.DataFrame(
        [
            {"fill_id": "buy-1", "side": "BUY", "quantity": 100, "price_vnd": 1000, "nav_vnd": 10_000_000},
            {"fill_id": "sell-1", "side": "SELL", "quantity": 100, "price_vnd": 1000, "nav_vnd": 10_000_000},
        ]
    )
    original = fills.copy(deep=True)
    costs = annotate_execution_costs(fills)
    assert costs.notional_vnd.tolist() == [100_000, 100_000]
    assert costs.cost_bps.tolist() == [17, 27]
    assert costs.cost_vnd.tolist() == [170, 270]
    assert sum(costs.cost_vnd) == 440  # 44 bps over a completed round trip, not per leg.
    assert costs.net_cash_vnd.tolist() == [-100_170, 99_730]
    assert costs.one_way_turnover.tolist() == pytest.approx([0.005, 0.005])
    pd.testing.assert_frame_equal(fills, original)
    assert "cost_vnd" not in fills


def test_annotate_execution_costs_accepts_large_vnd_and_exact_field_limits():
    fills = pd.DataFrame([{"fill_id": "large", "side": "BUY", "quantity": 1_000_000_000_000, "price_vnd": 1_000_000_000, "nav_vnd": 1_000_000_000_000_000_000}])
    result = annotate_execution_costs(fills)
    assert result.loc[0, "notional_vnd"] == 10**21
    assert result.loc[0, "cost_vnd"] == 17 * 10**21 // 10_000
    assert math.isfinite(result.loc[0, "one_way_turnover"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("fill_id", "bad id"), ("side", "HOLD"), ("quantity", True), ("quantity", 0),
        ("quantity", 10**12 + 1), ("price_vnd", False), ("price_vnd", 0),
        ("price_vnd", 10**9 + 1), ("nav_vnd", True), ("nav_vnd", 0),
        ("nav_vnd", 10**18 + 1),
    ],
    ids=["bad-id", "side", "bool-qty", "zero-qty", "qty-bound", "bool-price", "zero-price", "price-bound", "bool-nav", "zero-nav", "nav-bound"],
)
def test_annotate_execution_costs_rejects_invalid_rows(field, value):
    row = {"fill_id": "fill-1", "side": "BUY", "quantity": 1, "price_vnd": 1000, "nav_vnd": 10_000}
    row[field] = value
    with pytest.raises(ValueError):
        annotate_execution_costs(pd.DataFrame([row]))


def test_annotate_execution_costs_rejects_duplicate_ids_schema_and_scenario():
    row = {"fill_id": "fill-1", "side": "BUY", "quantity": 1, "price_vnd": 1000, "nav_vnd": 10_000}
    with pytest.raises(ValueError, match="unique"):
        annotate_execution_costs(pd.DataFrame([row, row]))
    with pytest.raises(ValueError, match="columns"):
        annotate_execution_costs(pd.DataFrame([{**row, "unexpected": 1}]))
    with pytest.raises(ValueError, match="scenario"):
        annotate_execution_costs(pd.DataFrame([row]), cost_scenario="other")
    with pytest.raises(ValueError):
        annotate_execution_costs([])


def test_walk_forward_registry_binding_metrics_and_immutable_inputs():
    panel, registry = _panel(), _registry()
    panel_before, registry_before = panel.copy(deep=True), deepcopy(registry)
    result = evaluate_walk_forward(panel, trial_registry=registry)
    again = evaluate_walk_forward(panel, trial_registry=registry)
    pd.testing.assert_frame_equal(panel, panel_before)
    assert registry == registry_before
    assert result == again
    assert result["trial_registry_provenance"] == "caller_supplied_unverified"
    assert result["trial_registry_digest"] == again["trial_registry_digest"]
    assert result["final_holdout"] == [24, 32]
    assert result["ablations"]["quant"]["final_holdout"]["attempted_trial_count"] == 2
    assert result["ablations"]["quant"]["final_holdout"]["n_rows"] == 18
    assert result["ablations"]["quant"]["validation"][0]["n_train_candidates"] == 24
    # Train labels ending at/after fold start are purged; embargo retains sessions 0-4, then E4 is grouped with E8.
    assert result["ablations"]["quant"]["validation"][0]["n_train_after_interval_purge_group_purge_embargo_and_availability"] == 12
    metric = result["ablations"]["quant"]["validation"][0]["oos_gross"]
    assert metric["familywise_test_count"] == 6
    assert metric["block_bootstrap_replicates"] == 512
    assert metric["sessions_with_rank_ic"] == 6
    assert result["net_oos_performance"] is None


def test_walk_forward_excludes_labels_crossing_window_or_holdout_end():
    result = _evaluate()
    trial = result["ablations"]["quant"]
    assert trial["validation"][0]["oos_gross"]["label_rows_available"] == 18
    assert trial["validation"][1]["oos_gross"]["label_rows_available"] == 18
    assert trial["final_holdout"]["n_rows"] == 18
    # A decision inside a window with its realized endpoint on/after end is not scored.
    panel = _panel()
    row = (panel.session == 13) & (panel.symbol == "AAA")
    panel.loc[row, "label_end_time"] = _stamp(_sessions()[16], 14)
    panel.loc[row, "label_available_at"] = _stamp(_sessions()[16], 15, 30)
    result = _evaluate(panel)
    assert result["ablations"]["quant"]["validation"][0]["oos_gross"]["label_rows_available"] == 17


def test_walk_forward_only_scores_matured_labels():
    panel = _panel()
    late = _stamp(_sessions()[35], 16) + timedelta(days=1)
    panel.loc[(panel.session == 9) & (panel.symbol == "AAA"), "label_available_at"] = late
    result = _evaluate(panel)
    metrics = result["ablations"]["quant"]["validation"][0]["oos_gross"]
    assert metrics["label_rows_available"] == 17
    assert metrics["label_row_coverage"] < 1


def test_walk_forward_fixed_windows_ignore_future_panel_insertion():
    registry = _registry()
    truncated = _panel(last_decision=23)
    full = _panel(last_decision=33)
    first = evaluate_walk_forward(truncated, trial_registry=registry)
    extended = evaluate_walk_forward(full, trial_registry=registry)
    assert [w["session_window"] for w in first["ablations"]["quant"]["validation"]] == [[8, 16], [16, 24]]
    assert first["ablations"]["quant"]["validation"] == extended["ablations"]["quant"]["validation"]
    assert first["trial_registry_digest"] == extended["trial_registry_digest"]


def test_walk_forward_missing_ic_sessions_disable_uncertainty():
    panel = _panel()
    panel = panel.loc[panel.session != 10].reset_index(drop=True)
    metrics = _evaluate(panel)["ablations"]["quant"]["validation"][0]["oos_gross"]
    assert metrics["block_bootstrap_status"] == "unavailable_nonconsecutive_sessions"
    assert metrics["block_bootstrap_95_ci"] is None
    assert metrics["block_bootstrap_replicates"] == 0
    assert metrics["hac_standard_error"] is None


def test_walk_forward_is_deterministic_on_seeded_synthetic_panels():
    first = _evaluate(_panel(seed=7))
    assert first == _evaluate(_panel(seed=7))
    assert first == _evaluate(_panel(seed=8))  # Noise preserves the cross-sectional ranks.


@pytest.mark.parametrize("bad", [True, -1, 0, 3.0, "3"], ids=["bool", "negative", "zero", "float", "string"])
def test_walk_forward_rejects_invalid_embargo(bad):
    registry = _registry()
    registry["embargo_sessions"] = bad
    with pytest.raises(ValueError):
        _evaluate(registry=registry)


def test_walk_forward_rejects_duplicate_score_columns_and_unbound_registry():
    trials = [_trial("q", "quant_only", "same"), _trial("mix", "combined", "same", weights=BLEND_WEIGHTS)]
    with pytest.raises(ValueError):
        _evaluate(registry=_registry(trials=trials))
    registry = _registry()
    registry["unregistered"] = 1
    with pytest.raises(ValueError):
        _evaluate(registry=registry)
    with pytest.raises(TypeError):
        evaluate_walk_forward([], trial_registry=_registry())


def test_walk_forward_rejects_bad_calendar_or_fold_binding():
    bad_calendar = _registry()
    bad_calendar["session_calendar"][4] = bad_calendar["session_calendar"][3]
    with pytest.raises(ValueError):
        _evaluate(registry=bad_calendar)
    bad_holdout = _registry()
    bad_holdout["trials"][0]["final_holdout"] = [23, 32]
    with pytest.raises(ValueError):
        _evaluate(registry=bad_holdout)
    bad_windows = _registry()
    bad_windows["trials"][0]["validation_windows"] = [[9, 16], [16, 24]]
    with pytest.raises(ValueError):
        _evaluate(registry=bad_windows)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.__setitem__("execution_time", _stamp(_sessions()[1], 15, 30)),
        lambda p: p.__setitem__("execution_time", _stamp(_sessions()[1], 11, 31)),
        lambda p: p.__setitem__("execution_time", datetime.fromisoformat("2026-09-02T10:00:00+07:00")),
        lambda p: p.__setitem__("label_end_time", _stamp(_sessions()[2], 15, 30)),
        lambda p: p.__setitem__("label_end_time", _stamp(_sessions()[2], 12, 0)),
        lambda p: p.__setitem__("label_available_at", _stamp(_sessions()[2], 13, 59)),
    ],
    ids=["execution-1530-invalid", "execution-lunch-invalid", "execution-holiday-invalid", "endpoint-1530-invalid", "endpoint-lunch-invalid", "label-before-endpoint"],
)
def test_walk_forward_rejects_invalid_session_clock_and_label_order(mutate):
    panel = _panel()
    row = panel.index[0]
    values = panel.loc[row].to_dict()
    mutate(values)
    for field, value in values.items():
        panel.at[row, field] = value
    with pytest.raises(ValueError):
        _evaluate(panel)


def test_walk_forward_accepts_inclusive_active_session_and_1530_label_availability():
    panel = _panel()
    panel.loc[0, "execution_time"] = _stamp(_sessions()[1], 14, 45)
    panel.loc[0, "label_end_time"] = _stamp(_sessions()[2], 14, 45)
    panel.loc[0, "label_available_at"] = _stamp(_sessions()[2], 15, 30)
    assert _evaluate(panel)["schema_version"] == "p6/evaluation-v1"


def test_walk_forward_rejects_actual_label_horizon_overrun_and_duplicate_rows():
    panel = _panel()
    panel.loc[0, "label_end_time"] = _stamp(_sessions()[4], 14)
    panel.loc[0, "label_available_at"] = _stamp(_sessions()[4], 15, 30)
    with pytest.raises(ValueError, match="horizon"):
        _evaluate(panel)
    duplicated = pd.concat([_panel(), _panel().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        _evaluate(duplicated)


def test_walk_forward_rejects_malformed_schema_timestamps_and_unregistered_score():
    panel = _panel()
    panel["decision_time"] = panel["decision_time"].astype(object)
    panel.loc[0, "decision_time"] = "2026-07-06T10:00:00"
    with pytest.raises(ValueError):
        _evaluate(panel)
    panel = _panel()
    panel["quant_score"] = 0.0
    with pytest.raises(ValueError, match="computed"):
        _evaluate(panel)
    panel = _panel().drop(columns="event_group")
    with pytest.raises(ValueError, match="missing"):
        _evaluate(panel)


def test_walk_forward_familywise_includes_every_trial_window_and_holdout():
    trials = [
        _trial("q", "quant_only", "q_score", "ret3"),
        _trial("mix", "combined", "mix_score", "ret5", BLEND_WEIGHTS),
        _trial("direct", "direct_only", "direct_score", "ret3", {"direct_news": 0.05, "spillover": 0.0, "pead": 0.0}),
    ]
    result = _evaluate(registry=_registry(trials=trials))
    for trial in result["ablations"].values():
        assert trial["validation"][0]["oos_gross"]["familywise_test_count"] == 9
        assert trial["final_holdout"]["oos_gross"]["familywise_test_count"] == 9


@pytest.mark.parametrize("bad", [None, [], {}, "bad", True])
def test_evaluator_rejects_non_dataframe_inputs(bad):
    with pytest.raises((TypeError, ValueError)):
        blend_features(bad, pd.DataFrame(), weights=ZERO_WEIGHTS, decision_time="2026-09-30T10:00:00+07:00")


def test_p6_shadow_positive_replay_cost_overlay_and_baseline_immutability(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("P6 must use supplied features without network or classification calls")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(ShadowPipeline, "_classification", forbidden)
    request = _w7_request()
    request["advisory"] = _p6_advisory(request, macro=0.8)
    original = deepcopy(request)
    pipeline = _pipeline(tmp_path)
    first = pipeline.run(request)
    assert first["outcome"] == "proposal"
    assert first["applied"] is False and first["live_lambda"] == 0
    assert first["annotations"]["p6"]["provenance"] == "caller_supplied_unverified"
    assert first["annotations"]["p6"]["historical_eligible"] is False
    assert first["annotations"]["p6"]["deployment_evidence"] is False
    assert first["annotations"]["p6"]["macro_multiplier"] == 0.8
    costs = first["annotations"]["p6"]["execution_costs"]
    assert costs["scenario"] == "p6_17_27_bps"
    assert costs["booked_in_w7_cash"] is False
    assert costs["units"] == "VND_FULL"
    assert len(costs["fills"]) == len(first["fills"])
    assert all("cost_vnd" in fill for fill in costs["fills"])
    assert first["ledger"]["cash"] <= request["initial_cash_vnd"]
    assert first["nav_residual_vnd"] == 0  # Comparison costs do not enter W7 cash reconciliation.
    assert request == original
    replay = pipeline.run(request)
    assert replay["outcome"] == "replay"
    assert replay["decision_digest"] == first["decision_digest"]
    assert len(replay["fills"]) == len(first["fills"])


def _assert_baseline_economics(actual, baseline):
    for key in ("weights", "orders", "fills", "nav_vnd"):
        assert actual[key] == baseline[key]
    for key in ("cash", "positions", "receivables", "peak"):
        assert actual["ledger"][key] == baseline["ledger"][key]


def _baseline_run(tmp_path, request, name="baseline.db"):
    baseline_request = deepcopy(request)
    baseline_request["advisory"] = None
    return _pipeline(tmp_path, mode="disabled", name=name).run(baseline_request)


@pytest.mark.parametrize(
    "case",
    [
        "extra-advisory-key", "missing-advisory-key", "extra-feature-key", "missing-feature-key",
        "missing-row", "extra-row", "duplicate-symbol", "out-of-order",
        "same-ict-date", "future-ict-date", "available-before-asof", "available-after-cutoff",
        "extra-weight", "missing-weight", "weight-over-limit", "aggregate-weight-over-limit",
        "macro-below-zero", "macro-above-one", "macro-bool",
    ],
)
def test_p6_adversarial_advisory_contract_falls_back_to_baseline(tmp_path, case):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    advisory = request["advisory"]
    if case == "extra-advisory-key":
        advisory["unexpected"] = 1
    elif case == "missing-advisory-key":
        del advisory["weights"]
    elif case == "extra-feature-key":
        advisory["features"][0]["unexpected"] = 1
    elif case == "missing-feature-key":
        del advisory["features"][0]["lineage"]
    elif case == "missing-row":
        advisory["features"].pop()
    elif case == "extra-row":
        advisory["features"].append(deepcopy(advisory["features"][-1]))
    elif case == "duplicate-symbol":
        advisory["features"][1] = deepcopy(advisory["features"][0])
    elif case == "out-of-order":
        advisory["features"].reverse()
    elif case == "same-ict-date":
        advisory["features"][0]["feature_as_of"] = "2026-09-29T17:30:00+00:00"
    elif case == "future-ict-date":
        advisory["features"][0]["feature_as_of"] = "2026-10-01T09:00:00+07:00"
    elif case == "available-before-asof":
        advisory["features"][0]["feature_available_at"] = "2026-09-29T13:00:00+07:00"
    elif case == "available-after-cutoff":
        advisory["features"][0]["feature_available_at"] = "2026-09-30T10:00:01+07:00"
    elif case == "extra-weight":
        advisory["weights"]["other"] = 0.0
    elif case == "missing-weight":
        del advisory["weights"]["pead"]
    elif case == "weight-over-limit":
        advisory["weights"]["direct_news"] = 0.1001
    elif case == "aggregate-weight-over-limit":
        advisory["weights"] = {"direct_news": 0.04, "spillover": 0.04, "pead": 0.04}
    elif case == "macro-below-zero":
        advisory["macro_multiplier"] = -0.01
    elif case == "macro-above-one":
        advisory["macro_multiplier"] = 1.01
    else:
        advisory["macro_multiplier"] = True

    baseline = _baseline_run(tmp_path, request)
    result = _pipeline(tmp_path, name="adversarial.db").run(request)
    assert result["outcome"] == "fallback"
    assert result["annotations"] == {}
    assert result["baseline_digest"] == baseline["baseline_digest"]
    _assert_baseline_economics(result, baseline)


def test_p6_zero_weights_preserve_baseline_without_second_optimizer(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request, macro=1.0)
    baseline = _baseline_run(tmp_path, request)
    original = shadow_pipeline_module.PortfolioOptimizer.optimize_weights
    calls = []

    def counted(optimizer, *args, **kwargs):
        calls.append(args[0].copy(deep=True))
        return original(optimizer, *args, **kwargs)

    with patch.object(shadow_pipeline_module.PortfolioOptimizer, "optimize_weights", counted):
        result = _pipeline(tmp_path, name="zero-weights.db").run(request)

    assert result["outcome"] == "proposal"
    assert len(calls) == 1  # Baseline optimizer only; zero influence skips P6 re-optimization.
    _assert_baseline_economics(result, baseline)


@pytest.mark.parametrize("macro", [0.0, 0.37], ids=["zero", "partial"])
def test_p6_blend_optimizes_unscaled_score_then_scales_after_optimizer(tmp_path, macro):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request, macro=macro, value=0.6)
    request["advisory"]["weights"] = dict(BLEND_WEIGHTS)
    baseline = _baseline_run(tmp_path, request)
    original = shadow_pipeline_module.PortfolioOptimizer.optimize_weights
    calls = []

    def observed(optimizer, *args, **kwargs):
        candidate = original(optimizer, *args, **kwargs)
        calls.append((args[0].copy(deep=True), candidate.copy(deep=True)))
        return candidate

    with patch.object(shadow_pipeline_module.PortfolioOptimizer, "optimize_weights", observed):
        result = _pipeline(tmp_path, name=f"blend-{macro}.db").run(request)

    assert result["outcome"] == "proposal"
    assert len(calls) == 2
    features = pd.DataFrame(
        request["advisory"]["features"],
        columns=["symbol", *STREAMS, "feature_as_of", "feature_available_at", "lineage"],
    ).set_index("symbol")
    quant = pd.Series(request["signal"]["values"], index=request["universe"], dtype=float)
    expected_blend = blend_features(
        quant, features, weights=BLEND_WEIGHTS, decision_time=request["cutoff"], macro_multiplier=macro,
    )
    pd.testing.assert_series_equal(calls[1][0], expected_blend["score_before_macro"], check_names=False)
    influence = math.fsum(BLEND_WEIGHTS.values())
    expected = [
        (base + influence * (float(candidate) - base)) * macro
        for base, candidate in zip(baseline["weights"], calls[1][1].tolist())
    ]
    assert result["weights"] == pytest.approx(expected)
    assert math.fsum(
        abs(base + influence * (float(candidate) - base) - base)
        for base, candidate in zip(baseline["weights"], calls[1][1].tolist())
    ) <= 0.1 + 1e-9


def test_p6_cutoff_equal_availability_and_all_missing_streams_remain_optional(tmp_path):
    request = _w7_request()
    request["cutoff"] = "2026-09-30T15:30:00+07:00"
    request["signal"]["available_at"] = request["cutoff"]
    for row in request["market"]:
        row["as_of"] = row["available_at"] = request["cutoff"]
    request["advisory"] = _p6_advisory(request, macro=1.0)
    request["advisory"]["weights"] = dict(BLEND_WEIGHTS)
    for feature in request["advisory"]["features"]:
        feature["feature_available_at"] = request["cutoff"]
        feature["direct_news"] = feature["spillover"] = feature["pead"] = None

    result = _pipeline(tmp_path).run(request)
    assert result["outcome"] == "proposal"
    p6 = result["annotations"]["p6"]
    assert p6["excluded_streams"] == list(STREAMS)
    assert p6["stream_validity"] == {stream: [False] * len(request["universe"]) for stream in STREAMS}


@pytest.mark.parametrize("fault", ["blend", "solver", "cost", "deadline"])
def test_p6_optional_failures_return_baseline_without_annotations(tmp_path, fault):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request, macro=0.8, value=0.2)
    request["advisory"]["weights"] = dict(BLEND_WEIGHTS)
    baseline = _baseline_run(tmp_path, request)
    pipeline = _pipeline(tmp_path, name=f"{fault}.db")
    if fault == "blend":
        patcher = patch("omega.pipeline.shadow_pipeline.blend_features", side_effect=RuntimeError("blend failure"))
    elif fault == "solver":
        original = shadow_pipeline_module.PortfolioOptimizer.optimize_weights
        calls = 0

        def fail_p6_optimizer(optimizer, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("solver failure")
            return original(optimizer, *args, **kwargs)

        patcher = patch.object(shadow_pipeline_module.PortfolioOptimizer, "optimize_weights", fail_p6_optimizer)
    elif fault == "cost":
        patcher = patch.object(ShadowPipeline, "_p6_costs", side_effect=RuntimeError("cost failure"))
    else:
        original_proposal = pipeline._proposal

        def expired_proposal(req, weights, cutoff, deadline, stages):
            return original_proposal(req, weights, cutoff, shadow_pipeline_module.time.monotonic() - 1, stages)

        patcher = patch.object(pipeline, "_proposal", side_effect=expired_proposal)

    with patcher:
        result = pipeline.run(request)

    assert result["outcome"] == "fallback"
    assert result["annotations"] == {}
    assert result["reason"] == ("deadline" if fault == "deadline" else "advisory_error")
    _assert_baseline_economics(result, baseline)


def test_p6_publication_failure_rolls_back_retry_commits_once_then_replays(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    pipeline = _pipeline(tmp_path)
    with patch.object(ShadowPipeline, "_commit", side_effect=sqlite3.OperationalError("injected commit failure")):
        failed = pipeline.run(request)
    assert failed["outcome"] == "uncommitted"
    assert failed["reason"] == "storage"
    assert failed["annotations"] == {}
    assert failed["committed"] is False

    retry = pipeline.run(request)
    replay = pipeline.run(request)
    assert retry["outcome"] == "proposal"
    assert replay["outcome"] == "replay"
    assert replay["decision_digest"] == retry["decision_digest"]
    with sqlite3.connect(pipeline.path) as db:
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1


def test_p6_worker_lock_is_not_released_by_rejected_concurrent_call(tmp_path):
    request = _w7_request()
    pipeline = _pipeline(tmp_path)
    assert pipeline._run_lock.acquire(blocking=False)
    try:
        with pytest.raises(ValueError, match="worker already active"):
            pipeline.run(request)
        assert pipeline._run_lock.locked()
    finally:
        pipeline._run_lock.release()

    result = pipeline.run(request)
    assert result["committed"] is True
    assert not pipeline._run_lock.locked()


@pytest.mark.parametrize(
    "location,value",
    [("macro", float("nan")), ("weight", float("inf")), ("feature", float("nan")), ("signal", float("inf"))],
)
def test_p6_nonfinite_request_is_rejected_before_database_mutation(tmp_path, location, value):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    if location == "macro":
        request["advisory"]["macro_multiplier"] = value
    elif location == "weight":
        request["advisory"]["weights"]["direct_news"] = value
    elif location == "feature":
        request["advisory"]["features"][0]["direct_news"] = value
    else:
        request["signal"]["values"][0] = value
    pipeline = _pipeline(tmp_path)

    with pytest.raises((TypeError, ValueError)):
        pipeline.run(request)
    assert not pipeline.path.exists()


def test_p6_cost_translation_handles_partial_empty_and_invalid_ledgers():
    selected = {
        "fills": [
            {"id": "buy-partial", "side": "BUY", "quantity": 100, "price_vnd": 1000},
            {"id": "sell-partial", "side": "SELL", "quantity": 100, "price_vnd": 1000},
        ]
    }
    costs = ShadowPipeline._p6_costs(selected, 10_000_000)
    assert [(row["fill_id"], row["side"]) for row in costs["fills"]] == [
        ("buy-partial", "BUY"), ("sell-partial", "SELL"),
    ]
    assert [row["cost_bps"] for row in costs["fills"]] == [17, 27]
    assert ShadowPipeline._p6_costs({"fills": []}, 10_000_000)["fills"] == []
    for selected_fills, nav in (([], 0), ([{**selected["fills"][0], "id": "duplicate"}] * 2, 10_000_000)):
        with pytest.raises(ValueError):
            ShadowPipeline._p6_costs({"fills": selected_fills}, nav)


@pytest.mark.parametrize("liquidity", [0, 100], ids=["unfilled", "partial"])
def test_p6_public_costs_use_executed_quantity_only(tmp_path, liquidity):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    for row in request["market"]:
        row["ask_quantity"] = liquidity
    result = _pipeline(tmp_path).run(request)
    assert result["outcome"] == "proposal"
    costs = result["annotations"]["p6"]["execution_costs"]["fills"]
    assert len(costs) == len(result["fills"])
    assert any(order["remainder_cancelled"] for order in result["orders"])
    for cost, fill in zip(costs, result["fills"]):
        assert cost["fill_id"] == fill["id"]
        assert cost["quantity"] == fill["quantity"] == liquidity
        assert cost["cost_vnd"] == (fill["quantity"] * fill["price_vnd"] * 17 + 5000) // 10_000
    assert result["nav_residual_vnd"] == 0


def test_p6_public_sell_costs_and_after_commit_reconciliation(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request, macro=1.0)
    pipeline = _pipeline(tmp_path)
    assert pipeline.run(request)["outcome"] == "proposal"
    request["decision_id"] = "D1"
    request["cutoff"] = "2026-10-02T13:00:00+07:00"
    request["advisory"]["macro_multiplier"] = 0.0
    for row in request["market"]:
        row["as_of"] = row["available_at"] = request["cutoff"]

    def committed_then_error(db):
        db.commit()
        raise sqlite3.OperationalError("ambiguous commit acknowledgement")

    with patch.object(ShadowPipeline, "_commit", side_effect=committed_then_error):
        result = pipeline.run(request)
    assert result["outcome"] == "proposal"
    assert result["committed"] is True
    assert result["fills"] and all(fill["side"] == "SELL" for fill in result["fills"])
    costs = result["annotations"]["p6"]["execution_costs"]["fills"]
    for cost, fill in zip(costs, result["fills"]):
        assert cost["fill_id"] == fill["id"]
        assert cost["cost_bps"] == 27
        assert fill["fee_vnd"] + fill["tax_vnd"] < cost["cost_vnd"]
    replay = pipeline.run(request)
    assert replay["outcome"] == "replay"
    assert replay["decision_digest"] == result["decision_digest"]
    assert replay["fills"] == result["fills"]
    assert replay["annotations"] == result["annotations"]
    with sqlite3.connect(pipeline.path) as db:
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2


@pytest.mark.parametrize("fault", ["shape", "negative", "nan", "inf", "oversized"])
def test_p6_invalid_optimizer_output_falls_back(tmp_path, fault):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    request["advisory"]["weights"] = dict(BLEND_WEIGHTS)
    baseline = _baseline_run(tmp_path, request)
    original = shadow_pipeline_module.PortfolioOptimizer.optimize_weights
    calls = 0

    def invalid_candidate(optimizer, *args, **kwargs):
        nonlocal calls
        calls += 1
        candidate = original(optimizer, *args, **kwargs)
        if calls == 2:
            if fault == "shape":
                return candidate.iloc[::-1]
            candidate.iloc[0] = {"negative": -0.01, "nan": float("nan"), "inf": float("inf"), "oversized": 1e13}[fault]
        return candidate

    with patch.object(shadow_pipeline_module.PortfolioOptimizer, "optimize_weights", invalid_candidate):
        result = _pipeline(tmp_path).run(request)
    assert calls == 2
    assert result["outcome"] == "fallback" and result["annotations"] == {}
    _assert_baseline_economics(result, baseline)


@pytest.mark.parametrize("mode", ["shadow", "replay"])
def test_p6_modes_commit_identical_request_once(tmp_path, mode):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    pipeline = _pipeline(tmp_path, mode=mode)
    first = pipeline.run(request)
    replay = pipeline.run(request)
    assert first["outcome"] == "proposal"
    assert replay["outcome"] == "replay"
    assert replay["decision_digest"] == first["decision_digest"]
    assert replay["annotations"] == first["annotations"]


def test_p6_post_cost_deadline_clears_annotations_and_preserves_baseline(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    baseline = _baseline_run(tmp_path, request)
    pipeline = _pipeline(tmp_path)
    original = pipeline._p6_costs

    def expire_after_cost(selected, nav):
        original(selected, nav)
        raise TimeoutError("post-cost deadline")

    with patch.object(pipeline, "_p6_costs", side_effect=expire_after_cost):
        result = pipeline.run(request)
    assert result["outcome"] == "fallback" and result["reason"] == "deadline"
    assert result["annotations"] == {}
    _assert_baseline_economics(result, baseline)


def test_p6_malformed_advisory_falls_back_without_partial_output_or_mutation(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    request["advisory"]["features"][0]["direct_news"] = 2.0
    before = deepcopy(request)
    baseline_request = deepcopy(request)
    baseline_request["advisory"] = None
    baseline = _pipeline(tmp_path, mode="disabled", name="baseline.db").run(baseline_request)
    result = _pipeline(tmp_path, name="fallback.db").run(request)
    assert result["outcome"] == "fallback"
    assert result["annotations"] == {}
    assert result["baseline_digest"] == baseline["baseline_digest"]
    for key in ("weights", "orders", "fills", "nav_vnd"):
        assert result[key] == baseline[key]
    for key in ("cash", "positions", "receivables", "peak"):
        assert result["ledger"][key] == baseline["ledger"][key]
    assert request == before


def test_p6_risk_halt_veto_dominates_advisory(tmp_path):
    request = _w7_request()
    request["risk_halt"] = True
    request["advisory"] = _p6_advisory(request, macro=0.0, value=1.0)
    result = _pipeline(tmp_path).run(request)
    assert result["outcome"] == "rejected"
    assert result["reason"] == "risk"
    assert result["fills"] == []
    assert result["applied"] is False
    assert result["live_lambda"] == 0


def test_p6_requires_shadow_or_replay_mode_and_ordered_prior_session_features(tmp_path):
    request = _w7_request()
    request["advisory"] = _p6_advisory(request)
    paper = _pipeline(tmp_path, mode="paper").run(request)
    assert paper["outcome"] == "fallback" and paper["annotations"] == {}
    request["advisory"]["features"][0]["feature_as_of"] = request["cutoff"]
    result = _pipeline(tmp_path, mode="shadow", name="bad-feature.db").run(request)
    assert result["outcome"] == "fallback"
    assert result["annotations"] == {}


def test_walk_forward_rejects_event_groups_crossing_oos_windows():
    panel = _panel()
    panel.loc[panel["session"] == 24, "event_group"] = "E8"
    with pytest.raises(ValueError, match="connected event groups"):
        _evaluate(panel)


def test_walk_forward_preserves_missing_quant_and_rejects_duplicate_row_index():
    panel = _panel()
    panel.loc[0, "quant"] = np.nan
    assert _evaluate(panel)["historical_eligible"] is False
    panel.index = [0] * len(panel)
    with pytest.raises(ValueError, match="row index"):
        _evaluate(panel)


def test_p6_cost_overlay_separates_booked_fees_from_comparison_costs():
    selected = {
        "fills": [
            {"id": "fill-buy", "side": "BUY", "quantity": 100, "price_vnd": 1000, "fee_vnd": 150, "tax_vnd": 0},
            {"id": "fill-sell", "side": "SELL", "quantity": 100, "price_vnd": 1000, "fee_vnd": 150, "tax_vnd": 100},
        ]
    }
    costs = ShadowPipeline._p6_costs(selected, 10_000_000)
    assert costs["booked_in_w7_cash"] is False
    assert [row["cost_bps"] for row in costs["fills"]] == [17, 27]
    assert [row["cost_vnd"] for row in costs["fills"]] == [170, 270]
    assert sum(row["cost_vnd"] for row in costs["fills"]) == 440
    assert [row["fee_vnd"] for row in selected["fills"]] == [150, 150]
    assert [row["tax_vnd"] for row in selected["fills"]] == [0, 100]
