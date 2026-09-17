"""Ensemble configurations and structures.

Defines the WeightingScheme, MetaLearnerType, EnsembleConfig,
BaseModelPrediction, and EnsembleResult classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
import pandas as pd


class WeightingScheme(Enum):
    """Weighting schemes for voting ensemble."""
    UNIFORM = "uniform"           # Equal weights
    IC_WEIGHTED = "ic_weighted"   # Weighted by IC
    SHARPE_WEIGHTED = "sharpe_weighted"  # Weighted by Sharpe
    INVERSE_VARIANCE = "inverse_variance"  # Weighted by inverse variance


class MetaLearnerType(Enum):
    """Meta-learner types for stacking."""
    RIDGE = "ridge"
    RANDOM_FOREST = "random_forest"
    XGBOOST = "xgboost"


@dataclass
class EnsembleConfig:
    """Configuration for ensemble methods."""
    
    # Voting config
    weighting_scheme: WeightingScheme = WeightingScheme.IC_WEIGHTED
    min_ic_threshold: float = 0.05
    max_weight: float = 0.6
    min_weight: float = 0.0
    
    # Stacking config
    meta_learner_type: MetaLearnerType = MetaLearnerType.RIDGE
    use_meta_features: bool = True
    cv_folds: int = 5
    
    # PIT safety
    embargo_days: int = 3
    
    # Training
    train_cutoff: str = "2023-12-31"
    validation_start: str = "2024-01-01"


@dataclass
class BaseModelPrediction:
    """Container for base model predictions."""
    model_name: str
    predictions: pd.Series
    ic: float = 0.0
    sharpe: float = 0.0
    variance: float = 0.0
    is_oos: bool = False
    train_end: Optional[pd.Timestamp] = None
    prediction_start: Optional[pd.Timestamp] = None
    generator_id: Optional[str] = None


@dataclass
class EnsembleResult:
    """Result from ensemble prediction."""
    predictions: pd.Series
    weights: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    meta_features: Optional[pd.DataFrame] = None
