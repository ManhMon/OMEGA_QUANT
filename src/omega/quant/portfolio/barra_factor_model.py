from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


STYLE_FACTOR_COLUMNS = ["size", "value", "momentum", "volatility", "liquidity"]


@dataclass(frozen=True)
class BarraFactorConfig:
    momentum_lookback: int = 252
    momentum_skip: int = 21
    volatility_lookback: int = 60
    liquidity_lookback: int = 20
    book_value_lag_days: int = 90
    winsor_limits: tuple[float, float] = (0.01, 0.99)


def _winsorize_and_zscore(values: pd.Series, limits: tuple[float, float]) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(0.0, index=values.index, dtype=float)
    lower = valid.quantile(limits[0])
    upper = valid.quantile(limits[1])
    clipped = numeric.clip(lower=lower, upper=upper)
    mean = clipped.mean()
    std = clipped.std(ddof=0)
    if not np.isfinite(std) or std <= 0:
        return pd.Series(0.0, index=values.index, dtype=float)
    z = (clipped - mean) / std
    return z.fillna(0.0)


def _require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


class BarraFactorModel:
    def __init__(self, config: BarraFactorConfig | None = None) -> None:
        self.config = config or BarraFactorConfig()

    def build_exposure_matrix(self, market_data: pd.DataFrame, as_of_date: pd.Timestamp | str) -> pd.DataFrame:
        _require_columns(
            market_data,
            {"date", "symbol", "close", "volume", "market_cap", "sector", "book_value", "period_end"},
        )
        as_of = pd.Timestamp(as_of_date)
        snapshot_date = as_of - pd.Timedelta(days=1)
        if market_data.empty:
            return pd.DataFrame(columns=STYLE_FACTOR_COLUMNS)

        data = market_data.copy()
        data["date"] = pd.to_datetime(data["date"])
        data["period_end"] = pd.to_datetime(data["period_end"])
        default_available_at = data["period_end"] + pd.to_timedelta(self.config.book_value_lag_days, unit="D")
        if "available_at" in data.columns:
            data["available_at"] = pd.to_datetime(data["available_at"]).fillna(default_available_at)
        else:
            data["available_at"] = default_available_at

        history = data.loc[data["date"] <= snapshot_date].sort_values(["symbol", "date"])
        if history.empty:
            return pd.DataFrame(columns=STYLE_FACTOR_COLUMNS)

        latest = history.groupby("symbol", sort=False).tail(1).set_index("symbol")
        close_history = history.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
        returns_history = close_history.pct_change()
        volume_history = history.pivot_table(index="date", columns="symbol", values="volume", aggfunc="last").sort_index()
        market_cap_history = history.pivot_table(index="date", columns="symbol", values="market_cap", aggfunc="last").sort_index()

        momentum = self._compute_momentum(close_history)
        volatility = self._compute_volatility(returns_history)
        liquidity = self._compute_liquidity(close_history, volume_history, market_cap_history)
        value = self._compute_value(data, latest.index, snapshot_date, latest["close"])

        exposures = pd.DataFrame(index=latest.index)
        exposures["size"] = np.log(latest["market_cap"].where(latest["market_cap"] > 0))
        exposures["value"] = value.reindex(exposures.index)
        exposures["momentum"] = momentum.reindex(exposures.index)
        exposures["volatility"] = volatility.reindex(exposures.index)
        exposures["liquidity"] = liquidity.reindex(exposures.index)

        for column in STYLE_FACTOR_COLUMNS:
            exposures[column] = _winsorize_and_zscore(exposures[column], self.config.winsor_limits)

        sector_dummies = pd.get_dummies(latest["sector"].fillna("Other"), prefix="industry", dtype=float)
        if not sector_dummies.empty:
            sector_dummies = sector_dummies - sector_dummies.mean(axis=0)
        sector_dummies.index = latest.index
        return pd.concat([exposures.fillna(0.0), sector_dummies], axis=1).sort_index(axis=1)

    def _compute_momentum(self, close_history: pd.DataFrame) -> pd.Series:
        if len(close_history.index) <= self.config.momentum_skip:
            return pd.Series(0.0, index=close_history.columns, dtype=float)
        long_leg = close_history.pct_change(self.config.momentum_lookback)
        short_leg = close_history.pct_change(self.config.momentum_skip)
        signal = long_leg.iloc[-1] - short_leg.iloc[-1]
        return signal.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _compute_volatility(self, returns_history: pd.DataFrame) -> pd.Series:
        window = min(self.config.volatility_lookback, len(returns_history.index))
        if window <= 1:
            return pd.Series(0.0, index=returns_history.columns, dtype=float)
        signal = returns_history.tail(window).std(ddof=0)
        return signal.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _compute_liquidity(
        self,
        close_history: pd.DataFrame,
        volume_history: pd.DataFrame,
        market_cap_history: pd.DataFrame,
    ) -> pd.Series:
        adv_window = min(self.config.liquidity_lookback, len(close_history.index))
        if adv_window <= 0:
            return pd.Series(0.0, index=close_history.columns, dtype=float)
        traded_value = close_history * volume_history
        adv20 = traded_value.tail(adv_window).mean()
        market_cap = market_cap_history.iloc[-1]
        ratio = adv20 / market_cap.where(market_cap > 0)
        return np.log(ratio.where(ratio > 0)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _compute_value(
        self,
        data: pd.DataFrame,
        symbols: pd.Index,
        snapshot_date: pd.Timestamp,
        latest_close: pd.Series,
    ) -> pd.Series:
        fundamentals = data.loc[data["available_at"] <= snapshot_date, ["symbol", "available_at", "book_value"]]
        if fundamentals.empty:
            return pd.Series(0.0, index=symbols, dtype=float)
        latest_fundamentals = fundamentals.sort_values(["symbol", "available_at"]).groupby("symbol", sort=False).tail(1)
        latest_fundamentals = latest_fundamentals.set_index("symbol").reindex(symbols)
        ratio = latest_fundamentals["book_value"] / latest_close.where(latest_close > 0)
        return ratio.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_barra_exposure_matrix(market_data: pd.DataFrame, as_of_date: pd.Timestamp | str) -> pd.DataFrame:
    return BarraFactorModel().build_exposure_matrix(market_data=market_data, as_of_date=as_of_date)
