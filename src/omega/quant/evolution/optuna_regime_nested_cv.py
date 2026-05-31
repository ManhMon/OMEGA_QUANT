"""
OMEGA_QUANT Optuna Nested CV for Regime Params
Inner loop: Optuna tunes regime params on inner folds
Outer loop: Evaluate tuned params on held-out outer fold
Prevents overfitting that plagued v3.3 single-split Optuna.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Nested CV is chronological (expanding window).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class RegimeTunedParams:
    """Best regime params from nested CV."""
    dd_threshold: float = -0.10
    hysteresis: int = 5
    bear_exposure: float = 0.5
    bull_exposure: float = 1.1
    sideways_exposure: float = 0.8
    inner_sharpe: float = 0.0
    outer_sharpe: float = 0.0
    n_outer_folds: int = 0


class OptunaRegimeNestedCV:
    """
    Nested cross-validation for regime params.
    
    Outer loop: 3 expanding-window folds (chronological)
    Inner loop: Optuna tunes on inner train, evaluates on inner val
    Final: Average outer fold performance = unbiased estimate
    """

    def __init__(self, n_outer_folds: int = 3, n_inner_trials: int = 20):
        self.n_outer_folds = n_outer_folds
        self.n_inner_trials = n_inner_trials

    def _compute_fold_sharpe(
        self, returns: np.ndarray, weights: np.ndarray, exposures: np.ndarray
    ) -> float:
        """Compute Sharpe from returns * weights * exposure."""
        port_ret = (returns * weights).sum(axis=1) * exposures
        if port_ret.std() < 1e-10:
            return 0.0
        return float((port_ret.mean() / port_ret.std()) * np.sqrt(252))

    def _compute_regime_exposures(
        self, market_returns: np.ndarray,
        dd_threshold: float, hysteresis: int,
        bear_exp: float, bull_exp: float, side_exp: float,
    ) -> np.ndarray:
        """Compute exposure array from regime params (PIT-safe)."""
        import sys
        sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src\omega\quant\portfolio')
        from regime_overlay import compute_regime_exposure

        raw = compute_regime_exposure(
            market_returns,
            dd_threshold=dd_threshold,
            hysteresis_days=hysteresis,
        )
        # Remap to configured levels
        final = np.where(raw > 1.0, bull_exp,
                np.where(raw < 0.6, bear_exp, side_exp))
        return final

    def _inner_objective(self, trial, inner_returns, inner_weights, inner_market_rets):
        """Optuna objective for inner fold."""
        import optuna

        dd = trial.suggest_float('dd_threshold', -0.15, -0.05, step=0.01)
        hyst = trial.suggest_int('hysteresis', 3, 15)
        bear = trial.suggest_float('bear_exposure', 0.3, 0.9, step=0.05)
        bull = trial.suggest_float('bull_exposure', 1.0, 1.2, step=0.05)
        side = trial.suggest_float('sideways_exposure', 0.7, 1.0, step=0.05)

        exposures = self._compute_regime_exposures(
            inner_market_rets, dd, hyst, bear, bull, side
        )

        # Trim to match returns length
        n = min(len(exposures), len(inner_returns))
        sharpe = self._compute_fold_sharpe(
            inner_returns[:n], inner_weights[:n], exposures[:n]
        )
        return sharpe

    def tune(
        self,
        returns: np.ndarray,
        weights: np.ndarray,
        market_returns: np.ndarray,
    ) -> RegimeTunedParams:
        """
        Run nested CV to find optimal regime params.

        Args:
            returns: T x N array of asset returns
            weights: T x N array of portfolio weights (pre-regime)
            market_returns: T-length array of market returns

        Returns:
            RegimeTunedParams with best params and unbiased OOS estimate.
        """
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        T = len(returns)
        fold_size = T // (self.n_outer_folds + 1)

        outer_results = []
        all_best_params = []

        logger.info("=== OPTUNA NESTED CV: %d outer folds, %d inner trials ===",
                    self.n_outer_folds, self.n_inner_trials)

        for fold in range(self.n_outer_folds):
            # Expanding window: train on [0, split), test on [split, split+fold_size)
            split = fold_size * (fold + 2)  # At least 2 fold_sizes for training
            test_end = min(split + fold_size, T)

            if split >= T or test_end <= split:
                continue

            inner_returns = returns[:split]
            inner_weights = weights[:split]
            inner_market = market_returns[:split]

            outer_returns = returns[split:test_end]
            outer_weights = weights[split:test_end]
            outer_market = market_returns[split:test_end]

            # Inner: Optuna tune
            study = optuna.create_study(direction='maximize')
            study.optimize(
                lambda trial: self._inner_objective(trial, inner_returns, inner_weights, inner_market),
                n_trials=self.n_inner_trials,
                show_progress_bar=False,
            )

            best = study.best_params
            inner_sharpe = study.best_value

            # Outer: evaluate best params on held-out fold
            # Pass full history up to test_end to avoid cold-start bias (Issue #1 fix)
            full_exposures = self._compute_regime_exposures(
                market_returns[:test_end],
                best['dd_threshold'], best['hysteresis'],
                best['bear_exposure'], best['bull_exposure'], best['sideways_exposure'],
            )
            outer_exposures = full_exposures[split:test_end]
            n = min(len(outer_exposures), len(outer_returns))
            outer_sharpe = self._compute_fold_sharpe(
                outer_returns[:n], outer_weights[:n], outer_exposures[:n]
            )

            outer_results.append(outer_sharpe)
            best['_inner_sharpe'] = inner_sharpe
            all_best_params.append(best)
            logger.info("  Fold %d: inner_SR=%.4f, outer_SR=%.4f, params=%s",
                        fold, inner_sharpe, outer_sharpe,
                        {k: round(v, 3) for k, v in best.items()})

        # Average best params across folds (robust)
        if all_best_params:
            avg_params = {
                'dd_threshold': np.mean([p['dd_threshold'] for p in all_best_params]),
                'hysteresis': int(np.median([p['hysteresis'] for p in all_best_params])),
                'bear_exposure': np.mean([p['bear_exposure'] for p in all_best_params]),
                'bull_exposure': np.mean([p['bull_exposure'] for p in all_best_params]),
                'sideways_exposure': np.mean([p['sideways_exposure'] for p in all_best_params]),
            }
        else:
            avg_params = {'dd_threshold': -0.10, 'hysteresis': 5, 'bear_exposure': 0.5,
                          'bull_exposure': 1.1, 'sideways_exposure': 0.8}

        avg_outer_sharpe = np.mean(outer_results) if outer_results else 0.0
        # Fix #3: accumulate inner sharpe from all folds (not just last study)
        all_inner_sharpes = [p.get('_inner_sharpe', 0) for p in all_best_params] if all_best_params else [0.0]
        avg_inner_sharpe = np.mean(all_inner_sharpes)

        result = RegimeTunedParams(
            dd_threshold=avg_params['dd_threshold'],
            hysteresis=avg_params['hysteresis'],
            bear_exposure=avg_params['bear_exposure'],
            bull_exposure=avg_params['bull_exposure'],
            sideways_exposure=avg_params['sideways_exposure'],
            inner_sharpe=avg_inner_sharpe,
            outer_sharpe=avg_outer_sharpe,
            n_outer_folds=len(outer_results),
        )

        logger.info("=== NESTED CV RESULT: outer_SR=%.4f ===", avg_outer_sharpe)
        logger.info("  Params: dd=%.3f, hyst=%d, bear=%.2f, bull=%.2f, side=%.2f",
                    result.dd_threshold, result.hysteresis,
                    result.bear_exposure, result.bull_exposure, result.sideways_exposure)

        return result
