"""Tail control overlay - vol targeting, max weight capping, drawdown scaling."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay
from omega.quant.portfolio.tail_controls import apply_tail_controls


class TailControlOverlay(WeightOverlay):
    def __init__(self, target_vol_ann: float = 0.15, max_abs_weight: float = 0.05,
                 dd_window: int = 20, dd_threshold: float = 0.08, dd_cut: float = 0.5,
                 soft_brake_enabled: bool = False,
                 soft_brake_base_threshold: float = 0.05,
                 soft_brake_min_scale: float = 0.1,
                 soft_brake_depth: float = 2.0,
                 soft_brake_vol_sensitivity: float = 1.0):
        self.target_vol_ann = target_vol_ann
        self.max_abs_weight = max_abs_weight
        self.dd_window = dd_window
        self.dd_threshold = dd_threshold
        self.dd_cut = dd_cut
        self.soft_brake_enabled = soft_brake_enabled
        self.soft_brake_base_threshold = soft_brake_base_threshold
        self.soft_brake_min_scale = soft_brake_min_scale
        self.soft_brake_depth = soft_brake_depth
        self.soft_brake_vol_sensitivity = soft_brake_vol_sensitivity

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        warmup = state.get("warmup_history")
        adj_w, _ = apply_tail_controls(
            weights, returns_pivot.to_numpy(),
            target_vol_ann=self.target_vol_ann,
            max_abs_weight=self.max_abs_weight,
            dd_window=self.dd_window,
            dd_threshold=self.dd_threshold,
            dd_cut=self.dd_cut,
            warmup_history=warmup,
            soft_brake_enabled=self.soft_brake_enabled,
            soft_brake_base_threshold=self.soft_brake_base_threshold,
            soft_brake_min_scale=self.soft_brake_min_scale,
            soft_brake_depth=self.soft_brake_depth,
            soft_brake_vol_sensitivity=self.soft_brake_vol_sensitivity,
        )
        return adj_w
