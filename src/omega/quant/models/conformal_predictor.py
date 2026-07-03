from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor


@dataclass
class ConformalPrediction:
    lower: np.ndarray
    upper: np.ndarray
    point: np.ndarray
    groups: list[Tuple[str, str]]


class ConformalTrendPredictor:
    """CQR-style predictor with Mondrian conformalization by (regime, liquidity)."""

    def __init__(self, alpha: float = 0.2, min_group_size: int = 25, random_state: int = 42, symmetric: bool = False, alphas: list[float] | None = None):
        self.alpha = alpha
        self.alphas = sorted(set(alphas or [alpha]), reverse=True)
        self.min_group_size = min_group_size
        self.random_state = random_state
        self.lower_model = GradientBoostingRegressor(loss="quantile", alpha=alpha / 2.0, random_state=random_state)
        self.upper_model = GradientBoostingRegressor(loss="quantile", alpha=1.0 - alpha / 2.0, random_state=random_state)
        self.point_model = GradientBoostingRegressor(loss="squared_error", random_state=random_state)
        self.symmetric = symmetric
        self.group_q_: Dict[float, Dict[Tuple[str, str], float]] = {}
        self.global_q_: Dict[float, float] = {}

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: Iterable[float],
        X_calib: pd.DataFrame,
        y_calib: Iterable[float],
        calib_groups: pd.DataFrame,
    ) -> "ConformalTrendPredictor":
        y_train_arr = np.asarray(list(y_train), dtype=float)
        y_calib_arr = np.asarray(list(y_calib), dtype=float)
        self.lower_model.fit(X_train, y_train_arr)
        self.upper_model.fit(X_train, y_train_arr)
        self.point_model.fit(X_train, y_train_arr)

        point = self.point_model.predict(X_calib)
        lower = self.lower_model.predict(X_calib)
        upper = self.upper_model.predict(X_calib)
        if self.symmetric:
            scores = np.maximum.reduce([
                lower - y_calib_arr,
                y_calib_arr - upper,
                np.abs(y_calib_arr - point),
            ])
        else:
            scores = np.maximum(lower - y_calib_arr, y_calib_arr - upper)
        scores = np.maximum(scores, 0.0)
        keys = self._group_keys(calib_groups)
        self.group_q_.clear()
        self.global_q_.clear()
        for alpha in self.alphas:
            self.global_q_[alpha] = self._quantile(scores, alpha)
            self.group_q_[alpha] = {}
            for key in sorted(set(keys)):
                group_scores = scores[np.array([k == key for k in keys])]
                if len(group_scores) >= self.min_group_size:
                    self.group_q_[alpha][key] = self._quantile(group_scores, alpha)
        return self

    def predict(self, X: pd.DataFrame, groups: pd.DataFrame, alpha: float | None = None) -> ConformalPrediction:
        point = self.point_model.predict(X)
        lower = self.lower_model.predict(X)
        upper = self.upper_model.predict(X)
        keys = self._group_keys(groups)
        alpha_value = alpha or self.alpha
        q = np.array([self.group_q_.get(alpha_value, {}).get(key, self.global_q_.get(alpha_value, 0.0)) for key in keys], dtype=float)
        if self.symmetric:
            lower_adj = point - q
            upper_adj = point + q
        else:
            lower_adj = lower - q
            upper_adj = upper + q
        return ConformalPrediction(lower=lower_adj, upper=upper_adj, point=point, groups=keys)

    def predict_multi(self, X: pd.DataFrame, groups: pd.DataFrame) -> Dict[float, ConformalPrediction]:
        return {alpha: self.predict(X, groups, alpha=alpha) for alpha in self.alphas}

    def conditional_coverage(self, y_true: Iterable[float], pred: ConformalPrediction) -> Dict[Tuple[str, str], float]:
        y = np.asarray(list(y_true), dtype=float)
        inside = (y >= pred.lower) & (y <= pred.upper)
        result: Dict[Tuple[str, str], float] = {}
        for key in sorted(set(pred.groups)):
            mask = np.array([g == key for g in pred.groups])
            result[key] = float(inside[mask].mean()) if mask.any() else 0.0
        return result

    def _group_keys(self, groups: pd.DataFrame) -> list[Tuple[str, str]]:
        return list(zip(groups["regime"].astype(str), groups["liquidity_bucket"].astype(str)))

    def _quantile(self, scores: np.ndarray, alpha: float) -> float:
        if len(scores) == 0:
            return 0.0
        level = min(1.0, np.ceil((len(scores) + 1) * (1.0 - alpha)) / len(scores))
        return float(np.quantile(scores, level, method="higher"))
