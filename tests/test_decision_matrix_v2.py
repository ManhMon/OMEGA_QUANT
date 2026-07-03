from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

@dataclass
class _PipelineFrame:
    timestamps: list
    values: dict


@dataclass
class _MarketState:
    timestamp: object
    cash: float
    positions: dict = field(default_factory=dict)
    pending_cash: float = 0.0
    pending_settlements: list = field(default_factory=list)


class _TemporalFirewall:
    def validate(self, features, targets):
        return types.SimpleNamespace(ok=True)


class _RiskEngine:
    def approve(self, *args, **kwargs):
        return {"approved": True}

    def max_drawdown(self, equity_curve):
        return 0.0

    def var_95(self, returns):
        return 0.0

    def cvar_95(self, returns):
        return 0.0


class _PortfolioOptimizer:
    def optimize_portfolio(self, returns_by_asset, expected):
        return ({sym: 1.0 / max(len(expected), 1) for sym in expected}, None, None)


class _ExecutionEngine:
    def generate_execution_plan(self, **kwargs):
        sym = next(iter(kwargs["prices"]))
        side = "BUY" if kwargs["target_portfolio"][sym] > 0 else "SELL"
        return {"orders": {sym: {"side": side, "total_quantity": 10.0}}}

    def execute(self, **kwargs):
        return self.generate_execution_plan(**kwargs)


class _StateEngine:
    def settle(self, state, ts):
        return state

    def apply_fill(self, state, sym, qty, price, side):
        positions = dict(state.positions)
        signed = qty if side == "BUY" else -qty
        positions[sym] = positions.get(sym, 0.0) + signed
        return _MarketState(timestamp=state.timestamp, cash=state.cash - signed * price, positions=positions)

    def mark_to_market(self, state, prices):
        return state.cash + sum(qty * prices.get(sym, 0.0) for sym, qty in state.positions.items())


@dataclass
class _OrderBookLevel:
    price: float = 0.0
    size: float = 0.0


def _apply_delisted_liquidations(state, current_date, trades, data_module):
    return state


sys.modules.setdefault("omega.backtest.types", types.SimpleNamespace(PipelineFrame=_PipelineFrame, MarketState=_MarketState))
sys.modules.setdefault("omega.backtest.temporal", types.SimpleNamespace(TemporalFirewall=_TemporalFirewall))
sys.modules.setdefault("omega.backtest.risk", types.SimpleNamespace(RiskEngine=_RiskEngine))
sys.modules.setdefault("omega.backtest.portfolio", types.SimpleNamespace(PortfolioOptimizer=_PortfolioOptimizer))
sys.modules.setdefault("omega.backtest.layer_03_execution_engine", types.SimpleNamespace(ExecutionEngine=_ExecutionEngine))
sys.modules.setdefault("omega.backtest.state", types.SimpleNamespace(StateEngine=_StateEngine))
sys.modules.setdefault("omega.backtest.orderbook", types.SimpleNamespace(OrderBookLevel=_OrderBookLevel))
sys.modules.setdefault("omega.backtest.backtest_liquidation", types.SimpleNamespace(apply_delisted_liquidations=_apply_delisted_liquidations))

from omega.backtest.vectorized_backtest import BacktestEngine
from omega.backtest.types import PipelineFrame
from omega.core.vn_market_rules import VnMarketRules
from omega.quant.features.frac_diff import frac_diff_fixed_window
from omega.quant.models.conformal_predictor import ConformalTrendPredictor
from omega.quant.models.liquidity_survival import LiquiditySurvivalModel
from omega.quant.portfolio.sector_classifier import SectorClassifier
from omega.quant.risk.pit_guardian import PITGuardian
from omega.quant.strategy.meta_labeler import MetaLabeler
from omega.quant.validation.cpcv import CombinatorialPurgedKFold


def _frame(ts, value_key="score", value=0.0):
    return PipelineFrame(timestamps=ts, values={value_key: [value for _ in ts]})


def test_future_shuffle_invariance():
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "ticker": ["AAA"] * 5,
        "sector_code": ["S1"] * 5,
        "return_1": [0.01, 0.02, 0.03, 0.04, 0.05],
        "market_cap": [100, 101, 102, 103, 104],
    })
    sc = SectorClassifier()
    a = sc.compute_rs_ex_top3(base, "2024-01-03")
    shuffled = base.copy()
    shuffled.loc[shuffled["date"] > pd.Timestamp("2024-01-03"), "market_cap"] = [999, 1]
    b = sc.compute_rs_ex_top3(shuffled, "2024-01-03")
    assert a["rs_ex_top3"].iloc[0] == b["rs_ex_top3"].iloc[0]


def test_sector_mapping_no_lookahead():
    hist = pd.DataFrame({
        "ticker": ["AAA", "AAA", "BBB"],
        "sector_code": ["OLD", "NEW", "S2"],
        "effective_date": ["2024-01-01", "2024-02-01", "2024-01-01"],
    })
    sc = SectorClassifier()
    jan = sc.get_sector_mapping_pit("2024-01-15", hist)
    feb = sc.get_sector_mapping_pit("2024-02-15", hist)
    assert jan["AAA"] == "OLD"
    assert feb["AAA"] == "NEW"


def test_rs_ex_top3_cross_section():
    rows = []
    for ticker, mcap, ret in [("A", 100, 0.10), ("B", 90, 0.08), ("C", 80, 0.06), ("D", 70, 0.04), ("E", 60, 0.02)]:
        rows += [
            {"date": "2024-01-01", "ticker": ticker, "sector_code": "S1", "return_1": 0.0, "market_cap": mcap},
            {"date": "2024-01-02", "ticker": ticker, "sector_code": "S1", "return_1": ret, "market_cap": mcap + 1},
        ]
    out = SectorClassifier().compute_rs_ex_top3(pd.DataFrame(rows), "2024-01-02")
    value = out.loc[out["ticker"] == "A", "rs_ex_top3"].iloc[0]
    assert np.isclose(value, 0.10 - np.mean([0.04, 0.02]))


def test_price_limit_buy_block():
    engine = BacktestEngine()
    ts = ["2024-01-01", "2024-01-02"]
    features = _frame(ts)
    targets = _frame(ts)
    signals = PipelineFrame(timestamps=ts, values={"AAA:score": [0.0, 1.0]})
    prices = {"AAA": [100.0, VnMarketRules.calculate_price_limits(100.0)[1]]}
    result = engine.run(features, targets, prices, signals)
    assert any(trade.get("warning") == "price_limit_buy_block" for trade in result.trades)


def test_price_limit_sell_block():
    engine = BacktestEngine()
    ts = ["2024-01-01", "2024-01-02"]
    features = _frame(ts)
    targets = _frame(ts)
    signals = PipelineFrame(timestamps=ts, values={"AAA:score": [1.0, -1.0]})
    prices = {"AAA": [100.0, VnMarketRules.calculate_price_limits(100.0)[0]]}
    result = engine.run(features, targets, prices, signals)
    assert any(trade.get("warning") == "price_limit_sell_block" for trade in result.trades)


def test_mondrian_conditional_coverage():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"x": rng.normal(size=320)})
    y = 0.5 * X["x"].to_numpy() + rng.normal(scale=0.35, size=320)
    groups = pd.DataFrame({
        "regime": np.repeat(["bull", "bear"], 160),
        "liquidity_bucket": np.tile(np.repeat(["high", "low"], 80), 2),
    })
    model = ConformalTrendPredictor(alpha=0.2, min_group_size=20)
    model.fit(X.iloc[:160], y[:160], X.iloc[160:240], y[160:240], groups.iloc[160:240])
    pred = model.predict(X.iloc[240:], groups.iloc[240:])
    coverage = model.conditional_coverage(y[240:], pred)
    assert all(0.78 <= val <= 0.86 for val in coverage.values())


def test_cqr_no_quantile_crossing():
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"x": rng.normal(size=120)})
    y = X["x"].to_numpy() + rng.normal(scale=0.1, size=120)
    groups = pd.DataFrame({"regime": ["r"] * 40, "liquidity_bucket": ["l"] * 40})
    model = ConformalTrendPredictor(alpha=0.2, min_group_size=5)
    model.fit(X.iloc[:80], y[:80], X.iloc[80:120], y[80:120], groups)
    pred = model.predict(X.iloc[:10], pd.DataFrame({"regime": ["r"] * 10, "liquidity_bucket": ["l"] * 10}))
    assert np.all(pred.lower <= pred.upper)


def test_embargo_isolation():
    ts = pd.date_range("2020-01-01", periods=1200, freq="D")
    cpcv = CombinatorialPurgedKFold(n_splits=10, n_test_splits=2, embargo_pct=200 / len(ts), label_horizon=60)
    train_idx, test_idx = next(cpcv.split(ts))
    post_test_train = ts[train_idx][ts[train_idx] > ts[test_idx].max()]
    assert len(post_test_train) > 0
    assert post_test_train.min() - ts[test_idx].max() >= pd.Timedelta(days=200)


def test_fracdiff_stationarity_memory():
    rng = np.random.default_rng(2)
    values = np.zeros(2048)
    noise = rng.normal(scale=0.2, size=2048)
    for i in range(1, len(values)):
        values[i] = 0.97 * values[i - 1] + noise[i]
    series = pd.Series(values)
    fd = frac_diff_fixed_window(series, d=0.05, window=16).dropna()
    corr = np.corrcoef(series.loc[fd.index], fd)[0, 1]
    from statsmodels.tsa.stattools import adfuller
    assert adfuller(fd)[1] < 0.05
    assert corr > 0.9


def test_pit_guardian_zero_violation():
    guardian = PITGuardian()
    features = pd.DataFrame({"x": [1, 2, 3]}, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    targets = pd.Series([0.1, 0.2], index=pd.to_datetime(["2024-01-04", "2024-01-05"]))
    assert guardian.check_target_leakage(features, targets, pd.Timestamp("2024-01-04"))
    assert guardian.get_violations() == []


def test_meta_label_and_survival_smoke():
    X = pd.DataFrame({"f1": np.linspace(-1, 1, 20), "f2": np.linspace(1, -1, 20)})
    primary = pd.Series(np.sign(X["f1"]).replace(0, 1), index=X.index)
    realized = pd.Series(np.where(np.arange(len(X)) % 3 == 0, -0.02, 0.02), index=X.index)
    meta = MetaLabeler().fit(X, primary, realized).predict(X)
    assert set(meta.labels.unique()).issubset({0, 1})

    surv = LiquiditySurvivalModel(lr=0.05, n_iter=50).fit(X, pd.Series(np.arange(1, 21)), pd.Series([0, 1] * 10))
    hz = surv.predict_hazard(X.head(3))
    assert np.all(hz > 0)
