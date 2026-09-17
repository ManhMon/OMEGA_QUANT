from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SurvivalFit:
    beta: np.ndarray
    feature_names: list[str]
    baseline_hazard: float


class LiquiditySurvivalModel:
    """Lightweight Cox-style proportional hazard approximation."""

    def __init__(self, lr: float = 0.01, n_iter: int = 400):
        self.lr = lr
        self.n_iter = n_iter
        self.fit_: SurvivalFit | None = None

    def fit(self, X: pd.DataFrame, duration: pd.Series, event: pd.Series) -> "LiquiditySurvivalModel":
        x = X.to_numpy(dtype=float)
        t = duration.to_numpy(dtype=float)
        e = event.to_numpy(dtype=float)
        order = np.argsort(-t)
        x = x[order]
        e = e[order]
        beta = np.zeros(x.shape[1], dtype=float)
        for _ in range(self.n_iter):
            risk = np.exp(x @ beta)
            cum_risk = np.cumsum(risk)
            weighted_x = np.cumsum(x * risk[:, None], axis=0)
            expected = weighted_x / cum_risk[:, None]
            grad = ((x - expected) * e[:, None]).sum(axis=0)
            beta += self.lr * grad / max(len(x), 1)
        baseline_hazard = float(e.sum() / np.clip(t.sum(), 1e-12, None))
        self.fit_ = SurvivalFit(beta=beta, feature_names=list(X.columns), baseline_hazard=baseline_hazard)
        return self

    def predict_hazard(self, X: pd.DataFrame) -> np.ndarray:
        if self.fit_ is None:
            raise ValueError("Model not fit")
        x = X[self.fit_.feature_names].to_numpy(dtype=float)
        return self.fit_.baseline_hazard * np.exp(x @ self.fit_.beta)

    def predict_survival(self, X: pd.DataFrame, horizon: float) -> np.ndarray:
        hazard = self.predict_hazard(X)
        return np.exp(-hazard * horizon)
