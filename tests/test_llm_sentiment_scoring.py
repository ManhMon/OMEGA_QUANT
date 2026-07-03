import sys
from pathlib import Path
from unittest.mock import patch

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import run_sentiment_enrichment as sentiment


def test_default_llm_models_match_latest_supported_values():
    assert sentiment.DEFAULT_GEMINI_MODEL == "gemini-3.5-flash"
    assert sentiment.DEFAULT_OPENAI_MODEL == "gpt-4o"


def test_llm_cache_hit_skips_api_call():
    cache = {
        sentiment.build_cache_key("FPT tăng trưởng lợi nhuận", "FPT"): {
            "headline": "FPT tăng trưởng lợi nhuận",
            "ticker": "FPT",
            "score": 0.77,
        }
    }

    def fail_if_called(headline, ticker):
        raise AssertionError("LLM scorer should not be called on cache hit")

    score = sentiment.score_headline_with_llm_cache(
        "FPT tăng trưởng lợi nhuận",
        "FPT",
        cache,
        llm_scorer=fail_if_called,
    )

    assert score == 0.77


def test_llm_cache_miss_stores_api_score():
    cache = {}
    calls = []

    def fake_llm(headline, ticker):
        calls.append((headline, ticker))
        return 0.42

    score = sentiment.score_headline_with_llm_cache(
        "VCB bứt phá mạnh",
        "VCB",
        cache,
        llm_scorer=fake_llm,
    )

    assert score == 0.42
    assert calls == [("VCB bứt phá mạnh", "VCB")]
    assert cache[sentiment.build_cache_key("VCB bứt phá mạnh", "VCB")]["score"] == 0.42


def test_llm_cache_file_round_trip_serialization(tmp_path):
    cache_path = tmp_path / ".ly_state" / "session" / "llm_sentiment_cache.json"

    loaded = sentiment.load_llm_cache(cache_path)

    assert loaded == {}
    assert cache_path.exists()

    cache = {
        sentiment.build_cache_key("FPT tăng trưởng lợi nhuận", "FPT"): {
            "headline": "FPT tăng trưởng lợi nhuận",
            "ticker": "FPT",
            "score": 0.77,
        }
    }
    sentiment.save_llm_cache(cache, cache_path)

    assert sentiment.load_llm_cache(cache_path) == cache


def test_parse_openai_like_response_content():
    assert sentiment.parse_llm_score("0.63") == 0.63
    assert sentiment.parse_llm_score("Sentiment: -0.35") == -0.35


def test_openai_provider_respects_custom_base_url(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "0.25"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:3000/v1/")
    monkeypatch.setenv("OPENAI_SENTIMENT_MODEL", "router-model")
    monkeypatch.setattr(sentiment.requests, "post", fake_post)

    score = sentiment._post_openai_sentiment("VCB tang truong loi nhuan", "VCB")

    assert score == 0.25
    assert captured["url"] == "http://127.0.0.1:3000/v1/chat/completions"
    assert captured["kwargs"]["json"]["model"] == "router-model"


def test_openai_provider_falls_back_to_omega_llm_env(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "0.11"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_SENTIMENT_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "omega-key")
    monkeypatch.setenv("OMEGA_LLM_BASE_URL", "http://127.0.0.1:4000/v1/")
    monkeypatch.setenv("OMEGA_LLM_MODEL", "omega-model")
    monkeypatch.setattr(sentiment.requests, "post", fake_post)

    score = sentiment._post_openai_sentiment("VCB tang truong loi nhuan", "VCB")

    assert score == 0.11
    assert captured["url"] == "http://127.0.0.1:4000/v1/chat/completions"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer omega-key"
    assert captured["kwargs"]["json"]["model"] == "omega-model"


def test_request_llm_sentiment_detects_omega_openai_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "omega-key")

    with patch.object(sentiment, "_post_openai_sentiment", return_value=0.5) as mock_openai:
        score = sentiment.request_llm_sentiment("VCB tang truong loi nhuan", "VCB")

    assert score == 0.5
    mock_openai.assert_called_once_with("VCB tang truong loi nhuan", "VCB")


def test_extract_ticker_scores_falls_back_to_keywords_when_llm_fails():
    articles = [{"headline": "HPG tăng trần sau tin tích cực", "tickers": ["HPG"]}]

    with patch.object(sentiment, "request_llm_sentiment", side_effect=RuntimeError("api down")):
        scores = sentiment.extract_ticker_scores(
            articles,
            use_llm=True,
            cache={},
            llm_scorer=sentiment.request_llm_sentiment,
        )

    assert scores["HPG"] == 1.0
