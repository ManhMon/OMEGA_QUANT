"""
OMEGA_QUANT Constraint Solver Module
Phase 20: Portfolio constraint validation and trade adjustment

Implements institutional-grade constraint checking with:
- Position limits (notional, leverage, concentration)
- Vectorized NumPy/Pandas operations
- PIT safety with as_of/available_at metadata
- Proportional scaling for constraint violations

Author: Backend Engineer (Role 9)
Created: 2026-05-15
Version: 1.1.0 (Fixed: flat portfolio leverage, binary search convergence)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Literal
import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass
class ConstraintConfig:
    """Configuration for portfolio constraints."""
    max_notional_per_asset: float
    max_leverage: float
    max_industry_concentration: float
    max_asset_concentration: float
    as_of: datetime
    available_at: datetime
    long_only: bool = True
    board_lot_size: int = 100
    min_cash_balance: float = 0.0
    
    def __post_init__(self):
        """Validate constraint parameters."""
        if self.max_notional_per_asset <= 0:
            raise ValueError("max_notional_per_asset must be positive")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        if not 0 < self.max_industry_concentration <= 1:
            raise ValueError("max_industry_concentration must be in (0, 1]")
        if not 0 < self.max_asset_concentration <= 1:
            raise ValueError("max_asset_concentration must be in (0, 1]")
        if self.available_at < self.as_of:
            raise ValueError("available_at cannot be before as_of")
        if self.board_lot_size <= 0:
            raise ValueError("board_lot_size must be positive")
        if self.min_cash_balance < 0:
            raise ValueError("min_cash_balance cannot be negative")


@dataclass
class ConstraintViolation:
    """Represents a constraint violation."""
    constraint_type: str
    asset: Optional[str]
    current_value: float
    limit_value: float
    excess: float
    
    def __str__(self) -> str:
        if self.asset:
            return (f"{self.constraint_type} violation for {self.asset}: "
                   f"{self.current_value:.2f} exceeds limit {self.limit_value:.2f} "
                   f"by {self.excess:.2f}")
        return (f"{self.constraint_type} violation: "
               f"{self.current_value:.2f} exceeds limit {self.limit_value:.2f} "
               f"by {self.excess:.2f}")


class ConstraintSolver:
    """Validates and adjusts portfolio trades to satisfy constraints."""
    
    def __init__(self, config: ConstraintConfig):
        """Initialize constraint solver."""
        self.config = config
    
    def validate_constraints(
        self,
        positions: pd.DataFrame,
        prices: pd.DataFrame,
        industry_map: Dict[str, str],
        as_of: datetime,
        current_cash: float = 0.0
    ) -> Tuple[bool, List[ConstraintViolation]]:
        """Validate portfolio positions against all constraints."""
        # PIT safety check
        if self.config.available_at > as_of:
            raise ValueError(
                f"Constraint config not available at {as_of} "
                f"(available_at: {self.config.available_at})"
            )
        
        violations = []
        
        # Filter prices to PIT
        prices_pit = prices[prices['as_of'] <= as_of].copy()
        prices_pit = prices_pit.sort_values('as_of').groupby('asset').last().reset_index()
        
        # Merge positions with prices
        portfolio = positions.merge(prices_pit[['asset', 'price']], on='asset', how='left')
        
        # Check for missing prices
        if portfolio['price'].isna().any():
            missing = portfolio[portfolio['price'].isna()]['asset'].tolist()
            raise ValueError(f"Missing prices for assets: {missing}")
        
        # Calculate notional exposures (vectorized)
        portfolio['notional'] = portfolio['quantity'] * portfolio['price']
        portfolio['abs_notional'] = np.abs(portfolio['notional'])
        
        # 1. Check max notional per asset
        violations.extend(self._check_notional_limits(portfolio))
        
        # 2. Check leverage
        violations.extend(self._check_leverage(portfolio))
        
        # 3. Check asset concentration
        violations.extend(self._check_asset_concentration(portfolio))
        
        # 4. Check industry concentration
        violations.extend(self._check_industry_concentration(portfolio, industry_map))
        
        # 5. Check long-only constraint
        violations.extend(self._check_long_only(portfolio))
        
        # 6. Check board lot constraint
        violations.extend(self._check_board_lot(portfolio))
        
        # 7. Check cash balance constraint
        violations.extend(self._check_cash_balance(portfolio, current_cash))
        
        is_valid = len(violations) == 0
        return is_valid, violations
    
    def _check_notional_limits(self, portfolio: pd.DataFrame) -> List[ConstraintViolation]:
        """Check per-asset notional limits."""
        violations = []
        mask = portfolio['abs_notional'] > self.config.max_notional_per_asset
        violating = portfolio[mask]
        
        violations = [
            ConstraintViolation(
                constraint_type="max_notional_per_asset",
                asset=row.asset,
                current_value=row.abs_notional,
                limit_value=self.config.max_notional_per_asset,
                excess=row.abs_notional - self.config.max_notional_per_asset,
            )
            for row in violating.itertuples(index=False)
        ]
        return violations
    
    def _check_leverage(self, portfolio: pd.DataFrame) -> List[ConstraintViolation]:
        """Check portfolio leverage. Handle flat portfolio (gross=0, net=0) as valid."""
        violations = []
        
        gross_exposure = portfolio['abs_notional'].sum()
        net_exposure = portfolio['notional'].sum()
        
        # FIX: Flat portfolio (gross=0, net=0) is valid
        if gross_exposure < 1e-9:
            return violations
        
        # Leverage = gross / |net|
        if abs(net_exposure) < 1e-9:
            leverage = float('inf')
        else:
            leverage = gross_exposure / abs(net_exposure)
            
        if leverage > self.config.max_leverage:
            violations.append(ConstraintViolation(
                constraint_type="max_leverage",
                asset=None,
                current_value=leverage,
                limit_value=self.config.max_leverage,
                excess=leverage - self.config.max_leverage
            ))
        
        return violations
    
    def _check_asset_concentration(self, portfolio: pd.DataFrame) -> List[ConstraintViolation]:
        """Check single-asset concentration."""
        violations = []
        
        total_abs_notional = portfolio['abs_notional'].sum()
        
        if total_abs_notional > 0:
            portfolio['concentration'] = portfolio['abs_notional'] / total_abs_notional
            mask = portfolio['concentration'] > self.config.max_asset_concentration
            violating = portfolio[mask]
            
            violations = [
                ConstraintViolation(
                    constraint_type="max_asset_concentration",
                    asset=row.asset,
                    current_value=row.concentration,
                    limit_value=self.config.max_asset_concentration,
                    excess=row.concentration - self.config.max_asset_concentration,
                )
                for row in violating.itertuples(index=False)
            ]
        
        return violations
    
    def _check_industry_concentration(
        self,
        portfolio: pd.DataFrame,
        industry_map: Dict[str, str]
    ) -> List[ConstraintViolation]:
        """Check industry concentration."""
        violations = []
        
        portfolio['industry'] = portfolio['asset'].map(industry_map)
        
        if portfolio['industry'].isna().any():
            unmapped = portfolio[portfolio['industry'].isna()]['asset'].tolist()
            raise ValueError(f"Assets not in industry_map: {unmapped}")
        
        total_abs_notional = portfolio['abs_notional'].sum()
        
        if total_abs_notional > 0:
            industry_exposure = portfolio.groupby('industry')['abs_notional'].sum()
            industry_concentration = industry_exposure / total_abs_notional
            
            mask = industry_concentration > self.config.max_industry_concentration
            violating = industry_concentration[mask]
            
            for industry, concentration in violating.items():
                violations.append(ConstraintViolation(
                    constraint_type="max_industry_concentration",
                    asset=industry,
                    current_value=concentration,
                    limit_value=self.config.max_industry_concentration,
                    excess=concentration - self.config.max_industry_concentration
                ))
        
        return violations
    
    def _check_long_only(self, portfolio: pd.DataFrame) -> List[ConstraintViolation]:
        """Check long-only constraint (no short positions)."""
        violations = []
        
        if not self.config.long_only:
            return violations
        
        # Check for negative quantities (short positions)
        mask = portfolio['quantity'] < 0
        violating = portfolio[mask]
        
        violations = [
            ConstraintViolation(
                constraint_type="long_only",
                asset=row.asset,
                current_value=row.quantity,
                limit_value=0.0,
                excess=abs(row.quantity),
            )
            for row in violating.itertuples(index=False)
        ]
        
        return violations
    
    def _check_board_lot(self, portfolio: pd.DataFrame) -> List[ConstraintViolation]:
        """Check board lot constraint (positions must be multiples of board_lot_size)."""
        violations = []
        
        if self.config.board_lot_size <= 0:
            return violations
        
        # Check if quantities are multiples of board_lot_size
        portfolio['remainder'] = np.abs(portfolio['quantity']) % self.config.board_lot_size
        mask = (portfolio['remainder'] > 1e-9) & (np.abs(portfolio['quantity']) > 1e-9)
        violating = portfolio[mask]
        
        violations = [
            ConstraintViolation(
                constraint_type="board_lot",
                asset=row.asset,
                current_value=row.quantity,
                limit_value=self.config.board_lot_size,
                excess=row.remainder,
            )
            for row in violating.itertuples(index=False)
        ]
        
        return violations
    
    def _check_cash_balance(
        self,
        portfolio: pd.DataFrame,
        current_cash: float
    ) -> List[ConstraintViolation]:
        """Check minimum cash balance constraint."""
        violations = []
        
        # Contract: current_cash is total portfolio equity in same currency as prices.
        # For target positions, projected cash = total_equity - target_notional.
        total_trade_cost = portfolio['notional'].sum()
        projected_cash = current_cash - total_trade_cost
        
        if projected_cash < self.config.min_cash_balance:
            violations.append(ConstraintViolation(
                constraint_type="min_cash_balance",
                asset=None,
                current_value=projected_cash,
                limit_value=self.config.min_cash_balance,
                excess=self.config.min_cash_balance - projected_cash
            ))
        
        return violations
    
    def get_violations(
        self,
        positions: pd.DataFrame,
        prices: pd.DataFrame,
        industry_map: Dict[str, str],
        as_of: datetime,
        current_cash: float = 0.0
    ) -> List[ConstraintViolation]:
        """Get list of constraint violations."""
        _, violations = self.validate_constraints(positions, prices, industry_map, as_of, current_cash)
        return violations
    
    def adjust_trades(
        self,
        trades: pd.DataFrame,
        current_positions: pd.DataFrame,
        prices: pd.DataFrame,
        industry_map: Dict[str, str],
        as_of: datetime,
        current_cash: float = 0.0
    ) -> pd.DataFrame:
        """Adjust trades to satisfy constraints using proportional scaling."""
        # PIT safety check
        if self.config.available_at > as_of:
            raise ValueError(
                f"Constraint config not available at {as_of} "
                f"(available_at: {self.config.available_at})"
            )
        
        # Merge current positions with trades
        all_assets = pd.concat([
            current_positions[['asset']],
            trades[['asset']]
        ]).drop_duplicates()
        
        positions_full = all_assets.merge(
            current_positions, on='asset', how='left', suffixes=('', '_current')
        ).merge(
            trades, on='asset', how='left', suffixes=('', '_trade')
        )
        
        positions_full['quantity_current'] = positions_full['quantity'].fillna(0)
        positions_full['quantity_trade'] = positions_full['quantity_trade'].fillna(0)
        
        # Calculate target positions
        target_positions = positions_full[['asset']].copy()
        target_positions['quantity'] = (
            positions_full['quantity_current'] + positions_full['quantity_trade']
        )
        
        # Check if target satisfies constraints
        is_valid, _ = self.validate_constraints(
            target_positions, prices, industry_map, as_of, current_cash
        )
        
        if is_valid:
            return trades.copy()
        
        # FIX: Improved binary search with better convergence
        scale_min = 0.0
        scale_max = 1.0
        scale_best = 0.0
        tolerance = 0.001
        max_iterations = 50
        
        for _ in range(max_iterations):
            scale = (scale_min + scale_max) / 2
            
            scaled_trades = trades.copy()
            scaled_trades['quantity'] = trades['quantity'] * scale
            
            scaled_target = positions_full[['asset']].copy()
            scaled_target['quantity'] = (
                positions_full['quantity_current'] + 
                scaled_trades.set_index('asset')['quantity'].reindex(
                    positions_full['asset']
                ).fillna(0).values
            )
            
            is_valid, _ = self.validate_constraints(
                scaled_target, prices, industry_map, as_of, current_cash
            )
            
            if is_valid:
                scale_best = scale
                scale_min = scale
            else:
                scale_max = scale
            
            if scale_max - scale_min < tolerance:
                break
        
        adjusted_trades = trades.copy()
        adjusted_trades['quantity'] = trades['quantity'] * scale_best
        
        return adjusted_trades
    
    def optimize_portfolio(
        self,
        returns: pd.DataFrame,
        prices: pd.DataFrame,
        industry_map: Dict[str, str],
        as_of: datetime,
        method: Literal['mvo', 'risk_parity'] = 'mvo',
        target_return: Optional[float] = None,
        current_cash: float = 0.0
    ) -> pd.DataFrame:
        """
        Optimize portfolio weights using MVO or Risk Parity.
        
        Args:
            returns: DataFrame with columns ['asset', 'as_of', 'return']
            prices: DataFrame with columns ['asset', 'as_of', 'price']
            industry_map: Dict mapping asset to industry
            as_of: Point-in-time date for optimization
            method: 'mvo' for Mean-Variance Optimization or 'risk_parity' for Risk Parity
            target_return: Target return for MVO (if None, maximize Sharpe ratio)
            current_cash: Available cash for trading
            
        Returns:
            DataFrame with columns ['asset', 'quantity'] representing optimal positions
        """
        # PIT safety check
        if self.config.available_at > as_of:
            raise ValueError(
                f"Constraint config not available at {as_of} "
                f"(available_at: {self.config.available_at})"
            )
        
        # Filter returns to PIT
        returns_pit = returns[returns['as_of'] <= as_of].copy()
        
        # Get unique assets
        assets = sorted(returns_pit['asset'].unique())
        n_assets = len(assets)
        
        if n_assets == 0:
            raise ValueError("No assets available for optimization")
        
        # Calculate covariance matrix (vectorized)
        returns_pivot = returns_pit.pivot_table(
            index='as_of', columns='asset', values='return'
        )
        
        # Filter out assets with all NaN returns
        valid_assets = [a for a in assets if a in returns_pivot.columns and not returns_pivot[a].isna().all()]
        if len(valid_assets) == 0:
            raise ValueError("No assets with valid returns")
        
        assets = valid_assets
        n_assets = len(assets)
        returns_pivot = returns_pivot[assets]  # Ensure consistent ordering
        
        # Handle missing values
        if returns_pivot.isna().any().any():
            returns_pivot = returns_pivot.fillna(0)
        
        # Check if we have enough observations
        if len(returns_pivot) < 2:
            # Insufficient data for covariance, return equal weights
            result = pd.DataFrame([
                {'asset': asset, 'quantity': 0} for asset in assets
            ])
            return result
        
        cov_matrix = returns_pivot.cov().values
        mean_returns = returns_pivot.mean().values
        
        # Check for NaN in covariance matrix
        if np.isnan(cov_matrix).any() or np.isnan(mean_returns).any():
            # Return empty portfolio if data is insufficient
            result = pd.DataFrame([
                {'asset': asset, 'quantity': 0} for asset in assets
            ])
            return result
        
        # Ensure covariance matrix is positive definite
        min_eig = np.min(np.real(np.linalg.eigvals(cov_matrix)))
        if min_eig < 0:
            cov_matrix -= 10 * min_eig * np.eye(n_assets)
        
        # Get current prices for position sizing
        prices_pit = prices[prices['as_of'] <= as_of].copy()
        prices_pit = prices_pit.sort_values('as_of').groupby('asset').last().reset_index()
        prices_dict = dict(zip(prices_pit['asset'], prices_pit['price']))
        
        # Optimize based on method
        if method == 'mvo':
            weights = self._optimize_mvo(
                mean_returns, cov_matrix, n_assets, target_return
            )
        elif method == 'risk_parity':
            weights = self._optimize_risk_parity(cov_matrix, n_assets)
        else:
            raise ValueError(f"Unknown optimization method: {method}")
        
        # Convert weights to positions
        positions = []
        total_capital = current_cash
        
        for i, asset in enumerate(assets):
            if asset not in prices_dict:
                continue
            
            price = prices_dict[asset]
            target_notional = weights[i] * total_capital
            quantity = target_notional / price
            
            # Apply board lot constraint (conservative: floor for long to avoid overspending)
            if self.config.board_lot_size > 0:
                quantity = np.floor(quantity / self.config.board_lot_size) * self.config.board_lot_size
            
            # Apply long-only constraint
            if self.config.long_only and quantity < 0:
                quantity = 0
            
            if abs(quantity) > 1e-9:
                positions.append({'asset': asset, 'quantity': quantity})
        
        result = pd.DataFrame(positions) if positions else pd.DataFrame(columns=['asset', 'quantity'])
        
        # Validate constraints
        if len(result) > 0:
            is_valid, violations = self.validate_constraints(
                result, prices, industry_map, as_of, current_cash
            )
            
            if not is_valid:
                # Scale down if constraints violated
                empty_positions = pd.DataFrame(columns=['asset', 'quantity'])
                result = self.adjust_trades(
                    result, empty_positions, prices, industry_map, as_of, current_cash
                )
                
                # If still infeasible after adjustment, return deterministic zero-quantity portfolio
                if len(result) == 0 or 'asset' not in result.columns:
                    result = pd.DataFrame([
                        {'asset': asset, 'quantity': 0} for asset in assets
                    ])
        else:
            # Return deterministic zero-quantity portfolio with stable schema
            result = pd.DataFrame([
                {'asset': asset, 'quantity': 0} for asset in assets
            ])
        
        return result
    
    def _optimize_mvo(
        self,
        mean_returns: np.ndarray,
        cov_matrix: np.ndarray,
        n_assets: int,
        target_return: Optional[float]
    ) -> np.ndarray:
        """Mean-Variance Optimization."""
        # Initial guess: equal weights
        x0 = np.ones(n_assets) / n_assets
        
        # Constraints: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
        
        # Add target return constraint if specified
        if target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda x: np.dot(x, mean_returns) - target_return
            })
        
        # Bounds: long-only if configured
        if self.config.long_only:
            bounds = tuple((0, 1) for _ in range(n_assets))
        else:
            bounds = tuple((-1, 1) for _ in range(n_assets))
        
        # Objective: minimize variance (or maximize Sharpe if no target return)
        if target_return is not None:
            # Minimize variance for target return
            objective = lambda x: np.dot(x, np.dot(cov_matrix, x))
        else:
            # Maximize Sharpe ratio (minimize negative Sharpe)
            objective = lambda x: -np.dot(x, mean_returns) / np.sqrt(np.dot(x, np.dot(cov_matrix, x)) + 1e-9)
        
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000}
        )
        
        if not result.success:
            # Fallback to equal weights
            return x0
        
        return result.x
    
    def _optimize_risk_parity(
        self,
        cov_matrix: np.ndarray,
        n_assets: int
    ) -> np.ndarray:
        """Risk Parity Optimization."""
        # Initial guess: equal weights
        x0 = np.ones(n_assets) / n_assets
        
        # Constraints: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
        
        # Bounds: long-only if configured
        if self.config.long_only:
            bounds = tuple((0, 1) for _ in range(n_assets))
        else:
            bounds = tuple((-1, 1) for _ in range(n_assets))
        
        # Objective: minimize sum of squared differences in risk contributions
        def objective(x):
            portfolio_var = np.dot(x, np.dot(cov_matrix, x))
            portfolio_vol = np.sqrt(portfolio_var + 1e-9)
            
            # Marginal risk contribution
            marginal_contrib = np.dot(cov_matrix, x) / portfolio_vol
            
            # Risk contribution
            risk_contrib = x * marginal_contrib
            
            # Target: equal risk contribution
            target_contrib = portfolio_var / n_assets
            
            return np.sum((risk_contrib - target_contrib) ** 2)
        
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000}
        )
        
        if not result.success:
            # Fallback to equal weights
            return x0
        
        return result.x
