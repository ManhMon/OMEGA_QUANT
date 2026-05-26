"""
Alpha Ensemble - Institutional Grade Multi-Alpha Integration Engine.

Combines multiple alpha signals into a single consensus score using:
- Rank-based Averaging (Robustness)
- IC-weighted Blending (Performance-aware)
- Regime-Conditional Scaling (Context-aware)

PIT Safety: All operations use T-1 lagged data. No look-ahead bias.
Vectorization: 100% pandas/numpy vectorized. No iterrows/for-loops over rows.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "AlphaEnsemble",
    "AlphaEnsembleConfig",
]

logger = logging.getLogger(__name__)


class AlphaEnsembleConfig:
    """Configuration for alpha ensemble integration."""

    def __init__(
        self,
        alpha_configs: Optional[List[Dict[str, Any]]] = None,
        regime_gate_threshold: float = 0.5,
        min_alphas: int = 2,
    ) -> None:
        """
        Args:
            alpha_configs: List of dicts with keys 'name', 'ic_weight', 'horizon'.
            regime_gate_threshold: Minimum regime confidence to pass signal.
            min_alphas: Minimum number of alphas required for ensemble.
        """
        self.alpha_configs = alpha_configs or []
        self.regime_gate_threshold = regime_gate_threshold
        self.min_alphas = min_alphas


class AlphaEnsemble:
    """
    Multi-alpha ensemble engine.

    Integrates N alpha signals into a single consensus score using
    IC-weighted rank averaging with optional regime-conditional gating.

    PIT Contract:
    - All alpha_series must already be T-1 lagged (shift(1) applied upstream).
    - Regime probabilities must be forward-only filtered (no smoothing).
    - Cross-sectional ranking prevents scale contamination.
    """

    def __init__(self, config: Optional[AlphaEnsembleConfig] = None) -> None:
        self.config = config or AlphaEnsembleConfig()
        self._alpha_configs = self.config.alpha_configs

    def compute_ensemble_score(
        self,
        alpha_series_dict: Dict[str, pd.Series],
        regime_probs: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Integrate multiple alpha series into a single ensemble score.

        STRICTLY PANEL-SAFE: Ranking is performed cross-sectionally (by date).
        100% vectorized - no loops over rows.

        Args:
            alpha_series_dict: Mapping of alpha_name -> pd.Series with
                MultiIndex (date, symbol). Must be T-1 lagged.
            regime_probs: Optional Series indexed by date with regime
                confidence values (forward-only filtered, no look-ahead).

        Returns:
            Final ensemble signal as pd.Series with MultiIndex (date, symbol),
            values in [0, 1] range (cross-sectional percentile rank).
        """
        if len(alpha_series_dict) < self.config.min_alphas:
            raise ValueError(
                f"Need at least {self.config.min_alphas} alphas, "
                f"got {len(alpha_series_dict)}"
            )

        logger.info("Integrating %d alphas into ensemble...", len(alpha_series_dict))

        # 1. Cross-sectional rank each alpha and apply IC weights (vectorized)
        weighted_frames: List[pd.Series] = []
        for name, series in alpha_series_dict.items():
            # Rank across symbols for EACH date (cross-sectional, no look-ahead)
            ranked = series.groupby(level=0).rank(pct=True) - 0.5

            # IC weight lookup
            weight = self._get_alpha_weight(name)
            weighted_frames.append(ranked * weight)

        # 2. Combine alphas via vectorized sum
        ensemble_df = pd.concat(weighted_frames, axis=1)
        ensemble_score = ensemble_df.sum(axis=1)

        # 3. Regime-conditional gating (PIT-safe: forward-only filtered probs)
        if regime_probs is not None:
            ensemble_score = self._apply_regime_gate(ensemble_score, regime_probs)

        # 4. Final cross-sectional rank -> signal in [0, 1]
        final_signal: pd.Series = ensemble_score.groupby(level=0).rank(pct=True)

        return final_signal

    def generate_black_litterman_views(
        self,
        ensemble_signal: pd.Series,
        symbols: List[str],
    ) -> List[Tuple[np.ndarray, float, float]]:
        """
        Convert ensemble signals into Black-Litterman views.

        Format: [(view_vector, expected_return, confidence), ...]

        Args:
            ensemble_signal: Ensemble signal with MultiIndex (date, symbol).
            symbols: Ordered list of symbols for view vector alignment.

        Returns:
            List of (view_vector, expected_return, confidence) tuples.
        """
        views: List[Tuple[np.ndarray, float, float]] = []

        # Center signal around 0.5 (neutral)
        excess_signals = ensemble_signal - 0.5

        for i, symbol in enumerate(symbols):
            if symbol not in excess_signals.index.get_level_values("symbol"):
                continue

            # Get the LATEST signal for this symbol (T-1 lagged upstream)
            symbol_signal = float(
                excess_signals.xs(symbol, level="symbol").iloc[-1]
            )

            # View vector: 1 at the stock's position, 0 elsewhere
            view_v = np.zeros(len(symbols), dtype=np.float64)
            view_v[i] = 1.0

            # Confidence: absolute distance from neutral, scaled to [0, 1]
            conf = float(np.abs(symbol_signal) * 2.0)

            views.append((view_v, symbol_signal, conf))

        return views

    def analyze_ensemble_performance(
        self,
        ensemble_score: pd.Series,
        target_data: pd.Series,
    ) -> Dict[str, float]:
        """
        Compute performance metrics for the combined ensemble signal.

        Args:
            ensemble_score: Ensemble signal series.
            target_data: Forward returns (aligned with ensemble_score).

        Returns:
            Dict with 'ic', 'rank_ic', 'sharpe_proxy'.
        """
        combined = pd.DataFrame(
            {"score": ensemble_score, "target": target_data}
        ).dropna()

        if combined.empty:
            return {"ic": 0.0, "rank_ic": 0.0, "sharpe_proxy": 0.0}

        ic = float(combined["score"].corr(combined["target"]))
        rank_ic = float(
            combined["score"].corr(combined["target"], method="spearman")
        )
        score_std = float(combined["score"].std())

        return {
            "ic": ic,
            "rank_ic": rank_ic,
            "sharpe_proxy": ic / (score_std + 1e-9),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_alpha_weight(self, name: str) -> float:
        """Lookup IC weight for an alpha by name."""
        for cfg in self._alpha_configs:
            if cfg.get("name") == name:
                return float(cfg.get("ic_weight", 1.0))
        return 1.0

    def _apply_regime_gate(
        self,
        ensemble_score: pd.Series,
        regime_probs: pd.Series,
    ) -> pd.Series:
        """
        Apply regime-conditional gating to ensemble score.

        Penalizes signals when regime confidence is below threshold.
        Uses vectorized reindex + where for PIT safety.
        """
        threshold = self.config.regime_gate_threshold

        # Broadcast regime_probs (date-indexed) to MultiIndex (date, symbol)
        regime_broadcasted = regime_probs.reindex(
            ensemble_score.index, level="date"
        )

        # Vectorized gate: zero out signals where confidence < threshold
        gate = regime_broadcasted.where(
            regime_broadcasted >= threshold, 0.0
        )
        return ensemble_score * gate
