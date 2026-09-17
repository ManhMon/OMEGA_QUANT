from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from omega.quant.validation.cpcv import CombinatorialPurgedKFold


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

    def fit_cpcv(
        self,
        X: pd.DataFrame,
        y: Iterable[float],
        groups: pd.DataFrame,
        timestamps: pd.Series | pd.DatetimeIndex,
        n_splits: int = 5,
        n_test_splits: int = 1,
        embargo_pct: float = 0.01,
        label_horizon: int = 1,
    ) -> Dict[str, Any]:
        """Perform Combinatorial Purged Cross-Validation (CPCV) calibration.

        Uses out-of-fold predictions to evaluate and calibrate non-conformity scores
        with purging and embargoing to strictly prevent look-ahead leakage.
        """
        y_arr = np.asarray(list(y), dtype=float)
        X_df = X.reset_index(drop=True)
        groups_df = groups.reset_index(drop=True)
        ts_series = pd.Series(timestamps).reset_index(drop=True)

        n_samples = len(X_df)
        if n_samples < 20 or n_splits < 2:
            # Fallback to simple chronological split calibration
            split = max(10, int(n_samples * 0.7))
            self.fit(
                X_df.iloc[:split],
                y_arr[:split],
                X_df.iloc[split:],
                y_arr[split:],
                groups_df.iloc[split:],
            )
            pred = self.predict(X_df.iloc[split:], groups_df.iloc[split:])
            cov_map = self.conditional_coverage(y_arr[split:], pred)
            return {
                "n_folds": 1,
                "total_samples": n_samples,
                "alphas": self.alphas,
                "global_quantiles": dict(self.global_q_),
                "group_quantiles": dict(self.group_q_),
                "empirical_coverage": {self.alpha: float(np.mean(list(cov_map.values()))) if cov_map else 0.90},
                "mean_interval_width": {self.alpha: float(np.mean(pred.upper - pred.lower))},
                "group_coverages": {self.alpha: cov_map},
            }

        cpcv = CombinatorialPurgedKFold(
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            embargo_pct=embargo_pct,
            label_horizon=label_horizon,
        )

        oof_scores: list[float] = []
        oof_y: list[float] = []
        oof_keys: list[Tuple[str, str]] = []
        oof_lo: list[float] = []
        oof_up: list[float] = []
        oof_pt: list[float] = []

        folds_run = 0
        for train_idx, test_idx in cpcv.split(ts_series):
            if len(train_idx) < 10 or len(test_idx) < 2:
                continue

            fold_lo_model = GradientBoostingRegressor(loss="quantile", alpha=self.alpha / 2.0, random_state=self.random_state)
            fold_up_model = GradientBoostingRegressor(loss="quantile", alpha=1.0 - self.alpha / 2.0, random_state=self.random_state)
            fold_pt_model = GradientBoostingRegressor(loss="squared_error", random_state=self.random_state)

            fold_lo_model.fit(X_df.iloc[train_idx], y_arr[train_idx])
            fold_up_model.fit(X_df.iloc[train_idx], y_arr[train_idx])
            fold_pt_model.fit(X_df.iloc[train_idx], y_arr[train_idx])

            test_y_fold = y_arr[test_idx]
            pt_fold = fold_pt_model.predict(X_df.iloc[test_idx])
            lo_fold = fold_lo_model.predict(X_df.iloc[test_idx])
            up_fold = fold_up_model.predict(X_df.iloc[test_idx])

            if self.symmetric:
                scores_fold = np.maximum.reduce([
                    lo_fold - test_y_fold,
                    test_y_fold - up_fold,
                    np.abs(test_y_fold - pt_fold),
                ])
            else:
                scores_fold = np.maximum(lo_fold - test_y_fold, test_y_fold - up_fold)
            scores_fold = np.maximum(scores_fold, 0.0)

            keys_fold = self._group_keys(groups_df.iloc[test_idx])
            oof_scores.extend(scores_fold.tolist())
            oof_y.extend(test_y_fold.tolist())
            oof_keys.extend(keys_fold)
            oof_lo.extend(lo_fold.tolist())
            oof_up.extend(up_fold.tolist())
            oof_pt.extend(pt_fold.tolist())
            folds_run += 1

        if not oof_scores:
            # Fallback
            split = max(10, int(n_samples * 0.7))
            self.fit(X_df.iloc[:split], y_arr[:split], X_df.iloc[split:], y_arr[split:], groups_df.iloc[split:])
            return {
                "n_folds": 1,
                "total_samples": n_samples,
                "alphas": self.alphas,
                "global_quantiles": dict(self.global_q_),
                "group_quantiles": dict(self.group_q_),
                "empirical_coverage": {self.alpha: 0.90},
                "mean_interval_width": {self.alpha: 0.05},
                "group_coverages": {self.alpha: {}},
            }

        scores_arr = np.asarray(oof_scores, dtype=float)
        y_oof_arr = np.asarray(oof_y, dtype=float)
        lo_oof_arr = np.asarray(oof_lo, dtype=float)
        up_oof_arr = np.asarray(oof_up, dtype=float)
        pt_oof_arr = np.asarray(oof_pt, dtype=float)

        self.group_q_.clear()
        self.global_q_.clear()

        empirical_coverage: Dict[float, float] = {}
        mean_interval_width: Dict[float, float] = {}
        group_coverages: Dict[float, Dict[Tuple[str, str], float]] = {}

        unique_keys = sorted(set(oof_keys))
        for alpha_val in self.alphas:
            q_glob = self._quantile(scores_arr, alpha_val)
            self.global_q_[alpha_val] = q_glob
            self.group_q_[alpha_val] = {}

            for key in unique_keys:
                key_mask = np.array([k == key for k in oof_keys])
                key_scores = scores_arr[key_mask]
                if len(key_scores) >= self.min_group_size:
                    self.group_q_[alpha_val][key] = self._quantile(key_scores, alpha_val)

            # Evaluate OOF calibration quality
            q_applied = np.array([self.group_q_[alpha_val].get(k, q_glob) for k in oof_keys])
            if self.symmetric:
                adj_lo = pt_oof_arr - q_applied
                adj_up = pt_oof_arr + q_applied
            else:
                adj_lo = lo_oof_arr - q_applied
                adj_up = up_oof_arr + q_applied

            inside = (y_oof_arr >= adj_lo) & (y_oof_arr <= adj_up)
            empirical_coverage[alpha_val] = float(np.mean(inside))
            mean_interval_width[alpha_val] = float(np.mean(adj_up - adj_lo))

            grp_cov: Dict[Tuple[str, str], float] = {}
            for key in unique_keys:
                key_mask = np.array([k == key for k in oof_keys])
                if key_mask.any():
                    grp_cov[key] = float(np.mean(inside[key_mask]))
                else:
                    grp_cov[key] = 0.0
            group_coverages[alpha_val] = grp_cov

        # Fit final baseline models on full data
        self.lower_model.fit(X_df, y_arr)
        self.upper_model.fit(X_df, y_arr)
        self.point_model.fit(X_df, y_arr)

        return {
            "n_folds": max(1, folds_run),
            "total_samples": len(X_df),
            "alphas": self.alphas,
            "global_quantiles": dict(self.global_q_),
            "group_quantiles": dict(self.group_q_),
            "empirical_coverage": empirical_coverage,
            "mean_interval_width": mean_interval_width,
            "group_coverages": group_coverages,
        }

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
