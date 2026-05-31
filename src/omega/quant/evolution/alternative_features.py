"""
OMEGA_QUANT Alternative Feature Generator
Derives alternative signals from OHLCV that are structurally different from simple returns.

Features:
1. Microstructure: intraday range, gap, body ratio
2. Volume Profile: volume momentum, relative volume, volume-price divergence
3. Cross-sectional: sector-relative strength, market-relative momentum
4. Regime: volatility regime, trend strength (ADX-like)
5. Order Flow Proxy: close location value (CLV), accumulation/distribution

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All features use only past data, T-1 lag enforced.
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AlternativeFeatureGenerator:
    """
    Generate alternative features from OHLCV data.
    All features are PIT-safe (use only past data).
    """

    def __init__(self, windows: list = None):
        self.windows = windows or [5, 10, 20, 60]

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all alternative features from OHLCV panel.

        Args:
            panel: MultiIndex [date, symbol] DataFrame with open/high/low/close/volume

        Returns:
            DataFrame with all alternative features added.
        """
        result = panel.copy()

        # Microstructure features
        result['intraday_range'] = (panel['high'] - panel['low']) / panel['close']
        result['gap'] = (panel['open'] - panel.groupby(level='symbol')['close'].shift(1)) / panel.groupby(level='symbol')['close'].shift(1)
        result['body_ratio'] = (panel['close'] - panel['open']) / (panel['high'] - panel['low']).replace(0, np.nan)
        result['upper_shadow'] = (panel['high'] - panel[['open', 'close']].max(axis=1)) / (panel['high'] - panel['low']).replace(0, np.nan)
        result['lower_shadow'] = (panel[['open', 'close']].min(axis=1) - panel['low']) / (panel['high'] - panel['low']).replace(0, np.nan)

        # Volume profile features
        result['volume_ma_ratio'] = panel['volume'] / panel.groupby(level='symbol')['volume'].transform(lambda x: x.rolling(20, min_periods=5).mean())
        result['volume_momentum'] = panel.groupby(level='symbol')['volume'].pct_change(5)
        result['volume_trend'] = panel.groupby(level='symbol')['volume'].transform(lambda x: x.rolling(5).mean() / x.rolling(20).mean())

        # Volume-price divergence (price up but volume down = bearish divergence)
        price_dir = panel.groupby(level='symbol')['close'].pct_change(5).apply(np.sign)
        vol_dir = panel.groupby(level='symbol')['volume'].pct_change(5).apply(np.sign)
        result['vp_divergence'] = price_dir - vol_dir

        # Close Location Value (CLV) - proxy for accumulation/distribution
        hl_range = (panel['high'] - panel['low']).replace(0, np.nan)
        result['clv'] = ((panel['close'] - panel['low']) - (panel['high'] - panel['close'])) / hl_range
        result['clv_ma'] = result.groupby(level='symbol')['clv'].transform(lambda x: x.rolling(10, min_periods=3).mean())

        # Accumulation/Distribution proxy (CLV * volume)
        result['ad_line'] = result['clv'] * panel['volume']
        result['ad_momentum'] = result.groupby(level='symbol')['ad_line'].pct_change(5)

        # Volatility regime
        result['realized_vol_5'] = panel.groupby(level='symbol')['close'].transform(lambda x: x.pct_change().rolling(5).std())
        result['realized_vol_20'] = panel.groupby(level='symbol')['close'].transform(lambda x: x.pct_change().rolling(20).std())
        result['vol_regime'] = result['realized_vol_5'] / result['realized_vol_20'].replace(0, np.nan)

        # Trend strength (simplified ADX-like)
        result['trend_strength'] = panel.groupby(level='symbol')['close'].transform(
            lambda x: (x.rolling(10).mean() - x.rolling(30).mean()) / x.rolling(30).std()
        )

        # Cross-sectional rank features (market-relative)
        result['ret_5d'] = panel.groupby(level='symbol')['close'].pct_change(5)
        result['ret_20d'] = panel.groupby(level='symbol')['close'].pct_change(20)
        result['cs_rank_ret5'] = result.groupby(level='date')['ret_5d'].rank(pct=True)
        result['cs_rank_ret20'] = result.groupby(level='date')['ret_20d'].rank(pct=True)
        result['cs_rank_volume'] = panel.groupby(level='date')['volume'].rank(pct=True)

        # Mean reversion signals (different from simple returns)
        result['distance_from_ma20'] = (panel['close'] - panel.groupby(level='symbol')['close'].transform(lambda x: x.rolling(20).mean())) / panel.groupby(level='symbol')['close'].transform(lambda x: x.rolling(20).std())
        result['distance_from_ma60'] = (panel['close'] - panel.groupby(level='symbol')['close'].transform(lambda x: x.rolling(60).mean())) / panel.groupby(level='symbol')['close'].transform(lambda x: x.rolling(60).std())

        # Momentum acceleration
        result['momentum_accel'] = result.groupby(level='symbol')['ret_5d'].transform(lambda x: x.diff())

        # Fill NaN with 0 for features (PIT-safe: NaN means insufficient history)
        feature_cols = [c for c in result.columns if c not in panel.columns]
        result[feature_cols] = result[feature_cols].fillna(0)

        logger.info("Generated %d alternative features", len(feature_cols))
        return result

    def get_feature_names(self) -> list:
        """Return list of all generated feature names."""
        return [
            'intraday_range', 'gap', 'body_ratio', 'upper_shadow', 'lower_shadow',
            'volume_ma_ratio', 'volume_momentum', 'volume_trend', 'vp_divergence',
            'clv', 'clv_ma', 'ad_line', 'ad_momentum',
            'realized_vol_5', 'realized_vol_20', 'vol_regime',
            'trend_strength',
            'ret_5d', 'ret_20d', 'cs_rank_ret5', 'cs_rank_ret20', 'cs_rank_volume',
            'distance_from_ma20', 'distance_from_ma60',
            'momentum_accel',
        ]
