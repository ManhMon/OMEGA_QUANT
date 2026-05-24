from __future__ import annotations

import pandas as pd

from src.features.pit_guard import enforce_t_minus_1_lag


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
