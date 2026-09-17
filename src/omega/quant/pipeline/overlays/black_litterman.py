"""Black-Litterman overlay - blends market-implied views with alpha signals."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class BlackLittermanOverlay(WeightOverlay):
    def __init__(self, tau: float = 0.05, view_confidence: float = 0.5,
                 l2_reg: float = 0.01, max_weight: float = 0.05):
        self.tau = tau
        self.view_confidence = view_confidence
        self.l2_reg = l2_reg
        self.max_weight = max_weight

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.black_litterman_overlay import apply_black_litterman_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        sig_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="composite_signal").fillna(0.0)
        sig_pivot = sig_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_black_litterman_overlay(
            weights, returns_pivot.to_numpy(), sig_pivot.to_numpy(),
            tau=self.tau, view_confidence=self.view_confidence,
            l2_reg=self.l2_reg, max_weight=self.max_weight
        )
