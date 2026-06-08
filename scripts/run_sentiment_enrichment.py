#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sprint 4: Daily Sentiment Enrichment Step

Fetches recent news articles, computes keyword-based sentiment scores
per ticker, and saves results for downstream signal generation.

PIT Safety: Uses as_of_time=now, only processes articles from the past 24h.

Author: Backend Engineer (Role 9)
Date: 2026-05-29
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Path setup for project imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import pandas as pd

try:
    from omega.data.news_aggregator import NewsAggregator
except ImportError:
    NewsAggregator = None

try:
    from omega.quant.sentiment_alpha import SentimentAlphaEngine
except ImportError:
    SentimentAlphaEngine = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] SENTIMENT: %(message)s",
)
logger = logging.getLogger("sentiment_enrichment")

# --- Keyword dictionaries (Vietnamese market context) ---
BULLISH_KEYWORDS = ["tang", "tich cuc", "loi nhuan", "tang truong", "dot pha"]
BEARISH_KEYWORDS = ["giam", "tieu cuc", "lo", "sut giam", "rui ro"]

OUTPUT_DIR = PROJECT_ROOT / ".ly_state" / "session"


def score_headline(headline: str) -> float:
    """Score a single headline using keyword matching.

    Returns a float in [-1, 1] range.
    """
    text = headline.lower()
    bullish_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bearish_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    total = bullish_hits + bearish_hits
    if total == 0:
        return 0.0
    return round((bullish_hits - bearish_hits) / total, 4)


def extract_ticker_scores(articles: list) -> dict:
    """Aggregate sentiment scores per ticker from article list.

    Each article is expected to have 'headline' and 'tickers' fields.
    Returns dict of ticker -> average sentiment score.
    """
    from collections import defaultdict

    ticker_scores = defaultdict(list)

    for article in articles:
        headline = article.get("headline", "") or article.get("title", "")
        tickers = article.get("tickers", [])
        if not headline:
            continue

        score = score_headline(headline)

        # If article has explicit ticker list, use it
        if tickers:
            for ticker in tickers:
                ticker_scores[ticker].append(score)
        else:
            # Fallback: check if any known ticker symbol appears in headline
            # This is a simple heuristic; production would use NER
            text_upper = headline.upper()
            # Common VN tickers to scan for
            common_tickers = [
                "VNM", "FPT", "VIC", "VHM", "HPG", "MSN", "MWG",
                "TCB", "VCB", "BID", "CTG", "MBB", "ACB", "STB",
                "VNI", "SSI", "HCM", "VND", "PNJ", "REE", "DGC",
            ]
            for ticker in common_tickers:
                if ticker in text_upper:
                    ticker_scores[ticker].append(score)

    # Average scores per ticker
    result = {}
    for ticker, scores in ticker_scores.items():
        if scores:
            result[ticker] = round(sum(scores) / len(scores), 4)

    return result


def run_sentiment_enrichment() -> int:
    """Main entry point. Returns exit code (0=success, 1=error)."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    logger.info(f"=== SENTIMENT ENRICHMENT START ({today_str}) ===")

    # --- Fetch news articles (PIT safe: as_of_time=now) ---
    articles = []

    if NewsAggregator is not None:
        try:
            aggregator = NewsAggregator()
            articles = aggregator.fetch_recent_news(as_of_time=now)
            logger.info(f"Fetched {len(articles)} articles via NewsAggregator")
        except Exception as e:
            logger.warning(f"NewsAggregator failed: {e}. Falling back to empty set.")
            articles = []
    else:
        logger.warning(
            "NewsAggregator not available (import failed). "
            "No articles to process."
        )

    if not articles:
        logger.info("No articles available. Writing empty scores.")
        output = {
            "date": today_str,
            "scores": {},
            "num_articles": 0,
            "generated_at": now.isoformat(),
        }
    else:
        # --- Compute sentiment scores per ticker ---
        ticker_scores = extract_ticker_scores(articles)
        logger.info(
            f"Computed sentiment for {len(ticker_scores)} tickers "
            f"from {len(articles)} articles"
        )

        output = {
            "date": today_str,
            "scores": ticker_scores,
            "num_articles": len(articles),
            "generated_at": now.isoformat(),
        }

    # --- Save output ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "sentiment_scores.json"

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved sentiment scores to {output_path}")
    except IOError as e:
        logger.error(f"Failed to write sentiment scores: {e}")
        return 1

    logger.info(f"=== SENTIMENT ENRICHMENT COMPLETE ({len(articles)} articles) ===")
    return 0


if __name__ == "__main__":
    exit_code = run_sentiment_enrichment()
    sys.exit(exit_code)
