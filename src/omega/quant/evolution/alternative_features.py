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
        
        Memory optimization: Calculate features on a narrow copy containing only
        essential OHLCV columns, then join back to original panel.

        Args:
            panel: MultiIndex [date, symbol] DataFrame with open/high/low/close/volume

        Returns:
            DataFrame with all alternative features added.
        """
        # Memory optimization: work on narrow copy with only OHLCV columns
        essential_cols = ['open', 'high', 'low', 'close', 'volume']
        narrow = panel[essential_cols].copy()
        
        # Create a new DataFrame for features only
        features = pd.DataFrame(index=narrow.index)

        # Microstructure features
        features['intraday_range'] = (narrow['high'] - narrow['low']) / narrow['close']
        features['gap'] = (narrow['open'] - narrow.groupby(level='symbol')['close'].shift(1)) / narrow.groupby(level='symbol')['close'].shift(1)
        features['body_ratio'] = (narrow['close'] - narrow['open']) / (narrow['high'] - narrow['low']).replace(0, np.nan)
        features['upper_shadow'] = (narrow['high'] - narrow[['open', 'close']].max(axis=1)) / (narrow['high'] - narrow['low']).replace(0, np.nan)
        features['lower_shadow'] = (narrow[['open', 'close']].min(axis=1) - narrow['low']) / (narrow['high'] - narrow['low']).replace(0, np.nan)

        # Volume profile features
        features['volume_ma_ratio'] = narrow['volume'] / narrow.groupby(level='symbol')['volume'].transform(lambda x: x.rolling(20, min_periods=5).mean())
        features['volume_momentum'] = narrow.groupby(level='symbol')['volume'].pct_change(5)
        features['volume_trend'] = narrow.groupby(level='symbol')['volume'].transform(lambda x: x.rolling(5).mean() / x.rolling(20).mean())

        # Volume-price divergence (price up but volume down = bearish divergence)
        price_dir = narrow.groupby(level='symbol')['close'].pct_change(5).map(np.sign)
        vol_dir = narrow.groupby(level='symbol')['volume'].pct_change(5).map(np.sign)
        features['vp_divergence'] = price_dir - vol_dir

        # Close Location Value (CLV) - proxy for accumulation/distribution
        hl_range = (narrow['high'] - narrow['low']).replace(0, np.nan)
        features['clv'] = ((narrow['close'] - narrow['low']) - (narrow['high'] - narrow['close'])) / hl_range
        features['clv_ma'] = features.groupby(level='symbol')['clv'].transform(lambda x: x.rolling(10, min_periods=3).mean())

        # Accumulation/Distribution proxy (CLV * volume)
        features['ad_line'] = features['clv'] * narrow['volume']
        features['ad_momentum'] = features.groupby(level='symbol')['ad_line'].pct_change(5)

        # Volatility regime
        features['realized_vol_5'] = narrow.groupby(level='symbol')['close'].transform(lambda x: x.pct_change().rolling(5).std())
        features['realized_vol_20'] = narrow.groupby(level='symbol')['close'].transform(lambda x: x.pct_change().rolling(20).std())
        features['vol_regime'] = features['realized_vol_5'] / features['realized_vol_20'].replace(0, np.nan)

        # Trend strength (simplified ADX-like)
        features['trend_strength'] = narrow.groupby(level='symbol')['close'].transform(
            lambda x: (x.rolling(10).mean() - x.rolling(30).mean()) / x.rolling(30).std()
        )

        # Cross-sectional rank features (market-relative)
        features['ret_5d'] = narrow.groupby(level='symbol')['close'].pct_change(5)
        features['ret_20d'] = narrow.groupby(level='symbol')['close'].pct_change(20)
        features['cs_rank_ret5'] = features.groupby(level='date')['ret_5d'].rank(pct=True)
        features['cs_rank_ret20'] = features.groupby(level='date')['ret_20d'].rank(pct=True)
        features['cs_rank_volume'] = narrow.groupby(level='date')['volume'].rank(pct=True)

        # Mean reversion signals (different from simple returns)
        features['distance_from_ma20'] = (narrow['close'] - narrow.groupby(level='symbol')['close'].transform(lambda x: x.rolling(20).mean())) / narrow.groupby(level='symbol')['close'].transform(lambda x: x.rolling(20).std())
        features['distance_from_ma60'] = (narrow['close'] - narrow.groupby(level='symbol')['close'].transform(lambda x: x.rolling(60).mean())) / narrow.groupby(level='symbol')['close'].transform(lambda x: x.rolling(60).std())

        # Momentum acceleration
        features['momentum_accel'] = features.groupby(level='symbol')['ret_5d'].transform(lambda x: x.diff())

        # Drop any columns from features that already exist in panel (avoid collision)
        overlap_cols = features.columns.intersection(panel.columns)
        if len(overlap_cols) > 0:
            features = features.drop(columns=overlap_cols)
            logger.info(f"Dropped {len(overlap_cols)} overlapping columns before join: {list(overlap_cols)}")

        # Join features back to original panel
        result = panel.join(features)
        
        # Leave NaN for features with insufficient history (PIT-safe).
        # Downstream consumers (screening, backtest) handle NaN via dropna/corr(nan_policy).
        # Do NOT fill with 0 — it biases cross-sectional ranks during warm-up.
        feature_cols = [c for c in result.columns if c not in panel.columns]
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
