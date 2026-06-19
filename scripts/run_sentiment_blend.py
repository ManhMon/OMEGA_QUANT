#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentiment Alpha Blend Step
==========================
Combines ML/Ensemble signals with sentiment_scores.json using SentimentAlphaEngine.
Enforces strict PIT safety (T-1 lag): sentiment data must be dated before target date.

T-1 Scanning: When the main sentiment_scores.json has date >= target_date (same-day
enrichment), this script scans dated archive files (sentiment_scores_YYYY-MM-DD.json)
to find the most recent PIT-valid sentiment. If none is found, blending is skipped
gracefully and the raw ensemble signals are preserved.

Overwrites the ensemble signals file in-place with blended signals.

Usage:
    python scripts/run_sentiment_blend.py --date 2026-06-19

Gate: SENTIMENT_ALPHA_WIRING_20260619
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --- Path setup ---
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from omega.quant.signal.sentiment_alpha import SentimentAlphaEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] SENTIMENT_BLEND: %(message)s",
)
logger = logging.getLogger("run_sentiment_blend")

ENSEMBLE_DIR = _REPO_ROOT / ".ly_state" / "shadow_live"
SENTIMENT_DIR = _REPO_ROOT / ".ly_state" / "session"
SENTIMENT_FILE = SENTIMENT_DIR / "sentiment_scores.json"
SENTIMENT_ARCHIVE_PREFIX = "sentiment_scores_"
SENTIMENT_ARCHIVE_SUFFIX = ".json"

DEFAULT_SENTIMENT_SCALE = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blend ensemble signals with sentiment alpha")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Target date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--sentiment-scale",
        type=float,
        default=DEFAULT_SENTIMENT_SCALE,
        help=f"Sentiment blend scale (default: {DEFAULT_SENTIMENT_SCALE})",
    )
    return parser.parse_args()


def load_ensemble_signals(target_date: str) -> dict:
    """Load ensemble signal file. Returns the full JSON dict."""
    path = ENSEMBLE_DIR / f"{target_date}_ensemble.json"
    if not path.exists():
        raise FileNotFoundError(f"Ensemble signals not found: {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "signals" not in data or not data["signals"]:
        raise ValueError(f"Ensemble file has no signals: {path}")
    logger.info(
        "Loaded ensemble signals: %d tickers from %s",
        len(data["signals"]), path,
    )
    return data


def load_sentiment_scores(path: Path | None = None) -> dict:
    """Load sentiment_scores.json from the given path (or default). Returns the full JSON dict."""
    target_path = path or SENTIMENT_FILE
    if not target_path.exists():
        raise FileNotFoundError(f"Sentiment scores not found: {target_path}")
    with open(target_path, encoding="utf-8") as fh:
        data = json.load(fh)
    logger.info(
        "Loaded sentiment scores: %d tickers, date=%s (from %s)",
        len(data.get("scores", {})), data.get("date", "unknown"), target_path.name,
    )
    return data


def find_latest_valid_sentiment(target_date: str) -> dict | None:
    """
    Find the latest sentiment file whose 'date' field is strictly before target_date.

    T-1 PIT contract: sentiment used for blending must be from a prior trading day.

    Search order:
      1. Main sentiment_scores.json — if its date < target_date, use it directly.
      2. Dated archive files sentiment_scores_YYYY-MM-DD.json — pick the most recent
         file where the embedded date < target_date.

    Returns the parsed sentiment dict, or None if no valid file is found.
    """
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    best_data: dict | None = None
    best_date = None

    # --- 1. Check the main (live) sentiment file ---
    if SENTIMENT_FILE.exists():
        try:
            data = load_sentiment_scores(SENTIMENT_FILE)
            file_date_str = data.get("date", "")
            if file_date_str:
                file_dt = datetime.strptime(file_date_str, "%Y-%m-%d").date()
                if file_dt < target_dt:
                    logger.info(
                        "Main sentiment file is PIT-valid (date=%s < target=%s)",
                        file_dt, target_dt,
                    )
                    return data
                logger.info(
                    "Main sentiment file date=%s >= target=%s — not PIT-valid, scanning archives",
                    file_dt, target_dt,
                )
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load main sentiment file: %s", exc)

    # --- 2. Scan dated archive files ---
    if not SENTIMENT_DIR.exists():
        logger.warning("Sentiment directory does not exist: %s", SENTIMENT_DIR)
        return None

    for archive_path in sorted(SENTIMENT_DIR.glob(
        f"{SENTIMENT_ARCHIVE_PREFIX}*{SENTIMENT_ARCHIVE_SUFFIX}"
    )):
        name = archive_path.stem  # e.g. sentiment_scores_2026-06-18
        date_part = name.removeprefix(SENTIMENT_ARCHIVE_PREFIX)
        try:
            filename_dt = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue

        # Filename date is a discovery hint — skip obviously future files early
        if filename_dt >= target_dt:
            continue

        try:
            with open(archive_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Skipping unreadable archive %s: %s", archive_path.name, exc)
            continue

        # Validate embedded date for PIT safety (authoritative, not filename)
        embedded_date_str = data.get("date", "")
        if not embedded_date_str:
            logger.warning(
                "Skipping archive %s: missing 'date' field", archive_path.name,
            )
            continue
        try:
            embedded_dt = datetime.strptime(embedded_date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(
                "Skipping archive %s: invalid embedded date '%s'",
                archive_path.name, embedded_date_str,
            )
            continue

        if embedded_dt >= target_dt:
            logger.warning(
                "Skipping archive %s: embedded date=%s >= target=%s (PIT-invalid)",
                archive_path.name, embedded_dt, target_dt,
            )
            continue

        if best_date is None or embedded_dt > best_date:
            best_date = embedded_dt
            best_data = data
            logger.info(
                "Found valid archive: %s (embedded_date=%s, filename_date=%s)",
                archive_path.name, embedded_dt, filename_dt,
            )

    if best_data is not None:
        logger.info(
            "Selected archive sentiment date=%s for target=%s (T-1 OK)",
            best_date, target_dt,
        )
    else:
        logger.warning(
            "No PIT-valid sentiment file found for target_date=%s", target_date,
        )

    return best_data


def validate_pit_safety(sentiment_date_str: str, target_date_str: str) -> None:
    """
    PIT T-1 lag gate: sentiment date must be strictly before target date.
    Raises ValueError on violation.
    """
    sentiment_dt = datetime.strptime(sentiment_date_str, "%Y-%m-%d").date()
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    if sentiment_dt >= target_dt:
        raise ValueError(
            f"PIT VIOLATION (T-1): sentiment date ({sentiment_dt}) "
            f">= target date ({target_dt}). Sentiment must be from a prior trading day."
        )
    logger.info("PIT safety PASS: sentiment %s < target %s (T-1 lag OK)", sentiment_dt, target_dt)


def blend_signals(
    ensemble_data: dict,
    sentiment_data: dict,
    target_date: str,
    sentiment_scale: float,
) -> dict:
    """
    Blend ensemble signals with sentiment scores using SentimentAlphaEngine.

    Returns updated ensemble_data dict with blended signals.
    """
    sentiment_date_str = sentiment_data.get("date", "")
    if not sentiment_date_str:
        raise ValueError("Sentiment data missing 'date' field")

    validate_pit_safety(sentiment_date_str, target_date)

    scores = sentiment_data.get("scores", {})
    if not scores:
        logger.warning("Sentiment scores are empty. Returning original ensemble signals.")
        return ensemble_data

    base_signals = pd.Series(ensemble_data["signals"], dtype=float)
    sentiment_series = pd.Series(scores, dtype=float)

    # Build PIT timestamps for SentimentAlphaEngine._validate_pit
    sentiment_date = datetime.strptime(sentiment_date_str, "%Y-%m-%d")
    as_of = sentiment_date.replace(hour=16, minute=0)
    generated_at_str = sentiment_data.get("generated_at", "")
    if generated_at_str:
        available_at = datetime.fromisoformat(generated_at_str)
        if available_at.tzinfo is not None:
            available_at = available_at.replace(tzinfo=None)
    else:
        available_at = sentiment_date.replace(hour=18, minute=0)

    target_dt = datetime.strptime(target_date, "%Y-%m-%d").replace(hour=9, minute=0)

    engine = SentimentAlphaEngine(sentiment_scale=sentiment_scale)
    combined = engine.combine_sentiment_alpha(
        base_signals=base_signals,
        sentiment_scores=sentiment_series,
        as_of=as_of,
        available_at=available_at,
        timestamp=target_dt,
    )

    blended = {ticker: round(float(score), 8) for ticker, score in combined.items()}

    logger.info(
        "Blended %d signals (scale=%.4f). Sentiment applied to %d/%d tickers.",
        len(blended),
        sentiment_scale,
        len(scores),
        len(blended),
    )

    ensemble_data["signals"] = blended
    ensemble_data["sentiment_blend"] = {
        "applied": True,
        "sentiment_date": sentiment_date_str,
        "sentiment_scale": sentiment_scale,
        "num_sentiment_tickers": len(scores),
        "blended_at": datetime.now().isoformat(),
    }
    return ensemble_data


def save_ensemble_signals(ensemble_data: dict, target_date: str) -> Path:
    """Overwrite the ensemble signals file with blended data."""
    output_path = ENSEMBLE_DIR / f"{target_date}_ensemble.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(ensemble_data, fh, indent=2, ensure_ascii=False)
    logger.info("Saved blended ensemble to %s", output_path)
    return output_path


def main() -> int:
    args = parse_args()
    target_date = args.date
    logger.info("=== Sentiment Alpha Blend === target=%s scale=%.4f", target_date, args.sentiment_scale)

    try:
        ensemble_data = load_ensemble_signals(target_date)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Cannot load ensemble signals: %s", exc)
        return 1

    try:
        sentiment_data = find_latest_valid_sentiment(target_date)
    except Exception as exc:
        logger.warning("Error scanning sentiment files: %s. Skipping blend.", exc)
        return 0

    if sentiment_data is None:
        logger.warning(
            "No PIT-valid sentiment data found for target_date=%s. "
            "Skipping sentiment blend (raw ensemble preserved).",
            target_date,
        )
        return 0

    try:
        ensemble_data = blend_signals(
            ensemble_data, sentiment_data, target_date, args.sentiment_scale,
        )
    except ValueError as exc:
        logger.error("Blend failed: %s", exc)
        return 1

    save_ensemble_signals(ensemble_data, target_date)
    logger.info("=== Sentiment blend complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
