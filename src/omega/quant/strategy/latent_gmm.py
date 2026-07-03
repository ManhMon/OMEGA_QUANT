"""Latent GMM Regime Clustering on Autoencoder Latent Space.

Gate: HYBRID_REGIME_DETECTION_20260619

Clusters market observations in the Latent AE space
(``latent_ae_00``, ``latent_ae_01``, ``latent_ae_11``) using a Gaussian
Mixture Model. Provides ex-ante regime labels and exposure-routing
multipliers for the RiskSizingOverlay.

PIT Safety
----------
- ``fit()`` only uses historical data (caller must ensure T-1 cutoff).
- ``predict_regime()`` / ``predict_proba()`` are pure inference on a
  frozen model — no data leakage.
- ``walk_forward_fit()`` enforces chronological-only training.

Usage
-----
>>> gmm = LatentGMMRegime(latent_columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"])
>>> gmm.walk_forward_fit(panel_train, current_date)
>>> regime, proba = gmm.predict_regime(panel_test)
>>> scale = gmm.get_exposure_scale(proba)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

logger = logging.getLogger(__name__)

# Default latent column names from NonlinearDeepLatentEncoder
_DEFAULT_LATENT_COLS = ["latent_ae_00", "latent_ae_01", "latent_ae_11"]


@dataclass
class LatentGMMConfig:
    """Configuration for Latent GMM regime detection.

    Parameters
    ----------
    n_components : int
        Number of GMM clusters / regimes (default 3: Bull, Sideways, Bear).
    covariance_type : str
        GMM covariance structure ('full', 'tied', 'diag', 'spherical').
    n_init : int
        Number of EM initializations.
    max_iter : int
        Maximum EM iterations per initialization.
    random_state : int
        Random seed for reproducibility.
    latent_columns : list of str
        Column names in the panel DataFrame for latent AE features.
    bear_dampening : float
        Exposure multiplier for Bear regime (default 0.3).
    bull_boost : float
        Exposure multiplier for Bull regime (default 1.1).
    sideways_scale : float
        Exposure multiplier for Sideways regime (default 0.8).
    min_training_samples : int
        Minimum samples required to fit GMM.
    refit_stride : int
        Refit GMM every N days during walk-forward.
    smooth_transition : bool
        If True, use sigmoid-based smooth transition between bear and bull
        exposure scales instead of discrete regime-weighted mixing.
    smooth_transition_temp : float
        Temperature parameter for the sigmoid in smooth transition mode.
        Lower values = sharper transition, higher = softer blend.
    """

    n_components: int = 3
    covariance_type: str = "full"
    n_init: int = 10
    max_iter: int = 100
    random_state: int = 42
    latent_columns: List[str] = field(
        default_factory=lambda: list(_DEFAULT_LATENT_COLS)
    )
    bear_dampening: float = 0.3
    bull_boost: float = 1.1
    sideways_scale: float = 0.8
    min_training_samples: int = 60
    refit_stride: int = 5
    smooth_transition: bool = False
    smooth_transition_temp: float = 0.1


class LatentGMMRegime:
    """Gaussian Mixture Model regime clustering on Latent AE features.

    PIT Safety
    ----------
    All fitting uses only historical (T-1 or earlier) data.
    Inference on new observations is a forward pass through a frozen model.
    """

    def __init__(self, config: Optional[LatentGMMConfig] = None):
        self.config = config or LatentGMMConfig()
        self._model: Optional[GaussianMixture] = None
        self._regime_map: Dict[int, str] = {}
        self._is_fitted: bool = False
        self._last_fit_date: Optional[pd.Timestamp] = None

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, latent_df: pd.DataFrame) -> "LatentGMMRegime":
        """Fit GMM on latent features.

        Parameters
        ----------
        latent_df : DataFrame
            Must contain columns named in ``config.latent_columns``.

        Returns
        -------
        self
        """
        cols = self.config.latent_columns
        missing = [c for c in cols if c not in latent_df.columns]
        if missing:
            raise ValueError(f"Missing latent columns: {missing}")

        # Check if date exists to compute daily mean (Gate: HYBRID_REGIME_DIAGNOSTICS_20260624)
        if "date" in latent_df.columns:
            agg_dict = {c: "mean" for c in cols}
            if "returns" in latent_df.columns:
                agg_dict["returns"] = "mean"
            daily_df = latent_df.groupby("date").agg(agg_dict).dropna()
            X = daily_df[cols].values
            train_returns = daily_df["returns"] if "returns" in daily_df.columns else None
        else:
            # Fallback for legacy test fixtures with no date column
            latent_train = latent_df[cols].dropna()
            X = latent_train.values
            train_returns = None
            if "returns" in latent_df.columns:
                train_returns = latent_df.loc[latent_train.index, "returns"]

        if len(X) < self.config.min_training_samples:
            logger.warning(
                "LatentGMMRegime: Insufficient data (%d < %d), skipping fit.",
                len(X),
                self.config.min_training_samples,
            )
            return self

        self._model = GaussianMixture(
            n_components=self.config.n_components,
            covariance_type=self.config.covariance_type,
            n_init=self.config.n_init,
            max_iter=self.config.max_iter,
            random_state=self.config.random_state,
        )
        self._model.fit(X)

        self._map_regimes(X, train_returns=train_returns)
        self._is_fitted = True

        logger.info(
            "LatentGMMRegime: Fitted on %d samples, regime_map=%s",
            len(X),
            self._regime_map,
        )
        return self

    def walk_forward_fit(
        self, panel: pd.DataFrame, current_date: pd.Timestamp
    ) -> "LatentGMMRegime":
        """PIT-safe walk-forward fit: only data strictly before current_date.

        Parameters
        ----------
        panel : DataFrame
            Flat panel with ``date`` column (or DatetimeIndex) and latent columns.
        current_date : Timestamp
            Current trading date — only data < current_date is used.

        Returns
        -------
        self
        """
        if "date" in panel.columns:
            dates = pd.to_datetime(panel["date"])
            train_mask = dates < current_date
            train_df = panel.loc[train_mask]
        elif isinstance(panel.index, pd.DatetimeIndex):
            train_df = panel[panel.index < current_date]
        elif isinstance(panel.index, pd.MultiIndex) and "date" in panel.index.names:
            date_vals = panel.index.get_level_values("date")
            train_df = panel[date_vals < current_date]
        else:
            logger.warning("LatentGMMRegime: Cannot determine date column/index for PIT filtering.")
            return self

        if len(train_df) < self.config.min_training_samples:
            logger.debug(
                "LatentGMMRegime: Not enough training data before %s (%d rows).",
                current_date,
                len(train_df),
            )
            return self

        return self.fit(train_df)

    def predict_regime(
        self, latent_df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Predict regime labels and probabilities for observations.

        Parameters
        ----------
        latent_df : DataFrame
            Must contain latent columns.

        Returns
        -------
        labels : ndarray of str
            Regime labels ('Bull', 'Sideways', 'Bear') per row.
        probabilities : ndarray
            Full GMM probability matrix (N, n_components).
        """
        if not self._is_fitted or self._model is None:
            n = len(latent_df)
            return np.full(n, "Sideways"), np.ones((n, self.config.n_components)) / self.config.n_components

        cols = self.config.latent_columns
        X = latent_df[cols].fillna(0.0).values

        state_ids = self._model.predict(X)
        probabilities = self._model.predict_proba(X)

        labels = np.array([
            self._regime_map.get(s, "Sideways") for s in state_ids
        ])

        return labels, probabilities

    def predict_proba(self, latent_df: pd.DataFrame) -> np.ndarray:
        """Return GMM posterior probabilities (N, n_components).

        PIT Safety: Frozen model inference — no data access beyond input.
        """
        if not self._is_fitted or self._model is None:
            n = len(latent_df)
            return np.ones((n, self.config.n_components)) / self.config.n_components

        cols = self.config.latent_columns
        X = latent_df[cols].fillna(0.0).values
        return self._model.predict_proba(X)

    def get_exposure_scale(self, probabilities: np.ndarray) -> np.ndarray:
        """Compute exposure multiplier from regime probabilities.

        Parameters
        ----------
        probabilities : ndarray
            Shape (N, n_components). Each row is [p_regime0, p_regime1, ...].

        Returns
        -------
        scales : ndarray
            Exposure multiplier per observation, shape (N,).
        """
        if not self._is_fitted:
            return np.ones(len(probabilities))

        if self.config.smooth_transition:
            return self._get_smooth_exposure_scale(probabilities)

        scales = np.zeros(len(probabilities))
        for state_id, regime_name in self._regime_map.items():
            if regime_name == "Bear":
                scales += probabilities[:, state_id] * self.config.bear_dampening
            elif regime_name == "Bull":
                scales += probabilities[:, state_id] * self.config.bull_boost
            else:
                scales += probabilities[:, state_id] * self.config.sideways_scale

        return np.clip(scales, 0.1, 2.0)

    def _get_smooth_exposure_scale(self, probabilities: np.ndarray) -> np.ndarray:
        """Smooth sigmoid-transition exposure scale.

        For each observation, computes:
          p_bull = sum of probabilities for Bull-state components,
          p_bear = sum of probabilities for Bear-state components,
          diff   = p_bull - p_bear,
          scale  = bear_dampening + (bull_boost - bear_dampening)
                   * sigmoid(diff / smooth_transition_temp)

        Returns
        -------
        scales : ndarray, shape (N,)
        """
        n = len(probabilities)
        p_bull = np.zeros(n)
        p_bear = np.zeros(n)
        for state_id, regime_name in self._regime_map.items():
            if regime_name == "Bull":
                p_bull += probabilities[:, state_id]
            elif regime_name == "Bear":
                p_bear += probabilities[:, state_id]

        diff = p_bull - p_bear
        temp = max(self.config.smooth_transition_temp, 1e-9)
        sigmoid = 1.0 / (1.0 + np.exp(-diff / temp))
        bear = self.config.bear_dampening
        bull = self.config.bull_boost
        scales = bear + (bull - bear) * sigmoid

        return np.clip(scales, 0.1, 2.0)

    def get_regime_probability_map(
        self, probabilities: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Map regime names to their probability arrays.

        Returns
        -------
        dict
            {'Bull': array, 'Sideways': array, 'Bear': array}
        """
        result = {}
        for state_id, regime_name in self._regime_map.items():
            result[regime_name] = probabilities[:, state_id]
        return result

    def _map_regimes(
        self,
        X: np.ndarray,
        train_returns: Optional[pd.Series] = None,
    ) -> None:
        """Map GMM component IDs to semantic regime labels.

        Primary strategy: use realized train-set returns aligned with the
        fitted latent observations. Highest mean return cluster → Bull,
        lowest mean return cluster → Bear, remainder → Sideways.

        Fallback: when aligned returns are unavailable or degenerate, fall
        back to the original latent-mean norm heuristic.
        """
        return_sorted_states = self._get_return_sorted_states(X, train_returns)
        if return_sorted_states is not None:
            self._assign_regime_labels(return_sorted_states)
            state_mean_returns = {
                int(state_id): float(mean_return)
                for state_id, mean_return in return_sorted_states
            }
            logger.debug(
                "LatentGMMRegime: Regime mapping = %s (mean_returns=%s)",
                self._regime_map,
                {k: f"{v:.6f}" for k, v in state_mean_returns.items()},
            )
            return

        means = self._model.means_
        norms = np.linalg.norm(means, axis=1)
        heuristic_sorted_states = [
            (int(state_id), float(norms[state_id]))
            for state_id in np.argsort(norms)
        ]

        self._assign_regime_labels(heuristic_sorted_states)

        logger.debug(
            "LatentGMMRegime: Regime mapping = %s (norms=%s)",
            self._regime_map,
            {state_id: f"{score:.3f}" for state_id, score in heuristic_sorted_states},
        )

    def _get_return_sorted_states(
        self,
        X: np.ndarray,
        train_returns: Optional[pd.Series],
    ) -> Optional[List[Tuple[int, float]]]:
        if train_returns is None or self._model is None:
            return None

        returns = pd.to_numeric(train_returns, errors="coerce")
        valid_mask = returns.notna().to_numpy()
        if valid_mask.sum() < self.config.n_components:
            return None

        state_ids = self._model.predict(X)
        state_return_df = pd.DataFrame(
            {"state_id": state_ids[valid_mask], "returns": returns.to_numpy()[valid_mask]}
        )
        if state_return_df.empty:
            return None

        state_mean_returns = state_return_df.groupby("state_id")["returns"].mean()
        if len(state_mean_returns) != self.config.n_components:
            return None

        state_mean_returns = state_mean_returns.sort_values()
        return [
            (int(state_id), float(mean_return))
            for state_id, mean_return in state_mean_returns.items()
        ]

    def _assign_regime_labels(self, sorted_states: List[Tuple[int, float]]) -> None:
        ordered_state_ids = [state_id for state_id, _ in sorted_states]
        n = self.config.n_components

        if n == 3:
            bear_id = ordered_state_ids[0]
            bull_id = ordered_state_ids[-1]
            sideways_id = ordered_state_ids[1]
            self._regime_map = {
                bull_id: "Bull",
                sideways_id: "Sideways",
                bear_id: "Bear",
            }
        elif n == 2:
            self._regime_map = {
                ordered_state_ids[0]: "Bear",
                ordered_state_ids[-1]: "Bull",
            }
        else:
            self._regime_map = {
                ordered_state_ids[0]: "Bear",
                ordered_state_ids[-1]: "Bull",
            }
            for state_id in ordered_state_ids[1:-1]:
                self._regime_map[state_id] = "Sideways"
