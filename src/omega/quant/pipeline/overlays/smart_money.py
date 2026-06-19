"""Smart Money overlay - boosts weights based on institutional flow signals."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class SmartMoneyOverlay(WeightOverlay):
    def __init__(self, boost_scale: float = 0.25):
        self.boost_scale = boost_scale

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.smart_money_overlay import apply_smart_money_overlay, compute_smart_money_features
        panel_idx = panel.set_index(["date", "symbol"]) if "date" in panel.columns else panel
        panel_idx = panel_idx.sort_index()
        res = compute_smart_money_features(panel_idx)
        scores = res["smart_money_score"].groupby(level="symbol").shift(1).fillna(0.0)
        return apply_smart_money_overlay(weights, scores, boost_scale=self.boost_scale)
