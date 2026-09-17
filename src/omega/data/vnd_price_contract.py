"""
OMEGA_QUANT VND_FULL Price-Unit Contract
==========================================
Centralized price-scale guard ensuring all data at ingestion write boundaries
uses the VND_FULL contract (prices in whole VND, e.g. 50000.0 for 50,000 VND).

VCI 4.x returns prices in THOUSANDS (e.g. 50.0 for 50,000 VND).
This module provides ``ensure_vnd_scale()`` to normalize at write time.

Usage at every ingestion write boundary::

    from omega.data.vnd_price_contract import ensure_vnd_scale, VND_FULL

    df = ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])
    # df is now in VND_FULL; metadata records price_unit = VND_FULL

Author: Data Engineer (Role 15)
Date: 2026-06-12
Gate: HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Price-Unit Contract Constants ────────────────────────────────────────────

#: Canonical price unit for the entire OMEGA_QUANT pipeline.
#: Prices are stored as whole Vietnamese Dong (e.g. 50000.0 = 50,000 VND).
VND_FULL: str = "VND_FULL"

#: Legacy price unit (VCI 4.x raw). Prices in thousands (e.g. 50.0 = 50,000 VND).
THOUSANDS: str = "THOUSANDS"

#: Heuristic threshold: if median close is below this, prices are in THOUSANDS.
RAW_PRICE_THRESHOLD: float = 1_000.0

#: Multiplier to convert THOUSANDS -> VND_FULL.
VND_PRICE_SCALE: float = 1_000.0

#: Default price columns for OHLC data.
DEFAULT_PRICE_COLS: List[str] = ["open", "high", "low", "close"]


# ── Scale Guard ──────────────────────────────────────────────────────────────

def detect_price_unit(df: pd.DataFrame, price_col: str = "close") -> str:
    """
    Detect whether prices in *df* are VND_FULL or THOUSANDS.

    Uses the median of the reference column. If median < RAW_PRICE_THRESHOLD
    and > 0, prices are assumed THOUSANDS.

    Returns:
        VND_FULL or THOUSANDS
    """
    if price_col not in df.columns:
        logger.warning(f"Price column '{price_col}' not found; assuming VND_FULL")
        return VND_FULL

    vals = pd.to_numeric(df[price_col], errors="coerce")
    vals = vals.replace([float("inf"), float("-inf")], float("nan")).dropna()
    if vals.empty:
        return VND_FULL

    median_price = float(vals.median())
    if 0 < median_price < RAW_PRICE_THRESHOLD:
        return THOUSANDS
    return VND_FULL


def ensure_vnd_scale(
    df: pd.DataFrame,
    price_cols: Optional[List[str]] = None,
    ref_col: str = "close",
    *,
    inplace: bool = False,
) -> pd.DataFrame:
    """
    Normalize price columns to VND_FULL if they are currently in THOUSANDS.

    This is the **single** authoritative guard that MUST be called at every
    ingestion write boundary (vnstock_adapter, vnstock_live, vnstock_vci,
    vnstock_ingest, update_market_data, batch loader).

    Args:
        df: Input DataFrame.
        price_cols: Columns to normalize. Default: OHLC.
        ref_col: Reference column for detection heuristic.
        inplace: Modify df in place (default False, returns copy).

    Returns:
        DataFrame with prices in VND_FULL.
    """
    if price_cols is None:
        price_cols = [c for c in DEFAULT_PRICE_COLS if c in df.columns]
    else:
        price_cols = [c for c in price_cols if c in df.columns]

    if not price_cols:
        return df

    target = df if inplace else df.copy()

    unit = detect_price_unit(target, ref_col if ref_col in target.columns else price_cols[0])

    if unit == THOUSANDS:
        for col in price_cols:
            target[col] = pd.to_numeric(target[col], errors="coerce") * VND_PRICE_SCALE
        logger.info(
            f"ensure_vnd_scale: converted {len(price_cols)} price columns "
            f"from THOUSANDS to VND_FULL (×{VND_PRICE_SCALE:.0f})"
        )
    else:
        logger.debug("ensure_vnd_scale: prices already VND_FULL, no conversion needed")

    return target


def price_scale_metadata() -> Dict[str, Any]:
    """
    Return a metadata dict describing the canonical price-unit contract.

    Suitable for embedding in manifests and session JSON artifacts.
    """
    return {
        "canonical_price_unit": VND_FULL,
        "raw_source_price_unit": THOUSANDS,
        "vnd_price_scale_factor": VND_PRICE_SCALE,
        "raw_price_threshold": RAW_PRICE_THRESHOLD,
        "description": (
            "All prices in OMEGA_QUANT pipeline are stored as VND_FULL "
            "(whole Vietnamese Dong). VCI 4.x returns prices in THOUSANDS "
            "and must be multiplied by 1000 at ingestion write boundaries."
        ),
    }


def get_price_multiplier(price_unit: str) -> float:
    """
    Return the multiplier to convert from *price_unit* to VND_FULL.

    - VND_FULL -> 1.0  (no conversion)
    - THOUSANDS -> 1000.0

    This is used by execution/PnL consumers that previously hardcoded *1000.
    """
    if price_unit == VND_FULL:
        return 1.0
    if price_unit == THOUSANDS:
        return VND_PRICE_SCALE
    raise ValueError(f"Unknown price_unit: {price_unit!r}. Expected VND_FULL or THOUSANDS.")
