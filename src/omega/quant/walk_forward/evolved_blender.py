"""Inline evolved-signal blending mixin."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EvolvedBlendingMixin:
    """Optional GP evolved alpha signal generation."""

    def _evolve_inline_signal(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        return_col: str,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Run inline GP evolution on train_df, execute best on test_df.

        PIT-safe: evolves only on train_actual, executes on test_df.
        Returns (evolved_signal_array, train_ic) or (None, 0.0) on failure.
        train_ic is used by caller for adaptive blend weighting.
        """
        try:
            from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
        except ImportError:
            logger.warning("Cannot import GeneticEngine, skipping evolved signal")
            return None, 0.0

        # Extract features from train_df (OHLCV + any alpha/feature columns)
        base_cols = ['open', 'high', 'low', 'close', 'volume']
        # Add any additional numeric columns available (alphas, fwd returns, etc.)
        alpha_cols = [c for c in self.alpha_cols_ref if c in train_df.columns]

        # Explicitly exclude return_col and any fwd_ret_* columns (prevent look-ahead leak)
        exclude_patterns = [return_col] + [c for c in train_df.columns if c.startswith('fwd_ret_')]
        available_cols = [
            c for c in base_cols + alpha_cols
            if c in train_df.columns and c not in exclude_patterns
        ]

        if len(available_cols) < 5:
            logger.warning(f"Insufficient features ({len(available_cols)}), skipping evolution")
            return None, 0.0

        # PIT Safety: T-1 lag raw OHLCV per ticker before GP sees them
        # Alpha columns are already T-1 lagged by compute_alphas(), but raw OHLCV are not.
        lagged_train = train_df.copy()
        lagged_test = test_df.copy()
        for col in base_cols:
            if col in lagged_train.columns:
                lagged_train[col] = lagged_train.groupby('ticker')[col].shift(1)
            if col in lagged_test.columns:
                lagged_test[col] = lagged_test.groupby('ticker')[col].shift(1)
        # Drop rows with NaN from lagging
        lagged_train = lagged_train.dropna(subset=[c for c in base_cols if c in lagged_train.columns])

        # Build features dict for train (using lagged OHLCV)
        train_features = {col: lagged_train[col].values for col in available_cols if col in lagged_train.columns}
        # Add target
        if return_col not in lagged_train.columns:
            logger.warning(f"Target {return_col} not in train_df, skipping evolution")
            return None, 0.0
        train_target = lagged_train[return_col].values
        # GP config: keep simple to avoid overfitting (V2 proven config)
        # Adaptive blend weight handles quality variance instead
        config = GPConfig(
            population_size=150,
            generations=3,
            max_depth=3,
            hall_of_fame_size=3,
        )
        engine = GeneticEngine(config)
        # features dict = OHLCV + alpha columns, target = forward returns
        train_target = lagged_train[return_col].values
        # Align hall_of_fame evolve with lagged train features
        hall_of_fame = engine.evolve(train_features, train_target)

        if not hall_of_fame:
            logger.warning("Evolution produced no individuals, skipping")
            return None, 0.0

        # P1: Ensemble top 3 GP trees (not just best) for robustness
        # Average signals from hall_of_fame[0:3] to reduce variance
        test_features = {
            col: lagged_test[col].values if col in lagged_test.columns else np.zeros(len(lagged_test))
            for col in available_cols
        }

        try:
            # Execute all individuals in hall_of_fame
            ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, test_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                # Normalize each signal to zero mean, unit std
                std_val = np.std(signal)
                if std_val > 1e-9:
                    signal = (signal - np.mean(signal)) / std_val
                ensemble_signals.append(signal)

            # Average ensemble signals
            evolved_signal = np.mean(ensemble_signals, axis=0)

            # Compute train IC on ensemble signal for adaptive blending
            train_ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, train_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                # Normalize each signal to zero mean, unit std (same as test side for parity)
                train_std = np.std(signal)
                if train_std > 1e-9:
                    signal = (signal - np.mean(signal)) / train_std
                train_ensemble_signals.append(signal)

            train_signal = np.mean(train_ensemble_signals, axis=0)
            train_ic = float(np.corrcoef(train_signal, train_target)[0, 1]) if len(train_signal) > 1 else 0.0
            if np.isnan(train_ic):
                train_ic = 0.0

            test_ret = (
                lagged_test[return_col].values
                if return_col in lagged_test.columns
                else np.zeros(len(lagged_test))
            )
            test_ic = float(np.corrcoef(evolved_signal, test_ret)[0, 1]) if len(evolved_signal) > 1 else 0.0
            if np.isnan(test_ic):
                test_ic = 0.0

            logger.info(
                f"GP ensemble (n={len(hall_of_fame)}): train_ic={train_ic:.4f}, "
                f"test_ic={test_ic:.4f}, signal_std={np.std(evolved_signal):.4f}"
            )
            return evolved_signal, train_ic
        except Exception as e:
            logger.error(f"GP ensemble execution failed: {e}")
            return None, 0.0
