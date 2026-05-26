"""
Black-Litterman Model for Portfolio Optimization.

Implements the Black-Litterman framework combining:
1. Market equilibrium returns (from market cap weights)
2. Investor alpha views (explicit forecasts)
3. Uncertainty in views (confidence levels)

Features:
- L2 Regularization: Prevents extreme weight concentrations
- Liquidity Constraints: Max weight <= 10% of ADV
- Regime-Aware Confidence: Adjusts view confidence based on HMM regime_confidence
- Turnover Constraint: Limits portfolio churn per rebalance

PIT Safety: All inputs (views, regime_confidence) must be T-1 lagged.
Vectorization: 100% numpy vectorized. No loops over assets for core math.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import gc
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

__all__ = [
    "BlackLittermanOptimizer",
]

logger = logging.getLogger(__name__)


class BlackLittermanOptimizer:
    """
    Black-Litterman portfolio optimizer.

    Combines market equilibrium with investor views to produce robust
    portfolio weights that avoid extreme allocations.

    Features:
    - L2 regularization for weight stability
    - Liquidity constraints (10% ADV max)
    - Regime-aware confidence adjustment
    - Turnover constraint to limit portfolio churn
    """

    def __init__(
        self,
        risk_aversion: float = 2.5,
        tau: float = 0.05,
        l2_lambda: float = 0.01,
        max_adv_pct: float = 0.10,
        max_turnover_per_rebalance: float = 0.20,
    ) -> None:
        """
        Args:
            risk_aversion: Risk aversion coefficient (lambda). Range: 2.0-4.0.
            tau: Scalar uncertainty parameter (0.01-0.1).
            l2_lambda: L2 regularization strength (0.001-0.1).
            max_adv_pct: Maximum weight as % of ADV (default 10%).
            max_turnover_per_rebalance: Maximum turnover per rebalance (default 20%).
        """
        self.risk_aversion = risk_aversion
        self.tau = tau
        self.l2_lambda = l2_lambda
        self.max_adv_pct = max_adv_pct
        self.max_turnover_per_rebalance = max_turnover_per_rebalance

    @staticmethod
    def _bounded_allocate(
        base_weights: np.ndarray,
        upper_bounds: np.ndarray,
        min_weight: float = 0.0,
    ) -> np.ndarray:
        """
        Allocate weights under hard per-asset caps.

        If aggregate capacity is below 100%, the result intentionally sums
        to less than one (residual cash) instead of violating caps.

        Args:
            base_weights: Raw weight proposals.
            upper_bounds: Per-asset maximum weights.
            min_weight: Minimum weight per asset.

        Returns:
            Allocated weights respecting caps.
        """
        weights = np.asarray(base_weights, dtype=np.float64)
        caps = np.asarray(upper_bounds, dtype=np.float64)

        weights = np.where(np.isfinite(weights), weights, 0.0)
        weights = np.maximum(weights, 0.0)
        caps = np.where(np.isfinite(caps), caps, 0.0)
        caps = np.maximum(caps, 0.0)

        if weights.size == 0:
            return weights

        floor = np.minimum(
            np.full(weights.size, max(float(min_weight), 0.0)), caps
        )
        target_total = min(1.0, float(caps.sum()))

        if floor.sum() >= target_total:
            if floor.sum() > 0:
                return floor * (target_total / floor.sum())
            return floor

        allocated = floor.copy()
        remaining = target_total - float(allocated.sum())
        room = caps - allocated

        for _ in range(weights.size + 1):
            eligible = room > 1e-12
            if remaining <= 1e-12 or not np.any(eligible):
                break

            scores = weights[eligible]
            if scores.sum() <= 1e-12:
                scores = room[eligible]

            proposal = remaining * scores / scores.sum()
            addition = np.minimum(proposal, room[eligible])

            allocated[eligible] += addition
            spent = float(addition.sum())
            remaining -= spent
            room = caps - allocated

            if spent <= 1e-12:
                break

        return np.minimum(allocated, caps)

    def get_market_implied_returns(
        self,
        market_weights: np.ndarray,
        cov_matrix: np.ndarray,
        risk_free_rate: float = 0.02,
    ) -> np.ndarray:
        """
        Calculate market-implied expected returns from market cap weights.

        Formula: pi = lambda * Sigma * w_market

        Args:
            market_weights: Market capitalization weights (n_assets,).
            cov_matrix: Covariance matrix (n_assets, n_assets).
            risk_free_rate: Risk-free rate.

        Returns:
            Implied expected returns (n_assets,).
        """
        if not np.isclose(market_weights.sum(), 1.0):
            market_weights = market_weights / market_weights.sum()

        # Vectorized: implied excess returns
        excess_returns = self.risk_aversion * (cov_matrix @ market_weights)
        return excess_returns + risk_free_rate

    def apply_views(
        self,
        implied_returns: np.ndarray,
        cov_matrix: np.ndarray,
        views: List[Tuple[np.ndarray, float, float]],
        risk_free_rate: float = 0.02,
        regime_confidence: Optional[float] = None,
    ) -> np.ndarray:
        """
        Apply investor views to market-implied returns.

        Args:
            implied_returns: Market-implied expected returns (n_assets,).
            cov_matrix: Covariance matrix (n_assets, n_assets).
            views: List of (view_vector, expected_return, confidence) tuples.
            risk_free_rate: Risk-free rate.
            regime_confidence: Optional HMM regime confidence (0-1, T-1 lagged).

        Returns:
            Posterior expected returns (n_assets,).
        """
        if not views:
            return implied_returns

        # Build view matrix P and view returns Q (vectorized)
        P = np.array([v[0] for v in views], dtype=np.float64)
        Q = np.array([v[1] for v in views], dtype=np.float64)
        confidence = np.array([v[2] for v in views], dtype=np.float64)

        # Regime-aware confidence scaling (PIT: regime_confidence is T-1 lagged)
        if regime_confidence is not None:
            confidence = confidence * regime_confidence
            logger.debug(
                "Regime-adjusted confidence: %.3f (regime_conf=%.3f)",
                confidence.mean(),
                regime_confidence,
            )

        # Omega: uncertainty in views (diagonal matrix)
        omega_diag = (1.0 - confidence) / (confidence + 1e-8)
        omega_diag = np.clip(omega_diag, 1e-4, 1.0)
        Omega = np.diag(omega_diag)

        # Posterior covariance of views
        tau_sigma = self.tau * cov_matrix
        M_inv = P @ tau_sigma @ P.T + Omega

        try:
            M = np.linalg.inv(M_inv)
        except np.linalg.LinAlgError:
            logger.warning(
                "Singular matrix in Black-Litterman. Using pseudo-inverse."
            )
            M = np.linalg.pinv(M_inv)

        # Posterior expected returns (vectorized)
        view_error = Q - P @ implied_returns
        posterior_excess = tau_sigma @ P.T @ M @ view_error
        posterior_returns = implied_returns + posterior_excess

        gc.collect()
        return posterior_returns

    def optimize_weights(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        max_weight: float = 0.2,
        min_weight: float = 0.0,
        adv_limits: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Optimize portfolio weights with L2 regularization and liquidity constraints.

        Args:
            expected_returns: Expected returns (n_assets,).
            cov_matrix: Covariance matrix (n_assets, n_assets).
            max_weight: Maximum weight per asset.
            min_weight: Minimum weight per asset.
            adv_limits: Optional liquidity limits per asset.

        Returns:
            Optimal weights (n_assets,).
        """
        n_assets = len(expected_returns)

        # Scale-aware L2 regularization
        l2_scaled = self.l2_lambda * np.trace(cov_matrix) / n_assets
        cov_regularized = cov_matrix + l2_scaled * np.eye(n_assets)

        # Volatilities (vectorized)
        vols = np.sqrt(np.maximum(np.diag(cov_regularized), 1e-8))

        # Sharpe-like scores (vectorized)
        sharpe_scores = expected_returns / (vols + 1e-8)
        sharpe_scores = np.clip(sharpe_scores, 0, None)  # Long-only

        # Normalize to weights
        total_score = sharpe_scores.sum()
        if total_score > 0:
            weights = sharpe_scores / total_score
        else:
            weights = np.ones(n_assets) / n_assets

        # Apply liquidity constraints
        if adv_limits is not None:
            effective_max = np.minimum(max_weight, adv_limits)
        else:
            effective_max = np.full(n_assets, max_weight)

        return self._bounded_allocate(weights, effective_max, min_weight=min_weight)

    def get_portfolio_weights(
        self,
        symbols: List[str],
        market_weights: Dict[str, float],
        cov_matrix: np.ndarray,
        views: Optional[List[Tuple[np.ndarray, float, float]]] = None,
        max_weight: float = 0.15,
        adv_dict: Optional[Dict[str, float]] = None,
        portfolio_nav: float = 2_000_000_000,
        regime_confidence: Optional[float] = None,
        prev_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Full Black-Litterman portfolio optimization pipeline.

        Args:
            symbols: List of symbol tickers.
            market_weights: Market cap weights {symbol: weight}.
            cov_matrix: Covariance matrix (n x n).
            views: Optional views [(view_vector, expected_return, confidence), ...].
            max_weight: Maximum weight per asset.
            adv_dict: Optional ADV {symbol: adv_value_vnd}.
            portfolio_nav: Portfolio NAV in VND.
            regime_confidence: Optional HMM regime confidence (0-1, T-1 lagged).
            prev_weights: Optional previous weights for turnover constraint.

        Returns:
            Optimal portfolio weights {symbol: weight}.
        """
        n_assets = len(symbols)
        market_w = np.array(
            [market_weights.get(s, 0.0) for s in symbols], dtype=np.float64
        )
        implied = self.get_market_implied_returns(market_w, cov_matrix)

        if views:
            posterior = self.apply_views(
                implied, cov_matrix, views, regime_confidence=regime_confidence
            )
        else:
            posterior = implied

        # Liquidity limits (fail closed: missing ADV -> 0 capacity)
        portfolio_nav_f = float(portfolio_nav)
        adv_limits = np.full(n_assets, max_weight, dtype=np.float64)

        if adv_dict is not None:
            adv_array = np.array(
                [adv_dict.get(s, 0.0) for s in symbols], dtype=np.float64
            )
            safe_pos_value = adv_array * self.max_adv_pct
            adv_limits = np.minimum(max_weight, safe_pos_value / portfolio_nav_f)

        # Mean-variance optimization with L2 regularization
        l2_scaled = self.l2_lambda * np.trace(cov_matrix) / n_assets
        cov_regularized = cov_matrix + l2_scaled * np.eye(n_assets)

        try:
            inv_cov = np.linalg.inv(cov_regularized)
        except np.linalg.LinAlgError:
            logger.warning(
                "Singular covariance in optimization. Using pseudo-inverse."
            )
            inv_cov = np.linalg.pinv(cov_regularized)

        raw_weights = inv_cov @ posterior
        raw_weights = np.maximum(raw_weights, 0.0)  # Long-only
        total = raw_weights.sum()
        if total > 0:
            raw_weights = raw_weights / total

        gc.collect()

        effective_max = np.minimum(max_weight, adv_limits)
        weights = self._bounded_allocate(raw_weights, effective_max)

        # Per-asset caps
        final_caps = np.minimum(max_weight, effective_max)
        total_capacity = final_caps.sum()

        # Turnover constraint
        turnover_applied = False
        if prev_weights is not None and self.max_turnover_per_rebalance < 1.0:
            prev_w = np.array(
                [prev_weights.get(s, 0.0) for s in symbols], dtype=np.float64
            )
            prev_w = np.minimum(prev_w, final_caps)
            weights = np.minimum(weights, final_caps)

            proposed_turnover = float(np.abs(weights - prev_w).sum())

            if proposed_turnover > self.max_turnover_per_rebalance:
                weight_delta = weights - prev_w
                scale_factor = self.max_turnover_per_rebalance / proposed_turnover
                weights = prev_w + weight_delta * scale_factor
                weights = np.maximum(weights, 0.0)
                weights = np.minimum(weights, final_caps)
                turnover_applied = True

        # Post-turnover concentration safety
        if not turnover_applied:
            for _ in range(100):
                violations = weights > final_caps
                if not violations.any():
                    break
                weights = np.minimum(weights, final_caps)
                if total_capacity >= 1.0:
                    total = weights.sum()
                    if total > 0:
                        weights = weights / total
                    else:
                        weights = np.ones(n_assets) / n_assets
                        break
                else:
                    break

        return {s: float(w) for s, w in zip(symbols, weights)}
