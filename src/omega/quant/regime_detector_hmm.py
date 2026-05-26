"""
Regime Detector HMM Module (Phase 11 - OMEGA_QUANT)
Layer 02: Strategy Logic

HMM-based Market Regime Detection for Risk Management.
Uses custom Gaussian HMM to classify 3 regimes: Bull (0), Sideways (1), Bear (2).

Key Features:
- PIT-Safe: Uses only T-1 data to predict regime for day T
- 3-State Model: Bull, Sideways, Bear
- Input: VN-Index Returns + Volatility + Volume Change (Multi-variate)
- Integration: Auto-dampens ensemble_score by 0.3x in Bear regime

# Adapted from: archive/V21_QUANT_FINAL_20260509/src/v21_system/layer_02_strategy_logic/regime_detector_hmm.py
"""

import numpy as np
import pandas as pd
import logging
from typing import Tuple, Optional
from dataclasses import dataclass
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture

logger = logging.getLogger(__name__)


@dataclass
class HMMRegimeConfig:
    """Configuration for HMM Regime Detector"""
    n_components: int = 3  # Bull, Sideways, Bear
    n_iter: int = 100
    random_state: int = 42
    bear_dampening: float = 0.3  # Reduce signal by 70% in Bear regime
    features: list = None

    def __post_init__(self):
        if self.features is None:
            self.features = ['returns', 'volatility', 'volume_change']


class RegimeDetectorHMM:
    """
    HMM-based Regime Detector using Gaussian HMM.

    Workflow:
    1. Train on historical VN-Index data (Returns + Volatility)
    2. Predict regime for current day using T-1 data (PIT-Safe)
    3. Apply dampening to ensemble_score if regime == Bear
    """

    def __init__(self, config: Optional[HMMRegimeConfig] = None):
        self.config = config or HMMRegimeConfig()
        # Use GaussianMixture as HMM alternative (simpler, no C extension issues)
        self.model = GaussianMixture(
            n_components=self.config.n_components,
            n_init=10,
            random_state=self.config.random_state,
            covariance_type='full'
        )
        self.is_fitted = False
        self.regime_map = {}  # Maps state ID to semantic label
        self.feature_means_ = None
        self.feature_stds_ = None
        self.filtered_state_ = None  # Posterior state for sequence modeling

    def fit(self, features_df: pd.DataFrame, target_returns: Optional[pd.Series] = None):
        """
        Train HMM on historical market data.

        Args:
            features_df: DataFrame with columns ['returns', 'volatility', 'volume_change']
            target_returns: Optional returns for regime mapping
        """
        required_cols = self.config.features
        missing = [c for c in required_cols if c not in features_df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        X = features_df[required_cols].values

        # Standardize features
        self.feature_means_ = np.mean(X, axis=0)
        self.feature_stds_ = np.std(X, axis=0) + 1e-8
        X_scaled = (X - self.feature_means_) / self.feature_stds_

        # Initialize HMM with stratified K-means
        if target_returns is not None:
            y = target_returns.values
            vol = X[:, 1]  # Volatility feature

            # Define Bear: negative returns + high volatility
            bear_mask = (y < np.percentile(y, 33)) & (vol > np.percentile(vol, 66))
            # Define Bull: positive returns + low volatility
            bull_mask = (y > np.percentile(y, 66)) & (vol < np.percentile(vol, 33))
            # Rest is Sideways
            sideways_mask = ~(bear_mask | bull_mask)

            # Force at least some samples in each regime
            if bear_mask.sum() < 50:
                bear_indices = np.argsort(y)[:max(50, len(y)//10)]
                bear_mask = np.zeros(len(y), dtype=bool)
                bear_mask[bear_indices] = True
                sideways_mask = ~(bear_mask | bull_mask)

            init_labels = np.zeros(len(X), dtype=int)
            init_labels[bear_mask] = 0
            init_labels[bull_mask] = 1
            init_labels[sideways_mask] = 2

            logger.info(f"Stratified initialization: Bear={bear_mask.sum()}, Bull={bull_mask.sum()}, Sideways={sideways_mask.sum()}")

            # Initialize means from stratified labels
            init_means = np.array([X_scaled[init_labels == i].mean(axis=0) for i in range(self.config.n_components)])
            self.model.means_ = init_means
        else:
            # Fallback to K-means
            kmeans = KMeans(n_clusters=self.config.n_components, random_state=self.config.random_state, n_init=10)
            init_labels = kmeans.fit_predict(X_scaled)
            init_means = np.array([X_scaled[init_labels == i].mean(axis=0) for i in range(self.config.n_components)])
            self.model.means_ = init_means

        # Train Gaussian Mixture Model (HMM alternative)
        logger.info(f"Training regime detector with {len(X)} samples (stratified initialization)...")
        self.model.fit(X_scaled)

        # Map states to regimes
        if target_returns is not None:
            self._map_regimes_from_returns(X_scaled, target_returns.values)
        else:
            self._map_regimes_by_volatility()

        self.is_fitted = True
        self.filtered_state_ = None
        logger.info(f"Regime detector trained. Regime mapping: {self.regime_map}")
        return self

    def train_walkforward(self, features_df: pd.DataFrame, curr_date, target_returns: Optional[pd.Series] = None):
        """
        Walk-forward training - only fit on data < curr_date (PIT-Safe).

        Args:
            features_df: DataFrame with columns ['returns', 'volatility', 'volume_change']
            curr_date: Current date for PIT compliance
            target_returns: Optional returns for regime mapping
        """
        # Filter to historical data only
        train_data = features_df[features_df.index < curr_date]

        if len(train_data) < 100:
            logger.warning(f"Insufficient training data before {curr_date}. Need 100+, got {len(train_data)}.")
            return self

        train_returns = target_returns[target_returns.index < curr_date] if target_returns is not None else None

        return self.fit(train_data, train_returns)

    def _map_regimes_from_returns(self, X: np.ndarray, y: np.ndarray):
        """
        Map states using returns AND volatility.
        Bear = Lowest return + Highest volatility
        Bull = Highest return + Low/Medium volatility
        """
        states = self.model.predict(X)
        state_stats = {}
        state_counts = {}

        for i in range(self.config.n_components):
            mask = (states == i)
            count = mask.sum()
            state_counts[i] = count

            if count > 0:
                state_stats[i] = {
                    'return': np.mean(y[mask]),
                    'volatility': self.model.covariances_[i][1, 1] if len(self.model.covariances_[i].shape) == 2 else self.model.covariances_[i, 1, 1]
                }
            else:
                state_stats[i] = {
                    'return': self.model.means_[i, 0],
                    'volatility': self.model.covariances_[i][1, 1] if len(self.model.covariances_[i].shape) == 2 else self.model.covariances_[i, 1, 1]
                }

        if self.config.n_components == 3:
            bear_candidate = min(state_stats.keys(), key=lambda k: state_stats[k]['return'])
            bull_candidate = max(state_stats.keys(), key=lambda k: state_stats[k]['return'])
            sideways_candidate = [k for k in state_stats.keys() if k not in [bear_candidate, bull_candidate]][0]

            logger.info(f"Regime Anchoring Stats:")
            logger.info(f"  Bear (State {bear_candidate}): Return={state_stats[bear_candidate]['return']:.4f}, Vol={state_stats[bear_candidate]['volatility']:.6f}, Count={state_counts[bear_candidate]}")
            logger.info(f"  Bull (State {bull_candidate}): Return={state_stats[bull_candidate]['return']:.4f}, Vol={state_stats[bull_candidate]['volatility']:.6f}, Count={state_counts[bull_candidate]}")
            logger.info(f"  Sideways (State {sideways_candidate}): Return={state_stats[sideways_candidate]['return']:.4f}, Vol={state_stats[sideways_candidate]['volatility']:.6f}, Count={state_counts[sideways_candidate]}")

            for state_name, state_id in [('Bear', bear_candidate), ('Bull', bull_candidate), ('Sideways', sideways_candidate)]:
                if state_counts[state_id] < 10:
                    logger.warning(f"  WARNING: {state_name} state has only {state_counts[state_id]} samples in training data!")

            self.regime_map = {
                bear_candidate: 'Bear',
                sideways_candidate: 'Sideways',
                bull_candidate: 'Bull'
            }
        else:
            self.regime_map = {i: f'Regime_{i}' for i in range(self.config.n_components)}

    def _map_regimes_by_volatility(self):
        """Map states based on volatility (fallback method)."""
        vols = {}
        for i in range(self.config.n_components):
            cov = self.model.covariances_[i]
            vols[i] = cov[1, 1] if len(cov.shape) == 2 else cov[1, 1]

        sorted_states = sorted(vols.keys(), key=lambda k: vols[k])

        if self.config.n_components == 3 and len(sorted_states) == 3:
            self.regime_map = {
                sorted_states[0]: 'Bull',
                sorted_states[1]: 'Sideways',
                sorted_states[2]: 'Bear'
            }
        else:
            self.regime_map = {i: f'Regime_{i}' for i in range(self.config.n_components)}

    def predict_regime(self, features_df: pd.DataFrame) -> str:
        """
        Predict regime for current day using T-1 data (PIT-Safe).

        Args:
            features_df: DataFrame with a single row of features.

        Returns:
            Regime label ('Bull', 'Sideways', 'Bear')
        """
        if not self.is_fitted:
            return 'Sideways'

        required_cols = self.config.features
        X = features_df[required_cols].values

        if len(X) == 0:
            return 'Sideways'

        # PIT Safety Guard: Verify features are T-1 (not current day)
        feature_date = None
        if isinstance(features_df.index, pd.MultiIndex):
            if 'date' in features_df.index.names:
                feature_date = features_df.index.get_level_values('date')[0]
        elif isinstance(features_df.index, pd.DatetimeIndex):
            feature_date = features_df.index[0]

        if feature_date is None and isinstance(features_df.index, pd.DatetimeIndex) and len(features_df.index) > 0:
            feature_date = features_df.index[0]

        if feature_date is not None:
            # Runtime assertion: features must be from past
            current_date = pd.Timestamp.now().normalize()
            assert feature_date < current_date, f"PIT violation: feature_date {feature_date} >= current_date {current_date}"

        X_scaled = (X - self.feature_means_) / self.feature_stds_
        state = self.model.predict(X_scaled)[0]
        regime = self.regime_map.get(state, 'Sideways')

        return regime

    def get_dampening_factor(self, regime: str) -> float:
        """
        Get dampening factor for ensemble score based on regime.

        Args:
            regime: Regime label ('Bull', 'Sideways', 'Bear')

        Returns:
            Dampening factor (1.0 for Bull/Sideways, 0.3 for Bear)
        """
        if regime == 'Bear':
            return self.config.bear_dampening
        return 1.0

