"""
Phase 6: Transaction-Cost & Slippage Analysis for Regime Switching
Implements turnover measurement, post-switch PnL analysis, and VN market slippage model.

Owner: OpenCode (L2)
Auditor: Codex (L3)
Date: 2026-05-01
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class Exchange(Enum):
    """Vietnamese stock exchange identifiers."""
    HOSE = "HOSE"
    HNX = "HNX"


@dataclass
class VNSlippageModel:
    """
    Slippage model for Vietnamese market â€” exchange-aware.
    
    Total slippage = half_spread + market_impact
    
    half_spread: Fixed cost component (half of bid-ask spread)
    market_impact: Variable cost component (function of order size vs ADV)
    
    HNX receives higher coefficients due to:
    - Lower ADV (median ~1/5 of HOSE equivalent-cap stocks)
    - Wider bid-ask spreads (fewer market makers)
    - Â±10% price limit vs HOSE Â±7% (larger gap risk on limit-down days)
    - impact_coefficient_HNX = impact_coefficient_HOSE Ã— 1.5
    """
    
    # --- HOSE defaults (top 50 liquid stocks) ---
    base_spread_bps_hose: float = 5.0       # Median half-spread for HOSE liquid stocks
    impact_coefficient_hose: float = 50.0   # bps per âˆš(participation rate) â€” HOSE
    
    # --- HNX defaults (top 20 liquid stocks) ---
    base_spread_bps_hnx: float = 8.0        # Wider spread due to lower liquidity
    impact_coefficient_hnx: float = 75.0    # 1.5Ã— HOSE â€” lower ADV amplifies impact
    
    def _get_params(self, exchange: Exchange) -> Tuple[float, float]:
        """Return (base_spread_bps, impact_coefficient) for the given exchange."""
        if exchange == Exchange.HNX:
            return self.base_spread_bps_hnx, self.impact_coefficient_hnx
        return self.base_spread_bps_hose, self.impact_coefficient_hose
    
    def compute_slippage_bps(
        self,
        order_notional: float,
        adv_notional: float,
        exchange: Exchange = Exchange.HOSE
    ) -> float:
        """
        Compute total slippage in basis points.
        
        Args:
            order_notional: Order size in VND
            adv_notional: Average daily volume in VND
            exchange: HOSE or HNX (determines spread & impact params)
        
        Returns:
            Total estimated slippage in basis points
        """
        base_spread, impact_coeff = self._get_params(exchange)
        
        participation_rate = order_notional / max(adv_notional, 1.0)
        market_impact = impact_coeff * np.sqrt(participation_rate)
        
        return base_spread + market_impact


@dataclass
class SwitchEvent:
    """Represents a single regime switch event."""
    switch_date: str
    source_regime: str
    target_regime: str
    turnover: float                    # Fractional turnover
    estimated_cost_vnd: float          # Transaction cost in VND
    ramp_day: int                      # Which day of ramp (1 to ramp_duration)
    post_switch_5d_pnl: Optional[float] = None
    post_switch_10d_pnl: Optional[float] = None
    clamp_rate: Optional[float] = None
    reject_rate: Optional[float] = None


@dataclass
class TransactionCostAnalysis:
    """Results from transaction cost analysis."""
    switch_events: List[SwitchEvent] = field(default_factory=list)
    total_turnover: float = 0.0
    total_transaction_cost_vnd: float = 0.0
    avg_turnover_per_switch: float = 0.0
    post_switch_5d_pnl_positive_rate: float = 0.0
    post_switch_10d_pnl_positive_rate: float = 0.0
    avg_clamp_rate_during_ramp: float = 0.0
    avg_clamp_rate_steady_state: float = 0.0
    ramp_vs_binary_comparison: Dict[str, float] = field(default_factory=dict)


class TransactionCostAnalyzer:
    """
    Analyzes transaction costs and slippage for regime switching strategies.
    
    Implements:
    - Turnover measurement per switch event
    - Post-switch PnL analysis (5d, 10d)
    - Binary vs ramp switching comparison
    - Clamp/reject rate tracking
    - VN market slippage model (HOSE/HNX aware)
    """
    
    def __init__(
        self,
        capital: float = 2_000_000_000,
        transaction_cost_bps: float = 15.0,
        slippage_model: Optional[VNSlippageModel] = None
    ):
        """
        Initialize transaction cost analyzer.
        
        Args:
            capital: Portfolio capital in VND
            transaction_cost_bps: Transaction cost in basis points (both sides)
            slippage_model: VN market slippage model (uses defaults if None)
        """
        self.capital = capital
        self.transaction_cost_bps = transaction_cost_bps
        self.slippage_model = slippage_model or VNSlippageModel()
    
    def measure_turnover(
        self,
        weights_before: Dict[str, float],
        weights_after: Dict[str, float]
    ) -> float:
        """
        Measure turnover as sum of absolute weight changes.
        
        turnover = Î£_asset |w_after(asset) - w_before(asset)|
        
        Args:
            weights_before: Portfolio weights on T-1 (under old profile)
            weights_after: Portfolio weights on T (under new profile, after ramp day 1)
        
        Returns:
            Fractional turnover (0 to 2)
        """
        all_assets = set(weights_before.keys()) | set(weights_after.keys())
        turnover = 0.0
        
        for asset in all_assets:
            w_before = weights_before.get(asset, 0.0)
            w_after = weights_after.get(asset, 0.0)
            turnover += abs(w_after - w_before)
        
        return turnover
    
    def estimate_transaction_cost(
        self,
        turnover: float,
        capital: Optional[float] = None
    ) -> float:
        """
        Estimate transaction cost from turnover.
        
        cost = turnover Ã— capital Ã— cost_bps / 10000
        
        Args:
            turnover: Fractional turnover
            capital: Portfolio capital (uses self.capital if None)
        
        Returns:
            Transaction cost in VND
        """
        cap = capital or self.capital
        return turnover * cap * self.transaction_cost_bps / 10000.0
    
    def analyze_post_switch_pnl(
        self,
        equity_curve: List[float],
        switch_indices: List[int],
        lookback_days: int = 5
    ) -> Tuple[List[float], List[float]]:
        """
        Analyze post-switch PnL for specified lookback periods.
        
        Args:
            equity_curve: Daily equity values
            switch_indices: Indices in equity_curve where switches occurred
            lookback_days: Number of days to look ahead (5 or 10)
        
        Returns:
            Tuple of (pnl_5d, pnl_10d) lists
        """
        pnl_5d = []
        pnl_10d = []
        
        for switch_idx in switch_indices:
            # 5-day PnL
            if switch_idx + 5 < len(equity_curve):
                pnl_5d.append(
                    equity_curve[switch_idx + 5] / equity_curve[switch_idx] - 1.0
                )
            
            # 10-day PnL
            if switch_idx + 10 < len(equity_curve):
                pnl_10d.append(
                    equity_curve[switch_idx + 10] / equity_curve[switch_idx] - 1.0
                )
        
        return pnl_5d, pnl_10d
    
    def compute_pnl_positive_rate(self, pnl_list: List[float]) -> float:
        """
        Compute percentage of positive PnL events.
        
        Args:
            pnl_list: List of PnL values
        
        Returns:
            Fraction of positive PnL (0 to 1)
        """
        if not pnl_list:
            return 0.0
        
        positive_count = sum(1 for pnl in pnl_list if pnl > 0)
        return positive_count / len(pnl_list)
    
    def analyze_ramp_vs_binary(
        self,
        metrics_with_ramp: Dict[str, float],
        metrics_without_ramp: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Compare ramp vs binary switching metrics.
        
        Args:
            metrics_with_ramp: Metrics from ramp-based switching
            metrics_without_ramp: Metrics from binary switching
        
        Returns:
            Comparison dict with deltas
        """
        comparison = {}
        
        for key in metrics_with_ramp.keys():
            if key in metrics_without_ramp:
                with_ramp = metrics_with_ramp[key]
                without_ramp = metrics_without_ramp[key]
                
                # Compute delta (percentage change)
                if abs(without_ramp) > 1e-12:
                    delta = (with_ramp - without_ramp) / abs(without_ramp)
                else:
                    delta = 0.0
                
                comparison[f"{key}_with_ramp"] = with_ramp
                comparison[f"{key}_without_ramp"] = without_ramp
                comparison[f"{key}_delta"] = delta
        
        return comparison
    
    def compute_slippage_for_order(
        self,
        order_notional: float,
        adv_notional: float,
        exchange: Exchange = Exchange.HOSE
    ) -> float:
        """
        Compute slippage for a single order.
        
        Args:
            order_notional: Order size in VND
            adv_notional: Average daily volume in VND
            exchange: HOSE or HNX
        
        Returns:
            Slippage in basis points
        """
        return self.slippage_model.compute_slippage_bps(
            order_notional, adv_notional, exchange
        )
    
    def analyze_clamp_rates(
        self,
        clamp_events_ramp: List[bool],
        clamp_events_steady: List[bool]
    ) -> Tuple[float, float]:
        """
        Analyze clamp/reject rates during ramp vs steady-state.
        
        Args:
            clamp_events_ramp: Boolean list of clamp events during ramp periods
            clamp_events_steady: Boolean list of clamp events during steady-state
        
        Returns:
            Tuple of (clamp_rate_ramp, clamp_rate_steady)
        """
        clamp_rate_ramp = (
            sum(clamp_events_ramp) / len(clamp_events_ramp)
            if clamp_events_ramp else 0.0
        )
        clamp_rate_steady = (
            sum(clamp_events_steady) / len(clamp_events_steady)
            if clamp_events_steady else 0.0
        )
        
        return clamp_rate_ramp, clamp_rate_steady
    
    def generate_analysis_report(
        self,
        switch_events: List[SwitchEvent],
        pnl_5d: List[float],
        pnl_10d: List[float],
        clamp_rate_ramp: float,
        clamp_rate_steady: float,
        ramp_vs_binary: Dict[str, float]
    ) -> TransactionCostAnalysis:
        """
        Generate comprehensive transaction cost analysis report.
        
        Args:
            switch_events: List of SwitchEvent objects
            pnl_5d: Post-switch 5-day PnL values
            pnl_10d: Post-switch 10-day PnL values
            clamp_rate_ramp: Clamp rate during ramp periods
            clamp_rate_steady: Clamp rate during steady-state
            ramp_vs_binary: Ramp vs binary comparison metrics
        
        Returns:
            TransactionCostAnalysis report
        """
        total_turnover = sum(event.turnover for event in switch_events)
        total_cost = sum(event.estimated_cost_vnd for event in switch_events)
        avg_turnover = (
            total_turnover / len(switch_events)
            if switch_events else 0.0
        )
        
        pnl_5d_positive_rate = self.compute_pnl_positive_rate(pnl_5d)
        pnl_10d_positive_rate = self.compute_pnl_positive_rate(pnl_10d)
        
        return TransactionCostAnalysis(
            switch_events=switch_events,
            total_turnover=total_turnover,
            total_transaction_cost_vnd=total_cost,
            avg_turnover_per_switch=avg_turnover,
            post_switch_5d_pnl_positive_rate=pnl_5d_positive_rate,
            post_switch_10d_pnl_positive_rate=pnl_10d_positive_rate,
            avg_clamp_rate_during_ramp=clamp_rate_ramp,
            avg_clamp_rate_steady_state=clamp_rate_steady,
            ramp_vs_binary_comparison=ramp_vs_binary
        )
