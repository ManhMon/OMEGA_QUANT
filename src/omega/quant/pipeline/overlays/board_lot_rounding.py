"""Board lot rounding overlay - convert weights to board-lot share quantities.

Gate: UNIFIED_SYSTEM_INTEGRATION_20260619

Converts fractional portfolio weights into integer board-lot (100 shares)
quantities using T-1 close prices to eliminate look-ahead bias from
same-day closing prices.

PIT Safety: Uses ONLY T-1 close prices for share count calculation.
The close price on day T is NOT available at the time of order placement.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class BoardLotRoundingOverlay(WeightOverlay):
    """Round portfolio weights to board-lot share quantities using T-1 close.

    Parameters
    ----------
    lot_size : int
        Board lot size (default 100 shares for HOSE).
    capital_vnd : float
        Total portfolio capital in VND (default 1e9).
    price_source_col : str
        Column name for price in panel (default 'close').
    """

    def __init__(
        self,
        lot_size: int = 100,
        capital_vnd: float = 1e9,
        price_source_col: str = "close",
    ):
        self.lot_size = lot_size
        self.capital_vnd = capital_vnd
        self.price_source_col = price_source_col

    def apply(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        if self.price_source_col not in panel_flat.columns:
            logger.warning("BoardLotRoundingOverlay: price column '%s' not found, returning weights unchanged.", self.price_source_col)
            return weights

        price_pivot = panel_flat.pivot_table(
            index="date", columns="symbol", values=self.price_source_col
        )
        price_pivot = price_pivot.sort_index()

        # T-1 shift: use PRIOR day's close price for lot calculation (PIT-safe)
        prices_t_minus_1 = price_pivot.shift(1)
        prices_t_minus_1 = prices_t_minus_1.reindex(
            index=weights.index, columns=weights.columns, fill_value=0.0
        )

        result = weights.copy()

        for dt in result.index:
            row = result.loc[dt]
            prices = prices_t_minus_1.loc[dt]

            for sym in row.index:
                w = row[sym]
                p = prices.get(sym, 0.0)
                # Handle NaN or zero prices (e.g., first day with no T-1 data)
                if pd.isna(p) or p <= 0:
                    result.loc[dt, sym] = 0.0
                    continue
                if abs(w) < 1e-8:
                    result.loc[dt, sym] = 0.0
                    continue

                # Scale price to VND if needed (raw unit prices < 1000 assumed to be in 1000 VND)
                if p < 1000.0:
                    p = p * 1000.0

                raw_shares = (abs(w) * self.capital_vnd) / p
                lots = int(round(raw_shares / self.lot_size))
                shares = lots * self.lot_size

                if shares >= self.lot_size:
                    real_value = shares * p
                    real_w = np.sign(w) * real_value / self.capital_vnd
                    result.loc[dt, sym] = real_w
                else:
                    result.loc[dt, sym] = 0.0

        return result
