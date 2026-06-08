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
    "TradingPipelineV2",
    "PipelineStateManager",
    "ParquetFeatureStoreAdapter",
    "DatabaseFeatureStoreAdapter",
    "BacktestOutputHandler",
    "LiveOutputHandler",
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

try:
    from .pipeline_v2 import (
        TradingPipelineV2,
        PipelineStateManager,
        ParquetFeatureStoreAdapter,
        DatabaseFeatureStoreAdapter,
        BacktestOutputHandler,
        LiveOutputHandler,
    )
except ImportError as e:
    import logging
    logging.warning("Failed to import pipeline_v2: %s", e)


try:
    from . import _portfolio_legacy
except ImportError:
    pass

try:
    from . import ab_tester
except ImportError:
    pass

try:
    from . import adaptive_portfolio_sizing
except ImportError:
    pass

try:
    from . import advanced_features
except ImportError:
    pass

try:
    from . import alpha_decay
except ImportError:
    pass

try:
    from . import alpha_discovery
except ImportError:
    pass

try:
    from . import alpha_discovery_integration
except ImportError:
    pass

try:
    from . import alpha_ensemble_xgboost
except ImportError:
    pass

try:
    from . import alpha_factory_legacy
except ImportError:
    pass

try:
    from . import alpha_factory_optimized
except ImportError:
    pass

try:
    from . import alpha_preprocessing
except ImportError:
    pass

try:
    from . import alpha_primitives
except ImportError:
    pass

try:
    from . import alpha_sanitizer
except ImportError:
    pass

try:
    from . import atomic_snapshot_manager
except ImportError:
    pass

try:
    from . import attribution
except ImportError:
    pass

try:
    from . import autotune_optimizer
except ImportError:
    pass

try:
    from . import backtest_engine
except ImportError:
    pass

try:
    from . import constraint_solver
except ImportError:
    pass

try:
    from . import continuous_learning
except ImportError:
    pass

try:
    from . import core_alphas
except ImportError:
    pass

try:
    from . import corporate_action
except ImportError:
    pass

try:
    from . import covariance_estimator
except ImportError:
    pass

try:
    from . import cv_splitter
except ImportError:
    pass

try:
    from . import dashboard
except ImportError:
    pass

try:
    from . import data_module
except ImportError:
    pass

try:
    from . import data_sanitizer
except ImportError:
    pass

try:
    from . import data_source_config
except ImportError:
    pass

try:
    from . import data_validator
except ImportError:
    pass

try:
    from . import decorrelation_engine
except ImportError:
    pass

try:
    from . import deployment
except ImportError:
    pass

try:
    from . import drift_detector
except ImportError:
    pass

try:
    from . import dynamic_universe
except ImportError:
    pass

try:
    from . import ensemble_builder
except ImportError:
    pass

try:
    from . import evolution_engine
except ImportError:
    pass

try:
    from . import execution_sim
except ImportError:
    pass

try:
    from . import expression_generator
except ImportError:
    pass

try:
    from . import factor_exposure
except ImportError:
    pass

try:
    from . import factor_neutralization
except ImportError:
    pass

try:
    from . import feature_discovery
except ImportError:
    pass

try:
    from . import feature_engineering
except ImportError:
    pass

try:
    from . import feature_module
except ImportError:
    pass

try:
    from . import feature_pruning
except ImportError:
    pass

try:
    from . import high_alpha_filter
except ImportError:
    pass

try:
    from . import hyperopt_layer
except ImportError:
    pass

try:
    from . import label_engine
except ImportError:
    pass

try:
    from . import lightweight_neutralization
except ImportError:
    pass

try:
    from . import live_execution_bridge
except ImportError:
    pass

try:
    from . import live_ingestor
except ImportError:
    pass

try:
    from . import live_trading_pipeline
except ImportError:
    pass

try:
    from . import macro_alphas
except ImportError:
    pass

try:
    from . import macro_context
except ImportError:
    pass

try:
    from . import market_microstructure
except ImportError:
    pass

try:
    from . import market_regime
except ImportError:
    pass

try:
    from . import markowitz_optimizer
except ImportError:
    pass

try:
    from . import math_utils
except ImportError:
    pass

try:
    from . import microstructure_alphas
except ImportError:
    pass

try:
    from . import midas_filters
except ImportError:
    pass

try:
    from . import ml_engine
except ImportError:
    pass

try:
    from . import ml_gate_validator
except ImportError:
    pass

try:
    from . import multi_horizon_labels
except ImportError:
    pass

try:
    from . import multi_symbol_router
except ImportError:
    pass

try:
    from . import neutralization
except ImportError:
    pass

try:
    from . import neutralization_engine
except ImportError:
    pass

try:
    from . import observability
except ImportError:
    pass

try:
    from . import paper_trading_engine
except ImportError:
    pass

try:
    from . import parallel_backtest
except ImportError:
    pass

try:
    from . import performance_tracker
except ImportError:
    pass

try:
    from . import phase34_microstructure_alphas
except ImportError:
    pass

try:
    from . import phase35_walk_forward
except ImportError:
    pass

try:
    from . import phase6_evolution_engine
except ImportError:
    pass

try:
    from . import pit_guard
except ImportError:
    pass

try:
    from . import pit_guardian
except ImportError:
    pass

try:
    from . import pnl_monitor
except ImportError:
    pass

try:
    from . import portfolio_optimizer
except ImportError:
    pass

try:
    from . import position_sizer
except ImportError:
    pass

try:
    from . import promoted_alphas
except ImportError:
    pass

try:
    from . import promotion
except ImportError:
    pass

try:
    from . import realtime_risk_guard
except ImportError:
    pass

try:
    from . import rebalancer
except ImportError:
    pass

try:
    from . import regime_aware_walk_forward
except ImportError:
    pass

try:
    from . import regime_detector_hmm
except ImportError:
    pass

try:
    from . import regime_switcher
except ImportError:
    pass

try:
    from . import registry
except ImportError:
    pass

try:
    from . import sanitization
except ImportError:
    pass

try:
    from . import sector_classifier
except ImportError:
    pass

try:
    from . import sentiment_alpha
except ImportError:
    pass

try:
    from . import signal_blender
except ImportError:
    pass

try:
    from . import signal_sanitizer
except ImportError:
    pass

try:
    from . import smart_money_features
except ImportError:
    pass

try:
    from . import smart_money_microstructure
except ImportError:
    pass

try:
    from . import strategy_engine
except ImportError:
    pass

try:
    from . import stress_testing
except ImportError:
    pass

try:
    from . import structure_features
except ImportError:
    pass

try:
    from . import target_module
except ImportError:
    pass

try:
    from . import thompson_sampling
except ImportError:
    pass

try:
    from . import trading_engine
except ImportError:
    pass

try:
    from . import transaction_cost
except ImportError:
    pass

try:
    from . import transaction_cost_optimizer
except ImportError:
    pass

try:
    from . import ultimate_alpha_arsenal
except ImportError:
    pass

try:
    from . import vci_integration
except ImportError:
    pass

try:
    from . import vn_alphas
except ImportError:
    pass

try:
    from . import vn_market_flow_datasource
except ImportError:
    pass

try:
    from . import vn_trading_calendar
except ImportError:
    pass

try:
    from . import vnstock_datasource
except ImportError:
    pass

try:
    from . import vnstock_vci_datasource
except ImportError:
    pass

try:
    from . import vnstock_vci_ingest
except ImportError:
    pass

try:
    from . import voting_stacking_ensemble
except ImportError:
    pass

try:
    from . import walk_forward_alpha_ensemble_integration
except ImportError:
    pass

try:
    from . import walk_forward_engine
except ImportError:
    pass

try:
    from . import walk_forward_ensemble
except ImportError:
    pass

# Auto-wired submodules and subpackages
try:
    from . import pipeline
except ImportError:
    pass

try:
    from . import factory
except ImportError:
    pass

try:
    from . import features
except ImportError:
    pass

try:
    from . import models
except ImportError:
    pass

try:
    from . import risk
except ImportError:
    pass

try:
    from . import universe
except ImportError:
    pass

try:
    from . import utils
except ImportError:
    pass

try:
    from . import validation
except ImportError:
    pass
