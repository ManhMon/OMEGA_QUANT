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
        "mom_10d", "mom_120d",
        "vol_10d", "vol_120d",
        "adv_10d", "adv_120d",
        "close_to_ma50", "close_to_ma200", "ma50_to_ma200",
        "volume_momentum_5d", "volume_momentum_20d",
        "vol_surge_30d", "ret_std_5d", "dollar_vol_ratio",
        "near_52w_low", "max_ret_5d", "min_ret_5d",
        "hl_spread_20d", "volume_std_20d", "price_rank",
    ]

    # M3: per-column fillna defaults (semantically meaningful, not blanket 0).
    _FILL_DEFAULTS: ClassVar[dict[str, float]] = {
        "mom_5d": 0.0, "mom_20d": 0.0, "mom_60d": 0.0, "mom_252d": 0.0,
        "adv_30d": 0.0, "vol_surge": 0.0, "dollar_vol": 0.0,
        "vol_20d": 0.0, "vol_60d": 0.0, "vol_ratio": 0.0,
        "above_ma50": 0.0, "above_ma200": 0.0, "ma50_slope": 0.0,
        "near_52w_high": 1.0,  # default = at 52w high (not a negative signal)
        "liq_rank": 0.5,       # default = median rank (neutral)
        "mom_10d": 0.0, "mom_120d": 0.0,
        "vol_10d": 0.0, "vol_120d": 0.0,
        "adv_10d": 0.0, "adv_120d": 0.0,
        "close_to_ma50": 0.0, "close_to_ma200": 0.0, "ma50_to_ma200": 0.0,
        "volume_momentum_5d": 0.0, "volume_momentum_20d": 0.0,
        "vol_surge_30d": 0.0, "ret_std_5d": 0.0, "dollar_vol_ratio": 1.0,
        "near_52w_low": 1.0, "max_ret_5d": 0.0, "min_ret_5d": 0.0,
        "hl_spread_20d": 0.0, "volume_std_20d": 0.0, "price_rank": 0.5,
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

        # 20 Alternative/New features with strict T-1 shift:
        df["mom_10d"] = g["close"].transform(lambda x: x.pct_change(10).shift(1))
        df["mom_120d"] = g["close"].transform(lambda x: x.pct_change(120).shift(1))

        df["vol_10d"] = g["ret_1d"].transform(
            lambda x: x.rolling(10, min_periods=2).std().shift(1) * np.sqrt(252)
        )
        df["vol_120d"] = g["ret_1d"].transform(
            lambda x: x.rolling(120, min_periods=2).std().shift(1) * np.sqrt(252)
        )

        df["adv_10d"] = g["volume"].transform(
            lambda x: x.rolling(10, min_periods=1).mean().shift(1)
        )
        df["adv_120d"] = g["volume"].transform(
            lambda x: x.rolling(120, min_periods=1).mean().shift(1)
        )

        # Trend / MA relations (shifted)
        df["close_to_ma50_raw"] = df["close"] / (df["ma_50"] + EPS) - 1.0
        df["close_to_ma50"] = g["close_to_ma50_raw"].shift(1)

        df["close_to_ma200_raw"] = df["close"] / (df["ma_200"] + EPS) - 1.0
        df["close_to_ma200"] = g["close_to_ma200_raw"].shift(1)

        df["ma50_to_ma200_raw"] = df["ma_50"] / (df["ma_200"] + EPS) - 1.0
        df["ma50_to_ma200"] = g["ma50_to_ma200_raw"].shift(1)

        # Volume momentum & surge (shifted)
        df["volume_momentum_5d"] = g["volume"].transform(
            lambda x: x.pct_change(5).shift(1)
        )
        df["volume_momentum_20d"] = g["volume"].transform(
            lambda x: x.pct_change(20).shift(1)
        )

        df["vol_surge_30d"] = g["volume"].transform(
            lambda x: (
                x.rolling(5, min_periods=1).mean()
                / (x.rolling(30, min_periods=1).mean() + 1.0)
            ).shift(1)
        )

        # Return volatility metrics (shifted)
        df["ret_std_5d"] = g["ret_1d"].transform(
            lambda x: x.rolling(5, min_periods=2).std().shift(1)
        )

        # Dollar Volume ratio (shifted)
        df["dollar_vol_raw"] = df["close"] * df["volume"]
        df["dollar_vol_5d"] = g["dollar_vol_raw"].transform(
            lambda x: x.rolling(5, min_periods=1).mean()
        )
        df["dollar_vol_20d"] = g["dollar_vol_raw"].transform(
            lambda x: x.rolling(20, min_periods=1).mean()
        )
        df["dollar_vol_ratio_raw"] = df["dollar_vol_5d"] / (df["dollar_vol_20d"] + EPS)
        df["dollar_vol_ratio"] = g["dollar_vol_ratio_raw"].shift(1)

        # 52w low (shifted)
        df["low_252d"] = g["close"].transform(
            lambda x: x.rolling(252, min_periods=1).min()
        )
        df["near_52w_low_raw"] = df["close"] / (df["low_252d"] + EPS)
        df["near_52w_low"] = g["near_52w_low_raw"].shift(1)

        # Min/Max return over window (shifted)
        df["max_ret_5d"] = g["ret_1d"].transform(
            lambda x: x.rolling(5, min_periods=1).max().shift(1)
        )
        df["min_ret_5d"] = g["ret_1d"].transform(
            lambda x: x.rolling(5, min_periods=1).min().shift(1)
        )

        # HL spread (shifted)
        df["close_max_20d"] = g["close"].transform(
            lambda x: x.rolling(20, min_periods=1).max()
        )
        df["close_min_20d"] = g["close"].transform(
            lambda x: x.rolling(20, min_periods=1).min()
        )
        df["close_mean_20d"] = g["close"].transform(
            lambda x: x.rolling(20, min_periods=1).mean()
        )
        df["hl_spread_20d_raw"] = (df["close_max_20d"] - df["close_min_20d"]) / (df["close_mean_20d"] + EPS)
        df["hl_spread_20d"] = g["hl_spread_20d_raw"].shift(1)

        # Volume std (shifted)
        df["volume_std_20d"] = g["volume"].transform(
            lambda x: x.rolling(20, min_periods=2).std().shift(1)
        )

        # Cross-sectional price rank (shifted)
        df["price_rank_pct"] = df.groupby("date")["close"].rank(pct=True)
        df["price_rank"] = g["price_rank_pct"].shift(1)

        # Latest snapshot per ticker.
        latest = g.tail(1)
        result = latest.set_index("ticker")[self.FEATURE_COLS].copy()

        # Replace infinite values with NaN before filling defaults.
        result = result.replace([np.inf, -np.inf], np.nan)

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
