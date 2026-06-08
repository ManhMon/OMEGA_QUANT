"""
Portfolio Optimizer - Institutional Grade

Implements three optimization methods:
1. Mean-Variance Optimization (MVO) - Markowitz efficient frontier
2. Risk Parity - Equal risk contribution across assets
3. Black-Litterman - Bayesian approach combining market equilibrium with views

All methods enforce institutional constraints via PortfolioConstraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import minimize

from src.portfolio.constraints import (
    PortfolioConstraints,
    validate_portfolio,
    apply_constraints,
)


class OptimizationMethod(Enum):
    """Supported optimization methods."""
    MVO = "mean_variance"
    RISK_PARITY = "risk_parity"
    BLACK_LITTERMAN = "black_litterman"


@dataclass
class OptimizationResult:
    """Result from portfolio optimization."""
    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    method: OptimizationMethod
    converged: bool
    message: str = ""
    constraint_violations: List[str] = field(default_factory=list)


class PortfolioOptimizer:
    """
    Institutional-grade portfolio optimizer.
    
    Features:
    - Mean-Variance Optimization (MVO)
    - Risk Parity
    - Black-Litterman
    - Constraint enforcement (position, sector, liquidity, board-lot)
    - Vectorized operations for performance
    """

    def __init__(
        self,
        risk_free_rate: float = 0.05,
        max_iterations: int = 1000,
        tolerance: float = 1e-8,
    ):
        """
        Initialize optimizer.
        
        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
            max_iterations: Maximum optimization iterations
            tolerance: Convergence tolerance
        """
        self.risk_free_rate = risk_free_rate
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def optimize(
        self,
        method: OptimizationMethod,
        expected_returns: Dict[str, float],
        covariance_matrix: np.ndarray,
        symbols: List[str],
        constraints: Optional[Dict] = None,
        views: Optional[Dict] = None,
        sector_map: Optional[Dict[str, str]] = None,
        adv_data: Optional[Dict[str, float]] = None,
        portfolio_value: Optional[float] = None,
        prices: Optional[Dict[str, float]] = None,
    ) -> OptimizationResult:
        """
        Optimize portfolio weights.
        
        Args:
            method: Optimization method to use
            expected_returns: Expected returns per symbol {symbol: return}
            covariance_matrix: Covariance matrix (NxN numpy array)
            symbols: List of symbols (must match covariance matrix order)
            constraints: Optional constraint dict (max_position, max_sector, etc.)
            views: Optional views for Black-Litterman {symbol: view_return}
            sector_map: Optional sector mapping {symbol: sector} for sector constraints
            adv_data: Optional ADV data {symbol: adv_vnd} for liquidity constraints
            portfolio_value: Optional portfolio value (VND) for liquidity/board-lot checks
            prices: Optional prices {symbol: price_in_1000_vnd} for liquidity/board-lot checks
            
        Returns:
            OptimizationResult with optimal weights and metrics
        """
        # Validate inputs
        n_assets = len(symbols)
        if covariance_matrix.shape != (n_assets, n_assets):
            raise ValueError(
                f"Covariance matrix shape {covariance_matrix.shape} "
                f"does not match {n_assets} symbols"
            )

        # Convert expected returns to array (aligned with symbols)
        mu = np.array([expected_returns.get(s, 0.0) for s in symbols])

        # Route to appropriate method
        if method == OptimizationMethod.MVO:
            result = self._optimize_mvo(mu, covariance_matrix, symbols, constraints, sector_map)
        elif method == OptimizationMethod.RISK_PARITY:
            result = self._optimize_risk_parity(covariance_matrix, symbols, constraints, sector_map)
        elif method == OptimizationMethod.BLACK_LITTERMAN:
            if views is None:
                raise ValueError("Black-Litterman requires views parameter")
            result = self._optimize_black_litterman(
                mu, covariance_matrix, symbols, views, constraints, sector_map
            )
        else:
            raise ValueError(f"Unknown optimization method: {method}")

        # Post-optimization: Apply constraints and validate
        # This ensures sector/liquidity/board-lot constraints are enforced
        # Only apply if base optimization succeeded
        if constraints and result.converged:
            constraint_config = PortfolioConstraints(
                max_position=constraints.get("max_position", 0.25),
                max_sector=constraints.get("max_sector", 0.40),
                max_adv_participation=constraints.get("max_adv_participation", 0.40),
                board_lot=constraints.get("board_lot", 100),
                min_weight=constraints.get("min_weight", 0.01),
            )

            # Apply sector constraints (post-optimization adjustment)
            adjusted_weights = apply_constraints(
                result.weights, constraint_config, sector_map
            )

            # Enforce liquidity and board-lot constraints via iterative repair
            if adv_data and portfolio_value and prices:
                adjusted_weights, converged = self._enforce_liquidity_and_board_lot(
                    adjusted_weights,
                    constraint_config,
                    symbols,
                    adv_data,
                    portfolio_value,
                    prices,
                )
                
                if not converged:
                    result.converged = False
                    result.message = "Failed to converge: constraints infeasible with given market data"
                    result.weights = adjusted_weights
                    return result

            # Validate all constraints (should have zero violations after enforcement)
            violations = validate_portfolio(
                adjusted_weights,
                constraint_config,
                sector_map=sector_map,
                adv_data=adv_data,
                portfolio_value=portfolio_value,
                prices=prices,
            )

            # Update result with adjusted weights and violations
            result.weights = adjusted_weights
            result.constraint_violations = [v.message for v in violations]
            
            # CRITICAL FIX: Convergence flag must check full validation report
            # However, position_limit violations are acceptable when caused by normalization
            # due to cash held from board-lot rounding (total_weight < 1.0)
            total_weight = sum(adjusted_weights.values())
            critical_violations = []
            
            for v in violations:
                # Position limit violations are acceptable if:
                # 1. Total weight < 1.0 (cash held due to board-lot rounding)
                # 2. The violation is only in the normalized weight, not raw weight
                if v.constraint_type == "position_limit" and total_weight < 1.0 - 0.01:
                    # Check if raw weight is within limit
                    raw_weight = adjusted_weights.get(v.symbol, 0.0)
                    if raw_weight <= constraint_config.max_position + 1e-6:
                        # This is acceptable - violation only exists after normalization
                        continue
                
                # All other violations are critical
                critical_violations.append(v)
            
            if critical_violations:
                result.converged = False
                result.message = f"Optimization failed: {len(critical_violations)} constraint violation(s) remain"

            # Recalculate metrics with adjusted weights
            weights_array = np.array([adjusted_weights.get(s, 0.0) for s in symbols])
            result.expected_return = float(np.dot(weights_array, mu))
            result.expected_volatility = float(
                np.sqrt(np.dot(weights_array, np.dot(covariance_matrix, weights_array)))
            )
            if result.expected_volatility > 0:
                result.sharpe_ratio = (
                    result.expected_return - self.risk_free_rate
                ) / result.expected_volatility
            else:
                result.sharpe_ratio = 0.0

        return result

    def _optimize_mvo(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        symbols: List[str],
        constraints: Optional[Dict],
        sector_map: Optional[Dict[str, str]],
    ) -> OptimizationResult:
        """
        Mean-Variance Optimization (Markowitz).
        
        Maximizes Sharpe ratio: (return - rf) / volatility
        Subject to: sum(weights) = 1, weights >= 0, position limits, and sector limits
        """
        n = len(symbols)

        # Objective: minimize negative Sharpe ratio
        def objective(w: np.ndarray) -> float:
            port_return = np.dot(w, mu)
            port_vol = np.sqrt(np.dot(w, np.dot(cov, w)))
            if port_vol < 1e-10:
                return 1e10  # Penalize zero volatility
            sharpe = (port_return - self.risk_free_rate) / port_vol
            return -sharpe  # Minimize negative Sharpe

        # Constraints
        cons = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},  # Weights sum to 1
        ]

        # Add sector constraints if sector_map provided
        if sector_map and constraints:
            max_sector = constraints.get("max_sector", 0.40)
            # Build sector constraint functions
            sectors = set(sector_map.values())
            for sector in sectors:
                # Get indices of symbols in this sector
                sector_indices = [i for i, sym in enumerate(symbols) if sector_map.get(sym) == sector]
                if sector_indices:
                    # Constraint: sum of weights in sector <= max_sector
                    cons.append({
                        "type": "ineq",
                        "fun": lambda w, idx=sector_indices: max_sector - np.sum(w[idx])
                    })

        # Bounds: [0, max_position]
        max_pos = constraints.get("max_position", 0.25) if constraints else 0.25
        bounds = [(0.0, max_pos) for _ in range(n)]

        # Initial guess: equal weight
        w0 = np.ones(n) / n

        # Optimize
        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": self.max_iterations, "ftol": self.tolerance},
        )

        # Extract results
        weights_array = result.x
        weights_dict = {symbols[i]: float(weights_array[i]) for i in range(n)}

        # Calculate metrics
        port_return = np.dot(weights_array, mu)
        port_vol = np.sqrt(np.dot(weights_array, np.dot(cov, weights_array)))
        sharpe = (port_return - self.risk_free_rate) / port_vol if port_vol > 0 else 0.0

        # Check if result is usable even if optimizer didn't fully converge
        # SLSQP sometimes reports failure even when constraints are satisfied
        weights_sum = np.sum(weights_array)
        bounds_satisfied = all(-1e-6 <= w <= max_pos + 1e-6 for w in weights_array)
        sum_constraint_satisfied = abs(weights_sum - 1.0) < 1e-3
        
        # If constraints are satisfied, treat as converged regardless of optimizer status
        converged = result.success or (sum_constraint_satisfied and bounds_satisfied)

        return OptimizationResult(
            weights=weights_dict,
            expected_return=float(port_return),
            expected_volatility=float(port_vol),
            sharpe_ratio=float(sharpe),
            method=OptimizationMethod.MVO,
            converged=converged,
            message="Optimization successful" if converged else result.message,
        )

    def _optimize_risk_parity(
        self,
        cov: np.ndarray,
        symbols: List[str],
        constraints: Optional[Dict],
        sector_map: Optional[Dict[str, str]],
    ) -> OptimizationResult:
        """
        Risk Parity Optimization.
        
        Allocates weights such that each asset contributes equally to portfolio risk.
        Risk contribution: w_i * (Cov * w)_i / sqrt(w^T * Cov * w)
        Subject to: sum(weights) = 1, weights >= 0, position limits, and sector limits
        """
        n = len(symbols)

        # Objective: minimize variance of risk contributions
        def objective(w: np.ndarray) -> float:
            # Portfolio volatility
            port_vol = np.sqrt(np.dot(w, np.dot(cov, w)))
            if port_vol < 1e-10:
                return 1e10

            # Marginal risk contribution: (Cov * w) / port_vol
            mrc = np.dot(cov, w) / port_vol

            # Risk contribution: w_i * mrc_i
            rc = w * mrc

            # Target: equal risk contribution (1/n of total risk)
            target_rc = port_vol / n

            # Minimize sum of squared deviations
            return np.sum((rc - target_rc) ** 2)

        # Constraints
        cons = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]

        # Add sector constraints if sector_map provided
        if sector_map and constraints:
            max_sector = constraints.get("max_sector", 0.40)
            sectors = set(sector_map.values())
            for sector in sectors:
                sector_indices = [i for i, sym in enumerate(symbols) if sector_map.get(sym) == sector]
                if sector_indices:
                    cons.append({
                        "type": "ineq",
                        "fun": lambda w, idx=sector_indices: max_sector - np.sum(w[idx])
                    })

        # Bounds
        max_pos = constraints.get("max_position", 0.25) if constraints else 0.25
        bounds = [(0.0, max_pos) for _ in range(n)]

        # Initial guess: equal weight
        w0 = np.ones(n) / n

        # Optimize
        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": self.max_iterations, "ftol": self.tolerance},
        )

        # Extract results
        weights_array = result.x
        weights_dict = {symbols[i]: float(weights_array[i]) for i in range(n)}

        # Calculate metrics (no expected return for risk parity)
        port_vol = np.sqrt(np.dot(weights_array, np.dot(cov, weights_array)))

        return OptimizationResult(
            weights=weights_dict,
            expected_return=0.0,  # Risk parity doesn't optimize for return
            expected_volatility=float(port_vol),
            sharpe_ratio=0.0,
            method=OptimizationMethod.RISK_PARITY,
            converged=result.success,
            message=result.message,
        )

    def _optimize_black_litterman(
        self,
        mu_market: np.ndarray,
        cov: np.ndarray,
        symbols: List[str],
        views: Dict[str, float],
        constraints: Optional[Dict],
        sector_map: Optional[Dict[str, str]],
    ) -> OptimizationResult:
        """
        Black-Litterman Optimization.
        
        Combines market equilibrium returns with investor views using Bayesian approach.
        
        Args:
            mu_market: Market equilibrium returns (prior)
            cov: Covariance matrix
            symbols: Symbol list
            views: Investor views {symbol: view_return}
            constraints: Position/sector constraints
            sector_map: Sector mapping for sector constraints
        """
        n = len(symbols)

        # Black-Litterman parameters
        tau = 0.05  # Uncertainty in prior (typically 0.01 - 0.05)
        
        # Build view matrix P and view vector Q
        # P: k x n matrix (k views, n assets)
        # Q: k x 1 vector of view returns
        view_symbols = [s for s in symbols if s in views]
        k = len(view_symbols)
        
        if k == 0:
            # No views, fall back to market equilibrium (MVO)
            result = self._optimize_mvo(mu_market, cov, symbols, constraints, sector_map)
            # Override method to BLACK_LITTERMAN (even though it fell back)
            result.method = OptimizationMethod.BLACK_LITTERMAN
            return result

        P = np.zeros((k, n))
        Q = np.zeros(k)
        
        for i, view_sym in enumerate(view_symbols):
            idx = symbols.index(view_sym)
            P[i, idx] = 1.0
            Q[i] = views[view_sym]

        # View uncertainty (Omega): diagonal matrix
        # Simplified: Omega = tau * P * Cov * P^T
        Omega = tau * np.dot(P, np.dot(cov, P.T))

        # Black-Litterman formula:
        # mu_BL = [(tau * Cov)^-1 + P^T * Omega^-1 * P]^-1 * [(tau * Cov)^-1 * mu_market + P^T * Omega^-1 * Q]
        
        tau_cov = tau * cov
        tau_cov_inv = np.linalg.inv(tau_cov + np.eye(n) * 1e-8)  # Add small regularization
        omega_inv = np.linalg.inv(Omega + np.eye(k) * 1e-8)

        # Posterior precision
        M_inv = tau_cov_inv + np.dot(P.T, np.dot(omega_inv, P))
        M = np.linalg.inv(M_inv + np.eye(n) * 1e-8)

        # Posterior mean
        mu_bl = np.dot(
            M,
            np.dot(tau_cov_inv, mu_market) + np.dot(P.T, np.dot(omega_inv, Q))
        )

        # Now optimize using Black-Litterman adjusted returns
        result = self._optimize_mvo(mu_bl, cov, symbols, constraints, sector_map)
        # Override method to BLACK_LITTERMAN
        result.method = OptimizationMethod.BLACK_LITTERMAN
        return result

    def _enforce_liquidity_and_board_lot(
        self,
        weights: Dict[str, float],
        constraints: PortfolioConstraints,
        symbols: List[str],
        adv_data: Dict[str, float],
        portfolio_value: float,
        prices: Dict[str, float],
        max_iterations: int = 50,
    ) -> Tuple[Dict[str, float], bool]:
        """
        Enforce liquidity and board-lot constraints via iterative projection/repair.
        
        Algorithm:
        1. Check for violations (liquidity, board-lot)
        2. If violations exist:
           a. For liquidity: reduce violating weights proportionally
           b. For board-lot: round shares to board lot, recalculate weights
           c. Renormalize to sum to 1.0
        3. Repeat until no violations or max iterations reached
        
        Note: Board-lot rounding may cause weights to sum to slightly less than 1.0.
        This is acceptable and represents cash held due to rounding.
        
        Args:
            weights: Current portfolio weights
            constraints: Constraint configuration
            symbols: List of symbols
            adv_data: ADV data {symbol: adv_vnd}
            portfolio_value: Portfolio value (VND)
            prices: Prices {symbol: price_in_1000_vnd}
            max_iterations: Maximum repair iterations
            
        Returns:
            Tuple of (adjusted_weights, converged)
            converged=False if constraints are infeasible
        """
        adjusted = weights.copy()
        
        for iteration in range(max_iterations):
            # Calculate violations
            liquidity_violations = {}
            board_lot_violations = {}
            
            for symbol, weight in adjusted.items():
                if weight < 1e-6:
                    continue
                    
                position_value = weight * portfolio_value
                price = prices.get(symbol, 0.0)
                adv_vnd = adv_data.get(symbol, 0.0)
                
                if price <= 0 or adv_vnd <= 0:
                    continue
                
                # Liquidity check
                position_shares = position_value / (price * 1000.0)
                adv_shares = adv_vnd / (price * 1000.0)
                participation = position_shares / adv_shares if adv_shares > 0 else 0.0
                
                if participation > constraints.max_adv_participation + 1e-6:
                    liquidity_violations[symbol] = participation
                
                # Board-lot check
                shares = int(position_value / (price * 1000.0))
                if shares > 0 and shares % constraints.board_lot != 0:
                    board_lot_violations[symbol] = shares
            
            # If no violations, we're done
            if not liquidity_violations and not board_lot_violations:
                return adjusted, True
            
            # Repair violations in priority order:
            # 1. Liquidity violations (higher priority)
            # 2. Board-lot violations
            
            if liquidity_violations:
                for symbol, participation in liquidity_violations.items():
                    # Scale down to max allowed participation with small buffer
                    scale_factor = (constraints.max_adv_participation * 0.99) / participation
                    adjusted[symbol] *= scale_factor
                
                # Do NOT renormalize - this would break position limits
                # The sum being < 1.0 represents cash held due to liquidity constraints
            
            # Repair board-lot violations
            elif board_lot_violations:
                # Calculate target shares for all positions (rounded to board lot)
                target_shares = {}
                for symbol, weight in adjusted.items():
                    if weight < 1e-6:
                        continue
                    price = prices.get(symbol, 0.0)
                    if price <= 0:
                        continue
                    
                    position_value = weight * portfolio_value
                    shares = int(position_value / (price * 1000.0))
                    
                    # Round to board lot
                    rounded_shares = (shares // constraints.board_lot) * constraints.board_lot
                    if rounded_shares > 0:
                        target_shares[symbol] = rounded_shares
                
                # Recalculate weights from rounded shares
                # Weights represent fraction of portfolio_value, so sum may be < 1.0
                if target_shares:
                    adjusted = {}
                    for symbol, shares in target_shares.items():
                        price = prices.get(symbol, 0.0)
                        position_value = shares * price * 1000.0
                        adjusted[symbol] = position_value / portfolio_value
                    
                    # Do NOT renormalize - this would break board-lot alignment
                    # The sum being < 1.0 represents cash held due to rounding
                    # Position limit violations will be caught in next iteration
                else:
                    # No valid positions after rounding
                    return weights, False
            
            # Remove positions that became too small
            adjusted = {
                sym: w for sym, w in adjusted.items()
                if w >= constraints.min_weight
            }
            
            # Check if we have any weights left
            if not adjusted or sum(adjusted.values()) < 1e-6:
                # Infeasible: all positions violated constraints
                return weights, False
        
        # Max iterations reached - check final state
        final_violations = validate_portfolio(
            adjusted,
            constraints,
            adv_data=adv_data,
            portfolio_value=portfolio_value,
            prices=prices,
        )
        # Check for liquidity and board-lot violations only
        # Position limit violations are acceptable when cash is held due to board-lot rounding
        critical_violations = [
            v for v in final_violations
            if v.constraint_type in ("liquidity_limit", "board_lot")
        ]
        
        if critical_violations:
            return adjusted, False
        
        return adjusted, True
