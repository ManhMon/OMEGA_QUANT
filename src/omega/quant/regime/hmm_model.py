"""Gaussian-mixture regime model with deterministic 4-state labeling.

Labels:
0 = Bear-Calm
1 = Bear-Volatile
2 = Bull-Calm
3 = Bull-Volatile
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

REGIME_BEAR_CALM = 0
REGIME_BEAR_VOLATILE = 1
REGIME_BULL_CALM = 2
REGIME_BULL_VOLATILE = 3
REGIME_LOCK_DAYS = 5


@dataclass(slots=True)
class HMMModelConfig:
    n_components: int = 4
    covariance_type: str = "full"
    n_init: int = 10
    max_iter: int = 200
    random_state: int = 42
    min_training_samples: int = 40
    feature_columns: list[str] = field(
        default_factory=lambda: ["market_return", "market_volatility"]
    )
    return_column: str = "market_return"
    volatility_column: str = "market_volatility"
    regime_lock_days: int = REGIME_LOCK_DAYS


def build_stable_regime_map(
    state_mean_returns: dict[int, float],
    state_mean_volatility: dict[int, float],
) -> dict[int, int]:
    """Map raw state ids to stable 4-state semantic labels."""
    raw_state_ids = sorted(state_mean_returns)
    if len(raw_state_ids) != 4 or set(raw_state_ids) != set(state_mean_volatility):
        raise ValueError("Expected exactly 4 aligned states for stable regime mapping")

    by_return = sorted(
        raw_state_ids,
        key=lambda raw_state_id: (state_mean_returns[raw_state_id], raw_state_id),
    )
    bear_state_ids = sorted(
        by_return[:2],
        key=lambda raw_state_id: (state_mean_volatility[raw_state_id], raw_state_id),
    )
    bull_state_ids = sorted(
        by_return[2:],
        key=lambda raw_state_id: (state_mean_volatility[raw_state_id], raw_state_id),
    )
    return {
        bear_state_ids[0]: REGIME_BEAR_CALM,
        bear_state_ids[1]: REGIME_BEAR_VOLATILE,
        bull_state_ids[0]: REGIME_BULL_CALM,
        bull_state_ids[1]: REGIME_BULL_VOLATILE,
    }


def apply_regime_lock(raw_regimes: np.ndarray, min_duration: int = REGIME_LOCK_DAYS) -> np.ndarray:
    """Only allow state changes after prior active state held for min_duration bars."""
    regimes = np.asarray(raw_regimes, dtype=int)
    if regimes.size == 0:
        return regimes.copy()

    locked = regimes.copy()
    active_regime = int(regimes[0])
    active_duration = 1
    locked[0] = active_regime
    for idx in range(1, regimes.size):
        candidate = int(regimes[idx])
        if candidate == active_regime:
            active_duration += 1
            locked[idx] = active_regime
            continue
        if active_duration >= min_duration:
            active_regime = candidate
            active_duration = 1
        else:
            active_duration += 1
        locked[idx] = active_regime
    return locked


class GaussianHMM4State:
    """GaussianMixture-backed 4-state regime detector.

    PIT-safe sequence inference: prediction for bar T uses features from T-1.
    """

    def __init__(self, config: HMMModelConfig | None = None):
        self.config = config or HMMModelConfig()
        if self.config.n_components != 4:
            raise ValueError("GaussianHMM4State requires n_components=4")
        self.model = GaussianMixture(
            n_components=self.config.n_components,
            covariance_type=self.config.covariance_type,
            n_init=self.config.n_init,
            max_iter=self.config.max_iter,
            random_state=self.config.random_state,
        )
        self.is_fitted = False
        self.regime_map_: dict[int, int] = {}
        self.state_mean_returns_: dict[int, float] = {}
        self.state_mean_volatility_: dict[int, float] = {}

    def fit(self, features: pd.DataFrame) -> "GaussianHMM4State":
        cols = self._required_columns()
        frame = features.loc[:, cols].dropna().copy()
        if len(frame) < self.config.min_training_samples:
            raise ValueError(
                f"Insufficient training samples for GaussianHMM4State: {len(frame)} < {self.config.min_training_samples}"
            )

        self.model.fit(frame.to_numpy(dtype=float))
        raw_states = self.model.predict(frame.to_numpy(dtype=float))
        state_series = pd.Series(raw_states, index=frame.index, name="raw_state_id")
        mean_returns = frame[self.config.return_column].groupby(state_series).mean()
        mean_volatility = frame[self.config.volatility_column].groupby(state_series).mean()

        state_mean_returns = {
            raw_state_id: float(mean_returns.get(raw_state_id, frame[self.config.return_column].mean()))
            for raw_state_id in range(self.config.n_components)
        }
        state_mean_volatility = {
            raw_state_id: float(mean_volatility.get(raw_state_id, frame[self.config.volatility_column].mean()))
            for raw_state_id in range(self.config.n_components)
        }

        self.state_mean_returns_ = state_mean_returns
        self.state_mean_volatility_ = state_mean_volatility
        self.regime_map_ = build_stable_regime_map(state_mean_returns, state_mean_volatility)
        self.is_fitted = True
        return self

    def fit_predict(self, features: pd.DataFrame) -> pd.Series:
        self.fit(features)
        return self.predict_sequence(features)

    def predict_raw_states(self, features: pd.DataFrame) -> np.ndarray:
        self._ensure_fitted()
        frame = self._prepare_features(features)
        return self.model.predict(frame.to_numpy(dtype=float))

    def predict_sequence(self, features: pd.DataFrame) -> pd.Series:
        """Return locked semantic regimes for bar T from features at T-1."""
        raw_states = self.predict_raw_states(features)
        mapped = np.array([self.regime_map_[int(raw_state_id)] for raw_state_id in raw_states], dtype=int)
        locked = apply_regime_lock(mapped, min_duration=self.config.regime_lock_days)
        result = pd.Series(locked, index=self._prepare_features(features).index, name="regime")
        return result.shift(1)

    def predict_next(self, features_t_minus_1: pd.DataFrame) -> int:
        """Predict a single active regime from T-1 features only."""
        raw_state_id = int(self.predict_raw_states(features_t_minus_1.tail(1))[0])
        return self.regime_map_[raw_state_id]

    def _required_columns(self) -> list[str]:
        required = list(dict.fromkeys([*self.config.feature_columns, self.config.return_column, self.config.volatility_column]))
        missing = [col for col in required if col not in self.config.feature_columns and col not in required]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return required

    def _prepare_features(self, features: pd.DataFrame) -> pd.DataFrame:
        cols = self._required_columns()
        missing = [col for col in cols if col not in features.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return features.loc[:, cols].dropna()

    def _ensure_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError("GaussianHMM4State must be fitted before prediction")
