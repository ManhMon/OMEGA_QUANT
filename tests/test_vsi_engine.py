"""Unit tests for Vietnam Sentiment Index (VSI) Engine."""

import pytest
from datetime import datetime, timedelta
from omega.quant.sentiment.vsi_engine import (
    SentimentData,
    SentimentPolarity,
    VSILevel,
    VSIPortfolioEngine
)


def test_sentiment_dictionary_matching() -> None:
    engine = VSIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    # 1. Bullish test
    bull_data = [
        SentimentData(
            text="thị trường bứt phá mạnh, dòng tiền mạnh đẩy nhiều bluechip tăng trần",
            source="CafeF",
            published_at=as_of,
            as_of_time=as_of
        )
    ]
    scores = engine.calculate_sentiment(bull_data)
    assert len(scores) == 1
    assert scores[0].raw_score > 0
    assert scores[0].polarity == SentimentPolarity.BULLISH
    
    # 2. Bearish test
    bear_data = [
        SentimentData(
            text="áp lực bán tháo diện rộng khiến nhiều cổ phiếu giảm sàn và giải chấp margin call",
            source="Vietstock",
            published_at=as_of,
            as_of_time=as_of
        )
    ]
    scores = engine.calculate_sentiment(bear_data)
    assert len(scores) == 1
    assert scores[0].raw_score < 0
    assert scores[0].polarity == SentimentPolarity.BEARISH
    
    # 3. Neutral test
    neutral_data = [
        SentimentData(
            text="thị trường sideway đi ngang không rõ xu hướng",
            source="VnExpress",
            published_at=as_of,
            as_of_time=as_of
        )
    ]
    scores = engine.calculate_sentiment(neutral_data)
    assert len(scores) == 1
    assert scores[0].polarity == SentimentPolarity.NEUTRAL


def test_vsi_index_aggregation() -> None:
    engine = VSIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    data = [
        SentimentData(text="bứt phá tăng trần", source="CafeF", published_at=as_of, as_of_time=as_of),
        SentimentData(text="dòng tiền mạnh bluechip tăng", source="CafeF", published_at=as_of, as_of_time=as_of),
        SentimentData(text="giảm sàn bán tháo", source="Vietstock", published_at=as_of, as_of_time=as_of),
    ]
    
    scores = engine.calculate_sentiment(data)
    vsi = engine.calculate_vsi(scores, as_of)
    
    assert vsi.article_count == 3
    # Two positive articles, one negative -> overall positive
    assert vsi.score > 50.0
    assert vsi.level in (VSILevel.GREED, VSILevel.EXTREME_GREED, VSILevel.NEUTRAL)
    assert vsi.timestamp == as_of


def test_pit_safety_validation() -> None:
    engine = VSIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    future_time = as_of + timedelta(hours=1)  # Future published date
    
    data = [
        SentimentData(
            text="tăng mạnh bứt phá",
            source="CafeF",
            published_at=future_time,
            as_of_time=as_of
        )
    ]
    
    with pytest.raises(ValueError, match="is after as_of_time"):
        engine.calculate_sentiment(data)
