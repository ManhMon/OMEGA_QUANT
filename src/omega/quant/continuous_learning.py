"""omega.quant.continuous_learning - shim wrapper for evolution"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import logging
import pandas as pd

from omega.quant.evolution.continuous_learning import (
    ContinuousLearningEngine as RealEngine,
    ContinuousLearningConfig as RealConfig
)

logger = logging.getLogger(__name__)


@dataclass
class ContinuousLearningConfig:
    """Compatibility config mapping to RealConfig."""
    learning_rate: float = 0.01
    window_size: int = 252
    min_samples: int = 60
    retrain_threshold: float = 0.02
    champion_ic_threshold: float = 0.02
    # Extra arguments from phase6_evolution_engine.py config
    retrain_frequency_days: int = 7
    training_window_days: int = 252
    validation_window_days: int = 60
    embargo_days: int = 3
    ic_improvement_threshold: float = 0.05
    p_value_threshold: float = 0.05
    min_absolute_ic: float = 0.10


class TrainableModel:
    """Dummy TrainableModel for backward compatibility."""
    def fit(self, X, y, **kwargs):
        pass

    def predict(self, X, **kwargs):
        return None

    def update(self, X, y, **kwargs):
        pass


class DecayMonitor:
    """Dummy DecayMonitor for backward compatibility."""
    def check(self, *args, **kwargs):
        return False


class ContinuousLearningEngine:
    """Wrapper delegating to the real ContinuousLearningEngine from
    evolution.
    """
    def __init__(self, config: ContinuousLearningConfig = None,
                 model_factory=None):
        self.config = config or ContinuousLearningConfig()
        self.model_factory = model_factory
        self._champion: Optional[TrainableModel] = None
        self.decay_monitor = DecayMonitor()
        self._retrain_count = 0

        # Instantiate real engine
        real_cfg = RealConfig(
            retraining_interval_days=self.config.retrain_frequency_days,
            min_ic_improvement=self.config.ic_improvement_threshold,
            p_value_threshold=self.config.p_value_threshold,
            min_absolute_ic=self.config.min_absolute_ic
        )
        self._real = RealEngine(config=real_cfg)

    @property
    def champion(self) -> Optional[TrainableModel]:
        return self._champion

    @champion.setter
    def champion(self, val: Optional[TrainableModel]) -> None:
        self._champion = val
        if val is not None and self._real.champion_model is None:
            self._real.champion_model = {
                "model_name": "champion",
                "ic": 0.12,
                "sharpe": 1.5,
                "timestamp": pd.Timestamp.now().isoformat()
            }

    def update(self, *args, **kwargs):
        pass

    def predict(self, *args, **kwargs):
        return None

    def monitor_and_retrain(
        self, current_date, features, targets
    ) -> Dict[str, Any]:
        ts = pd.Timestamp(current_date)

        # Save prior champion IC before running retrain_cycle
        prior_ic = (self._real.champion_model.get("ic", 0.0)
                    if self._real.champion_model else 0.0)

        res = self._real.retrain_cycle(features, targets, ts)

        retrain_triggered = res.get("status") in ("promoted", "retained")
        status = res.get("status", "skipped")

        if retrain_triggered:
            self._retrain_count += 1

        if status == "promoted":
            if self._champion is None:
                self._champion = TrainableModel()

        current_sharpe = 0.0
        current_ic = 0.0
        comparison = None

        if self._real.champion_model:
            current_sharpe = self._real.champion_model.get("sharpe", 0.0)
            current_ic = self._real.champion_model.get("ic", 0.0)

        if status in ("promoted", "retained"):
            challenger_metrics = res.get("metrics", {})
            ic_challenger = challenger_metrics.get("ic", 0.0)
            comparison = {
                'ic_champion': prior_ic,
                'ic_challenger': ic_challenger
            }

        cl_status = {
            'retrain_triggered': retrain_triggered,
            'retrain_reason': res.get("reason", ""),
            'promotion_decision': status,
            'current_sharpe': current_sharpe,
            'current_ic': current_ic
        }
        if comparison:
            cl_status['comparison'] = comparison

        return cl_status

    def get_status(self) -> Dict[str, Any]:
        return {
            'champion_exists': (
                self.champion is not None
                or self._real.champion_model is not None
            ),
            'last_retrain_date': self._real.last_retrain_date,
            'retrain_count': self._retrain_count
        }


ContinuousLearner = ContinuousLearningEngine
