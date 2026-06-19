"""
OMEGA_QUANT Pipeline Overlays
Composable weight overlay implementations for post-optimization adjustments.
"""
from omega.quant.pipeline.overlays.base import WeightOverlay
from omega.quant.pipeline.overlays.smart_money import SmartMoneyOverlay
from omega.quant.pipeline.overlays.sentiment import SentimentOverlay
from omega.quant.pipeline.overlays.contagion import ContagionOverlay
from omega.quant.pipeline.overlays.tcost import TCostOverlay
from omega.quant.pipeline.overlays.circuit_breaker import CircuitBreakerOverlay
from omega.quant.pipeline.overlays.tail_control import TailControlOverlay
from omega.quant.pipeline.overlays.adaptive_sizing import AdaptiveSizingOverlay
from omega.quant.pipeline.overlays.black_litterman import BlackLittermanOverlay
from omega.quant.pipeline.overlays.continuous_learning import ContinuousLearningOverlay
from omega.quant.pipeline.overlays.drift import DriftOverlay
from omega.quant.pipeline.overlays.regime import RegimeOverlay
from omega.quant.pipeline.overlays.thompson_sampling import ThompsonSamplingWeightOverlay
from omega.quant.pipeline.overlays.weight_smoothing import WeightSmoothingOverlay

__all__ = [
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
]
