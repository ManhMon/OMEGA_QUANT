"""
OMEGA_QUANT Exchange Resolver
=============================
Centralized exchange mapping and UNKNOWN exclusion for promoted candidate datasets.

Resolves authoritative exchange assignments from:
1. Session exchange map (exchange_map_20260612.json)
2. VCI Listing API (when available)
3. Hardcoded fallback map in structure_features

UNKNOWN exchange rows are explicitly excluded from canonical promotion and
exchange-aware consumers.  The module writes a manifest documenting
included/excluded counts per exchange.

Author: Data Engineer (Role 15)
Date: 2026-06-12
Gate: HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Authoritative valid exchanges for Vietnam market
VALID_EXCHANGES: Set[str] = {"HOSE", "HNX", "UPCOM"}

# Hardcoded fallback for the most liquid names (VN30 + HNX blue chips)
# This is the MINIMUM set; production should use the session exchange map.
_FALLBACK_EXCHANGE_MAP: Dict[str, str] = {
    # HOSE - VN30
    "VNM": "HOSE", "VIC": "HOSE", "VHM": "HOSE", "VCB": "HOSE",
    "BID": "HOSE", "CTG": "HOSE", "TCB": "HOSE", "MBB": "HOSE",
    "HPG": "HOSE", "MSN": "HOSE", "VRE": "HOSE", "GAS": "HOSE",
    "SAB": "HOSE", "MWG": "HOSE", "FPT": "HOSE", "VJC": "HOSE",
    "SSI": "HOSE", "HDB": "HOSE", "ACB": "HOSE", "STB": "HOSE",
    "VPB": "HOSE", "VIB": "HOSE", "TPB": "HOSE", "MSN": "HOSE",
    # HNX blue chips
    "PVS": "HNX", "SHB": "HNX", "PVX": "HNX", "CEO": "HNX",
}


def load_exchange_map(map_path: Optional[str] = None) -> Dict[str, str]:
    """
    Load the ticker-to-exchange mapping from a JSON file.

    Args:
        map_path: Path to exchange map JSON. If None, searches standard locations.

    Returns:
        Dict mapping ticker symbol to exchange code.
    """
    if map_path is None:
        candidates = [
            Path(".ly_state/session/exchange_map_20260612.json"),
            Path(".ly_state/session/exchange_map.json"),
        ]
        for c in candidates:
            if c.exists():
                map_path = str(c)
                break

    if map_path and Path(map_path).exists():
        with open(map_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        logger.info(f"Loaded exchange map from {map_path}: {len(raw)} entries")
        return raw

    logger.warning("No exchange map file found; using hardcoded fallback only")
    return _FALLBACK_EXCHANGE_MAP.copy()


def resolve_exchange(
    ticker: str,
    exchange_map: Optional[Dict[str, str]] = None,
) -> str:
    """
    Resolve the exchange for a single ticker.

    Returns:
        Exchange code ('HOSE', 'HNX', 'UPCOM') or 'UNKNOWN'.
    """
    if exchange_map is None:
        exchange_map = load_exchange_map()

    exchange = exchange_map.get(ticker, "UNKNOWN")

    # Validate: only accept known valid exchanges
    if exchange not in VALID_EXCHANGES:
        return "UNKNOWN"

    return exchange


def assign_exchange_column(
    df: pd.DataFrame,
    exchange_map: Optional[Dict[str, str]] = None,
    ticker_col: str = "ticker",
) -> pd.DataFrame:
    """
    Add or overwrite the 'exchange' column on a DataFrame.

    Args:
        df: Input DataFrame with a ticker column.
        exchange_map: Optional pre-loaded map.
        ticker_col: Name of the ticker column.

    Returns:
        DataFrame with 'exchange' column assigned.
    """
    if exchange_map is None:
        exchange_map = load_exchange_map()

    df = df.copy()
    df["exchange"] = df[ticker_col].map(
        lambda t: resolve_exchange(t, exchange_map)
    )
    return df


def build_promoted_candidate(
    df: pd.DataFrame,
    exchange_map: Optional[Dict[str, str]] = None,
    ticker_col: str = "ticker",
    exclude_unknown: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Build a promoted candidate dataset with exchange assignment.

    UNKNOWN exchange rows are excluded by default (safe approach).
    A manifest dict is returned with included/excluded counts.

    Args:
        df: Input rebuilt dataset.
        exchange_map: Optional pre-loaded exchange map.
        ticker_col: Ticker column name.
        exclude_unknown: If True, drop UNKNOWN rows. If False, flag them.

    Returns:
        (promoted_df, manifest_dict)
    """
    if exchange_map is None:
        exchange_map = load_exchange_map()

    df_work = assign_exchange_column(df, exchange_map, ticker_col)

    # Per-ticker exchange resolution stats
    unique_tickers = df_work[ticker_col].nunique()
    exchange_counts = (
        df_work.groupby("exchange")[ticker_col].nunique().to_dict()
    )
    row_counts = df_work.groupby("exchange").size().to_dict()

    unknown_tickers: List[str] = []
    if "UNKNOWN" in exchange_counts:
        unknown_tickers = sorted(
            df_work[df_work["exchange"] == "UNKNOWN"][ticker_col].unique().tolist()
        )

    if exclude_unknown:
        promoted = df_work[df_work["exchange"] != "UNKNOWN"].copy()
    else:
        promoted = df_work.copy()
        # Flag UNKNOWN rows with exchange_flag column
        promoted["exchange_flag"] = promoted["exchange"].apply(
            lambda e: "EXCLUDED_UNKNOWN" if e == "UNKNOWN" else "OK"
        )

    promoted_tickers = promoted[ticker_col].nunique()
    promoted_rows = len(promoted)

    # Zero-volume stats (important for ADV/capacity)
    if "volume" in promoted.columns:
        zero_vol_rows = int((promoted["volume"] == 0).sum())
        total_zero_vol_tickers = int(
            promoted.groupby(ticker_col)["volume"]
            .apply(lambda x: (x == 0).all())
            .sum()
        )
    else:
        zero_vol_rows = 0
        total_zero_vol_tickers = 0

    manifest = {
        "total_input_tickers": int(unique_tickers),
        "total_input_rows": int(len(df_work)),
        "promoted_tickers": int(promoted_tickers),
        "promoted_rows": int(promoted_rows),
        "excluded_unknown_tickers": int(len(unknown_tickers)),
        "excluded_unknown_rows": int(
            row_counts.get("UNKNOWN", 0)
        ),
        "exchange_ticker_counts": {
            k: int(v) for k, v in exchange_counts.items()
        },
        "exchange_row_counts": {
            k: int(v) for k, v in row_counts.items()
        },
        "zero_volume_rows_in_promoted": zero_vol_rows,
        "fully_inactive_tickers_in_promoted": total_zero_vol_tickers,
        "unknown_ticker_list": unknown_tickers[:50],  # First 50 for readability
        "exclude_unknown": exclude_unknown,
    }

    logger.info(
        f"Promoted candidate: {promoted_rows} rows, {promoted_tickers} tickers. "
        f"Excluded {manifest['excluded_unknown_tickers']} UNKNOWN tickers "
        f"({manifest['excluded_unknown_rows']} rows)."
    )

    return promoted, manifest


def write_promoted_manifest(
    manifest: Dict[str, Any],
    output_path: str,
) -> None:
    """Write promoted candidate manifest to JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info(f"Promoted manifest written to {path}")
