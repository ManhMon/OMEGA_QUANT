"""Phase 3.4 Alpha Discovery - Microstructure Alphas for T+3/T+5.

Version: v21.36-Phase34
Date: 2026-05-07

Targets short-term (T+3, T+5) alpha on VN equities via market
microstructure signals.  Every alpha enforces strict T-1 lag for
PIT compliance.  All operations are 100% vectorised
(Pandas / NumPy), no Python loops, no console output.

ALPHA INVENTORY (7 alphas):
  1. alpha_p34_volatility_compression_5      - Intraday range compression -> breakout predictor
  2. alpha_p34_volume_clock_acceleration_10   - Trade-time acceleration vs calendar-time
  3. alpha_p34_kyle_lambda_20                 - Price-impact coefficient (Kyle lambda)
  4. alpha_p34_tick_signed_volume_imbalance_5 - Tick-rule signed volume OFI
  5. alpha_p34_close_auction_drift_10         - Close-vs-VWAP drift (institutional signal)
  6. alpha_p34_liquidity_provision_ratio_10   - Passive vs aggressive volume ratio
  7. alpha_p34_micro_momentum_5_20            - Microstructure-weighted short-term momentum

COMPLIANCE:
  - PIT (Point-in-Time): All features use T-1 lagged data exclusively.
  - Vectorisation: 100% Pandas / NumPy; zero Python-level row loops.
  - Robustness: safe division, NaN / Inf clamping, graceful fallback.
  - Silent Mode: No print() / console output.
  - Full type annotations on public API.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger: logging.Logger = logging.getLogger(__name__)

PHASE34_ALPHA_COLUMNS: tuple[str, ...] = (
    "alpha_p34_volatility_compression_5",
    "alpha_p34_volume_clock_acceleration_10",
    "alpha_p34_kyle_lambda_20",
    "alpha_p34_tick_signed_volume_imbalance_5",
    "alpha_p34_close_auction_drift_10",
    "alpha_p34_liquidity_provision_ratio_10",
    "alpha_p34_micro_momentum_5_20",
)


def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    fill_value: float = 0.0,
) -> pd.Series:
    """Division with zero / NaN / Inf protection."""
    result: pd.Series = numerator / denominator
    result = result.replace([np.inf, -np.inf], np.nan).fillna(fill_value)
    return result.astype(np.float64)


def _rolling_mean(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    mp: int = min_periods if min_periods is not None else window
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .mean()
        .reset_index(level=0, drop=True)
    )


def _rolling_std(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    mp: int = min_periods if min_periods is not None else window
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .std()
        .reset_index(level=0, drop=True)
    )


def _rolling_sum(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    mp: int = min_periods if min_periods is not None else window
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .sum()
        .reset_index(level=0, drop=True)
    )


def _rolling_zscore(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: int = 5,
) -> pd.Series:
    mu: pd.Series = _rolling_mean(series, groups, window, min_periods=min_periods)
    sigma: pd.Series = _rolling_std(series, groups, window, min_periods=min_periods)
    return _safe_divide(series - mu, sigma, fill_value=0.0)


def compute_phase34_microstructure_alphas(
    df: pd.DataFrame,
    *,
    symbol_col: str = "ticker",
    date_col: str = "date",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.DataFrame:
    """Compute Phase 3.4 microstructure alphas (7 factors).

    All alphas enforce strict T-1 lag for PIT compliance.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV panel with *date_col* and *symbol_col*.
    symbol_col, date_col, open_col, high_col, low_col, close_col, volume_col :
        Column name overrides.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with 7 new ``alpha_p34_*`` columns appended.
    """
    df_work: pd.DataFrame = df.copy()
    df_work = df_work.sort_values([date_col, symbol_col]).reset_index(drop=True)

    symbols: pd.Series = df_work[symbol_col]

    open_lag: pd.Series = df_work.groupby(symbol_col)[open_col].shift(1).fillna(0.0).astype(np.float64)
    high_lag: pd.Series = df_work.groupby(symbol_col)[high_col].shift(1).fillna(0.0).astype(np.float64)
    low_lag: pd.Series = df_work.groupby(symbol_col)[low_col].shift(1).fillna(0.0).astype(np.float64)
    close_lag: pd.Series = df_work.groupby(symbol_col)[close_col].shift(1).fillna(0.0).astype(np.float64)
    volume_lag: pd.Series = df_work.groupby(symbol_col)[volume_col].shift(1).fillna(0.0).astype(np.float64)
    prev_close_lag: pd.Series = df_work.groupby(symbol_col)[close_col].shift(2).fillna(0.0).astype(np.float64)

    lagged_return: pd.Series = _safe_divide(
        close_lag - prev_close_lag, prev_close_lag.abs().clip(lower=1e-9)
    )
    value_lag: pd.Series = close_lag * volume_lag

    # ALPHA 1 - Intraday Volatility Compression (5-day)
    intraday_range: pd.Series = _safe_divide(
        high_lag - low_lag, close_lag.abs().clip(lower=1e-9)
    )
    range_ma20: pd.Series = _rolling_mean(intraday_range, symbols, 20, min_periods=5)
    compression_raw: pd.Series = _safe_divide(
        range_ma20 - intraday_range, range_ma20.abs().clip(lower=1e-9)
    )
    alpha_p34_volatility_compression_5: pd.Series = _rolling_mean(
        compression_raw, symbols, 5, min_periods=1
    ).clip(lower=-3.0, upper=3.0)

    # ALPHA 2 - Volume-Clock Acceleration (10-day)
    vol_ma5: pd.Series = _rolling_mean(volume_lag, symbols, 5, min_periods=1)
    vol_ma20: pd.Series = _rolling_mean(volume_lag, symbols, 20, min_periods=5)
    vol_acceleration_raw: pd.Series = _safe_divide(
        vol_ma5 - vol_ma20, vol_ma20.abs().clip(lower=1e-9)
    )
    alpha_p34_volume_clock_acceleration_10: pd.Series = _rolling_zscore(
        vol_acceleration_raw, symbols, 10, min_periods=3
    ).clip(lower=-5.0, upper=5.0)

    # ALPHA 3 - Kyle Lambda (20-day price impact coefficient)
    abs_return: pd.Series = lagged_return.abs()
    sqrt_dollar_vol: pd.Series = np.sqrt(value_lag.abs().clip(lower=1.0))
    kyle_raw: pd.Series = _safe_divide(abs_return, sqrt_dollar_vol)
    alpha_p34_kyle_lambda_20: pd.Series = -_rolling_zscore(
        kyle_raw, symbols, 20, min_periods=5
    ).clip(lower=-5.0, upper=5.0)

    # ALPHA 4 - Tick-Rule Signed Volume Imbalance (5-day OFI)
    buy_col_name: Optional[str] = None
    sell_col_name: Optional[str] = None
    for bcand, scand in [
        ("buy_volume", "sell_volume"),
        ("matched_buy_volume", "matched_sell_volume"),
        ("total_buy_volume", "total_sell_volume"),
    ]:
        if bcand in df_work.columns and scand in df_work.columns:
            buy_col_name = bcand
            sell_col_name = scand
            break

    if buy_col_name is not None and sell_col_name is not None:
        buy_lag_v: pd.Series = df_work.groupby(symbol_col)[buy_col_name].shift(1).fillna(0.0).astype(np.float64)
        sell_lag_v: pd.Series = df_work.groupby(symbol_col)[sell_col_name].shift(1).fillna(0.0).astype(np.float64)
        signed_vol: pd.Series = buy_lag_v - sell_lag_v
        total_vol: pd.Series = buy_lag_v + sell_lag_v
    else:
        signed_vol = np.sign(lagged_return.fillna(0.0)) * volume_lag
        total_vol = volume_lag

    ofi_5: pd.Series = _rolling_sum(signed_vol, symbols, 5, min_periods=1)
    total_5: pd.Series = _rolling_sum(total_vol, symbols, 5, min_periods=1)
    alpha_p34_tick_signed_volume_imbalance_5: pd.Series = _safe_divide(
        ofi_5, total_5.abs().clip(lower=1e-9)
    ).clip(lower=-1.0, upper=1.0)

    # ALPHA 5 - Close-Auction Drift (10-day)
    vwap_proxy: pd.Series = (high_lag + low_lag + close_lag) / 3.0
    close_drift_raw: pd.Series = _safe_divide(
        close_lag - vwap_proxy, vwap_proxy.abs().clip(lower=1e-9)
    )
    alpha_p34_close_auction_drift_10: pd.Series = _rolling_mean(
        close_drift_raw, symbols, 10, min_periods=3
    ).clip(lower=-1.0, upper=1.0)

    # ALPHA 6 - Liquidity Provision Ratio (10-day)
    body_size: pd.Series = (close_lag - open_lag).abs()
    total_range: pd.Series = (high_lag - low_lag).clip(lower=1e-9)
    wick_ratio: pd.Series = _safe_divide(total_range - body_size, total_range)
    alpha_p34_liquidity_provision_ratio_10: pd.Series = _rolling_zscore(
        wick_ratio, symbols, 10, min_periods=3
    ).clip(lower=-5.0, upper=5.0)

    # ALPHA 7 - Microstructure Momentum (5/20-day)
    close_lag_6: pd.Series = df_work.groupby(symbol_col)[close_col].shift(6).fillna(0.0).astype(np.float64)
    close_lag_21: pd.Series = df_work.groupby(symbol_col)[close_col].shift(21).fillna(0.0).astype(np.float64)
    ret_5: pd.Series = _safe_divide(
        close_lag - close_lag_6,
        close_lag_6.abs().clip(lower=1e-9),
    )
    ret_20: pd.Series = _safe_divide(
        close_lag - close_lag_21,
        close_lag_21.abs().clip(lower=1e-9),
    )
    vol_weight: pd.Series = vol_acceleration_raw.clip(lower=-2.0, upper=2.0) + 1.0
    micro_mom_raw: pd.Series = (ret_5 * vol_weight) - ret_20
    alpha_p34_micro_momentum_5_20: pd.Series = _rolling_zscore(
        micro_mom_raw, symbols, 10, min_periods=3
    ).clip(lower=-5.0, upper=5.0)

    # Assemble output
    df_out: pd.DataFrame = df_work.copy()
    alphas: dict[str, pd.Series] = {
        "alpha_p34_volatility_compression_5": alpha_p34_volatility_compression_5,
        "alpha_p34_volume_clock_acceleration_10": alpha_p34_volume_clock_acceleration_10,
        "alpha_p34_kyle_lambda_20": alpha_p34_kyle_lambda_20,
        "alpha_p34_tick_signed_volume_imbalance_5": alpha_p34_tick_signed_volume_imbalance_5,
        "alpha_p34_close_auction_drift_10": alpha_p34_close_auction_drift_10,
        "alpha_p34_liquidity_provision_ratio_10": alpha_p34_liquidity_provision_ratio_10,
        "alpha_p34_micro_momentum_5_20": alpha_p34_micro_momentum_5_20,
    }

    for name, values in alphas.items():
        df_out[name] = (
            values.reindex(df_out.index)
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(np.float64)
        )

    return df_out


def get_phase34_alpha_metadata() -> dict[str, dict[str, str]]:
    """Return metadata dict for all Phase 3.4 alphas."""
    return {
        "alpha_p34_volatility_compression_5": {
            "category": "Phase34 Microstructure",
            "description": "Intraday range compression vs 20d MA - breakout predictor (T+3/T+5)",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_volume_clock_acceleration_10": {
            "category": "Phase34 Microstructure",
            "description": "Volume-clock 5d/20d acceleration z-scored over 10d",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_kyle_lambda_20": {
            "category": "Phase34 Microstructure",
            "description": "Kyle price-impact coefficient (|ret|/sqrt($vol)) z-scored 20d",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_tick_signed_volume_imbalance_5": {
            "category": "Phase34 Microstructure",
            "description": "Tick-rule signed order-flow imbalance over 5 days",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_close_auction_drift_10": {
            "category": "Phase34 Microstructure",
            "description": "Close-vs-VWAP drift 10d MA - institutional accumulation signal",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_liquidity_provision_ratio_10": {
            "category": "Phase34 Microstructure",
            "description": "Wick-to-body ratio z-scored 10d - passive liquidity provision",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
        "alpha_p34_micro_momentum_5_20": {
            "category": "Phase34 Microstructure",
            "description": "Volume-weighted 5d vs 20d micro-momentum z-score",
            "source": "PHASE_3_4_ALPHA_DISCOVERY",
        },
    }
