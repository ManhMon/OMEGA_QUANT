"""Real-data smoke tests for OMEGA_QUANT."""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path("data/market_2015_now.parquet")
SYMBOLS = ["VNM", "VIC", "HPG", "TCB", "BID"]


def _load_frame(columns):
    df = pd.read_parquet(DATA_PATH, columns=columns)
    return df[df["ticker"].isin(SYMBOLS)].copy()


def _build_returns_frame():
    df = _load_frame(["ticker", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    px = df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    px = px.dropna(how="any")
    ret = px.pct_change().dropna(how="any").tail(252)
    return ret


def _softmax_weights(zscores):
    exp_z = np.exp(zscores)
    return exp_z.div(exp_z.sum(axis=1), axis=0)


def test_real_data_file_exists():
    assert DATA_PATH.exists(), f"Missing real data file: {DATA_PATH}"


def test_real_data_pit_compliance():
    df = _load_frame(["ticker", "date", "close", "available_at"])
    df["date"] = pd.to_datetime(df["date"])
    available = pd.to_datetime(df["available_at"]).dt.normalize()
    trade_date = df["date"].dt.normalize()

    assert not df.empty, "No rows loaded for smoke symbols"
    assert int((available <= trade_date).sum()) == 0


def test_real_data_live_rolling_path():
    ret = _build_returns_frame()
    momentum = ret.rolling(20).mean()
    zscores = momentum.sub(momentum.mean(axis=1), axis=0).div(
        momentum.std(axis=1).replace(0, 1.0), axis=0
    ).fillna(0)
    weights = _softmax_weights(zscores)
    lagged_weights = weights.shift(1)

    portfolio = (ret * lagged_weights).sum(axis=1).fillna(0)
    turnover = lagged_weights.diff().abs().sum(axis=1) / 2.0
    costs = 0.001 * turnover.reindex(portfolio.index).fillna(0)
    net = portfolio - costs

    gross_sharpe = portfolio.mean() / portfolio.std() * np.sqrt(252)
    net_sharpe = net.mean() / net.std() * np.sqrt(252)

    assert len(ret) == 252
    assert np.isfinite(gross_sharpe)
    assert np.isfinite(net_sharpe)
    assert net_sharpe < gross_sharpe
    assert 0 < turnover.mean() < 1.0
    assert -5.0 < net_sharpe < 10.0


def test_real_data_backtest_path():
    ret = _build_returns_frame()
    momentum = ret.rolling(20).mean()
    zscores = momentum.sub(momentum.mean(axis=1), axis=0).div(
        momentum.std(axis=1).replace(0, 1.0), axis=0
    ).fillna(0)
    weights = _softmax_weights(zscores)

    gross = (ret * weights.shift(1)).sum(axis=1).replace([np.inf, -np.inf], np.nan).fillna(0)
    turnover = weights.shift(1).diff().abs().sum(axis=1) / 2.0
    net = gross - (0.001 * turnover).reindex(gross.index).fillna(0)

    gross_sharpe = gross.mean() / gross.std() * np.sqrt(252)
    net_sharpe = net.mean() / net.std() * np.sqrt(252)
    total_return = (1 + net).prod() - 1

    assert np.isfinite(gross_sharpe)
    assert np.isfinite(net_sharpe)
    assert np.isfinite(total_return)
    assert net_sharpe < gross_sharpe
    assert -5.0 < net_sharpe < 10.0
    assert -1.0 < total_return < 10.0


def test_real_data_coverage():
    df = _load_frame(["ticker", "date", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])

    assert len(df) > 1000
    assert (df.groupby("ticker").size() > 200).all()
    assert ((df.groupby("ticker")["close"].apply(lambda s: s.isna().mean())) < 0.1).all()
    assert (df["date"].max() - df["date"].min()).days > 200
