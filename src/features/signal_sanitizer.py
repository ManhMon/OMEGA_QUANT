from __future__ import annotations

import pandas as pd


SIGNAL_COLUMNS = [
    "signal_mean_reversion",
    "signal_momentum",
    "signal_trend",
]


def validate_monotonic_time(df: pd.DataFrame, time_col: str = "timestamp") -> None:
    if time_col not in df.columns:
        raise ValueError(f"Time column '{time_col}' not found in DataFrame")
    if not df[time_col].is_monotonic_increasing:
        raise ValueError(f"Data is not strictly monotonic increasing by {time_col}.")
    if df[time_col].duplicated().any():
        raise ValueError(f"Data contains duplicate timestamps in {time_col}; strict monotonicity required.")


def enforce_t_minus_1_lag(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    result[columns] = result[columns].shift(1)
    return result


def validate_t_minus_1_lag(
    df: pd.DataFrame,
    columns: list[str],
    source_df: pd.DataFrame | None = None,
    time_col: str = "timestamp",
) -> None:
    if source_df is not None:
        validate_monotonic_time(source_df, time_col=time_col)

    if source_df is not None and len(df.index) != len(source_df.index):
        raise ValueError("PIT validation requires source and sanitized frames to have identical row counts")

    if source_df is not None:
        if time_col not in df.columns:
            raise ValueError(f"Time column '{time_col}' not found in DataFrame")
        if time_col not in source_df.columns:
            raise ValueError(f"Time column '{time_col}' not found in source DataFrame")

        timestamp_mismatch = ~df[time_col].eq(source_df[time_col])
        if timestamp_mismatch.any():
            first_bad_index = timestamp_mismatch[timestamp_mismatch].index[0]
            raise ValueError(
                f"PIT violation: timestamp at row {first_bad_index} does not match source frame exactly"
            )

    for column in columns:
        if column not in df.columns:
            raise ValueError(f"Signal column '{column}' not found in DataFrame")
        if len(df.index) > 0 and not pd.isna(df[column].iloc[0]):
            raise ValueError(f"PIT violation: column '{column}' must be T-1 lagged")

        if source_df is None:
            continue
        if column not in source_df.columns:
            raise ValueError(f"Signal column '{column}' not found in source DataFrame")

        expected = source_df[column].shift(1)
        actual = df[column]
        mismatch = ~(
            (actual.isna() & expected.isna())
            | actual.eq(expected)
        )
        if mismatch.any():
            first_bad_index = mismatch[mismatch].index[0]
            raise ValueError(
                f"PIT violation: column '{column}' at row {first_bad_index} does not match exact T-1 source value"
            )
def sanitize_signals(
    df: pd.DataFrame,
    signal_columns: list[str] | None = None,
    time_col: str = "timestamp",
    apply_lag: bool = False,
    source_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    signal_columns = signal_columns or SIGNAL_COLUMNS
    validate_monotonic_time(df, time_col=time_col)

    if not apply_lag:
        if source_df is None:
            raise ValueError("apply_lag=False is unsafe without source_df for absolute T-1 validation")
        validate_monotonic_time(source_df, time_col=time_col)

    result = enforce_t_minus_1_lag(df, signal_columns) if apply_lag else df.copy()
    validate_t_minus_1_lag(result, signal_columns, source_df=df if apply_lag else source_df, time_col=time_col)
    return result
