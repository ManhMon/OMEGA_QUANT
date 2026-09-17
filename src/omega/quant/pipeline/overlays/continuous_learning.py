"""Continuous learning overlay - triggers retrain when IC decays."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class ContinuousLearningOverlay(WeightOverlay):
    def __init__(self, retrain_threshold_ic: float = 0.01, retrain_lookback: int = 120,
                 retrain_every: int = 60, min_train: int = 252):
        self.retrain_threshold_ic = retrain_threshold_ic
        self.retrain_lookback = retrain_lookback
        self.retrain_every = retrain_every
        self.min_train = min_train

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.continuous_learning_overlay import apply_continuous_learning_overlay
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        feat_cols = [c for c in panel_flat.columns if c.startswith("feature_") or c.startswith("alpha_")]
        if not feat_cols:
            feat_cols = ["composite_signal"]

        features_df = panel_flat.groupby("date")[feat_cols].mean().reindex(weights.index).fillna(0.0)
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        target_returns = returns_pivot.mean(axis=1).to_numpy()

        return apply_continuous_learning_overlay(
            weights, features_df.to_numpy(), target_returns,
            retrain_threshold_ic=self.retrain_threshold_ic,
            retrain_lookback=self.retrain_lookback,
            retrain_every=self.retrain_every,
            min_train=self.min_train
        )
