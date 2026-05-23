from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.risk.cvar import cvar_historical, portfolio_cvar, rolling_cvar, var_historical


@pytest.fixture
def sample_returns() -> pd.Series:
    return pd.Series([-0.05, -0.03, -0.02, 0.01, 0.02, 0.03, -0.04, 0.01, -0.01, 0.02], dtype="float64")


def test_var_historical_95(sample_returns: pd.Series) -> None:
    assert var_historical(sample_returns, confidence=0.95) == pytest.approx(0.05)


def test_cvar_historical_95(sample_returns: pd.Series) -> None:
    assert cvar_historical(sample_returns, confidence=0.95) == pytest.approx(0.05)


def test_cvar_historical_99(sample_returns: pd.Series) -> None:
    assert cvar_historical(sample_returns, confidence=0.99) == pytest.approx(0.05)


def test_var_rejects_bad_confidence(sample_returns: pd.Series) -> None:
    with pytest.raises(ValueError, match="confidence"):
        var_historical(sample_returns, confidence=1.0)


def test_cvar_ignores_nulls() -> None:
    returns = pd.Series([-0.05, np.nan, -0.02, 0.01])
    assert cvar_historical(returns, confidence=0.95) == pytest.approx(0.05)


def test_rolling_cvar_applies_t_minus_1_lag(sample_returns: pd.Series) -> None:
    result = rolling_cvar(sample_returns, window=3, confidence=0.95)
    expected = cvar_historical(sample_returns.iloc[0:3], confidence=0.95)
    assert result.iloc[3] == pytest.approx(expected)


def test_rolling_cvar_rejects_bad_window(sample_returns: pd.Series) -> None:
    with pytest.raises(ValueError, match="window"):
        rolling_cvar(sample_returns, window=0)


def test_portfolio_cvar_uses_lagged_asset_returns() -> None:
    asset_returns = pd.DataFrame(
        {
            "A": [0.01, -0.50, 0.02, 0.01],
            "B": [0.01, -0.10, 0.03, 0.02],
        }
    )
    weights = {"A": 0.5, "B": 0.5}
    result = portfolio_cvar(asset_returns, weights, confidence=0.95)
    lagged_portfolio = asset_returns.shift(1).mul(pd.Series(weights), axis=1).sum(axis=1).dropna()
    assert result == pytest.approx(cvar_historical(lagged_portfolio, confidence=0.95))
