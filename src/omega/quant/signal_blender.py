"""
Signal Blender - V21 Institutional
Normalizes and blends signals from multiple models.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class BlendedSignal:
    """Result of signal blending."""
    final_scores: Dict[str, float]        # symbol -> final blended score
    model_contributions: Dict[str, Dict[str, float]]  # model -> {symbol: contribution}
    weights_used: Dict[str, float]        # model -> weight used


class SignalBlender:
    """Blend signals from multiple models into a single score per symbol.

    Steps:
    1. Normalize each model's scores (z-score or rank)
    2. Winsorize outliers
    3. Apply ensemble weights
    4. Produce final blended signal
    """

    def __init__(
        self,
        normalization: str = "zscore",  # "zscore" | "rank" | "minmax"
        winsorize_pct: float = 0.01     # Clip at 1% / 99%
    ):
        self.normalization = normalization
        self.winsorize_pct = winsorize_pct

    def _normalize_zscore(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to z-score."""
        values = np.array(list(scores.values()))
        if len(values) < 2 or np.std(values) < 1e-10:
            return {s: 0.0 for s in scores}
        mean_v = np.mean(values)
        std_v = np.std(values)
        return {s: (v - mean_v) / std_v for s, v in scores.items()}

    def _normalize_rank(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to percentile rank [0, 1]."""
        symbols = list(scores.keys())
        values = np.array([scores[s] for s in symbols])
        n = len(values)
        if n == 0:
            return {}
        ranks = np.argsort(np.argsort(values)).astype(float)
        ranks = ranks / max(1, n - 1)  # Scale to [0, 1]
        return {s: float(r) for s, r in zip(symbols, ranks)}

    def _normalize_minmax(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to [0, 1] using min-max."""
        values = np.array(list(scores.values()))
        if len(values) == 0:
            return {}
        vmin, vmax = np.min(values), np.max(values)
        if vmax - vmin < 1e-10:
            return {s: 0.5 for s in scores}
        return {s: (v - vmin) / (vmax - vmin) for s, v in scores.items()}

    def _normalize(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Apply selected normalization method."""
        if self.normalization == "zscore":
            return self._normalize_zscore(scores)
        elif self.normalization == "rank":
            return self._normalize_rank(scores)
        elif self.normalization == "minmax":
            return self._normalize_minmax(scores)
        return scores

    def _winsorize(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Clip extreme values to reduce outlier impact."""
        values = np.array(list(scores.values()))
        if len(values) < 5:
            return scores
        low = np.percentile(values, self.winsorize_pct * 100)
        high = np.percentile(values, (1 - self.winsorize_pct) * 100)
        return {s: float(np.clip(v, low, high)) for s, v in scores.items()}

    def blend(
        self,
        model_scores: Dict[str, Dict[str, float]],
        weights: Dict[str, float]
    ) -> BlendedSignal:
        """Blend multiple model signals into final score.

        Args:
            model_scores: Dict of model_name -> {symbol: raw_score}
            weights: Dict of model_name -> weight (sum=1)

        Returns:
            BlendedSignal with final scores
        """
        if not model_scores or not weights:
            return BlendedSignal(final_scores={}, model_contributions={}, weights_used=weights)

        # 1. Normalize each model's scores
        normalized: Dict[str, Dict[str, float]] = {}
        for model_name, scores in model_scores.items():
            norm = self._normalize(scores)
            norm = self._winsorize(norm)
            normalized[model_name] = norm

        # 2. Get all symbols
        all_symbols = set()
        for scores in normalized.values():
            all_symbols.update(scores.keys())

        # 3. Weighted blend
        final_scores: Dict[str, float] = {}
        contributions: Dict[str, Dict[str, float]] = {m: {} for m in model_scores}

        for symbol in all_symbols:
            weighted_sum = 0.0
            total_weight = 0.0
            for model_name, scores in normalized.items():
                w = weights.get(model_name, 0.0)
                score = scores.get(symbol, 0.0)
                contribution = w * score
                weighted_sum += contribution
                total_weight += w
                contributions[model_name][symbol] = contribution

            final_scores[symbol] = weighted_sum / total_weight if total_weight > 0 else 0.0

        return BlendedSignal(
            final_scores=final_scores,
            model_contributions=contributions,
            weights_used=weights
        )
