import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any
import time
import numpy as np


@dataclass
class TCALogEntry:
    timestamp: int
    symbol: str
    side: str
    parent_quantity: int
    filled_quantity: int
    avg_fill_price: float
    benchmark_price: float
    pre_trade_impact_bps: float
    post_trade_slippage_bps: float = 0.0
    implementation_shortfall_bps: float = 0.0


class TCA:
    """
    Trade Cost Analysis (TCA) module for post-trade analysis.
    Calculates various slippage and implementation shortfall metrics.
    """
    
    def __init__(self, log_dir: str = "state/tca_logs"):
        self.log_dir = log_dir

    def calculate_is(self, fill_price, benchmark_price, side, quantity) -> float:
        """
        Calculates Implementation Shortfall (IS) in basis points.
        IS = (Sign * (FillPrice - BenchmarkPrice) / BenchmarkPrice) * 10000
        """
        if benchmark_price == 0:
            return 0.0
        
        if side == "BUY":
            is_bps = ((fill_price - benchmark_price) / benchmark_price) * 10000
        else:  # SELL
            is_bps = ((benchmark_price - fill_price) / benchmark_price) * 10000
            
        return is_bps

    def calculate_slippage_bps(self, fill_price, benchmark_price) -> float:
        """
        Calculates slippage from a benchmark price in basis points.
        Slippage = ((FillPrice - BenchmarkPrice) / BenchmarkPrice) * 10000
        """
        if benchmark_price == 0:
            return 0.0
        return ((fill_price - benchmark_price) / benchmark_price) * 10000

    def generate_report(self, log_entries: List[TCALogEntry]) -> Dict[str, Any]:
        """
        Generates a summary report from TCA log entries.
        """
        total_is_bps = []
        total_slippage_bps = []
        total_traded_value = 0.0

        for entry in log_entries:
            total_is_bps.append(entry.implementation_shortfall_bps)
            total_slippage_bps.append(entry.post_trade_slippage_bps)
            total_traded_value += entry.filled_quantity * entry.avg_fill_price

        return {
            "num_trades": len(log_entries),
            "total_traded_value": total_traded_value,
            "average_is_bps": float(np.mean(total_is_bps)) if total_is_bps else 0.0,
            "average_slippage_bps": float(np.mean(total_slippage_bps)) if total_slippage_bps else 0.0,
            "max_is_bps": float(np.max(total_is_bps)) if total_is_bps else 0.0,
            "min_is_bps": float(np.min(total_is_bps)) if total_slippage_bps else 0.0,
        }
