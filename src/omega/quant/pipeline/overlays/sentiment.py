"""Sentiment overlay - boosts weights based on sentiment proxy signals."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class SentimentOverlay(WeightOverlay):
    def __init__(self, boost_scale: float = 0.2):
        self.boost_scale = boost_scale

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.sentiment_overlay import apply_sentiment_overlay, compute_sentiment_proxy
        panel_idx = panel.set_index(["date", "symbol"]) if "date" in panel.columns else panel
        panel_idx = panel_idx.sort_index()
        res_sent = compute_sentiment_proxy(panel_idx)
        scores = res_sent.groupby(level="symbol").shift(1).fillna(0.0)
        return apply_sentiment_overlay(weights, scores, boost_scale=self.boost_scale)
