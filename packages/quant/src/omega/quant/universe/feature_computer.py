"""Universe Feature Computer - PIT-safe feature engineering for stock universe."""
from __future__ import annotations

import logging
from typing import ClassVar

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EPS = 1e-9


class UniverseFeatureComputer:
    """Compute PIT-safe features for stock universe selection.

    Features (15 total):
      Momentum (4): mom_5d, mom_20d, mom_60d, mom_252d
      Volume (3): adv_30d, vol_surge, dollar_vol
      Volatility (3): vol_20d, vol_60d, vol_ratio
      Trend (3): above_ma50, above_ma200, ma50_slope
      Position (1): near_52w_high
      Liquidity (1): liq_rank

    PIT guarantee: only data with date < as_of_date is used.
    """

    FEATURE_COLS: ClassVar[list[str]] = [
        "mom_5d", "mom_20d", "mom_60d", "mom_252d",
        "adv_30d", "vol_surge", "dollar_vol",
        "vol_20d", "vol_60d", "vol_ratio",
        "above_ma50", "above_ma200", "ma50_slope",
        "near_52w_high", "liq_rank",
    ]

    # M3: per-column fillna defaults (semantically meaningful, not blanket 0).
    _FILL_DEFAULTS: ClassVar[dict[str, float]] = {
        "mom_5d": 0.0, "mom_20d": 0.0, "mom_60d": 0.0, "mom_252d": 0.0,
        "adv_30d": 0.0, "vol_surge": 0.0, "dollar_vol": 0.0,
        "vol_20d": 0.0, "vol_60d": 0.0, "vol_ratio": 0.0,
        "above_ma50": 0.0, "above_ma200": 0.0, "ma50_slope": 0.0,
        "near_52w_high": 1.0,  # default = at 52w high (not a negative signal)
        "liq_rank": 0.5,       # default = median rank (neutral)
    }

    def compute(self, df: pd.DataFrame, as_of_date: pd.Timestamp) -> pd.DataFrame:
        """Compute features as of ``as_of_date`` (exclusive).

        Args:
            df: DataFrame with columns [ticker, date, close, volume].
            as_of_date: cutoff timestamp; only data with date < as_of_date is used.

        Returns:
            DataFrame indexed by ticker with FEATURE_COLS columns.

        Raises:
            ValueError: if required input columns are missing.
        """
        if df is None or df.empty:
            logger.warning("Empty input dataframe; returning empty result.")
            return pd.DataFrame(columns=self.FEATURE_COLS)

        # H2: explicit column validation + datetime coercion.
        required = {"ticker", "date", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        as_of_date = pd.Timestamp(as_of_date)

        # PIT guard: strictly before as_of_date (no look-ahead).
        df = df[df["date"] < as_of_date]
        if df.empty:
            logger.warning("No data before as_of_date=%s; returning empty result.", as_of_date)
            return pd.DataFrame(columns=self.FEATURE_COLS)

        df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

        # M1: single groupby reused for every ticker-scoped feature.
        g = df.groupby("ticker", group_keys=False)

        # Momentum (4)
        df["mom_5d"] = g["close"].pct_change(5)
        df["mom_20d"] = g["close"].pct_change(20)
        df["mom_60d"] = g["close"].pct_change(60)
        df["mom_252d"] = g["close"].pct_change(252)

        # Volume (3) — H1: dead placeholder removed.
        df["adv_30d"] = g["volume"].transform(
            lambda x: x.rolling(30, min_periods=1).mean()
        )
        df["vol_surge"] = g["volume"].transform(
            lambda x: x.rolling(5, min_periods=1).mean()
            / (x.rolling(60, min_periods=1).mean() + 1.0)
        )
        df["dollar_vol"] = df["close"] * df["adv_30d"]

        # Volatility (3)
        df["ret_1d"] = g["close"].pct_change(1)
        df["vol_20d"] = g["ret_1d"].transform(
            lambda x: x.rolling(20, min_periods=2).std() * np.sqrt(252)
        )
        df["vol_60d"] = g["ret_1d"].transform(
            lambda x: x.rolling(60, min_periods=2).std() * np.sqrt(252)
        )
        df["vol_ratio"] = df["vol_20d"] / (df["vol_60d"] + EPS)

        # Trend (3)
        df["ma_50"] = g["close"].transform(
            lambda x: x.rolling(50, min_periods=1).mean()
        )
        df["ma_200"] = g["close"].transform(
            lambda x: x.rolling(200, min_periods=1).mean()
        )
        df["above_ma50"] = (df["close"] > df["ma_50"]).astype(int)
        df["above_ma200"] = (df["close"] > df["ma_200"]).astype(int)
        df["ma50_slope"] = g["ma_50"].pct_change(20)

        # Position (1) - 52-week high
        df["high_252d"] = g["close"].transform(
            lambda x: x.rolling(252, min_periods=1).max()
        )
        df["near_52w_high"] = df["close"] / (df["high_252d"] + EPS)

        # Liquidity (1) - cross-sectional rank by date (date-groupby, not ticker).
        df["liq_rank"] = df.groupby("date")["adv_30d"].rank(pct=True)

        # Latest snapshot per ticker.
        latest = g.tail(1)
        result = latest.set_index("ticker")[self.FEATURE_COLS].copy()

        # M3: per-column fillna defaults (replaces blanket fillna(0.0)).
        result = result.fillna(self._FILL_DEFAULTS)

        # M2: vectorized winsorize at 1%/99% (single pass, no per-column loop).
        q = result.quantile([0.01, 0.99])
        result = result.clip(lower=q.loc[0.01], upper=q.loc[0.99], axis=1)

        logger.info(
            "Computed %d features for %d tickers as_of=%s",
            len(self.FEATURE_COLS), len(result), as_of_date.date(),
        )
        return result
