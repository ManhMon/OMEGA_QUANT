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
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes
else:
    import fcntl

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
OVERLAP_EQUIVALENCE_COLUMNS = [
    "exchange", "open", "high", "low", "close", "volume", "available_at",
    "source", "price_scale", "adjusted",
]

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_CANONICAL_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
DEFAULT_RELEASE_ROOT = REPO_ROOT / "data" / "market_releases"
DEFAULT_POINTER_PATH = REPO_ROOT / "data" / "market_current.json"
UNIVERSE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"
MARKET_DATA_RECEIPT_DIR = REPO_ROOT / ".ly_state" / "session" / "market_data_receipts"
MARKET_DATA_ATTEMPT_SCHEMA_VERSION = 2
VCI_AUTHORITY_RECEIPT_SCHEMA_VERSION = 2
MARKET_DATA_RECEIPT_ALGORITHM = "HMAC-SHA256"
MARKET_DATA_RECEIPT_ACTIVE_KEY_ID = "OMEGA_MARKET_RECEIPT_HMAC_ACTIVE_KEY_ID"
MARKET_DATA_RECEIPT_KEYRING = "OMEGA_MARKET_RECEIPT_HMAC_KEYRING_JSON"
MARKET_DATA_PROJECTION = REPO_ROOT / ".ly_state" / "session" / "update_market_data_result.json"
MARKET_DATA_RECONCILIATION_LATEST = REPO_ROOT / ".ly_state" / "session" / "market_data_reconciliation_latest.json"
MARKET_DATA_RECONCILIATION_STATE = REPO_ROOT / ".ly_state" / "session" / "market_data_reconciliation_state.json"
MARKET_DATA_RECEIPT_FIELDS = {
    "in_progress": {"schema_version", "attempt_id", "state", "started_at", "execution_allowed", "integrity"},
    "terminal": {"schema_version", "attempt_id", "state", "started_at", "completed_at", "published", "stale", "terminal_session", "execution_allowed", "reason", "publication", "projection_path", "projection_sha256", "projection_attempt_id", "provenance", "gate_evidence", "integrity"},
}
GATE_EVIDENCE_FIELDS = {"schema_version", "terminal_session", "cutoff_at", "candidate_path", "candidate_sha256", "pointer_path", "pointer_sha256", "projection_path", "projection_sha256", "projection_attempt_id", "release_gate_passed", "vci_authority_receipt_path", "vci_authority_receipt_sha256"}
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
LEGACY_VCI_SOURCE_VALUES = frozenset({"vnstock_vci", "vci"})
LEGACY_VCI_PROVENANCE = {
    "price_scale": "VND",
    "adjusted": "backward_adjusted",
    "rebuild_date": "2026-06-13",
}

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
SPARSE_TERMINAL_MAX_MISSED_SESSIONS = 25
TICKER_LIFECYCLE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_ticker_lifecycle.json"
LIFECYCLE_RECEIPT_LEDGER_DIR = REPO_ROOT / ".ly_state" / "session" / "lifecycle_receipt_ledger"
SPARSE_TERMINAL_STATUSES = frozenset({"halted", "delisted", "suspended"})
LIFECYCLE_EVIDENCE_SCHEMA_VERSION = 1
LIFECYCLE_EVIDENCE_ALGORITHM = "HMAC-SHA256"
LIFECYCLE_EVIDENCE_FIELDS = {"schema_version", "payload", "signed_at", "expires_at", "receipt_id", "integrity"}
LIFECYCLE_EVIDENCE_PAYLOAD_FIELDS = {"ticker", "status", "reason", "effective_at", "as_of", "source"}
LIFECYCLE_EVIDENCE_INTEGRITY_FIELDS = {"algorithm", "key_id", "payload_sha256", "signature"}
LIFECYCLE_RECEIPT_KEYRING = "OMEGA_LIFECYCLE_RECEIPT_KEYRING_JSON"
LIFECYCLE_RECEIPT_LEDGER_SCHEMA_VERSION = 1
LIFECYCLE_RECEIPT_MAX_SIGNING_AGE = timedelta(hours=24)
VN_HOLIDAYS_PATH = REPO_ROOT / "config" / "vn_holidays.json"

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
RELEASE_RETENTION = 14
CHECKPOINT_RETENTION = 3
CHECKPOINT_RETENTION_DAYS = 7
FAILED_RETENTION_DAYS = 90
PIT_MANIFEST_RETENTION_DAYS = 365 * 7
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


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
    if "price_scale" in df.columns:
        df["price_scale"] = df["price_scale"].fillna(PRICE_SCALE_LABEL)
    if "adjusted" in df.columns:
        df["adjusted"] = df["adjusted"].fillna("backward_adjusted")
    if "rebuild_date" in df.columns:
        df["rebuild_date"] = df["rebuild_date"].fillna("2026-06-13")
    ticker_count = df["ticker"].nunique() if "ticker" in df.columns else 0
    logger.info(f"Canonical loaded: {len(df)} rows, {ticker_count} tickers")
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


def _create_kbs_client():
    """Create the reference-only KBS client."""
    from omega.data.vnstock_client import VnstockClient, RateLimiter
    return VnstockClient(source="KBS", rate_limiter=RateLimiter(max_requests=55, period_seconds=60.0))


def _run_reconciliation(
    combined: pd.DataFrame,
    symbols: List[str],
    exchange_map: Dict[str, str],
    as_of_date: str,
    state_path: Path,
    latest_path: Path,
) -> Dict:
    """Best-effort KBS reconciliation. Never affects VCI publication."""
    from omega.data.provider_reconciliation import reconcile_ohlcv
    prior_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    try:
        kbs_data, _ = fetch_symbols(_create_kbs_client(), symbols, exchange_map, as_of_date, as_of_date)
        payload, next_state = reconcile_ohlcv(combined, kbs_data, prior_state, as_of_date)
    except Exception as exc:
        logger.warning("KBS reconciliation unavailable: %s", exc)
        payload, next_state = reconcile_ohlcv(combined, None, prior_state, as_of_date)
        payload["findings"][0]["reason"] = f"reconciliation_failed: {exc}"
    _write_fsync(state_path, _canonical_json(next_state))
    _write_fsync(latest_path, _canonical_json(payload))
    return payload


def _resolve_listing_dates(
    client,
    symbol: str,
    listing_date: Optional[str] = None,
    delisting_date: Optional[str] = None,
) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """Resolve positive listing and delisting dates from explicit args, client metadata, or signed envelopes."""
    list_dt = pd.to_datetime(listing_date) if listing_date is not None else None
    delist_dt = pd.to_datetime(delisting_date) if delisting_date is not None else None
    if list_dt is not None:
        return list_dt, delist_dt

    if hasattr(client, "get_listing_date") and callable(client.get_listing_date):
        try:
            ld = client.get_listing_date(symbol)
            if ld:
                list_dt = pd.to_datetime(ld)
        except Exception:
            pass
    elif hasattr(client, "listing_date"):
        try:
            ld = getattr(client, "listing_date")
            if ld:
                list_dt = pd.to_datetime(ld)
        except Exception:
            pass
    elif hasattr(client, "fetch_company_profile") and callable(client.fetch_company_profile):
        try:
            prof = client.fetch_company_profile(symbol)
            if isinstance(prof, pd.DataFrame) and not prof.empty and "listing_date" in prof.columns:
                val = prof["listing_date"].dropna().iloc[0]
                if val:
                    list_dt = pd.to_datetime(val)
        except Exception:
            pass

    if list_dt is None or delist_dt is None:
        try:
            if TICKER_LIFECYCLE_PATH.exists():
                lifecycle_data = json.loads(TICKER_LIFECYCLE_PATH.read_text(encoding="utf-8"))
                sym_entry = lifecycle_data.get(symbol.upper(), {})
                payload = sym_entry.get("payload", sym_entry)
                if list_dt is None and "listing_date" in payload:
                    list_dt = pd.to_datetime(payload["listing_date"])
                if delist_dt is None and "delisting_date" in payload:
                    delist_dt = pd.to_datetime(payload["delisting_date"])
        except Exception:
            pass

    return list_dt, delist_dt


def _fetch_history_chunked(
    client,
    symbol: str,
    start_date: str,
    end_date: str,
    max_chunk_retries: int = 3,
    max_total_attempts: int = 15,
    listing_date: Optional[str] = None,
    delisting_date: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch history chunked in <= 5-year slices to bypass vnstock 8-year community window truncation.

    Enforces deterministic retry ceiling per chunk and symbol-level total attempt budget.
    Requires positive listing metadata and fails closed on empty chunks during listed periods.
    """
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    max_days = 5 * 365

    list_dt, delist_dt = _resolve_listing_dates(client, symbol, listing_date, delisting_date)

    if (end_dt - start_dt).days <= max_days:
        total_attempts = 0
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_chunk_retries + 1):
            if total_attempts >= max_total_attempts:
                raise RuntimeError(
                    f"[{symbol}] Upstream attempt ceiling ({max_total_attempts}) exhausted while fetching chunk {start_date}..{end_date}"
                )
            total_attempts += 1
            try:
                res = client.fetch_history(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval="1D",
                    normalize_vnd=True,
                )
                if res is None or res.empty:
                    is_pre_listing = list_dt is not None and end_dt < list_dt
                    is_post_delisting = delist_dt is not None and start_dt > delist_dt
                    if is_pre_listing or is_post_delisting:
                        return pd.DataFrame()
                    if list_dt is None:
                        raise RuntimeError(
                            f"[{symbol}] Unverified empty chunk {start_date}..{end_date}: missing positive listing_date or trading continuity proof"
                        )
                    raise RuntimeError(
                        f"[{symbol}] Unverified empty chunk {start_date}..{end_date}: empty chunk during listed period (listing_date={list_dt.date()}) failed closed, missing positive listing_date or trading continuity proof"
                    )
                return res
            except Exception as e:
                last_exc = e
        if isinstance(last_exc, RuntimeError) and (
            "Unverified empty chunk" in str(last_exc)
            or "Detected silent empty chunk gap" in str(last_exc)
            or "during listed period" in str(last_exc)
            or "missing positive listing" in str(last_exc)
        ):
            raise last_exc
        raise RuntimeError(
            f"[{symbol}] Required chunk {start_date}..{end_date} failed after {max_chunk_retries} attempts"
        ) from last_exc

    chunk_results: List[Tuple[pd.Timestamp, pd.Timestamp, pd.DataFrame]] = []
    curr_start = start_dt
    total_attempts = 0
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=max_days), end_dt)
        chunk_success = False
        last_exc = None
        for attempt in range(1, max_chunk_retries + 1):
            if total_attempts >= max_total_attempts:
                raise RuntimeError(
                    f"[{symbol}] Upstream attempt ceiling ({max_total_attempts}) exhausted while fetching chunk {curr_start.date()}..{curr_end.date()}"
                )
            total_attempts += 1
            try:
                chunk = client.fetch_history(
                    symbol=symbol,
                    start_date=curr_start.strftime("%Y-%m-%d"),
                    end_date=curr_end.strftime("%Y-%m-%d"),
                    interval="1D",
                    normalize_vnd=True,
                )
                chunk_df = chunk if (chunk is not None and not chunk.empty) else pd.DataFrame()
                if chunk_df.empty:
                    is_pre_listing = list_dt is not None and curr_end < list_dt
                    is_post_delisting = delist_dt is not None and curr_start > delist_dt
                    if any(not c[2].empty for c in chunk_results) and not is_post_delisting:
                        if attempt < max_chunk_retries:
                            continue
                        raise RuntimeError(
                            f"[{symbol}] Detected silent empty chunk gap: chunk {curr_start.date()}..{curr_end.date()} returned no data while preceding chunks contain data"
                        )
                    if not (is_pre_listing or is_post_delisting):
                        if attempt < max_chunk_retries:
                            continue
                        if list_dt is None:
                            raise RuntimeError(
                                f"[{symbol}] Unverified empty chunk {curr_start.date()}..{curr_end.date()}: missing positive listing_date or trading continuity proof"
                            )
                        raise RuntimeError(
                            f"[{symbol}] Unverified empty chunk {curr_start.date()}..{curr_end.date()}: empty chunk during listed period (listing_date={list_dt.date()}) failed closed, missing positive listing_date or trading continuity proof"
                        )
                chunk_results.append((curr_start, curr_end, chunk_df))
                chunk_success = True
                break
            except Exception as e:
                last_exc = e
        if not chunk_success:
            if isinstance(last_exc, RuntimeError) and (
                "Unverified empty chunk" in str(last_exc)
                or "Detected silent empty chunk gap" in str(last_exc)
                or "during listed period" in str(last_exc)
                or "missing positive listing" in str(last_exc)
            ):
                raise last_exc
            raise RuntimeError(
                f"[{symbol}] Required chunk {curr_start.date()}..{curr_end.date()} failed after {max_chunk_retries} attempts"
            ) from last_exc
        curr_start = curr_end + timedelta(days=1)

    first_data_idx: Optional[int] = None
    last_data_idx: Optional[int] = None
    for idx, (_, _, c_df) in enumerate(chunk_results):
        if not c_df.empty:
            if first_data_idx is None:
                first_data_idx = idx
            last_data_idx = idx

    # Fail-closed validation for intermediate gaps
    if first_data_idx is not None and last_data_idx is not None:
        for i in range(first_data_idx + 1, last_data_idx):
            c_start, c_end, c_df = chunk_results[i]
            if c_df.empty:
                raise RuntimeError(
                    f"[{symbol}] Detected silent empty chunk gap: chunk {c_start.date()}..{c_end.date()} returned no data while subsequent chunks contain data"
                )

    # Fail-closed validation for leading empty chunks (must be proven pre-listing with positive listing metadata)
    if first_data_idx is not None and first_data_idx > 0:
        for i in range(0, first_data_idx):
            c_start, c_end, c_df = chunk_results[i]
            if c_df.empty:
                if list_dt is None:
                    raise RuntimeError(
                        f"[{symbol}] Unverified empty chunk {c_start.date()}..{c_end.date()}: missing positive listing_date or trading continuity proof"
                    )
                if not (c_end < list_dt):
                    raise RuntimeError(
                        f"[{symbol}] Unverified empty chunk {c_start.date()}..{c_end.date()}: empty chunk during listed period (listing_date={list_dt.date()}) failed closed, missing positive listing_date or trading continuity proof"
                    )

    # Fail-closed validation for trailing empty chunks (must be proven post-delisting with positive delisting metadata)
    if last_data_idx is not None and last_data_idx < len(chunk_results) - 1:
        for i in range(last_data_idx + 1, len(chunk_results)):
            c_start, c_end, c_df = chunk_results[i]
            if c_df.empty:
                if delist_dt is None or not (c_start > delist_dt):
                    raise RuntimeError(
                        f"[{symbol}] Unverified empty chunk {c_start.date()}..{c_end.date()}: missing positive listing_date or trading continuity proof"
                    )

    chunks = [c_df for _, _, c_df in chunk_results if not c_df.empty]
    if not chunks:
        if list_dt is not None and end_dt < list_dt:
            return pd.DataFrame()
        if delist_dt is not None and start_dt > delist_dt:
            return pd.DataFrame()
        if list_dt is None:
            raise RuntimeError(
                f"[{symbol}] All required chunks returned unverified empty data without positive listing proof"
            )
        raise RuntimeError(
            f"[{symbol}] All required chunks returned empty data during listed period (listing_date={list_dt.date()}): missing positive listing_date or trading continuity proof"
        )
    out = pd.concat(chunks, ignore_index=True)
    date_col = "time" if "time" in out.columns else ("date" if "date" in out.columns else None)
    if date_col is not None:
        out["_temp_dt"] = pd.to_datetime(out[date_col], errors="coerce")
        out = (
            out.dropna(subset=["_temp_dt"])
            .drop_duplicates(subset=["_temp_dt"], keep="last")
            .sort_values("_temp_dt")
            .drop(columns=["_temp_dt"])
            .reset_index(drop=True)
        )
    return out


def fetch_one_symbol(
    client,
    symbol: str,
    start_date: str,
    end_date: str,
    exchange: str,
    listing_date: Optional[str] = None,
    delisting_date: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch OHLCV for one symbol from VCI, returning canonical-schema DataFrame."""
    df = _fetch_history_chunked(
        client=client,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        listing_date=listing_date,
        delisting_date=delisting_date,
    )

    if df is None or df.empty:
        return pd.DataFrame()

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
    df["available_at"] = _vci_available_at(df["date"])
    df["source"] = "vnstock_vci"
    df["price_scale"] = PRICE_SCALE_LABEL
    df["adjusted"] = "backward_adjusted"
    df["rebuild_date"] = "2026-06-13"

    # Select and order canonical columns
    existing = [c for c in CANONICAL_COLUMNS if c in df.columns]
    return df[existing].copy()


def _vci_available_at(dates: pd.Series) -> pd.Series:
    """Return canonical start-of-next-day dissemination time in Vietnam time."""
    return (pd.to_datetime(dates).dt.normalize() + timedelta(days=1)).dt.tz_localize(VN_TZ)


def _normalize_legacy_vci_available_at(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize PIT timestamps; repair only positively identified legacy VCI rows."""
    normalized = df.copy()
    if "price_scale" in normalized.columns:
        normalized["price_scale"] = normalized["price_scale"].fillna(PRICE_SCALE_LABEL)
    if "adjusted" in normalized.columns:
        normalized["adjusted"] = normalized["adjusted"].fillna("backward_adjusted")
    if "rebuild_date" in normalized.columns:
        normalized["rebuild_date"] = normalized["rebuild_date"].fillna("2026-06-13")
    vci_rows = _is_legacy_vci_provenance(normalized)
    normalized["available_at"] = pd.to_datetime(
        normalized["available_at"], errors="coerce", utc=True
    ).dt.tz_convert(VN_TZ)
    normalized.loc[vci_rows, "available_at"] = _vci_available_at(normalized.loc[vci_rows, "date"])
    return normalized


def _is_legacy_vci_provenance(df: pd.DataFrame) -> pd.Series:
    """Classify only known VCI source aliases or the complete canonical legacy signature."""
    required = {"source", *LEGACY_VCI_PROVENANCE}
    if not required.issubset(df.columns):
        return pd.Series(False, index=df.index)
    source = df["source"].astype("string").str.strip().str.casefold()
    known_vci_source = source.isin(LEGACY_VCI_SOURCE_VALUES)
    canonical_signature = pd.Series(True, index=df.index)
    for field, value in LEGACY_VCI_PROVENANCE.items():
        canonical_signature &= df[field].astype("string").str.strip().eq(value)
    return known_vci_source | (source.isna() | source.eq("")) & canonical_signature


def merge_canonical_and_new(existing: pd.DataFrame, new_data: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Merge ordinary overlaps only when immutable market fields agree."""
    existing = _normalize_legacy_vci_available_at(existing)
    new_data = _normalize_legacy_vci_available_at(new_data)
    combined = pd.concat([existing, new_data], ignore_index=True)
    duplicate_mask = combined.duplicated(["ticker", "date"], keep=False)
    conflicts: List[str] = []
    for (ticker, date), rows in combined.loc[duplicate_mask].groupby(["ticker", "date"], sort=False):
        if len(rows[OVERLAP_EQUIVALENCE_COLUMNS].drop_duplicates()) != 1:
            conflicts.append(f"overlap conflict: {ticker} {pd.Timestamp(date).date()}")
    if conflicts:
        return combined, conflicts
    return combined.drop_duplicates(["ticker", "date"], keep="first").sort_values(
        ["ticker", "date"]
    ).reset_index(drop=True), []


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

def _pit_timestamp_errors(df: pd.DataFrame, label: str) -> List[str]:
    """Require aware available_at on the exact date+1 calendar-day rule."""
    if "available_at" not in df.columns or "date" not in df.columns:
        return []
    expected = pd.to_datetime(df["date"], errors="coerce").dt.normalize() + timedelta(days=1)
    available = df["available_at"]
    parsed = pd.to_datetime(available, errors="coerce", utc=True)
    if isinstance(available.dtype, pd.DatetimeTZDtype):
        timezone_aware = pd.Series(True, index=df.index)
    else:
        timezone_aware = available.astype("string").str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True, na=False)
    local = parsed.dt.tz_convert(VN_TZ)
    invalid = (
        expected.isna()
        | parsed.isna()
        | ~timezone_aware
        | ~local.dt.normalize().dt.tz_localize(None).eq(expected)
        | local.dt.hour.ne(0)
        | local.dt.minute.ne(0)
        | local.dt.second.ne(0)
        | local.dt.microsecond.ne(0)
    )
    invalid_count = int(invalid.sum())
    if not invalid_count:
        return []
    return [
        f"{label}: {invalid_count} available_at values must be timezone-aware and equal date + 1 day at 00:00:00.000000 Asia/Ho_Chi_Minh"
    ]

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

    # 4. Non-positive OHLC and finiteness
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            bad_ct = int(((vals <= 0) | (~np.isfinite(vals))).sum())
            if bad_ct > 0:
                errors.append(f"{label}: {bad_ct} non-positive/non-finite values in '{col}'")

    # 5. Negative volume and finiteness
    if "volume" in df.columns:
        vol_vals = pd.to_numeric(df["volume"], errors="coerce")
        neg_vol = int(((vol_vals < 0) | (~np.isfinite(vol_vals))).sum())
        if neg_vol > 0:
            errors.append(f"{label}: {neg_vol} negative/non-finite volume values")

    # 5b. OHLC relationship invariants: high >= max(open, close, low), low <= min(open, close, high)
    if all(c in df.columns for c in ("open", "high", "low", "close")):
        h = pd.to_numeric(df["high"], errors="coerce")
        l = pd.to_numeric(df["low"], errors="coerce")
        o = pd.to_numeric(df["open"], errors="coerce")
        c = pd.to_numeric(df["close"], errors="coerce")
        bad_high = int(((h < o) | (h < c) | (h < l)).sum())
        if bad_high > 0:
            errors.append(f"{label}: {bad_high} rows where high < max(open, close, low)")
        bad_low = int(((l > o) | (l > c) | (l > h)).sum())
        if bad_low > 0:
            errors.append(f"{label}: {bad_low} rows where low > min(open, close, high)")

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

    # 8. PIT available_at = date + 1, timezone-aware
    errors.extend(_pit_timestamp_errors(df, label))

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
# Atomic Write with Backup & Directory Durability
# ═══════════════════════════════════════════════════════════════════════════════

def _fsync_directory(path: Path) -> None:
    """Fsync directory for durability; safe on POSIX and Windows."""
    try:
        if os.name == "nt":
            return
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (AttributeError, OSError):
        pass


def atomic_write_with_backup(
    df: pd.DataFrame,
    target_path: Path,
    backup: bool = True,
    lock_timeout_seconds: float = 60.0,
) -> Path:
    """Write DataFrame to parquet atomically with optional backup and writer exclusion.

    Certified atomic write ordering:
      1. Temp write: serialize DataFrame to unique temp file on the same filesystem.
      2. File fsync: flush and fsync temp file descriptors.
      3. Validation: validate serialized parquet readback and row count before replacement.
      4. Backup: create durable backup of existing file (if backup=True and target exists).
      5. Atomic replace: atomically replace target with temp file.
      6. Directory fsync: fsync parent directory for crash durability. Rollback on failure.

    Returns the path written to.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")

    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target_path.parent / f".{target_path.name}.lock"

    from filelock import FileLock

    with FileLock(str(lock_path), timeout=lock_timeout_seconds):
        had_existing = target_path.exists()
        backup_path: Optional[Path] = None

        # Write to temp file in same directory (guaranteed same filesystem)
        with tempfile.NamedTemporaryFile(
            dir=str(target_path.parent),
            prefix=f".tmp_{target_path.stem}_",
            suffix=".parquet.tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        try:
            # 1. Temp write
            df.to_parquet(temp_path, index=False)

            # 2. File fsync
            with temp_path.open("rb+") as stream:
                stream.flush()
                os.fsync(stream.fileno())

            # 3. Validation
            readback = pd.read_parquet(temp_path)
            if len(readback) != len(df):
                raise ValueError(
                    f"Temp parquet verification failed: expected {len(df)} rows, got {len(readback)}"
                )

            # 4. Backup (only after temp write, fsync, and readback validation succeed)
            if backup and had_existing:
                backup_path = target_path.with_suffix(".parquet.bak")
                shutil.copy2(str(target_path), str(backup_path))
                with backup_path.open("rb+") as bstream:
                    bstream.flush()
                    os.fsync(bstream.fileno())
                logger.info(f"Backup created: {backup_path}")

            # 5. Atomic replace
            os.replace(temp_path, target_path)

            # 6. Directory fsync
            _fsync_directory(target_path.parent)
            logger.info(f"Atomic write complete: {target_path} ({len(df)} rows)")
        except Exception as exc:
            # Rollback: if target was lost during replacement but backup exists, restore target
            if had_existing and backup_path is not None and backup_path.exists() and not target_path.exists():
                try:
                    shutil.copy2(str(backup_path), str(target_path))
                    with target_path.open("rb+") as rstream:
                        rstream.flush()
                        os.fsync(rstream.fileno())
                    _fsync_directory(target_path.parent)
                except Exception:
                    pass
            raise exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    return target_path


def _write_fsync(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    with path.open("rb+") as stream:
        os.fsync(stream.fileno())
    if os.name != "nt":
        _fsync_directory(path.parent)


def _write_immutable_json(path: Path, payload: Dict) -> Path:
    """Create an append-only, durable receipt through an atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"immutable receipt collision: {path.name}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise RuntimeError(f"immutable receipt collision: {path.name}")
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def _reject_duplicate_keys(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_strict_json(path: Path) -> Dict:
    try:
        value = json.loads(path.read_bytes().decode("utf-8", errors="strict"), object_pairs_hook=_reject_duplicate_keys, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("receipt must be object")
    return value


def _canonical_json(value: object) -> bytes:
    if value is None or isinstance(value, bool) or isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).encode("ascii")
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("nonfinite JSON")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("ascii")
    if isinstance(value, list):
        return b"[" + b",".join(_canonical_json(item) for item in value) + b"]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return b"{" + b",".join(_canonical_json(key) + b":" + _canonical_json(value[key]) for key in sorted(value)) + b"}"
    raise ValueError("unsupported JSON value")


def _trusted_keyring() -> Tuple[str, Dict[str, bytes]]:
    active_id = os.environ.get(MARKET_DATA_RECEIPT_ACTIVE_KEY_ID, "")
    raw = os.environ.get(MARKET_DATA_RECEIPT_KEYRING, "")
    if not active_id or not raw:
        raise RuntimeError("market receipt signing configuration unavailable")
    try:
        keyring = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("market receipt keyring invalid") from exc
    if not isinstance(keyring, dict) or not keyring:
        raise RuntimeError("market receipt keyring invalid")
    parsed = {}
    for key_id, encoded in keyring.items():
        if not isinstance(key_id, str) or not __import__("re").fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id) or not isinstance(encoded, str):
            raise RuntimeError("market receipt keyring invalid")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("market receipt keyring invalid") from exc
        if len(key) < 32:
            raise RuntimeError("market receipt keyring invalid")
        parsed[key_id] = key
    if active_id not in parsed:
        raise RuntimeError("market receipt active key unavailable")
    return active_id, parsed


def _trusted_lifecycle_keyring() -> Dict[str, Tuple[bytes, Set[str]]]:
    raw = os.environ.get(LIFECYCLE_RECEIPT_KEYRING, "")
    if not raw:
        raise RuntimeError("lifecycle receipt keyring unavailable")
    try:
        keyring = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("lifecycle receipt keyring invalid") from exc
    if not isinstance(keyring, dict) or not keyring:
        raise RuntimeError("lifecycle receipt keyring invalid")
    parsed = {}
    for key_id, metadata in keyring.items():
        if not isinstance(key_id, str) or __import__("re").fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id) is None or not isinstance(metadata, dict) or set(metadata) != {"secret", "sources"} or not isinstance(metadata["secret"], str) or not isinstance(metadata["sources"], list):
            raise RuntimeError("lifecycle receipt keyring invalid")
        try:
            key = base64.b64decode(metadata["secret"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("lifecycle receipt keyring invalid") from exc
        sources = set(metadata["sources"])
        if len(key) < 32 or not sources or any(not isinstance(source, str) or not source for source in sources):
            raise RuntimeError("lifecycle receipt keyring invalid")
        parsed[key_id] = (key, sources)
    return parsed


def _sign_receipt(record: Dict, active_id: str, key: bytes) -> Dict:
    record = dict(record)
    record["integrity"] = {"algorithm": MARKET_DATA_RECEIPT_ALGORITHM, "key_id": active_id}
    signature = hmac.new(key, _canonical_json(record), hashlib.sha256).hexdigest()
    record["integrity"]["signature"] = signature
    return record


def verify_market_data_receipt(record: Dict) -> bool:
    try:
        state = record["state"]
        if state not in MARKET_DATA_RECEIPT_FIELDS or set(record) != MARKET_DATA_RECEIPT_FIELDS[state]:
            return False
        integrity = record["integrity"]
        if set(integrity) != {"algorithm", "key_id", "signature"} or integrity["algorithm"] != MARKET_DATA_RECEIPT_ALGORITHM:
            return False
        _, keyring = _trusted_keyring()
        key = keyring.get(integrity["key_id"])
        signature = integrity["signature"]
        if key is None or not isinstance(signature, str) or len(signature) != 64:
            return False
        unsigned = dict(record)
        unsigned["integrity"] = dict(integrity)
        del unsigned["integrity"]["signature"]
        return hmac.compare_digest(signature, hmac.new(key, _canonical_json(unsigned), hashlib.sha256).hexdigest())
    except (KeyError, TypeError, ValueError, RuntimeError):
        return False


def start_market_data_attempt(receipt_dir: Path = MARKET_DATA_RECEIPT_DIR, now: Optional[datetime] = None) -> Dict:
    active_id, keyring = _trusted_keyring()
    now = now or datetime.now(timezone.utc)
    attempt_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex
    record = {
        "schema_version": MARKET_DATA_ATTEMPT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "state": "in_progress",
        "started_at": now.isoformat(timespec="seconds"),
        "execution_allowed": False,
    }
    record = _sign_receipt(record, active_id, keyring[active_id])
    path = _write_immutable_json(receipt_dir / f"{attempt_id}.in_progress.json", record)
    return {"attempt_id": attempt_id, "path": path, "record": record}


def finish_market_data_attempt(
    attempt: Dict,
    result: Dict,
    projection_error: Optional[str] = None,
    receipt_dir: Path = MARKET_DATA_RECEIPT_DIR,
    projection_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Dict:
    active_id, keyring = _trusted_keyring()
    projection_failed = bool(projection_error)
    projection_path = projection_path or MARKET_DATA_PROJECTION
    projection_sha256 = _sha256(projection_path) if projection_error is None and projection_path.is_file() else None
    completed_at = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    gate_evidence = _gate_evidence_from_result(result, attempt["attempt_id"], projection_path, projection_sha256)
    allowed = not projection_failed and validate_gate_evidence(gate_evidence, attempt["attempt_id"], completed_at)
    terminal_session = gate_evidence["terminal_session"] if allowed else None
    record = {
        "schema_version": MARKET_DATA_ATTEMPT_SCHEMA_VERSION,
        "attempt_id": attempt["attempt_id"],
        "state": "terminal",
        "started_at": attempt["record"]["started_at"],
        "completed_at": completed_at,
        "published": allowed,
        "stale": not allowed,
        "terminal_session": terminal_session,
        "execution_allowed": allowed,
        "reason": "eligible" if allowed else f"projection_failed: {projection_error}" if projection_failed else "pit_evidence_invalid",
        "publication": {"run_id": result.get("run_id"), "candidate_path": result.get("candidate_path"), "pointer_path": result.get("pointer_path"), "sha256": result.get("sha256")},
        "projection_path": str(projection_path),
        "projection_sha256": projection_sha256,
        "projection_attempt_id": attempt["attempt_id"],
        "provenance": {"result_status": result.get("status"), "publication_run_id": result.get("run_id"), "projection_error": projection_error},
        "gate_evidence": gate_evidence,
    }
    record = _sign_receipt(record, active_id, keyring[active_id])
    path = _write_immutable_json(receipt_dir / f"{attempt['attempt_id']}.terminal.json", record)
    return {"path": path, "record": record}


def _write_quarantine(path: Path, content: bytes) -> None:
    """Persist quarantine bytes; Windows makes no directory-durability claim."""
    path.write_bytes(content)
    with path.open("rb+") as stream:
        os.fsync(stream.fileno())
    if os.name != "nt":
        _fsync_directory(path.parent)


class _PublicationLockLease:
    def __init__(self, token: str, fd: int, identity: tuple[int, int]) -> None:
        self.token = token
        self.fd = fd
        self.identity = identity


def _open_lock_lease(lock_path: Path, payload: Dict[str, object]) -> _PublicationLockLease:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            wintypes.LPCWSTR(str(lock_path)),
            0x00010000 | 0x80000000 | 0x40000000,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            1,
            0x00000080,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            error = ctypes.get_last_error()
            if error in (80, 183):
                raise FileExistsError(error, "CreateFileW", str(lock_path))
            raise OSError(error, "CreateFileW", str(lock_path))
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR | getattr(os, "O_BINARY", 0))
    else:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _lock_fd(fd)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        stat = os.fstat(fd)
        return _PublicationLockLease(str(payload["token"]), fd, (stat.st_dev, stat.st_ino))
    except Exception:
        _unlock_fd(fd)
        os.close(fd)
        raise


def _lock_fd(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _mark_handle_delete_pending_windows(fd: int) -> None:
    """Delete the object bound to fd, never a separately resolved pathname."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    disposition = ctypes.c_ubyte(1)
    handle = msvcrt.get_osfhandle(fd)
    if kernel32.SetFileInformationByHandle(
        wintypes.HANDLE(handle), 4, ctypes.byref(disposition), ctypes.sizeof(disposition)
    ):
        return
    error = ctypes.get_last_error()
    raise OSError(error, "SetFileInformationByHandle")


def _acquire_publication_lock(lock_path: Path) -> _PublicationLockLease:
    token = uuid.uuid4().hex
    payload = {"pid": os.getpid(), "started_at": time.time(), "token": token}
    try:
        return _open_lock_lease(lock_path, payload)
    except FileExistsError as exc:
        raise RuntimeError("publication lock held; operator recovery required") from exc


def _release_publication_lock(lock_path: Path, lease: _PublicationLockLease) -> None:
    try:
        os.lseek(lease.fd, 0, os.SEEK_SET)
        owner = json.load(os.fdopen(lease.fd, "r", encoding="utf-8", closefd=False))
    except (OSError, ValueError, json.JSONDecodeError):
        _unlock_fd(lease.fd)
        os.close(lease.fd)
        return
    try:
        current = os.fstat(lease.fd)
        if owner.get("token") != lease.token or (current.st_dev, current.st_ino) != lease.identity:
            os.close(lease.fd)
            lease.fd = -1
            raise RuntimeError("publication lock owner mismatch")
        if os.name == "nt":
            _mark_handle_delete_pending_windows(lease.fd)
        else:
            raise RuntimeError("safe identity-bound lock deletion unavailable on this platform")
        _unlock_fd(lease.fd)
        os.close(lease.fd)
        lease.fd = -1
    finally:
        if lease.fd >= 0:
            _unlock_fd(lease.fd)
            os.close(lease.fd)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_hex(value: bytes) -> str:
    """Hash immutable in-memory candidate bytes."""
    return hashlib.sha256(value).hexdigest()


def _parse_aware_timestamp(value: object, label: str) -> datetime:
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{label} must be an aware ISO timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be an aware ISO timestamp")
    return parsed.astimezone(timezone.utc)


def _vn_trading_days(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Return documented Vietnam trading sessions in the inclusive range."""
    holidays = json.loads(VN_HOLIDAYS_PATH.read_text(encoding="utf-8")).get("holidays", {})
    closed = {day for dates in holidays.values() for day in dates}
    days = pd.date_range(start.normalize(), end.normalize(), freq="B")
    return days[~days.strftime("%Y-%m-%d").isin(closed)]


def _canonical_terminal_by_ticker(canonical_path: Path) -> Dict[str, pd.Timestamp]:
    if not canonical_path.exists():
        return {}
    dates = pd.read_parquet(canonical_path, columns=["ticker", "date"])
    dates["date"] = pd.to_datetime(dates["date"]).dt.normalize()
    return {
        str(ticker).upper(): terminal
        for ticker, terminal in dates.groupby("ticker")["date"].max().items()
    }


def _load_ticker_lifecycle(path: Path = TICKER_LIFECYCLE_PATH) -> Dict[str, Dict]:
    """Load signed lifecycle envelopes; mutable repository labels are never evidence."""
    if not path.exists():
        return {}
    try:
        data = _load_strict_json(path)
    except ValueError:
        return {}
    entries = data.get("evidence") if data.get("schema_version") == LIFECYCLE_EVIDENCE_SCHEMA_VERSION else None
    if not isinstance(entries, list):
        return {}
    result = {}
    for envelope in entries:
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        ticker = payload.get("ticker") if isinstance(payload, dict) else None
        if isinstance(ticker, str) and ticker.upper() not in result:
            result[ticker.upper()] = envelope
    return result


def _claim_lifecycle_receipt(evidence: Dict, payload: Dict, ledger_dir: Path) -> Optional[str]:
    ledger = {"schema_version": LIFECYCLE_RECEIPT_LEDGER_SCHEMA_VERSION, "receipt_id": evidence["receipt_id"], "receipt_sha256": sha256_hex(_canonical_json(evidence)), "key_id": evidence["integrity"]["key_id"], "source": payload["source"], "ticker": payload["ticker"]}
    ledger_bytes = _canonical_json(ledger)
    path = ledger_dir / f"{evidence['receipt_id']}.json"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    created_identity = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            if path.read_bytes() != _canonical_json(_load_strict_json(path)) or _load_strict_json(path) != ledger:
                return "receipt ledger integrity invalid"
        except (OSError, ValueError):
            return "receipt ledger integrity invalid"
        return "evidence receipt replayed"
    try:
        created_identity = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        with os.fdopen(fd, "wb") as stream:
            stream.write(ledger_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(ledger_dir)
        if path.read_bytes() != ledger_bytes or _load_strict_json(path) != ledger:
            raise RuntimeError("lifecycle receipt claim verification failed")
    except Exception:
        try:
            current = path.stat()
            if created_identity == (current.st_dev, current.st_ino):
                path.unlink()
                if path.exists():
                    raise RuntimeError("lifecycle receipt claim cleanup failed")
            _fsync_directory(ledger_dir)
        except FileNotFoundError:
            _fsync_directory(ledger_dir)
        except Exception as cleanup_error:
            raise RuntimeError("lifecycle receipt claim cleanup failed") from cleanup_error
        raise RuntimeError("lifecycle receipt claim failed")
    return None


def _sparse_terminal_evidence_error(
    ticker: str,
    terminal: pd.Timestamp,
    authority_terminal: pd.Timestamp,
    cutoff_at: datetime,
    evidence: object,
    used_receipt_ids: Set[str],
    lifecycle_receipt_ledger_dir: Optional[Path] = None,
    claim_receipt: bool = True,
) -> Optional[str]:
    if not isinstance(evidence, dict):
        return "missing independent lifecycle/provider evidence"
    if set(evidence) != LIFECYCLE_EVIDENCE_FIELDS or evidence.get("schema_version") != LIFECYCLE_EVIDENCE_SCHEMA_VERSION:
        return "evidence envelope invalid"
    payload, integrity = evidence.get("payload"), evidence.get("integrity")
    if not isinstance(payload, dict) or set(payload) != LIFECYCLE_EVIDENCE_PAYLOAD_FIELDS:
        return "evidence payload invalid"
    if not isinstance(integrity, dict) or set(integrity) != LIFECYCLE_EVIDENCE_INTEGRITY_FIELDS:
        return "evidence integrity invalid"
    receipt_id = evidence.get("receipt_id")
    if not isinstance(receipt_id, str) or not __import__("re").fullmatch(r"[A-Za-z0-9._-]{16,128}", receipt_id):
        return "evidence receipt ID invalid"
    if receipt_id in used_receipt_ids:
        return "evidence receipt replayed"
    try:
        key_metadata, signature = _trusted_lifecycle_keyring().get(integrity.get("key_id")), integrity.get("signature")
        key = key_metadata[0] if key_metadata else None
        unsigned = dict(evidence)
        unsigned_integrity = dict(integrity)
        unsigned_integrity.pop("signature")
        unsigned["integrity"] = unsigned_integrity
        if integrity.get("algorithm") != LIFECYCLE_EVIDENCE_ALGORITHM or key is None or payload.get("source") not in key_metadata[1] or not isinstance(signature, str) or len(signature) != 64 or integrity.get("payload_sha256") != sha256_hex(_canonical_json(payload)) or not hmac.compare_digest(signature, hmac.new(key, _canonical_json(unsigned), hashlib.sha256).hexdigest()):
            return "evidence signature invalid"
    except (TypeError, ValueError, RuntimeError):
        return "evidence signature invalid"
    if payload.get("ticker") != ticker:
        return "evidence ticker mismatch"
    if payload.get("status") not in SPARSE_TERMINAL_STATUSES:
        return "evidence status is not halted, suspended, or delisted"
    if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
        return "evidence reason missing"
    try:
        effective_at = _parse_aware_timestamp(payload.get("effective_at"), "evidence effective_at")
        evidence_as_of = _parse_aware_timestamp(payload.get("as_of"), "evidence as_of")
        signed_at = _parse_aware_timestamp(evidence.get("signed_at"), "evidence signed_at")
        expires_at = _parse_aware_timestamp(evidence.get("expires_at"), "evidence expires_at")
    except ValueError:
        return "evidence timestamp invalid"
    if not effective_at <= evidence_as_of <= signed_at <= cutoff_at < expires_at:
        return "evidence timestamp ordering invalid"
    if cutoff_at - signed_at > LIFECYCLE_RECEIPT_MAX_SIGNING_AGE:
        return "evidence signing age exceeds maximum"
    if evidence_as_of.date() < authority_terminal.date() or evidence_as_of.date() < terminal.date():
        return "evidence as_of is stale"
    if claim_receipt:
        claim_error = _claim_lifecycle_receipt(
            evidence, payload, lifecycle_receipt_ledger_dir or LIFECYCLE_RECEIPT_LEDGER_DIR,
        )
        if claim_error:
            return claim_error
    used_receipt_ids.add(receipt_id)
    return None


def _vci_terminal_evidence(
    candidate: pd.DataFrame,
    requested_symbols: List[str],
    requested_end: pd.Timestamp,
    canonical_max: Optional[pd.Timestamp],
    cutoff_at: datetime,
    canonical_terminals: Optional[Dict[str, pd.Timestamp]] = None,
    sparse_terminal_evidence: Optional[Dict[str, Dict]] = None,
    lifecycle_receipt_ledger_dir: Optional[Path] = None,
    claim_receipts: bool = True,
    bypass_lifecycle: bool = False,
) -> Tuple[bool, List[str], Dict]:
    """Derive VCI authority while preserving reconciled sparse histories."""
    errors: List[str] = []
    requested = {str(ticker).upper() for ticker in requested_symbols}
    observed = set(candidate["ticker"].astype(str).str.upper()) if "ticker" in candidate else set()
    terminal_by_ticker: Dict[str, str] = {}
    sparse_exceptions: Dict[str, str] = {}
    used_lifecycle_receipt_ids: Set[str] = set()
    if candidate.empty:
        errors.append("candidate: empty")
    else:
        missing = requested - observed
        if missing:
            errors.append(f"coverage: missing requested tickers: {sorted(missing)}")
        for ticker in sorted(requested):
            rows = candidate[candidate["ticker"].astype(str).str.upper() == ticker]
            if rows.empty:
                errors.append(f"coverage: missing ticker {ticker}")
                continue
            terminal_by_ticker[ticker] = pd.to_datetime(rows["date"]).max().strftime("%Y-%m-%d")
        terminal_counts = pd.Series(terminal_by_ticker).value_counts()
        terminal_session = terminal_counts.index[0] if not terminal_counts.empty else None
        if terminal_session:
            terminal = pd.Timestamp(terminal_session)
            if terminal_counts.iloc[0] <= len(requested) // 2:
                errors.append("terminal_session: no common authority cohort")
            if terminal != pd.Timestamp(max(terminal_by_ticker.values())):
                errors.append("terminal_session: common authority is not latest observed session")
            if terminal > requested_end.normalize():
                errors.append("terminal_session: beyond requested end")
            elif terminal not in _vn_trading_days(terminal, terminal):
                errors.append("terminal_session: authority is not a Vietnam trading session")
            for ticker, value in terminal_by_ticker.items():
                ticker_terminal = pd.Timestamp(value)
                if ticker_terminal > requested_end.normalize():
                    errors.append(f"terminal_session: {ticker} beyond requested end")
                    continue
                if ticker_terminal not in _vn_trading_days(ticker_terminal, ticker_terminal):
                    errors.append(f"terminal_session: {ticker} terminal is not a Vietnam trading session")
                    continue
                canonical_terminal = (canonical_terminals or {}).get(ticker)
                if canonical_terminal is not None and ticker_terminal < canonical_terminal.normalize():
                    errors.append(f"terminal_session: {ticker} regressed below canonical terminal")
                    continue
                missed_sessions = len(_vn_trading_days(ticker_terminal + timedelta(days=1), terminal))
                if missed_sessions > SPARSE_TERMINAL_MAX_MISSED_SESSIONS:
                    if bypass_lifecycle:
                        sparse_exceptions[ticker] = "bypassed_by_flag"
                    else:
                        evidence_error = _sparse_terminal_evidence_error(
                            ticker, ticker_terminal, terminal, cutoff_at,
                            (sparse_terminal_evidence or {}).get(ticker),
                            used_lifecycle_receipt_ids,
                            lifecycle_receipt_ledger_dir,
                            claim_receipt=claim_receipts,
                        )
                        if evidence_error:
                            errors.append(
                                f"terminal_session: {ticker} stale {missed_sessions} sessions: {evidence_error}"
                            )
                        else:
                            sparse_exceptions[ticker] = "independent_lifecycle_or_provider_evidence"
        try:
            cutoff_vn = cutoff_at.astimezone(VN_TZ)
            allowed_max_date = cutoff_vn.date() + timedelta(days=1 if cutoff_vn.hour >= 15 else 0)
            allowed_max_ts = pd.Timestamp(allowed_max_date, tz=VN_TZ).to_pydatetime()
            effective_cutoff = max(cutoff_at, allowed_max_ts)
            if any(_parse_aware_timestamp(value, "available_at") > effective_cutoff for value in candidate["available_at"]):
                errors.append("provenance: available_at exceeds cutoff")
        except (TypeError, ValueError):
            errors.append("provenance: invalid available_at")
    terminal_session = pd.Series(terminal_by_ticker).value_counts().index[0] if terminal_by_ticker else None
    return not errors, errors, {
        "provider": "VCI",
        "requested_symbols": sorted(requested_symbols),
        "terminal_by_ticker": terminal_by_ticker,
        "terminal_session": terminal_session,
        "sparse_terminal_max_missed_sessions": SPARSE_TERMINAL_MAX_MISSED_SESSIONS,
        "sparse_terminal_exceptions": sparse_exceptions,
        "cutoff_at": cutoff_at.isoformat(),
        "validation_outcome": "passed" if not errors else "failed",
    }


def _claim_sparse_terminal_receipts(
    authority: Dict,
    sparse_terminal_evidence: Optional[Dict[str, Dict]],
    lifecycle_receipt_ledger_dir: Optional[Path],
    claimed_receipt_ids: Optional[Set[str]] = None,
) -> List[str]:
    """Consume lifecycle receipts only after every release gate has passed."""
    errors = []
    for ticker in authority.get("sparse_terminal_exceptions", {}):
        evidence = (sparse_terminal_evidence or {}).get(ticker)
        if evidence is None:
            errors.append(f"terminal_session: {ticker} lifecycle receipt: evidence missing")
            continue
        claim_error = _claim_lifecycle_receipt(
            evidence, evidence["payload"],
            lifecycle_receipt_ledger_dir or LIFECYCLE_RECEIPT_LEDGER_DIR,
        )
        if claim_error:
            errors.append(f"terminal_session: {ticker} lifecycle receipt: {claim_error}")
        elif claimed_receipt_ids is not None:
            claimed_receipt_ids.add(evidence["receipt_id"])
    return errors


def _release_lifecycle_receipt_claims(
    authority: Dict,
    sparse_terminal_evidence: Optional[Dict[str, Dict]],
    lifecycle_receipt_ledger_dir: Optional[Path],
    claimed_receipt_ids: Set[str],
) -> None:
    """Undo claims made by this unpublished transaction."""
    ledger_dir = lifecycle_receipt_ledger_dir or LIFECYCLE_RECEIPT_LEDGER_DIR
    for ticker in authority.get("sparse_terminal_exceptions", {}):
        evidence = (sparse_terminal_evidence or {}).get(ticker)
        if evidence is None or evidence["receipt_id"] not in claimed_receipt_ids:
            continue
        path = ledger_dir / f"{evidence['receipt_id']}.json"
        expected = {
            "schema_version": LIFECYCLE_RECEIPT_LEDGER_SCHEMA_VERSION,
            "receipt_id": evidence["receipt_id"],
            "receipt_sha256": sha256_hex(_canonical_json(evidence)),
            "key_id": evidence["integrity"]["key_id"],
            "source": evidence["payload"]["source"],
            "ticker": evidence["payload"]["ticker"],
        }
        if not path.exists() or path.read_bytes() != _canonical_json(expected):
            raise RuntimeError("lifecycle receipt claim rollback verification failed")
        path.unlink()
        if path.exists():
            raise RuntimeError("lifecycle receipt claim rollback failed")
        _fsync_directory(ledger_dir)


def _restore_publication_pointer(pointer_path: Path, prior_pointer: Optional[bytes]) -> None:
    """Restore and durably verify the pointer after an unpublished failure."""
    if prior_pointer is None:
        pointer_path.unlink(missing_ok=True)
        _fsync_directory(pointer_path.parent)
        if pointer_path.exists():
            raise RuntimeError("publication pointer rollback verification failed")
        return
    restore_path = pointer_path.with_suffix(pointer_path.suffix + ".rollback.tmp")
    restore_path.write_bytes(prior_pointer)
    with restore_path.open("rb+") as stream:
        os.fsync(stream.fileno())
    os.replace(str(restore_path), str(pointer_path))
    with pointer_path.open("rb+") as stream:
        os.fsync(stream.fileno())
    _fsync_directory(pointer_path.parent)
    if pointer_path.read_bytes() != prior_pointer:
        raise RuntimeError("publication pointer rollback verification failed")


def _validate_phase_coverage(
    candidate: pd.DataFrame,
    requested_symbols: List[str],
    fetch_stats: Dict,
    full_refetch_stats: Optional[Dict],
) -> List[str]:
    """Require each requested ticker to survive the incremental or final full-history phase."""
    errors: List[str] = []
    requested = {str(ticker).upper() for ticker in requested_symbols}
    details = (full_refetch_stats or {}).get("details", [])
    full_targets = {str(detail.get("symbol", "")).upper() for detail in details}
    full_success = {
        str(detail.get("symbol", "")).upper()
        for detail in details
        if detail.get("status") == "success"
    }
    if full_targets - requested:
        errors.append("coverage: full-history refetch includes unrequested ticker")
    if full_targets - full_success:
        errors.append("coverage: full-history refetch ticker missing or failed")
    if fetch_stats.get("empty", 0) or fetch_stats.get("empty_tickers"):
        errors.append(f"source empty tickers: {fetch_stats.get('empty_tickers', [])}")
    observed = set(candidate["ticker"].astype(str).str.upper()) if "ticker" in candidate else set()
    missing = requested - observed
    if missing:
        errors.append(f"coverage: missing requested tickers: {sorted(missing)}")
    return errors


def validate_gate_evidence(evidence: object, attempt_id: str, completed_at: str) -> bool:
    if not isinstance(evidence, dict) or set(evidence) != GATE_EVIDENCE_FIELDS:
        return False
    strings = ("terminal_session", "cutoff_at", "candidate_path", "pointer_path", "projection_path", "projection_attempt_id", "vci_authority_receipt_path")
    if evidence.get("schema_version") != VCI_AUTHORITY_RECEIPT_SCHEMA_VERSION or evidence.get("projection_attempt_id") != attempt_id or evidence.get("release_gate_passed") is not True or any(not isinstance(evidence.get(key), str) or not evidence[key] for key in strings) or any(not isinstance(evidence.get(key), str) or __import__("re").fullmatch(r"[0-9a-f]{64}", evidence[key]) is None for key in ("candidate_sha256", "pointer_sha256", "projection_sha256", "vci_authority_receipt_sha256")):
        return False
    try:
        cutoff = _parse_aware_timestamp(evidence["cutoff_at"], "cutoff_at")
        pointer_path, projection_path, candidate_path = (Path(evidence[key]) for key in ("pointer_path", "projection_path", "candidate_path"))
        pointer, projection = _load_strict_json(pointer_path), _load_strict_json(projection_path)
        authority_path = Path(evidence["vci_authority_receipt_path"])
        authority = _load_strict_json(authority_path)
        if cutoff > _parse_aware_timestamp(completed_at, "completed_at") or _sha256(pointer_path) != evidence["pointer_sha256"] or pointer.get("candidate") != str(candidate_path) or pointer.get("sha256") != evidence["candidate_sha256"] or _sha256(projection_path) != evidence["projection_sha256"] or projection.get("market_data_attempt_id") != attempt_id or candidate_path.suffix != ".parquet" or _sha256(candidate_path) != evidence["candidate_sha256"] or _sha256(authority_path) != evidence["vci_authority_receipt_sha256"] or not verify_market_data_receipt(authority):
            return False
        candidate = pd.read_parquet(candidate_path)
        valid, _ = validate_dataframe(candidate, "published_candidate")
        authority_evidence = authority.get("gate_evidence", {})
        if not valid or authority.get("terminal_session") != evidence["terminal_session"] or authority_evidence.get("candidate_sha256") != evidence["candidate_sha256"] or authority_evidence.get("cutoff_at") != evidence["cutoff_at"]:
            return False
        return True
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        return False


def _gate_evidence_from_result(result: Dict, attempt_id: str, projection_path: Path, projection_sha256: Optional[str]) -> Optional[Dict]:
    report, authority = result.get("gate_report"), result.get("vci_authority")
    if not isinstance(report, dict) or not isinstance(authority, dict) or not projection_sha256 or not all(isinstance(result.get(key), str) and result[key] for key in ("candidate_path", "pointer_path", "sha256", "vci_authority_receipt_path")) or not isinstance(report.get("terminal_session"), str) or not isinstance(report.get("gates"), dict) or not report["gates"] or not all(value is True for value in report["gates"].values()):
        return None
    try:
        return {"schema_version": VCI_AUTHORITY_RECEIPT_SCHEMA_VERSION, "terminal_session": report["terminal_session"], "cutoff_at": authority["cutoff_at"], "candidate_path": result["candidate_path"], "candidate_sha256": result["sha256"], "pointer_path": result["pointer_path"], "pointer_sha256": _sha256(Path(result["pointer_path"])), "projection_path": str(projection_path), "projection_sha256": projection_sha256, "projection_attempt_id": attempt_id, "release_gate_passed": True, "vci_authority_receipt_path": result["vci_authority_receipt_path"], "vci_authority_receipt_sha256": _sha256(Path(result["vci_authority_receipt_path"]))}
    except (KeyError, OSError, ValueError, TypeError):
        return None


def validate_release_gates(
    combined: pd.DataFrame,
    fetch_stats: Dict,
    requested_symbols: List[str],
    requested_end: pd.Timestamp,
    canonical_max: Optional[pd.Timestamp],
    cutoff_at: Optional[datetime] = None,
    full_refetch_stats: Optional[Dict] = None,
    terminal_candidate: Optional[pd.DataFrame] = None,
    canonical_terminals: Optional[Dict[str, pd.Timestamp]] = None,
    sparse_terminal_evidence: Optional[Dict[str, Dict]] = None,
    lifecycle_receipt_ledger_dir: Optional[Path] = None,
    claim_receipts: bool = True,
    bypass_lifecycle: bool = False,
) -> Tuple[bool, List[str], Dict]:
    """Enforce publication gates without mutating candidate or production."""
    errors: List[str] = []
    rejected_rows = int(len(combined) - len(combined.drop_duplicates(["ticker", "date"]))) if not combined.empty else 0
    if rejected_rows:
        errors.append(f"duplicates: rejected {rejected_rows} duplicate (ticker, date) rows before publication")
    if fetch_stats.get("errors", 0) != 0 or fetch_stats.get("errors_list"):
        errors.append(f"source errors: {fetch_stats.get('errors_list', [])}")
    errors.extend(_validate_phase_coverage(
        combined, requested_symbols, fetch_stats, full_refetch_stats,
    ))
    cutoff_at = cutoff_at or datetime.now(timezone.utc)
    authority_ok, authority_errors, authority = _vci_terminal_evidence(
        terminal_candidate if terminal_candidate is not None else combined,
        requested_symbols, requested_end, canonical_max, cutoff_at, canonical_terminals,
        sparse_terminal_evidence,
        lifecycle_receipt_ledger_dir,
        claim_receipts=False,
        bypass_lifecycle=bypass_lifecycle,
    )
    errors.extend(authority_errors)
    if not errors and claim_receipts:
        errors.extend(_claim_sparse_terminal_receipts(
            authority, sparse_terminal_evidence, lifecycle_receipt_ledger_dir,
        ))
    report = {
        "requested_symbols": len(requested_symbols),
        "observed_symbols": int(combined["ticker"].nunique()) if not combined.empty else 0,
        "terminal_session": authority["terminal_session"],
        "rejected_rows": rejected_rows,
        "source_errors": int(fetch_stats.get("errors", 0)),
        "gates": {"source_errors": not bool(fetch_stats.get("errors", 0) or fetch_stats.get("errors_list")), "terminal_coverage": authority_ok, "duplicates": rejected_rows == 0},
    }
    return not errors, errors, report | {"vci_authority": authority}


def publish_candidate(
    candidate: pd.DataFrame,
    canonical_path: Path,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    pointer_path: Path = DEFAULT_POINTER_PATH,
    manifest: Optional[Dict] = None,
    vci_authority: Optional[Dict] = None,
    sparse_terminal_evidence: Optional[Dict[str, Dict]] = None,
    lifecycle_receipt_ledger_dir: Optional[Path] = None,
    expected_generation: Optional[int] = None,
    expected_pointer_sha256: Optional[str] = None,
) -> Dict:
    """Write run-ID candidate, manifest, then atomically swap read-only pointer."""
    release_root.mkdir(parents=True, exist_ok=True)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = pointer_path.with_suffix(pointer_path.suffix + ".lock")
    lock_lease = _acquire_publication_lock(lock_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = release_root / run_id
    run_dir.mkdir()
    candidate_path = run_dir / canonical_path.name
    manifest_path = run_dir / "manifest.json"
    prior_pointer = pointer_path.read_bytes() if pointer_path.exists() else None
    claimed_lifecycle_receipt_ids: Set[str] = set()
    try:
        atomic_write_with_backup(candidate, candidate_path, backup=False)
        # Test doubles may only assert the call; production always has the file.
        if not candidate_path.exists():
            candidate.to_parquet(candidate_path, index=False)
        payload = dict(manifest or {})
        prior = json.loads(pointer_path.read_text(encoding="utf-8")) if pointer_path.exists() else {}
        prior_generation = int(prior.get("generation", 0))
        prior_hash = _sha256(pointer_path) if pointer_path.exists() else None
        if expected_generation is not None and prior_generation != expected_generation:
            raise RuntimeError("stale publication generation")
        if expected_pointer_sha256 is not None and prior_hash != expected_pointer_sha256:
            raise RuntimeError("stale publication pointer")
        if not isinstance(vci_authority, dict) or vci_authority.get("validation_outcome") != "passed":
            raise RuntimeError("VCI authority evidence unavailable")
        candidate_sha256 = _sha256(candidate_path)
        active_id, keyring = _trusted_keyring()
        authority = {
            "schema_version": MARKET_DATA_ATTEMPT_SCHEMA_VERSION,
            "attempt_id": run_id,
            "state": "terminal",
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "published": True,
            "stale": False,
            "terminal_session": vci_authority["terminal_session"],
            "execution_allowed": True,
            "reason": "vci_authority_v2",
            "publication": {"run_id": run_id, "candidate_path": str(candidate_path), "pointer_path": str(pointer_path), "sha256": candidate_sha256},
            "projection_path": "",
            "projection_sha256": "",
            "projection_attempt_id": run_id,
            "provenance": vci_authority,
            "gate_evidence": {"candidate_sha256": candidate_sha256, "terminal_session": vci_authority["terminal_session"], "cutoff_at": vci_authority["cutoff_at"], "validation_outcome": "passed", "release_gate_evidence": payload.get("gate_report", {})},
        }
        authority = _sign_receipt(authority, active_id, keyring[active_id])
        authority_path = run_dir / "vci_authority_receipt.v2.json"
        _write_immutable_json(authority_path, authority)
        if not verify_market_data_receipt(authority):
            raise RuntimeError("VCI authority receipt signature invalid")
        payload.update({"run_id": run_id, "candidate": str(candidate_path), "sha256": candidate_sha256, "canonical_sha256": _sha256(canonical_path) if canonical_path.exists() else None, "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pit_publication_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "canonical_path": str(canonical_path), "release_class": payload.get("release_class", "release"), "state": "published", "generation": prior_generation + 1, "vci_authority_receipt_path": str(authority_path), "vci_authority_receipt_sha256": _sha256(authority_path)})
        _write_fsync(manifest_path, json.dumps(payload, indent=2, default=str).encode())
        _write_fsync(run_dir / "pit_manifest.json", json.dumps({"run_id": run_id, "published_at": payload["published_at"], "terminal_session": vci_authority["terminal_session"]}, indent=2).encode())
        pointer = {"run_id": run_id, "candidate": str(candidate_path), "manifest": str(manifest_path), "sha256": payload["sha256"], "generation": payload["generation"]}
        fd, tmp_name = tempfile.mkstemp(prefix="market_current.", suffix=".tmp", dir=str(pointer_path.parent))
        os.close(fd)
        tmp_pointer = Path(tmp_name)
        tmp_pointer.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
        with tmp_pointer.open("rb+") as stream:
            os.fsync(stream.fileno())
        receipt_errors = _claim_sparse_terminal_receipts(
            vci_authority, sparse_terminal_evidence, lifecycle_receipt_ledger_dir,
            claimed_lifecycle_receipt_ids,
        )
        if receipt_errors:
            raise RuntimeError("; ".join(receipt_errors))
        tmp_pointer.replace(pointer_path)
        _fsync_directory(pointer_path.parent)
        try:
            prune_releases(release_root, pointer_path)
        except Exception:
            logger.exception("Post-commit release pruning failed")
            if os.name == "nt":
                _write_quarantine(run_dir / "quarantine.json", json.dumps({"state": "quarantined", "reason": "post-pointer release pruning failed", "run_id": run_id}, indent=2).encode())
                raise
        return {"run_id": run_id, "candidate_path": str(candidate_path), "manifest_path": str(manifest_path), "pointer_path": str(pointer_path), "sha256": payload["sha256"], "vci_authority_receipt_path": str(authority_path)}
    except Exception as exc:
        rollback_errors = []
        try:
            _restore_publication_pointer(pointer_path, prior_pointer)
        except Exception as rollback_exc:
            rollback_errors.append(rollback_exc)
        if claimed_lifecycle_receipt_ids:
            try:
                _release_lifecycle_receipt_claims(
                    vci_authority, sparse_terminal_evidence, lifecycle_receipt_ledger_dir,
                    claimed_lifecycle_receipt_ids,
                )
            except Exception as rollback_exc:
                rollback_errors.append(rollback_exc)
        _write_quarantine(run_dir / "quarantine.json", json.dumps({"state": "quarantined", "reason": str(exc), "run_id": run_id}, indent=2).encode())
        logger.exception("Candidate quarantined: %s", run_dir)
        if rollback_errors:
            raise ExceptionGroup("publication failed and rollback failed", [exc, *rollback_errors])
        raise
    finally:
        _release_publication_lock(lock_path, lock_lease)


def prune_releases(release_root: Path = DEFAULT_RELEASE_ROOT, pointer_path: Path = DEFAULT_POINTER_PATH) -> None:
    """Apply release, checkpoint, failed, and PIT-manifest retention classes."""
    releases = sorted((p for p in release_root.iterdir() if p.is_dir()), reverse=True) if release_root.exists() else []
    active = None
    pointer = pointer_path
    if pointer.exists():
        try:
            active = json.loads(pointer.read_text(encoding="utf-8")).get("run_id")
        except (OSError, json.JSONDecodeError):
            pass
    now = datetime.now()
    normal = []
    checkpoints: Dict[str, List[Path]] = {}
    for release in releases:
        try:
            metadata = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if (release / "quarantine.json").exists() or metadata.get("state") in {"failed", "quarantined"}:
            if now - datetime.fromtimestamp(release.stat().st_mtime) > timedelta(days=FAILED_RETENTION_DAYS) and release.name != active:
                shutil.rmtree(release)
        elif metadata.get("release_class") == "checkpoint":
            checkpoint_run = str(metadata.get("checkpoint_run_id", "default"))
            checkpoints.setdefault(checkpoint_run, []).append(release)
            if now - datetime.fromtimestamp(release.stat().st_mtime) > timedelta(days=CHECKPOINT_RETENTION_DAYS) and release.name != active:
                shutil.rmtree(release)
        elif (release / "pit_manifest.json").exists():
            if now - datetime.fromtimestamp((release / "pit_manifest.json").stat().st_mtime) > timedelta(days=PIT_MANIFEST_RETENTION_DAYS) and release.name != active:
                shutil.rmtree(release)
            else:
                continue
        else:
            normal.append(release)
    for checkpoint_releases in checkpoints.values():
        live = [p for p in checkpoint_releases if p.exists()]
        for release in live[CHECKPOINT_RETENTION:]:
            if release.name != active:
                shutil.rmtree(release)
    for release in normal[RELEASE_RETENTION:]:
        if release.name != active:
            shutil.rmtree(release)


def read_published_candidate(pointer_path: Path) -> pd.DataFrame:
    """Read pointer and candidate from private in-memory copies."""
    pointer_bytes = pointer_path.read_bytes()
    pointer = json.loads(pointer_bytes)
    candidate = Path(pointer["candidate"])
    expected_hash = str(pointer["sha256"])
    candidate_bytes = candidate.read_bytes() if candidate.is_file() else None
    if candidate_bytes is None or hashlib.sha256(candidate_bytes).hexdigest() != expected_hash:
        raise RuntimeError("published candidate hash mismatch")
    return pd.read_parquet(io.BytesIO(candidate_bytes))


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
    bypass_lifecycle: bool = False,
    expected_generation: Optional[int] = None,
    expected_pointer_sha256: Optional[str] = None,
    reconciliation_state_path: Path = MARKET_DATA_RECONCILIATION_STATE,
    reconciliation_latest_path: Path = MARKET_DATA_RECONCILIATION_LATEST,
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
        bypass_lifecycle: If True, allow writes despite unresolved lifecycle evidence.

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

    requested_symbols = sorted(symbol_filter or set(all_symbols))
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

    unresolved_lifecycle_symbols = (
        fetch_stats.get("empty_tickers", []) +
        [failure["symbol"] for failure in fetch_stats.get("errors_list", [])]
    )
    if unresolved_lifecycle_symbols and not bypass_lifecycle:
        logger.error(
            "BLOCKED: unresolved sparse/lifecycle exceptions require independently "
            "signed or checkpointed official exchange evidence; no write will be performed."
        )
        return {
            "status": "lifecycle_evidence_required",
            "unresolved_lifecycle_symbols": sorted(set(unresolved_lifecycle_symbols)),
            "fetch_stats": fetch_stats,
        }
    if unresolved_lifecycle_symbols:
        logger.warning(
            "BYPASS: proceeding despite unresolved lifecycle evidence for symbols: %s",
            sorted(set(unresolved_lifecycle_symbols)),
        )

    if new_data.empty:
        logger.warning("No new data fetched. Nothing to update.")
        return {"status": "no_new_data", "fetch_stats": fetch_stats}

    # 4a. Anomaly detection: compare new data boundary against canonical
    refetch_stats: Dict = {}
    full_refetch_stats: Dict = {}
    full_history_symbols: Set[str] = set()
    terminal_candidate = new_data
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
            # The incremental batch is the terminal-session authority. Full-history
            # recovery replaces history but must not advance a ticker's session.
            terminal_candidate = new_data.copy()
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

    # 4. Normalize candidate PIT metadata before any overlap comparison or validation.
    new_data = _normalize_legacy_vci_available_at(new_data)
    terminal_candidate = _normalize_legacy_vci_available_at(terminal_candidate)
    new_valid, new_errors = validate_dataframe(new_data, "new_data")
    if not new_valid:
        logger.error("New data validation FAILED:")
        for err in new_errors:
            logger.error(f"  - {err}")
        return {"status": "dry_run" if dry_run else "validation_failed", "errors": new_errors, "dry_run": dry_run, "rejected_rows": int(len(new_data))}

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
            combined, overlap_errors = merge_canonical_and_new(existing, new_data)
            if overlap_errors:
                return {
                    "status": "dry_run" if dry_run else "validation_failed",
                    "errors": overlap_errors,
                    "dry_run": dry_run,
                    "rejected_rows": int(len(combined)),
                }
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
        return {"status": "dry_run" if dry_run else "validation_failed", "errors": combined_errors, "dry_run": dry_run, "rejected_rows": int(len(combined))}

    canonical_max = read_canonical_max_date(canonical_path) if canonical_path.exists() else None
    canonical_terminals = _canonical_terminal_by_ticker(canonical_path)
    sparse_terminal_evidence = _load_ticker_lifecycle() if not skip_refetch else {}
    gates_ok, gate_errors, gate_report = validate_release_gates(
        combined, fetch_stats, requested_symbols, end_ts, canonical_max,
        full_refetch_stats=full_refetch_stats, terminal_candidate=terminal_candidate,
        canonical_terminals=canonical_terminals,
        sparse_terminal_evidence=sparse_terminal_evidence,
        claim_receipts=False,
        bypass_lifecycle=bypass_lifecycle,
    )
    if not gates_ok:
        return {"status": "gates_failed", "errors": gate_errors, "gate_report": gate_report, "rejected_rows": gate_report["rejected_rows"]}

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
        "gate_report": {key: value for key, value in gate_report.items() if key != "vci_authority"},
        "vci_authority": gate_report["vci_authority"],
    }
    try:
        summary["market_data_reconciliation"] = _run_reconciliation(
            combined, requested_symbols, exchange_map, end_str,
            reconciliation_state_path, reconciliation_latest_path,
        )
    except Exception as exc:
        logger.warning("KBS reconciliation boundary failed: %s", exc)
        summary["market_data_reconciliation"] = {"status": "warning", "reason": "reconciliation_failed"}

    if dry_run:
        logger.info("DRY-RUN: lifecycle receipts and market data writes bypassed.")
        logger.info(f"  New rows: {len(new_data)}")
        logger.info(f"  Combined rows: {len(combined)}")
        logger.info(f"  Combined tickers: {combined['ticker'].nunique()}")
        logger.info(f"  Date range: {combined['date'].min()} to {combined['date'].max()}")
        logger.info(f"  Exchange split: {combined['exchange'].value_counts().to_dict()}")
        summary["exchange_split"] = combined["exchange"].value_counts().to_dict()
        return summary

    # 8. Stage and publish only after every gate passes. Production parquet is read-only.
    publication = publish_candidate(
        combined,
        canonical_path,
        release_root=canonical_path.parent / "market_releases",
        pointer_path=canonical_path.parent / "market_current.json",
        manifest={"gate_report": summary["gate_report"], "fetch_stats": fetch_stats, "rejected_rows": gate_report["rejected_rows"]},
        vci_authority=summary["vci_authority"],
        sparse_terminal_evidence=sparse_terminal_evidence,
        expected_generation=expected_generation,
        expected_pointer_sha256=expected_pointer_sha256,
    )
    summary.update(publication)
    summary["status"] = "published"
    summary["output_path"] = publication["candidate_path"]

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
    parser.add_argument(
        "--bypass-lifecycle", action="store_true",
        help="Bypass independent lifecycle evidence requirement",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    canonical_path = Path(args.canonical) if args.canonical else DEFAULT_CANONICAL_PATH
    output_path = Path(args.output) if args.output else None
    symbol_filter = set(s.upper() for s in args.symbols) if args.symbols else None

    if args.dry_run:
        try:
            result = run_updater(
                canonical_path=canonical_path, output_path=output_path, start_date=args.start, end_date=args.end,
                dry_run=True, symbol_filter=symbol_filter, skip_refetch=args.no_refetch,
                bypass_lifecycle=args.bypass_lifecycle,
            )
        except Exception as exc:
            logger.exception("Updater dry-run crashed")
            return 1
        return 0 if result.get("status") == "dry_run" else 1

    try:
        attempt = start_market_data_attempt()
    except RuntimeError:
        logger.error("Market receipt signing configuration unavailable")
        return 1
    try:
        result = run_updater(
            canonical_path=canonical_path,
            output_path=output_path,
            start_date=args.start,
            end_date=args.end,
            dry_run=args.dry_run,
            symbol_filter=symbol_filter,
            skip_refetch=args.no_refetch,
            bypass_lifecycle=args.bypass_lifecycle,
        )
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}
        logger.exception("Updater crashed")

    # Save result summary
    summary_path = MARKET_DATA_PROJECTION
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    projection_error = None
    try:
        result["market_data_attempt_id"] = attempt["attempt_id"]
        _write_fsync(summary_path, _canonical_json(result))
        if _load_strict_json(summary_path) != result:
            raise RuntimeError("dashboard projection verification failed")
        logger.info(f"Result summary saved to {summary_path}")
    except Exception as exc:
        projection_error = str(exc)
        logger.exception("Dashboard projection failed")
    try:
        terminal = finish_market_data_attempt(attempt, result, projection_error, projection_path=summary_path)
        result["attempt_receipt"] = str(terminal["path"])
    except Exception:
        logger.exception("Failed to append terminal market-data receipt")
        return 1

    if projection_error or result.get("status") not in ("dry_run", "published"):
        logger.error(f"Pipeline FAILED: {result.get('status')}")
        return 1

    logger.info(f"Pipeline {result.get('status', 'complete').upper()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
