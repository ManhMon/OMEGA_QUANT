"""Transaction cost overlay - dampens small trades below cost threshold.

Supports dynamic turnover budgeting with regime IC scaling.
PIT-safe: all parameters use only current/past data.
"""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class TCostOverlay(WeightOverlay):
    """Transaction cost overlay with dynamic parameter support.

    Args:
        cost_per_trade_bps: Round-trip cost in bps.
        min_trade_threshold_bps: Base minimum trade threshold in bps.
        use_dynamic_budgeting: If True, use regime IC to dynamically
            adjust the trade threshold (cost-reduction lever #3).
        ic_lookback: Rolling window for IC computation (days).
    """

    def __init__(
        self,
        cost_per_trade_bps: float = 15.0,
        min_trade_threshold_bps: float = 30.0,
        use_dynamic_budgeting: bool = False,
        ic_lookback: int = 20,
    ):
        self.cost_per_trade_bps = cost_per_trade_bps
        self.min_trade_threshold_bps = min_trade_threshold_bps
        self.use_dynamic_budgeting = use_dynamic_budgeting
        self.ic_lookback = ic_lookback

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        if self.use_dynamic_budgeting:
            from omega.quant.portfolio.tcost_optimizer_overlay import apply_dynamic_tcost_overlay
            # Extract returns from panel for IC computation
            panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
            returns_pivot = panel_flat.pivot_table(
                index="date", columns="symbol", values="returns"
            ).fillna(0.0)
            returns_pivot = returns_pivot.reindex(
                index=weights.index, columns=weights.columns, fill_value=0.0
            )
            return apply_dynamic_tcost_overlay(
                weights,
                daily_returns=returns_pivot,
                cost_per_trade_bps=self.cost_per_trade_bps,
                base_threshold_bps=self.min_trade_threshold_bps,
                ic_lookback=self.ic_lookback,
            )
        else:
            from omega.quant.portfolio.tcost_optimizer_overlay import apply_tcost_overlay
            return apply_tcost_overlay(
                weights,
                cost_per_trade_bps=self.cost_per_trade_bps,
                min_trade_threshold_bps=self.min_trade_threshold_bps,
            )
