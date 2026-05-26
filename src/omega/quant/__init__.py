"""OMEGA_QUANT Quant Package - Institutional Grade
Version: 2.4
Status: Production Ready

Unified quant engine with:
- QuantEngine: End-to-end pipeline (features → alphas → signals → weights)
- AlphaRegistry: Alpha lifecycle management (IC tracking, auto-promotion/retirement)
- Feature/Alpha/Model/Signal modules from V21 Core Intelligence

Author: OMEGA_QUANT Team
Last Updated: 2026-05-26
"""

# Core exports - Institutional Grade Quant Engine
__all__ = [
    # Unified Engine
    "QuantEngine",
    "QuantEngineConfig",
    "QuantEngineOutput",
    
    # Alpha Registry
    "AlphaRegistry",
    "AlphaRegistryConfig",
    "AlphaMetadata",
    
    # V21 Core Intelligence Modules
    "AlphaFactory",
    "ModelModule",
    "ModelConfig",
    "SignalModule",
    "SignalModuleConfig",
    "FeatureFactory",
    "GeneticProgrammingEngine",
    "GPConfig",
    "EnsembleOptimizer",
    "WeightsConfig",
    "ExperimentTracker",
    "PITManager",
]

# Import core components
try:
    from .quant_engine import (
        QuantEngine,
        QuantEngineConfig,
        QuantEngineOutput,
    )
except ImportError as e:
    import logging
    logging.warning("Failed to import QuantEngine: %s", e)

try:
    from .alpha_registry import (
        AlphaRegistry,
        AlphaRegistryConfig,
        AlphaMetadata,
    )
except ImportError as e:
    import logging
    logging.warning("Failed to import AlphaRegistry: %s", e)

# Import V21 modules
try:
    from .alpha_factory import AlphaFactory
except ImportError:
    pass

try:
    from .model_module import ModelModule, ModelConfig
except ImportError:
    pass

try:
    from .signal_module import SignalModule, SignalModuleConfig
except ImportError:
    pass

try:
    from .feature_factory import (
        MomentumGenerator as FeatureFactory,  # Alias for backward compat
    )
except ImportError:
    pass

try:
    from .genetic_programming import GeneticProgrammingEngine, GPConfig
except ImportError:
    pass

try:
    from .ensemble_optimizer import EnsembleOptimizer, WeightsConfig
except ImportError:
    pass

try:
    from .experiment_tracker import ExperimentTracker
except ImportError:
    pass

try:
    from .pit_manager import PITManager
except ImportError:
    pass

# Legacy compatibility imports (with fallbacks)
try:
    from omega.memory.memory_archive import AlphaMemory, ErrorMemory
    __all__.extend(["AlphaMemory", "ErrorMemory"])
except ImportError:
    pass

try:
    from omega.memory.memory_retrieval import AlphaRetriever
    __all__.append("AlphaRetriever")
except ImportError:
    pass

try:
    from omega.risk.risk_monitor import RiskMonitor
    __all__.append("RiskMonitor")
except ImportError:
    pass

try:
    from omega.observability import StructuredLogger, MetricsRegistry
    __all__.extend(["StructuredLogger", "MetricsRegistry"])
except ImportError:
    pass

try:
    from omega.security import SecretsVault
    __all__.append("SecretsVault")
except ImportError:
    pass

try:
    from omega.execution.broker_gateway import BrokerOrder
    from omega.execution.order_router import OrderRouter
    __all__.extend(["BrokerOrder", "OrderRouter"])
except ImportError:
    pass
