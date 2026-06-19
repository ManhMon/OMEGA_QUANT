"""Transaction cost overlay - dampens small trades below cost threshold."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class TCostOverlay(WeightOverlay):
    def __init__(self, cost_per_trade_bps: float = 15.0, min_trade_threshold_bps: float = 30.0):
        self.cost_per_trade_bps = cost_per_trade_bps
        self.min_trade_threshold_bps = min_trade_threshold_bps

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.tcost_optimizer_overlay import apply_tcost_overlay
        return apply_tcost_overlay(
            weights,
            cost_per_trade_bps=self.cost_per_trade_bps,
            min_trade_threshold_bps=self.min_trade_threshold_bps
        )
