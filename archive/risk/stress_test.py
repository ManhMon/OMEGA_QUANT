from __future__ import annotations

import pandas as pd


def apply_stress_scenario(
    exposures: pd.Series | dict[str, float],
    shocks: pd.Series | dict[str, float],
) -> pd.Series:
    exposure_series = pd.Series(exposures, dtype="float64")
    shock_series = pd.Series(shocks, dtype="float64")
    aligned_shocks = shock_series.reindex(exposure_series.index).fillna(0.0)
    return exposure_series * aligned_shocks


def scenario_pnl(
    positions: pd.Series | dict[str, float],
    price_shocks: pd.Series | dict[str, float],
) -> float:
    stressed = apply_stress_scenario(positions, price_shocks)
    return float(stressed.sum())


def historical_stress_pnl(asset_returns: pd.DataFrame, weights: pd.Series | dict[str, float]) -> pd.Series:
    if asset_returns.empty:
        raise ValueError("asset_returns must contain at least 1 row")
    weight_series = pd.Series(weights, dtype="float64")
    missing = asset_returns.columns.difference(weight_series.index)
    if len(missing) > 0:
        raise ValueError(f"weights missing assets: {list(missing)}")
    lagged = asset_returns[weight_series.index].shift(1)
    return lagged.mul(weight_series, axis=1).sum(axis=1, min_count=1)


def worst_historical_stress(asset_returns: pd.DataFrame, weights: pd.Series | dict[str, float]) -> float:
    pnl = historical_stress_pnl(asset_returns, weights).dropna()
    if pnl.empty:
        raise ValueError("historical stress pnl is empty after T-1 lag")
    return abs(float(pnl.min()))


def factor_stress_matrix(exposures: pd.DataFrame, factor_shocks: pd.DataFrame) -> pd.DataFrame:
    if list(exposures.columns) != list(factor_shocks.columns):
        raise ValueError("factor columns must match exactly")
    return exposures.astype("float64") @ factor_shocks.astype("float64").T
