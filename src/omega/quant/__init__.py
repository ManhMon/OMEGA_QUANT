"""Public API for :mod:`omega.quant`.

Exports are resolved lazily to keep package import cheap while preserving the
legacy top-level names exposed by the previous eager import initializer.
"""

from importlib import import_module

_Q = "omega.quant."
_EXPORTS = {
    "QuantEngine": (_Q + "quant_engine", "QuantEngine"),
    "QuantEngineConfig": (_Q + "quant_engine", "QuantEngineConfig"),
    "QuantEngineOutput": (_Q + "quant_engine", "QuantEngineOutput"),
    "AlphaRegistry": (_Q + "alpha.registry", "AlphaRegistry"),
    "AlphaRegistryConfig": (_Q + "alpha.registry", "AlphaRegistryConfig"),
    "AlphaMetadata": (_Q + "alpha.registry", "AlphaMetadata"),
    "AlphaFactory": (_Q + "alpha.factory", "AlphaFactory"),
    "ModelModule": (_Q + "ml.model_module", "ModelModule"),
    "ModelConfig": (_Q + "ml.model_module", "ModelConfig"),
    "SignalModule": (_Q + "signal.module", "SignalModule"),
    "SignalModuleConfig": (_Q + "signal.module", "SignalModuleConfig"),
    "FeatureFactory": (_Q + "feature.factory", "MomentumGenerator"),
    "GeneticProgrammingEngine": (
        _Q + "evolution.genetic_programming", "GeneticProgrammingEngine",
    ),
    "GPConfig": (_Q + "evolution.genetic_programming", "GPConfig"),
    "EnsembleOptimizer": (_Q + "evolution.ensemble_optimizer", "EnsembleOptimizer"),
    "WeightsConfig": (_Q + "evolution.ensemble_optimizer", "WeightsConfig"),
    "ExperimentTracker": (_Q + "monitoring.experiment_tracker", "ExperimentTracker"),
    "PITManager": (_Q + "risk.pit_manager", "PITManager"),
    "TradingPipelineV2": (_Q + "pipeline_v2", "TradingPipelineV2"),
    "PipelineStateManager": (_Q + "pipeline_v2", "PipelineStateManager"),
    "ParquetFeatureStoreAdapter": (
        _Q + "pipeline_v2", "ParquetFeatureStoreAdapter",
    ),
    "DatabaseFeatureStoreAdapter": (
        _Q + "pipeline_v2", "DatabaseFeatureStoreAdapter",
    ),
    "BacktestOutputHandler": (_Q + "pipeline_v2", "BacktestOutputHandler"),
    "LiveOutputHandler": (_Q + "pipeline_v2", "LiveOutputHandler"),
    "AlphaMemory": ("omega.memory.memory_archive", "AlphaMemory"),
    "ErrorMemory": ("omega.memory.memory_archive", "ErrorMemory"),
    "AlphaRetriever": ("omega.memory.memory_retrieval", "AlphaRetriever"),
    "RiskMonitor": ("omega.risk.risk_monitor", "RiskMonitor"),
    "StructuredLogger": ("omega.observability", "StructuredLogger"),
    "MetricsRegistry": ("omega.observability", "MetricsRegistry"),
    "SecretsVault": ("omega.security", "SecretsVault"),
    "BrokerOrder": ("omega.execution.broker_gateway", "BrokerOrder"),
    "OrderRouter": ("omega.execution.order_router", "OrderRouter"),
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    """Load legacy top-level exports on first access."""
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg) from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
