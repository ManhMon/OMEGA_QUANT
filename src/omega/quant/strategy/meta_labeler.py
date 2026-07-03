from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


@dataclass
class MetaLabelResult:
    labels: pd.Series
    probabilities: pd.Series


class MetaLabeler:
    def __init__(self, threshold: float = 0.5, random_state: int = 42):
        self.threshold = threshold
        self.model = LogisticRegression(random_state=random_state, max_iter=200)

    def fit(self, X: pd.DataFrame, primary_side: pd.Series, realized_return: pd.Series) -> "MetaLabeler":
        y = ((primary_side.astype(float) * realized_return.astype(float)) > 0).astype(int)
        self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> MetaLabelResult:
        prob = self.model.predict_proba(X)[:, 1]
        labels = (prob >= self.threshold).astype(int)
        return MetaLabelResult(labels=pd.Series(labels, index=X.index), probabilities=pd.Series(prob, index=X.index))
