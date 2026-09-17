"""Point-in-time safe sentiment alpha scoring."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Mapping

import numpy as np
import pandas as pd


MAX_AGE_DAYS = 90


class SentimentAlphaEngine:
    """Combine baseline signals with age-decayed sentiment adjustments."""

    def __init__(
        self, sentiment_scale: float = 0.05, default_score: float = 0.0,
        sentiment_decay: float = 0.0,
    ) -> None:
        if not math.isfinite(sentiment_decay) or sentiment_decay < 0:
            raise ValueError("sentiment_decay must be finite and non-negative")
        if not math.isfinite(sentiment_scale):
            raise ValueError("sentiment_scale must be finite")
        if not math.isfinite(default_score):
            raise ValueError("default_score must be finite")
        self.sentiment_scale = sentiment_scale
        self.default_score = default_score
        self.sentiment_decay = sentiment_decay

    @staticmethod
    def _validate_pit(
        as_of: datetime, available_at: datetime | pd.Series,
        timestamp: datetime | pd.Series, symbols: pd.Index,
    ) -> None:
        if as_of is None or available_at is None or timestamp is None:
            raise ValueError("PIT violation: as_of/available_at/timestamp required")
        as_of_timestamp = pd.Timestamp(as_of)
        available = SentimentAlphaEngine._normalize_pit_timestamp(available_at, symbols, "available_at")
        observed = SentimentAlphaEngine._normalize_pit_timestamp(timestamp, symbols, "timestamp")
        if (available.dt.tz is None) != (as_of_timestamp.tzinfo is None) or (
            available.dt.tz is None
        ) != (observed.dt.tz is None):
            raise ValueError("PIT violation: timestamps must use compatible timezones")
        if (available > as_of_timestamp).any():
            raise ValueError("PIT violation: available_at must not exceed as_of")
        if (as_of_timestamp > observed).any():
            raise ValueError("PIT violation: as_of must not exceed timestamp")
        if (available >= observed).any():
            raise ValueError("PIT violation: available_at must be strictly less than timestamp")

    @staticmethod
    def _normalize_pit_timestamp(
        value: datetime | pd.Series, symbols: pd.Index, name: str,
    ) -> pd.Series:
        if isinstance(value, pd.Series):
            if value.index.has_duplicates:
                raise ValueError(f"PIT violation: {name} must have unique index")
            values = pd.to_datetime(value).reindex(symbols)
        else:
            values = pd.Series(pd.Timestamp(value), index=symbols)
        if values.isna().any():
            raise ValueError(f"PIT violation: {name} contains NaT")
        return values

    def combine_sentiment_alpha(
        self, base_signals: pd.Series, sentiment_scores: pd.Series, as_of: datetime,
        available_at: datetime | pd.Series, timestamp: datetime | pd.Series,
        sentiment_age_days: float | pd.Series = 0.0, article_counts: pd.Series | None = None,
        sectors: pd.Series | Mapping[str, str] | None = None,
    ) -> pd.Series:
        if base_signals.index.has_duplicates:
            raise ValueError("base_signals must have unique index")
        if not np.isfinite(base_signals.to_numpy(dtype=float)).all():
            raise ValueError("base_signals must be finite")
        self._validate_pit(as_of, available_at, timestamp, base_signals.index)
        if base_signals.empty:
            return pd.Series(dtype=float)
        all_symbols = base_signals.index
        age = self._validate_age(sentiment_age_days, all_symbols)
        aligned_sentiment = sentiment_scores.reindex(all_symbols).fillna(self.default_score)
        clamped = np.clip(aligned_sentiment.to_numpy(dtype=float), -1.0, 1.0)
        decay_factor = np.exp(-self.sentiment_decay * age.to_numpy(dtype=float))
        decay_factor = np.where(age.to_numpy(dtype=float) >= MAX_AGE_DAYS, 0.0, decay_factor)
        adjustment = clamped * self.sentiment_scale * decay_factor
        if article_counts is not None:
            original_counts = article_counts.to_numpy(dtype=float)
            if not np.isfinite(original_counts).all() or (original_counts < 0).any():
                raise ValueError("article_counts must be finite and non-negative")
            counts = article_counts.reindex(all_symbols).fillna(0.0).to_numpy(dtype=float)
            adjustment *= np.log1p(counts)
        adjustment = pd.Series(adjustment, index=all_symbols)
        if sectors is not None:
            sector_series = pd.Series(sectors).reindex(all_symbols).fillna("Unclassified")
            adjustment -= adjustment.groupby(sector_series).transform("mean")
        return (base_signals.astype(float) + adjustment).sort_index()

    @staticmethod
    def _validate_age(sentiment_age_days: float | pd.Series, symbols: pd.Index) -> pd.Series:
        if isinstance(sentiment_age_days, pd.Series):
            if sentiment_age_days.isna().any():
                raise ValueError("sentiment_age_days contains NaN values")
            if sentiment_age_days.index.has_duplicates:
                raise ValueError("sentiment_age_days must have unique index")
            values = sentiment_age_days.to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError("sentiment_age_days must be finite and non-negative")
            return sentiment_age_days.reindex(symbols).fillna(MAX_AGE_DAYS)
        if not math.isfinite(sentiment_age_days) or sentiment_age_days < 0:
            raise ValueError("sentiment_age_days must be finite and non-negative")
        return pd.Series(sentiment_age_days, index=symbols)

    def compute_weighted_allocation(self, signals: pd.Series, target_sum: float = 1.0) -> pd.Series:
        """Convert positive signals into weights normalized to ``target_sum``."""
        if signals.empty:
            return pd.Series(dtype=float)
        positive_signals = np.maximum(signals.values, 0.0)
        total = np.sum(positive_signals)
        weights = positive_signals / total * target_sum if total > 0 else np.zeros_like(positive_signals)
        return pd.Series(weights, index=signals.index)
