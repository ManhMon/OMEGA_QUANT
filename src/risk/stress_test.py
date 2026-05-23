"""
Stress testing utilities.

Public API
----------
apply_stress_scenario(positions, shocks) -> pd.Series
scenario_pnl(positions, shocks) -> float
historical_stress_pnl(returns, weights) -> pd.Series
worst_historical_stress(returns, weights) -> float
factor_stress_matrix(exposures, shocks) -> pd.DataFrame
"""
from __future__ import annotations

import pandas as pd


def apply_stress_scenario(
    positions: dict[str, float],
    shocks: dict[str, float],
) -> pd.Series:
    """
    Apply shock to each position.  Missing shocks default to 0.

    Returns a Series of PnL per asset (position * shock).
    """
    pos = pd.Series(positions)
    shock_series = pd.Series(shocks).reindex(pos.index).fillna(0.0)
    return pos * shock_series


def scenario_pnl(
    positions: dict[str, float],
    shocks: dict[str, float],
) -> float:
    """Total portfolio PnL under a stress scenario."""
    return float(apply_stress_scenario(positions, shocks).sum())


def historical_stress_pnl(
    returns: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    """
    Weighted portfolio PnL using T-1 lagged returns.

    Row 0 is NaN (no prior bar). Row i uses returns.iloc[i-1].
    Raises ValueError if weights are missing any asset column.
    """
    missing = set(returns.columns) - set(weights.keys())
    if missing:
        raise ValueError(f"weights missing assets: {missing}")
    w = pd.Series(weights).reindex(returns.columns)
    lagged = returns.shift(1)
    return lagged.mul(w, axis=1).sum(axis=1, min_count=1)


def worst_historical_stress(
    returns: pd.DataFrame,
    weights: dict[str, float],
) -> float:
    """Worst (most negative) historical stress PnL, returned as positive loss magnitude."""
    pnl = historical_stress_pnl(returns, weights).dropna()
    if pnl.empty:
        return 0.0
    return float(abs(pnl.min()))


def factor_stress_matrix(
    exposures: pd.DataFrame,
    shocks: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute asset PnL for each scenario via matrix multiply.

    exposures : assets × factors
    shocks    : scenarios × factors
    result    : assets × scenarios

    Raises ValueError if factor columns don't match exactly.
    """
    if set(exposures.columns) != set(shocks.columns):
        raise ValueError(
            "factor columns must match exactly: "
            f"exposures={set(exposures.columns)}, shocks={set(shocks.columns)}"
        )
    shocks_aligned = shocks[exposures.columns]
    # result[asset, scenario] = exposures[asset, :] · shocks[scenario, :]
    result = exposures.values @ shocks_aligned.values.T
    return pd.DataFrame(result, index=exposures.index, columns=shocks.index)
