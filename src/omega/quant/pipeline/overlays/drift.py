"""Drift overlay - detects alpha decay and adjusts exposure."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class DriftOverlay(WeightOverlay):
    def __init__(self, lookback: int = 60, ic_threshold: float = 0.0, drift_exposure: float = 0.5):
        self.lookback = lookback
        self.ic_threshold = ic_threshold
        self.drift_exposure = drift_exposure

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.drift_overlay import apply_drift_overlay
        port_rets = state.get("portfolio_returns_history", np.array([]))
        if len(port_rets) == 0:
            panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
            returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
            returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
            common_idx = weights.index.intersection(returns_pivot.index)
            common_cols = weights.columns.intersection(returns_pivot.columns)
            w_sub = weights.loc[common_idx, common_cols]
            r_sub = returns_pivot.loc[common_idx, common_cols]
            port_rets = (w_sub.to_numpy() * r_sub.to_numpy()).sum(axis=1)
        return apply_drift_overlay(
            weights, port_rets,
            lookback=self.lookback,
            ic_threshold=self.ic_threshold,
            drift_exposure=self.drift_exposure
        )
