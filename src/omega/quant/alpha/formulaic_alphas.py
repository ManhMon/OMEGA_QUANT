"""Formulaic Alpha Adapter — Kakushadze 101 Formulaic Alphas (PIT-safe subset).

GATE: FORMULAIC_ALPHA_ADAPTER_20260614
GATE: FORMULAIC_ALPHA_V2_20260614
GATE: FORMULAIC_ALPHA_V3_PRUNE_20260614
GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616
Version: 1.3.0
Date: 2026-06-16

Research-only, opt-in adapter that generates PIT-safe subsets of formulaic
alpha candidates inspired by Kakushadze (2016) "101 Formulaic Alphas".

Only existing OHLCV/volume fields from Phase35 data are used.  No external
data is required.  The adapter is disabled by default and has no effect on
live or default pipeline behaviour.

ALPHA SET "small" (v1, 5 candidates):
  1. alpha_fml001_ts_rank_momentum_20   — ts_rank of 5d return over 20d window
  2. alpha_fml006_vp_corr_10            — -1 * corr(open, volume, 10d)
  3. alpha_fml012_mean_rev_rank_10      — mean-reversion rank signal
  4. alpha_fml033_vol_vol_interact_10   — volatility x volume interaction
  5. alpha_fml045_liq_turnover_5        — body-to-range turnover proxy

ALPHA SET "mean_reversion_liquidity" (v2, 8 candidates):
  GATE: FORMULAIC_ALPHA_V2_20260614
  Research-only opt-in.  Focuses on mean reversion / liquidity / volume-price
  families.  Excludes weak momentum (alpha_fml001 negative IC in CPCV12).
  Best v1 candidates retained: fml012 (IC 0.0104, 75% pos folds),
  fml045 (IC 0.0091, 66.7%), fml006 (IC 0.0059).
  1. alpha_fml006_vp_corr_10            — -1 * corr(open, volume, 10d)
  2. alpha_fml012_mean_rev_rank_10      — mean-reversion rank signal
  3. alpha_fml033_vol_vol_interact_10   — volatility x volume interaction
  4. alpha_fml045_liq_turnover_5        — body-to-range turnover proxy
  5. alpha_fml052_close_zscore_mr_20    — close z-score mean reversion
  6. alpha_fml067_vol_price_diverge_10  — volume-price trend divergence
  7. alpha_fml078_range_compression_10  — high-low range compression
  8. alpha_fml089_amihud_illiq_20       — Amihud illiquidity ratio

ALPHA SET "v3_pruned" (v3, 5 candidates):
  GATE: FORMULAIC_ALPHA_V3_PRUNE_20260614
  Research-only opt-in ablation set.  Prunes v2 candidates with negative
  CPCV12 IC (fml089 Amihud IC -0.0610, fml078 range compression IC -0.0100,
  fml033 vol-vol interaction weak/mediocre).  Retains only the 5 candidates
  with strongest positive IC evidence from v2 CPCV12 evaluation.
  Excluded: momentum (v1), amihud_illiq, range_compression, vol_vol_interact.
  1. alpha_fml052_close_zscore_mr_20    — close z-score mean reversion  (IC 0.0164)
  2. alpha_fml012_mean_rev_rank_10      — mean-reversion rank signal    (IC 0.0104)
  3. alpha_fml045_liq_turnover_5        — body-to-range turnover proxy  (IC 0.0091)
  4. alpha_fml067_vol_price_diverge_10  — volume-price trend divergence (IC 0.0080)
  5. alpha_fml006_vp_corr_10            — -1 * corr(open, volume, 10d)  (IC 0.0059)

ALPHA SET "v4_vn_extended" (v4, 7 candidates):
  GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616
  Research-only opt-in extension of v3_pruned.  Adds 2 new VN microstructure/
  liquidity alpha factors designed for Vietnam equity market characteristics:
  - alpha_fml090_vn_liquidity_momentum: Captures accelerating/decelerating
    liquidity via turnover momentum (volume normalized by typical price).
  - alpha_fml091_vn_hl_spread_reversal: High-low spread z-score mean-reversion
    signal. Wide spreads expected to compress (mean revert).
  Retains all 5 v3_pruned candidates (positive IC, strong signal quality).
  1. alpha_fml052_close_zscore_mr_20       — close z-score mean reversion
  2. alpha_fml012_mean_rev_rank_10         — mean-reversion rank signal
  3. alpha_fml045_liq_turnover_5           — body-to-range turnover proxy
  4. alpha_fml067_vol_price_diverge_10     — volume-price trend divergence
  5. alpha_fml006_vp_corr_10               — -1 * corr(open, volume, 10d)
  6. alpha_fml090_vn_liquidity_momentum    — VN liquidity momentum (NEW)
  7. alpha_fml091_vn_hl_spread_reversal    — VN high-low spread reversal (NEW)

COMPLIANCE:
  - PIT Safe: All signals shifted by at least T-1 per ticker (no lookahead)
  - No negative shifts anywhere in computation
  - Inf/NaN sanitised on output
  - Deterministic given same input
  - 100% vectorised (Pandas / NumPy)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger: logging.Logger = logging.getLogger(__name__)

# Gate identifiers for traceability
GATE_ID = "FORMULAIC_ALPHA_ADAPTER_20260614"
GATE_ID_V2 = "FORMULAIC_ALPHA_V2_20260614"
GATE_ID_V3 = "FORMULAIC_ALPHA_V3_PRUNE_20260614"
GATE_ID_V4 = "FORMULAIC_ALPHA_V4_EXTENDED_20260616"

# ---------------------------------------------------------------------------
# Alpha set registry
# ---------------------------------------------------------------------------

FORMULAIC_ALPHA_SETS: Dict[str, Tuple[str, ...]] = {
    "small": (
        "alpha_fml001_ts_rank_momentum_20",
        "alpha_fml006_vp_corr_10",
        "alpha_fml012_mean_rev_rank_10",
        "alpha_fml033_vol_vol_interact_10",
        "alpha_fml045_liq_turnover_5",
    ),
    # GATE: FORMULAIC_ALPHA_V2_20260614
    # Research-only opt-in set focusing on mean reversion / liquidity /
    # volume-price families.  Excludes weak momentum (fml001 negative IC).
    "mean_reversion_liquidity": (
        "alpha_fml006_vp_corr_10",
        "alpha_fml012_mean_rev_rank_10",
        "alpha_fml033_vol_vol_interact_10",
        "alpha_fml045_liq_turnover_5",
        "alpha_fml052_close_zscore_mr_20",
        "alpha_fml067_vol_price_diverge_10",
        "alpha_fml078_range_compression_10",
        "alpha_fml089_amihud_illiq_20",
    ),
    # GATE: FORMULAIC_ALPHA_V3_PRUNE_20260614
    # Research-only opt-in ablation set.  Prunes v2 candidates with negative
    # CPCV12 IC evidence: fml089 Amihud (IC -0.0610), fml078 range compression
    # (IC -0.0100), fml033 vol-vol interaction (weak/mediocre).  Retains only
    # the 5 strongest positive-IC candidates from v2 CPCV12 evaluation.
    # No momentum, no amihud, no range compression.
    "v3_pruned": (
        "alpha_fml052_close_zscore_mr_20",
        "alpha_fml012_mean_rev_rank_10",
        "alpha_fml045_liq_turnover_5",
        "alpha_fml067_vol_price_diverge_10",
        "alpha_fml006_vp_corr_10",
    ),
    # GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616
    # Research-only opt-in extension of v3_pruned.  Adds 2 new VN
    # microstructure/liquidity alpha factors for Vietnam equity market:
    # fml090 (liquidity momentum) and fml091 (high-low spread reversal).
    # Retains all 5 v3_pruned candidates + 2 new VN-specific alphas = 7 total.
    "v4_vn_extended": (
        "alpha_fml052_close_zscore_mr_20",
        "alpha_fml012_mean_rev_rank_10",
        "alpha_fml045_liq_turnover_5",
        "alpha_fml067_vol_price_diverge_10",
        "alpha_fml006_vp_corr_10",
        "alpha_fml090_vn_liquidity_momentum",
        "alpha_fml091_vn_hl_spread_reversal",
    ),
}

# Public alias used by CLI / engine
DEFAULT_FORMULAIC_ALPHA_SET = "small"


def get_formulaic_alpha_columns(set_name: str = "small") -> Tuple[str, ...]:
    """Return tuple of alpha column names for a given set.

    Parameters
    ----------
    set_name : str
        Name of the alpha set.  Currently only "small" is supported.

    Returns
    -------
    tuple of str
        Alpha column names.

    Raises
    ------
    ValueError
        If set_name is not recognised.
    """
    if set_name not in FORMULAIC_ALPHA_SETS:
        valid = ", ".join(sorted(FORMULAIC_ALPHA_SETS.keys()))
        raise ValueError(
            f"Unknown formulaic alpha set '{set_name}'. Valid: [{valid}]"
        )
    return FORMULAIC_ALPHA_SETS[set_name]


# ---------------------------------------------------------------------------
# Internal helpers (PIT-safe building blocks)
# ---------------------------------------------------------------------------

def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    fill_value: float = 0.0,
) -> pd.Series:
    """Division with zero / NaN / Inf protection."""
    result: pd.Series = numerator / denominator
    result = result.replace([np.inf, -np.inf], np.nan).fillna(fill_value)
    return result.astype(np.float64)


def _sanitize(series: pd.Series) -> pd.Series:
    """Replace inf/nan with 0.0 and cast to float64."""
    return series.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float64)


def _groupby_rank(
    series: pd.Series,
    groups: pd.Series,
) -> pd.Series:
    """Cross-sectional percentile rank within each group (0-1 range).

    Parameters
    ----------
    series : pd.Series
        Values to rank.
    groups : pd.Series
        Group labels (e.g., dates for cross-sectional rank).
    """
    ranked = series.groupby(groups).rank(pct=True, method="average")
    return ranked.fillna(0.5)


def _groupby_ts_rank(
    series: pd.Series,
    symbol_groups: pd.Series,
    window: int,
    min_periods: int = 5,
) -> pd.Series:
    """Time-series rank of current value within a rolling window per ticker.

    For each row, count how many of the preceding `window` values are less
    than or equal to the current value, divided by the number of valid
    observations.  This is a PIT-safe rolling-window percentile rank.

    Parameters
    ----------
    series : pd.Series
        Values to rank.
    symbol_groups : pd.Series
        Ticker groups for per-ticker rolling.
    window : int
        Rolling window size.
    min_periods : int
        Minimum observations required.
    """
    def _ts_rank_window(x: pd.Series) -> float:
        if len(x) < min_periods:
            return np.nan
        current = x.iloc[-1]
        if np.isnan(current):
            return np.nan
        count_le = (x[:-1] <= current).sum()
        n_valid = x[:-1].notna().sum()
        if n_valid == 0:
            return np.nan
        return count_le / n_valid

    return (
        series.groupby(symbol_groups)
        .rolling(window, min_periods=min_periods)
        .apply(_ts_rank_window, raw=False)
        .reset_index(level=0, drop=True)
    )


def _groupby_rolling_corr(
    x: pd.Series,
    y: pd.Series,
    symbol_groups: pd.Series,
    window: int,
    min_periods: int = 5,
) -> pd.Series:
    """Rolling Pearson correlation between x and y, per ticker group.

    Uses paired rolling on each group to avoid lookahead.
    """
    df_pair = pd.DataFrame({"x": x, "y": y, "_grp": symbol_groups})
    results = []
    for _grp_name, grp_df in df_pair.groupby("_grp"):
        corr = grp_df["x"].rolling(window, min_periods=min_periods).corr(grp_df["y"])
        results.append(corr)
    if results:
        return pd.concat(results).reindex(x.index)
    return pd.Series(0.0, index=x.index)


def _groupby_rolling_mean(
    series: pd.Series,
    symbol_groups: pd.Series,
    window: int,
    min_periods: int = 1,
) -> pd.Series:
    """Rolling mean per ticker group."""
    return (
        series.groupby(symbol_groups)
        .rolling(window, min_periods=min_periods)
        .mean()
        .reset_index(level=0, drop=True)
    )


def _groupby_rolling_std(
    series: pd.Series,
    symbol_groups: pd.Series,
    window: int,
    min_periods: int = 5,
) -> pd.Series:
    """Rolling std per ticker group."""
    return (
        series.groupby(symbol_groups)
        .rolling(window, min_periods=min_periods)
        .std()
        .reset_index(level=0, drop=True)
    )


def _groupby_rolling_sum(
    series: pd.Series,
    symbol_groups: pd.Series,
    window: int,
    min_periods: int = 1,
) -> pd.Series:
    """Rolling sum per ticker group."""
    return (
        series.groupby(symbol_groups)
        .rolling(window, min_periods=min_periods)
        .sum()
        .reset_index(level=0, drop=True)
    )


# ---------------------------------------------------------------------------
# Formulaic Alpha Implementations
# ---------------------------------------------------------------------------

def _compute_fml001_ts_rank_momentum(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
) -> pd.Series:
    """Alpha001 — ts_rank of 5-day return within 20-day rolling window.

    Inspired by Kakushadze Alpha#001: rank(ts_rank(close, 5)).
    PIT-safe: uses shift(1) on close before computing returns.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    close_lag6 = df.groupby(symbol_col)[close_col].shift(6)
    ret_5 = _safe_divide(
        close_lag - close_lag6, close_lag6.abs().clip(lower=1e-9)
    )
    ts_rank = _groupby_ts_rank(ret_5, symbols, window=20, min_periods=5)
    return _sanitize(ts_rank).clip(0.0, 1.0)


def _compute_fml006_vp_corr(
    df: pd.DataFrame,
    symbol_col: str,
    open_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha006 — -1 * correlation(open, volume, 10d).

    Inspired by Kakushadze Alpha#006: -1 * correlation(open, volume, 10).
    PIT-safe: both open and volume shifted by 1 per ticker.
    """
    symbols = df[symbol_col]
    open_lag = df.groupby(symbol_col)[open_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)
    corr = _groupby_rolling_corr(
        open_lag, volume_lag, symbols, window=10, min_periods=5
    )
    return _sanitize(-1.0 * corr).clip(-1.0, 1.0)


def _compute_fml012_mean_rev_rank(
    df: pd.DataFrame,
    symbol_col: str,
    date_col: str,
    close_col: str,
    volume_col: str,
    open_col: str,
) -> pd.Series:
    """Alpha012 — mean-reversion rank signal.

    Inspired by Kakushadze Alpha#012 (simplified):
    signal = sign(vwap - close) * rank(|close - open| / (high - low + eps))

    Uses cross-sectional rank of intraday body-to-range ratio,
    signed by whether close is below the typical price (mean reversion cue).
    PIT-safe: all inputs shifted T-1.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    open_lag = df.groupby(symbol_col)[open_col].shift(1)
    high_lag = df.groupby(symbol_col)["high"].shift(1)
    low_lag = df.groupby(symbol_col)["low"].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    # Typical price proxy
    typical_price = (high_lag + low_lag + close_lag) / 3.0
    # Sign: positive if close < typical price (mean-reversion expected)
    sign_signal = np.sign(typical_price - close_lag).fillna(0.0)

    # Body-to-range ratio
    body = (close_lag - open_lag).abs()
    range_val = (high_lag - low_lag).clip(lower=1e-9)
    body_range = _safe_divide(body, range_val)

    # Cross-sectional rank by date
    dates = df[date_col]
    ranked_br = _groupby_rank(body_range, dates)

    result = sign_signal * ranked_br
    return _sanitize(result).clip(-1.0, 1.0)


def _compute_fml033_vol_vol_interact(
    df: pd.DataFrame,
    symbol_col: str,
    open_col: str,
    close_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha033 — volatility × volume interaction.

    Inspired by Kakushadze Alpha#033:
    rank(-1 + open/close) * rank(-1 + volume / mean(volume, 10))

    PIT-safe: all inputs shifted T-1 per ticker.
    Cross-sectional rank applied on date groups.
    """
    symbols = df[symbol_col]
    open_lag = df.groupby(symbol_col)[open_col].shift(1)
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    # Price change component
    price_comp = _safe_divide(
        open_lag - close_lag, close_lag.abs().clip(lower=1e-9)
    )
    # Volume deviation from 10d mean
    vol_mean_10 = _groupby_rolling_mean(volume_lag, symbols, window=10, min_periods=3)
    vol_comp = _safe_divide(
        volume_lag - vol_mean_10, vol_mean_10.abs().clip(lower=1e-9)
    )

    # Cross-sectional rank by date
    dates = df[df.columns[0]]  # placeholder — use actual date col from caller
    # We need the date column; passed via a workaround in the main function
    # For now, rank using symbols as proxy (within-group rank per row)
    # Actually: use the full df index alignment
    price_rank = price_comp.groupby(symbols).rank(pct=True).fillna(0.5)
    vol_rank = vol_comp.groupby(symbols).rank(pct=True).fillna(0.5)

    result = price_rank * vol_rank
    return _sanitize(result).clip(-3.0, 3.0)


def _compute_fml033_vol_vol_interact_v2(
    df: pd.DataFrame,
    symbol_col: str,
    date_col: str,
    open_col: str,
    close_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha033 v2 — volatility × volume interaction with cross-sectional rank.

    PIT-safe: all inputs shifted T-1 per ticker.
    """
    symbols = df[symbol_col]
    dates = df[date_col]
    open_lag = df.groupby(symbol_col)[open_col].shift(1)
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    price_comp = _safe_divide(
        open_lag - close_lag, close_lag.abs().clip(lower=1e-9)
    )
    vol_mean_10 = _groupby_rolling_mean(volume_lag, symbols, window=10, min_periods=3)
    vol_comp = _safe_divide(
        volume_lag - vol_mean_10, vol_mean_10.abs().clip(lower=1e-9)
    )

    # Cross-sectional rank by date
    price_rank = _groupby_rank(price_comp, dates)
    vol_rank = _groupby_rank(vol_comp, dates)

    result = price_rank * vol_rank
    return _sanitize(result).clip(-3.0, 3.0)


def _compute_fml045_liq_turnover(
    df: pd.DataFrame,
    symbol_col: str,
    open_col: str,
    close_col: str,
    high_col: str,
    low_col: str,
) -> pd.Series:
    """Alpha045 — liquidity/turnover proxy: -1 * sum(body/range, 5d).

    Inspired by Kakushadze Alpha#045:
    -1 * sum(rank((close - open) / (high - low)), 5)

    PIT-safe: all inputs shifted T-1 per ticker.
    Negative sign: high body/range suggests momentum, so contrarian signal.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    open_lag = df.groupby(symbol_col)[open_col].shift(1)
    high_lag = df.groupby(symbol_col)[high_col].shift(1)
    low_lag = df.groupby(symbol_col)[low_col].shift(1)

    range_val = (high_lag - low_lag).clip(lower=1e-9)
    body_signed = close_lag - open_lag
    body_range = _safe_divide(body_signed, range_val)

    summed = _groupby_rolling_sum(body_range, symbols, window=5, min_periods=1)
    result = -1.0 * summed
    return _sanitize(result).clip(-5.0, 5.0)


# ---------------------------------------------------------------------------
# V2 Formulaic Alpha Implementations (GATE: FORMULAIC_ALPHA_V2_20260614)
# Mean reversion / liquidity / volume-price families.  No momentum.
# ---------------------------------------------------------------------------

def _compute_fml052_close_zscore_mr(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
) -> pd.Series:
    """Alpha052 — close z-score mean reversion signal.

    Measures how far current close deviates from its 20-day rolling mean,
    normalised by rolling std.  Negative z-score implies price below mean
    (expected to revert up), positive implies above mean (expected to revert
    down).  Signal is negated so positive = mean-reversion buy.

    PIT-safe: close shifted T-1 per ticker before rolling.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)

    roll_mean = _groupby_rolling_mean(close_lag, symbols, window=20, min_periods=10)
    roll_std = _groupby_rolling_std(close_lag, symbols, window=20, min_periods=10)

    zscore = _safe_divide(
        close_lag - roll_mean, roll_std.abs().clip(lower=1e-9)
    )
    # Negate: low z-score (below mean) becomes positive (buy signal)
    result = -1.0 * zscore
    return _sanitize(result).clip(-3.0, 3.0)


def _compute_fml067_vol_price_diverge(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha067 — volume-price trend divergence.

    Computes the difference between volume rank and price rank within a
    rolling 10-day window per ticker.  When volume rises but price falls
    (or vice versa), it signals a potential mean-reversion opportunity.

    Specifically: rank_10d(volume) - rank_10d(close).
    High positive values indicate volume increasing while price lags
    (accumulation signal).

    PIT-safe: both close and volume shifted T-1 per ticker.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    def _rolling_pct_rank(x: pd.Series) -> float:
        if len(x) < 5:
            return np.nan
        current = x.iloc[-1]
        if np.isnan(current):
            return np.nan
        count_le = (x[:-1] <= current).sum()
        n_valid = x[:-1].notna().sum()
        if n_valid == 0:
            return np.nan
        return count_le / n_valid

    vol_rank = (
        volume_lag.groupby(symbols)
        .rolling(10, min_periods=5)
        .apply(_rolling_pct_rank, raw=False)
        .reset_index(level=0, drop=True)
    )
    price_rank = (
        close_lag.groupby(symbols)
        .rolling(10, min_periods=5)
        .apply(_rolling_pct_rank, raw=False)
        .reset_index(level=0, drop=True)
    )

    divergence = vol_rank - price_rank
    return _sanitize(divergence).clip(-1.0, 1.0)


def _compute_fml078_range_compression(
    df: pd.DataFrame,
    symbol_col: str,
    high_col: str,
    low_col: str,
    close_col: str,
) -> pd.Series:
    """Alpha078 — high-low range compression signal.

    Measures the ratio of short-term (5d) to long-term (20d) average
    true range.  When short-term range compresses relative to long-term,
    it signals a volatility squeeze often followed by mean-reversion moves.

    Signal: 1 - (5d_avg_range / 20d_avg_range).
    Positive values indicate compression (potential breakout/reversion).

    PIT-safe: all inputs shifted T-1 per ticker.
    """
    symbols = df[symbol_col]
    high_lag = df.groupby(symbol_col)[high_col].shift(1)
    low_lag = df.groupby(symbol_col)[low_col].shift(1)
    close_lag = df.groupby(symbol_col)[close_col].shift(1)

    daily_range = (high_lag - low_lag).clip(lower=1e-9)

    range_5d = _groupby_rolling_mean(daily_range, symbols, window=5, min_periods=3)
    range_20d = _groupby_rolling_mean(daily_range, symbols, window=20, min_periods=10)

    ratio = _safe_divide(range_5d, range_20d.abs().clip(lower=1e-9))
    # Compression: ratio < 1 means short-term range is smaller
    result = 1.0 - ratio
    return _sanitize(result).clip(-2.0, 2.0)


def _compute_fml089_amihud_illiq(
    df: pd.DataFrame,
    symbol_col: str,
    close_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha089 — Amihud illiquidity ratio (20d rolling mean).

    Amihud (2002) illiquidity measure: mean(|daily_return| / dollar_volume).
    Higher illiquidity is associated with higher expected returns (premium).
    Signal is negated so that lower illiquidity (higher liquidity) yields
    a positive contrarian signal.

    PIT-safe: close and volume shifted T-1 per ticker.
    """
    symbols = df[symbol_col]
    close_lag = df.groupby(symbol_col)[close_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    # Daily return from lagged close
    close_lag2 = df.groupby(symbol_col)[close_col].shift(2)
    daily_ret = _safe_divide(
        close_lag - close_lag2, close_lag2.abs().clip(lower=1e-9)
    )

    # Dollar volume proxy (close * volume)
    dollar_volume = close_lag.abs() * volume_lag
    dollar_volume = dollar_volume.clip(lower=1e-9)

    # Amihud ratio: |return| / dollar_volume
    amihud_daily = _safe_divide(daily_ret.abs(), dollar_volume)

    # 20-day rolling mean
    amihud_20d = _groupby_rolling_mean(amihud_daily, symbols, window=20, min_periods=10)

    # Negate: lower illiquidity = higher signal (contrarian)
    result = -1.0 * amihud_20d
    # Scale to reasonable range — Amihud values are typically very small
    # Clip to prevent extreme values
    return _sanitize(result).clip(-1.0, 1.0)


# ---------------------------------------------------------------------------
# V4 VN-Specific Alpha Implementations (GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616)
# Vietnam market microstructure/liquidity alphas.
# ---------------------------------------------------------------------------

def _compute_fml090_vn_liquidity_momentum(
    df: pd.DataFrame,
    symbol_col: str,
    high_col: str,
    low_col: str,
    volume_col: str,
) -> pd.Series:
    """Alpha090 — VN liquidity momentum signal.

    Captures accelerating/decelerating liquidity in Vietnam equity market.
    Measures momentum of turnover ratio (volume normalized by typical price).

    Signal: (turnover_5d - turnover_20d) / turnover_20d
    where turnover = volume / ((high + low) / 2)

    Positive values indicate increasing liquidity (bullish microstructure signal).
    Negative values indicate decreasing liquidity (bearish microstructure signal).

    PIT-safe: all inputs shifted T-1 per ticker.
    GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616
    """
    symbols = df[symbol_col]
    high_lag = df.groupby(symbol_col)[high_col].shift(1)
    low_lag = df.groupby(symbol_col)[low_col].shift(1)
    volume_lag = df.groupby(symbol_col)[volume_col].shift(1)

    # Typical price proxy: (high + low) / 2
    typical_price = (high_lag + low_lag) / 2.0
    typical_price = typical_price.clip(lower=1e-9)

    # Daily turnover ratio: volume / typical_price
    daily_turnover = _safe_divide(volume_lag, typical_price)

    # Rolling mean turnover over 5d and 20d windows
    turnover_5d = _groupby_rolling_mean(daily_turnover, symbols, window=5, min_periods=3)
    turnover_20d = _groupby_rolling_mean(daily_turnover, symbols, window=20, min_periods=10)

    # Momentum: (short_term - long_term) / long_term
    momentum = _safe_divide(
        turnover_5d - turnover_20d, turnover_20d.abs().clip(lower=1e-9)
    )

    return _sanitize(momentum).clip(-2.0, 2.0)


def _compute_fml091_vn_hl_spread_reversal(
    df: pd.DataFrame,
    symbol_col: str,
    high_col: str,
    low_col: str,
    close_col: str,
) -> pd.Series:
    """Alpha091 — VN high-low spread mean-reversion signal.

    High-low spread as percentage of close price, z-scored over 20-day window.
    Wide spreads (high volatility) are expected to revert (compress).

    Signal: -1 * z-score((high - low) / close, 20d)

    Negative z-score (tight spread) gives positive signal (expecting expansion/continuation).
    Positive z-score (wide spread) gives negative signal (expecting mean-reversion/compression).

    PIT-safe: all inputs shifted T-1 per ticker.
    GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616
    """
    symbols = df[symbol_col]
    high_lag = df.groupby(symbol_col)[high_col].shift(1)
    low_lag = df.groupby(symbol_col)[low_col].shift(1)
    close_lag = df.groupby(symbol_col)[close_col].shift(1)

    # High-low spread as % of close
    hl_spread_pct = _safe_divide(
        high_lag - low_lag, close_lag.abs().clip(lower=1e-9)
    )

    # Rolling mean and std over 20-day window
    spread_mean = _groupby_rolling_mean(hl_spread_pct, symbols, window=20, min_periods=10)
    spread_std = _groupby_rolling_std(hl_spread_pct, symbols, window=20, min_periods=10)

    # Z-score: (current - mean) / std
    zscore = _safe_divide(
        hl_spread_pct - spread_mean, spread_std.abs().clip(lower=1e-9)
    )

    # Negate: wide spread (high z-score) becomes negative (mean-reversion signal)
    result = -1.0 * zscore

    return _sanitize(result).clip(-3.0, 3.0)



# ---------------------------------------------------------------------------
# Main adapter entry point
# ---------------------------------------------------------------------------

def compute_formulaic_alphas(
    df: pd.DataFrame,
    *,
    set_name: str = "small",
    symbol_col: str = "ticker",
    date_col: str = "date",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.DataFrame:
    """Compute formulaic alpha columns and append to DataFrame.

    GATE: FORMULAIC_ALPHA_ADAPTER_20260614
    GATE: FORMULAIC_ALPHA_V2_20260614

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV panel with at minimum: symbol_col, date_col, open, high, low,
        close, volume columns.
    set_name : str
        Alpha set to compute.  ``"small"`` (5 alphas, v1) or
        ``"mean_reversion_liquidity"`` (8 alphas, v2).
    symbol_col, date_col, ... : str
        Column name overrides.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with formulaic alpha columns appended.
        If set_name is not recognised, returns df unchanged with a warning.
    """
    if set_name not in FORMULAIC_ALPHA_SETS:
        logger.warning(
            f"[FormulaicAlphas] Unknown set '{set_name}', skipping. "
            f"Valid: {list(FORMULAIC_ALPHA_SETS.keys())}"
        )
        return df.copy()

    df_work: pd.DataFrame = df.copy()
    df_work = df_work.sort_values([date_col, symbol_col]).reset_index(drop=True)

    required_cols = [open_col, high_col, low_col, close_col, volume_col, symbol_col, date_col]
    missing = [c for c in required_cols if c not in df_work.columns]
    if missing:
        logger.warning(
            f"[FormulaicAlphas] Missing columns {missing}, skipping computation"
        )
        return df_work

    alpha_names = FORMULAIC_ALPHA_SETS[set_name]
    logger.info(
        f"[FormulaicAlphas] Computing set='{set_name}' ({len(alpha_names)} alphas) "
        f"gate={GATE_ID}"
    )

    alphas: Dict[str, pd.Series] = {}

    # Alpha 001 — ts_rank momentum (v1 only)
    if "alpha_fml001_ts_rank_momentum_20" in alpha_names:
        try:
            alphas["alpha_fml001_ts_rank_momentum_20"] = _compute_fml001_ts_rank_momentum(
                df_work, symbol_col, close_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml001 failed: {e}")
            alphas["alpha_fml001_ts_rank_momentum_20"] = pd.Series(0.0, index=df_work.index)

    # Alpha 006 — volume-price correlation
    if "alpha_fml006_vp_corr_10" in alpha_names:
        try:
            alphas["alpha_fml006_vp_corr_10"] = _compute_fml006_vp_corr(
                df_work, symbol_col, open_col, volume_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml006 failed: {e}")
            alphas["alpha_fml006_vp_corr_10"] = pd.Series(0.0, index=df_work.index)

    # Alpha 012 — mean-reversion rank
    if "alpha_fml012_mean_rev_rank_10" in alpha_names:
        try:
            alphas["alpha_fml012_mean_rev_rank_10"] = _compute_fml012_mean_rev_rank(
                df_work, symbol_col, date_col, close_col, volume_col, open_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml012 failed: {e}")
            alphas["alpha_fml012_mean_rev_rank_10"] = pd.Series(0.0, index=df_work.index)

    # Alpha 033 — volatility x volume interaction
    if "alpha_fml033_vol_vol_interact_10" in alpha_names:
        try:
            alphas["alpha_fml033_vol_vol_interact_10"] = _compute_fml033_vol_vol_interact_v2(
                df_work, symbol_col, date_col, open_col, close_col, volume_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml033 failed: {e}")
            alphas["alpha_fml033_vol_vol_interact_10"] = pd.Series(0.0, index=df_work.index)

    # Alpha 045 — liquidity/turnover proxy
    if "alpha_fml045_liq_turnover_5" in alpha_names:
        try:
            alphas["alpha_fml045_liq_turnover_5"] = _compute_fml045_liq_turnover(
                df_work, symbol_col, open_col, close_col, high_col, low_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml045 failed: {e}")
            alphas["alpha_fml045_liq_turnover_5"] = pd.Series(0.0, index=df_work.index)

    # GATE: FORMULAIC_ALPHA_V2_20260614 — v2-only alphas
    # Alpha 052 — close z-score mean reversion
    if "alpha_fml052_close_zscore_mr_20" in alpha_names:
        try:
            alphas["alpha_fml052_close_zscore_mr_20"] = _compute_fml052_close_zscore_mr(
                df_work, symbol_col, close_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml052 failed: {e}")
            alphas["alpha_fml052_close_zscore_mr_20"] = pd.Series(0.0, index=df_work.index)

    # Alpha 067 — volume-price divergence
    if "alpha_fml067_vol_price_diverge_10" in alpha_names:
        try:
            alphas["alpha_fml067_vol_price_diverge_10"] = _compute_fml067_vol_price_diverge(
                df_work, symbol_col, close_col, volume_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml067 failed: {e}")
            alphas["alpha_fml067_vol_price_diverge_10"] = pd.Series(0.0, index=df_work.index)

    # Alpha 078 — range compression
    if "alpha_fml078_range_compression_10" in alpha_names:
        try:
            alphas["alpha_fml078_range_compression_10"] = _compute_fml078_range_compression(
                df_work, symbol_col, high_col, low_col, close_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml078 failed: {e}")
            alphas["alpha_fml078_range_compression_10"] = pd.Series(0.0, index=df_work.index)

    # Alpha 089 — Amihud illiquidity
    if "alpha_fml089_amihud_illiq_20" in alpha_names:
        try:
            alphas["alpha_fml089_amihud_illiq_20"] = _compute_fml089_amihud_illiq(
                df_work, symbol_col, close_col, volume_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml089 failed: {e}")
            alphas["alpha_fml089_amihud_illiq_20"] = pd.Series(0.0, index=df_work.index)

    # GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616 — v4-only alphas
    # Alpha 090 — VN liquidity momentum
    if "alpha_fml090_vn_liquidity_momentum" in alpha_names:
        try:
            alphas["alpha_fml090_vn_liquidity_momentum"] = _compute_fml090_vn_liquidity_momentum(
                df_work, symbol_col, high_col, low_col, volume_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml090 failed: {e}")
            alphas["alpha_fml090_vn_liquidity_momentum"] = pd.Series(0.0, index=df_work.index)

    # Alpha 091 — VN high-low spread reversal
    if "alpha_fml091_vn_hl_spread_reversal" in alpha_names:
        try:
            alphas["alpha_fml091_vn_hl_spread_reversal"] = _compute_fml091_vn_hl_spread_reversal(
                df_work, symbol_col, high_col, low_col, close_col
            )
        except Exception as e:
            logger.warning(f"[FormulaicAlphas] fml091 failed: {e}")
            alphas["alpha_fml091_vn_hl_spread_reversal"] = pd.Series(0.0, index=df_work.index)

    # Append to DataFrame with sanitisation
    df_out = df_work.copy()
    for name in alpha_names:
        if name in alphas:
            df_out[name] = _sanitize(alphas[name])
        else:
            df_out[name] = 0.0

    logger.info(f"[FormulaicAlphas] Computed {len(alphas)} alphas successfully")
    return df_out


def get_formulaic_alpha_metadata() -> Dict[str, Dict[str, str]]:
    """Return metadata dict for all formulaic alphas."""
    return {
        "alpha_fml001_ts_rank_momentum_20": {
            "category": "Formulaic (Kakushadze-inspired)",
            "family": "momentum",
            "description": "ts_rank of 5d return within 20d window — momentum rank",
            "source": GATE_ID,
        },
        "alpha_fml006_vp_corr_10": {
            "category": "Formulaic (Kakushadze-inspired)",
            "family": "volume_price",
            "description": "-1 * rolling corr(open, volume, 10d) — volume-price divergence",
            "source": GATE_ID,
        },
        "alpha_fml012_mean_rev_rank_10": {
            "category": "Formulaic (Kakushadze-inspired)",
            "family": "mean_reversion",
            "description": "Signed body-to-range rank — mean-reversion rank signal",
            "source": GATE_ID,
        },
        "alpha_fml033_vol_vol_interact_10": {
            "category": "Formulaic (Kakushadze-inspired)",
            "family": "volatility_volume",
            "description": "Volatility x volume interaction rank — cross-sectional",
            "source": GATE_ID,
        },
        "alpha_fml045_liq_turnover_5": {
            "category": "Formulaic (Kakushadze-inspired)",
            "family": "liquidity",
            "description": "-1 * sum(body/range, 5d) — liquidity/turnover proxy",
            "source": GATE_ID,
        },
        # GATE: FORMULAIC_ALPHA_V2_20260614 — v2 metadata
        "alpha_fml052_close_zscore_mr_20": {
            "category": "Formulaic v2 (mean-reversion/liquidity)",
            "family": "mean_reversion",
            "description": "Negated z-score of close vs 20d rolling mean — mean reversion",
            "source": GATE_ID_V2,
        },
        "alpha_fml067_vol_price_diverge_10": {
            "category": "Formulaic v2 (mean-reversion/liquidity)",
            "family": "volume_price",
            "description": "Volume rank minus price rank over 10d — accumulation/divergence",
            "source": GATE_ID_V2,
        },
        "alpha_fml078_range_compression_10": {
            "category": "Formulaic v2 (mean-reversion/liquidity)",
            "family": "mean_reversion",
            "description": "1 - (5d avg range / 20d avg range) — volatility squeeze/compression",
            "source": GATE_ID_V2,
        },
        "alpha_fml089_amihud_illiq_20": {
            "category": "Formulaic v2 (mean-reversion/liquidity)",
            "family": "liquidity",
            "description": "Negated Amihud illiquidity ratio (20d) — liquidity premium proxy",
            "source": GATE_ID_V2,
        },
        # GATE: FORMULAIC_ALPHA_V4_EXTENDED_20260616 — v4 VN-specific metadata
        "alpha_fml090_vn_liquidity_momentum": {
            "category": "Formulaic v4 (VN microstructure/liquidity)",
            "family": "liquidity",
            "description": "VN liquidity momentum: (turnover_5d - turnover_20d) / turnover_20d",
            "source": GATE_ID_V4,
        },
        "alpha_fml091_vn_hl_spread_reversal": {
            "category": "Formulaic v4 (VN microstructure/liquidity)",
            "family": "mean_reversion",
            "description": "VN high-low spread z-score mean-reversion: -1 * zscore((H-L)/C, 20d)",
            "source": GATE_ID_V4,
        },
    }


# ---------------------------------------------------------------------------
# V3 Ablation Report (GATE: FORMULAIC_ALPHA_V3_PRUNE_20260614)
# ---------------------------------------------------------------------------

def get_v3_ablation_report() -> Dict:
    """Return ablation metadata comparing v2 vs v3 candidate lists.

    Research-only evidence summary for Tier 3 audit.  All IC values are
    CPCV12 portfolio IC from the v2 evaluation run (2026-06-14).

    Returns
    -------
    dict
        JSON-serialisable ablation report with v2 candidates, v3 retained,
        v3 excluded, IC evidence, and rationale.
    """
    v2_candidates = list(FORMULAIC_ALPHA_SETS["mean_reversion_liquidity"])
    v3_candidates = list(FORMULAIC_ALPHA_SETS["v3_pruned"])

    ic_evidence: Dict[str, float] = {
        "alpha_fml052_close_zscore_mr_20": 0.0164,
        "alpha_fml012_mean_rev_rank_10": 0.0104,
        "alpha_fml045_liq_turnover_5": 0.0091,
        "alpha_fml067_vol_price_diverge_10": 0.0080,
        "alpha_fml006_vp_corr_10": 0.0059,
        "alpha_fml033_vol_vol_interact_10": 0.0037,
        "alpha_fml078_range_compression_10": -0.0100,
        "alpha_fml089_amihud_illiq_20": -0.0610,
    }

    excluded = [c for c in v2_candidates if c not in v3_candidates]
    excluded_reasons: Dict[str, str] = {
        "alpha_fml089_amihud_illiq_20": (
            "Negative CPCV12 IC (-0.0610). Amihud illiquidity ratio "
            "shows strong negative signal — harmful to portfolio. "
            "No transformation evidence available to rehabilitate."
        ),
        "alpha_fml078_range_compression_10": (
            "Negative CPCV12 IC (-0.0100). Range compression signal "
            "anti-predictive in Vietnam market. No transformation "
            "evidence available to rehabilitate."
        ),
        "alpha_fml033_vol_vol_interact_10": (
            "Weak CPCV12 IC (~0.0037, at portfolio average). "
            "Volatility-volume interaction adds noise without "
            "improving mean IC. Pruned for parsimony."
        ),
    }

    v2_raw_ic: float = 0.0083
    v2_portfolio_ic: float = 0.0037
    v3_expected_mean_ic: float = sum(
        ic_evidence[c] for c in v3_candidates
    ) / len(v3_candidates)

    return {
        "gate": GATE_ID_V3,
        "version": "v3_pruned",
        "date": "2026-06-14",
        "v2_set_name": "mean_reversion_liquidity",
        "v2_n_candidates": len(v2_candidates),
        "v2_candidates": v2_candidates,
        "v2_cpcv12_portfolio_ic": v2_portfolio_ic,
        "v2_cpcv12_raw_ic": v2_raw_ic,
        "v3_set_name": "v3_pruned",
        "v3_n_candidates": len(v3_candidates),
        "v3_candidates": v3_candidates,
        "v3_expected_mean_candidate_ic": round(v3_expected_mean_ic, 4),
        "v3_excluded": excluded,
        "v3_exclusion_rationale": excluded_reasons,
        "ic_evidence_by_candidate": ic_evidence,
        "v3_retained_all_positive_ic": all(
            ic_evidence[c] > 0 for c in v3_candidates
        ),
        "v3_no_momentum": not any(
            "momentum" in c for c in v3_candidates
        ),
        "v3_no_amihud": "alpha_fml089_amihud_illiq_20" not in v3_candidates,
        "v3_no_range_compression": "alpha_fml078_range_compression_10" not in v3_candidates,
        "pit_safe": True,
        "deterministic": True,
        "default_unchanged": DEFAULT_FORMULAIC_ALPHA_SET == "small",
    }
