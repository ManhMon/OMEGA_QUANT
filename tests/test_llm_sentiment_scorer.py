from datetime import datetime, timedelta, timezone

import pytest

from src.omega.data.llm_sentiment_scorer import LLMSentimentScorer


def test_lexicon_fallback_score():
    result = LLMSentimentScorer().score("Công ty tăng lợi nhuận tích cực")
    assert result.provenance.tier == "lexicon"
    assert result.score > 0
    assert result.label == "positive"


def test_llm_tier_used():
    result = LLMSentimentScorer(lambda _: -0.8).score("tin tức")
    assert result.provenance.tier == "llm"


def test_llm_failure_falls_back():
    def fail(_):
        raise RuntimeError("failure")

    result = LLMSentimentScorer(fail).score("Công ty tăng lợi nhuận tích cực")
    assert result.provenance.tier == "lexicon"


def test_llm_invalid_score_falls_back():
    result = LLMSentimentScorer(lambda _: "invalid").score("Công ty tăng lợi nhuận tích cực")
    assert result.provenance.tier == "lexicon"


def test_event_time_recorded():
    result = LLMSentimentScorer().score("tin tức")
    assert result.provenance.event_time is not None


def test_semantic_duplicate_48_hours():
    scorer = LLMSentimentScorer()
    t0 = datetime.now(timezone.utc)
    assert scorer.is_semantic_duplicate("tin tức tăng lợi nhuận", t0, t0) is False
    assert scorer.is_semantic_duplicate("tin tức tăng lợi nhuận", t0, t0 + timedelta(hours=47)) is True
    assert scorer.is_semantic_duplicate("tin tức tăng lợi nhuận", t0, t0 + timedelta(hours=49)) is False


def test_pit_safety_cutoff_enforcement():
    scorer = LLMSentimentScorer()
    cutoff = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        scorer.score("tin tức", event_time=cutoff + timedelta(seconds=1), cutoff_at=cutoff)
    result = scorer.score("tin tức", event_time=cutoff, cutoff_at=cutoff)
    assert result.provenance.cutoff_at == cutoff.isoformat()


def test_provenance_schema_present():
    result = LLMSentimentScorer().score("tin tức")
    assert result.provenance is not None


def test_real_vietnamese_unicode_lexicon_terms():
    result = LLMSentimentScorer().score("Doanh nghiệp tăng trưởng, lợi nhuận tích cực")
    assert result.provenance.tier == "lexicon"
    assert result.label == "positive"


def test_utf8_lexicon_handles_diacritic_terms():
    result = LLMSentimentScorer().score("Doanh nghiệp giảm tiêu cực vì thua lỗ")
    assert result.provenance.tier == "lexicon"
    assert result.score < 0
    assert result.label == "negative"
    assert result.provenance.parser_version


def test_llm_non_finite_score_falls_back():
    result = LLMSentimentScorer(lambda _: float("nan")).score("Công ty tăng lợi nhuận tích cực")
    assert result.provenance.tier == "lexicon"
