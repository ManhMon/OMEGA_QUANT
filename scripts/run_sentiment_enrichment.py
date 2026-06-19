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
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

try:
    from omega.data.news_aggregator import NewsAggregator
except ImportError:
    NewsAggregator = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] SENTIMENT: %(message)s",
)
logger = logging.getLogger("sentiment_enrichment")

BULLISH_KEYWORDS = ["tang", "tich cuc", "loi nhuan", "tang truong", "dot pha"]
BEARISH_KEYWORDS = ["giam", "tieu cuc", "lo", "sut giam", "rui ro"]

OUTPUT_DIR = PROJECT_ROOT / ".ly_state" / "session"

DEFAULT_HOURS_BACK = 240  # 10 days


def score_headline(headline: str) -> float:
    """Score a single headline using keyword matching. Returns float in [-1, 1]."""
    text = headline.lower()
    bullish_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bearish_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    total = bullish_hits + bearish_hits
    if total == 0:
        return 0.0
    return round((bullish_hits - bearish_hits) / total, 4)


def extract_ticker_scores(articles: list) -> dict:
    """Aggregate sentiment scores per ticker from article list.

    Each article is a dict with 'headline' (or 'title') and optional 'tickers'.
    Returns dict of ticker -> average sentiment score.
    """
    ticker_scores = defaultdict(list)

    for article in articles:
        headline = article.get("headline", "") or article.get("title", "") or article.get("text", "")
        tickers = article.get("tickers", [])
        if not headline:
            continue

        score = score_headline(headline)

        if tickers:
            for ticker in tickers:
                ticker_scores[ticker].append(score)
        else:
            text_upper = headline.upper()
            common_tickers = [
                "VNM", "FPT", "VIC", "VHM", "HPG", "MSN", "MWG",
                "TCB", "VCB", "BID", "CTG", "MBB", "ACB", "STB",
                "VNI", "SSI", "HCM", "VND", "PNJ", "REE", "DGC",
            ]
            for ticker in common_tickers:
                if ticker in text_upper:
                    ticker_scores[ticker].append(score)

    return {
        ticker: round(sum(scores) / len(scores), 4)
        for ticker, scores in ticker_scores.items()
        if scores
    }


def run_sentiment_enrichment(hours_back: int = DEFAULT_HOURS_BACK) -> int:
    """Main entry point. Returns exit code (0=success, 1=error)."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    logger.info("=== SENTIMENT ENRICHMENT START (%s, hours_back=%d) ===", today_str, hours_back)

    articles = []

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
                    "tickers": [],
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
        ticker_scores = extract_ticker_scores(articles)
        logger.info(
            "Computed sentiment for %d tickers from %d articles",
            len(ticker_scores), len(articles),
        )
        output = {
            "date": today_str,
            "scores": ticker_scores,
            "num_articles": len(articles),
            "hours_back": hours_back,
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
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exit_code = run_sentiment_enrichment(hours_back=args.hours_back)
    sys.exit(exit_code)
