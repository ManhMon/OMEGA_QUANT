"""
Volatility Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().mean()
  with reset_index(level=0, drop=True)
"""

import pandas as pd
import numpy as np
from .primitives import _safe_divide


def compute_atr_normalized(
    df: pd.DataFrame, period: int = 14, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Average True Range (ATR) normalized by close price.

    Formula: ATR / Close
             TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    PIT: Uses T-1 lagged values.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, high, low, close columns
        period: Lookback period (default 14)
        symbol_col: Symbol column name

    Returns:
        Series with normalized ATR values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate True Range components
    high_low = df_work["high"] - df_work["low"]

    close_prev = df_work.groupby(symbol_col)["close"].shift(1)
    high_close_prev = (df_work["high"] - close_prev).abs()
    low_close_prev = (df_work["low"] - close_prev).abs()

    # True Range = max of three components
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(
        axis=1
    )

    # Calculate ATR using native rolling API
    atr = (
        tr.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Normalize by close price
    atr_norm = _safe_divide(atr, df_work["close"], fill_value=0.0)

    # Apply T-1 lag for PIT safety
    df_work["_atr_norm_temp"] = atr_norm
    atr_norm_lagged = df_work.groupby(symbol_col)["_atr_norm_temp"].shift(1)

    return atr_norm_lagged.fillna(0.0)


def compute_historical_volatility(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Historical Volatility - Standard deviation of returns.

    Formula: StdDev(log_returns) * sqrt(252) (annualized)
    PIT: Uses T-1 lagged prices.
    Native Rolling API: Uses .groupby().rolling().std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with annualized volatility values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate log returns
    log_returns = np.log(
        df_work[price_col] / df_work.groupby(symbol_col)[price_col].shift(1)
    )

    # Calculate rolling standard deviation using native rolling API
    vol = (
        log_returns.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Annualize (252 trading days)
    vol_annualized = vol * np.sqrt(252)

    # Apply T-1 lag for PIT safety
    df_work["_vol_temp"] = vol_annualized
    vol_lagged = df_work.groupby(symbol_col)["_vol_temp"].shift(1)

    return vol_lagged.fillna(0.0)


def compute_downside_volatility(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Downside Volatility - Semi-deviation (only negative returns).

    Formula: StdDev(returns where returns < 0)
    PIT: Uses T-1 lagged prices.

    Args:
        df: DataFrame with date, symbol, and price columns
        period: Lookback period (default 20)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with downside volatility values
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate returns
    returns = df_work.groupby(symbol_col)[price_col].pct_change()

    # Only keep negative returns
    neg_returns = returns.where(returns < 0, 0.0)

    # Calculate rolling std using native rolling API
    downside_vol = (
        neg_returns.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=2)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Apply T-1 lag for PIT safety
    df_work["_dvol_temp"] = downside_vol
    dvol_lagged = df_work.groupby(symbol_col)["_dvol_temp"].shift(1)

    return dvol_lagged.fillna(0.0)


def compute_parkinson_volatility(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Parkinson Volatility - High-Low range estimator.

    Formula: sqrt(1/(4*ln(2)) * mean(ln(High/Low)^2)) * sqrt(252)
    PIT: Uses T-1 lagged values.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, high, low columns
        period: Lookback period (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with Parkinson volatility values (annualized)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate log(High/Low)^2
    hl_ratio = (
        np.log(_safe_divide(df_work["high"], df_work["low"], fill_value=1.0))
        ** 2
    )

    # Calculate rolling mean using native rolling API
    hl_mean = (
        hl_ratio.groupby(df_work[symbol_col])
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Parkinson estimator
    parkinson_var = hl_mean / (4 * np.log(2))
    parkinson_vol = np.sqrt(parkinson_var) * np.sqrt(252)

    # Apply T-1 lag for PIT safety
    df_work["_pvol_temp"] = parkinson_vol
    pvol_lagged = df_work.groupby(symbol_col)["_pvol_temp"].shift(1)

    return pvol_lagged.fillna(0.0)


def compute_garman_klass_volatility(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Garman-Klass Volatility - Advanced OHLC estimator
    (more efficient than Parkinson).

    Formula: sqrt(0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2) * sqrt(252)
    PIT: Uses T-1 lagged values.
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, open, high, low, close columns
        period: Lookback period (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with Garman-Klass volatility values (annualized, float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    open_lagged = df_work.groupby(symbol_col)["open"].shift(1)

    # Garman-Klass formula components
    hl_component = 0.5 * (
        np.log(_safe_divide(high_lagged, low_lagged, fill_value=1.0)) ** 2
    )
    co_component = (2 * np.log(2) - 1) * (
        np.log(_safe_divide(close_lagged, open_lagged, fill_value=1.0)) ** 2
    )

    gk_var = hl_component - co_component

    # Calculate rolling mean using native rolling API
    df_work["_gk_var"] = gk_var.astype(np.float64)
    gk_var_mean = (
        df_work.groupby(symbol_col)["_gk_var"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Annualize
    gk_vol = np.sqrt(gk_var_mean.clip(lower=0)) * np.sqrt(252)

    return gk_vol.fillna(0.0).astype(np.float64)


def compute_yang_zhang_volatility(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    Yang-Zhang Volatility - Most efficient OHLC estimator
    (handles overnight gaps).

    Formula: sqrt(sigma_o^2 + k*sigma_c^2 + (1-k)*sigma_rs^2)
    where:
        sigma_o = overnight volatility (open/close_prev)
        sigma_c = close-to-close volatility
        sigma_rs = Rogers-Satchell volatility
        k = 0.34 / (1.34 + (n+1)/(n-1))
    PIT: Uses T-1 lagged values.
    Native Rolling API: Uses .groupby().rolling().var()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, open, high, low, close columns
        period: Lookback period (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with Yang-Zhang volatility values (annualized, float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    open_lagged = df_work.groupby(symbol_col)["open"].shift(1)
    close_prev_lagged = df_work.groupby(symbol_col)["close"].shift(2)

    # 1. Overnight volatility (open/close_prev) - with boundary check
    overnight_ratio = _safe_divide(
        open_lagged, close_prev_lagged, fill_value=1.0
    )
    # Ensure positive for log: clip to [1e-10, 1e10]
    overnight_ratio = overnight_ratio.clip(lower=1e-10, upper=1e10)
    overnight_ret = np.log(overnight_ratio)
    df_work["_overnight_ret"] = overnight_ret.astype(np.float64)
    sigma_o_sq = (
        df_work.groupby(symbol_col)["_overnight_ret"]
        .rolling(window=period, min_periods=2)
        .var()
        .reset_index(level=0, drop=True)
    )

    # 2. Close-to-close volatility - with boundary check
    close_ratio = _safe_divide(close_lagged, close_prev_lagged, fill_value=1.0)
    close_ratio = close_ratio.clip(lower=1e-10, upper=1e10)
    close_ret = np.log(close_ratio)
    df_work["_close_ret"] = close_ret.astype(np.float64)
    sigma_c_sq = (
        df_work.groupby(symbol_col)["_close_ret"]
        .rolling(window=period, min_periods=2)
        .var()
        .reset_index(level=0, drop=True)
    )

    # 3. Rogers-Satchell volatility (intraday) - with boundary check
    hl_ratio = _safe_divide(high_lagged, close_lagged, fill_value=1.0).clip(
        lower=1e-10, upper=1e10
    )
    ho_ratio = _safe_divide(high_lagged, open_lagged, fill_value=1.0).clip(
        lower=1e-10, upper=1e10
    )
    ll_ratio = _safe_divide(low_lagged, close_lagged, fill_value=1.0).clip(
        lower=1e-10, upper=1e10
    )
    lo_ratio = _safe_divide(low_lagged, open_lagged, fill_value=1.0).clip(
        lower=1e-10, upper=1e10
    )

    rs_component = np.log(hl_ratio) * np.log(ho_ratio) + np.log(
        ll_ratio
    ) * np.log(lo_ratio)

    df_work["_rs_component"] = rs_component.astype(np.float64)
    sigma_rs_sq = (
        df_work.groupby(symbol_col)["_rs_component"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # 4. Yang-Zhang estimator with k factor
    n = float(period)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))

    yz_var = (
        sigma_o_sq.fillna(0)
        + k * sigma_c_sq.fillna(0)
        + (1 - k) * sigma_rs_sq.fillna(0)
    )
    yz_vol = np.sqrt(yz_var.clip(lower=0)) * np.sqrt(252)

    return yz_vol.fillna(0.0).astype(np.float64)
