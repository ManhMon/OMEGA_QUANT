import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from genetic_alpha_evolution_v3 import (
    EMBARGO_TRADING_DAYS,
    VN_REGIME_DEFINITIONS,
    apply_trading_day_embargo,
    build_feature_fingerprint,
    build_vn_trading_days,
    compute_regime_ic,
    compute_turnover,
    permutation_test_ic,
)


def test_regime_ic_computes_per_regime_with_rationale():
    dates = pd.to_datetime([
        "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02",
        "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04",
    ])
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)

    regime_ic = compute_regime_ic(signal, target, dates.to_numpy(), VN_REGIME_DEFINITIONS)

    assert regime_ic["COVID_2020"]["ic"] == 1.0
    assert regime_ic["Bear_2022"]["ic"] == -1.0
    assert regime_ic["COVID_2020"]["rationale"]
    assert regime_ic["Lockbox_2025"]["ic"] is None


def test_turnover_computes_mean_cross_sectional_position_change():
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-02", "2024-01-02",
        "2024-01-03", "2024-01-03", "2024-01-03",
    ])
    tickers = np.array(["AAA", "BBB", "CCC", "AAA", "BBB", "CCC"])
    signal = np.array([0.0, 0.5, 1.0, 0.5, 0.0, 1.0], dtype=float)

    turnover = compute_turnover(signal, dates.to_numpy(), tickers)

    assert turnover == 1.0 / 3.0


def test_vn_calendar_excludes_holidays_and_applies_trading_day_embargo():
    trading_days = build_vn_trading_days(pd.Timestamp("2025-01-20"), pd.Timestamp("2025-02-10"))

    assert pd.Timestamp("2025-01-29") not in trading_days
    assert pd.Timestamp("2025-02-03") not in trading_days

    cutoff = apply_trading_day_embargo(pd.Timestamp("2025-02-10"), EMBARGO_TRADING_DAYS, trading_days)
    assert cutoff == pd.Timestamp("2025-01-24")


def test_permutation_test_uses_seeded_per_date_shuffling():
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
        "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03",
    ])
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)

    result_a = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=7)
    result_b = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=7)
    result_c = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=9)

    assert result_a == result_b
    assert result_a["observed_ic"] == 1.0
    assert result_a["n_permutations"] == 32
    assert result_a["random_seed"] == 7
    assert result_c["random_seed"] == 9


def test_feature_fingerprint_changes_when_features_change():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "ticker": ["AAA", "BBB"],
            "close": [10000.0, 20000.0],
            "volume": [1_000_000.0, 2_000_000.0],
            "fwd_ret_5": [0.01, 0.02],
            "returns_1d": [0.1, 0.2],
            "returns_5d": [0.3, 0.4],
            "vol_ratio": [1.0, 1.1],
            "hl_range": [0.02, 0.03],
            "oc_range": [0.01, 0.02],
            "hl_range_cs_z": [-1.0, 1.0],
            "oc_range_cs_z": [-1.0, 1.0],
        }
    )

    fingerprint_a = build_feature_fingerprint(frame)
    frame.loc[0, "returns_1d"] = 0.9
    fingerprint_b = build_feature_fingerprint(frame)

    assert fingerprint_a != fingerprint_b
