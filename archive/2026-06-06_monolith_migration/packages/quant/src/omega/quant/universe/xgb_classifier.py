"""
OMEGA_QUANT Universe Classifier (Phase 1.2)
Layer 02: Strategy Logic - Universe Selection

XGBoost-based binary classifier that scores tickers on their probability of
being a "top performer" in the next horizon. Used to filter a large investable
universe down to the top-N candidates per rebalance date.

PIT Safety:
- Caller is responsible for providing PIT-safe features (shift(1) applied upstream).
- This module performs no time-series transformation; it is a pure cross-sectional
  classifier wrapper. Features in -> probabilities out.

Performance:
- 100% vectorized. predict_proba is a single XGBoost batch call.
- select_universe relies on numpy argpartition (O(n)) for top-N selection.

Adapted from: V21_QUANT universe selection patterns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

logger = logging.getLogger(__name__)


class UniverseClassifier:
    """
    XGBoost binary classifier for universe selection.

    The positive class (label=1) represents "top performer" in the labeling
    horizon used by the caller (e.g. top-quintile forward return). The model
    outputs P(top_performer) per row, which is then used to rank and select
    the top-N tickers per date.

    Attributes:
        model: Underlying xgboost.XGBClassifier instance.
        feature_cols: Ordered list of feature column names captured at fit time.
        is_trained: True once `fit` has completed.
    """

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        early_stopping_rounds: int = 20,
        random_state: int = 42,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.early_stopping_rounds = early_stopping_rounds
        self.random_state = random_state

        self.model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            objective="binary:logistic",
            eval_metric="auc",
            tree_method="hist",
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
        )
        self.feature_cols: List[str] = []
        self.is_trained: bool = False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        eval_set: Optional[Sequence[Tuple[pd.DataFrame, pd.Series]]] = None,
    ) -> "UniverseClassifier":
        """
        Train the classifier.

        Args:
            X: Feature matrix (n_samples x n_features). Column order is captured
               and re-applied on every predict call.
            y: Binary labels in {0, 1}. Length must match len(X).
            eval_set: Optional [(X_val, y_val)] used for early stopping. When
               provided, early_stopping_rounds is honored.

        Returns:
            self (sklearn convention).
        """
        if X is None or len(X) == 0:
            logger.warning("UniverseClassifier.fit called with empty X; skipping training.")
            return self
        if len(X) != len(y):
            raise ValueError(f"X and y length mismatch: {len(X)} vs {len(y)}")

        self.feature_cols = list(X.columns)

        fit_kwargs = {}
        if eval_set is not None and len(eval_set) > 0:
            # XGBoost >= 2.0 expects early_stopping_rounds via constructor.
            self.model.set_params(early_stopping_rounds=self.early_stopping_rounds)
            # Align eval_set columns to training columns to keep feature names consistent.
            aligned_eval = [
                (Xe.reindex(columns=self.feature_cols), np.asarray(ye))
                for Xe, ye in eval_set
            ]
            fit_kwargs["eval_set"] = aligned_eval
            fit_kwargs["verbose"] = False

        logger.info(
            "Training UniverseClassifier: n_samples=%d, n_features=%d, eval_set=%s",
            len(X),
            X.shape[1],
            "yes" if eval_set else "no",
        )
        # Pass the DataFrame (not .values) so XGBoost records feature names and
        # can validate eval_set + future predict_proba inputs consistently.
        self.model.fit(X, np.asarray(y), **fit_kwargs)
        self.is_trained = True
        return self

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Return P(top_performer) for each row.

        Args:
            X: Feature matrix. Columns are reindexed to the training order.

        Returns:
            1-D numpy array of shape (n_samples,) with probabilities in [0, 1].
        """
        if not self.is_trained:
            raise RuntimeError("UniverseClassifier.predict_proba called before fit.")
        if X is None or len(X) == 0:
            return np.empty(0, dtype=float)

        X_aligned = X.reindex(columns=self.feature_cols)
        proba = self.model.predict_proba(X_aligned)
        # Column 1 is the positive class probability.
        return proba[:, 1] if proba.ndim == 2 and proba.shape[1] == 2 else proba.ravel()

    def select_universe(self, X: pd.DataFrame, n: int = 50) -> pd.Index:
        """
        Return the index of the top-N rows by predicted probability.

        Vectorized via numpy.argpartition (O(n)) followed by a small sort over
        the top-N slice (O(n log n) only on the top-N).

        Args:
            X: Feature matrix indexed by ticker (or any unique key).
            n: Number of tickers to select.

        Returns:
            pd.Index of the top-N row labels, ordered by descending probability.
        """
        if X is None or len(X) == 0:
            return pd.Index([], name=getattr(X, "index", pd.Index([])).name)
        n = max(0, min(int(n), len(X)))
        if n == 0:
            return X.index[:0]

        proba = self.predict_proba(X)
        # argpartition gets top-N (unordered), then sort just those N descending.
        top_idx = np.argpartition(-proba, n - 1)[:n]
        top_sorted = top_idx[np.argsort(-proba[top_idx])]
        return X.index[top_sorted]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def feature_importance(self) -> pd.DataFrame:
        """
        Return feature importances as a DataFrame sorted descending.

        Returns:
            DataFrame with columns ['feature', 'importance'].
        """
        if not self.is_trained:
            return pd.DataFrame(columns=["feature", "importance"])

        importances = np.asarray(self.model.feature_importances_, dtype=float)
        df = pd.DataFrame({"feature": self.feature_cols, "importance": importances})
        return df.sort_values("importance", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: str) -> None:
        """Persist the full classifier (model + metadata) via joblib."""
        if not self.is_trained:
            logger.warning("Saving an untrained UniverseClassifier to %s", path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("UniverseClassifier saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "UniverseClassifier":
        """Load a persisted classifier from disk."""
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Loaded object is not a UniverseClassifier: {type(obj)}")
        logger.info("UniverseClassifier loaded from %s", path)
        return obj
