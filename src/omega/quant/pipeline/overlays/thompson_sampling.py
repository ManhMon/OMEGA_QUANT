"""Thompson sampling overlay - Bayesian exploration/exploitation weight adjustment."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class ThompsonSamplingWeightOverlay(WeightOverlay):
    def __init__(self, lookback: int = 20, update_every: int = 5):
        self.lookback = lookback
        self.update_every = update_every

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.thompson_sampling_overlay import apply_thompson_sampling_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_thompson_sampling_overlay(
            weights, returns_pivot,
            lookback=self.lookback,
            update_every=self.update_every
        )
