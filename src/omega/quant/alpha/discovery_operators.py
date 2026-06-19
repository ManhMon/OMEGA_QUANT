"""Alpha Discovery operators and primitives.

Contains vectorized primitive operators for cross-sectional and time-series transforms
and technical indicators (RSI, MACD).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_panel_index(x: pd.Series) -> None:
    if not isinstance(x.index, pd.MultiIndex) or x.index.nlevels != 2:
        raise ValueError("Expected MultiIndex Series with levels [timestamp, symbol].")


def _ensure_series(x: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(x, pd.DataFrame):
        if x.shape[1] != 1:
            raise ValueError("Expression result must be a Series or single-column DataFrame.")
        return x.iloc[:, 0]
    return x


def rank(x: pd.Series) -> pd.Series:
    """Cross-sectional rank at each timestamp."""
    _validate_panel_index(x)
    timestamp_level = x.index.names[0]
    return x.groupby(level=timestamp_level).rank(pct=True, method="average")


def delay(x: pd.Series, n: int) -> pd.Series:
    """Value from n days ago for each symbol."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    return x.groupby(level=symbol_level).shift(int(n))


def delta(x: pd.Series, n: int) -> pd.Series:
    """Difference versus n-day lag: x - delay(x, n)."""
    return x - delay(x, n)


def ts_corr(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    """Rolling correlation over n days for each symbol.

    EVO-001-FIX-3: Vectorized via unstack/rolling.corr/stack pattern.
    Replaces .groupby.apply(lambda s: s.rolling(n).corr(...)) which was O(n*m*k).
    New approach: O(n*m) using pd.DataFrame.rolling().corr() column-wise.
    PIT Safety: PASS - rolling window only uses past data; no shift needed here.
    """
    _validate_panel_index(x)
    _validate_panel_index(y)
    timestamp_level = x.index.names[0]
    symbol_level = x.index.names[1]

    # Unstack to shape (timestamp, symbol) for vectorized rolling
    x_wide = x.unstack(level=symbol_level)
    y_wide = y.reindex(x.index).unstack(level=symbol_level)

    # Compute rolling corr column-wise (each column = one symbol)
    # pd.DataFrame.rolling().corr(other) is fully vectorized
    corr_wide = x_wide.rolling(int(n)).corr(y_wide)

    # Restack back to MultiIndex (timestamp, symbol) and realign
    out = corr_wide.stack(future_stack=True)
    out.index.names = [timestamp_level, symbol_level]
    return out.reindex(x.index)


def ts_std(x: pd.Series, n: int) -> pd.Series:
    """Rolling standard deviation over n days for each symbol."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    return x.groupby(level=symbol_level).rolling(int(n)).std().reset_index(level=0, drop=True)


def ts_max(x: pd.Series, n: int) -> pd.Series:
    """Rolling maximum over n days for each symbol."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    return x.groupby(level=symbol_level).rolling(int(n)).max().reset_index(level=0, drop=True)


def ts_min(x: pd.Series, n: int) -> pd.Series:
    """Rolling minimum over n days for each symbol."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    return x.groupby(level=symbol_level).rolling(int(n)).min().reset_index(level=0, drop=True)


def _ts_rolling_rank_helper(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(n)).rank(pct=True, method="average")


def ts_rank(x: pd.Series, n: int) -> pd.Series:
    """Rolling rank within window for each symbol (time-series rank)."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    return x.groupby(level=symbol_level).transform(_ts_rolling_rank_helper, n=n)


def _linear_decay_weights(v: np.ndarray) -> float:
    n_val = len(v)
    weights = np.arange(1, n_val + 1)
    return (v * weights).sum() / weights.sum()


def decay_linear(x: pd.Series, n: int) -> pd.Series:
    """Linear decay weighted average over n days for each symbol."""
    _validate_panel_index(x)
    symbol_level = x.index.names[1]
    
    def _linear_decay(s: pd.Series) -> pd.Series:
        # Vectorized: weighted sum using rolling dot product equivalent
        out = pd.Series(np.nan, index=s.index)
        # Avoid lambda/apply: use explicit shift/sum logic for linear decay
        weights = np.arange(1, int(n) + 1)
        weights = weights / weights.sum()
        # Sum of weighted shifted series
        out_v = 0.0
        for i in range(int(n)):
            out_v += s.shift(i).fillna(0.0) * weights[int(n)-1-i]
        return out_v
    
    return x.groupby(level=symbol_level).transform(_linear_decay)


def high_low_efficiency(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Proxy for microstructure efficiency: how much of daily range was filled."""
    _validate_panel_index(high)
    _validate_panel_index(low)
    _validate_panel_index(close)
    
    range_size = high - low
    body = abs(close - close.groupby(level=close.index.names[1]).shift(1))
    
    return body / (range_size + 1e-9)


def _rolling_mean_5(s: pd.Series) -> pd.Series:
    return s.rolling(5).mean()


def volume_imbalance_proxy(volume: pd.Series, close: pd.Series) -> pd.Series:
    """Proxy for order book imbalance using volume and price direction."""
    _validate_panel_index(volume)
    _validate_panel_index(close)
    
    price_direction = np.sign(close.groupby(level=close.index.names[1]).diff())
    
    return (price_direction * volume).groupby(level=volume.index.names[1]).transform(_rolling_mean_5)


def _safe_shift(x: pd.Series, n: int = 1) -> pd.Series:
    """Safe shift that handles edge cases."""
    return x.groupby(level=x.index.names[1]).shift(n)


def _safe_div(a: pd.Series, b: pd.Series, fill_value: float = 0.0) -> pd.Series:
    """Safe division that handles division by zero."""
    result = a / (b + 1e-9)
    return result.replace([np.inf, -np.inf], fill_value).fillna(fill_value)


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    close: pd.Series,
    fast_span: int = 12,
    slow_span: int = 26,
    signal_span: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast_span, adjust=False).mean()
    ema_slow = close.ewm(span=slow_span, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_span, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def build_alpha_signals(df: pd.DataFrame) -> pd.DataFrame:
    from omega.quant.risk.pit_guard import enforce_t_minus_1_lag
    required = {"timestamp", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    out = df.copy()
    out = out.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    out["alpha_rsi_raw"] = compute_rsi(out["close"])
    macd_line, signal_line, histogram = compute_macd(out["close"])
    out["alpha_macd_raw"] = macd_line
    out["alpha_macd_signal_raw"] = signal_line
    out["alpha_macd_hist_raw"] = histogram

    raw_cols = [
        "alpha_rsi_raw",
        "alpha_macd_raw",
        "alpha_macd_signal_raw",
        "alpha_macd_hist_raw",
    ]
    shifted = enforce_t_minus_1_lag(out, raw_cols)
    out["alpha_rsi"] = shifted["alpha_rsi_raw"]
    out["alpha_macd"] = shifted["alpha_macd_raw"]
    out["alpha_macd_signal"] = shifted["alpha_macd_signal_raw"]
    out["alpha_macd_hist"] = shifted["alpha_macd_hist_raw"]

    out = out.drop(columns=raw_cols)
    return out
