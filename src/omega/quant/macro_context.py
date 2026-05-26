"""
Layer 01 macro context features for VN equities.

This module derives slow-moving macro indicators from a daily macro frame.
All rolling statistics are shifted by one period to preserve point-in-time
correctness when the features are used on the current date.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _pick_column(frame: pd.DataFrame, candidates: Iterable[str], feature_name: str) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    available = ", ".join(frame.columns.astype(str))
    raise ValueError(
        f"Missing source column for {feature_name}. "
        f"Expected one of {list(candidates)}, available columns: [{available}]"
    )


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    shifted = series.shift(1)
    mean = shifted.rolling(window=window, min_periods=max(20, window // 3)).mean()
    std = shifted.rolling(window=window, min_periods=max(20, window // 3)).std()
    return (shifted - mean) / std.replace(0, np.nan)


def get_macro_indicators(macro_frame: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    Build point-in-time macro indicators for the VN market.

    Required inputs are resolved by alias to avoid coupling this utility to a
    single vendor schema.

    Output columns:
    - ``usd_vnd_zscore``: z-score of USD/VND FX level stress.
    - ``gold_vn_ratio``: SJC gold price divided by the VN-Index level.
    - ``bond_stress_idx``: z-score of corporate bond stress. When direct
      corporate-credit data is unavailable, this falls back to the spread
      between the VN 10Y yield and the policy rate as a proxy for systemic
      credit stress.
    """
    if not isinstance(macro_frame, pd.DataFrame):
        raise TypeError("macro_frame must be a pandas DataFrame")
    if macro_frame.empty:
        return pd.DataFrame(index=macro_frame.index)
    if window < 20:
        raise ValueError("window must be at least 20 trading days")

    frame = macro_frame.sort_index().copy()
    result = pd.DataFrame(index=frame.index)

    usd_vnd_col = _pick_column(
        frame,
        ["usd_vnd", "usd_vnd_rate", "fx_usd_vnd", "usdvnd", "USDVND"],
        "usd_vnd_zscore",
    )
    vn_gold_col = _pick_column(
        frame,
        ["gold_vn", "gold_vn_price", "sjc_gold", "vn_gold_price"],
        "gold_vn_ratio",
    )
    vn_index_col = _pick_column(
        frame,
        ["vn_index", "vnindex", "vn_index_level", "vni", "VNINDEX"],
        "gold_vn_ratio",
    )
    corporate_spread_candidates = [
        "corp_bond_stress",
        "corp_credit_spread",
        "corporate_bond_spread",
        "corporate_credit_spread",
        "corp_ig_aaa_spread",
        "vn_corp_bond_spread",
        "credit_spread",
    ]
    corporate_level_candidates = [
        "corp_bond_yield",
        "corporate_bond_yield",
        "vn_corp_bond_yield",
    ]
    bond_stress_series: pd.Series | None = None

    for candidate in corporate_spread_candidates:
        if candidate in frame.columns:
            bond_stress_series = frame[candidate].astype(float)
            break

    if bond_stress_series is None:
        corporate_yield_col = next(
            (candidate for candidate in corporate_level_candidates if candidate in frame.columns),
            None,
        )
        if corporate_yield_col is not None:
            short_rate_col = _pick_column(
                frame,
                ["policy_rate", "interbank_overnight", "short_rate", "vn_1m_rate"],
                "bond_stress_idx",
            )
            bond_stress_series = (
                frame[corporate_yield_col].astype(float) - frame[short_rate_col].astype(float)
            )

    if bond_stress_series is None:
        bond_10y_col = _pick_column(
            frame,
            ["vn10y_yield", "bond_10y", "gov_bond_10y", "vn_bond_10y_yield"],
            "bond_stress_idx",
        )
        short_rate_col = _pick_column(
            frame,
            ["policy_rate", "interbank_overnight", "short_rate", "vn_1m_rate"],
            "bond_stress_idx",
        )
        bond_stress_series = frame[bond_10y_col].astype(float) - frame[short_rate_col].astype(float)

    result["usd_vnd_zscore"] = _rolling_zscore(frame[usd_vnd_col].astype(float), window=window)

    result["gold_vn_ratio"] = frame[vn_gold_col].astype(float).shift(1) / frame[vn_index_col].astype(float).shift(1).replace(0, np.nan)

    result["bond_stress_idx"] = _rolling_zscore(bond_stress_series, window=window)

    return result
