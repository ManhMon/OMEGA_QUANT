# flake8: noqa
"""Alpha Discovery Engine primitives and expression evaluator.

Shim wrapper preserving backward compatibility.
"""
from __future__ import annotations

import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.alpha.discovery is deprecated; import from individual submodules instead.",
    DeprecationWarning,
    stacklevel=2
)


from omega.quant.alpha.discovery_operators import (
    rank,
    delay,
    delta,
    ts_corr,
    ts_std,
    ts_max,
    ts_min,
    ts_rank,
    decay_linear,
    high_low_efficiency,
    volume_imbalance_proxy,
    compute_rsi,
    compute_macd,
    build_alpha_signals,
)
from omega.quant.alpha.discovery_alchemist import (
    AlphaAlchemist,
    ALPHA_TEMPLATES,
    LAGS,
    WINDOWS,
    generate_all_candidate_expressions,
)
from omega.quant.alpha.discovery_judge import (
    AlphaJudge,
    OrthogonalityChecker,
    correlation_based_clustering,
)
from omega.quant.alpha.discovery_universe import (
    FeatureUniverseManager,
    AlphaExpansionRunner,
    AlphaPromoter,
    AlphaDecayMonitor,
)
from omega.quant.alpha.discovery_engine import (
    DiscoveryConfig,
    AlphaDiscoveryEngine,
)

__all__ = [
    "rank",
    "delay",
    "delta",
    "ts_corr",
    "ts_std",
    "ts_max",
    "ts_min",
    "ts_rank",
    "decay_linear",
    "high_low_efficiency",
    "volume_imbalance_proxy",
    "compute_rsi",
    "compute_macd",
    "build_alpha_signals",
    "AlphaAlchemist",
    "ALPHA_TEMPLATES",
    "LAGS",
    "WINDOWS",
    "generate_all_candidate_expressions",
    "AlphaJudge",
    "OrthogonalityChecker",
    "correlation_based_clustering",
    "FeatureUniverseManager",
    "AlphaExpansionRunner",
    "AlphaPromoter",
    "AlphaDecayMonitor",
    "DiscoveryConfig",
    "AlphaDiscoveryEngine",
]
