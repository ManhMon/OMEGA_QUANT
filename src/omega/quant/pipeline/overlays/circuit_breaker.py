"""Circuit breaker overlay - derisk portfolio when CVaR exceeds limit."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class CircuitBreakerOverlay(WeightOverlay):
    def __init__(self, cvar_limit: float = -0.08, derisk_multiplier: float = 0.5, lookback: int = 60):
        self.cvar_limit = cvar_limit
        self.derisk_multiplier = derisk_multiplier
        self.lookback = lookback

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.advanced_breaker_overlay import apply_advanced_circuit_breaker
        port_rets = state.get("portfolio_returns_history", np.array([]))
        if len(port_rets) != len(weights):
            panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
            returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
            returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
            common_idx = weights.index.intersection(returns_pivot.index)
            common_cols = weights.columns.intersection(returns_pivot.columns)
            w_sub = weights.loc[common_idx, common_cols]
            r_sub = returns_pivot.loc[common_idx, common_cols]
            port_rets = (w_sub.to_numpy() * r_sub.to_numpy()).sum(axis=1)
        return apply_advanced_circuit_breaker(
            weights, port_rets,
            cvar_limit=self.cvar_limit,
            derisk_multiplier=self.derisk_multiplier,
            lookback=self.lookback
        )
