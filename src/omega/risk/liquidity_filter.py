"""
Liquidity Filter Module for V21_QUANT.
v21.16.2: FIXED P1 Look-ahead Bias. Implements Point-in-Time (PIT) filtering.

Filters stocks based on Average Daily Value (ADV) of the PREVIOUS 20 days.
"""

import pandas as pd
import numpy as np
import logging
from typing import List, Optional

class LiquidityFilter:
    """
    PIT-Compliant Liquidity Filter.
    Ensures no survivorship or look-ahead bias in universe selection.
    """
    RAW_PRICE_THRESHOLD = 1_000.0
    VND_PRICE_SCALE = 1_000.0
    
    def __init__(self, min_adv: float = 1e9, lookback_days: int = 20):
        self.min_adv = min_adv
        self.lookback_days = lookback_days

    def _daily_value_vnd(self, df: pd.DataFrame) -> pd.Series:
        close = pd.to_numeric(df['close'], errors='coerce').astype(float)
        volume = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0).astype(float)
        close_vnd = close.where((close <= 0) | (close >= self.RAW_PRICE_THRESHOLD), close * self.VND_PRICE_SCALE)
        return close_vnd * volume
        
    def apply_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filters the dataframe dynamically per date.
        A stock is included on Date T only if its ADV from [T-20 to T-1] >= min_adv.
        """
        df = df.copy().sort_index()
        
        # 1. Calculate Daily Value (PIT)
        df['daily_value'] = self._daily_value_vnd(df)
        
        # 2. Calculate Rolling ADV with SHIFT(1) (P1 FIX: PIT Compliance)
        # We must shift(1) so that today's filter doesn't know today's volume
        df['adv_signal'] = df.groupby(level='symbol')['daily_value'].transform(
            lambda x: x.rolling(self.lookback_days).mean().shift(1)
        )
        
        # 3. Filter: Keep only rows where liquidity was sufficient at that point in time
        # Handle NaN (early days of listing) by filling with 0 (fail-safe)
        df = df[df['adv_signal'].fillna(0) >= self.min_adv]
        
        # Cleanup temporary columns
        return df.drop(columns=['daily_value', 'adv_signal'])

    def get_liquid_universe_at_date(self, df: pd.DataFrame, date: pd.Timestamp) -> List[str]:
        """
        Returns list of symbols that were liquid as of the given date (using prior data).
        Useful for the main backtest loop.
        
        BUG-P2-001 FIX: A symbol must have >= lookback_days observations in the prior window
        before it is eligible. Previously any non-empty tail was averaged, allowing
        symbols with only 1-2 days of history to appear as liquid.
        """
        historical_data = df[df.index.get_level_values('date') < date]
        if historical_data.empty:
            return []
        
        daily_val = self._daily_value_vnd(historical_data)
        
        # Require full lookback window: count must >= lookback_days
        symbol_tail = daily_val.groupby(level='symbol').tail(self.lookback_days)
        symbol_count = symbol_tail.groupby(level='symbol').count()
        symbol_adv = symbol_tail.groupby(level='symbol').mean()
        
        # Both conditions must be met: enough history AND sufficient ADV
        eligible = symbol_count[symbol_count >= self.lookback_days].index
        liquid = symbol_adv.loc[symbol_adv.index.isin(eligible)]
        
        return liquid[liquid >= self.min_adv].index.tolist()

def apply_pit_liquidity_filter(df: pd.DataFrame, min_adv: float = 1e9) -> pd.DataFrame:
    """Convenience wrapper for Layer 01."""
    filter_obj = LiquidityFilter(min_adv=min_adv)
    return filter_obj.apply_filter(df)
