import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import genetic_alpha_evolution_v3 as v3
import genetic_alpha_evolution_v4 as v4
from omega.quant.evolution import genetic_engine as ge


def _make_features():
    dates = pd.to_datetime(
        [
            "2024-01-02",
            "2024-01-02",
            "2024-01-02",
            "2024-01-02",
            "2024-01-02",
            "2024-01-02",
            "2024-01-03",
            "2024-01-03",
            "2024-01-03",
            "2024-01-03",
            "2024-01-03",
            "2024-01-03",
        ]
    ).to_numpy()
    return {
        "returns_1d": np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float),
        "returns_5d": np.array([6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6], dtype=float),
        "__date__": dates,
        "__log_market_cap__": np.linspace(10.0, 20.0, 12),
        "__sector__": np.array([0, 0, 1, 1, 2, 2, 0, 0, 1, 1, 2, 2]),
        "__liquidity_mask__": np.ones(12, dtype=bool),
    }


def test_v4_daily_ic_matches_v3():
    features = _make_features()
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)
    config = ge.GPConfig(neutralize_size_sector=True)

    ic_v3 = v3.compute_engine_consistent_daily_ic(signal, target, dict(features), config)
    ic_v4 = v4.compute_engine_consistent_daily_ic(signal, target, dict(features), config)

    assert abs(ic_v4 - ic_v3) <= 1e-12


def test_v4_time_fold_ir_matches_original_patch_target():
    features = _make_features()
    features[ge.FOLD_STRUCTURE_CACHE_KEY] = ge._build_time_fold_structure(features["__date__"], 3)
    features[ge.NEUTRALIZATION_CACHE_KEY] = ge._build_neutralization_cache(
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
    )
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)
    config = ge.GPConfig(use_time_fold_ir=True, time_folds=3, fold_ir_std_floor=0.03, neutralize_size_sector=True)

    original = v4.ORIGINAL_COMPUTE_TIME_FOLD_IR(signal, target, dict(features), config)
    patched = v4._compute_time_fold_ir_v4(signal, target, dict(features), config)

    assert abs(original - patched) <= 1e-12


def test_v4_subtree_cache_keeps_signal_identical():
    shared = ge.GPNode(operator="+", children=[ge.GPNode(operator="terminal", value="returns_1d"), ge.GPNode(operator="terminal", value="returns_5d")])
    tree = ge.GPNode(operator="*", children=[shared, shared])
    features = _make_features()
    original = v4.ORIGINAL_GPINDIVIDUAL(tree=tree)
    patched = ge.GPIndividual(tree=tree)

    original_signal = original._execute_tree(tree, dict(features))
    patched_signal = patched._execute_tree(tree, features)

    np.testing.assert_allclose(original_signal, patched_signal)
    assert v4.SUBTREE_CACHE_KEY in features
    cache_size = len(features[v4.SUBTREE_CACHE_KEY])
    patched._execute_tree(tree, features)
    assert len(features[v4.SUBTREE_CACHE_KEY]) == cache_size


def test_build_feature_bank_matches_v3_feature_logic():
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"] * 8 + ["BBB"] * 8,
            "date": list(pd.date_range("2024-01-01", periods=8, freq="B")) * 2,
            "open": np.arange(16, dtype=float) + 10.0,
            "high": np.arange(16, dtype=float) + 11.0,
            "low": np.arange(16, dtype=float) + 9.0,
            "close": np.arange(16, dtype=float) + 10.5,
            "volume": np.arange(16, dtype=float) + 100.0,
            "fwd_ret_5": np.linspace(0.01, 0.16, 16),
        }
    ).sort_values(["ticker", "date"]).reset_index(drop=True)
    args = SimpleNamespace(avg_volume_window=5, min_avg_volume=0.0)

    expected = frame.copy()
    expected["returns_1d"] = expected.groupby("ticker")["close"].transform(lambda x: x.pct_change(1))
    expected["returns_5d"] = expected.groupby("ticker")["close"].transform(lambda x: x.pct_change(5))
    expected["vol_ratio"] = expected["volume"] / expected.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    expected["hl_range"] = (expected["high"] - expected["low"]) / expected["close"]
    expected["oc_range"] = (expected["close"] - expected["open"]) / expected["close"]
    expected["hl_range_cs_z"] = v3._cs_zscore_by_date(expected["hl_range"], expected["date"])
    expected["oc_range_cs_z"] = v3._cs_zscore_by_date(expected["oc_range"], expected["date"])
    expected["__log_market_cap__"] = np.log1p((expected["close"] * expected["volume"]).clip(lower=0.0))
    expected["__sector__"] = v3._volume_quartile_sector_proxy(expected["volume"], expected["date"])
    expected["traded_value"] = expected["close"] * expected["volume"]
    expected["avg_traded_value"] = (
        expected.groupby("ticker")["traded_value"].rolling(args.avg_volume_window, min_periods=5).mean().reset_index(level=0, drop=True)
    )
    expected["avg_traded_value"] = expected.groupby("ticker")["avg_traded_value"].shift(1)
    expected["liquidity_mask"] = (expected["avg_traded_value"] > args.min_avg_volume).fillna(False)
    expected[v3.FEATURE_COLS] = expected.groupby("ticker")[v3.FEATURE_COLS].shift(1)
    expected["__log_market_cap__"] = expected.groupby("ticker")["__log_market_cap__"].shift(1)
    expected["__sector__"] = expected.groupby("ticker")["__sector__"].shift(1)

    actual = v4._build_feature_bank(frame, args)

    for col in v3.FEATURE_COLS + ["__log_market_cap__", "avg_traded_value"]:
        np.testing.assert_allclose(actual[col].to_numpy(), expected[col].to_numpy(), equal_nan=True)
    np.testing.assert_array_equal(actual["liquidity_mask"].to_numpy(), expected["liquidity_mask"].to_numpy())
