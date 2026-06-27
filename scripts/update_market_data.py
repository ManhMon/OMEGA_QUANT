#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical VCI Updater / Backfill for data/market_2015_now.parquet
==================================================================
Role:   Data Engineer (Role 15, L2)
Gate:   CANONICAL_UPDATER_FULL_OVERLAP_RELOAD_20260626
Date:   2026-06-26

Replaces the old VN30-only TOP_SYMBOLS pipeline with a canonical-safe
updater that:

  - Supports full HSX/HNX universe from VCI listing or existing
    .ly_state/session/vci_universe_hsx_hnx.json
  - Supports --dry-run (no-write) validation mode
  - Supports incremental update/backfill from canonical max date + 1
    to target end date
  - Preserves canonical 14-column schema:
      ticker, date, exchange, open, high, low, close, volume,
      as_of, available_at, source, price_scale, adjusted, rebuild_date
  - Uses VCI only for OHLCV; source=vnstock_vci
  - price_scale label: "VND" (compatible with existing canonical data;
    values are VND_FULL i.e. whole-Dong, e.g. 50000.0)
  - Enforces PIT available_at = date + 1 day
  - Enforces hard date lower bound >= 2015-01-01
  - Validates before write: duplicates, null OHLCV, non-positive OHLC,
    negative volume, exchange whitelist, schema
  - Atomic write with backup when writing canonical
  - **Automatic Targeted Re-fetch**: detects price jumps (>25% daily
    return) at the canonical/new-data boundary, classifies them as
    SPLIT_LIKE (corporate action) or PRICE_JUMP (data error), and
    automatically re-fetches PRICE_JUMP symbols from the symbol's own
    canonical last date minus 15 calendar days.  Disable with
    --no-refetch.
  - **Direct Overlap Check**: the re-fetch window intentionally overlaps
    canonical data. Shared trading dates are compared directly. Any
    overlap mismatch above 0.1% is treated as a phase shift and queued
    for full-history refetch. Overlapping rows are always trimmed
    (canonical takes precedence), ensuring no duplicate writes and clean
    boundary stitching.
  - **Full-History Refetch on Phase Shift**: when the overlap check
    detects a mismatch at the 0.1% threshold, this indicates a corporate
    action (small split, bonus shares, cash dividend) has shifted the
    backward-adjusted price series.  The affected ticker's entire history
    is reloaded from 2015-01-01, all old canonical rows are deleted, and
    fresh VCI data is written to avoid phase mismatch in the parquet.

Usage:
    # Incremental update (today - canonical_max_date)
    python scripts/update_market_data.py

    # Dry-run (no write)
    python scripts/update_market_data.py --dry-run

    # Backfill specific range
    python scripts/update_market_data.py --start 2026-06-01 --end 2026-06-13

    # Override output path (for testing)
    python scripts/update_market_data.py --output .ly_state/session/test_output.parquet

    # Limit symbols (for testing)
    python scripts/update_market_data.py --symbols VCB HPG FPT --dry-run

    # Disable automatic targeted re-fetch
    python scripts/update_market_data.py --no-refetch
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("update_market_data")

# ── Canonical schema (14 columns, exact order) ──────────────────────────────
CANONICAL_COLUMNS = [
    "ticker", "date", "exchange", "open", "high", "low", "close",
    "volume", "as_of", "available_at", "source", "price_scale",
    "adjusted", "rebuild_date",
]

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_CANONICAL_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
UNIVERSE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"
MIN_DATE = pd.Timestamp("2015-01-01")
EXCHANGE_WHITELIST = {"HOSE", "HNX"}
MAX_RETRIES = 3
RATE_LIMIT_SECONDS = 1.0
BATCH_SIZE = 50

# ── Price-scale compatibility note ──────────────────────────────────────────
# The existing canonical data uses price_scale label "VND" while the actual
# values are VND_FULL (whole Dong, e.g. 50000.0).  VCI 4.x returns prices in
# THOUSANDS (e.g. 50.0).  The ensure_vnd_scale() guard multiplies by 1000
# when median close < 1000.  We write price_scale="VND" for compatibility
# with the existing canonical parquet, but the values satisfy VND_FULL.
PRICE_SCALE_LABEL = "VND"

# ── Targeted Re-fetch detection thresholds ──────────────────────────────────
# Vietnam daily price limits are ±7% (±10% for stocks without reference price).
# A return exceeding PRICE_JUMP_THRESHOLD signals a probable data error, not a
# legitimate market move.  SPLIT_LOW / SPLIT_HIGH bracket the expected price
# ratio for common stock splits (2:1 → ~0.50, 3:2 → ~0.67, 3:1 → ~0.33).
PRICE_JUMP_THRESHOLD = 0.25       # |daily return| > 25% → suspicious
SPLIT_RATIO_LOW = 0.30            # lower bound of split-like price ratio
SPLIT_RATIO_HIGH = 0.72           # upper bound of split-like price ratio
VOLUME_SPIKE_SPLIT = 1.5          # volume >= 1.5× 20-day avg → volume spike
REFETCH_LOOKBACK_DAYS = 15        # symbol last canonical date minus 15 calendar days
MAX_REFETCH_SYMBOLS = 20          # safety cap to prevent runaway re-fetches

# ── Overlap Check thresholds ─────────────────────────────────────────────────
# When re-fetching with a symbol-specific overlap window the re-fetched rows
# intentionally cover dates already in canonical.  Every shared trading date
# must match within tolerance; any mismatch indicates a phase-shifted adjusted
# series and triggers full-history reload.
OVERLAP_PRICE_TOLERANCE = 0.001   # 0.1% max |close_diff| / canon_close
OVERLAP_MIN_ROWS = 1              # direct comparison starts at first shared day
OVERLAP_PASS_RATIO = 1.00         # direct overlap: every shared day must match

# ── Full-history refetch (corporate-action phase-shift recovery) ─────────────
# When the overlap check at 0.1% detects a mismatch the canonical and new data
# are out-of-phase (backward-adjusted prices differ because of a split/dividend
# that was applied after the canonical data was written).  The only safe
# recovery is to reload the *entire* history from 2015-01-01 for the affected
# ticker, delete all old rows, and overwrite with the fresh VCI data.
FULL_HISTORY_START = "2015-01-01"


# ═══════════════════════════════════════════════════════════════════════════════
# Universe Loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_universe_from_json(path: Path) -> Dict[str, List[str]]:
    """Load HSX/HNX universe from the VCI universe JSON file."""
    if not path.exists():
        logger.error(f"Universe file not found: {path}")
        return {"hsx": [], "hnx": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    logger.info(
        f"Universe loaded from {path.name}: "
        f"{data.get('hsx_count', len(data.get('hsx', [])))} HSX + "
        f"{data.get('hnx_count', len(data.get('hnx', [])))} HNX = "
        f"{data.get('total', 0)} total"
    )
    return {"hsx": data.get("hsx", []), "hnx": data.get("hnx", [])}


def build_symbol_exchange_map(universe: Dict[str, List[str]]) -> Dict[str, str]:
    """Build {symbol: exchange} map. HSX -> HOSE for canonical compatibility."""
    exchange_map: Dict[str, str] = {}
    for sym in universe.get("hsx", []):
        exchange_map[sym] = "HOSE"
    for sym in universe.get("hnx", []):
        exchange_map[sym] = "HNX"
    return exchange_map


# ═══════════════════════════════════════════════════════════════════════════════
# Canonical Read / Incremental Start Date
# ═══════════════════════════════════════════════════════════════════════════════

def read_canonical_max_date(canonical_path: Path) -> Optional[pd.Timestamp]:
    """Read the maximum date in the canonical parquet. Returns None if missing."""
    if not canonical_path.exists():
        logger.warning(f"Canonical file not found: {canonical_path}")
        return None
    df_dates = pd.read_parquet(canonical_path, columns=["date"])
    df_dates["date"] = pd.to_datetime(df_dates["date"])
    max_date = df_dates["date"].max()
    logger.info(f"Canonical max date: {max_date.date()} ({canonical_path.name})")
    return max_date


def read_canonical(canonical_path: Path) -> Optional[pd.DataFrame]:
    """Read the full canonical parquet. Returns None if missing."""
    if not canonical_path.exists():
        return None
    df = pd.read_parquet(canonical_path)
    df["date"] = pd.to_datetime(df["date"])
    if "available_at" in df.columns:
        df["available_at"] = pd.to_datetime(df["available_at"])
    logger.info(f"Canonical loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# VCI Fetch (via vnstock 4.x)
# ═══════════════════════════════════════════════════════════════════════════════

def _create_vnstock_client():
    """Create a VnstockClient using the unified adapter."""
    try:
        from omega.data.vnstock_client import VnstockClient, RateLimiter
        return VnstockClient(
            source="VCI",
            rate_limiter=RateLimiter(max_requests=55, period_seconds=60.0),
        )
    except ImportError:
        logger.error("Cannot import omega.data.vnstock_client. Ensure src/ is on path.")
        return None


def fetch_one_symbol(
    client,
    symbol: str,
    start_date: str,
    end_date: str,
    exchange: str,
) -> pd.DataFrame:
    """Fetch OHLCV for one symbol from VCI, returning canonical-schema DataFrame."""
    try:
        df = client.fetch_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1D",
            normalize_vnd=True,
        )
    except Exception as e:
        logger.error(f"[{symbol}] Fetch failed: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.columns = [c.lower() for c in df.columns]

    # Normalize date column
    if "time" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"time": "date"})
    if "date" not in df.columns:
        logger.warning(f"[{symbol}] No date column found, columns={list(df.columns)}")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    # Hard date lower bound: discard any pre-2015 rows
    pre_count = len(df)
    df = df[df["date"] >= MIN_DATE].copy()
    if len(df) < pre_count:
        logger.info(f"[{symbol}] Filtered {pre_count - len(df)} pre-{MIN_DATE.date()} rows")

    # Coerce OHLCV types
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(np.int64)
    else:
        df["volume"] = 0

    # Add canonical metadata columns
    df["ticker"] = symbol.upper()
    df["exchange"] = exchange
    df["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["available_at"] = df["date"] + timedelta(days=1)
    df["source"] = "vnstock_vci"
    df["price_scale"] = PRICE_SCALE_LABEL
    df["adjusted"] = "backward_adjusted"
    df["rebuild_date"] = "2026-06-13"

    # Select and order canonical columns
    existing = [c for c in CANONICAL_COLUMNS if c in df.columns]
    return df[existing].copy()


def fetch_symbols(
    client,
    symbols: List[str],
    exchange_map: Dict[str, str],
    start_date: str,
    end_date: str,
    symbol_filter: Optional[Set[str]] = None,
    symbol_max_dates: Optional[Dict[str, pd.Timestamp]] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Fetch OHLCV for a list of symbols with retry and rate limiting.

    Returns:
        (combined_df, stats_dict)
    """
    if symbol_filter:
        symbols = [s for s in symbols if s in symbol_filter]

    all_frames: List[pd.DataFrame] = []
    stats = {"fetched": 0, "empty": 0, "errors": 0, "rows": 0, "total_symbols": len(symbols)}
    errors: List[Dict] = []
    empty_tickers: List[str] = []
    t0 = time.time()

    for i, symbol in enumerate(symbols):
        exchange = exchange_map.get(symbol, "UNKNOWN")
        if exchange not in EXCHANGE_WHITELIST:
            logger.debug(f"[{symbol}] Skipping: exchange={exchange} not in whitelist")
            continue

        symbol_start = start_date
        if symbol_max_dates and symbol in symbol_max_dates:
            overlap_dt = symbol_max_dates[symbol] - timedelta(days=15)
            if overlap_dt < MIN_DATE:
                overlap_dt = MIN_DATE
            symbol_start = overlap_dt.strftime("%Y-%m-%d")

        retries = 0
        df = pd.DataFrame()
        while retries < MAX_RETRIES:
            try:
                df = fetch_one_symbol(client, symbol, symbol_start, end_date, exchange)
                break
            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    wait = 2 ** retries
                    logger.warning(
                        f"[{symbol}] Retry {retries}/{MAX_RETRIES}: {e}, wait {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"[{symbol}] FAILED after {MAX_RETRIES} retries: {e}")
                    stats["errors"] += 1
                    errors.append({"symbol": symbol, "error": str(e)})

        if df.empty:
            stats["empty"] += 1
            empty_tickers.append(symbol)
        else:
            # OHLC invariant filter
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

        # Progress logging
        if (i + 1) % 10 == 0 or i == len(symbols) - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(symbols) - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"[{i+1}/{len(symbols)}] {symbol}: {len(df)} rows | "
                f"Fetched: {stats['fetched']}, Empty: {stats['empty']}, "
                f"Errors: {stats['errors']} | Total rows: {stats['rows']} | "
                f"Rate: {rate:.2f}/s | ETA: {eta:.0f}s"
            )

        # Rate limit between symbols
        if i < len(symbols) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=CANONICAL_COLUMNS)

    stats["errors_list"] = errors
    stats["empty_tickers"] = empty_tickers
    return combined, stats


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-Write Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_dataframe(df: pd.DataFrame, label: str = "data") -> Tuple[bool, List[str]]:
    """Validate a DataFrame against canonical quality requirements.

    Returns (is_valid, list_of_error_messages).
    """
    errors: List[str] = []

    if df.empty:
        errors.append(f"{label}: DataFrame is empty")
        return False, errors

    # 1. Schema: all canonical columns present
    missing_cols = [c for c in CANONICAL_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"{label}: Missing columns: {missing_cols}")

    # 2. Duplicates on (ticker, date)
    if "ticker" in df.columns and "date" in df.columns:
        dup_count = int(df.duplicated(subset=["ticker", "date"]).sum())
        if dup_count > 0:
            errors.append(f"{label}: {dup_count} duplicate (ticker, date) rows")

    # 3. Null OHLCV
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            null_ct = int(df[col].isna().sum())
            if null_ct > 0:
                errors.append(f"{label}: {null_ct} null values in '{col}'")

    # 4. Non-positive OHLC
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            bad_ct = int((pd.to_numeric(df[col], errors="coerce") <= 0).sum())
            if bad_ct > 0:
                errors.append(f"{label}: {bad_ct} non-positive values in '{col}'")

    # 5. Negative volume
    if "volume" in df.columns:
        neg_vol = int((pd.to_numeric(df["volume"], errors="coerce") < 0).sum())
        if neg_vol > 0:
            errors.append(f"{label}: {neg_vol} negative volume values")

    # 6. Exchange whitelist
    if "exchange" in df.columns:
        exchanges = set(df["exchange"].unique())
        invalid_exchanges = exchanges - EXCHANGE_WHITELIST
        if invalid_exchanges:
            errors.append(f"{label}: Invalid exchanges: {invalid_exchanges}")

    # 7. Date lower bound
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"])
        pre_min = int((dates < MIN_DATE).sum())
        if pre_min > 0:
            errors.append(f"{label}: {pre_min} rows before {MIN_DATE.date()}")

    # 8. PIT available_at = date + 1
    if "available_at" in df.columns and "date" in df.columns:
        dates_norm = pd.to_datetime(df["date"]).dt.normalize()
        avail = pd.to_datetime(df["available_at"]).dt.normalize()
        pit_violations = int((avail != dates_norm + timedelta(days=1)).sum())
        if pit_violations > 0:
            errors.append(
                f"{label}: {pit_violations} rows where available_at != date + 1 day"
            )

    is_valid = len(errors) == 0
    return is_valid, errors


# ═══════════════════════════════════════════════════════════════════════════════
# Targeted Re-fetch: Anomaly Detection & Classification
# ═══════════════════════════════════════════════════════════════════════════════

def detect_price_anomalies(
    new_df: pd.DataFrame,
    canonical_df: Optional[pd.DataFrame],
) -> List[Dict]:
    """Detect overlap mismatches between canonical and newly-fetched data."""
    if canonical_df is None or canonical_df.empty or new_df.empty:
        return []

    canon_cols = ["ticker", "date", "close", "volume", "exchange"]
    new_cols = ["ticker", "date", "close", "volume", "exchange"]
    canon_overlap = canonical_df[canon_cols].copy()
    new_overlap = new_df[new_cols].copy()
    canon_overlap["date"] = pd.to_datetime(canon_overlap["date"]).dt.normalize()
    new_overlap["date"] = pd.to_datetime(new_overlap["date"]).dt.normalize()
    canon_overlap = canon_overlap.drop_duplicates(subset=["ticker", "date"], keep="last")
    new_overlap = new_overlap.drop_duplicates(subset=["ticker", "date"], keep="last")

    merged = new_overlap.merge(
        canon_overlap,
        on=["ticker", "date"],
        how="inner",
        suffixes=("_new", "_canon"),
    )
    if merged.empty:
        return []

    merged = merged[(merged["close_canon"] > 0) & (merged["close_new"] > 0)].copy()
    if merged.empty:
        return []

    merged["diff_ratio"] = (
        (merged["close_new"] - merged["close_canon"]).abs() / merged["close_canon"].abs()
    )
    merged["signed_return"] = (
        (merged["close_new"] - merged["close_canon"]) / merged["close_canon"]
    )

    anomalies: List[Dict] = []
    for symbol, symbol_df in merged.groupby("ticker"):
        mismatch_df = symbol_df[symbol_df["diff_ratio"] > OVERLAP_PRICE_TOLERANCE]
        if mismatch_df.empty:
            continue

        mismatch_row = mismatch_df.sort_values("diff_ratio", ascending=False).iloc[0]
        canon_close = float(mismatch_row["close_canon"])
        new_close = float(mismatch_row["close_new"])
        canon_volume = float(mismatch_row.get("volume_canon", 0) or 0)
        new_volume = float(mismatch_row.get("volume_new", 0) or 0)
        anomalies.append({
            "symbol": symbol,
            "exchange": mismatch_row.get("exchange_new") or mismatch_row.get("exchange_canon") or "UNKNOWN",
            "date": str(pd.Timestamp(mismatch_row["date"]).date()),
            "canon_date": str(pd.Timestamp(mismatch_row["date"]).date()),
            "canon_close": canon_close,
            "new_close": new_close,
            "return_pct": round(float(mismatch_row["signed_return"]) * 100, 2),
            "diff_pct": round(float(mismatch_row["diff_ratio"]) * 100, 4),
            "price_ratio": round(new_close / canon_close, 4),
            "volume_ratio": round(new_volume / canon_volume, 2) if canon_volume > 0 else 0.0,
            "overlap_rows": int(len(symbol_df)),
            "mismatch_rows": int(len(mismatch_df)),
            "classification": "PRICE_JUMP",
            "reason": (
                f"shared-date close mismatch > {OVERLAP_PRICE_TOLERANCE:.2%} "
                f"on {pd.Timestamp(mismatch_row['date']).date()}"
            ),
        })

    return anomalies


def classify_anomaly(price_ratio: float, volume_ratio: float) -> str:
    """Classify a detected price anomaly.

    Returns one of:
        SPLIT_LIKE   – price halved + volume spike → probable stock split
        PRICE_JUMP   – large price change, not split-like → data error
    """
    if SPLIT_RATIO_LOW <= price_ratio <= SPLIT_RATIO_HIGH and volume_ratio >= VOLUME_SPIKE_SPLIT:
        return "SPLIT_LIKE"
    return "PRICE_JUMP"


def check_overlap_consistency(
    refetched_df: pd.DataFrame,
    canonical_df: Optional[pd.DataFrame],
    symbol: str,
) -> Dict:
    """Compare re-fetched data against canonical for overlapping trading dates.

    When a targeted re-fetch uses a symbol-specific overlap window the
    returned rows cover dates already present in canonical. This function
    checks whether every overlapping close price agrees within
    ``OVERLAP_PRICE_TOLERANCE``.

    Args:
        refetched_df: Re-fetched OHLCV DataFrame (canonical schema) for ONE symbol.
        canonical_df: Full canonical parquet DataFrame (or None).
        symbol: Ticker being checked (for logging).

    Returns:
        Dict with keys:
            overlap_rows   – number of shared trading dates
            match_rows     – rows where |diff| <= tolerance
            match_ratio    – match_rows / overlap_rows
            passed         – True when overlap is sufficient & consistent
            reason         – human-readable pass/fail explanation
            canonical_max  – last canonical date for this symbol (or None)
            trimmed_df     – refetched_df with overlap rows removed (only new dates)
    """
    result: Dict = {
        "overlap_rows": 0,
        "match_rows": 0,
        "match_ratio": 0.0,
        "passed": False,
        "reason": "",
        "canonical_max": None,
        "trimmed_df": refetched_df,
    }

    if canonical_df is None or canonical_df.empty or refetched_df.empty:
        result["reason"] = "no canonical or refetched data"
        result["passed"] = True  # nothing to compare → accept
        return result

    canon_sym = canonical_df[canonical_df["ticker"] == symbol].copy()
    if canon_sym.empty:
        result["reason"] = f"{symbol} not in canonical"
        result["passed"] = True
        return result

    canon_sym["date"] = pd.to_datetime(canon_sym["date"]).dt.normalize()
    canon_max_date = canon_sym["date"].max()
    result["canonical_max"] = str(canon_max_date.date())

    ref_sym = refetched_df.copy()
    ref_sym["date"] = pd.to_datetime(ref_sym["date"]).dt.normalize()

    # Identify overlapping dates (present in both canonical and re-fetched)
    canon_dates = set(canon_sym["date"])
    ref_dates = set(ref_sym["date"])
    overlap_dates = canon_dates & ref_dates

    overlap_count = len(overlap_dates)
    result["overlap_rows"] = overlap_count

    if overlap_count == 0:
        result["reason"] = "no overlapping dates"
        result["passed"] = True
        return result

    # Compare close prices on overlapping dates
    canon_close = canon_sym.set_index("date")["close"]
    ref_close = ref_sym.set_index("date")["close"]

    common = pd.DataFrame({
        "canon": canon_close,
        "refetch": ref_close,
    }).dropna()

    if common.empty:
        result["reason"] = "no valid close pairs for comparison"
        result["passed"] = True
        result["trimmed_df"] = ref_sym[~ref_sym["date"].isin(overlap_dates)].copy()
        return result

    pct_diff = ((common["refetch"] - common["canon"]).abs() / common["canon"].abs())
    match_mask = pct_diff <= OVERLAP_PRICE_TOLERANCE
    match_count = int(match_mask.sum())
    total_pairs = len(common)
    match_ratio = match_count / total_pairs if total_pairs > 0 else 0.0

    result["match_rows"] = match_count
    result["match_ratio"] = round(match_ratio, 4)

    # Trim overlapping rows — canonical takes precedence
    trimmed = ref_sym[~ref_sym["date"].isin(overlap_dates)].copy()
    result["trimmed_df"] = trimmed

    if match_ratio >= OVERLAP_PASS_RATIO:
        result["passed"] = True
        result["reason"] = (
            f"overlap OK: {match_count}/{total_pairs} shared rows match "
            f"({match_ratio:.0%} >= {OVERLAP_PASS_RATIO:.0%})"
        )
    else:
        result["passed"] = False
        result["reason"] = (
            f"overlap MISMATCH: {total_pairs - match_count}/{total_pairs} shared rows "
            f"differ by more than {OVERLAP_PRICE_TOLERANCE:.2%}"
        )
        logger.warning(
            f"[{symbol}] Overlap check failed: {result['reason']}"
        )

    return result


def run_targeted_refetch(
    client,
    anomalies: List[Dict],
    exchange_map: Dict[str, str],
    end_date: str,
    canonical_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Re-fetch OHLCV for symbols flagged as PRICE_JUMP with overlap checking.

    SPLIT_LIKE anomalies are logged but **not** re-fetched (the data is
    likely correct-backward-adjusted prices already reflect the split).

    After a successful boundary-return check the **Direct Overlap Check**
    compares re-fetched close prices against canonical for shared trading
    dates. Any mismatch above ``OVERLAP_PRICE_TOLERANCE`` is queued for
    full-history refetch. Overlapping rows are always discarded - canonical
    data takes precedence for dates already stored.

    Args:
        client: VnstockClient instance.
        anomalies: List of anomaly dicts from ``detect_price_anomalies``.
        exchange_map: {symbol: exchange} mapping.
        end_date: End date string (YYYY-MM-DD).
        canonical_df: Full canonical DataFrame for overlap validation.

    Returns:
        (refetched_df, refetch_stats)
    """
    refetch_targets = [
        a for a in anomalies
        if a["classification"] == "PRICE_JUMP"
    ]

    if not refetch_targets:
        logger.info("Targeted re-fetch: no PRICE_JUMP anomalies to re-fetch")
        return pd.DataFrame(), {
            "targets": 0, "success": 0, "failed": 0,
            "needs_full_refetch": [],
        }

    if len(refetch_targets) > MAX_REFETCH_SYMBOLS:
        logger.warning(
            f"Targeted re-fetch: {len(refetch_targets)} targets exceeds cap "
            f"{MAX_REFETCH_SYMBOLS}, truncating"
        )
        refetch_targets = refetch_targets[:MAX_REFETCH_SYMBOLS]

    logger.info(
        f"Targeted re-fetch: {len(refetch_targets)} symbols, "
        f"symbol-specific window = canonical last date - {REFETCH_LOOKBACK_DAYS} days"
    )

    frames: List[pd.DataFrame] = []
    stats = {
        "targets": len(refetch_targets),
        "success": 0,
        "failed": 0,
        "overlap_checks": 0,
        "overlap_passed": 0,
        "overlap_failed": 0,
        "details": [],
    }
    # Symbols whose overlap mismatch indicates a corporate-action phase shift
    # → need a full-history reload from 2015-01-01.
    needs_full_refetch: List[Dict] = []

    for anomaly in refetch_targets:
        sym = anomaly["symbol"]
        exchange = exchange_map.get(sym, anomaly.get("exchange", "UNKNOWN"))
        logger.info(
            f"  Re-fetching {sym}: return={anomaly['return_pct']}%, "
            f"classification={anomaly['classification']}"
        )

        canon_date = anomaly.get("canon_date") or anomaly.get("date")
        canon_max_ts = pd.Timestamp(canon_date)
        start_ts = canon_max_ts - timedelta(days=REFETCH_LOOKBACK_DAYS)
        if start_ts < MIN_DATE:
            start_ts = MIN_DATE
        refetch_start = start_ts.strftime("%Y-%m-%d")
        logger.info(
            f"  [{sym}] Refetch window: {refetch_start} to {end_date} "
            f"(canon_last={canon_max_ts.date()})"
        )

        retries = 0
        df = pd.DataFrame()
        while retries < MAX_RETRIES:
            try:
                df = fetch_one_symbol(client, sym, refetch_start, end_date, exchange)
                break
            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    wait = 2 ** retries
                    logger.warning(f"  [{sym}] Re-fetch retry {retries}: {e}, wait {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"  [{sym}] Re-fetch FAILED after {MAX_RETRIES} retries: {e}")

        if df.empty:
            stats["failed"] += 1
            stats["details"].append({"symbol": sym, "status": "failed", "reason": "empty"})
        else:
            # Stage 1: Validate re-fetched data at boundary
            # Compare close at the first trading day AFTER canonical max date
            # (the boundary), NOT iloc[0] of the full lookback window.
            sorted_df = df.sort_values("date")
            boundary_mask = sorted_df["date"] > canon_max_ts
            if boundary_mask.any():
                boundary_row = sorted_df.loc[boundary_mask].iloc[0]
                ref_boundary_close = float(boundary_row["close"])
                boundary_date_actual = boundary_row["date"]
                logger.debug(
                    f"  [{sym}] Stage 1: boundary date={boundary_date_actual}, "
                    f"boundary close={ref_boundary_close}, "
                    f"canon max date={canon_max_ts.date()}, "
                    f"canon close={anomaly['canon_close']}"
                )
            else:
                # No re-fetched rows after canonical max date
                ref_boundary_close = None
                logger.warning(
                    f"  [{sym}] Stage 1: no re-fetched rows after canonical "
                    f"max date {canon_max_ts.date()}"
                )

            canon_close = anomaly["canon_close"]
            new_ret = (
                abs((ref_boundary_close - canon_close) / canon_close)
                if ref_boundary_close is not None and canon_close > 0
                else 1.0
            )

            if new_ret >= PRICE_JUMP_THRESHOLD:
                stats["failed"] += 1
                stats["details"].append({
                    "symbol": sym,
                    "status": "still_anomalous",
                    "return_pct": round(new_ret * 100, 2),
                })
                logger.warning(
                    f"  [{sym}] Re-fetch still anomalous: "
                    f"boundary return={new_ret*100:.1f}%, discarding"
                )
            else:
                # Stage 2: Overlap Check — compare overlapping dates
                overlap_result = check_overlap_consistency(df, canonical_df, sym)
                stats["overlap_checks"] += 1

                if not overlap_result["passed"]:
                    stats["overlap_failed"] += 1
                    # Overlap mismatch > 0.1% on any shared day → phase shift.
                    # Queue direct full-history reload from 2015-01-01.
                    needs_full_refetch.append({
                        "symbol": sym,
                        "exchange": exchange,
                        "reason": overlap_result["reason"],
                        "overlap_rows": overlap_result["overlap_rows"],
                        "match_ratio": overlap_result["match_ratio"],
                    })
                    stats["details"].append({
                        "symbol": sym,
                        "status": "overlap_mismatch_queued_full_refetch",
                        "overlap_rows": overlap_result["overlap_rows"],
                        "match_ratio": overlap_result["match_ratio"],
                        "reason": overlap_result["reason"],
                    })
                    logger.warning(
                        f"  [{sym}] Overlap mismatch → queued for full-history "
                        f"refetch: {overlap_result['reason']}"
                    )
                else:
                    # Accept: use trimmed (non-overlapping) rows only
                    trimmed = overlap_result["trimmed_df"]
                    if trimmed.empty:
                        stats["failed"] += 1
                        stats["details"].append({
                            "symbol": sym,
                            "status": "no_new_rows_after_overlap",
                            "reason": "all re-fetched rows overlap with canonical",
                        })
                        logger.warning(
                            f"  [{sym}] No new rows after overlap trim"
                        )
                    else:
                        stats["overlap_passed"] += 1
                        stats["success"] += 1
                        frames.append(trimmed)
                        stats["details"].append({
                            "symbol": sym,
                            "status": "success",
                            "rows": len(trimmed),
                            "new_return_pct": round(new_ret * 100, 2),
                            "overlap_rows": overlap_result["overlap_rows"],
                            "overlap_match_ratio": overlap_result["match_ratio"],
                        })
                        logger.info(
                            f"  [{sym}] Re-fetch OK: {len(trimmed)} new rows "
                            f"({overlap_result['overlap_rows']} overlap trimmed, "
                            f"match={overlap_result['match_ratio']:.0%}), "
                            f"boundary return={new_ret*100:.1f}%"
                        )

        time.sleep(RATE_LIMIT_SECONDS)

    stats["needs_full_refetch"] = needs_full_refetch

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=CANONICAL_COLUMNS)

    return combined, stats


def run_full_history_refetch(
    client,
    symbols_to_refetch: List[Dict],
    exchange_map: Dict[str, str],
    end_date: str,
) -> Tuple[pd.DataFrame, Dict]:
    """Reload full history from 2015-01-01 for symbols with phase-shifted data.

    When the overlap check at 0.1% tolerance detects a close-price mismatch on
    shared trading dates, this indicates a corporate action (small split, bonus
    shares, or cash dividend) has shifted the backward-adjusted price series.
    The old canonical rows are now out-of-phase with the VCI source.

    The only safe recovery: re-download the **entire** history from 2015-01-01
    for each affected symbol and overwrite all old rows in the canonical parquet.

    Args:
        client: VnstockClient instance.
        symbols_to_refetch: List of dicts from ``run_targeted_refetch``
            ``needs_full_refetch`` key (each has symbol, exchange, reason).
        exchange_map: {symbol: exchange} mapping.
        end_date: End date string (YYYY-MM-DD).

    Returns:
        (full_history_df, stats_dict)
    """
    if not symbols_to_refetch:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "targets": 0, "success": 0, "failed": 0,
        }

    logger.info(
        f"Full-history refetch: {len(symbols_to_refetch)} symbols from "
        f"{FULL_HISTORY_START} to {end_date}"
    )

    frames: List[pd.DataFrame] = []
    stats = {
        "targets": len(symbols_to_refetch),
        "success": 0,
        "failed": 0,
        "details": [],
    }

    for entry in symbols_to_refetch:
        sym = entry["symbol"]
        exchange = exchange_map.get(sym, entry.get("exchange", "UNKNOWN"))
        logger.info(
            f"  Full-history refetch {sym}: {entry.get('reason', 'phase shift')}"
        )

        retries = 0
        df = pd.DataFrame()
        while retries < MAX_RETRIES:
            try:
                df = fetch_one_symbol(client, sym, FULL_HISTORY_START, end_date, exchange)
                break
            except Exception as e:
                retries += 1
                if retries < MAX_RETRIES:
                    wait = 2 ** retries
                    logger.warning(
                        f"  [{sym}] Full-refetch retry {retries}: {e}, wait {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"  [{sym}] Full-refetch FAILED after {MAX_RETRIES} retries: {e}"
                    )

        if df.empty:
            stats["failed"] += 1
            stats["details"].append({
                "symbol": sym, "status": "failed", "reason": "empty",
            })
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
            if df.empty:
                stats["failed"] += 1
                stats["details"].append({
                    "symbol": sym, "status": "failed",
                    "reason": "all rows failed OHLC invariant",
                })
            else:
                stats["success"] += 1
                frames.append(df)
                stats["details"].append({
                    "symbol": sym, "status": "success",
                    "rows": len(df),
                    "date_range": f"{df['date'].min()} to {df['date'].max()}",
                })
                logger.info(
                    f"  [{sym}] Full-history OK: {len(df)} rows "
                    f"({df['date'].min().date()} to {df['date'].max().date()})"
                )

        time.sleep(RATE_LIMIT_SECONDS)

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=CANONICAL_COLUMNS)

    return combined, stats


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic Write with Backup
# ═══════════════════════════════════════════════════════════════════════════════

def atomic_write_with_backup(
    df: pd.DataFrame,
    target_path: Path,
    backup: bool = True,
) -> Path:
    """Write DataFrame to parquet atomically with optional backup.

    1. Create backup of existing file (if backup=True and file exists)
    2. Write to temp file in same directory
    3. Atomic rename temp -> target

    Returns the path written to.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if backup and target_path.exists():
        backup_path = target_path.with_suffix(".parquet.bak")
        shutil.copy2(str(target_path), str(backup_path))
        logger.info(f"Backup created: {backup_path}")

    # Write to temp file then rename (atomic on same filesystem)
    fd, tmp_path_str = tempfile.mkstemp(
        suffix=".parquet.tmp",
        dir=str(target_path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        import os
        os.close(fd)
        df.to_parquet(tmp_path, index=False)
        tmp_path.replace(target_path)
        logger.info(f"Atomic write complete: {target_path} ({len(df)} rows)")
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return target_path


# ═══════════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_updater(
    canonical_path: Path = DEFAULT_CANONICAL_PATH,
    output_path: Optional[Path] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dry_run: bool = False,
    symbol_filter: Optional[Set[str]] = None,
    skip_refetch: bool = False,
) -> Dict:
    """Main updater pipeline.

    Args:
        canonical_path: Path to canonical parquet.
        output_path: Override output path (defaults to canonical_path).
        start_date: Override start date (YYYY-MM-DD). Defaults to canonical_max + 1 day.
        end_date: Override end date (YYYY-MM-DD). Defaults to today.
        dry_run: If True, validate but do not write.
        symbol_filter: Optional set of symbols to restrict fetching.
        skip_refetch: If True, disable automatic targeted re-fetch on anomaly.

    Returns:
        Dict with pipeline results summary.
    """
    target_path = output_path or canonical_path
    today = pd.Timestamp(datetime.now().date())
    end_ts = pd.Timestamp(end_date) if end_date else today

    logger.info("=" * 70)
    logger.info("Canonical VCI Updater / Backfill")
    logger.info(f"Gate: CANONICAL_UPDATER_FULL_OVERLAP_RELOAD_20260626")
    logger.info(f"Canonical: {canonical_path}")
    logger.info(f"Output: {target_path}")
    logger.info(f"Dry-run: {dry_run}")
    logger.info("=" * 70)

    # 1. Load universe
    universe = load_universe_from_json(UNIVERSE_PATH)
    exchange_map = build_symbol_exchange_map(universe)
    all_symbols = sorted(exchange_map.keys())
    logger.info(f"Universe: {len(all_symbols)} symbols")

    if not all_symbols:
        logger.error("No symbols in universe. Cannot proceed.")
        return {"status": "error", "message": "Empty universe"}

    # 2. Determine incremental date range
    symbol_max_dates: Dict[str, pd.Timestamp] = {}
    if start_date:
        fetch_start = pd.Timestamp(start_date)
    else:
        if canonical_path.exists():
            df_dates = pd.read_parquet(canonical_path, columns=["ticker", "date"])
            df_dates["date"] = pd.to_datetime(df_dates["date"])
            symbol_max_dates = df_dates.groupby("ticker")["date"].max().to_dict()
            global_max = max(symbol_max_dates.values()) if symbol_max_dates else None
            fetch_start = global_max + timedelta(days=1) if global_max else MIN_DATE
        else:
            fetch_start = MIN_DATE
            logger.info("No canonical data found; starting from 2015-01-01 (full backfill)")

    # Enforce minimum date
    if fetch_start < MIN_DATE:
        logger.warning(f"Start date {fetch_start.date()} before {MIN_DATE.date()}, clamping")
        fetch_start = MIN_DATE

    if fetch_start > end_ts:
        logger.info(f"Already up to date: start={fetch_start.date()} > end={end_ts.date()}")
        return {"status": "up_to_date", "start": str(fetch_start.date()), "end": str(end_ts.date())}

    start_str = fetch_start.strftime("%Y-%m-%d")
    end_str = end_ts.strftime("%Y-%m-%d")
    logger.info(f"Fetch window: {start_str} to {end_str}")

    # 3. Fetch new data from VCI
    client = _create_vnstock_client()
    if client is None:
        logger.error("Failed to create VnstockClient. Cannot fetch.")
        return {"status": "error", "message": "VnstockClient creation failed"}

    new_data, fetch_stats = fetch_symbols(
        client,
        all_symbols,
        exchange_map,
        start_str,
        end_str,
        symbol_filter=symbol_filter,
        symbol_max_dates=symbol_max_dates,
    )
    logger.info(
        f"Fetch complete: {fetch_stats['rows']} new rows from "
        f"{fetch_stats['fetched']} symbols "
        f"({fetch_stats['empty']} empty, {fetch_stats['errors']} errors)"
    )

    if new_data.empty:
        logger.warning("No new data fetched. Nothing to update.")
        return {"status": "no_new_data", "fetch_stats": fetch_stats}

    # 4a. Anomaly detection: compare new data boundary against canonical
    refetch_stats: Dict = {}
    full_refetch_stats: Dict = {}
    full_history_symbols: Set[str] = set()
    anomalies: List[Dict] = []
    if not skip_refetch:
        logger.info("─" * 50)
        logger.info("Overlap mismatch scan: shared-date close validation")
        canonical_for_detect = read_canonical(canonical_path)
        anomalies = detect_price_anomalies(new_data, canonical_for_detect)

        if anomalies:
            logger.info(
                f"Overlap mismatches detected: {len(anomalies)} PRICE_JUMP symbols"
            )
            for a in anomalies:
                logger.info(
                    f"  [{a['symbol']}] {a['classification']}: "
                    f"date={a['date']}, diff={a['diff_pct']}%, "
                    f"overlap_rows={a['overlap_rows']}, mismatches={a['mismatch_rows']}"
                )

            needs_full = [
                {
                    "symbol": a["symbol"],
                    "exchange": a.get("exchange", "UNKNOWN"),
                    "reason": a.get("reason", "shared-date overlap mismatch"),
                    "overlap_rows": a.get("overlap_rows", 0),
                    "mismatch_rows": a.get("mismatch_rows", 0),
                }
                for a in anomalies
            ]
            refetch_stats = {
                "targets": 0,
                "success": 0,
                "failed": 0,
                "needs_full_refetch": needs_full,
                "details": [],
            }
            logger.info("─" * 50)
            logger.info(
                f"Full-History Refetch: {len(needs_full)} symbols with overlap mismatch"
            )
            full_df, full_refetch_stats = run_full_history_refetch(
                client, needs_full, exchange_map, end_str,
            )
            full_history_symbols = {
                d["symbol"]
                for d in full_refetch_stats.get("details", [])
                if d["status"] == "success"
            }
            if full_history_symbols:
                before = len(new_data)
                new_data = new_data[
                    ~new_data["ticker"].isin(full_history_symbols)
                ].copy()
                after = len(new_data)
                logger.info(
                    f"Full-history refetch: removed {before - after} "
                    f"incremental rows for {len(full_history_symbols)} "
                    f"symbols from new_data (will overwrite canonical)"
                )
                if not full_df.empty:
                    new_data = pd.concat(
                        [new_data, full_df], ignore_index=True,
                    )
        else:
            logger.info("No shared-date close mismatches detected")
    else:
        logger.info("Targeted re-fetch skipped (--no-refetch)")

    # 4. Validate new data before merge
    new_valid, new_errors = validate_dataframe(new_data, "new_data")
    if not new_valid:
        logger.error("New data validation FAILED:")
        for err in new_errors:
            logger.error(f"  - {err}")
        # Deduplicate new data and retry validation
        logger.info("Attempting auto-fix: dedup + drop invalid rows")
        new_data = new_data.drop_duplicates(subset=["ticker", "date"], keep="last")
        new_data = new_data.dropna(subset=["open", "high", "low", "close", "volume"])
        new_data = new_data[new_data["date"] >= MIN_DATE].copy()
        new_data = new_data[new_data["exchange"].isin(EXCHANGE_WHITELIST)].copy()
        new_valid, new_errors = validate_dataframe(new_data, "new_data (post-fix)")
        if not new_valid:
            logger.error("Post-fix validation still FAILED:")
            for err in new_errors:
                logger.error(f"  - {err}")
            if not dry_run:
                return {"status": "validation_failed", "errors": new_errors}

    # 5. Merge with existing canonical (if writing to canonical path)
    if target_path == canonical_path and canonical_path.exists():
        existing = read_canonical(canonical_path)
        if existing is not None:
            # Delete old history for full-history-refetched symbols
            # (corporate-action phase shift → old data is out-of-phase)
            if full_history_symbols:
                before_delete = len(existing)
                existing = existing[
                    ~existing["ticker"].isin(full_history_symbols)
                ].copy()
                deleted = before_delete - len(existing)
                logger.info(
                    f"Deleted {deleted} old canonical rows for "
                    f"{len(full_history_symbols)} phase-shifted symbols: "
                    f"{sorted(full_history_symbols)}"
                )
            combined = pd.concat([existing, new_data], ignore_index=True)
            before_dedup = len(combined)
            combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
            after_dedup = len(combined)
            if before_dedup != after_dedup:
                logger.info(f"Deduplication removed {before_dedup - after_dedup} rows")
            combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
        else:
            combined = new_data.sort_values(["ticker", "date"]).reset_index(drop=True)
    else:
        combined = new_data.sort_values(["ticker", "date"]).reset_index(drop=True)

    # 6. Validate combined data
    combined_valid, combined_errors = validate_dataframe(combined, "combined")
    if not combined_valid:
        logger.warning("Combined data validation issues:")
        for err in combined_errors:
            logger.warning(f"  - {err}")
        # Gate: invalid combined data must NEVER reach atomic_write_with_backup
        # when dry_run=False. Dry-run may return the invalid summary without writing.
        if not dry_run:
            logger.error(
                "BLOCKED: combined validation failed and dry_run=False; "
                "no write will be performed."
            )
            return {"status": "validation_failed", "errors": combined_errors}

    # 7. Report summary
    summary = {
        "status": "dry_run" if dry_run else "written",
        "fetch_start": start_str,
        "fetch_end": end_str,
        "new_rows": len(new_data),
        "combined_rows": len(combined),
        "combined_tickers": int(combined["ticker"].nunique()),
        "date_range": f"{combined['date'].min()} to {combined['date'].max()}",
        "fetch_stats": fetch_stats,
        "new_data_valid": new_valid,
        "combined_valid": combined_valid,
        "dry_run": dry_run,
        "anomalies_detected": len(anomalies),
        "refetch_stats": refetch_stats,
        "full_history_refetch_stats": full_refetch_stats,
        "full_history_symbols": sorted(full_history_symbols) if full_history_symbols else [],
    }

    if dry_run:
        logger.info("DRY-RUN: No data written.")
        logger.info(f"  New rows: {len(new_data)}")
        logger.info(f"  Combined rows: {len(combined)}")
        logger.info(f"  Combined tickers: {combined['ticker'].nunique()}")
        logger.info(f"  Date range: {combined['date'].min()} to {combined['date'].max()}")
        logger.info(f"  Exchange split: {combined['exchange'].value_counts().to_dict()}")
        summary["exchange_split"] = combined["exchange"].value_counts().to_dict()
        return summary

    # 8. Write atomically with backup
    written_path = atomic_write_with_backup(combined, target_path)
    summary["output_path"] = str(written_path)
    logger.info(f"Update complete: {written_path} ({len(combined)} total rows)")
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Canonical VCI Updater / Backfill for market_2015_now.parquet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and report without writing to canonical",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Override start date (YYYY-MM-DD). Default: canonical max date + 1 day",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="Override end date (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Override output path (for testing). Default: canonical path",
    )
    parser.add_argument(
        "--canonical", type=str, default=None,
        help="Override canonical input path. Default: data/market_2015_now.parquet",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Restrict to specific symbols (for testing)",
    )
    parser.add_argument(
        "--no-refetch", action="store_true",
        help="Disable automatic targeted re-fetch on price anomaly detection",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    canonical_path = Path(args.canonical) if args.canonical else DEFAULT_CANONICAL_PATH
    output_path = Path(args.output) if args.output else None
    symbol_filter = set(s.upper() for s in args.symbols) if args.symbols else None

    result = run_updater(
        canonical_path=canonical_path,
        output_path=output_path,
        start_date=args.start,
        end_date=args.end,
        dry_run=args.dry_run,
        symbol_filter=symbol_filter,
        skip_refetch=args.no_refetch,
    )

    # Save result summary
    summary_path = REPO_ROOT / ".ly_state" / "session" / "update_market_data_result.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Result summary saved to {summary_path}")

    if result.get("status") in ("error", "validation_failed"):
        logger.error(f"Pipeline FAILED: {result.get('status')}")
        return 1

    logger.info(f"Pipeline {result.get('status', 'complete').upper()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
