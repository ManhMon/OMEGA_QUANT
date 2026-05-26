"""
omega.quant.strategy - Strategy Logic Layer
Upgraded from V21 layer_02_strategy_logic
"""

from omega.quant.strategy.alpha_ensemble import AlphaEnsemble
from omega.quant.strategy.black_litterman import BlackLittermanOptimizer
from omega.quant.strategy.dl_models import LSTMModel, TransformerModel
from omega.quant.strategy.ml_hyperopt import HyperoptConfig, run_hyperopt
from omega.quant.strategy.ml_models import XGBModel, LGBModel
from omega.quant.strategy.model_trainer import ModelTrainer
from omega.quant.strategy.multi_model_ensemble import MultiModelEnsemble, EnsembleConfig
from omega.quant.strategy.oos_walk_forward_validator import OOSWalkForwardValidator, WalkForwardConfig
from omega.quant.strategy.purged_cv import PurgedTimeSeriesCV
from omega.quant.strategy.regime_conditional import RegimeConditionalStrategy, GaussianHMM
from omega.quant.strategy.rl_agent import RLAgent
from omega.quant.strategy.transaction_cost_analyzer import TransactionCostAnalyzer, VNSlippageModel

__all__ = [
    "AlphaEnsemble",
    "BlackLittermanOptimizer",
    "LSTMModel",
    "TransformerModel",
    "HyperoptConfig",
    "run_hyperopt",
    "XGBModel",
    "LGBModel",
    "ModelTrainer",
    "MultiModelEnsemble",
    "EnsembleConfig",
    "OOSWalkForwardValidator",
    "WalkForwardConfig",
    "PurgedTimeSeriesCV",
    "RegimeConditionalStrategy",
    "GaussianHMM",
    "RLAgent",
    "TransactionCostAnalyzer",
    "VNSlippageModel",
]
