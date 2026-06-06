"""
OMEGA_QUANT Smart Money Overlay for Pipeline A
Computes smart money signals from daily OHLCV (no tick data needed).

Signals:
- CMF (Chaikin Money Flow 20d)
- VWAP deviation
- Volume-Price correlation
- OBV Rate of Change

Flag: --smart-money
Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All indicators use rolling past data only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_smart_money_features(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Compute smart money features from OHLCV panel.

    Args:
        panel: MultiIndex [date, symbol] with open/high/low/close/volume

    Returns:
        Panel with smart money features added.
    """
    result = panel.copy()

    # 1. Chaikin Money Flow (CMF 20d)
    # CMF = sum(MFV, 20) / sum(volume, 20)
    # MFV = ((close - low) - (high - close)) / (high - low) * volume
    hl_range = (panel['high'] - panel['low']).replace(0, np.nan)
    mf_multiplier = ((panel['close'] - panel['low']) - (panel['high'] - panel['close'])) / hl_range
    mf_volume = mf_multiplier * panel['volume']
    result['cmf_20'] = (
        mf_volume.groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=10).sum()) /
        panel['volume'].groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=10).sum())
    ).fillna(0)

    # 2. VWAP deviation (proxy: typical_price vs rolling VWAP)
    typical_price = (panel['high'] + panel['low'] + panel['close']) / 3
    vwap_20 = (
        (typical_price * panel['volume']).groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=10).sum()) /
        panel['volume'].groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=10).sum())
    )
    result['vwap_deviation'] = ((panel['close'] - vwap_20) / vwap_20).fillna(0)

    # 3. Volume-Price Correlation (20d rolling)
    result['vol_price_corr'] = panel.groupby(level='symbol').apply(
        lambda g: g['close'].rolling(20, min_periods=10).corr(g['volume'])
    ).droplevel(0).fillna(0)

    # 4. OBV Rate of Change (10d)
    price_change = panel.groupby(level='symbol')['close'].diff()
    obv_direction = np.sign(price_change).fillna(0)
    obv = (obv_direction * panel['volume']).groupby(level='symbol').cumsum()
    obv_ma = obv.groupby(level='symbol').transform(lambda x: x.rolling(10, min_periods=5).mean())
    obv_prev = obv_ma.groupby(level='symbol').shift(10)
    result['obv_roc'] = ((obv_ma - obv_prev) / obv_prev.abs().replace(0, 1)).fillna(0)

    # 5. Smart Money Composite Score
    # Normalize each signal to [-1, 1] range and combine
    cmf_norm = result['cmf_20'].clip(-1, 1)
    vwap_norm = (result['vwap_deviation'] * 20).clip(-1, 1)  # Scale ~5% deviation to [-1,1]
    vpc_norm = result['vol_price_corr'].clip(-1, 1)
    obv_norm = result['obv_roc'].clip(-1, 1)

    result['smart_money_score'] = (cmf_norm * 0.3 + vwap_norm * 0.25 + vpc_norm * 0.25 + obv_norm * 0.2)

    logger.info("Smart money features: CMF, VWAP dev, Vol-Price corr, OBV RoC, composite score")
    return result


def apply_smart_money_overlay(
    daily_weights: pd.DataFrame,
    smart_money_scores: pd.Series,
    boost_scale: float = 0.25,
) -> pd.DataFrame:
    """
    Apply smart money boost to portfolio weights.
    Positive score = smart money buying = boost weight.
    Negative score = smart money selling = reduce weight.

    Args:
        daily_weights: T x N weights
        smart_money_scores: MultiIndex [date, symbol] smart money composite score
        boost_scale: Max boost/reduction (0.25 = +/-25%)

    Returns:
        Boosted weights.
    """
    # Unstack scores to match weights shape
    scores_unstacked = smart_money_scores.unstack(level='symbol')

    # Align
    common_dates = daily_weights.index.intersection(scores_unstacked.index)
    common_cols = daily_weights.columns.intersection(scores_unstacked.columns)

    if len(common_dates) == 0 or len(common_cols) == 0:
        return daily_weights

    scores_aligned = scores_unstacked.loc[common_dates, common_cols].fillna(0)

    # Boost: weight * (1 + score * boost_scale)
    boost_matrix = 1.0 + scores_aligned * boost_scale
    boost_matrix = boost_matrix.clip(1.0 - boost_scale, 1.0 + boost_scale)

    adjusted = daily_weights.copy()
    adjusted.loc[common_dates, common_cols] = adjusted.loc[common_dates, common_cols] * boost_matrix

    # Re-normalize
    target_exposure = daily_weights.abs().sum(axis=1)
    current_exposure = adjusted.abs().sum(axis=1).replace(0, 1.0)
    adjusted = adjusted.mul(target_exposure / current_exposure, axis=0)

    logger.info("Smart money overlay: mean_boost=%.4f, boost_scale=%.2f",
                boost_matrix.mean().mean() - 1.0, boost_scale)
    return adjusted
