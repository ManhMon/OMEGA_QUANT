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

def test_pipeline_state_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
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

def test_parquet_feature_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "features.parquet"
        
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
        df.to_parquet(tmp_path)
        
        adapter = ParquetFeatureStoreAdapter(tmp_path)
        res = adapter.get_features(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-04"), ["HPG"])
        assert len(res) == 3
        assert (res["ticker"] == "HPG").all()
        assert (res["date"] >= "2026-01-02").all()
        assert (res["date"] <= "2026-01-04").all()

def test_trading_pipeline_v2_backtest():
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
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
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

def test_trading_pipeline_v2_live():
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
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
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
