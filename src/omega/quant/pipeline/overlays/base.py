"""Base interface for post-optimization overlays."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd


class WeightOverlay:
    """Base interface for post-optimization overlays."""
    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        raise NotImplementedError
