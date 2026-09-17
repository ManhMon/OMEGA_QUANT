"""Hybrid Regime Alpha Signals — v2 Expansion.

Gate: HYBRID_REGIME_ALPHA_EXPANSION_20260621

Provides 15 PIT-safe alpha signals spanning:
  - 7 original hybrid regime signals (v1)
  - 8 new expansion signals (v2): intraday microstructure, sector rotation,
    sentiment blend, and regime-conditional features.

COMPLIANCE:
  - PIT Safety: All signals use groupby(symbol).shift(1) — T-1 lag.
  - Vectorization: 100% Pandas/NumPy, zero Python loops over rows.
  - Robustness: Inf/NaN replaced with 0.0; bounded output.

Economic rationale per signal is documented in each function's docstring.
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column name constants
# ---------------------------------------------------------------------------

# v1 (original 7)
_VAM = "alpha_hr_vol_adjusted_momentum"
_VPP = "alpha_hr_volume_price_pressure"
_RPB = "alpha_hr_range_position_breakout"
_XDISP = "alpha_hr_cross_sectional_dispersion"
_LSR = "alpha_hr_liquidity_shock_reversal"
_VCE = "alpha_hr_vol_compression_expansion"
_SMD = "alpha_hr_smart_money_divergence"

# v2 (expansion 8)
_OGR = "alpha_hr_overnight_gap_return"
_IRVR = "alpha_hr_intraday_range_volume_ratio"
_SRS = "alpha_hr_sector_relative_strength"
_SMS = "alpha_hr_sector_momentum_spread"
_SPB = "alpha_hr_sentiment_price_blend"
_RCM = "alpha_hr_regime_conditional_momentum"
_BAB = "alpha_hr_bid_ask_bounce_proxy"
_VIP = "alpha_hr_volume_imbalance_pressure"

# Public lists
HYBRID_REGIME_ALPHA_COLUMNS: list[str] = [
    _VAM, _VPP, _RPB, _XDISP, _LSR, _VCE, _SMD,
]

HYBRID_REGIME_V2_COLUMNS: list[str] = [
    _OGR, _IRVR, _SRS, _SMS, _SPB, _RCM, _BAB, _VIP,
]

ALL_HYBRID_REGIME_COLUMNS: list[str] = (
    HYBRID_REGIME_ALPHA_COLUMNS + HYBRID_REGIME_V2_COLUMNS
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_divide(
    num: pd.Series, den: pd.Series, fill: float = 0.0
) -> pd.Series:
    """Divide two series, replacing inf/nan with *fill*."""
    result = num / den.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan).fillna(fill)


def _pit_shift(series: pd.Series, symbol_col_vals: pd.Series) -> pd.Series:
    """Apply T-1 shift per symbol for PIT safety.

    Groups *series* by *symbol_col_vals* and shifts by 1 period.
    The first row per symbol becomes 0.0 (not NaN).
    """
    shifted = series.groupby(symbol_col_vals).shift(1)
    return shifted.fillna(0.0)


# ---------------------------------------------------------------------------
# v1: Original 7 Signals
# ---------------------------------------------------------------------------

def compute_vol_adjusted_momentum(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Volatility-adjusted momentum.

    Economic rationale: raw momentum divided by realised volatility
    captures risk-adjusted price trends.  Stocks with high momentum
    but low vol are stronger candidates than high-momentum/high-vol.

    PIT: uses shift(1) — signal at T uses data up to T-1.
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    mom = df.groupby(symbol_col)["close"].pct_change(period)
    vol = ret.groupby(df[symbol_col]).rolling(period).std().reset_index(level=0, drop=True)
    raw = _safe_divide(mom, vol)
    return _pit_shift(raw, df[symbol_col])


def compute_volume_price_pressure(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Volume-weighted price pressure.

    Economic rationale: combines price change with volume surge to
    detect institutional accumulation/distribution.  High volume on
    up days suggests buying pressure; high volume on down days
    suggests distribution.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    vol_ratio = df[symbol_col].groupby(df[symbol_col]).transform(
        lambda _: 1.0
    )  # placeholder for proper vol ratio
    vol_ma = df.groupby(symbol_col)["volume"].transform(
        lambda x: x.rolling(period, min_periods=5).mean()
    )
    vol_norm = _safe_divide(df["volume"], vol_ma)
    raw = ret * vol_norm
    raw = raw.groupby(df[symbol_col]).rolling(period, min_periods=5).mean().reset_index(level=0, drop=True)
    return _pit_shift(raw, df[symbol_col])


def compute_range_position_breakout(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Close location value within the daily range (CLV).

    Economic rationale: CLV near 1.0 signals strong buying into the
    close; CLV near 0.0 signals selling pressure.  Averaged over a
    window, this detects accumulation/distribution patterns.

    PIT: uses shift(1).
    """
    hl_range = df["high"] - df["low"]
    clv = _safe_divide(2.0 * df["close"] - df["low"] - df["high"], hl_range)
    raw = clv.groupby(df[symbol_col]).rolling(period, min_periods=5).mean().reset_index(level=0, drop=True)
    return _pit_shift(raw, df[symbol_col])


def compute_cross_sectional_dispersion(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Cross-sectional return dispersion per stock vs. universe.

    Economic rationale: stocks whose returns deviate from the
    cross-sectional mean may be undergoing idiosyncratic repricing.
    High positive dispersion indicates outperformance relative to peers.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    daily_mean = ret.groupby(df["date"]).transform("mean")
    daily_std = ret.groupby(df["date"]).transform("std").replace(0, np.nan)
    raw = _safe_divide(ret - daily_mean, daily_std)
    raw = raw.groupby(df[symbol_col]).rolling(period, min_periods=5).mean().reset_index(level=0, drop=True)
    return _pit_shift(raw, df[symbol_col])


def compute_liquidity_shock_reversal(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Liquidity shock reversal — mean-reversion after volume spikes.

    Economic rationale: extreme volume events (liquidity shocks) are
    often followed by short-term reversals as the market absorbs the
    information.  Stocks with large volume spikes tend to revert.

    PIT: uses shift(1).
    """
    vol_ma = df.groupby(symbol_col)["volume"].transform(
        lambda x: x.rolling(period, min_periods=5).mean()
    )
    vol_std = df.groupby(symbol_col)["volume"].transform(
        lambda x: x.rolling(period, min_periods=5).std()
    )
    vol_zscore = _safe_divide(df["volume"] - vol_ma, vol_std)
    ret = df.groupby(symbol_col)["close"].pct_change()
    # Negative correlation: high volume shock → expect reversal
    raw = -(vol_zscore * ret)
    raw = raw.groupby(df[symbol_col]).rolling(period, min_periods=5).mean().reset_index(level=0, drop=True)
    return _pit_shift(raw, df[symbol_col])


def compute_vol_compression_expansion(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Volatility compression/expansion signal.

    Economic rationale: volatility is mean-reverting.  After periods
    of compression (low vol), breakouts tend to follow.  This signal
    captures the ratio of short-term to long-term volatility.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    short_vol = ret.groupby(df[symbol_col]).rolling(5, min_periods=3).std().reset_index(level=0, drop=True)
    long_vol = ret.groupby(df[symbol_col]).rolling(period, min_periods=5).std().reset_index(level=0, drop=True)
    raw = _safe_divide(short_vol, long_vol) - 1.0
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_smart_money_divergence(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Smart money divergence — volume-weighted return vs. equal-weighted.

    Economic rationale: large-volume trades are more likely to be
    informed (smart money).  When volume-weighted returns diverge
    from equal-weighted returns, it signals institutional activity.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    vol_ret = ret * df["volume"]
    vol_sum = df.groupby(symbol_col)["volume"].rolling(period, min_periods=5).sum().reset_index(level=0, drop=True)
    vw_ret = vol_ret.groupby(df[symbol_col]).rolling(period, min_periods=5).sum().reset_index(level=0, drop=True)
    vw_ret_norm = _safe_divide(vw_ret, vol_sum)
    ew_ret = ret.groupby(df[symbol_col]).rolling(period, min_periods=5).mean().reset_index(level=0, drop=True)
    raw = vw_ret_norm - ew_ret
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


# ---------------------------------------------------------------------------
# v2: 8 New Expansion Signals
# ---------------------------------------------------------------------------

def compute_overnight_gap_return(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
) -> pd.Series:
    """Overnight gap return: open_T / close_{T-1} - 1.

    Category: Intraday microstructure.

    Economic rationale: overnight gaps capture information that arrives
    outside trading hours (earnings, news, global market moves).
    In VN market, the ATO auction reflects overnight order accumulation.
    Large positive gaps often lead to intraday fade (reversal),
    while small gaps may indicate continuation.

    PIT: uses shift(1) — gap at T uses close_{T-1}, which is available
    before T's open.  Then shifted again so signal is available for
    trading at T+1.
    """
    prev_close = df.groupby(symbol_col)["close"].shift(1)
    raw = _safe_divide(df["open"] - prev_close, prev_close)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_intraday_range_volume_ratio(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Intraday range per unit volume: (H - L) / (volume * close).

    Category: Intraday microstructure / bid-ask bounce proxy.

    Economic rationale: high range per unit of dollar volume indicates
    a thin order book — prices move more for each share traded.
    This is a proxy for bid-ask bounce and market impact cost.
    Stocks with low range/volume have deep books (easier to trade).
    Averaged over a window for stability.

    PIT: uses shift(1).
    """
    dollar_vol = df["volume"] * df["close"]
    hl_range = df["high"] - df["low"]
    raw_point = _safe_divide(hl_range, dollar_vol)
    raw = raw_point.groupby(df[symbol_col]).rolling(
        period, min_periods=5
    ).mean().reset_index(level=0, drop=True)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_sector_relative_strength(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    sector_col: str = "sector",
    period: int = 20,
) -> pd.Series:
    """Relative sector strength: stock return minus sector average return.

    Category: Sector rotation.

    Economic rationale: sector rotation is a key driver of
    cross-sectional returns.  Stocks in outperforming sectors
    tend to continue outperforming (sector momentum), while
    the within-sector relative strength captures stock-specific alpha.
    This signal isolates the stock's excess return over its sector.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change(period)

    if sector_col in df.columns:
        sector_ret = ret.groupby(
            [df[sector_col], df["date"]]
        ).transform("mean")
    else:
        # Fallback: use cross-sectional mean as proxy
        sector_ret = ret.groupby(df["date"]).transform("mean")

    raw = ret - sector_ret
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_sector_momentum_spread(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    sector_col: str = "sector",
    period: int = 20,
) -> pd.Series:
    """Sector momentum spread: rank of stock's sector momentum in universe.

    Category: Sector rotation.

    Economic rationale: measures where a stock's sector sits in the
    sector momentum ranking.  Stocks in top-ranked sectors get a
    positive signal; stocks in bottom-ranked sectors get negative.
    This captures the sector rotation effect where capital flows
    from lagging to leading sectors.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change(period)

    if sector_col in df.columns:
        sector_avg = ret.groupby(
            [df[sector_col], df["date"]]
        ).transform("mean")
    else:
        sector_avg = ret.groupby(df["date"]).transform("mean")

    # Rank sector momentum cross-sectionally per day
    sector_rank = sector_avg.groupby(df["date"]).rank(pct=True)
    # Center around 0: [-0.5, 0.5]
    raw = sector_rank - 0.5
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_sentiment_price_blend(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Sentiment-price blend: volume surge + price trend as sentiment proxy.

    Category: Sentiment blend.

    Economic rationale: in the absence of direct news sentiment data,
    volume surges combined with price trends serve as a proxy for
    market sentiment.  High volume on up-days signals bullish
    sentiment; high volume on down-days signals bearish sentiment.
    The blend smooths short-term noise with a rolling average.

    PIT: uses shift(1).
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    vol_ma = df.groupby(symbol_col)["volume"].transform(
        lambda x: x.rolling(period, min_periods=5).mean()
    )
    vol_surge = _safe_divide(df["volume"], vol_ma)

    # Signed volume surge: positive on up days, negative on down days
    signed_surge = np.sign(ret) * vol_surge

    # Blend: rolling average of signed surge weighted by price trend
    trend = df.groupby(symbol_col)["close"].transform(
        lambda x: x.rolling(period, min_periods=5).mean()
    )
    trend_dir = np.sign(df["close"] - trend)

    raw = signed_surge * (1.0 + 0.5 * trend_dir)
    raw = raw.groupby(df[symbol_col]).rolling(
        period, min_periods=5
    ).mean().reset_index(level=0, drop=True)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_regime_conditional_momentum(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
    regime_window: int = 60,
) -> pd.Series:
    """Regime-conditional momentum: momentum scaled by regime filter.

    Category: Regime-conditional feature.

    Economic rationale: momentum works well in trending regimes
    (bull/bear) but fails in sideways/choppy regimes.  This signal
    detects the local regime using the ratio of trend to noise
    (R-squared of a linear fit over a window), then scales momentum
    up in trending regimes and down in choppy regimes.

    PIT: uses shift(1) — regime detection uses only lagged data.
    """
    ret = df.groupby(symbol_col)["close"].pct_change()
    mom = df.groupby(symbol_col)["close"].pct_change(period)

    # Trend strength proxy: abs(mean return) / std(return)
    # High ratio = trending; low ratio = choppy
    roll_mean = ret.groupby(df[symbol_col]).rolling(
        regime_window, min_periods=10
    ).mean().reset_index(level=0, drop=True)
    roll_std = ret.groupby(df[symbol_col]).rolling(
        regime_window, min_periods=10
    ).std().reset_index(level=0, drop=True)
    trend_strength = _safe_divide(roll_mean.abs(), roll_std)
    # Normalize to [0, 1] with a sigmoid-like transform
    regime_scale = 1.0 - np.exp(-2.0 * trend_strength)
    regime_scale = regime_scale.clip(0.0, 1.0)

    # Scale momentum by regime
    raw = mom * regime_scale
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_bid_ask_bounce_proxy(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 20,
) -> pd.Series:
    """Bid-ask bounce proxy: autocorrelation of close-to-open returns.

    Category: Intraday microstructure.

    Economic rationale: bid-ask bounce creates negative serial
    correlation in returns.  Stocks with high negative autocorrelation
    of intraday returns are likely experiencing more bounce (wider
    effective spread).  This signal uses close-to-open and
    open-to-close return alternation as a Roll (1984) proxy.

    PIT: uses shift(1).
    """
    prev_close = df.groupby(symbol_col)["close"].shift(1)
    co_ret = _safe_divide(df["open"] - prev_close, prev_close)  # close-to-open
    oc_ret = _safe_divide(df["close"] - df["open"], df["open"])  # open-to-close

    # Alternating return product (negative = bounce)
    alt_product = co_ret * oc_ret

    # Rolling mean: negative values indicate bounce
    raw = alt_product.groupby(df[symbol_col]).rolling(
        period, min_periods=5
    ).mean().reset_index(level=0, drop=True)
    # Negate so positive = more bounce (wider spread → mean-reversion opportunity)
    raw = -raw
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


def compute_volume_imbalance_pressure(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    period: int = 10,
) -> pd.Series:
    """Volume imbalance pressure: CLV-weighted volume accumulation.

    Category: Intraday microstructure / order flow proxy.

    Economic rationale: uses Close Location Value (CLV) to weight
    volume, creating a proxy for buy/sell pressure.  When CLV > 0
    (close in upper half), volume is attributed to buyers; when
    CLV < 0, volume is attributed to sellers.  The cumulative
    imbalance over a window signals institutional accumulation
    or distribution.

    PIT: uses shift(1).
    """
    hl_range = (df["high"] - df["low"]).replace(0, np.nan)
    clv = (2.0 * df["close"] - df["low"] - df["high"]) / hl_range
    clv = clv.fillna(0.0).clip(-1.0, 1.0)

    # Signed volume: positive when close is in upper half
    signed_vol = clv * df["volume"]

    # Rolling imbalance: net signed volume normalized by total volume
    roll_signed = signed_vol.groupby(df[symbol_col]).rolling(
        period, min_periods=3
    ).sum().reset_index(level=0, drop=True)
    roll_total = df["volume"].groupby(df[symbol_col]).rolling(
        period, min_periods=3
    ).sum().reset_index(level=0, drop=True)

    raw = _safe_divide(roll_signed, roll_total)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _pit_shift(raw, df[symbol_col])


# ---------------------------------------------------------------------------
# Orchestrator functions
# ---------------------------------------------------------------------------

def compute_all_hybrid_regime_alphas(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
) -> Dict[str, pd.Series]:
    """Compute all 7 v1 hybrid regime alpha signals.

    Returns a dict of {column_name: pd.Series}.
    """
    return {
        _VAM: compute_vol_adjusted_momentum(df, symbol_col=symbol_col),
        _VPP: compute_volume_price_pressure(df, symbol_col=symbol_col),
        _RPB: compute_range_position_breakout(df, symbol_col=symbol_col),
        _XDISP: compute_cross_sectional_dispersion(df, symbol_col=symbol_col),
        _LSR: compute_liquidity_shock_reversal(df, symbol_col=symbol_col),
        _VCE: compute_vol_compression_expansion(df, symbol_col=symbol_col),
        _SMD: compute_smart_money_divergence(df, symbol_col=symbol_col),
    }


def compute_all_hybrid_regime_v2_alphas(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
) -> Dict[str, pd.Series]:
    """Compute all 8 v2 expansion alpha signals.

    Returns a dict of {column_name: pd.Series}.
    """
    return {
        _OGR: compute_overnight_gap_return(df, symbol_col=symbol_col),
        _IRVR: compute_intraday_range_volume_ratio(
            df, symbol_col=symbol_col
        ),
        _SRS: compute_sector_relative_strength(
            df, symbol_col=symbol_col
        ),
        _SMS: compute_sector_momentum_spread(
            df, symbol_col=symbol_col
        ),
        _SPB: compute_sentiment_price_blend(
            df, symbol_col=symbol_col
        ),
        _RCM: compute_regime_conditional_momentum(
            df, symbol_col=symbol_col
        ),
        _BAB: compute_bid_ask_bounce_proxy(
            df, symbol_col=symbol_col
        ),
        _VIP: compute_volume_imbalance_pressure(
            df, symbol_col=symbol_col
        ),
    }


def compute_all_hybrid_regime_combined(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
) -> Dict[str, pd.Series]:
    """Compute all 15 hybrid regime alpha signals (v1 + v2).

    Returns a dict of {column_name: pd.Series}.
    """
    result = compute_all_hybrid_regime_alphas(df, symbol_col=symbol_col)
    result.update(
        compute_all_hybrid_regime_v2_alphas(df, symbol_col=symbol_col)
    )
    return result
