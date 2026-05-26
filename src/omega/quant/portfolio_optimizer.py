"""Portfolio Optimizer for OMEGA_QUANT Phase 3.2.

Implements mean-variance optimization with institutional constraints:
- PIT (Point-In-Time) safety: weights at time t use only data from t-1
- Vectorized NumPy/Pandas operations for performance
- Constraint enforcement: leverage, concentration, liquidity limits
- Deterministic: same inputs â†’ same outputs

Usage:
    optimizer = PortfolioOptimizer(max_leverage=1.0, max_concentration=0.1)
    weights = optimizer.optimize_weights(alpha_scores, constraints)
    metrics = optimizer.calculate_portfolio_metrics(weights, returns)
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from scipy.optimize import minimize


@dataclass
class OptimizerConfig:
    """Portfolio optimizer configuration (alias for PortfolioConstraints)."""
    max_leverage: float = 1.0  # Maximum gross leverage
    max_concentration: float = 0.1  # Maximum single asset weight
    min_weight: float = 0.0  # Minimum position size
    max_weight: float = 1.0  # Maximum position size
    max_turnover: Optional[float] = None  # Maximum turnover vs previous weights
    turnover_penalty: float = 0.0  # Penalty factor for turnover in objective
    transaction_cost_bps: float = 0.0  # Transaction cost in basis points (1/10000)
    sector_limits: Optional[Dict[str, float]] = None  # Sector exposure limits
    liquidity_limits: Optional[Dict[str, float]] = None  # Asset liquidity constraints
    method: str = "mean_variance"  # Optimization method
    rebalance_threshold: Optional[float] = None  # Rebalancing threshold
    allow_short: bool = False  # Allow short positions
    sector_neutral: bool = False  # Enforce sector neutrality


@dataclass
class PortfolioConstraints:
    """Portfolio construction constraints."""
    max_leverage: float = 1.0  # Maximum gross leverage
    max_concentration: float = 0.1  # Maximum single asset weight
    min_weight: float = 0.0  # Minimum position size
    max_weight: float = 1.0  # Maximum position size
    max_turnover: Optional[float] = None  # Maximum turnover vs previous weights
    turnover_penalty: float = 0.0  # Penalty factor for turnover in objective
    transaction_cost_bps: float = 0.0  # Transaction cost in basis points
    sector_limits: Optional[Dict[str, float]] = None  # Sector exposure limits
    liquidity_limits: Optional[Dict[str, float]] = None  # Asset liquidity constraints


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics."""
    expected_return: float
    expected_risk: float
    sharpe_ratio: float
    max_weight: float
    min_weight: float
    gross_leverage: float
    num_positions: int


class PortfolioOptimizer:
    """Mean-variance portfolio optimizer with institutional constraints.
    
    Implements Markowitz mean-variance optimization with:
    - Quadratic programming for optimal weight calculation
    - Constraint enforcement (leverage, concentration, turnover)
    - PIT-safe operations (T-1 lag enforcement)
    - Vectorized NumPy operations for performance
    """
    
    def __init__(
        self,
        config: Optional[OptimizerConfig] = None,
        max_leverage: float = 1.0,
        max_concentration: float = 0.1,
        risk_aversion: float = 1.0,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        turnover_penalty: float = 0.0,
        transaction_cost_bps: float = 0.0
    ):
        """Initialize portfolio optimizer.
        
        Args:
            config: Optional OptimizerConfig object (takes precedence over individual params).
            max_leverage: Maximum gross leverage (sum of absolute weights).
            max_concentration: Maximum weight for any single asset.
            risk_aversion: Risk aversion parameter (higher = more conservative).
            min_weight: Minimum position size (0 for long-only).
            max_weight: Maximum position size.
            turnover_penalty: Penalty factor for turnover in objective function.
            transaction_cost_bps: Transaction cost in basis points (1/10000).
        """
        if config is not None:
            self.config = config
            self.max_leverage = config.max_leverage
            self.max_concentration = config.max_concentration
            self.risk_aversion = 1.0  # Not in config, use default
            self.min_weight = config.min_weight
            self.max_weight = config.max_weight
            self.turnover_penalty = config.turnover_penalty
            self.transaction_cost_bps = config.transaction_cost_bps
        else:
            self.config = OptimizerConfig(
                max_leverage=max_leverage,
                max_concentration=max_concentration,
                min_weight=min_weight,
                max_weight=max_weight,
                turnover_penalty=turnover_penalty,
                transaction_cost_bps=transaction_cost_bps
            )
            self.max_leverage = max_leverage
            self.max_concentration = max_concentration
            self.risk_aversion = risk_aversion
            self.min_weight = min_weight
            self.max_weight = max_weight
            self.turnover_penalty = turnover_penalty
            self.transaction_cost_bps = transaction_cost_bps
    
    def optimize_weights(
        self,
        alpha_scores: pd.Series,
        constraints: Optional[PortfolioConstraints] = None,
        covariance_matrix: Optional[pd.DataFrame] = None,
        previous_weights: Optional[pd.Series] = None
    ) -> pd.Series:
        """Optimize portfolio weights using mean-variance optimization.
        
        PIT Safety: All inputs must be T-1 lagged (available at decision time).
        
        Args:
            alpha_scores: Expected returns/alpha scores for each asset (T-1 data).
            constraints: Portfolio constraints (optional, uses defaults if None).
            covariance_matrix: Asset return covariance matrix (T-1 data, optional).
            previous_weights: Previous portfolio weights for turnover control (optional).
        
        Returns:
            Optimized portfolio weights as pd.Series (index = asset names).
        
        Raises:
            ValueError: If inputs are misaligned or optimization fails.
        """
        # Validate inputs
        if alpha_scores.empty:
            raise ValueError("alpha_scores cannot be empty")
        
        if alpha_scores.isna().any():
            raise ValueError("alpha_scores contains NaN values")
            
        # PIT Safety Check: previous_weights must be EXACT T-1 if metadata available
        if previous_weights is not None and hasattr(previous_weights, 'name') and isinstance(previous_weights.name, pd.Timestamp):
            if hasattr(alpha_scores, 'name') and isinstance(alpha_scores.name, pd.Timestamp):
                # Verify previous is exactly 1 trading day before current
                # Note: BDay(1) is a simple approximation; institutional code should use actual calendar
                expected_prev = alpha_scores.name - pd.offsets.BDay(1)
                if previous_weights.name != expected_prev:
                    raise ValueError(f"PIT Violation: previous_weights ({previous_weights.name}) must be exact T-1 ({expected_prev})")
        
        # Use default constraints if not provided
        if constraints is None:
            constraints = PortfolioConstraints(
                max_leverage=self.max_leverage,
                max_concentration=self.max_concentration,
                min_weight=self.min_weight,
                max_weight=self.max_weight
            )
        
        # Get asset universe
        assets = alpha_scores.index
        n_assets = len(assets)
        
        # If no covariance matrix provided, use identity (equal risk)
        if covariance_matrix is None:
            covariance_matrix = pd.DataFrame(
                np.eye(n_assets),
                index=assets,
                columns=assets
            )
        else:
            # Validate covariance matrix alignment
            if not assets.equals(covariance_matrix.index):
                raise ValueError("alpha_scores and covariance_matrix indices must match")
        
        # Convert to numpy for optimization
        alpha_vec = alpha_scores.values
        cov_mat = covariance_matrix.values
        
        # Initial guess: proportional to alpha scores (normalized)
        alpha_normalized = alpha_vec / (np.abs(alpha_vec).sum() + 1e-10)
        x0 = np.clip(alpha_normalized, constraints.min_weight, constraints.max_weight)
        x0 = x0 / (np.abs(x0).sum() + 1e-10) * constraints.max_leverage
        
        # Objective function: minimize -return + risk_aversion * risk + turnover_penalty + transaction_cost
        def objective(w):
            portfolio_return = np.dot(w, alpha_vec)
            portfolio_variance = np.dot(w, np.dot(cov_mat, w))
            
            # Base objective: maximize return, minimize risk
            obj = -portfolio_return + self.risk_aversion * portfolio_variance
            
            # Add turnover-based costs (if previous weights provided)
            if previous_weights is not None:
                prev_w = previous_weights.reindex(assets, fill_value=0.0).values
                delta_w = w - prev_w
                # Use smooth approximation for SLSQP: sqrt(x^2 + eps) instead of abs(x)
                smooth_turnover = np.sqrt(delta_w**2 + 1e-9).sum()
                
                # Turnover penalty (gross turnover with smooth surrogate)
                obj += constraints.turnover_penalty * smooth_turnover
                
                # Transaction cost (basis points applied to smooth turnover)
                if constraints.transaction_cost_bps > 0:
                    tc_cost = (constraints.transaction_cost_bps / 10000.0) * smooth_turnover
                    obj += tc_cost
            
            return obj
        
        # Constraints list
        constraint_list = []
        
        # Leverage constraint: sum(|w|) <= max_leverage (smooth approximation)
        constraint_list.append({
            'type': 'ineq',
            'fun': lambda w: constraints.max_leverage - np.sqrt(w**2 + 1e-9).sum()
        })
        
        # Turnover constraint (if previous weights provided)
        if previous_weights is not None and constraints.max_turnover is not None:
            prev_w = previous_weights.reindex(assets, fill_value=0.0).values
            # Use smooth approximation for SLSQP stability
            constraint_list.append({
                'type': 'ineq',
                'fun': lambda w: constraints.max_turnover - np.sqrt((w - prev_w)**2 + 1e-9).sum()
            })
        
        # Bounds: min_weight <= w_i <= max_weight
        bounds = [(constraints.min_weight, constraints.max_weight) for _ in range(n_assets)]
        
        # Apply concentration limit to bounds
        max_w = min(constraints.max_weight, constraints.max_concentration)
        bounds = [(constraints.min_weight, max_w) for _ in range(n_assets)]
        
        # Optimize
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraint_list,
            options={'maxiter': 1000, 'ftol': 1e-9}
        )
        
        if not result.success:
            # Fallback: proportional allocation with constraints
            weights = self._fallback_allocation(alpha_scores, constraints)
        else:
            weights = pd.Series(result.x, index=assets)
        
        # Apply final constraints
        weights = self.apply_constraints(weights, constraints)
        
        return weights
    
    def _fallback_allocation(
        self,
        alpha_scores: pd.Series,
        constraints: PortfolioConstraints
    ) -> pd.Series:
        """Fallback allocation when optimization fails.
        
        Simple proportional allocation based on alpha scores.
        """
        # Normalize alpha scores
        alpha_abs = alpha_scores.abs()
        weights = alpha_scores / (alpha_abs.sum() + 1e-10)
        
        # Scale to max leverage
        weights = weights * constraints.max_leverage
        
        # Clip to bounds
        weights = weights.clip(constraints.min_weight, constraints.max_concentration)
        
        # Renormalize to max leverage
        current_leverage = weights.abs().sum()
        if current_leverage > constraints.max_leverage:
            weights = weights * (constraints.max_leverage / current_leverage)
        
        return weights
    
    def apply_constraints(
        self,
        weights: pd.Series,
        constraints: PortfolioConstraints
    ) -> pd.Series:
        """Apply hard constraints to portfolio weights.
        
        Args:
            weights: Raw portfolio weights.
            constraints: Portfolio constraints to enforce.
        
        Returns:
            Constrained portfolio weights.
        """
        # Clip individual weights
        weights = weights.clip(constraints.min_weight, constraints.max_concentration)
        
        # Enforce leverage limit
        current_leverage = weights.abs().sum()
        if current_leverage > constraints.max_leverage:
            weights = weights * (constraints.max_leverage / current_leverage)
        
        # Enforce liquidity limits (if provided)
        if constraints.liquidity_limits is not None:
            for asset, max_liq_weight in constraints.liquidity_limits.items():
                if asset in weights.index:
                    weights.loc[asset] = np.clip(
                        weights.loc[asset],
                        -max_liq_weight,
                        max_liq_weight
                    )
        
        return weights
    
    def calculate_portfolio_metrics(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        risk_free_rate: float = 0.0
    ) -> PortfolioMetrics:
        """Calculate portfolio performance metrics.
        
        PIT Safety: returns must be T-1 historical data (not forward-looking).
        
        Args:
            weights: Portfolio weights.
            returns: Historical asset returns (T-1 data, shape: [time, assets]).
            risk_free_rate: Risk-free rate for Sharpe ratio calculation.
        
        Returns:
            PortfolioMetrics with expected return, risk, Sharpe ratio, etc.
        
        Raises:
            ValueError: If weights and returns are misaligned.
        """
        # Validate alignment
        common_assets = weights.index.intersection(returns.columns)
        if len(common_assets) == 0:
            raise ValueError("No common assets between weights and returns")
        
        # Align weights and returns
        weights_aligned = weights.reindex(common_assets, fill_value=0.0)
        returns_aligned = returns[common_assets]
        
        # Calculate portfolio returns time series
        portfolio_returns = (returns_aligned * weights_aligned).sum(axis=1)
        
        # Calculate metrics
        expected_return = portfolio_returns.mean()
        expected_risk = portfolio_returns.std()
        
        # Sharpe ratio (annualized assuming daily returns)
        sharpe_ratio = (expected_return - risk_free_rate) / (expected_risk + 1e-10)
        
        # Position statistics
        max_weight = weights_aligned.abs().max()
        min_weight = weights_aligned.abs().min()
        gross_leverage = weights_aligned.abs().sum()
        num_positions = (weights_aligned.abs() > 1e-6).sum()
        
        return PortfolioMetrics(
            expected_return=expected_return,
            expected_risk=expected_risk,
            sharpe_ratio=sharpe_ratio,
            max_weight=max_weight,
            min_weight=min_weight,
            gross_leverage=gross_leverage,
            num_positions=num_positions
        )
    
    def construct_portfolio(
        self,
        alphas: pd.DataFrame,
        method: Optional[str] = None,
        constraints: Optional[PortfolioConstraints] = None
    ) -> pd.DataFrame:
        """
        Construct portfolio weights from alpha signals.
        
        Args:
            alphas: DataFrame with MultiIndex (date, ticker) or flat with date/ticker columns.
            method: Portfolio construction method:
                    - "equal_weight": Equal weight across all assets
                    - "alpha_weight": Weight proportional to alpha scores
                    - "rank_weight": Weight based on alpha rank
                    - "mean_variance": Mean-variance optimization
            constraints: Portfolio constraints (optional).
        
        Returns:
            DataFrame with columns: ticker, date, target_weight (flat format).
        
        Raises:
            ValueError: If alphas are empty or invalid.
        """
        if alphas.empty:
            # Return empty DataFrame with correct columns instead of raising error
            return pd.DataFrame(columns=['ticker', 'date', 'target_weight'])
        
        # Convert to flat format if MultiIndex
        original_format = 'multiindex' if isinstance(alphas.index, pd.MultiIndex) else 'flat'
        
        if original_format == 'multiindex':
            alphas_flat = alphas.reset_index()
        else:
            alphas_flat = alphas.copy()
        
        # Ensure we have date and ticker columns
        if 'date' not in alphas_flat.columns or 'ticker' not in alphas_flat.columns:
            raise ValueError("Alphas must have 'date' and 'ticker' columns")
        
        # Use default constraints if not provided
        if constraints is None:
            constraints = PortfolioConstraints(
                max_leverage=self.max_leverage,
                max_concentration=self.max_concentration,
                min_weight=self.min_weight,
                max_weight=self.max_weight
            )
        
        # Use method from config if available
        if method is None and hasattr(self, 'config'):
            method = self.config.method
        if method is None:
            method = "equal_weight"
        
        # Get alpha column (first numeric column that's not date/ticker/sector)
        exclude_cols = ['date', 'ticker', 'sector', 'expected_return', 'volatility']
        alpha_cols = [col for col in alphas_flat.columns 
                      if col not in exclude_cols and pd.api.types.is_numeric_dtype(alphas_flat[col])]
        if not alpha_cols:
            raise ValueError("No alpha columns found in DataFrame")
        alpha_col = alpha_cols[0]
        
        # Construct weights based on method
        if method == "equal_weight":
            n_assets = len(alphas_flat)
            alphas_flat['target_weight'] = 1.0 / n_assets
        
        elif method == "alpha_weight":
            # Weight proportional to alpha (handle negative alphas)
            alpha_abs = alphas_flat[alpha_col].abs()
            if alpha_abs.sum() > 0:
                alphas_flat['target_weight'] = alpha_abs / alpha_abs.sum()
            else:
                alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
        
        elif method == "rank_weight":
            # Weight based on rank (higher alpha = higher rank = higher weight)
            # Check if all alphas are equal (or nearly equal)
            alpha_std = alphas_flat[alpha_col].std()
            if alpha_std < 1e-10:  # All equal, use equal weight
                alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
            else:
                ranks = alphas_flat[alpha_col].rank(method='average', ascending=True)
                if ranks.sum() > 0:
                    alphas_flat['target_weight'] = ranks / ranks.sum()
                else:
                    alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
        
        elif method == "mean_variance":
            # If expected_return and volatility columns exist, use them
            # Otherwise fall back to alpha-based weighting
            if 'expected_return' in alphas_flat.columns and 'volatility' in alphas_flat.columns:
                # Simple Sharpe-ratio based weighting (full MVO requires covariance matrix)
                sharpe = alphas_flat['expected_return'] / alphas_flat['volatility']
                sharpe_pos = sharpe.clip(lower=0)
                if sharpe_pos.sum() > 0:
                    alphas_flat['target_weight'] = sharpe_pos / sharpe_pos.sum()
                else:
                    alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
            else:
                # Fall back to rank-based weighting using alpha values
                alpha_std = alphas_flat[alpha_col].std()
                if alpha_std < 1e-10:  # All equal
                    alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
                else:
                    ranks = alphas_flat[alpha_col].rank(method='average', ascending=True)
                    if ranks.sum() > 0:
                        alphas_flat['target_weight'] = ranks / ranks.sum()
                    else:
                        alphas_flat['target_weight'] = 1.0 / len(alphas_flat)
        
        else:
            raise ValueError(f"Unknown method: {method}")
        
        # Apply constraints
        alphas_flat['target_weight'] = alphas_flat['target_weight'].clip(
            lower=constraints.min_weight,
            upper=constraints.max_weight
        )
        
        # Renormalize
        total_weight = alphas_flat['target_weight'].sum()
        if total_weight > 0:
            alphas_flat['target_weight'] = alphas_flat['target_weight'] / total_weight
        
        # Apply sector neutrality if requested
        if hasattr(self.config, 'sector_neutral') and self.config.sector_neutral:
            if 'sector' in alphas_flat.columns:
                # Compute target weight per sector (equal weight across sectors)
                sectors = alphas_flat['sector'].unique()
                n_sectors = len(sectors)
                target_sector_weight = 1.0 / n_sectors
                
                # Reweight within each sector to achieve sector neutrality
                for sector in sectors:
                    sector_mask = alphas_flat['sector'] == sector
                    sector_assets = alphas_flat[sector_mask]
                    n_assets_in_sector = len(sector_assets)
                    
                    if n_assets_in_sector > 0:
                        # Distribute sector weight proportionally to current weights
                        sector_current_weights = alphas_flat.loc[sector_mask, 'target_weight']
                        sector_total = sector_current_weights.sum()
                        
                        if sector_total > 0:
                            # Scale to target sector weight
                            alphas_flat.loc[sector_mask, 'target_weight'] = (
                                sector_current_weights / sector_total * target_sector_weight
                            )
                        else:
                            # Equal weight within sector
                            alphas_flat.loc[sector_mask, 'target_weight'] = (
                                target_sector_weight / n_assets_in_sector
                            )
        
        return alphas_flat
    
    def compute_portfolio_metrics(self, portfolio: pd.DataFrame) -> Dict[str, float]:
        """
        Compute portfolio metrics (concentration, diversification, etc.).
        
        Args:
            portfolio: DataFrame with target_weight column.
            
        Returns:
            Dictionary with portfolio metrics.
        """
        metrics = {}
        
        if 'target_weight' in portfolio.columns:
            weights = portfolio['target_weight'].abs()
            
            # Herfindahl index (concentration)
            herfindahl = float((weights ** 2).sum())
            metrics['concentration'] = herfindahl
            metrics['herfindahl_index'] = herfindahl  # Alias
            
            # Effective number of positions (diversification)
            if herfindahl > 0:
                effective_n = float(1.0 / herfindahl)
                metrics['effective_n_positions'] = effective_n
                metrics['effective_n'] = effective_n  # Alias
            else:
                metrics['effective_n_positions'] = 0.0
                metrics['effective_n'] = 0.0
            
            # Max weight
            metrics['max_weight'] = float(weights.max())
            
            # Number of positions
            metrics['num_positions'] = int((weights > 0.001).sum())
        
        return metrics
    
    def compute_turnover(self, current: pd.DataFrame, target: pd.DataFrame) -> float:
        """
        Compute portfolio turnover between current and target weights.
        
        Args:
            current: DataFrame with current weights (ticker, weight columns).
            target: DataFrame with target weights (ticker, target_weight columns).
            
        Returns:
            Turnover as sum of absolute weight changes.
        """
        # Merge on ticker
        if 'ticker' not in current.columns or 'ticker' not in target.columns:
            return 0.0
        
        # Determine weight column in current (try multiple names)
        current_weight_col = None
        for col in ['weight', 'current_weight', 'target_weight']:
            if col in current.columns:
                current_weight_col = col
                break
        
        if current_weight_col is None:
            return 0.0
        
        # Determine weight column in target
        target_weight_col = 'target_weight' if 'target_weight' in target.columns else 'weight'
        if target_weight_col not in target.columns:
            return 0.0
        
        merged = pd.merge(
            current[['ticker', current_weight_col]].rename(columns={current_weight_col: 'current_weight'}),
            target[['ticker', target_weight_col]].rename(columns={target_weight_col: 'target_weight'}),
            on='ticker',
            how='outer'
        ).fillna(0.0)
        
        # Compute turnover as one-way turnover: 0.5 * sum(abs(delta_w))
        # One-way turnover is the standard convention in portfolio management
        # (represents the fraction of portfolio that needs to be rebalanced)
        turnover = 0.5 * (merged['target_weight'] - merged['current_weight']).abs().sum()
        return float(turnover)
    
    def apply_turnover_constraint(
        self,
        current: pd.DataFrame,
        target: pd.DataFrame,
        max_turnover: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Apply turnover constraint to target portfolio.
        
        Args:
            current: DataFrame with current weights.
            target: DataFrame with target weights.
            max_turnover: Maximum allowed turnover (optional, uses config if available).
            
        Returns:
            Adjusted target portfolio with turnover constraint applied.
        """
        if max_turnover is None:
            max_turnover = getattr(self.config, 'max_turnover', None)
        
        if max_turnover is None:
            return target
        
        # Compute current turnover
        turnover = self.compute_turnover(current, target)
        
        if turnover <= max_turnover:
            return target
        
        # Determine weight column in current
        current_weight_col = 'weight' if 'weight' in current.columns else ('current_weight' if 'current_weight' in current.columns else 'target_weight')
        
        # Scale down changes to meet turnover constraint
        merged = pd.merge(
            current[['ticker', current_weight_col]].rename(columns={current_weight_col: 'current_weight'}),
            target[['ticker', 'target_weight']],
            on='ticker',
            how='outer'
        ).fillna(0.0)
        
        # Scale changes
        scale_factor = max_turnover / turnover
        merged['adjusted_weight'] = merged['current_weight'] + scale_factor * (merged['target_weight'] - merged['current_weight'])
        
        # Renormalize
        total = merged['adjusted_weight'].sum()
        if total > 0:
            merged['adjusted_weight'] = merged['adjusted_weight'] / total
        
        result = target.copy()
        result['target_weight'] = merged['adjusted_weight'].values
        
        return result

    def compute_rebalance_trades(
        self,
        current: pd.DataFrame,
        target: pd.DataFrame,
        portfolio_value: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Compute trades needed to rebalance from current to target portfolio.
        
        Args:
            current: DataFrame with current weights (ticker, weight columns).
            target: DataFrame with target weights (ticker, target_weight columns).
            portfolio_value: Total portfolio value (optional).
            
        Returns:
            DataFrame with columns: ticker, trade_weight, trade_value (if portfolio_value provided).
        """
        # Determine weight columns
        current_weight_col = 'current_weight' if 'current_weight' in current.columns else ('weight' if 'weight' in current.columns else 'target_weight')
        target_weight_col = 'target_weight' if 'target_weight' in target.columns else 'weight'
        
        # Merge current and target
        merged = pd.merge(
            current[['ticker', current_weight_col]].rename(columns={current_weight_col: 'current_weight'}),
            target[['ticker', target_weight_col]].rename(columns={target_weight_col: 'target_weight'}),
            on='ticker',
            how='outer'
        ).fillna(0.0)
        
        # Compute trade weights
        merged['trade_weight'] = merged['target_weight'] - merged['current_weight']
        
        # Compute trade values if portfolio value provided
        if portfolio_value is not None:
            merged['trade_value'] = merged['trade_weight'] * portfolio_value
        
        # Return only non-zero trades
        trades = merged[merged['trade_weight'].abs() > 1e-10].copy()
        
        return trades[['ticker', 'trade_weight'] + (['trade_value'] if portfolio_value is not None else [])]
