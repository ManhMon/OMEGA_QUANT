"""Adaptive sizing overlay - scales positions by capital and ADV liquidity."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class AdaptiveSizingOverlay(WeightOverlay):
    def __init__(self, capital_vnd: float = 1e9):
        self.capital_vnd = capital_vnd

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.adaptive_sizing_overlay import apply_adaptive_sizing
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        adv_series = None
        if "adv_vnd" in panel_flat.columns:
            adv_frame = panel_flat[["date", "symbol", "adv_vnd"]].dropna(subset=["date", "symbol"]).copy()
            adv_frame = adv_frame.sort_values(["symbol", "date"])
            adv_frame["adv_vnd_pit"] = adv_frame.groupby("symbol", sort=False)["adv_vnd"].transform(
                lambda s: s.expanding(min_periods=1).mean().shift(1)
            )
            adv_series = adv_frame.pivot_table(
                index="date",
                columns="symbol",
                values="adv_vnd_pit",
                aggfunc="last",
            ).reindex(index=weights.index, columns=weights.columns)
        return apply_adaptive_sizing(weights, self.capital_vnd, adv_series)
