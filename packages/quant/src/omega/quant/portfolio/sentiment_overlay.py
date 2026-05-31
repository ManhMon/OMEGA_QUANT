"""
OMEGA_QUANT Sentiment Overlay for Pipeline A
Lightweight sentiment proxy from OHLCV (no ViBERT needed for backtest).

For backtest: derives sentiment proxy from price-volume patterns:
- Gap-up on high volume = positive sentiment
- Gap-down on high volume = negative sentiment
- Consecutive up/down days = momentum sentiment

For live: can integrate vnstock news API (future enhancement).

Flag: --sentiment
Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All signals from past OHLCV only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_sentiment_proxy(panel: pd.DataFrame) -> pd.Series:
    """
    Compute sentiment proxy from OHLCV patterns.

    Combines:
    1. Gap sentiment (gap-up/down on volume)
    2. Streak sentiment (consecutive up/down days)
    3. Volume sentiment (unusual volume = news event proxy)

    Args:
        panel: MultiIndex [date, symbol] with OHLCV

    Returns:
        Series of sentiment scores [-1, 1] aligned with panel index.
    """
    # 1. Gap sentiment: (open - prev_close) / prev_close * volume_zscore
    prev_close = panel.groupby(level='symbol')['close'].shift(1)
    gap = (panel['open'] - prev_close) / prev_close.replace(0, np.nan)
    vol_ma = panel.groupby(level='symbol')['volume'].transform(lambda x: x.rolling(20, min_periods=5).mean())
    vol_zscore = (panel['volume'] - vol_ma) / vol_ma.replace(0, 1)
    gap_sentiment = (gap * vol_zscore.clip(-3, 3)).fillna(0)

    # 2. Streak sentiment: rolling sum of sign(returns) over 5 days / 5
    daily_ret = panel.groupby(level='symbol')['close'].pct_change()
    ret_sign = daily_ret.map(np.sign)
    streak = ret_sign.groupby(level='symbol').transform(lambda x: x.rolling(5, min_periods=3).sum()) / 5
    streak_sentiment = streak.fillna(0)

    # 3. Volume sentiment: high volume days = news proxy
    # Positive if price up + high volume, negative if price down + high volume
    vol_spike = (vol_zscore > 2.0).astype(float)
    vol_sentiment = vol_spike * daily_ret.map(np.sign)
    vol_sentiment_smooth = vol_sentiment.groupby(level='symbol').transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    ).fillna(0)

    # Composite sentiment score
    sentiment = (gap_sentiment * 0.3 + streak_sentiment * 0.4 + vol_sentiment_smooth * 0.3).clip(-1, 1)

    logger.info("Sentiment proxy: gap=%.4f, streak=%.4f, vol=%.4f (mean composite=%.4f)",
                gap_sentiment.mean(), streak_sentiment.mean(), vol_sentiment_smooth.mean(), sentiment.mean())
    return sentiment


def apply_sentiment_overlay(
    daily_weights: pd.DataFrame,
    sentiment_scores: pd.Series,
    boost_scale: float = 0.2,
) -> pd.DataFrame:
    """
    Apply sentiment boost to portfolio weights.

    Args:
        daily_weights: T x N weights
        sentiment_scores: MultiIndex [date, symbol] sentiment scores [-1, 1]
        boost_scale: Max boost (0.2 = +/-20%)

    Returns:
        Sentiment-adjusted weights.
    """
    scores_unstacked = sentiment_scores.unstack(level='symbol')

    common_dates = daily_weights.index.intersection(scores_unstacked.index)
    common_cols = daily_weights.columns.intersection(scores_unstacked.columns)

    if len(common_dates) == 0 or len(common_cols) == 0:
        return daily_weights

    scores_aligned = scores_unstacked.loc[common_dates, common_cols].fillna(0)
    boost_matrix = 1.0 + scores_aligned * boost_scale
    boost_matrix = boost_matrix.clip(1.0 - boost_scale, 1.0 + boost_scale)

    adjusted = daily_weights.copy()
    adjusted.loc[common_dates, common_cols] = adjusted.loc[common_dates, common_cols] * boost_matrix

    row_sums = adjusted.sum(axis=1).replace(0, 1.0)
    adjusted = adjusted.div(row_sums, axis=0)

    logger.info("Sentiment overlay: mean_boost=%.4f, scale=%.2f", boost_matrix.mean().mean() - 1.0, boost_scale)
    return adjusted
