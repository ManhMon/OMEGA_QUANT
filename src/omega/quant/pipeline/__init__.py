"""Lazy public API for OMEGA_QUANT pipeline components."""

from __future__ import annotations

from importlib import import_module

_PIPELINE_V2_EXPORTS = {
    "TradingPipelineV2",
    "PipelineStateManager",
    "FeatureStoreAdapter",
    "ParquetFeatureStoreAdapter",
    "DatabaseFeatureStoreAdapter",
    "PipelineOutputHandler",
    "BacktestOutputHandler",
    "LiveOutputHandler",
    "HMMRegimeOverlay",
    "RegimeAwareWFOverlay",
}

_OVERLAY_EXPORTS = {
    "WeightOverlay",
    "SmartMoneyOverlay",
    "SentimentOverlay",
    "ContagionOverlay",
    "TCostOverlay",
    "CircuitBreakerOverlay",
    "TailControlOverlay",
    "AdaptiveSizingOverlay",
    "BlackLittermanOverlay",
    "ContinuousLearningOverlay",
    "DriftOverlay",
    "RegimeOverlay",
    "ThompsonSamplingWeightOverlay",
    "WeightSmoothingOverlay",
}

__all__ = sorted({"TradingPipeline", *_PIPELINE_V2_EXPORTS, *_OVERLAY_EXPORTS})


class TradingPipeline:
    """Backward-compatible facade for the retired v1 orchestration API."""

    def __init__(self, discovery_engine, optimizer, risk_monitor, order_router, backtest_engine):
        from omega.quant.monitoring.observability import setup_observability

        self.discovery = discovery_engine
        self.optimizer = optimizer
        self.risk = risk_monitor
        self.router = order_router
        self.backtest = backtest_engine

        obs = setup_observability("pipeline")
        self.logger_obs = obs["logger"]
        self.metrics = obs["metrics"]
        self.alerts = obs["alerts"]
        self.alerts.add_rule("High Pipeline Latency", "latency_ms", ">", 5000.0, severity="WARNING")


def __getattr__(name: str):
    """Resolve pipeline exports on first access to keep package import cheap."""
    if name == "TradingPipeline":
        return TradingPipeline

    if name in _PIPELINE_V2_EXPORTS:
        value = getattr(import_module("omega.quant.pipeline_v2"), name)
        globals()[name] = value
        return value

    if name in _OVERLAY_EXPORTS:
        value = getattr(import_module("omega.quant.pipeline.overlays"), name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
