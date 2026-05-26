import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Union

class SmartMoneyFeatures:
    """
    Calculates 9 high-frequency Smart Money indicators tailored for the
    Vietnamese stock market (VN30/HOSE).

    Goal: 100% compliance with Codex R2 audit findings. No legacy APIs.
    Strict Point-in-Time (PIT) safety is enforced.
    """

    def __init__(self):
        pass

    @staticmethod
    def calculate_obi(bids: List[float], asks: List[float]) -> float:
        """
        Order Book Imbalance (OBI).
        Measures relative buying vs. selling pressure resting in the limit order book.
        Formula: OBI_t = (sum(bids) - sum(asks)) / (sum(bids) + sum(asks))
        """
        b_sum = sum(bids)
        a_sum = sum(asks)
        if b_sum + a_sum == 0:
            return 0.0
        return (b_sum - a_sum) / (b_sum + a_sum)

    @staticmethod
    def calculate_vwap_deviation(price: float, vwap: float) -> float:
        """
        VWAP Deviation.
        Distance of current price from VWAP.
        Formula: Dev_VWAP_t = (P_t - VWAP_{0->t}) / VWAP_{0->t}
        
        PIT Contract:
        - Granularity: Tick/1-minute.
        - Finalization: Continually updated at t.
        - Lag: EXPLICIT T-1 LAG REQUIRED. Both `price` and `vwap` MUST
          be lagged by 1 period (T-1 values) before calling this function.
          This ensures the deviation reflects information available at T-1,
          not at time t.
        - Session Reset: MUST reset at the start of each HOSE trading session (9:00 AM).
        
        IMPORTANT: Use `calculate_vwap_deviation_t1` for explicit PIT-safe
        wrapping when working with time series inputs.
        """
        if vwap == 0:
            return 0.0
        return (price - vwap) / vwap

    @staticmethod
    def calculate_vwap_deviation_t1(price_series: Union[pd.Series, List[float]], vwap_series: Union[pd.Series, List[float]]) -> pd.Series:
        """
        PIT-safe T-1 wrapper for VWAP deviation.

        Shifts both inputs by 1 period, then computes deviation using only
        information available at T-1.
        """
        price_t1 = pd.Series(price_series).shift(1)
        vwap_t1 = pd.Series(vwap_series).shift(1)
        deviation = np.where(vwap_t1 == 0, 0.0, (price_t1 - vwap_t1) / vwap_t1)
        return pd.Series(deviation, index=price_t1.index, dtype=float)

    @staticmethod
    def calculate_amihud(window_return: float, window_traded_value: float) -> float:
        """
        Amihud Intraday Illiquidity proxy.
        Formula: Amihud_t = |r_t| / TradedValue_t
        Computed for a finalized window.
        
        PIT Contract:
        - Granularity: Non-overlapping intraday windows (e.g., 5-min).
        - Finalization: End of window t.
        - Lag: EXPLICIT T-1 LAG REQUIRED.
        - Session Reset: N/A.
        """
        if window_traded_value == 0:
            return 0.0
        return abs(window_return) / window_traded_value

    @staticmethod
    def calculate_block_trade_proxy(trade_volumes: List[float], threshold_t_minus_1: float) -> float:
        """
        Block Trade Proxy.
        Isolates "whale" activity by filtering transactions exceeding a size threshold.
        threshold_t_minus_1 MUST be calculated from previous day(s) data (lagged by 1 day).
        Formula: BTP_t = sum(V_j * I(V_j > tau)) / sum(V_j)
        """
        if not trade_volumes:
            return 0.0
        total_vol = sum(trade_volumes)
        if total_vol == 0:
            return 0.0
        block_vol = sum(v for v in trade_volumes if v > threshold_t_minus_1)
        return block_vol / total_vol

    @staticmethod
    def calculate_absorption_score(buy_vol: float, sell_vol: float, delta_p: float, atr: float, epsilon: float = 1e-8) -> float:
        """
        Absorption Score.
        Detects "iceberg" absorption.
        Formula: Absorb_t = max(-1, min(1, ((V_buy - V_sell) / max(eps, V_total)) * (Delta_P / max(eps, ATR_t))))
        """
        v_total = buy_vol + sell_vol
        term1 = (buy_vol - sell_vol) / max(epsilon, v_total)
        term2 = delta_p / max(epsilon, atr)
        score = term1 * term2
        return max(-1.0, min(1.0, score))

    @staticmethod
    def calculate_fnv_persistence(foreign_buy_vols: List[float], foreign_sell_vols: List[float]) -> float:
        """
        Foreign Net Volume Persistence.
        Cumulative intraday delta of foreign buying vs. selling.
        Formula: FNV_t = sum(V_foreign_buy) - sum(V_foreign_sell)
        """
        return sum(foreign_buy_vols) - sum(foreign_sell_vols)

    @staticmethod
    def calculate_ofi(buy_tick_vols: List[float], sell_tick_vols: List[float]) -> float:
        """
        Order Flow Imbalance.
        Classifies aggressive market orders to detect informed directional bets.
        Formula: OFI_t = sum(V_buy_tick) - sum(V_sell_tick)
        """
        return sum(buy_tick_vols) - sum(sell_tick_vols)

    @staticmethod
    def calculate_intraday_smi(prev_smi: float, return_0900_0930: float, return_1400_1445: float) -> float:
        """
        Intraday Smart Money Flow Index (SMI).
        Adapts SMI for HOSE market.
        Formula: SMI_day = SMI_{day-1} - Return_{09:00->09:30} + Return_{14:00->14:45}
        """
        return prev_smi - return_0900_0930 + return_1400_1445

    @staticmethod
    def calculate_trade_size_skew(trade_volumes: List[float]) -> float:
        """
        Trade Size Distribution Skew.
        Analyzes the skewness of trade sizes over a rolling window.
        Formula: Skew_t = n/((n-1)(n-2)) * sum(((V_i - V_bar)/s_V)^3)
        """
        n = len(trade_volumes)
        if n < 3:
            return 0.0
        
        arr = np.array(trade_volumes)
        mean_v = np.mean(arr)
        std_v = np.std(arr, ddof=1)
        
        if std_v == 0:
            return 0.0
            
        skew = (n / ((n - 1) * (n - 2))) * np.sum(((arr - mean_v) / std_v) ** 3)
        return float(skew)

