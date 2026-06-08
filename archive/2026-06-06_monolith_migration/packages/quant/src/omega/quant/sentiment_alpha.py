"""
OMEGA_QUANT Phase 22.3: Sentiment Alpha Integration
Modular sentiment-driven alpha scoring engine.

Sentiment values ranges:
- [-1.0, 1.0] where 1.0 is extremely bullish, -1.0 is extremely bearish.

Features:
- Alpha scoring: combining baseline signal with sentiment score using sentiment scale.
- Vectorized operations on pandas Series.
- Neutralization support across sectors.
- Strict T-1 lag checks on incoming sentiment timeseries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict
import pandas as pd
import numpy as np


class SentimentAlphaEngine:
    """
    Sentiment alpha signal optimizer and combiner.
    """

    def __init__(
        self,
        sentiment_scale: float = 0.05,
        default_score: float = 0.0
    ):
        self.sentiment_scale = sentiment_scale
        self.default_score = default_score

    @staticmethod
    def _validate_pit(as_of: datetime, available_at: datetime, timestamp: datetime):
        if as_of is None or available_at is None or timestamp is None:
            raise ValueError("PIT violation: as_of/available_at/timestamp required")
        if as_of.date() >= timestamp.date():
            raise ValueError(
                f"PIT violation (T-1): as_of ({as_of.date()}) >= timestamp ({timestamp.date()})"
            )
        if available_at >= timestamp:
            raise ValueError(
                f"PIT violation: available_at ({available_at}) >= timestamp ({timestamp})"
            )

    def combine_sentiment_alpha(
        self,
        base_signals: pd.Series,
        sentiment_scores: pd.Series,
        as_of: datetime,
        available_at: datetime,
        timestamp: datetime
    ) -> pd.Series:
        """
        Combine baseline signals with sentiment scores using vectorization.

        Formula:
            combined_signal = base_signal + (sentiment_score * sentiment_scale)
            
        Args:
            base_signals: pd.Series of baseline scores index=symbol
            sentiment_scores: pd.Series of sentiment values index=symbol [-1.0, 1.0]
            as_of: market/sentiment data timestamp
            available_at: availability timestamp
            timestamp: current run timestamp
        """
        self._validate_pit(as_of=as_of, available_at=available_at, timestamp=timestamp)

        if base_signals.empty:
            return pd.Series(dtype=float)

        all_symbols = base_signals.index
        aligned_sentiment = sentiment_scores.reindex(all_symbols, fill_value=self.default_score)

        # Clamping sentiment to [-1.0, 1.0] bounds
        clamped_sentiment = np.clip(aligned_sentiment.values, -1.0, 1.0)

        combined = base_signals.values + (clamped_sentiment * self.sentiment_scale)
        return pd.Series(combined, index=all_symbols)

    def compute_weighted_allocation(
        self,
        signals: pd.Series,
        target_sum: float = 1.0
    ) -> pd.Series:
        """
        Convert signals into weights (only positive weights, normalized to target_sum).
        Uses simple soft-thresholding.
        """
        if signals.empty:
            return pd.Series(dtype=float)

        # Soft-threshold positive weights only
        pos_signals = np.maximum(signals.values, 0.0)
        total = np.sum(pos_signals)
        if total > 0:
            weights = (pos_signals / total) * target_sum
        else:
            weights = np.zeros_like(pos_signals)

        return pd.Series(weights, index=signals.index)
