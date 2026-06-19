import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from omega.quant import (
    TradingPipelineV2,
    PipelineStateManager,
    ParquetFeatureStoreAdapter,
    DatabaseFeatureStoreAdapter,
    BacktestOutputHandler,
    LiveOutputHandler,
)
from omega.quant.pipeline_v2 import (
    SmartMoneyOverlay,
    SentimentOverlay,
    ContagionOverlay,
    TCostOverlay,
    CircuitBreakerOverlay,
    TailControlOverlay,
    AdaptiveSizingOverlay,
    BlackLittermanOverlay,
    ContinuousLearningOverlay,
    DriftOverlay,
    HMMRegimeOverlay,
    RegimeAwareWFOverlay,
    RegimeOverlay,
    ThompsonSamplingWeightOverlay,
)

def test_pipeline_state_manager(tmp_path):
    """TEST-01 FIX3: use pytest tmp_path (ACL-safe) instead of tempfile.TemporaryDirectory."""
    manager = PipelineStateManager(tmp_path)
    
    test_state = {
        "last_weights": {"HPG": 0.5, "SSI": -0.5},
        "portfolio_returns_history": np.array([0.01, -0.02, 0.015]),
        "warmup_history": [0.01, -0.02, 0.015]
    }
    manager.save_state("test_run", test_state)
    
    loaded = manager.load_state("test_run")
    assert loaded["last_weights"] == {"HPG": 0.5, "SSI": -0.5}
    assert loaded["portfolio_returns_history"] == [0.01, -0.02, 0.015]
    
    assert manager.load_state("non_existent") == {}

def test_parquet_feature_store(tmp_path):
    """TEST-01 FIX3: use pytest tmp_path (ACL-safe) instead of tempfile.TemporaryDirectory."""
    parquet_path = tmp_path / "features.parquet"
    
    dates = pd.date_range("2026-01-01", "2026-01-05", freq="D")
    tickers = ["HPG", "SSI"]
    rows = []
    for d in dates:
        for t in tickers:
            rows.append({
                "date": d,
                "ticker": t,
                "close": 100.0,
                "volume": 1000.0,
                "returns": 0.01,
                "composite_signal": 0.5
            })
    df = pd.DataFrame(rows)
    df.to_parquet(parquet_path)
    
    adapter = ParquetFeatureStoreAdapter(parquet_path)
    res = adapter.get_features(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-04"), ["HPG"])
    assert len(res) == 3
    assert (res["ticker"] == "HPG").all()
    assert (res["date"] >= "2026-01-02").all()
    assert (res["date"] <= "2026-01-04").all()

def test_trading_pipeline_v2_backtest(tmp_path):
    """TEST-01 FIX3: use pytest tmp_path (ACL-safe) instead of tempfile.TemporaryDirectory."""
    def query_fn(start, end, tickers):
        rows = []
        hist_dates = pd.date_range(end=end, periods=40, freq="D")
        for d in hist_dates:
            for t in ["HPG", "SSI"]:
                rows.append({
                    "date": d,
                    "symbol": t,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.5,
                    "close": 10.0,
                    "volume": 1000.0,
                    "returns": 0.01,
                    "adv_vnd": 10000.0,
                    "composite_signal": 0.5 if t == "HPG" else -0.5
                })
        return pd.DataFrame(rows)
        
    feature_store = DatabaseFeatureStoreAdapter(query_fn)
    
    state_manager = PipelineStateManager(tmp_path)
    
    out_json = tmp_path / "report.json"
    out_csv = tmp_path / "equity.csv"
    output_handler = BacktestOutputHandler(out_json, out_csv)
    
    overlays = [
        SmartMoneyOverlay(boost_scale=0.1),
        SentimentOverlay(boost_scale=0.1),
        ContagionOverlay(lookback=5, spike_threshold_std=2.0),
        TCostOverlay(cost_per_trade_bps=10.0, min_trade_threshold_bps=5.0),
        CircuitBreakerOverlay(cvar_limit=-0.1, derisk_multiplier=0.8, lookback=5),
        TailControlOverlay(target_vol_ann=0.2, max_abs_weight=0.5),
        AdaptiveSizingOverlay(capital_vnd=1e9),
        BlackLittermanOverlay(tau=0.05, view_confidence=0.5, l2_reg=0.01, max_weight=0.05),
        ContinuousLearningOverlay(retrain_threshold_ic=0.01, retrain_lookback=10, retrain_every=10, min_train=10),
        DriftOverlay(lookback=5, ic_threshold=0.0, drift_exposure=0.5),
        HMMRegimeOverlay(bear_exposure=0.5, bull_exposure=1.1, sideways_exposure=0.8, retrain_every=10),
        RegimeAwareWFOverlay(bear_scale=0.3, bull_scale=1.0, sideways_scale=0.7, retrain_every=10, min_train=10),
        RegimeOverlay(hysteresis_days=2, dd_threshold=-0.10),
        ThompsonSamplingWeightOverlay(lookback=5, update_every=2)
    ]
    
    pipeline = TradingPipelineV2(
        feature_store=feature_store,
        state_manager=state_manager,
        output_handler=output_handler,
        overlays=overlays,
        config={"initial_capital_vnd": 1e9}
    )
    
    res = pipeline.execute(
        run_id="test_run",
        date_start="2026-01-01",
        date_end="2026-01-10",
        tickers=["HPG", "SSI"]
    )
    
    assert out_json.exists()
    assert out_csv.exists()
    assert "total_return" in res
    assert "annualized_sharpe" in res
    assert "max_drawdown" in res

def test_trading_pipeline_v2_live(tmp_path):
    """TEST-01 FIX3: use pytest tmp_path (ACL-safe) instead of tempfile.TemporaryDirectory."""
    def query_fn(start, end, tickers):
        rows = []
        hist_dates = pd.date_range(end=end, periods=40, freq="D")
        for d in hist_dates:
            for t in ["HPG", "SSI"]:
                rows.append({
                    "date": d,
                    "symbol": t,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.5,
                    "close": 10.0,
                    "volume": 1000.0,
                    "returns": 0.01,
                    "adv_vnd": 10000.0,
                    "composite_signal": 0.8 if t == "HPG" else -0.8
                })
        return pd.DataFrame(rows)
        
    feature_store = DatabaseFeatureStoreAdapter(query_fn)
    
    state_manager = PipelineStateManager(tmp_path)
    
    class MockRouter:
        def __init__(self):
            self.routed = []
        def route_orders(self, orders):
            self.routed = orders
            
    router = MockRouter()
    positions = {"HPG": 0.1, "SSI": 0.2}
    output_handler = LiveOutputHandler(router, positions, initial_capital=1e9)
    
    pipeline = TradingPipelineV2(
        feature_store=feature_store,
        state_manager=state_manager,
        output_handler=output_handler,
        overlays=[
            TCostOverlay(cost_per_trade_bps=10.0, min_trade_threshold_bps=5.0)
        ],
        config={"initial_capital_vnd": 1e9}
    )
    
    orders = pipeline.execute(
        run_id="live_run",
        date_start="2026-01-05",
        date_end="2026-01-05",
        tickers=["HPG", "SSI"]
    )
    
    assert len(orders) > 0
    assert router.routed == orders
    state = state_manager.load_state("live_run")
    assert "last_weights" in state
    assert "portfolio_returns_history" in state


def test_signal_overlays_use_prior_day_scores(monkeypatch):
    import omega.quant.portfolio.sentiment_overlay as sentiment_mod
    import omega.quant.portfolio.smart_money_overlay as smart_money_mod

    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    symbols = ["HPG", "SSI"]
    index = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    scores = pd.Series([1.0, -1.0, -1.0, 1.0], index=index)

    def fake_smart_money_features(panel):
        return pd.DataFrame({"smart_money_score": scores}, index=scores.index)

    def fake_sentiment_proxy(panel):
        return scores

    monkeypatch.setattr(smart_money_mod, "compute_smart_money_features", fake_smart_money_features)
    monkeypatch.setattr(sentiment_mod, "compute_sentiment_proxy", fake_sentiment_proxy)

    panel = pd.DataFrame(
        [
            {
                "date": date,
                "symbol": symbol,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 1000.0,
            }
            for date in dates
            for symbol in symbols
        ]
    )
    weights = pd.DataFrame(0.5, index=dates, columns=symbols)

    smart_money_out = SmartMoneyOverlay(boost_scale=0.5).apply(weights, panel, {})
    sentiment_out = SentimentOverlay(boost_scale=0.5).apply(weights, panel, {})

    assert np.allclose(smart_money_out.loc[dates[0]], weights.loc[dates[0]])
    assert np.allclose(sentiment_out.loc[dates[0]], weights.loc[dates[0]])
    assert smart_money_out.loc[dates[1], "HPG"] > smart_money_out.loc[dates[1], "SSI"]
    assert sentiment_out.loc[dates[1], "HPG"] > sentiment_out.loc[dates[1], "SSI"]


def test_adaptive_sizing_overlay_uses_prior_expanding_adv(monkeypatch):
    import omega.quant.portfolio.adaptive_sizing_overlay as adaptive_mod

    captured = {}

    def fake_apply_adaptive_sizing(weights, capital_vnd, adv_series):
        captured["adv_series"] = adv_series.copy()
        return weights

    monkeypatch.setattr(adaptive_mod, "apply_adaptive_sizing", fake_apply_adaptive_sizing)

    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    rows = []
    for date, hpg_adv, ssi_adv in zip(dates, [100.0, 300.0, 900.0], [50.0, 150.0, 450.0]):
        rows.append({"date": date, "symbol": "HPG", "adv_vnd": hpg_adv})
        rows.append({"date": date, "symbol": "SSI", "adv_vnd": ssi_adv})

    weights = pd.DataFrame(0.5, index=dates, columns=["HPG", "SSI"])
    AdaptiveSizingOverlay(capital_vnd=1e9).apply(weights, pd.DataFrame(rows), {})

    adv_series = captured["adv_series"]
    assert pd.isna(adv_series.loc[dates[0], "HPG"])
    assert pd.isna(adv_series.loc[dates[0], "SSI"])
    assert adv_series.loc[dates[1], "HPG"] == 100.0
    assert adv_series.loc[dates[1], "SSI"] == 50.0
    assert adv_series.loc[dates[2], "HPG"] == 200.0
    assert adv_series.loc[dates[2], "SSI"] == 100.0
