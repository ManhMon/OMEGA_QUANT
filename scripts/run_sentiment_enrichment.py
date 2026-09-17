#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sprint 4: Daily Sentiment Enrichment Step

Fetches recent news articles, computes keyword-based sentiment scores
per ticker, and saves results for downstream signal generation.

PIT Safety: Uses as_of_time=now, only processes articles within hours_back.

Author: Backend Engineer (Role 9)
Date: 2026-06-19
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests


def _configure_utf8_stdio() -> None:
    if not sys.platform.startswith("win"):
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


_configure_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

try:
    from omega.data.news_aggregator import NewsAggregator, infer_tickers_from_text
except ImportError:
    NewsAggregator = None
    infer_tickers_from_text = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] SENTIMENT: %(message)s",
)
logger = logging.getLogger("sentiment_enrichment")

BULLISH_KEYWORDS = [
    "tang", "tăng", "tich cuc", "tích cực", "loi nhuan", "lợi nhuận",
    "tang truong", "tăng trưởng", "dot pha", "đột phá", "tăng trần",
]
BEARISH_KEYWORDS = [
    "giam", "giảm", "tieu cuc", "tiêu cực", "lo", "lỗ",
    "sut giam", "sụt giảm", "rui ro", "rủi ro",
]

OUTPUT_DIR = PROJECT_ROOT / ".ly_state" / "session"
CACHE_PATH = OUTPUT_DIR / "llm_sentiment_cache.json"

DEFAULT_HOURS_BACK = 240  # 10 days
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT_SECONDS = 30


def build_cache_key(headline: str, ticker: Optional[str]) -> str:
    normalized = re.sub(r"\s+", " ", headline.strip().lower())
    raw_key = f"{(ticker or '').upper()}::{normalized}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def load_llm_cache(cache_path: Path = CACHE_PATH) -> dict:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        cache_path.write_text("{}\n", encoding="utf-8")
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (IOError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read LLM cache %s: %s", cache_path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_llm_cache(cache: dict, cache_path: Path = CACHE_PATH) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def parse_llm_score(value: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError(f"No numeric sentiment score found in response: {value!r}")
    score = float(match.group(0))
    return max(-1.0, min(1.0, round(score, 4)))


def _build_llm_prompt(headline: str, ticker: Optional[str]) -> str:
    ticker_text = ticker or "UNKNOWN"
    return (
        "Score the sentiment of this Vietnam equity market news headline for the given ticker. "
        "Return only one float between -1.0 and 1.0. "
        "-1.0 = very bearish, 0.0 = neutral, 1.0 = very bullish.\n"
        f"Ticker: {ticker_text}\n"
        f"Headline: {headline}"
    )


def resolve_openai_base_url() -> str:
    return (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OMEGA_LLM_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_OPENAI_BASE_URL
    ).rstrip("/")


def resolve_openai_api_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY") or os.getenv("OMEGA_LLM_API_KEY")


def resolve_openai_model() -> str:
    return os.getenv("OPENAI_SENTIMENT_MODEL") or os.getenv("OMEGA_LLM_MODEL") or DEFAULT_OPENAI_MODEL


def _post_openai_sentiment(headline: str, ticker: Optional[str]) -> float:
    api_key = resolve_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = resolve_openai_model()
    response = requests.post(
        f"{resolve_openai_base_url()}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a financial sentiment scoring function. Output a single float only.",
                },
                {"role": "user", "content": _build_llm_prompt(headline, ticker)},
            ],
            "temperature": 0,
            "max_tokens": 16,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return parse_llm_score(content)


def _post_gemini_sentiment(headline: str, ticker: Optional[str]) -> float:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = os.getenv("GEMINI_SENTIMENT_MODEL", DEFAULT_GEMINI_MODEL)
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "You are a financial sentiment scoring function. Output a single float only.\n"
                                + _build_llm_prompt(headline, ticker)
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 16},
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    content = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_llm_score(content)


def request_llm_sentiment(headline: str, ticker: Optional[str]) -> float:
    provider = os.getenv("LLM_SENTIMENT_PROVIDER", "auto").lower()
    providers = []
    if provider == "openai":
        providers = [_post_openai_sentiment]
    elif provider == "gemini":
        providers = [_post_gemini_sentiment]
    else:
        if resolve_openai_api_key():
            providers.append(_post_openai_sentiment)
        if os.getenv("GEMINI_API_KEY"):
            providers.append(_post_gemini_sentiment)

    if not providers:
        raise RuntimeError("No LLM sentiment provider configured")

    last_error = None
    for provider_fn in providers:
        try:
            return provider_fn(headline, ticker)
        except Exception as exc:
            last_error = exc
            logger.warning("LLM sentiment provider failed: %s", exc)
    raise RuntimeError(f"All LLM sentiment providers failed: {last_error}")


def score_headline(headline: str) -> float:
    """Score a single headline using keyword matching. Returns float in [-1, 1]."""
    text = headline.lower()
    bullish_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bearish_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    total = bullish_hits + bearish_hits
    if total == 0:
        return 0.0
    return round((bullish_hits - bearish_hits) / total, 4)


def score_headline_with_llm_cache(
    headline: str,
    ticker: Optional[str],
    cache: dict,
    llm_scorer: Callable[[str, Optional[str]], float] = request_llm_sentiment,
) -> float:
    cache_key = build_cache_key(headline, ticker)
    cached_entry = cache.get(cache_key)
    if isinstance(cached_entry, dict) and "score" in cached_entry:
        return float(cached_entry["score"])

    score = llm_scorer(headline, ticker)
    cache[cache_key] = {
        "headline": headline,
        "ticker": ticker,
        "score": round(score, 4),
    }
    return round(score, 4)


def extract_ticker_scores(
    articles: list,
    use_llm: bool = False,
    cache: Optional[dict] = None,
    llm_scorer: Callable[[str, Optional[str]], float] = request_llm_sentiment,
) -> dict:
    """Aggregate sentiment scores per ticker from article list.

    Each article is a dict with 'headline' (or 'title') and optional 'tickers'.
    Returns dict of ticker -> average sentiment score.
    """
    ticker_scores = defaultdict(list)
    cache = cache if cache is not None else {}

    for article in articles:
        headline = article.get("headline", "") or article.get("title", "") or article.get("text", "")
        tickers = article.get("tickers", [])
        if not headline:
            continue

        resolved_tickers = tickers or (infer_tickers_from_text(headline) if infer_tickers_from_text else [])
        if not resolved_tickers:
            continue

        for ticker in resolved_tickers:
            if use_llm:
                try:
                    score = score_headline_with_llm_cache(headline, ticker, cache, llm_scorer)
                except Exception as exc:
                    logger.warning("LLM sentiment scoring failed for %s: %s. Falling back to keywords.", ticker, exc)
                    score = score_headline(headline)
            else:
                score = score_headline(headline)
            ticker_scores[ticker].append(score)

    return {
        ticker: round(sum(scores) / len(scores), 4)
        for ticker, scores in ticker_scores.items()
        if scores
    }


def run_sentiment_enrichment(hours_back: int = DEFAULT_HOURS_BACK, use_llm: bool = False) -> int:
    """Main entry point. Returns exit code (0=success, 1=error)."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    logger.info("=== SENTIMENT ENRICHMENT START (%s, hours_back=%d) ===", today_str, hours_back)

    articles = []
    cache = load_llm_cache() if use_llm else {}

    if NewsAggregator is not None:
        try:
            aggregator = NewsAggregator()
            raw_articles = aggregator.fetch_recent_news(as_of_time=now, hours_back=hours_back)
            articles = [
                {
                    "headline": item.text,
                    "title": item.text,
                    "source": item.source,
                    "timestamp": item.timestamp.isoformat(),
                    "tickers": [item.ticker] if item.ticker else [],
                }
                for item in raw_articles
            ]
            logger.info("Fetched %d articles via NewsAggregator", len(articles))
        except Exception as exc:
            logger.warning("NewsAggregator failed: %s. Falling back to empty set.", exc)
            articles = []
    else:
        logger.warning("NewsAggregator not available (import failed). No articles to process.")

    if not articles:
        logger.info("No articles available. Writing empty scores.")
        output = {
            "date": today_str,
            "scores": {},
            "num_articles": 0,
            "hours_back": hours_back,
            "generated_at": now.isoformat(),
        }
    else:
        ticker_scores = extract_ticker_scores(articles, use_llm=use_llm, cache=cache)
        logger.info(
            "Computed sentiment for %d tickers from %d articles",
            len(ticker_scores), len(articles),
        )
        output = {
            "date": today_str,
            "scores": ticker_scores,
            "num_articles": len(articles),
            "hours_back": hours_back,
            "scoring_method": "llm" if use_llm else "keyword",
            "generated_at": now.isoformat(),
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "sentiment_scores.json"
    archive_path = OUTPUT_DIR / f"sentiment_scores_{today_str}.json"

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, ensure_ascii=False)
        logger.info("Saved sentiment scores to %s", output_path)

        with open(archive_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, ensure_ascii=False)
        logger.info("Archived sentiment scores to %s", archive_path)

        if use_llm:
            save_llm_cache(cache)
            logger.info("Saved LLM sentiment cache to %s", CACHE_PATH)
    except IOError as exc:
        logger.error("Failed to write sentiment scores: %s", exc)
        return 1

    logger.info("=== SENTIMENT ENRICHMENT COMPLETE (%d articles) ===", len(articles))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sentiment enrichment pipeline")
    parser.add_argument(
        "--hours-back",
        type=int,
        default=DEFAULT_HOURS_BACK,
        help=f"Lookback window in hours (default: {DEFAULT_HOURS_BACK})",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM sentiment scoring with local cache and keyword fallback",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = run_sentiment_enrichment(hours_back=args.hours_back, use_llm=args.use_llm)
    sys.exit(exit_code)
