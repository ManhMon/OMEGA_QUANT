"""
Compatibility shim for ML Engine.
Redirects imports to the canonical implementation in omega.quant.ml.ml_engine.
"""
from __future__ import annotations

from omega.quant.ml.ml_engine import (
    MLModelType,
    TrainingStatus,
    AlphaMetrics,
    ModelConfig,
    TrainedModel,
    MLEngine,
    get_ml_engine,
)

__all__ = [
    "MLModelType",
    "TrainingStatus",
    "AlphaMetrics",
    "ModelConfig",
    "TrainedModel",
    "MLEngine",
    "get_ml_engine",
]
