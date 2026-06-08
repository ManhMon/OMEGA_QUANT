"""
omega.quant.strategy - Strategy Logic Layer
Upgraded from V21 layer_02_strategy_logic
"""

from omega.quant.strategy.alpha_ensemble import AlphaEnsemble, AlphaEnsembleConfig
from omega.quant.strategy.black_litterman import BlackLittermanOptimizer
from omega.quant.strategy.dl_models import LSTMModel, TCNModel, TransformerModel
from omega.quant.strategy.ml_hyperopt import AutoTuneResult, MLHyperparameterAutotuner
from omega.quant.strategy.ml_models import XGBEstimator, LGBEstimator, CatBoostEstimator
from omega.quant.strategy.model_trainer import TrainerConfig, WalkForwardOptunaTrainer
from omega.quant.strategy.multi_model_ensemble import MultiModelEnsemble, EnsembleConfig, AdaptiveEnsembleWeighting
from omega.quant.strategy.oos_walk_forward_validator import OOSWalkForwardValidator, WalkForwardConfig
from omega.quant.strategy.purged_cv import PurgedTimeSeriesSplit
from omega.quant.strategy.regime_conditional import RegimeConditionalStrategy, GaussianHMM, HMMConfig
from omega.quant.strategy.rl_agent import RLPortfolioAgent, RLConfig
from omega.quant.strategy.transaction_cost_analyzer import TransactionCostAnalyzer, VNSlippageModel, TransactionCostAnalysis

__all__ = [
    "AlphaEnsemble", "AlphaEnsembleConfig",
    "BlackLittermanOptimizer",
    "LSTMModel", "TCNModel", "TransformerModel",
    "AutoTuneResult", "MLHyperparameterAutotuner",
    "XGBEstimator", "LGBEstimator", "CatBoostEstimator",
    "TrainerConfig", "WalkForwardOptunaTrainer",
    "MultiModelEnsemble", "EnsembleConfig", "AdaptiveEnsembleWeighting",
    "OOSWalkForwardValidator", "WalkForwardConfig",
    "PurgedTimeSeriesSplit",
    "RegimeConditionalStrategy", "GaussianHMM", "HMMConfig",
    "RLPortfolioAgent", "RLConfig",
    "TransactionCostAnalyzer", "VNSlippageModel", "TransactionCostAnalysis",
]

# Auto-wired submodules and subpackages
try:
    from . import alpha_ensemble
except ImportError:
    pass

try:
    from . import black_litterman
except ImportError:
    pass

try:
    from . import dl_models
except ImportError:
    pass

try:
    from . import ml_hyperopt
except ImportError:
    pass

try:
    from . import ml_models
except ImportError:
    pass

try:
    from . import model_trainer
except ImportError:
    pass

try:
    from . import multi_model_ensemble
except ImportError:
    pass

try:
    from . import oos_walk_forward_validator
except ImportError:
    pass

try:
    from . import purged_cv
except ImportError:
    pass

try:
    from . import regime_conditional
except ImportError:
    pass

try:
    from . import rl_agent
except ImportError:
    pass

try:
    from . import transaction_cost_analyzer
except ImportError:
    pass
