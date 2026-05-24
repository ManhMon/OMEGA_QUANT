from __future__ import annotations

import pandas as pd


def mean_reversion_signal(prices: pd.Series, window: int = 20) -> pd.Series:
    """Negative z-score on same-bar prices. Lag applied downstream in sanitizer."""
    prices = prices.astype(float)
    rolling_mean = prices.rolling(window=window, min_periods=window).mean()
    rolling_std = prices.rolling(window=window, min_periods=window).std()
    z_score = (prices - rolling_mean) / rolling_std.replace(0.0, pd.NA)
    return (-z_score).fillna(0.0)


def momentum_signal(prices: pd.Series, window: int = 20) -> pd.Series:
    """Same-bar rate-of-change momentum. Lag applied downstream in sanitizer."""
    prices = prices.astype(float)
    return prices.pct_change(periods=window).fillna(0.0)


def trend_signal(prices: pd.Series, short_window: int = 10, long_window: int = 30) -> pd.Series:
    """Same-bar moving-average spread. Lag applied downstream in sanitizer."""
    prices = prices.astype(float)
    short_ma = prices.rolling(window=short_window, min_periods=short_window).mean()
    long_ma = prices.rolling(window=long_window, min_periods=long_window).mean()
    spread = short_ma - long_ma
    signal = spread / long_ma.abs().replace(0.0, pd.NA)
    return signal.fillna(0.0)


def generate_signals(
    df: pd.DataFrame,
    price_col: str = "close",
    mean_reversion_window: int = 20,
    momentum_window: int = 20,
    trend_short_window: int = 10,
    trend_long_window: int = 30,
) -> pd.DataFrame:
    """Generate raw same-bar signals from price history."""
    if price_col not in df.columns:
        raise ValueError(f"Price column '{price_col}' not found in DataFrame")

    prices = df[price_col]
    result = df.copy()
    result["signal_mean_reversion"] = mean_reversion_signal(prices, window=mean_reversion_window)
    result["signal_momentum"] = momentum_signal(prices, window=momentum_window)
    result["signal_trend"] = trend_signal(
        prices,
        short_window=trend_short_window,
        long_window=trend_long_window,
    )
    return result
