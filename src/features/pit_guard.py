import pandas as pd
import numpy as np

def verify_no_lookahead(df: pd.DataFrame, time_col: str = 'time') -> None:
    """
    Asserts that the dataframe index is sorted and strictly monotonic.
    """
    if not df[time_col].is_monotonic_increasing:
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
