"""
Multi-horizon Label Engineering Module - Phase 2 (v21.7.0)
Based on Codex Alpha Factory V2.0 Strategic Blueprint.

This module generates multiple forward return targets (T+3, T+5, T+10, T+20)
while strictly enforcing the T+2.5 settlement gap for the Vietnam market.

Author: Ly (AI Assistant)
Date: 2026-04-22
Version: 1.0 (Priority #1: Label Lever)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any

class MultiHorizonLabels:
    """
    Generates multi-horizon forward return labels.
    Ensures zero temporal leakage by aligning with VN T+2.5 settlement.
    """
    
    def __init__(self, horizons: List[int] = [3, 5, 10, 20], settlement_gap: float = 2.5):
        self.horizons = horizons
        # We use ceil because even at T+2.5, you can only realistically 
        # use the capital/position at the start of the next day (T+3).
        self.settlement_gap = int(np.ceil(settlement_gap)) 
        
    def compute_labels(self, prices: pd.Series) -> pd.DataFrame:
        """
        Computes forward returns for each defined horizon.
        
        Formula: (Price at t + horizon + gap) / (Price at t) - 1
        
        Args:
            prices: pd.Series with MultiIndex (date, symbol) or DatetimeIndex and Close prices.
            
        Returns:
            pd.DataFrame containing columns for each horizon (e.g., 'target_3d', 'target_5d').
        """
        labels = {}
        
        for h in self.horizons:
            # Total shift = horizon + settlement delay
            total_shift = -(h + self.settlement_gap)
            
            # CRITICAL FIX: If MultiIndex, shift within each symbol group
            if isinstance(prices.index, pd.MultiIndex):
                # Group by symbol (level 1) and shift within each group
                target_price = prices.groupby(level=1).shift(total_shift)
            else:
                # Simple DatetimeIndex: direct shift
                target_price = prices.shift(total_shift)
            
            labels[f'target_{h}d'] = (target_price / prices) - 1
            
        return pd.DataFrame(labels, index=prices.index)

    def get_summary_stats(self, labels_df: pd.DataFrame) -> Dict[str, Any]:
        """Returns statistical summary of the generated labels for validation."""
        stats = {}
        for col in labels_df.columns:
            stats[col] = {
                "count": int(labels_df[col].count()),
                "mean": float(labels_df[col].mean()),
                "std": float(labels_df[col].std()),
                "min": float(labels_df[col].min()),
                "max": float(labels_df[col].max()),
                "coverage": float(labels_df[col].notna().mean())
            }
        return stats

if __name__ == "__main__":
    # Quick test stub
    dates = pd.date_range("2023-01-01", periods=100)
    mock_prices = pd.Series(np.linspace(100, 200, 100), index=dates)
    
    mhl = MultiHorizonLabels()
    df = mhl.compute_labels(mock_prices)
    print("Multi-Horizon Labels (First 5 rows):")
    print(df.head())
    print("\nCoverage Summary:")
    for h, stat in mhl.get_summary_stats(df).items():
        print(f"{h}: {stat['coverage']:.2%}")
