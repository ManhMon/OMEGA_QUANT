import numpy as np
import pytest

from omega.quant.evolution.genetic_engine import GPConfig, GPIndividual, GPNode, _evaluation_mask


def test_evaluation_mask_respects_liquidity_filter():
    alpha = np.array([1.0, 2.0, np.nan, 4.0])
    target = np.array([1.0, 2.0, 3.0, 4.0])
    features = {"__liquidity_mask__": np.array([True, False, True, True])}

    mask = _evaluation_mask(alpha, target, features)

    assert mask.tolist() == [True, False, False, True]


def test_neutralization_and_liquidity_mask_reduce_inflated_ic():
    rng = np.random.RandomState(42)
    n_dates = 12
    per_date = 8
    n = n_dates * per_date
    dates = np.repeat(np.arange(n_dates), per_date)
    log_mcap = np.tile(np.linspace(1.0, 2.5, per_date), n_dates)
    sectors = np.tile(np.array([0, 0, 1, 1, 2, 2, 3, 3]), n_dates)
    true_signal = rng.randn(n)
    noise = rng.randn(n)
    sector_effect = np.take(np.array([1.0, -0.5, 0.3, -0.2]), sectors)

    alpha = true_signal + 3.0 * log_mcap + sector_effect
    target = (0.35 * true_signal) + (0.65 * noise) + 2.0 * log_mcap + sector_effect
    target[: per_date * 2] = alpha[: per_date * 2]
    liquidity_mask = np.ones(n, dtype=bool)
    liquidity_mask[: per_date * 2] = False

    features = {
        "f1": alpha,
        "__date__": dates,
        "__log_market_cap__": log_mcap,
        "__sector__": sectors,
        "__liquidity_mask__": liquidity_mask,
    }
    config = GPConfig(min_observations=10, neutralize_size_sector=True)
    individual = GPIndividual(tree=GPNode(operator="terminal", value="f1"))

    ic_filtered = individual._compute_combined_ic(alpha, target, features, config)
    ic_unfiltered = individual._compute_combined_ic(
        alpha,
        target,
        {k: v for k, v in features.items() if k != "__liquidity_mask__"},
        config,
    )

    assert np.isfinite(ic_filtered)
    assert ic_filtered < ic_unfiltered
    assert ic_filtered > 0.0
