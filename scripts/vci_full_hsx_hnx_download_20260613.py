"""
VCI Full HSX/HNX Market Dataset Download (2015-now)
====================================================
Role:   Data Engineer (Role 15, L2)
Gate:   VCI_FULL_HSX_HNX_2015_NOW_20260613
Date:   2026-06-13

Downloads FULL HSX+HNX OHLCV from VCI via vnstock 4.x into parquet.
Universe is built from VCI Listing API (exchange=HSX/HNX, type=STOCK),
NOT from canonical subset. Treats HSX as HOSE in output exchange field.

Output: data/market_vci_hsx_hnx_2015_now_20260613.parquet

Compat: CANONICAL_VCI_UPDATER_LEGACY_TRACKING_20260613
  - This script performs the initial full backfill; update_market_data.py
    handles incremental updates to data/market_2015_now.parquet.
  - price_scale="VND" label is compatible with canonical (values are VND_FULL).
  - Schema matches canonical 14-column layout.
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

from omega.data.vnstock_client import VnstockClient, RateLimiter
from omega.data.vnd_price_contract import ensure_vnd_scale, VND_FULL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vci_full_hsx_hnx_download")

# Config
OUTPUT_PATH = REPO_ROOT / "data" / "market_vci_hsx_hnx_2015_now_20260613.parquet"
UNIVERSE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"
CHECKPOINT_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_full_hsx_hnx_checkpoint.json"
STATS_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_full_hsx_hnx_stats.json"
START_DATE = "2015-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
BATCH_SIZE = 50
MAX_RETRIES = 3
RATE_LIMIT_SEC = 1.0


def load_universe() -> dict:
    """Load VCI universe from JSON (HSX + HNX stocks only)."""
    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)
    logger.info(f"Universe loaded: {universe['hsx_count']} HSX + {universe['hnx_count']} HNX = {universe['total']} total")
    return universe


def build_symbol_exchange_map(universe: dict) -> dict[str, str]:
    """Build {symbol: exchange} map. HSX -> HOSE for output compatibility."""
    exchange_map = {}
    for sym in universe["hsx"]:
        exchange_map[sym] = "HOSE"
    for sym in universe["hnx"]:
        exchange_map[sym] = "HNX"
    return exchange_map


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
    if "date" not in df.columns:
        logger.warning(f"{symbol}: no date column found, columns={list(df.columns)}")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    # Hard date lower bound: discard any pre-2015 rows returned by the API
    pre_filter = len(df)
    df = df[df["date"] >= pd.Timestamp(START_DATE)].copy()
    if len(df) < pre_filter:
        logger.info(f"{symbol}: filtered {pre_filter - len(df)} pre-{START_DATE} rows")

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
    df["rebuild_date"] = "2026-06-13"

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
        json.dump({
            "completed": sorted(completed),
            "stats": stats,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)


def load_checkpoint() -> set:
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            ckpt = json.load(f)
        completed = set(ckpt.get("completed", []))
        logger.info(f"Resuming from checkpoint: {len(completed)} tickers done")
        return completed
    return set()


def main():
    t0 = time.time()
    logger.info("=" * 70)
    logger.info("VCI Full HSX/HNX Market Dataset Download (2015-now)")
    logger.info(f"Gate: VCI_FULL_HSX_HNX_2015_NOW_20260613")
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Period: {START_DATE} to {END_DATE}")
    logger.info("=" * 70)

    universe = load_universe()
    exchange_map = build_symbol_exchange_map(universe)
    all_symbols = sorted(exchange_map.keys())
    logger.info(f"Total symbols: {len(all_symbols)}")

    client = VnstockClient(
        source="VCI",
        rate_limiter=RateLimiter(max_requests=55, period_seconds=60.0),
    )

    completed = load_checkpoint()
    remaining = [s for s in all_symbols if s not in completed]
    logger.info(f"Remaining: {len(remaining)} symbols to fetch")

    all_frames: list[pd.DataFrame] = []
    stats = {"fetched": 0, "empty": 0, "errors": 0, "rows": 0}
    errors: list[dict] = []
    empty_tickers: list[str] = []

    for i, symbol in enumerate(remaining):
        exchange = exchange_map[symbol]
        retries = 0
        df = pd.DataFrame()

        while retries < MAX_RETRIES:
            try:
                df = fetch_one_symbol(client, symbol, START_DATE, END_DATE, exchange)
                break
            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    wait = 2 ** retries
                    logger.warning(
                        f"Retry {retries}/{MAX_RETRIES} for {symbol}: {e}, wait {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"FAILED {symbol} after {MAX_RETRIES} retries: {e}")
                    stats["errors"] += 1
                    errors.append({"symbol": symbol, "error": str(e)})

        if df.empty:
            stats["empty"] += 1
            empty_tickers.append(symbol)
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
            else:
                stats["empty"] += 1
                empty_tickers.append(symbol)

        completed.add(symbol)

        if (i + 1) % 10 == 0 or i == len(remaining) - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"[{i+1}/{len(remaining)}] {symbol}: {len(df)} rows | "
                f"Fetched: {stats['fetched']}, Empty: {stats['empty']}, "
                f"Errors: {stats['errors']} | "
                f"Total rows: {stats['rows']} | Rate: {rate:.2f}/s | ETA: {eta:.0f}s"
            )

        if (i + 1) % BATCH_SIZE == 0:
            save_checkpoint(completed, stats)
            if all_frames:
                partial = pd.concat(all_frames, ignore_index=True)
                partial_path = str(OUTPUT_PATH).replace('.parquet', '_partial.parquet')
                partial.to_parquet(partial_path, index=False)
                logger.info(f"  Partial save: {len(partial)} rows to {partial_path}")

    # Final assembly
    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        # Defense-in-depth: hard filter to guarantee no pre-START_DATE rows
        pre_count = len(result)
        result = result[result["date"] >= pd.Timestamp(START_DATE)].copy()
        if len(result) < pre_count:
            logger.warning(
                f"Defense-in-depth: removed {pre_count - len(result)} pre-{START_DATE} rows"
            )
        result = result.drop_duplicates(subset=["ticker", "date"], keep="last")
        result = result.sort_values(["ticker", "date"]).reset_index(drop=True)

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(OUTPUT_PATH, index=False)
        logger.info(f"Saved {len(result)} rows to {OUTPUT_PATH}")
        logger.info(f"  Tickers: {result['ticker'].nunique()}")
        logger.info(f"  Date range: {result['date'].min()} to {result['date'].max()}")
        logger.info(f"  Exchange split:")
        logger.info(result["exchange"].value_counts().to_string())
    else:
        logger.warning("No data fetched at all!")
        result = pd.DataFrame()

    elapsed_total = time.time() - t0

    # Save stats
    summary = {
        "timestamp": datetime.now().isoformat(),
        "gate": "VCI_FULL_HSX_HNX_2015_NOW_20260613",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "universe_hsx": universe["hsx_count"],
        "universe_hnx": universe["hnx_count"],
        "universe_total": universe["total"],
        "completed": len(completed),
        "stats": stats,
        "errors": errors[:100],
        "empty_tickers": empty_tickers[:200],
        "output_path": str(OUTPUT_PATH),
        "elapsed_seconds": elapsed_total,
    }
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Stats saved to {STATS_PATH}")
    logger.info(f"Total elapsed: {elapsed_total:.1f}s ({elapsed_total/60:.1f} min)")

    return result


if __name__ == "__main__":
    main()
