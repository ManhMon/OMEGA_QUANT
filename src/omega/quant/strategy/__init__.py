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
