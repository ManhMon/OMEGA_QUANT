"""Contagion overlay - reduces exposure during cross-asset contagion spikes."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class ContagionOverlay(WeightOverlay):
    def __init__(self, lookback: int = 60, spike_threshold_std: float = 2.0, spike_exposure: float = 0.5):
        self.lookback = lookback
        self.spike_threshold_std = spike_threshold_std
        self.spike_exposure = spike_exposure

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.contagion_overlay import apply_contagion_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        return apply_contagion_overlay(
            weights, returns_pivot.to_numpy(),
            lookback=self.lookback,
            spike_threshold_std=self.spike_threshold_std,
            spike_exposure=self.spike_exposure
        )
