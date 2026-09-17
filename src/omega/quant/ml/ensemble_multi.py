"""PIT-safe multi-model alpha ensemble.

Combines XGBoost, LightGBM, RandomForest, and Ridge regressors with train-only
IC weights. Optional dependencies degrade by skipping unavailable models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MultiModelEnsembleResult:
    predictions: pd.Series
    weights: Dict[str, float] = field(default_factory=dict)
    train_ics: Dict[str, float] = field(default_factory=dict)
    active_models: List[str] = field(default_factory=list)


class MultiModelAlphaEnsemble:
    """XGBoost + LightGBM + RandomForest + Ridge alpha ensemble."""

    def __init__(self, min_ic_threshold: float = 0.0, random_state: int = 42):
        self.min_ic_threshold = min_ic_threshold
        self.random_state = random_state
        self.models: Dict[str, Any] = {}
        self.feature_cols: List[str] = []
        self.weights: Dict[str, float] = {}
        self.train_ics: Dict[str, float] = {}
        self._winsor_lower: Optional[pd.Series] = None
        self._winsor_upper: Optional[pd.Series] = None

    def _prepare_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        mkt_prices = df.unstack(level="symbol")["close"].ffill()
        index_proxy = mkt_prices.mean(axis=1)
        mkt_vol = index_proxy.pct_change().rolling(20).std().shift(1)
        mkt_ret = index_proxy.pct_change(20).shift(1)
        dates = df.index.get_level_values("date")
        df["mkt_vol_20d"] = mkt_vol.reindex(dates).values
        df["mkt_ret_20d"] = mkt_ret.reindex(dates).values
        df[["mkt_vol_20d", "mkt_ret_20d"]] = df[["mkt_vol_20d", "mkt_ret_20d"]].ffill().fillna(0)
        return df

    def _clean_features(self, X: pd.DataFrame, fit: bool) -> pd.DataFrame:
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if fit:
            self._winsor_lower = X.quantile(0.01)
            self._winsor_upper = X.quantile(0.99)
        if self._winsor_lower is not None and self._winsor_upper is not None:
            X = X.clip(lower=self._winsor_lower, upper=self._winsor_upper, axis=1)
        return X

    @staticmethod
    def _ic(pred: pd.Series, actual: pd.Series) -> float:
        aligned = pd.DataFrame({"pred": pred, "actual": actual}).dropna()
        if len(aligned) < 10:
            return 0.0
        ic = aligned["pred"].corr(aligned["actual"], method="spearman")
        return 0.0 if pd.isna(ic) else float(ic)

    def _candidate_models(self) -> Dict[str, Any]:
        models: Dict[str, Any] = {}
        try:
            from xgboost import XGBRegressor
            models["xgboost"] = XGBRegressor(
                objective="reg:squarederror",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.03,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                tree_method="hist",
            )
        except ImportError:
            logger.info("XGBoost unavailable; skipping in multi-model ensemble")

        try:
            from lightgbm import LGBMRegressor
            models["lightgbm"] = LGBMRegressor(
                objective="regression",
                n_estimators=120,
                max_depth=4,
                learning_rate=0.03,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                verbosity=-1,
            )
        except ImportError:
            logger.info("LightGBM unavailable; skipping in multi-model ensemble")

        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.linear_model import Ridge
            models["random_forest"] = RandomForestRegressor(
                n_estimators=120,
                max_depth=6,
                min_samples_leaf=10,
                random_state=self.random_state,
                n_jobs=-1,
            )
            models["ridge"] = Ridge(alpha=1.0)
        except ImportError:
            logger.info("scikit-learn unavailable; skipping RF/Ridge in multi-model ensemble")
        return models

    def train(self, df: pd.DataFrame, alpha_cols: List[str], cutoff_date: str, embargo_days: int = 0) -> None:
        df = self._prepare_regime_features(df)
        df["target_fwd_ret"] = df.groupby(level="symbol")["close"].transform(lambda x: x.pct_change(5).shift(-5))
        self.feature_cols = alpha_cols + ["mkt_vol_20d", "mkt_ret_20d"]
        train_data = df.dropna(subset=self.feature_cols + ["target_fwd_ret"]).copy()
        cutoff_ts = pd.Timestamp(cutoff_date) - pd.Timedelta(days=embargo_days)
        train_data = train_data[train_data.index.get_level_values("date") <= cutoff_ts].sort_index(level="date")
        if train_data.empty:
            raise ValueError("No multi-model ensemble training data before cutoff")

        X = self._clean_features(train_data[self.feature_cols], fit=True)
        y = train_data["target_fwd_ret"]
        for name, model in self._candidate_models().items():
            try:
                model.fit(X, y)
                pred = pd.Series(model.predict(X), index=X.index)
                ic = self._ic(pred.shift(1), y)
                if ic >= self.min_ic_threshold:
                    self.models[name] = model
                    self.train_ics[name] = ic
            except Exception as exc:  # pragma: no cover - optional model failures
                logger.warning("Multi-model component %s failed: %s", name, exc)

        if not self.models:
            raise ValueError("No multi-model ensemble components passed training")
        positive = {k: max(v, 0.0) for k, v in self.train_ics.items()}
        total = sum(positive.values())
        self.weights = {k: (v / total if total > 0 else 1.0 / len(positive)) for k, v in positive.items()}

    def predict(self, df: pd.DataFrame, alpha_cols: List[str]) -> MultiModelEnsembleResult:
        if not self.models:
            base = df[alpha_cols].mean(axis=1)
            return MultiModelEnsembleResult(base, {}, {}, [])
        df = self._prepare_regime_features(df)
        X = self._clean_features(df[self.feature_cols], fit=False)
        weighted = []
        for name, model in self.models.items():
            pred = pd.Series(model.predict(X), index=X.index)
            std = pred.std(ddof=0)
            pred = (pred - pred.mean()) / std if std and not np.isnan(std) else pred * 0.0
            weighted.append(pred * self.weights.get(name, 0.0))
        predictions = sum(weighted) if weighted else pd.Series(0.0, index=df.index)
        return MultiModelEnsembleResult(predictions, dict(self.weights), dict(self.train_ics), list(self.models))
