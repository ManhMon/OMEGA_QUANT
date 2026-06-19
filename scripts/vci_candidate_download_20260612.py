"""
VCI Candidate Market Dataset Download
======================================
Role:   Data Engineer (Role 15, L2)
Gate:   VCI_CANDIDATE_MARKET_DOWNLOAD_20260612
Date:   2026-06-12

Downloads full HOSE+HNX OHLCV from VCI via vnstock 4.x into a candidate
parquet for cross-source validation against canonical market_2015_now.parquet.

Uses the unified VnstockClient adapter (src/omega/data/vnstock_client.py)
which provides VND_FULL normalization, rate limiting, and error handling.

Output: data/market_vci_candidate_20260612.parquet
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.data.vnstock_client import VnstockClient
from omega.data.vnd_price_contract import ensure_vnd_scale, VND_FULL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vci_candidate_download")

# ── Config ──────────────────────────────────────────────────────────────────
CANONICAL_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_PATH = REPO_ROOT / "data" / "market_vci_candidate_20260612.parquet"
CHECKPOINT_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_candidate_checkpoint.json"
STATS_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_candidate_stats.json"
BATCH_SIZE = 50
MAX_RETRIES = 3


def load_canonical_metadata(canonical_path: Path) -> dict:
    """Derive universe, date range, and exchange map from canonical parquet."""
    logger.info(f"Loading canonical metadata from {canonical_path}")
    df = pd.read_parquet(canonical_path, columns=["ticker", "date", "exchange"])
    min_date = df["date"].min().strftime("%Y-%m-%d")
    max_date = df["date"].max().strftime("%Y-%m-%d")
    exchange_map = dict(zip(df["ticker"], df["exchange"]))
    tickers = sorted(df["ticker"].unique().tolist())
    del df
    return {
        "tickers": tickers,
        "exchange_map": exchange_map,
        "min_date": min_date,
        "max_date": max_date,
    }


def fetch_one_symbol(
    client: VnstockClient,
    symbol: str,
    start_date: str,
    end_date: str,
    exchange: str,
) -> pd.DataFrame:
    """Fetch OHLCV for one symbol, returning canonical-schema DataFrame."""
    df = client.fetch_history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        interval="1D",
        normalize_vnd=True,
    )
    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.columns = [c.lower() for c in df.columns]

    if "time" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"time": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(np.int64)
    else:
        df["volume"] = 0

    df["ticker"] = symbol.upper()
    df["exchange"] = exchange
    df["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["available_at"] = df["date"] + timedelta(days=1)
    df["source"] = "vnstock_vci"
    df["price_scale"] = "VND"
    df["adjusted"] = "backward_adjusted"
    df["rebuild_date"] = datetime.now().strftime("%Y-%m-%d")

    cols = [
        "ticker", "date", "exchange", "open", "high", "low", "close",
        "volume", "as_of", "available_at", "source", "price_scale",
        "adjusted", "rebuild_date",
    ]
    existing = [c for c in cols if c in df.columns]
    return df[existing].copy()


def save_checkpoint(completed: set, stats: dict):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump({"completed": sorted(completed), "stats": stats,
                    "timestamp": datetime.now().isoformat()}, f, indent=2)


def load_checkpoint() -> tuple[set, list]:
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            ckpt = json.load(f)
        completed = set(ckpt.get("completed", []))
        logger.info(f"Resuming from checkpoint: {len(completed)} tickers done")
        return completed, []
    return set(), []


def main():
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("VCI Candidate Market Dataset Download")
    logger.info("=" * 70)

    meta = load_canonical_metadata(CANONICAL_PATH)
    tickers = meta["tickers"]
    exchange_map = meta["exchange_map"]
    start_date = meta["min_date"]
    end_date = meta["max_date"]
    logger.info(f"Universe: {len(tickers)} tickers")
    logger.info(f"Date range: {start_date} to {end_date}")

    client = VnstockClient(source="VCI")

    completed, all_frames = load_checkpoint()
    remaining = [t for t in tickers if t not in completed]
    logger.info(f"Remaining: {len(remaining)} tickers to fetch")

    stats = {"fetched": 0, "empty": 0, "errors": 0, "rows": 0}
    errors = []

    for i, symbol in enumerate(remaining):
        exchange = exchange_map.get(symbol, "UNKNOWN")
        if exchange not in ("HOSE", "HNX"):
            completed.add(symbol)
            continue

        retries = 0
        df = pd.DataFrame()
        while retries < MAX_RETRIES:
            try:
                df = fetch_one_symbol(client, symbol, start_date, end_date, exchange)
                break
            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    wait = 2 ** retries
                    logger.warning(f"Retry {retries}/{MAX_RETRIES} for {symbol}: {e}, wait {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"FAILED {symbol} after {MAX_RETRIES} retries: {e}")
                    stats["errors"] += 1
                    errors.append({"symbol": symbol, "error": str(e)})

        if df.empty:
            stats["empty"] += 1
        else:
            valid = (
                (df["high"] >= df["low"]) &
                (df["high"] >= df["open"]) &
                (df["high"] >= df["close"]) &
                (df["low"] <= df["open"]) &
                (df["low"] <= df["close"]) &
                (df["close"] > 0)
            )
            df = df[valid].copy()
            if not df.empty:
                all_frames.append(df)
                stats["fetched"] += 1
                stats["rows"] += len(df)

        completed.add(symbol)

        if (i + 1) % 10 == 0 or i == len(remaining) - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"[{i+1}/{len(remaining)}] {symbol}: {len(df)} rows | "
                f"Total: {stats['rows']} | Rate: {rate:.1f}/s | ETA: {eta:.0f}s"
            )

        if (i + 1) % BATCH_SIZE == 0:
            save_checkpoint(completed, stats)

    # ── Final assembly ──────────────────────────────────────────────────
    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        result = result.drop_duplicates(subset=["ticker", "date"], keep="last")
        result = result.sort_values(["ticker", "date"]).reset_index(drop=True)

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(OUTPUT_PATH, index=False)
        logger.info(f"Saved {len(result)} rows to {OUTPUT_PATH}")
        logger.info(f"  Tickers: {result['ticker'].nunique()}")
        logger.info(f"  Date range: {result['date'].min()} to {result['date'].max()}")
    else:
        logger.warning("No data fetched at all!")
        result = pd.DataFrame()

    # ── Stats ───────────────────────────────────────────────────────────
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_tickers": len(tickers),
        "completed": len(completed),
        "stats": stats,
        "errors": errors[:50],
        "output_path": str(OUTPUT_PATH),
        "elapsed_seconds": time.time() - t0,
    }
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Stats saved to {STATS_PATH}")

    return result


if __name__ == "__main__":
    main()
