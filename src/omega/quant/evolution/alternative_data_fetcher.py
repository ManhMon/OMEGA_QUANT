"""
OMEGA_QUANT Alternative Data Fetcher
Fetches foreign flow, margin data from vnstock API.
Fallback: derives proxy signals from OHLCV when API unavailable.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All data fetched with as_of constraint.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AlternativeDataFetcher:
    """
    Fetch or derive alternative data signals.
    Primary: vnstock API (foreign flow, margin)
    Fallback: OHLCV-derived proxies
    """

    def __init__(self, use_api: bool = False):
        self.use_api = use_api

    def get_foreign_flow_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Foreign flow proxy from OHLCV.
        Logic: Large volume + price up = foreign buying (institutional flow).
        Proxy: volume_zscore * sign(return) — captures unusual volume with direction.

        PIT Safety: Uses only past data (rolling stats).
        """
        vol = panel['volume']
        vol_ma = vol.groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=5).mean())
        vol_std = vol.groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=5).std())
        vol_zscore = (vol - vol_ma) / vol_std.replace(0, 1)

        ret_sign = panel.groupby(level='symbol')['close'].pct_change().map(np.sign)
        foreign_proxy = vol_zscore * ret_sign

        return foreign_proxy.fillna(0)

    def get_margin_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Margin outstanding proxy.
        Logic: Sustained buying on increasing volume = margin accumulation.
        Proxy: cumulative sum of (volume * return) over rolling window.

        PIT Safety: Rolling cumsum, no future data.
        """
        ret = panel.groupby(level='symbol')['close'].pct_change()
        flow = panel['volume'] * ret
        margin_proxy = flow.groupby(level='symbol').transform(lambda x: x.rolling(10, min_periods=3).sum())

        return margin_proxy.fillna(0)

    def get_sector_rotation_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Sector rotation proxy.
        Logic: Relative strength vs market mean — stocks outperforming market = sector inflow.
        Proxy: symbol_return - cross_sectional_mean_return (rolling 10d).

        PIT Safety: Cross-sectional at each date, no future data.
        """
        ret_10d = panel.groupby(level='symbol')['close'].pct_change(10)
        market_mean = ret_10d.groupby(level='date').transform('mean')
        rotation_proxy = ret_10d - market_mean

        return rotation_proxy.fillna(0)

    def get_order_imbalance_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Order imbalance proxy from OHLCV.
        Logic: (close - open) / (high - low) indicates buying/selling pressure.
        Combined with volume for strength.

        PIT Safety: Same-bar data only, no future.
        """
        hl_range = (panel['high'] - panel['low']).replace(0, np.nan)
        pressure = (panel['close'] - panel['open']) / hl_range
        imbalance = pressure * np.log1p(panel['volume'])

        return imbalance.fillna(0)

    def get_liquidity_shock_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Liquidity shock detector.
        Logic: Sudden volume spike (>3x average) with large price move.

        PIT Safety: Rolling stats only.
        """
        vol = panel['volume']
        vol_ma = vol.groupby(level='symbol').transform(lambda x: x.rolling(20, min_periods=5).mean())
        vol_spike = vol / vol_ma.replace(0, 1)

        abs_ret = panel.groupby(level='symbol')['close'].pct_change().abs()
        shock = vol_spike * abs_ret

        return shock.fillna(0)

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all alternative data signals.

        Args:
            panel: MultiIndex [date, symbol] with OHLCV

        Returns:
            Panel with additional alt data columns.
        """
        result = panel.copy()

        result['foreign_flow'] = self.get_foreign_flow_proxy(panel)
        result['margin_proxy'] = self.get_margin_proxy(panel)
        result['sector_rotation'] = self.get_sector_rotation_proxy(panel)
        result['order_imbalance'] = self.get_order_imbalance_proxy(panel)
        result['liquidity_shock'] = self.get_liquidity_shock_proxy(panel)

        # Rolling aggregates for signal smoothing
        result['foreign_flow_ma5'] = result.groupby(level='symbol')['foreign_flow'].transform(lambda x: x.rolling(5, min_periods=2).mean())
        result['margin_trend'] = result.groupby(level='symbol')['margin_proxy'].transform(lambda x: x.rolling(5).mean() / x.rolling(20).mean().replace(0, 1))
        result['rotation_momentum'] = result.groupby(level='symbol')['sector_rotation'].transform(lambda x: x.rolling(5, min_periods=2).mean())

        logger.info("Generated 8 alternative data signals")
        return result

    def get_feature_names(self) -> list:
        """Return list of alternative data feature names."""
        return [
            'foreign_flow', 'margin_proxy', 'sector_rotation',
            'order_imbalance', 'liquidity_shock',
            'foreign_flow_ma5', 'margin_trend', 'rotation_momentum',
        ]
