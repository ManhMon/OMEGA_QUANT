"""Nonredundant Alpha Family Set v1 — PIT-safe, trailing-window alpha candidates.

GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
Version: 1.2.0
Date: 2026-06-15

Research-only, opt-in module providing nonredundant alpha families designed
to complement existing Phase 3.4 microstructure alphas and formulaic alphas.

Alpha Sets:
  v1 (10 candidates from 5 families):
    Full set — all 5 families × 2 candidates each.

  v1_pruned (5 candidates — positive-evidence only):
    Pruned subset retaining only candidates with positive per-fold IC evidence.
    Excludes negative-IC candidates and neutral alpha_nr_liq_shock_zscore_20.

    Included (positive evidence):
      - alpha_nr_market_relative_momentum_20
      - alpha_nr_range_pressure_momentum_20
      - alpha_nr_liq_shock_reversal_10
      - alpha_nr_close_location_value_10
      - alpha_nr_vol_breakout_directional_10

    Excluded (negative evidence):
      - alpha_nr_advance_decline_signal_20
      - alpha_nr_residual_reversal_10
      - alpha_nr_breadth_conditioned_reversal_10
      - alpha_nr_vol_compression_20

    Excluded (neutral — not needed):
      - alpha_nr_liq_shock_zscore_20

  v1_mrm_only (1 candidate — focused overlay):
    GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    Single strongest positive-evidence candidate: market-relative momentum.
    Minimal overlay for isolated IC attribution.

    Included:
      - alpha_nr_market_relative_momentum_20

  v1_mrm_range (2 candidates — focused overlay):
    GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    Two strongest positive-evidence candidates: market-relative momentum
    plus range-pressure momentum. Tests additive IC from second candidate.

    Included:
      - alpha_nr_market_relative_momentum_20
      - alpha_nr_range_pressure_momentum_20

Alpha Families (v1):
  1. Liquidity Shock Reversal (2 candidates)
     - alpha_nr_liq_shock_zscore_20: volume z-score spike detection
     - alpha_nr_liq_shock_reversal_10: reversal after volume spike

  2. Range Pressure / Close-Location Value (2 candidates)
     - alpha_nr_close_location_value_10: close position within range
     - alpha_nr_range_pressure_momentum_20: range-expansion momentum

  3. Volatility Compression Breakout (2 candidates)
     - alpha_nr_vol_compression_20: Bollinger width compression
     - alpha_nr_vol_breakout_directional_10: directional breakout signal

  4. Sector/Market-Relative Residual Momentum/Reversal (2 candidates)
     - alpha_nr_residual_reversal_10: residual return reversal
     - alpha_nr_market_relative_momentum_20: market-relative momentum

  5. Breadth-Conditioned Reversal (2 candidates)
     - alpha_nr_breadth_conditioned_reversal_10: reversal × breadth interaction
     - alpha_nr_advance_decline_signal_20: advance-decline momentum

Total: 10 candidate alpha columns (v1), 5 candidates (v1_pruned),
       1 candidate (v1_mrm_only), 2 candidates (v1_mrm_range).

COMPLIANCE:
  - PIT Safe: All signals use T-1 lag per ticker (no lookahead)
  - No negative shifts anywhere in computation
  - Inf/NaN sanitised on output
  - Deterministic given same input
  - 100% vectorised (Pandas / NumPy)
  - All formulas use trailing windows only
  - Sector fallback: uses market-relative only if no sector map available
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger: logging.Logger = logging.getLogger(__name__)

# Gate identifier for traceability
GATE_ID = "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615"
# GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615
V1_PRUNED_GATE_ID = "NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615"
# GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
FOCUSED_OVERLAY_GATE_ID = "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615"

# ---------------------------------------------------------------------------
# Alpha set registry
# ---------------------------------------------------------------------------

NONREDUNDANT_ALPHA_SETS: Dict[str, Tuple[str, ...]] = {
    "v1": (
        "alpha_nr_liq_shock_zscore_20",
        "alpha_nr_liq_shock_reversal_10",
        "alpha_nr_close_location_value_10",
        "alpha_nr_range_pressure_momentum_20",
        "alpha_nr_vol_compression_20",
        "alpha_nr_vol_breakout_directional_10",
        "alpha_nr_residual_reversal_10",
        "alpha_nr_market_relative_momentum_20",
        "alpha_nr_breadth_conditioned_reversal_10",
        "alpha_nr_advance_decline_signal_20",
    ),
    # GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615
    # Positive-evidence-only subset of v1.
    # Excludes negative-IC candidates (advance_decline, residual_reversal,
    # breadth_conditioned_reversal, vol_compression) and neutral
    # liq_shock_zscore_20.
    "v1_pruned": (
        "alpha_nr_market_relative_momentum_20",
        "alpha_nr_range_pressure_momentum_20",
        "alpha_nr_liq_shock_reversal_10",
        "alpha_nr_close_location_value_10",
        "alpha_nr_vol_breakout_directional_10",
    ),
    # GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    # Focused overlay: single strongest positive-evidence candidate.
    # Minimal overlay for isolated IC attribution of market-relative momentum.
    "v1_mrm_only": (
        "alpha_nr_market_relative_momentum_20",
    ),
    # GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615
    # Focused overlay: two strongest positive-evidence candidates.
    # Tests additive IC from range-pressure momentum on top of MRM.
    "v1_mrm_range": (
        "alpha_nr_market_relative_momentum_20",
        "alpha_nr_range_pressure_momentum_20",
    ),
}

DEFAULT_NONREDUNDANT_ALPHA_SET = "v1"


def get_nonredundant_alpha_columns(set_name: str = "v1") -> Tuple[str, ...]:
    """Return tuple of alpha column names for a given set.

    Parameters
    ----------
    set_name : str
        Alpha set name. 'v1' (10 candidates), 'v1_pruned' (5 candidates),
        'v1_mrm_only' (1 candidate), or 'v1_mrm_range' (2 candidates).

    Returns
    -------
    tuple of str
        Alpha column names.

    Raises
    ------
    ValueError
        If set_name not in NONREDUNDANT_ALPHA_SETS.
    """
    if set_name not in NONREDUNDANT_ALPHA_SETS:
        valid = ", ".join(sorted(NONREDUNDANT_ALPHA_SETS.keys()))
        raise ValueError(
            f"Unknown nonredundant alpha set '{set_name}'. "
            f"Valid sets: [{valid}]"
        )
    return NONREDUNDANT_ALPHA_SETS[set_name]


# ---------------------------------------------------------------------------
# Vectorized helpers (PIT-safe)
# ---------------------------------------------------------------------------

def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    fill_value: float = 0.0,
) -> pd.Series:
    """Division with zero/NaN/Inf protection."""
    result = numerator / denominator
    result = result.replace([np.inf, -np.inf], np.nan).fillna(fill_value)
    return result.astype(np.float64)


def _grouped_rolling_mean(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    """Per-group trailing rolling mean (PIT-safe: no lookahead)."""
    mp = min_periods if min_periods is not None else max(3, window // 2)
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .mean()
        .reset_index(level=0, drop=True)
    )


def _grouped_rolling_std(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    """Per-group trailing rolling std (PIT-safe: no lookahead)."""
    mp = min_periods if min_periods is not None else max(3, window // 2)
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .std()
        .reset_index(level=0, drop=True)
    )


def _grouped_rolling_max(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    """Per-group trailing rolling max (PIT-safe: no lookahead)."""
    mp = min_periods if min_periods is not None else max(3, window // 2)
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .max()
        .reset_index(level=0, drop=True)
    )


def _grouped_rolling_min(
    series: pd.Series,
    groups: pd.Series,
    window: int,
    min_periods: Optional[int] = None,
) -> pd.Series:
    """Per-group trailing rolling min (PIT-safe: no lookahead)."""
    mp = min_periods if min_periods is not None else max(3, window // 2)
    return (
        series.groupby(groups)
        .rolling(window, min_periods=mp)
        .min()
        .reset_index(level=0, drop=True)
    )


def _sanitize_output(series: pd.Series) -> pd.Series:
    """Replace Inf/NaN and ensure float64."""
    return series.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float64)


# ---------------------------------------------------------------------------
# Family 1: Liquidity Shock Reversal
# ---------------------------------------------------------------------------

def _compute_liq_shock_zscore(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    volume_col: str,
    window: int = 20,
) -> pd.Series:
    """Compute trailing volume z-score (PIT-safe, T-1 lag).

    alpha_nr_liq_shock_zscore_20 = (volume_{T-1} - mean_vol_{T-20..T-1}) / std_vol_{T-20..T-1}

    Positive z-score = abnormally high volume (liquidity shock).
    """
    vol_lagged = df.groupby(symbol_col)[volume_col].shift(1)
    vol_mean = _grouped_rolling_mean(vol_lagged, groups, window)
    vol_std = _grouped_rolling_std(vol_lagged, groups, window)
    zscore = _safe_divide(vol_lagged - vol_mean, vol_std + 1e-9)
    return _sanitize_output(zscore)


def _compute_liq_shock_reversal(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    close_col: str,
    volume_col: str,
    window: int = 10,
) -> pd.Series:
    """Compute reversal signal after volume spike (PIT-safe, T-1 lag).

    alpha_nr_liq_shock_reversal_10 = -1 * sign(ret_{T-1}) * vol_zscore_{T-1}

    Hypothesis: abnormally high volume + positive return → subsequent reversal.
    """
    ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(groups).shift(1)
    vol_lagged = df.groupby(symbol_col)[volume_col].shift(1)
    vol_mean = _grouped_rolling_mean(vol_lagged, groups, window)
    vol_std = _grouped_rolling_std(vol_lagged, groups, window)
    vol_zscore = _safe_divide(vol_lagged - vol_mean, vol_std + 1e-9)
    sign_ret = np.sign(ret_lagged)
    signal = -1.0 * sign_ret * vol_zscore
    return _sanitize_output(signal)


# ---------------------------------------------------------------------------
# Family 2: Range Pressure / Close-Location Value
# ---------------------------------------------------------------------------

def _compute_close_location_value(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    high_col: str,
    low_col: str,
    close_col: str,
    window: int = 10,
) -> pd.Series:
    """Compute close-location value within trailing range (PIT-safe, T-1 lag).

    CLV = (close_{T-1} - min_low_{T-W..T-1}) / (max_high_{T-W..T-1} - min_low_{T-W..T-1})

    CLV near 1 = close near high (bullish pressure).
    CLV near 0 = close near low (bearish pressure).
    """
    close_lagged = df.groupby(symbol_col)[close_col].shift(1)
    high_lagged = df.groupby(symbol_col)[high_col].shift(1)
    low_lagged = df.groupby(symbol_col)[low_col].shift(1)

    max_high = _grouped_rolling_max(high_lagged, groups, window)
    min_low = _grouped_rolling_min(low_lagged, groups, window)

    range_val = max_high - min_low
    clv = _safe_divide(close_lagged - min_low, range_val + 1e-9)
    # Normalize to [-1, 1]
    signal = 2.0 * clv - 1.0
    return _sanitize_output(signal)


def _compute_range_pressure_momentum(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    high_col: str,
    low_col: str,
    window: int = 20,
) -> pd.Series:
    """Compute range expansion momentum (PIT-safe, T-1 lag).

    alpha_nr_range_pressure_momentum_20 = range_{T-1} / mean_range_{T-20..T-1} - 1

    Positive = expanding range (momentum), negative = compressing.
    """
    high_lagged = df.groupby(symbol_col)[high_col].shift(1)
    low_lagged = df.groupby(symbol_col)[low_col].shift(1)
    daily_range = high_lagged - low_lagged
    mean_range = _grouped_rolling_mean(daily_range, groups, window)
    signal = _safe_divide(daily_range, mean_range + 1e-9) - 1.0
    return _sanitize_output(signal)


# ---------------------------------------------------------------------------
# Family 3: Volatility Compression Breakout
# ---------------------------------------------------------------------------

def _compute_vol_compression(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    close_col: str,
    window: int = 20,
) -> pd.Series:
    """Compute Bollinger-band width compression (PIT-safe, T-1 lag).

    alpha_nr_vol_compression_20 = std_{T-20..T-1} / mean_{T-20..T-1}

    Low value = compression (potential breakout), high = expansion.
    Signal: negative = compression (bullish breakout potential).
    """
    close_lagged = df.groupby(symbol_col)[close_col].shift(1)
    roll_std = _grouped_rolling_std(close_lagged, groups, window)
    roll_mean = _grouped_rolling_mean(close_lagged, groups, window)
    bb_width = _safe_divide(roll_std, roll_mean.abs() + 1e-9)
    # Invert: low BB width (compression) → positive signal
    # Use z-score of BB width: negative z-score = compression
    bb_mean = _grouped_rolling_mean(bb_width, groups, window)
    bb_std = _grouped_rolling_std(bb_width, groups, window)
    signal = -1.0 * _safe_divide(bb_width - bb_mean, bb_std + 1e-9)
    return _sanitize_output(signal)


def _compute_vol_breakout_directional(
    df: pd.DataFrame,
    groups: pd.Series,
    symbol_col: str,
    close_col: str,
    window: int = 10,
) -> pd.Series:
    """Compute directional breakout from compression (PIT-safe, T-1 lag).

    alpha_nr_vol_breakout_directional_10 = (close_{T-1} - sma_{T-10}) / std_{T-10}

    Measures how far price has moved from trailing mean in std units.
    Large positive = upside breakout, large negative = downside breakout.
    """
    close_lagged = df.groupby(symbol_col)[close_col].shift(1)
    roll_mean = _grouped_rolling_mean(close_lagged, groups, window)
    roll_std = _grouped_rolling_std(close_lagged, groups, window)
    signal = _safe_divide(close_lagged - roll_mean, roll_std + 1e-9)
    return _sanitize_output(signal)


# ---------------------------------------------------------------------------
# Family 4: Sector/Market-Relative Residual Momentum/Reversal
# ---------------------------------------------------------------------------

def _compute_residual_reversal(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    date_col: str,
    window: int = 10,
    sector_map: Optional[Dict[str, str]] = None,
) -> pd.Series:
    """Compute residual return reversal (PIT-safe, T-1 lag).

    Residual = stock_return - market_return [- sector_return if available]
    Signal = -1 * trailing_mean(residual_{T-W..T-1})

    Hypothesis: stocks that underperformed their market/sector revert.
    Falls back to market-relative if no sector map.
    """
    groups = df[symbol_col]
    # T-1 lagged returns per ticker (per-group shift to avoid cross-ticker contamination)
    ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(groups).shift(1)

    # Market return per date (equal-weight mean of lagged returns)
    market_ret = ret_lagged.groupby(df[date_col]).transform('mean')

    residual = ret_lagged - market_ret

    # If sector map available, also subtract sector return
    if sector_map is not None and len(sector_map) > 0:
        # Map tickers to sectors
        sector_series = df[symbol_col].map(sector_map).fillna('UNKNOWN')
        # Per-date, per-sector mean return
        sector_ret = ret_lagged.groupby([df[date_col], sector_series]).transform('mean')
        residual = residual - sector_ret

    # Trailing mean of residual → reversal signal
    residual_mean = _grouped_rolling_mean(residual, groups, window)
    signal = -1.0 * residual_mean
    return _sanitize_output(signal)


def _compute_market_relative_momentum(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    date_col: str,
    window: int = 20,
) -> pd.Series:
    """Compute market-relative momentum (PIT-safe, T-1 lag).

    alpha_nr_market_relative_momentum_20 =
        cumret_stock_{T-20..T-1} - cumret_market_{T-20..T-1}

    Stocks outperforming the market → positive signal.
    """
    groups = df[symbol_col]
    ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(groups).shift(1)
    market_ret = ret_lagged.groupby(df[date_col]).transform('mean')

    # Cumulative trailing return
    stock_cumret = _grouped_rolling_mean(ret_lagged, groups, window) * window
    market_cumret = _grouped_rolling_mean(market_ret, groups, window) * window

    signal = stock_cumret - market_cumret
    return _sanitize_output(signal)


# ---------------------------------------------------------------------------
# Family 5: Breadth-Conditioned Reversal
# ---------------------------------------------------------------------------

def _compute_breadth_conditioned_reversal(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    date_col: str,
    window: int = 10,
) -> pd.Series:
    """Compute breadth-conditioned reversal (PIT-safe, T-1 lag).

    Short-term reversal scaled by market breadth deviation.
    When breadth is extreme (most stocks up/down), reversal is stronger.

    signal = -1 * ret_{T-1} * (breadth_{T-1} - 0.5) * 4

    breadth = fraction of stocks with positive return on date.
    """
    groups = df[symbol_col]
    ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(groups).shift(1)

    # Market breadth: fraction of stocks with positive return per date
    pos_ret = (ret_lagged > 0).astype(float)
    breadth = pos_ret.groupby(df[date_col]).transform('mean')

    # Breadth deviation from 0.5 (neutral), scaled
    breadth_dev = (breadth - 0.5) * 4.0

    # Reversal signal conditioned on breadth
    signal = -1.0 * ret_lagged * breadth_dev
    return _sanitize_output(signal)


def _compute_advance_decline_signal(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    date_col: str,
    window: int = 20,
) -> pd.Series:
    """Compute advance-decline momentum signal (PIT-safe, T-1 lag).

    A/D line = cumulative (advancers - decliners) / total stocks.
    Signal = trailing z-score of A/D line change.

    Positive A/D momentum = broad participation (bullish).
    """
    ret_lagged = df.groupby(symbol_col)[close_col].pct_change().groupby(df[symbol_col]).shift(1)

    # Per-date: advance-decline ratio
    advancers = (ret_lagged > 0).astype(float).groupby(df[date_col]).sum()
    decliners = (ret_lagged < 0).astype(float).groupby(df[date_col]).sum()
    total = ret_lagged.groupby(df[date_col]).count()
    ad_ratio = _safe_divide(advancers - decliners, total + 1e-9)

    # Cumulative A/D line (expanding sum)
    ad_cumulative = ad_ratio.sort_index().expanding().sum()

    # Change in A/D line over trailing window
    ad_change = ad_cumulative.diff(window)

    # Broadcast per-date A/D change to all stocks
    ad_change_broadcast = df[date_col].map(ad_change)

    # Z-score of A/D change
    ad_mean = ad_change.expanding(min_periods=max(5, window // 2)).mean()
    ad_std = ad_change.expanding(min_periods=max(5, window // 2)).std()
    ad_zscore = _safe_divide(ad_change - ad_mean, ad_std + 1e-9)

    signal = df[date_col].map(ad_zscore).fillna(0.0)
    return _sanitize_output(pd.Series(signal, index=df.index))


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------

def compute_nonredundant_alphas(
    df: pd.DataFrame,
    set_name: str = "v1",
    max_candidates: Optional[int] = None,
    symbol_col: str = "ticker",
    date_col: str = "date",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    sector_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Compute nonredundant alpha columns and append to DataFrame.

    GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615

    All alphas are PIT-safe:
    - Every feature uses T-1 lagged data per ticker
    - No forward-looking windows
    - Trailing statistics only
    - Deterministic given same input

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with required columns.
    set_name : str
        Alpha set name (default 'v1').
    max_candidates : int, optional
        Maximum number of alpha columns to compute. If None, compute all.
    symbol_col : str
        Column name for ticker symbol.
    date_col : str
        Column name for date.
    open_col, high_col, low_col, close_col, volume_col : str
        Column names for OHLCV data.
    sector_map : dict, optional
        Mapping of ticker -> sector string. If None, sector-relative
        alphas fall back to market-relative only.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with nonredundant alpha columns appended.

    Raises
    ------
    ValueError
        If set_name is not recognized.
    """
    if set_name not in NONREDUNDANT_ALPHA_SETS:
        valid = ", ".join(sorted(NONREDUNDANT_ALPHA_SETS.keys()))
        raise ValueError(
            f"Unknown nonredundant alpha set '{set_name}'. "
            f"Valid sets: [{valid}]"
        )

    alpha_names = NONREDUNDANT_ALPHA_SETS[set_name]
    if max_candidates is not None and max_candidates > 0:
        alpha_names = alpha_names[:max_candidates]

    result = df.copy()
    groups = result[symbol_col]

    # Ensure sorted by symbol, date for rolling operations
    result = result.sort_values([symbol_col, date_col]).reset_index(drop=True)
    groups = result[symbol_col]

    logger.info(
        f"[NonredundantAlphas] Computing {len(alpha_names)} alphas "
        f"from set '{set_name}' (sector_map={'yes' if sector_map else 'no'})"
    )

    # Family 1: Liquidity Shock Reversal
    if "alpha_nr_liq_shock_zscore_20" in alpha_names:
        result["alpha_nr_liq_shock_zscore_20"] = _compute_liq_shock_zscore(
            result, groups, symbol_col, volume_col, window=20,
        )

    if "alpha_nr_liq_shock_reversal_10" in alpha_names:
        result["alpha_nr_liq_shock_reversal_10"] = _compute_liq_shock_reversal(
            result, groups, symbol_col, close_col, volume_col, window=10,
        )

    # Family 2: Range Pressure / Close-Location Value
    if "alpha_nr_close_location_value_10" in alpha_names:
        result["alpha_nr_close_location_value_10"] = _compute_close_location_value(
            result, groups, symbol_col, high_col, low_col, close_col, window=10,
        )

    if "alpha_nr_range_pressure_momentum_20" in alpha_names:
        result["alpha_nr_range_pressure_momentum_20"] = _compute_range_pressure_momentum(
            result, groups, symbol_col, high_col, low_col, window=20,
        )

    # Family 3: Volatility Compression Breakout
    if "alpha_nr_vol_compression_20" in alpha_names:
        result["alpha_nr_vol_compression_20"] = _compute_vol_compression(
            result, groups, symbol_col, close_col, window=20,
        )

    if "alpha_nr_vol_breakout_directional_10" in alpha_names:
        result["alpha_nr_vol_breakout_directional_10"] = _compute_vol_breakout_directional(
            result, groups, symbol_col, close_col, window=10,
        )

    # Family 4: Sector/Market-Relative Residual Momentum/Reversal
    if "alpha_nr_residual_reversal_10" in alpha_names:
        result["alpha_nr_residual_reversal_10"] = _compute_residual_reversal(
            result, symbol_col, close_col, date_col, window=10,
            sector_map=sector_map,
        )

    if "alpha_nr_market_relative_momentum_20" in alpha_names:
        result["alpha_nr_market_relative_momentum_20"] = _compute_market_relative_momentum(
            result, symbol_col, close_col, date_col, window=20,
        )

    # Family 5: Breadth-Conditioned Reversal
    if "alpha_nr_breadth_conditioned_reversal_10" in alpha_names:
        result["alpha_nr_breadth_conditioned_reversal_10"] = _compute_breadth_conditioned_reversal(
            result, symbol_col, close_col, date_col, window=10,
        )

    if "alpha_nr_advance_decline_signal_20" in alpha_names:
        result["alpha_nr_advance_decline_signal_20"] = _compute_advance_decline_signal(
            result, symbol_col, close_col, date_col, window=20,
        )

    logger.info(
        f"[NonredundantAlphas] Computed {len(alpha_names)} alpha columns"
    )
    return result


def load_sector_map(
    path: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Load sector mapping from CSV file.

    Parameters
    ----------
    path : str, optional
        Explicit path to sector mapping CSV. If None, tries default location.
    repo_root : str, optional
        Repository root directory. Used to resolve default path.

    Returns
    -------
    dict or None
        Mapping of ticker -> sector, or None if file not found.
    """
    if path is None:
        if repo_root is not None:
            path = str(Path(repo_root) / "data" / "sector_mapping_level2.csv")
        else:
            # Try relative to this file
            path = str(
                Path(__file__).resolve().parents[4]
                / "data"
                / "sector_mapping_level2.csv"
            )

    try:
        sector_df = pd.read_csv(path)
        # Expect columns: ticker, sector (or similar)
        ticker_col = None
        sector_col = None
        for col in sector_df.columns:
            cl = col.lower().strip()
            if cl in ("ticker", "symbol", "stock"):
                ticker_col = col
            if cl in ("sector", "industry", "sector_l2", "icb_l2"):
                sector_col = col
        if ticker_col is None:
            ticker_col = sector_df.columns[0]
        if sector_col is None:
            sector_col = sector_df.columns[1]

        mapping = dict(zip(
            sector_df[ticker_col].astype(str).str.strip(),
            sector_df[sector_col].astype(str).str.strip(),
        ))
        logger.info(
            f"[SectorMap] Loaded {len(mapping)} sector mappings from {path}"
        )
        return mapping
    except FileNotFoundError:
        logger.warning(
            f"[SectorMap] Sector mapping file not found at {path}. "
            f"Using market-relative fallback."
        )
        return None
    except Exception as e:
        logger.warning(
            f"[SectorMap] Failed to load sector mapping: {e}. "
            f"Using market-relative fallback."
        )
        return None
