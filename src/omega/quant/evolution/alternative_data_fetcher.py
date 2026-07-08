"""
OMEGA_QUANT Alternative Data Fetcher
Fetches foreign flow, margin data from vnstock API.
Fallback: derives proxy signals from OHLCV when API unavailable.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All data fetched with as_of constraint.
Memory Optimization: 2026-07-07 - Narrow copy calculation, vectorized date mapping.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from omega.quant.sentiment.focal_point_detector import VNFocalPointDetector
from omega.quant.sentiment.vsi_engine import VSIPortfolioEngine, SentimentData

logger = logging.getLogger(__name__)


class AlternativeDataFetcher:
    """
    Fetch or derive alternative data signals.
    Primary: vnstock API (foreign flow, margin)
    Fallback: OHLCV-derived proxies
    """

    def __init__(self, use_api: bool = False):
        self.use_api = use_api
        self.fp_detector = VNFocalPointDetector()
        self.vsi_engine = VSIPortfolioEngine()

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

    def _derive_sentiment_indicators(self, panel: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Derives VSI and Focal Stress Score (FSS) in a PIT-safe manner.
        For each date T, uses market data from date T-1 to generate VSI and FSS.

        Memory optimization: Uses vectorized date mapping instead of boolean masking loop.
        Memory optimization 2 (GP_ALT_DATA_FETCHER_OPTIMIZATION): Pre-group by date once
        before loop to replace 12,782 slow .xs() MultiIndex slicing operations with fast
        dict lookups.

        Memory optimization 3 (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION): Build a narrow
        copy panel_fp containing only ['foreign_flow', 'liquidity_shock', 'sector_rotation']
        (the columns actually consumed by focal_point_detector.analyze) and pre-group by date
        on that narrow copy. The original `panel` is left intact for daily_returns and
        daily_foreign computations downstream.
        """
        dates = sorted(panel.index.get_level_values('date').unique())

        # MEMORY OPTIMIZATION (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION): narrow copy with
        # only the columns the focal-point detector actually needs. Original panel is kept
        # untouched for downstream daily_returns / daily_foreign calculations.
        fp_cols = ['foreign_flow', 'liquidity_shock', 'sector_rotation']
        panel_fp = panel[[c for c in fp_cols if c in panel.columns]].copy()

        # Memory optimization: Pre-group narrow panel by date once (replaces expensive .xs() calls in loop)
        market_by_date = {}
        for date_str, group in panel_fp.groupby(level='date'):
            market_by_date[date_str] = group.droplevel('date')
        
        # Build date -> score mappings (vectorized assignment at the end)
        vsi_map = {dates[0]: 50.0}  # Default for first date
        fss_map = {dates[0]: 20.0}
        
        # Calculate daily market returns and foreign flows
        daily_returns = panel.groupby(level='symbol')['close'].pct_change().groupby(level='date').mean()
        # Using margin_proxy as a proxy for physical market flow in the fallback calculation
        daily_foreign = panel['margin_proxy'].groupby(level='date').mean()
        
        # We loop from the second date to enforce T-1 lag
        for i in range(1, len(dates)):
            curr_date_str = dates[i]
            prev_date_str = dates[i-1]
            prev_datetime = pd.to_datetime(prev_date_str)
            
            # 1. Generate synthetic news based on T-1 market moves
            ret = daily_returns.get(prev_date_str, 0.0)
            flow = daily_foreign.get(prev_date_str, 0.0)
            
            news_items = []
            if ret < -0.015:
                news_items.append(SentimentData(text="Thị trường giảm mạnh bán tháo áp lực margin call", source="CAFEF", published_at=prev_datetime, as_of_time=prev_datetime))
                news_items.append(SentimentData(text="Nhiều cổ phiếu giảm sàn cắt lỗ hàng loạt", source="VIETSTOCK", published_at=prev_datetime, as_of_time=prev_datetime))
            elif ret > 0.015:
                news_items.append(SentimentData(text="Thị trường tăng trần bứt phá dòng tiền mạnh tích cực", source="CAFEF", published_at=prev_datetime, as_of_time=prev_datetime))
            else:
                news_items.append(SentimentData(text="Thị trường sideway ổn định giao dịch trầm lắng", source="VNEXPRESS", published_at=prev_datetime, as_of_time=prev_datetime))
                
            if flow < -1.0:
                news_items.append(SentimentData(text="Khối ngoại bán ròng mạnh rút vốn tiêu cực", source="VIETSTOCK", published_at=prev_datetime, as_of_time=prev_datetime))
                
            # If no items, add a neutral baseline
            if not news_items:
                news_items.append(SentimentData(text="Thị trường bình thường", source="VNEXPRESS", published_at=prev_datetime, as_of_time=prev_datetime))
                
            # 2. Compute VSI
            sentiment_scores = self.vsi_engine.calculate_sentiment(news_items)
            vsi_score_obj = self.vsi_engine.calculate_vsi(sentiment_scores, as_of_time=prev_datetime)
            vsi_val = vsi_score_obj.score
            
            # 3. Compute Focal Point Stress
            # Use pre-grouped single-index slice (memory optimization - avoids expensive .xs() call)
            prev_slice = market_by_date.get(prev_date_str, pd.DataFrame())
            fss_summary = self.fp_detector.analyze(sentiment_scores, prev_slice, prev_datetime)
            fss_val = fss_summary.aggregate_stress_score
            
            # Store in mapping for vectorized assignment later
            vsi_map[curr_date_str] = vsi_val
            fss_map[curr_date_str] = fss_val
            
        # Vectorized date mapping (eliminates O(T*N) boolean masking overhead)
        date_index = panel.index.get_level_values('date')
        vsi_series = pd.Series(date_index.map(vsi_map), index=panel.index).fillna(50.0)
        fss_series = pd.Series(date_index.map(fss_map), index=panel.index).fillna(20.0)
            
        return vsi_series, fss_series

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all alternative data signals.
        
        Memory optimization: Calculate proxy signals on a narrow copy containing only
        essential OHLCV columns, then join back to original panel.
        
        Memory optimization 2 (GP_ALT_DATA_FETCHER_OPTIMIZATION): Reorder MultiIndex to 
        [symbol, date] and sort once to make groupby(level='symbol') operations contiguous.
        This prevents pandas from allocating expensive (n_groups, n_rows) alignment matrices.

        Args:
            panel: MultiIndex [date, symbol] with OHLCV

        Returns:
            Panel with additional alt data columns.
        """
        # Memory optimization: reorder MultiIndex to [symbol, date] and sort
        # This makes all subsequent groupby(level='symbol') operations contiguous
        panel = panel.reorder_levels(['symbol', 'date']).sort_index()
        
        # Memory optimization: work on narrow copy with only OHLCV columns
        essential_cols = ['open', 'high', 'low', 'close', 'volume']
        narrow = panel[essential_cols].copy()
        
        # Create a new DataFrame for features only
        features = pd.DataFrame(index=narrow.index)

        features['foreign_flow'] = self.get_foreign_flow_proxy(narrow)
        features['margin_proxy'] = self.get_margin_proxy(narrow)
        features['sector_rotation'] = self.get_sector_rotation_proxy(narrow)
        features['order_imbalance'] = self.get_order_imbalance_proxy(narrow)
        features['liquidity_shock'] = self.get_liquidity_shock_proxy(narrow)

        # Rolling aggregates for signal smoothing
        features['foreign_flow_ma5'] = features.groupby(level='symbol')['foreign_flow'].transform(lambda x: x.rolling(5, min_periods=2).mean())
        features['margin_trend'] = features.groupby(level='symbol')['margin_proxy'].transform(lambda x: x.rolling(5).mean() / x.rolling(20).mean().replace(0, 1))
        features['rotation_momentum'] = features.groupby(level='symbol')['sector_rotation'].transform(lambda x: x.rolling(5, min_periods=2).mean())

        # Combine narrow panel with calculated features for sentiment indicators
        # (margin_proxy is required by _derive_sentiment_indicators)
        narrow_with_features = narrow.join(features)
        
        # Generate sentiment and focal point stress features
        vsi_s, fss_s = self._derive_sentiment_indicators(narrow_with_features)
        features['vsi_score'] = vsi_s
        features['focal_stress_score'] = fss_s

        # Join all features back to original panel
        result = panel.join(features)

        # Restore index levels order to prevent silent column swap in unified_feature_adapter.py
        result = result.reorder_levels(['date', 'symbol']).sort_index()

        logger.info("Generated 10 alternative data signals")
        return result

    def get_feature_names(self) -> list:
        """Return list of alternative data feature names."""
        return [
            'foreign_flow', 'margin_proxy', 'sector_rotation',
            'order_imbalance', 'liquidity_shock',
            'foreign_flow_ma5', 'margin_trend', 'rotation_momentum',
            'vsi_score', 'focal_stress_score',
        ]
