from __future__ import annotations

import pandas as pd

from src.features.pit_guard import verify_no_lookahead
from src.indicators.alpha_discovery import build_alpha_signals


def run_alpha_discovery_pipeline(price_df: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "close"}
    missing = required.difference(price_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = price_df.copy()
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    verify_no_lookahead(df, time_col="timestamp")

    features = build_alpha_signals(df)

    ordered_cols = [
        "timestamp",
        "close",
        "alpha_rsi",
        "alpha_macd",
        "alpha_macd_signal",
        "alpha_macd_hist",
    ]
    features = features.loc[:, ordered_cols]

    return features
