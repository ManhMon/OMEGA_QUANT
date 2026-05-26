"""omega.quant.continuous_learning - compatibility shim"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class ContinuousLearningConfig:
    learning_rate: float = 0.01
    window_size: int = 252
    min_samples: int = 60
    retrain_threshold: float = 0.02
    champion_ic_threshold: float = 0.02

class TrainableModel:
    def fit(self, X, y, **kwargs): pass
    def predict(self, X, **kwargs): return None
    def update(self, X, y, **kwargs): pass

class DecayMonitor:
    def check(self, *args, **kwargs): return False

class ContinuousLearningEngine:
    def __init__(self, config: ContinuousLearningConfig = None, model_factory=None):
        self.config = config or ContinuousLearningConfig()
        self.model_factory = model_factory
        self.champion: Optional[TrainableModel] = None
        self.decay_monitor = DecayMonitor()
        self._retrain_count = 0
        self._last_retrain_date = None

    def update(self, *args, **kwargs): pass
    def predict(self, *args, **kwargs): return None

    def monitor_and_retrain(self, current_date, features, targets) -> Dict[str, Any]:
        return {
            'retrain_triggered': False,
            'retrain_reason': '',
            'promotion_decision': ''
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            'champion_exists': self.champion is not None,
            'last_retrain_date': self._last_retrain_date,
            'retrain_count': self._retrain_count
        }

ContinuousLearner = ContinuousLearningEngine
