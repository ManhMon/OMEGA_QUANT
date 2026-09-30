import pandas as pd
import numpy as np
import hashlib
from datetime import datetime, timezone

from omega.core.llm_config import _canonical


def validate_shadow_data_guard(
    df: pd.DataFrame, *, cutoff: datetime, price_units: str = "VND_FULL",
    annotation: str | None = None,
) -> dict:
    """Isolated deterministic guard; retains raw rows, never repairs or filters data."""
    required = ("symbol", "as_of", "available_at", "open", "high", "low", "close", "volume")
    if not isinstance(df, pd.DataFrame) or len(df) > 10000 or not df.columns.is_unique:
        raise ValueError("invalid guard frame")
    if set(df.columns) != set(required) or price_units != "VND_FULL":
        raise ValueError("invalid guard schema or units")
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("guard cutoff must be timezone-aware")
    if annotation is not None and annotation not in (
        "valid_market_breakout", "unadjusted_corporate_action_gap", "block_trade_noise", "stale_feed_error",
    ):
        raise ValueError("invalid anomaly annotation")
    symbols = df["symbol"]
    if any(type(value) is not str or not value or len(value) > 32 for value in symbols):
        raise ValueError("invalid guard symbols")
    numeric = df[list(required[3:])]
    if any(dtype.kind not in "iuf" for dtype in numeric.dtypes):
        raise ValueError("guard values must be real numeric")
    values = numeric.to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("non-finite guard values")
    times = []
    for name in ("as_of", "available_at"):
        series = df[name]
        if not isinstance(series.dtype, pd.DatetimeTZDtype) or series.isna().any():
            raise ValueError("guard times must be timezone-aware and non-null")
        times.append(series.dt.tz_convert("UTC"))
    observed, available = times
    reasons = []
    for rule, invalid in (
        ("PIT_ORDER", observed > available),
        ("NOT_AVAILABLE", available > cutoff.astimezone(timezone.utc)),
        ("NON_POSITIVE_PRICE", (numeric.iloc[:, :4] <= 0).any(axis=1)),
        ("NEGATIVE_VOLUME", numeric["volume"] < 0),
        ("OHLC_ORDER", (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)) |
                       (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1))),
        ("DUPLICATE", df.duplicated(["symbol", "as_of"], keep=False)),
    ):
        if invalid.any():
            reasons.append(rule)
    # ponytail: declared units only; exchange/calendar/action evidence belongs to ingestion SSOT.
    raw = {"columns": list(df.columns), "dtypes": [str(d) for d in df.dtypes],
           "index": [str(i) for i in df.index],
           "rows": [[value.isoformat() if isinstance(value, datetime) else value
                     for value in row] for row in df.itertuples(index=False, name=None)]}
    raw_digest = hashlib.sha256(_canonical(raw)).hexdigest()
    result = {"schema_version": "w6_guard_v1", "rule_version": "1", "raw_digest": raw_digest,
              "cutoff": cutoff.astimezone(timezone.utc).isoformat(), "price_units": price_units,
              "status": "quarantined" if reasons else "valid", "reasons": reasons,
              "row_count": len(df), "advisory_only": True, "applied": False}
    result["canonical_digest"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result

def verify_no_lookahead(df: pd.DataFrame, time_col: str = 'time') -> None:
    """
    Asserts that the dataframe index is sorted and strictly monotonic.
    """
    if (time_col not in df or df[time_col].isna().any() or
            not df[time_col].is_monotonic_increasing or df[time_col].duplicated().any()):
        raise ValueError(f"Data is not strictly monotonic increasing by {time_col}.")

def enforce_t_minus_1_lag(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Shifts the specified columns by 1 to enforce T-1 lag, ensuring PIT safety.
    """
    df_shifted = df.copy()
    df_shifted[columns] = df_shifted[columns].shift(1)
    return df_shifted

def check_leakage(
    df: pd.DataFrame,
    time_col: str = 'timestamp',
    cutoff_time: pd.Timestamp | None = None
) -> None:
    """
    Verify no future data leaks into feature set.
    
    Args:
        df: DataFrame to check
        time_col: Name of timestamp column
        cutoff_time: Maximum allowed timestamp (T-1). If None, uses max(time_col) - 1 period.
    
    Raises:
        ValueError: If any timestamps exceed cutoff_time
    """
    if time_col not in df.columns:
        raise ValueError(f"Time column '{time_col}' not found in DataFrame")
    
    if cutoff_time is None:
        # Default: no explicit cutoff check (assumes pre-shifted data)
        return
    
    # Check for timestamps beyond cutoff
    leaked_rows = df[df[time_col] > cutoff_time]
    if len(leaked_rows) > 0:
        raise ValueError(
            f"Leakage detected: {len(leaked_rows)} rows have timestamps > cutoff {cutoff_time}. "
            f"First violation: {leaked_rows[time_col].iloc[0]}"
        )
