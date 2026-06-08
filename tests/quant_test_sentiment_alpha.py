import pytest
import pandas as pd
from datetime import datetime, timezone

from omega.quant.sentiment_alpha import SentimentAlphaEngine


def test_sentiment_alpha_combination_vectorized():
    engine = SentimentAlphaEngine(sentiment_scale=0.1)

    base = pd.Series([0.05, 0.12, -0.04], index=["VNM", "HPG", "VIC"])
    sentiment = pd.Series([0.5, -0.8, 1.2], index=["VNM", "HPG", "VIC"])

    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

    # VIC's sentiment 1.2 is clamped to 1.0. Scale = 0.1
    # VNM expected: 0.05 + 0.5 * 0.1 = 0.10
    # HPG expected: 0.12 + -0.8 * 0.1 = 0.04
    # VIC expected: -0.04 + 1.0 * 0.1 = 0.06
    combined = engine.combine_sentiment_alpha(
        base_signals=base,
        sentiment_scores=sentiment,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )

    assert abs(combined["VNM"] - 0.10) < 1e-6
    assert abs(combined["HPG"] - 0.04) < 1e-6
    assert abs(combined["VIC"] - 0.06) < 1e-6


def test_compute_weighted_allocation_positive_only():
    engine = SentimentAlphaEngine()

    signals = pd.Series([-0.05, 0.08, 0.04], index=["VIC", "VNM", "HPG"])

    # Sum of positives: 0.08 + 0.04 = 0.12
    # VNM expected weight: 0.08 / 0.12 * 1.0 = 0.66667
    # HPG expected weight: 0.04 / 0.12 * 1.0 = 0.33333
    # VIC expected weight: 0.0 (negative)
    weights = engine.compute_weighted_allocation(signals, target_sum=1.0)

    assert weights["VIC"] == 0.0
    assert abs(weights["VNM"] - 0.6666666) < 1e-5
    assert abs(weights["HPG"] - 0.3333333) < 1e-5


def test_sentiment_alpha_engine_pit_violation_available_at_raises():
    engine = SentimentAlphaEngine()

    base = pd.Series([0.05], index=["VNM"])
    sentiment = pd.Series([0.5], index=["VNM"])

    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    # available_at after timestamp => violation
    available_at = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="PIT violation"):
        engine.combine_sentiment_alpha(
            base_signals=base,
            sentiment_scores=sentiment,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )
