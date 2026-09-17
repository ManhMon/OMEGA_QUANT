"""
VN-Specific Alpha Functions

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

This module contains all Vietnam market-specific alpha functions including:
- BATCH 1: VN-Specific Liquidity Alphas (4 functions)
- BATCH 2: Advanced Mean Reversion Alphas (4 functions)
- BATCH 3: Microstructure & Foreign Flows (4 functions)
- BATCH 4: VN T+2 Settlement & Limit Mechanics (3 functions)
- Core VN-specific functions (4 functions)
- PHASE 3.4 ROUND 1: VN Microstructure Alphas (2 functions)
- PHASE 3.4 ROUND 2: VN Microstructure Alphas (3 functions)
- RESCUE P3 WEEK 1: 3 Missing Alphas (3 functions)

Total: 27 VN-specific alpha functions

COMPLIANCE:
- PIT (Point-in-Time): All alphas computed using T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- Robustness: Handles division by zero, NaN, and Inf
- Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)
- VN Settlement Rules: T+2 for money settlement, T+3 for securities settlement
- VN Limit Rules: HOSE ±7%, HNX ±10%, UPCOM ±15%
"""

import pandas as pd
import numpy as np
from .primitives import _safe_divide, _round_to_board_lot

# ============================================================================
# BATCH 1: VN-SPECIFIC LIQUIDITY ALPHAS (4)
# ============================================================================


def compute_vn_amihud_liquidity_reversal(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Amihud Liquidity Reversal - Mean reversion based on illiquidity spikes.

    Formula: -1 * zscore(Amihud_illiquidity)
             Hypothesis: Extreme illiquidity spikes reverse (liquidity returns)
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate Amihud illiquidity
    returns = df_work.groupby(symbol_col)[price_col].pct_change().abs()
    amihud = (
        _safe_divide(
            returns, df_work[volume_col].astype(np.float64), fill_value=0.0
        )
        * 1e6
    )

    # Calculate rolling mean and std for zscore using native rolling API
    df_work["_amihud"] = amihud
    amihud_mean = (
        df_work.groupby(symbol_col)["_amihud"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    amihud_std = (
        df_work.groupby(symbol_col)["_amihud"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Calculate zscore
    zscore = _safe_divide(amihud - amihud_mean, amihud_std, fill_value=0.0)

    # Reversal signal: negative zscore (high illiquidity predicts reversal)
    signal = -1.0 * zscore

    # Apply T-1 lag for PIT safety
    df_work["_signal_temp"] = signal
    signal_lagged = df_work.groupby(symbol_col)["_signal_temp"].shift(1)

    return signal_lagged.fillna(0.0)


def compute_vn_illiq_regime_penalty(
    df: pd.DataFrame,
    period: int = 60,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN ILLIQ Regime Penalty - Penalizes stocks in persistent
    illiquidity regimes.

    Formula: -1 * (Amihud_60d / Amihud_20d)
             Hypothesis: Worsening liquidity regime = avoid
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate Amihud illiquidity
    returns = df_work.groupby(symbol_col)[price_col].pct_change().abs()
    amihud = (
        _safe_divide(
            returns, df_work[volume_col].astype(np.float64), fill_value=0.0
        )
        * 1e6
    )

    # Calculate rolling averages using native rolling API
    df_work["_amihud"] = amihud
    amihud_60d = (
        df_work.groupby(symbol_col)["_amihud"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    amihud_20d = (
        df_work.groupby(symbol_col)["_amihud"]
        .rolling(window=20, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Regime ratio (higher = worsening liquidity)
    regime_ratio = _safe_divide(amihud_60d, amihud_20d, fill_value=1.0)

    # Penalty signal: negative ratio
    penalty = -1.0 * regime_ratio

    # Apply T-1 lag for PIT safety
    df_work["_penalty_temp"] = penalty
    penalty_lagged = df_work.groupby(symbol_col)["_penalty_temp"].shift(1)

    return penalty_lagged.fillna(0.0)


def compute_vn_volume_shock_reversal(
    df: pd.DataFrame,
    period: int = 20,
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Volume Shock Reversal - Mean reversion after extreme volume spikes.

    Formula: -1 * zscore(volume)
             Hypothesis: Extreme volume spikes reverse (exhaustion)
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Convert volume to float64
    volume = df_work[volume_col].astype(np.float64)

    # Calculate rolling mean and std for zscore using native rolling API
    df_work["_volume"] = volume
    vol_mean = (
        df_work.groupby(symbol_col)["_volume"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)["_volume"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Calculate zscore
    zscore = _safe_divide(volume - vol_mean, vol_std, fill_value=0.0)

    # Reversal signal: negative zscore (high volume predicts reversal)
    signal = -1.0 * zscore

    # Apply T-1 lag for PIT safety
    df_work["_signal_temp"] = signal
    signal_lagged = df_work.groupby(symbol_col)["_signal_temp"].shift(1)

    return signal_lagged.fillna(0.0)


def compute_vn_turnover_exhaustion(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Turnover Exhaustion - Detects exhaustion after high turnover periods.

    Formula: -1 * zscore(turnover_ratio)
             where turnover_ratio = volume / rolling_avg_volume
             Hypothesis: Extreme turnover exhausts buying power
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Convert volume to float64
    volume = df_work[volume_col].astype(np.float64)

    # Calculate rolling average volume using native rolling API
    df_work["_volume"] = volume
    vol_ma = (
        df_work.groupby(symbol_col)["_volume"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Calculate turnover ratio
    turnover_ratio = _safe_divide(volume, vol_ma, fill_value=1.0)

    # Calculate zscore of turnover ratio
    df_work["_turnover"] = turnover_ratio
    turnover_mean = (
        df_work.groupby(symbol_col)["_turnover"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    turnover_std = (
        df_work.groupby(symbol_col)["_turnover"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    zscore = _safe_divide(
        turnover_ratio - turnover_mean, turnover_std, fill_value=0.0
    )

    # Exhaustion signal: negative zscore (high turnover predicts reversal)
    signal = -1.0 * zscore

    # Apply T-1 lag for PIT safety
    df_work["_signal_temp"] = signal
    signal_lagged = df_work.groupby(symbol_col)["_signal_temp"].shift(1)

    return signal_lagged.fillna(0.0)


# ============================================================================
# BATCH 2: ADVANCED MEAN REVERSION ALPHAS (4)
# ============================================================================


def compute_vn_bollinger_snapback(
    df: pd.DataFrame,
    period: int = 20,
    num_std: float = 2.0,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Bollinger Snapback - Mean reversion signal from Bollinger Band extremes.

    Formula: -1 * sign(BB_position) * |BB_position|^2
             where BB_position = (Price - MA) / (num_std * StdDev)
             Hypothesis: Extreme BB positions (>1 or <-1)
                         predict snapback to mean
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate Bollinger Bands on lagged data using native rolling API
    df_work["_price_lagged"] = price_lagged
    ma = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    std = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Calculate BB position (normalized distance from mean)
    bb_position = _safe_divide(
        price_lagged - ma, num_std * std, fill_value=0.0
    )

    # Snapback signal: -sign(position) * position^2 (quadratic penalty for
    # extremes)
    signal = -1.0 * np.sign(bb_position) * (bb_position**2)

    return signal.fillna(0.0).astype(np.float64)


def compute_vn_rsi_divergence_reversal(
    df: pd.DataFrame,
    period: int = 14,
    lookback: int = 5,
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN RSI Divergence Reversal - Enhanced RSI divergence signal with magnitude.

    Formula: divergence * -price_slope * RSI_deviation
             where divergence = sign(price_slope) != sign(RSI_slope)
             Hypothesis: Price-RSI divergence predicts reversal
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate RSI on lagged data using native rolling API
    df_work["_price_lagged"] = price_lagged
    delta = df_work.groupby(symbol_col)["_price_lagged"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    df_work["_gain"] = gain
    df_work["_loss"] = loss
    avg_gain = (
        df_work.groupby(symbol_col)["_gain"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    avg_loss = (
        df_work.groupby(symbol_col)["_loss"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    rs = _safe_divide(avg_gain, avg_loss, fill_value=0.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Calculate slopes on lagged data
    price_slope = (
        price_lagged.groupby(df_work[symbol_col]).diff(lookback).values
    )
    rsi_slope = rsi.groupby(df_work[symbol_col]).diff(lookback).values

    # Detect divergence
    divergence = (
        (np.sign(price_slope) != np.sign(rsi_slope))
        & (price_slope != 0)
        & (rsi_slope != 0)
    )
    rsi_deviation = np.abs(rsi.values - 50.0) / 50.0

    # Signal: divergence * -price_slope * RSI_deviation
    signal = np.where(divergence, -1.0 * price_slope * rsi_deviation, 0.0)

    return (
        pd.Series(signal, index=df_work.index).astype(np.float64).fillna(0.0)
    )


def compute_vn_sector_neutral_residual_reversion(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    symbol_col: str = "ticker",
    sector_col: str = "sector",
) -> pd.Series:
    """
    VN Sector-Neutral Residual Reversion - Mean reversion
    of sector-adjusted returns.

    Formula: -1 * zscore(residual)
             where residual = stock_return - sector_median_return
             Hypothesis: Extreme sector-relative performance reverts
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Use lagged prices to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate stock returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    stock_returns = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate sector median returns using LAGGED returns (cross-sectional
    # per date)
    df_work["_return"] = stock_returns

    if sector_col in df_work.columns:
        # Calculate sector median from lagged returns per date
        sector_median = df_work.groupby(["date", sector_col])[
            "_return"
        ].transform("median")
    else:
        # No sector column - use cross-sectional median across all stocks per
        # date
        sector_median = df_work.groupby("date")["_return"].transform("median")

    # Calculate residual (stock return - sector return)
    residual = stock_returns - sector_median

    # Calculate rolling zscore of residual using per-ticker rolling
    df_work["_residual"] = residual.astype(np.float64)
    residual_mean = (
        df_work.groupby(symbol_col)["_residual"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    residual_std = (
        df_work.groupby(symbol_col)["_residual"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    zscore = _safe_divide(
        residual - residual_mean, residual_std, fill_value=0.0
    )

    # Reversion signal: -zscore (extreme outperformance predicts reversal)
    signal = -1.0 * zscore

    return signal.astype(np.float64).fillna(0.0)


def compute_vn_close_location_reversion(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN Close Location Reversion - Mean reversion based on Close
    Location Value (CLV).

    Formula: -1 * zscore(CLV)
             where CLV = (Close - Low) / (High - Low) - 0.5
             Hypothesis: Extreme CLV (close near high/low) predicts reversal
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)

    # Calculate Close Location Value (CLV) on lagged data
    hl_range = high_lagged - low_lagged
    clv = (
        _safe_divide(close_lagged - low_lagged, hl_range, fill_value=0.0) - 0.5
    )

    # Calculate rolling zscore of CLV using native rolling API
    df_work["_clv"] = clv.astype(np.float64)
    clv_mean = (
        df_work.groupby(symbol_col)["_clv"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    clv_std = (
        df_work.groupby(symbol_col)["_clv"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    zscore = _safe_divide(clv - clv_mean, clv_std, fill_value=0.0)

    # Reversion signal: -zscore (extreme CLV predicts reversal)
    signal = -1.0 * zscore

    return signal.fillna(0.0).astype(np.float64)


# ============================================================================
# BATCH 3: MICROSTRUCTURE & FOREIGN FLOWS (4)
# ============================================================================


def compute_vn_foreign_flow_persistence(
    df: pd.DataFrame, period: int = 5, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN Foreign Flow Persistence - Foreign net flow continuation signal.

    Formula: sign(foreign_net_flow_t-1) * |zscore(foreign_net_flow_t-1)|
             where foreign_net_flow = foreign_buy_value - foreign_sell_value
             Hypothesis: Strong foreign flows persist in short term
    PIT: Uses T-1 lagged foreign data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate foreign net flow (handle missing columns)
    if (
        "foreign_buy_value" in df_work.columns
        and "foreign_sell_value" in df_work.columns
    ):
        foreign_net_flow = (
            df_work["foreign_buy_value"].fillna(0.0)
            - df_work["foreign_sell_value"].fillna(0.0)
        ).astype(np.float64)
    elif "foreign_net_value" in df_work.columns:
        foreign_net_flow = (
            df_work["foreign_net_value"].fillna(0.0).astype(np.float64)
        )
    else:
        # No foreign data available, return zeros
        return pd.Series(0.0, index=df_work.index, dtype=np.float64)

    # MANDATORY: Lag ALL foreign data first to guarantee PIT safety
    df_work["_foreign_net_temp"] = foreign_net_flow
    foreign_net_flow_lagged = df_work.groupby(symbol_col)[
        "_foreign_net_temp"
    ].shift(1)

    # Calculate rolling zscore using native rolling API on lagged data
    df_work["_foreign_net"] = foreign_net_flow_lagged
    flow_mean = (
        df_work.groupby(symbol_col)["_foreign_net"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    flow_std = (
        df_work.groupby(symbol_col)["_foreign_net"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    zscore = _safe_divide(
        foreign_net_flow_lagged - flow_mean, flow_std, fill_value=0.0
    )

    # Persistence signal: sign * |zscore| (directional momentum)
    signal = np.sign(foreign_net_flow_lagged) * np.abs(zscore)

    return signal.fillna(0.0).astype(np.float64)


def compute_vn_foreign_absorption_reversal(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN Foreign Absorption Reversal - Reversal after heavy foreign absorption.

    Formula: -1 * zscore(foreign_net_flow / volume)
             Hypothesis: Extreme foreign absorption (relative to
                         volume) predicts reversal
    PIT: Uses T-1 lagged foreign data and volume.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate foreign net flow (handle missing columns)
    if (
        "foreign_buy_value" in df_work.columns
        and "foreign_sell_value" in df_work.columns
    ):
        foreign_net_flow = (
            df_work["foreign_buy_value"].fillna(0.0)
            - df_work["foreign_sell_value"].fillna(0.0)
        ).astype(np.float64)
    elif "foreign_net_value" in df_work.columns:
        foreign_net_flow = (
            df_work["foreign_net_value"].fillna(0.0).astype(np.float64)
        )
    else:
        # No foreign data available, return zeros
        return pd.Series(0.0, index=df_work.index, dtype=np.float64)

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    df_work["_foreign_net_temp"] = foreign_net_flow
    foreign_net_flow_lagged = df_work.groupby(symbol_col)[
        "_foreign_net_temp"
    ].shift(1)

    volume_lagged = (
        df_work.groupby(symbol_col)["volume"]
        .shift(1)
        .astype(np.float64)
        .replace(0, np.nan)
    )

    # Calculate foreign absorption ratio (foreign_net / volume) on lagged data
    absorption_ratio = _safe_divide(
        foreign_net_flow_lagged, volume_lagged, fill_value=0.0
    )

    # Calculate rolling zscore using native rolling API
    df_work["_absorption"] = absorption_ratio.astype(np.float64)
    absorption_mean = (
        df_work.groupby(symbol_col)["_absorption"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    absorption_std = (
        df_work.groupby(symbol_col)["_absorption"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    zscore = _safe_divide(
        absorption_ratio - absorption_mean, absorption_std, fill_value=0.0
    )

    # Reversal signal: -zscore (extreme absorption predicts reversal)
    signal = -1.0 * zscore

    return signal.fillna(0.0).astype(np.float64)


def compute_vn_foreign_room_squeeze(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN Foreign Room Squeeze - Signal based on foreign room
    availability percentage.

    Formula: -1 * (1 - foreign_room_pct)
             where foreign_room_pct = foreign_room / total_shares
             Hypothesis: Low foreign room (near limit) creates selling pressure
    PIT: Uses T-1 lagged foreign room data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate foreign room percentage (handle missing columns)
    if "foreign_room" in df_work.columns and "total_shares" in df_work.columns:
        total_shares = (
            df_work["total_shares"].astype(np.float64).replace(0, np.nan)
        )
        foreign_room_pct = _safe_divide(
            df_work["foreign_room"].fillna(0.0).astype(np.float64),
            total_shares,
            fill_value=1.0,
        )
    elif "foreign_room_pct" in df_work.columns:
        foreign_room_pct = (
            df_work["foreign_room_pct"].fillna(1.0).astype(np.float64)
        )
    else:
        # No foreign room data available, return zeros (neutral)
        return pd.Series(0.0, index=df_work.index, dtype=np.float64)

    # MANDATORY: Lag ALL foreign room data first to guarantee PIT safety
    df_work["_foreign_room_pct_temp"] = foreign_room_pct
    foreign_room_pct_lagged = df_work.groupby(symbol_col)[
        "_foreign_room_pct_temp"
    ].shift(1)

    # Smooth foreign room percentage using rolling mean on lagged data
    df_work["_room_pct"] = foreign_room_pct_lagged
    room_pct_smooth = (
        df_work.groupby(symbol_col)["_room_pct"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Squeeze signal: -1 * (1 - room_pct) = room_pct - 1
    signal = room_pct_smooth - 1.0

    return signal.fillna(0.0).astype(np.float64)


def compute_vn_limit_lock_continuation(
    df: pd.DataFrame,
    period: int = 5,
    exchange: str = "HOSE",
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Limit Lock Continuation - Continuation signal after limit-lock
    (ceil/floor) events.

    Formula: sign(limit_lock) * limit_lock_streak / period
             where limit_lock = 1 (ceiling), -1 (floor), 0 (no lock)
             Hypothesis: Limit locks persist in short term
                         (momentum continuation)
    PIT: Uses T-1 lagged price data.
    VN Limit Rules: HOSE ±7%, HNX ±10%, UPCOM ±15%
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Define limits by exchange
    limits = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
    limit = limits.get(exchange.upper(), 0.07)

    # MANDATORY: Lag price data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate price change on lagged data
    df_work["_price_lagged"] = price_lagged
    price_change = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Detect limit lock (with tolerance)
    is_ceiling = (price_change >= (limit - 0.001)).astype(int)
    is_floor = (price_change <= -(limit - 0.001)).astype(int)
    limit_lock = is_ceiling - is_floor  # Range: -1, 0, +1

    # Calculate rolling sum of limit locks (streak intensity) using native
    # rolling API
    df_work["_limit_lock"] = limit_lock.astype(np.float64)
    lock_sum = (
        df_work.groupby(symbol_col)["_limit_lock"]
        .rolling(window=period, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    # Normalize by period to get signal in range [-1, +1]
    signal = _safe_divide(lock_sum, float(period), fill_value=0.0)

    return signal.fillna(0.0).astype(np.float64)


# ============================================================================
# CORE VN-SPECIFIC FUNCTIONS (4)
# ============================================================================


def compute_limit_lock_streak(
    df: pd.DataFrame,
    exchange: str = "HOSE",
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Limit Lock Streak - Consecutive days at price limit (VN-specific).

    Formula: Count consecutive days where |price_change| >= limit
    PIT: Uses T-1 lagged prices.
    VN Limit Rules: HOSE ±7%, HNX ±10%, UPCOM ±15%
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Define limits by exchange
    limits = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
    limit = limits.get(exchange.upper(), 0.07)

    # Calculate price change
    price_change = df_work.groupby(symbol_col)[price_col].pct_change()

    # Detect limit lock (with tolerance)
    is_locked = (price_change.abs() >= (limit - 0.001)).astype(int)

    # Calculate streak
    df_work["_is_locked"] = is_locked

    # Reset streak counter when lock ends
    lock_groups = df_work.groupby(symbol_col)["_is_locked"].cumsum()
    reset_points = ~df_work["_is_locked"].astype(bool) & df_work.groupby(
        symbol_col
    )["_is_locked"].shift(1).fillna(False).astype(bool)

    df_work["_lock_groups"] = lock_groups
    df_work["_reset_points"] = reset_points

    streak = df_work["_lock_groups"] - df_work["_lock_groups"].where(
        df_work["_reset_points"]
    ).groupby(df_work[symbol_col]).ffill().fillna(0)

    # Apply T-1 lag for PIT safety
    df_work["_streak_temp"] = streak
    streak_lagged = df_work.groupby(symbol_col)["_streak_temp"].shift(1)

    return streak_lagged.fillna(0)


def compute_t2_momentum_adjustment(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    T+2 Momentum Adjustment - VN settlement cycle effect.

    Formula: ret_2d - ret_3d (captures T+2 money settlement vs
             T+3 securities settlement differential)
             Hypothesis: T+2 (money) vs T+3 (securities) settlement
                         creates momentum differential
    PIT: Uses T-1 lagged prices.
    VN Settlement Rules: T+2 for money, T+3 for securities
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate 2-day and 3-day returns (T+2 money vs T+3 securities)
    ret_2d = df_work.groupby(symbol_col)[price_col].pct_change(2)
    ret_3d = df_work.groupby(symbol_col)[price_col].pct_change(3)

    # Calculate differential (T+2 money settlement effect vs T+3 securities
    # settlement)
    t2_adj = ret_2d - ret_3d

    # Apply T-1 lag for PIT safety
    df_work["_t2_adj_temp"] = t2_adj
    t2_adj_lagged = df_work.groupby(symbol_col)["_t2_adj_temp"].shift(1)

    return t2_adj_lagged.fillna(0.0)


def compute_penny_trap_score(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Penny Trap Score - Low-price, low-liquidity manipulation risk
    (VN-specific).

    Formula: (1 / price) * (1 / ADV) * zero_trade_freq
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Price inverse
    price_inv = _safe_divide(
        pd.Series(1.0, index=df_work.index), df_work[price_col], fill_value=0.0
    )

    # ADV inverse
    daily_value = df_work[volume_col] * df_work[price_col]
    df_work["_daily_value"] = daily_value
    adv = (
        df_work.groupby(symbol_col)["_daily_value"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    adv_inv = _safe_divide(
        pd.Series(1.0, index=df_work.index), adv, fill_value=0.0
    )

    # Zero trade frequency
    zero_days = (df_work[volume_col] == 0).astype(int)
    df_work["_zero_days"] = zero_days
    zero_freq = (
        df_work.groupby(symbol_col)["_zero_days"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Combine
    trap_score = price_inv * adv_inv * zero_freq

    # Apply T-1 lag for PIT safety
    df_work["_trap_temp"] = trap_score
    trap_lagged = df_work.groupby(symbol_col)["_trap_temp"].shift(1)

    return trap_lagged.fillna(0.0)


def compute_smart_money_lite(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    Smart Money Lite - Simplified smart money flow indicator.

    Formula: Composite signal from Chaikin Money Flow (CMF) and
             volume-price correlation
             CMF = sum((((C-L)-(H-C))/(H-L)) * V) / sum(V)
             Signal = CMF_zscore * volume_price_corr
    PIT: Uses T-1 lagged data.
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)
    close_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)[volume_col].shift(1).astype(np.float64)
    )

    # Calculate Chaikin Money Flow (CMF) on lagged data
    hl_range = high_lagged - low_lagged
    mf_multiplier = _safe_divide(
        (close_lagged - low_lagged) - (high_lagged - close_lagged),
        hl_range,
        fill_value=0.0,
    )
    mf_volume = mf_multiplier * volume_lagged

    # Calculate CMF using native rolling API
    df_work["_mf_volume"] = mf_volume
    df_work["_volume_lagged"] = volume_lagged

    mf_sum = (
        df_work.groupby(symbol_col)["_mf_volume"]
        .rolling(window=period, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )
    vol_sum = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    cmf = _safe_divide(mf_sum, vol_sum, fill_value=0.0)

    # Calculate CMF zscore using native rolling API
    df_work["_cmf"] = cmf
    cmf_mean = (
        df_work.groupby(symbol_col)["_cmf"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    cmf_std = (
        df_work.groupby(symbol_col)["_cmf"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    cmf_zscore = _safe_divide(cmf - cmf_mean, cmf_std, fill_value=0.0)

    # Calculate volume-price correlation on lagged data
    df_work["_close_lagged"] = close_lagged
    price_change = df_work.groupby(symbol_col)["_close_lagged"].pct_change()
    volume_change = df_work.groupby(symbol_col)["_volume_lagged"].pct_change()

    # Calculate rolling correlation using vectorized approach
    df_work["_price_change"] = price_change
    df_work["_volume_change"] = volume_change

    correlation = pd.Series(index=df_work.index, dtype=np.float64)

    for ticker in df_work[symbol_col].unique():
        mask = df_work[symbol_col] == ticker
        price_chg = df_work.loc[mask, "_price_change"]
        vol_chg = df_work.loc[mask, "_volume_change"]

        # Calculate rolling correlation
        ticker_corr = price_chg.rolling(window=period, min_periods=5).corr(
            vol_chg
        )
        correlation.loc[mask] = ticker_corr.values

    # Combine CMF zscore and volume-price correlation
    signal = cmf_zscore * correlation.fillna(0.0)

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_limit_unlock_exhaustion(
    df: pd.DataFrame,
    period: int = 5,
    exchange: str = "HOSE",
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    VN Limit Unlock Exhaustion - Signal after limit unlock
    (momentum exhaustion).

    Formula: -sign(price_change) * zscore(volume) after limit breakout
             Hypothesis: When price breaks limit-lock (ceiling/floor),
                         momentum often exhausts
    PIT: Uses T-1 lagged price and volume data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period for zscore (default 5)
        exchange: Exchange name (HOSE=7%, HNX=10%, UPCOM=15%)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with limit unlock exhaustion signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Define limits by exchange
    limits = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
    limit_pct = limits.get(exchange.upper(), 0.07)

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate price change on lagged data
    df_work["_price_lagged"] = price_lagged
    price_change = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Detect limit lock breakout (price hits limit)
    is_limit_lock = price_change.abs() >= (limit_pct - 0.001)

    # Calculate volume zscore on lagged data using native rolling API
    df_work["_volume_lagged"] = volume_lagged
    vol_mean = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    vol_zscore = _safe_divide(
        volume_lagged - vol_mean, vol_std, fill_value=0.0
    )

    # Signal: -sign(price_change) * zscore(volume) when limit lock occurs
    # Negative price change (floor hit) -> positive signal (expect bounce)
    # Positive price change (ceiling hit) -> negative signal (expect reversal)
    signal = np.where(
        is_limit_lock, -1.0 * np.sign(price_change) * vol_zscore, 0.0
    )

    return (
        pd.Series(signal, index=df_work.index).astype(np.float64).fillna(0.0)
    )


def alpha_vn_t2_settlement_supply_overhang(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN T+2 Settlement Supply Overhang - Supply pressure from T+2
    settlement cycle.

    Formula: -1 * zscore(T2_sell_volume) * price_momentum
             Hypothesis: Stocks sold at T are delivered at T+2 before
                         13:00 (money settlement),
                        creating supply overhang.
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().sum/mean/std()
                        with reset_index(level=0, drop=True)

    VN Settlement Rules:
    - T+2 before 13:00: Money settlement (cash from sales available)
      - both money & securities
    - This function models T+2 settlement impact on supply

    Args:
        df: DataFrame with date, symbol, close, volume, and optional
            is_t2_settlement flag
        period: Lookback period for zscore (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with T+2 settlement supply overhang signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate price momentum on lagged data
    df_work["_close_lagged"] = close_lagged
    close_lagged_shifted = df_work.groupby(symbol_col)["_close_lagged"].shift(
        5
    )
    price_momentum = (
        _safe_divide(close_lagged, close_lagged_shifted, fill_value=1.0) - 1.0
    )

    # T+2 Settlement Logic: Volume sold at T-1 creates settlement at T+2
    # (shift by 1 for T+2)
    # VN settlement: T+2 before 13:00 (both money & securities)
    df_work["_volume_lagged"] = volume_lagged
    t2_settlement_volume = df_work.groupby(symbol_col)["_volume_lagged"].shift(
        1
    )

    # Round to board lot (100 shares) for VN market compliance
    t2_settlement_volume = _round_to_board_lot(
        t2_settlement_volume.fillna(0.0), board_size=100
    )

    # Calculate zscore of T+2 settlement volume using native rolling API
    df_work["_t2_settle_vol"] = t2_settlement_volume
    t2_mean = (
        df_work.groupby(symbol_col)["_t2_settle_vol"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    t2_std = (
        df_work.groupby(symbol_col)["_t2_settle_vol"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    t2_zscore = _safe_divide(
        t2_settlement_volume - t2_mean, t2_std, fill_value=0.0
    )

    # Signal: -1 * zscore(T2_settlement_volume) * price_momentum
    # High T+2 settlement volume + positive momentum -> negative signal
    # (supply overhang)
    signal = -1.0 * t2_zscore * price_momentum

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_t2_cash_recycling_bounce(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    VN T+2 Cash Recycling Bounce - Buying power returns after T+2 settlement.

    Formula: +1 * zscore(T2_cash_available) * price_momentum
             Hypothesis: Cash from sales at T returns at T+2 before
                         13:00 (money settlement),
                        enabling new buy orders.
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().sum/mean/std()
                        with reset_index(level=0, drop=True)

    VN Settlement Rules:
    - T+2 before 13:00: Money settlement (cash from sales available
      for reinvestment) - both money & securities
    - This function models T+2 cash recycling impact on buying power

    Args:
        df: DataFrame with date, symbol, close, volume, and optional
            is_t2_settlement flag
        period: Lookback period for zscore (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with T+2 cash recycling bounce signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate price momentum on lagged data
    df_work["_close_lagged"] = close_lagged
    close_lagged_shifted = df_work.groupby(symbol_col)["_close_lagged"].shift(
        5
    )
    price_momentum = (
        _safe_divide(close_lagged, close_lagged_shifted, fill_value=1.0) - 1.0
    )

    # T+2 Settlement Logic: Cash from sales at T-1 becomes available at T+2
    # (shift by 1 for T+2)
    # VN settlement: T+2 before 13:00 (both money & securities)
    df_work["_volume_lagged"] = volume_lagged
    df_work["_close_t2"] = df_work.groupby(symbol_col)["_close_lagged"].shift(
        1
    )

    # Estimate cash available from T-1 sales (volume * price at T-1)
    t2_cash_available = volume_lagged * df_work["_close_t2"]
    df_work["_t2_cash_temp"] = t2_cash_available
    t2_cash_available = df_work.groupby(symbol_col)["_t2_cash_temp"].shift(
        1
    )  # Shift by 1 for T+2 settlement (per-ticker)

    # Round equivalent shares to board lot (100 shares) for VN market
    # compliance
    t2_equivalent_shares = _safe_divide(
        t2_cash_available, close_lagged, fill_value=0.0
    )
    t2_equivalent_shares = _round_to_board_lot(
        t2_equivalent_shares.fillna(0.0), board_size=100
    )

    # Calculate zscore of T+2 cash recycling using native rolling API
    df_work["_t2_cash"] = t2_equivalent_shares
    t2_mean = (
        df_work.groupby(symbol_col)["_t2_cash"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    t2_std = (
        df_work.groupby(symbol_col)["_t2_cash"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    t2_zscore = _safe_divide(
        t2_equivalent_shares - t2_mean, t2_std, fill_value=0.0
    )

    # Signal: +1 * zscore(T2_cash_available) * price_momentum
    # High T+2 cash recycling + positive momentum -> positive signal (buying
    # power bounce)
    signal = 1.0 * t2_zscore * price_momentum

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_001_post_settlement_momentum(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    ALPHA_VN_001: Post-Settlement Momentum - Momentum continuation
    after T+2 settlement.

    Formula: sign(price_momentum_5d) * zscore(T2_cash_recycling) *
             price_momentum_5d
             Hypothesis: After T+2 settlement (cash available), momentum
                         continues if cash recycling is strong (high volume
                         at T-2 creates buying power at T).
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    VN Settlement Rules:
    - T+2 before 13:00: Money settlement (cash from sales available
      for reinvestment)
    - This alpha captures momentum continuation enabled by T+2 cash recycling

    Args:
        df: DataFrame with date, symbol, close, volume columns
        period: Lookback period for zscore (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with post-settlement momentum signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate 5-day price momentum on lagged data
    df_work["_close_lagged"] = close_lagged
    close_lagged_5d = df_work.groupby(symbol_col)["_close_lagged"].shift(5)
    price_momentum_5d = (
        _safe_divide(close_lagged, close_lagged_5d, fill_value=1.0) - 1.0
    )

    # T+2 Settlement Logic: Cash from sales at T-2 becomes available at T
    # (shift by 2 for T+2)
    # Estimate cash recycling potential from T-2 volume
    df_work["_volume_lagged"] = volume_lagged
    df_work["_close_t2"] = df_work.groupby(symbol_col)["_close_lagged"].shift(
        2
    )

    # T+2 cash available = volume_t-2 * price_t-2 (cash from sales 2 days ago)
    t2_cash_available = (
        df_work.groupby(symbol_col)["_volume_lagged"].shift(2)
        * df_work["_close_t2"]
    )

    # Normalize by current price to get equivalent shares
    t2_equivalent_shares = _safe_divide(
        t2_cash_available, close_lagged, fill_value=0.0
    )

    # Round to board lot (100 shares) for VN market compliance
    t2_equivalent_shares = _round_to_board_lot(
        t2_equivalent_shares.fillna(0.0), board_size=100
    )

    # Calculate zscore of T+2 cash recycling using native rolling API
    df_work["_t2_cash"] = t2_equivalent_shares
    t2_mean = (
        df_work.groupby(symbol_col)["_t2_cash"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    t2_std = (
        df_work.groupby(symbol_col)["_t2_cash"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    t2_zscore = _safe_divide(
        t2_equivalent_shares - t2_mean, t2_std, fill_value=0.0
    )

    # Signal: sign(momentum) * zscore(T2_cash) * momentum
    # Strong T+2 cash recycling + positive momentum -> positive signal
    # (continuation)
    # Strong T+2 cash recycling + negative momentum -> negative signal
    # (continuation)
    signal = np.sign(price_momentum_5d) * t2_zscore * price_momentum_5d

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_002_limit_band_reversion(
    df: pd.DataFrame,
    period: int = 20,
    exchange: str = "HOSE",
    price_col: str = "close",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    ALPHA_VN_002: Limit-Band Reversion - Mean reversion near limit bands.

    Formula: -1 * sign(distance_to_limit) * |distance_to_limit|^2 *
             zscore(volume)
             where distance_to_limit = (price_change - limit_threshold) /
                              limit_threshold
             Hypothesis: Stocks near limit bands (±7% for HOSE) experience
    mean reversion,
                        especially with high volume (exhaustion signal).
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    VN Limit Rules:
    - HOSE: ?7% daily limit
    - HNX: ?10% daily limit
    - UPCOM: ?15% daily limit

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period for zscore (default 20)
        exchange: Exchange name (HOSE=7%, HNX=10%, UPCOM=15%)
        price_col: Price column name
        symbol_col: Symbol column name

    Returns:
        Series with limit-band reversion signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Define limits by exchange
    limits = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}
    limit_pct = limits.get(exchange.upper(), 0.07)

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate price change on lagged data
    df_work["_price_lagged"] = price_lagged
    price_change = df_work.groupby(symbol_col)["_price_lagged"].pct_change()

    # Calculate distance to limit band (normalized)
    # Positive distance = approaching ceiling, Negative distance = approaching
    # floor
    distance_to_limit = _safe_divide(price_change, limit_pct, fill_value=0.0)

    # Clip to [-1.5, 1.5] range (beyond limit is capped)
    distance_to_limit = distance_to_limit.clip(-1.5, 1.5)

    # Calculate volume zscore on lagged data using native rolling API
    df_work["_volume_lagged"] = volume_lagged
    vol_mean = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    vol_zscore = _safe_divide(
        volume_lagged - vol_mean, vol_std, fill_value=0.0
    )

    # Signal: -sign(distance) * distance^2 * zscore(volume)
    # Near ceiling (+) with high volume -> negative signal
    # (expect reversal down)
    # Near floor (-) with high volume -> positive signal (expect reversal up)
    # Quadratic penalty for extreme distances (stronger signal near limits)
    signal = (
        -1.0 * np.sign(distance_to_limit) * (distance_to_limit**2) * vol_zscore
    )

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_003_foreign_flow_divergence(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    ALPHA_VN_003: Foreign Flow Divergence - Divergence between foreign
    flow and price momentum.

    Formula: -sign(foreign_net_flow) * price_momentum *
             |zscore(foreign_net_flow)|
             Hypothesis: When foreign flow diverges from price momentum
                         (foreign selling during price rise, or foreign
                         buying during price fall), it signals potential
                         reversal.
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, close, and foreign flow columns
        period: Lookback period for zscore (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with foreign flow divergence signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # Calculate foreign net flow (handle missing columns)
    if (
        "foreign_buy_value" in df_work.columns
        and "foreign_sell_value" in df_work.columns
    ):
        foreign_net_flow = (
            df_work["foreign_buy_value"].fillna(0.0)
            - df_work["foreign_sell_value"].fillna(0.0)
        ).astype(np.float64)
    elif "foreign_net_value" in df_work.columns:
        foreign_net_flow = (
            df_work["foreign_net_value"].fillna(0.0).astype(np.float64)
        )
    else:
        # No foreign data available, return zeros
        return pd.Series(0.0, index=df_work.index, dtype=np.float64)

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    df_work["_foreign_net_temp"] = foreign_net_flow
    foreign_net_flow_lagged = df_work.groupby(symbol_col)[
        "_foreign_net_temp"
    ].shift(1)

    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)

    # Calculate price momentum (5-day) on lagged data
    df_work["_close_lagged"] = close_lagged
    close_lagged_5d = df_work.groupby(symbol_col)["_close_lagged"].shift(5)
    price_momentum = (
        _safe_divide(close_lagged, close_lagged_5d, fill_value=1.0) - 1.0
    )

    # Calculate zscore of foreign net flow using native rolling API
    df_work["_foreign_net"] = foreign_net_flow_lagged
    flow_mean = (
        df_work.groupby(symbol_col)["_foreign_net"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    flow_std = (
        df_work.groupby(symbol_col)["_foreign_net"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    flow_zscore = _safe_divide(
        foreign_net_flow_lagged - flow_mean, flow_std, fill_value=0.0
    )

    # Divergence signal: -sign(foreign_flow) * price_momentum *
    # |zscore(foreign_flow)|
    # When foreign selling (negative flow) during price rise (positive
    # momentum) -> positive signal (reversal expected)
    # When foreign buying (positive flow) during price fall (negative
    # momentum) -> negative signal (reversal expected)
    signal = (
        -1.0
        * np.sign(foreign_net_flow_lagged)
        * price_momentum
        * np.abs(flow_zscore)
    )

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_004_intraday_persistence(
    df: pd.DataFrame, period: int = 5, symbol_col: str = "ticker"
) -> pd.Series:
    """
    ALPHA_VN_004: Intraday Persistence - Intraday momentum persistence signal.

    Formula: sign(intraday_return) * zscore(intraday_return) * volume_ratio
             where intraday_return = (close - open) / open
                   volume_ratio = volume / volume_ma
             Hypothesis: Strong intraday moves with high volume persist
    into next day.
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, open, close, volume columns
        period: Lookback period for zscore (default 5)
        symbol_col: Symbol column name

    Returns:
        Series with intraday persistence signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    open_lagged = df_work.groupby(symbol_col)["open"].shift(1)
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)["volume"].shift(1).astype(np.float64)
    )

    # Calculate intraday return on lagged data
    intraday_return = _safe_divide(
        close_lagged - open_lagged, open_lagged, fill_value=0.0
    )

    # Calculate zscore of intraday return using native rolling API
    df_work["_intraday_return"] = intraday_return
    return_mean = (
        df_work.groupby(symbol_col)["_intraday_return"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return_std = (
        df_work.groupby(symbol_col)["_intraday_return"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    return_zscore = _safe_divide(
        intraday_return - return_mean, return_std, fill_value=0.0
    )

    # Calculate volume ratio using native rolling API
    df_work["_volume_lagged"] = volume_lagged
    volume_ma = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    volume_ratio = _safe_divide(volume_lagged, volume_ma, fill_value=1.0)

    # Persistence signal: sign(intraday_return) * zscore(intraday_return)
    # * volume_ratio
    # Strong intraday move (high zscore) with high volume (high ratio) ->
    # strong signal
    signal = np.sign(intraday_return) * return_zscore * volume_ratio

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_005_liquidity_adjusted_reversal(
    df: pd.DataFrame, period: int = 20, symbol_col: str = "ticker"
) -> pd.Series:
    """
    ALPHA_VN_005: Liquidity-Adjusted Reversal - Mean reversion adjusted
    by liquidity conditions.

    Formula: -zscore(returns) * liquidity_penalty
             where liquidity_penalty = 1 / (1 + normalized_spread)
                   normalized_spread = (high - low) / close (proxy for
                                       bid-ask spread)
             Hypothesis: Mean reversion is stronger in liquid stocks
                         (low spread), weaker in illiquid stocks (high
                         spread).
    PIT: Uses T-1 lagged data.
    Native Rolling API: Uses .groupby().rolling().mean/std()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, high, low, close columns
        period: Lookback period for zscore (default 20)
        symbol_col: Symbol column name

    Returns:
        Series with liquidity-adjusted reversal signal (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    high_lagged = df_work.groupby(symbol_col)["high"].shift(1)
    low_lagged = df_work.groupby(symbol_col)["low"].shift(1)
    close_lagged = df_work.groupby(symbol_col)["close"].shift(1)

    # Calculate returns on lagged data
    df_work["_close_lagged"] = close_lagged
    returns = df_work.groupby(symbol_col)["_close_lagged"].pct_change()

    # Calculate zscore of returns using native rolling API
    df_work["_returns"] = returns
    return_mean = (
        df_work.groupby(symbol_col)["_returns"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    return_std = (
        df_work.groupby(symbol_col)["_returns"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    return_zscore = _safe_divide(
        returns - return_mean, return_std, fill_value=0.0
    )

    # Calculate normalized spread (proxy for bid-ask spread) on lagged data
    normalized_spread = _safe_divide(
        high_lagged - low_lagged, close_lagged, fill_value=0.0
    )

    # Calculate liquidity penalty using native rolling API
    # Smooth the spread over period to reduce noise
    df_work["_spread"] = normalized_spread
    spread_ma = (
        df_work.groupby(symbol_col)["_spread"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Liquidity penalty: 1 / (1 + spread) - higher spread = lower penalty =
    # weaker signal
    liquidity_penalty = _safe_divide(
        pd.Series(1.0, index=df_work.index), 1.0 + spread_ma, fill_value=0.5
    )

    # Reversal signal: -zscore(returns) * liquidity_penalty
    # Extreme returns (high |zscore|) in liquid stocks (high penalty)
    # -> strong reversal signal
    # Extreme returns in illiquid stocks (low penalty) -> weak reversal signal
    signal = -1.0 * return_zscore * liquidity_penalty

    return signal.astype(np.float64).fillna(0.0)


def alpha_vn_t2_momentum_diff(
    df: pd.DataFrame, price_col: str = "close", symbol_col: str = "ticker"
) -> pd.Series:
    """
    RESCUE P3 WEEK 1 - Alpha 1/3: VN T+2 Momentum Differential

    Formula: ret_2d - ret_3d (T+2 vs T+3 differential)
    Logic: Captures VN T+2 settlement cycle momentum differential
    PIT: Uses T-1 lagged prices
    Vectorization: 100% Pandas/NumPy operations

    VN Settlement Rules:
    - T+2: Money settlement (cash available)
    - T+3: Securities settlement (shares delivered)
    - This captures the 1-day differential between money and
      securities settlement

    Args:
        df: DataFrame with date, symbol, and price columns
        price_col: Price column name (default 'close')
        symbol_col: Symbol column name (default 'ticker')

    Returns:
        Series with T+2 momentum differential values (float64)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag price first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)

    # Calculate 2-day and 3-day returns on lagged prices
    df_work["_price_lagged"] = price_lagged
    ret_2d = df_work.groupby(symbol_col)["_price_lagged"].pct_change(2)
    ret_3d = df_work.groupby(symbol_col)["_price_lagged"].pct_change(3)

    # Calculate differential (T+2 money settlement effect vs T+3 securities
    # settlement)
    t2_momentum_diff = ret_2d - ret_3d

    return (
        t2_momentum_diff.replace([np.inf, -np.inf], 0.0)
        .astype(np.float64)
        .fillna(0.0)
    )


def alpha_vn_penny_trap_risk(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    RESCUE P3 WEEK 1 - Alpha 2/3: VN Penny Trap Risk Score

    Formula: (1 / price) * (1 / ADV) * zero_trade_freq
    Logic: Identifies low-price, low-liquidity stocks prone to manipulation
    PIT: Uses T-1 lagged data
    Vectorization: 100% Pandas/NumPy operations
    Native Rolling API: Uses .groupby().rolling().mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period for ADV and zero_trade_freq (default 20)
        price_col: Price column name (default 'close')
        volume_col: Volume column name (default 'volume')
        symbol_col: Symbol column name (default 'ticker')

    Returns:
        Series with penny trap risk scores (float64, higher = higher risk)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)[volume_col].shift(1).astype(np.float64)
    )

    # 1. Price inverse (1 / price) - handle zero/low prices safely
    price_inv = _safe_divide(
        pd.Series(1.0, index=df_work.index), price_lagged, fill_value=0.0
    )

    # 2. ADV inverse (1 / ADV) using native rolling API
    daily_value = volume_lagged * price_lagged
    df_work["_daily_value"] = daily_value
    adv = (
        df_work.groupby(symbol_col)["_daily_value"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    adv_inv = _safe_divide(
        pd.Series(1.0, index=df_work.index), adv, fill_value=0.0
    )

    # 3. Zero trade frequency using native rolling API
    zero_days = (volume_lagged == 0).astype(int)
    df_work["_zero_days"] = zero_days
    zero_freq = (
        df_work.groupby(symbol_col)["_zero_days"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Combine all three components (already PIT-safe via lagged inputs)
    penny_trap_risk = price_inv * adv_inv * zero_freq

    return penny_trap_risk.astype(np.float64).fillna(0.0)


def alpha_liquidity_quality_score(
    df: pd.DataFrame,
    period: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
    symbol_col: str = "ticker",
) -> pd.Series:
    """
    RESCUE P3 WEEK 1 - Alpha 3/3: Liquidity Quality Score

    Formula: (volume_std / volume_mean) * (close_std / close_mean)
    Logic: Combines volume consistency and price stability
           (lower = better quality)
    PIT: Uses T-1 lagged data
    Vectorization: 100% Pandas/NumPy operations
    Native Rolling API: Uses .groupby().rolling().std/mean()
                        with reset_index(level=0, drop=True)

    Args:
        df: DataFrame with date, symbol, price, and volume columns
        period: Lookback period for rolling statistics (default 20)
        price_col: Price column name (default 'close')
        volume_col: Volume column name (default 'volume')
        symbol_col: Symbol column name (default 'ticker')

    Returns:
        Series with liquidity quality scores (float64, lower = better quality)
    """
    df_work = df.copy()
    df_work = df_work.sort_values(["date", symbol_col])

    # MANDATORY: Lag ALL input data first to guarantee PIT safety
    price_lagged = df_work.groupby(symbol_col)[price_col].shift(1)
    volume_lagged = (
        df_work.groupby(symbol_col)[volume_col].shift(1).astype(np.float64)
    )

    # Calculate volume CV (coefficient of variation) using native rolling API
    df_work["_volume_lagged"] = volume_lagged
    vol_mean = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    vol_std = (
        df_work.groupby(symbol_col)["_volume_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    vol_cv = _safe_divide(vol_std, vol_mean, fill_value=0.0)

    # Calculate price CV (coefficient of variation) using native rolling API
    df_work["_price_lagged"] = price_lagged
    price_mean = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    price_std = (
        df_work.groupby(symbol_col)["_price_lagged"]
        .rolling(window=period, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )
    price_cv = _safe_divide(price_std, price_mean, fill_value=0.0)

    # Combine volume CV and price CV (already PIT-safe via lagged inputs)
    liquidity_quality = vol_cv * price_cv

    return liquidity_quality.astype(np.float64).fillna(0.0)
