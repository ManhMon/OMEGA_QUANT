"""Weight smoothing overlay - EMA smoothing to reduce turnover."""
from __future__ import annotations

import logging
from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class WeightSmoothingOverlay(WeightOverlay):
    def __init__(self, ema_alpha: float = 0.2):
        self.ema_alpha = ema_alpha

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        smoothed = weights.ewm(alpha=self.ema_alpha, adjust=False).mean()
        target_exposure = weights.abs().sum(axis=1)
        current_exposure = smoothed.abs().sum(axis=1).replace(0, 1.0)
        smoothed = smoothed.mul(target_exposure / current_exposure, axis=0)
        logger.info("Weight smoothing applied: ema_alpha=%.2f", self.ema_alpha)
        return smoothed
