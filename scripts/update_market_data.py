#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase B: Automated Daily Ingestion
Pulls EOD data via vnstock3 and appends to the master parquet warehouse.

Author: Data Engineer (Role 08)
Date: 2026-05-24
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

try:
    from vnstock import Vnstock
except ImportError:
    logging.warning("vnstock not installed. Skipping live data pull.")
    Vnstock = None

PROJECT_ROOT = Path(__file__).parent.parent
WAREHOUSE_PATH = PROJECT_ROOT / "data" / "market_2015_now.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("update_market_data")

# VN30 representative tickers
TOP_SYMBOLS = [
    'VCB', 'HPG', 'FPT', 'VIC', 'MSN', 'MWG', 'VNM', 'SAB', 'VHM', 'GAS',
    'BID', 'VPB', 'ACB', 'TCB', 'MBB', 'HDB', 'STB', 'VIB', 'CTG', 'TPB',
]

MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 0.5


def get_latest_date_in_warehouse() -> pd.Timestamp:
    """Find the most recent date in the existing warehouse."""
    if not WAREHOUSE_PATH.exists():
        return pd.Timestamp("2025-01-01")  # Default fallback

    # Read just the date column to save memory
    df_dates = pd.read_parquet(WAREHOUSE_PATH, columns=["date"])
    df_dates["date"] = pd.to_datetime(df_dates["date"])
    return df_dates["date"].max()


def _passes_quality_checks(df: pd.DataFrame, symbol: str) -> bool:
    """Validate fetched data quality. Returns True if data is acceptable."""
    # Check 1: DataFrame is empty
    if df.empty:
        logger.warning(f"[{symbol}] Quality check FAILED: DataFrame is empty.")
        return False

    # Check 2: Any price column has >50% NaN
    price_cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    for col in price_cols:
        nan_ratio = df[col].isna().sum() / len(df)
        if nan_ratio > 0.5:
            logger.warning(
                f"[{symbol}] Quality check FAILED: column '{col}' has "
                f"{nan_ratio:.0%} NaN (threshold 50%)."
            )
            return False

    # Check 3: Close price is 0 or negative
    if "close" in df.columns:
        invalid_close = (df["close"] <= 0).any()
        if invalid_close:
            logger.warning(
                f"[{symbol}] Quality check FAILED: close price contains 0 or negative values."
            )
            return False

    logger.info(f"[{symbol}] Quality checks PASSED ({len(df)} rows).")
    return True


def _fetch_symbol_with_retry(symbol: str, start_str: str, end_str: str) -> pd.DataFrame | None:
    """Fetch a single symbol with retry logic (exponential backoff)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            stock = Vnstock().stock(symbol=symbol, source='VCI')
            df = stock.quote.history(start=start_str, end=end_str)
            return df
        except Exception as e:
            backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"[{symbol}] Attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                time.sleep(backoff)
            else:
                logger.error(
                    f"[{symbol}] All {MAX_RETRIES} attempts failed. Last error: {e}. "
                    f"Skipping symbol."
                )
    return None


def fetch_and_append_data():
    """Main ingestion pipeline: fetch, validate, deduplicate, append."""
    logger.info("Starting Daily Oracle Data Ingestion...")
    latest_date = get_latest_date_in_warehouse()
    logger.info(f"Latest data in warehouse is up to: {latest_date.date()}")

    today = pd.Timestamp(datetime.now().date())

    # Idempotency guard: skip if already up to date
    if latest_date >= today:
        logger.info("Warehouse is already up to date for today. No pull required.")
        return

    start_str = (latest_date + timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    logger.info(f"Targeting fetch window: {start_str} to {end_str}")

    if Vnstock is None:
        logger.error("vnstock3 package not installed. Cannot fetch live data. Exiting.")
        return

    all_frames: list[pd.DataFrame] = []

    for i, sym in enumerate(TOP_SYMBOLS):
        logger.info(f"Fetching [{i + 1}/{len(TOP_SYMBOLS)}]: {sym}")

        df = _fetch_symbol_with_retry(sym, start_str, end_str)

        if df is None:
            continue

        # Data quality gate
        if not _passes_quality_checks(df, sym):
            continue

        # Tag with ticker
        df["ticker"] = sym
        all_frames.append(df)

        # Rate limiting between symbols
        if i < len(TOP_SYMBOLS) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    if not all_frames:
        logger.warning("No valid data fetched for any symbol. Nothing to append.")
        return

    new_data = pd.concat(all_frames, ignore_index=True)
    logger.info(f"Total new rows fetched: {len(new_data)}")

    # Ensure date column is datetime
    if "time" in new_data.columns and "date" not in new_data.columns:
        new_data = new_data.rename(columns={"time": "date"})
        
    if "date" in new_data.columns:
        new_data["date"] = pd.to_datetime(new_data["date"])
        # Format to date-only string to match warehouse format
        new_data["date"] = new_data["date"].dt.normalize()

    # Standardize new data to VND scale (Vnstock 4.x returns raw thousands)
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if col in new_data.columns:
            new_data[col] = new_data[col].astype(float)
            
    mask_to_scale = (new_data["close"] > 0) & (new_data["close"] < 1000.0)
    for col in price_cols:
        if col in new_data.columns:
            new_data.loc[mask_to_scale, col] = new_data.loc[mask_to_scale, col] * 1000.0
            
    logger.info("New data prices successfully standardized to VND scale.")

    # Append to warehouse with deduplication
    if WAREHOUSE_PATH.exists():
        existing = pd.read_parquet(WAREHOUSE_PATH)
        existing["date"] = pd.to_datetime(existing["date"])
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    # Deduplicate on (ticker, date)
    before_dedup = len(combined)
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    after_dedup = len(combined)
    if before_dedup != after_dedup:
        logger.info(f"Deduplication removed {before_dedup - after_dedup} duplicate rows.")

    # Write back
    combined.to_parquet(WAREHOUSE_PATH, index=False)
    logger.info(f"Warehouse updated: {WAREHOUSE_PATH} ({len(combined)} total rows)")


if __name__ == "__main__":
    fetch_and_append_data()
