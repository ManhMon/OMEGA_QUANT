"""Weight smoothing overlay - EMA smoothing to reduce turnover."""
from __future__ import annotations

import logging
from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class WeightSmoothingOverlay(WeightOverlay):
    def __init__(self, ema_alpha: float = 0.05, exposure_blend: float = 0.0):
        """
        Args:
            ema_alpha: EMA decay factor. Lower = smoother (longer half-life).
                       half_life ≈ log(0.5)/log(1-alpha). Default 0.05 ≈ 14-bar half-life.
            exposure_blend: fraction of raw target exposure to blend back in [0, 1].
                           0.0 = pure smoothing (no rescale), 1.0 = old behavior (full rescale).
                           Default 0.0. Use 0.3 if drawdown control needs faster exposure recovery.
        """
        self.ema_alpha = ema_alpha
        self.exposure_blend = float(exposure_blend)

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        smoothed = weights.ewm(alpha=self.ema_alpha, adjust=False).mean()
        if self.exposure_blend > 0.0:
            # Partial rescale: blend raw target exposure with smoothed exposure
            # exposure_blend=0.3 means 30% snap back to raw, 70% EMA-smoothed magnitude
            target_exposure = weights.abs().sum(axis=1)
            current_exposure = smoothed.abs().sum(axis=1).replace(0, 1.0)
            blend_exposure = (
                self.exposure_blend * target_exposure
                + (1.0 - self.exposure_blend) * current_exposure
            )
            smoothed = smoothed.mul(blend_exposure / current_exposure, axis=0)
        # ponytail: full rescale (old behavior) available via exposure_blend=1.0
        logger.info(
            "Weight smoothing applied: ema_alpha=%.2f, exposure_blend=%.2f",
            self.ema_alpha, self.exposure_blend,
        )
        return smoothed
