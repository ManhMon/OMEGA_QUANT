"""Internal deterministic market-breadth calculations."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

_SYMBOL = re.compile(r"^[A-Z0-9]{1,16}$")


class MarketBreadthAggregator:
    """Compute breadth from a date-indexed close-price frame."""

    def calculate(self, prices: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(prices, pd.DataFrame) or prices.empty:
            return pd.DataFrame(columns=["date", "advance", "decline", "ad_ratio", "ad_line", "mcclellan_oscillator", "above_ma20", "above_ma50", "above_ma200"])
        if "date" not in prices.columns:
            raise ValueError("prices requires date column")
        symbols = [c for c in prices.columns if c != "date"]
        if not symbols:
            raise ValueError("prices requires at least one symbol")
        frame = prices.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="raise", utc=True)
        if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
            raise ValueError("prices dates must be unique and monotonically increasing")
        if any(not _SYMBOL.fullmatch(str(symbol).strip().upper()) for symbol in symbols):
            raise ValueError("prices contains invalid symbol column")
        try:
            close = frame[symbols].apply(pd.to_numeric, errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError("prices contains non-numeric values") from exc
        if close.isna().any().any() or not close.gt(0).all().all():
            raise ValueError("prices contains non-positive or missing values")
        changes = close.diff()
        result = pd.DataFrame({"date": frame["date"], "advance": changes.gt(0).sum(axis=1), "decline": changes.lt(0).sum(axis=1)})
        result["ad_ratio"] = result["advance"] / result["decline"].replace(0, 1)
        net_advances = result["advance"] - result["decline"]
        result["ad_line"] = net_advances.cumsum()
        result["mcclellan_oscillator"] = net_advances.ewm(span=19, adjust=False).mean() - net_advances.ewm(span=39, adjust=False).mean()
        for window in (20, 50, 200):
            result[f"above_ma{window}"] = close.gt(close.rolling(window, min_periods=1).mean()).mean(axis=1).clip(0, 1)
        return result.replace([math.inf, -math.inf], 0).fillna(0)
