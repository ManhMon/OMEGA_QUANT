from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from omega.quant.regime.hmm_model import (
    GaussianHMM4State,
    HMMModelConfig,
    REGIME_BEAR_CALM,
    REGIME_BEAR_VOLATILE,
    REGIME_BULL_CALM,
    REGIME_BULL_VOLATILE,
    apply_regime_lock,
    build_stable_regime_map,
)


def test_regime_lock_requires_minimum_five_day_hold() -> None:
    raw = np.array([0, 0, 0, 1, 1, 0, 2, 2, 2, 2, 2, 3])
    locked = apply_regime_lock(raw, min_duration=5)
    assert locked.tolist() == [0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 2, 3]


def test_label_mapping_stable_under_state_id_permutation() -> None:
    canonical_returns = {0: -0.03, 1: -0.02, 2: 0.01, 3: 0.02}
    canonical_vols = {0: 0.10, 1: 0.30, 2: 0.08, 3: 0.25}
    canonical = build_stable_regime_map(canonical_returns, canonical_vols)
    assert canonical == {0: 0, 1: 1, 2: 2, 3: 3}

    permuted_returns = {7: 0.01, 9: -0.02, 4: 0.02, 3: -0.03}
    permuted_vols = {7: 0.08, 9: 0.30, 4: 0.25, 3: 0.10}
    permuted = build_stable_regime_map(permuted_returns, permuted_vols)
    assert permuted == {3: REGIME_BEAR_CALM, 9: REGIME_BEAR_VOLATILE, 7: REGIME_BULL_CALM, 4: REGIME_BULL_VOLATILE}


@pytest.mark.parametrize(
    ("state_mean_returns", "state_mean_volatility", "expected"),
    [
        (
            {0: -0.02, 1: -0.02, 2: 0.01, 3: 0.01},
            {0: 0.12, 1: 0.12, 2: 0.05, 3: 0.05},
            {0: REGIME_BEAR_CALM, 1: REGIME_BEAR_VOLATILE, 2: REGIME_BULL_CALM, 3: REGIME_BULL_VOLATILE},
        ),
        (
            {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.04},
            {0: 0.15, 1: 0.10, 2: 0.20, 3: 0.12},
            {1: REGIME_BEAR_CALM, 0: REGIME_BEAR_VOLATILE, 3: REGIME_BULL_CALM, 2: REGIME_BULL_VOLATILE},
        ),
        (
            {0: -0.04, 1: -0.03, 2: -0.02, 3: -0.01},
            {0: 0.30, 1: 0.10, 2: 0.25, 3: 0.05},
            {1: REGIME_BEAR_CALM, 0: REGIME_BEAR_VOLATILE, 3: REGIME_BULL_CALM, 2: REGIME_BULL_VOLATILE},
        ),
    ],
)
def test_stable_sort_tie_break_edge_cases(
    state_mean_returns: dict[int, float],
    state_mean_volatility: dict[int, float],
    expected: dict[int, int],
) -> None:
    assert build_stable_regime_map(state_mean_returns, state_mean_volatility) == expected


def test_predict_sequence_is_pit_safe_uses_t_minus_1_features_only() -> None:
    dates = pd.date_range("2024-01-01", periods=80, freq="D")
    returns = np.r_[np.full(20, -0.03), np.full(20, -0.01), np.full(20, 0.01), np.full(20, 0.03)]
    vols = np.r_[np.full(20, 0.10), np.full(20, 0.30), np.full(20, 0.08), np.full(20, 0.25)]
    features = pd.DataFrame(
        {
            "market_return": returns,
            "market_volatility": vols,
        },
        index=dates,
    )

    model = GaussianHMM4State(HMMModelConfig(min_training_samples=20, n_init=1, max_iter=50, random_state=0))
    regimes = model.fit_predict(features)

    assert pd.isna(regimes.iloc[0])
    expected_first_live = model.predict_next(features.iloc[[0]])
    assert regimes.iloc[1] == expected_first_live

    mutated = features.copy()
    mutated.iloc[-1] = [999.0, 999.0]
    mutated_regimes = model.predict_sequence(mutated)
    pd.testing.assert_series_equal(regimes.iloc[:-1], mutated_regimes.iloc[:-1])
