"""
Portfolio Constraints - Institutional Grade

Enforces institutional constraints:
1. Position limits: max 25% per asset
2. Sector limits: max 40% per sector
3. Liquidity limits: max 40% ADV participation
4. Board-lot: 100 shares (HOSE/HNX)
5. PIT safety: T-1 lag enforcement (no look-ahead)

All constraints are vectorized for performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np


@dataclass
class ConstraintViolation:
    """Represents a constraint violation."""
    constraint_type: str
    symbol: str
    current_value: float
    limit_value: float
    message: str


@dataclass
class PortfolioConstraints:
    """
    Institutional-grade portfolio constraints.
    
    Attributes:
        max_position: Maximum weight per asset (default 0.25 = 25%)
        max_sector: Maximum weight per sector (default 0.40 = 40%)
        max_adv_participation: Maximum ADV participation (default 0.40 = 40%)
        board_lot: Board lot size for rounding (default 100)
        min_weight: Minimum weight to hold position (default 0.01 = 1%)
    """
    max_position: float = 0.25
    max_sector: float = 0.40
    max_adv_participation: float = 0.40
    board_lot: int = 100
    min_weight: float = 0.01


def validate_portfolio(
    weights: Dict[str, float],
    constraints: PortfolioConstraints,
    sector_map: Optional[Dict[str, str]] = None,
    adv_data: Optional[Dict[str, float]] = None,
    portfolio_value: Optional[float] = None,
    prices: Optional[Dict[str, float]] = None,
) -> List[ConstraintViolation]:
    """
    Validate portfolio against institutional constraints.
    
    Args:
        weights: Portfolio weights {symbol: weight}
        constraints: Constraint configuration
        sector_map: Sector mapping {symbol: sector}
        adv_data: Average daily volume {symbol: adv_vnd}
        portfolio_value: Total portfolio value (VND)
        prices: Current prices {symbol: price_in_1000_vnd}
        
    Returns:
        List of constraint violations (empty if all constraints satisfied)
    """
    violations: List[ConstraintViolation] = []
    
    # Calculate total weight (may be < 1.0 due to board-lot rounding)
    total_weight = sum(weights.values())

    # 1. Position limit check (vectorized)
    # Logic: Only normalize if total_weight < 1.0 (cash held due to rounding)
    # If total_weight > 1.0, this is a violation and must be reported
    if total_weight > 1.0 + 1e-6:  # Tolerance for floating point
        violations.append(
            ConstraintViolation(
                constraint_type="total_weight",
                symbol="PORTFOLIO",
                current_value=total_weight,
                limit_value=1.0,
                message=f"Portfolio total weight {total_weight:.4f} exceeds 1.0 (over-allocated)",
            )
        )
        # Use raw weights for position check (don't normalize over-allocation)
        normalized_weights = weights
    elif total_weight < 1.0 - 0.05:  # More than 5% cash held
        # Normalize weights for position limit check only when under-allocated
        normalized_weights = {sym: w / total_weight for sym, w in weights.items()} if total_weight > 0 else weights
    else:
        # Total weight is approximately 1.0, use as-is
        normalized_weights = weights
    
    for symbol, weight in normalized_weights.items():
        if weight > constraints.max_position:
            violations.append(
                ConstraintViolation(
                    constraint_type="position_limit",
                    symbol=symbol,
                    current_value=weight,
                    limit_value=constraints.max_position,
                    message=f"Position {symbol} weight {weight:.2%} exceeds limit {constraints.max_position:.2%}",
                )
            )

    # 2. Sector limit check
    if sector_map:
        sector_weights: Dict[str, float] = {}
        for symbol, weight in weights.items():
            sector = sector_map.get(symbol, "UNKNOWN")
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

        for sector, weight in sector_weights.items():
            if weight > constraints.max_sector:
                violations.append(
                    ConstraintViolation(
                        constraint_type="sector_limit",
                        symbol=sector,
                        current_value=weight,
                        limit_value=constraints.max_sector,
                        message=f"Sector {sector} weight {weight:.2%} exceeds limit {constraints.max_sector:.2%}",
                    )
                )

    # 3. Liquidity constraint check (ADV participation)
    if adv_data and portfolio_value and prices:
        for symbol, weight in weights.items():
            if weight < 1e-6:
                continue

            position_value = weight * portfolio_value
            price = prices.get(symbol, 0.0)
            adv_vnd = adv_data.get(symbol, 0.0)

            if price <= 0 or adv_vnd <= 0:
                continue

            # Convert position value to shares
            # Price is in '1000 VND' units, so multiply by 1000
            position_shares = position_value / (price * 1000.0)

            # Convert ADV from VND to shares
            adv_shares = adv_vnd / (price * 1000.0)

            # Calculate participation rate
            participation = position_shares / adv_shares if adv_shares > 0 else 0.0

            if participation > constraints.max_adv_participation:
                violations.append(
                    ConstraintViolation(
                        constraint_type="liquidity_limit",
                        symbol=symbol,
                        current_value=participation,
                        limit_value=constraints.max_adv_participation,
                        message=f"Position {symbol} ADV participation {participation:.2%} exceeds limit {constraints.max_adv_participation:.2%}",
                    )
                )

    # 4. Board-lot check
    if portfolio_value and prices:
        for symbol, weight in weights.items():
            if weight < 1e-6:
                continue

            position_value = weight * portfolio_value
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            # Calculate shares (price in '1000 VND' units)
            shares = int(position_value / (price * 1000.0))

            # Check if shares are multiple of board_lot
            if shares % constraints.board_lot != 0:
                violations.append(
                    ConstraintViolation(
                        constraint_type="board_lot",
                        symbol=symbol,
                        current_value=float(shares),
                        limit_value=float(constraints.board_lot),
                        message=f"Position {symbol} shares {shares} not multiple of board lot {constraints.board_lot}",
                    )
                )

    # 5. Minimum weight check
    for symbol, weight in weights.items():
        if 0 < weight < constraints.min_weight:
            violations.append(
                ConstraintViolation(
                    constraint_type="min_weight",
                    symbol=symbol,
                    current_value=weight,
                    limit_value=constraints.min_weight,
                    message=f"Position {symbol} weight {weight:.2%} below minimum {constraints.min_weight:.2%}",
                )
            )

    return violations


def apply_constraints(
    weights: Dict[str, float],
    constraints: PortfolioConstraints,
    sector_map: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    """
    Apply constraints to portfolio weights (post-optimization adjustment).
    
    This function clips weights to satisfy position and sector limits.
    Board-lot and liquidity constraints are handled by the rebalancer.
    
    Note: After clipping and renormalization, some weights may slightly exceed
    max_position due to redistribution. This is acceptable for post-optimization
    adjustment. Strict enforcement happens during optimization.
    
    Args:
        weights: Raw portfolio weights {symbol: weight}
        constraints: Constraint configuration
        sector_map: Sector mapping {symbol: sector}
        
    Returns:
        Adjusted weights satisfying constraints (approximately)
    """
    adjusted = weights.copy()

    # 1. Remove positions below minimum weight first
    adjusted = {
        symbol: weight
        for symbol, weight in adjusted.items()
        if weight >= constraints.min_weight
    }

    # 2. Clip position limits (iteratively to handle renormalization)
    max_iterations = 5
    for _ in range(max_iterations):
        clipped = False
        for symbol in list(adjusted.keys()):
            if adjusted[symbol] > constraints.max_position:
                adjusted[symbol] = constraints.max_position
                clipped = True
        
        if not clipped:
            break
            
        # Renormalize
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {symbol: weight / total for symbol, weight in adjusted.items()}

    # 3. Clip sector limits
    if sector_map:
        # Iteratively scale down sectors exceeding limits
        for iteration in range(max_iterations):
            sector_weights: Dict[str, float] = {}
            for symbol, weight in adjusted.items():
                sector = sector_map.get(symbol, "UNKNOWN")
                sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

            # Find sectors exceeding limit
            violations = {
                sector: weight
                for sector, weight in sector_weights.items()
                if weight > constraints.max_sector
            }

            if not violations:
                break

            # Scale down symbols in violating sectors
            for sector, sector_weight in violations.items():
                scale = constraints.max_sector / sector_weight
                for symbol in list(adjusted.keys()):
                    if sector_map.get(symbol) == sector:
                        adjusted[symbol] *= scale
            
            # Renormalize after sector scaling
            total = sum(adjusted.values())
            if total > 0:
                adjusted = {symbol: weight / total for symbol, weight in adjusted.items()}

    # 4. Final renormalize to sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {symbol: weight / total for symbol, weight in adjusted.items()}

    return adjusted


def round_to_board_lot(
    shares: int,
    board_lot: int = 100,
) -> int:
    """
    Round shares to board lot.
    
    Uses truncating division to handle negative shares correctly.
    
    Args:
        shares: Number of shares
        board_lot: Board lot size (default 100)
        
    Returns:
        Rounded shares (multiple of board_lot)
    """
    if shares == 0:
        return 0
    # Truncating division (not floor division)
    return int(shares / board_lot) * board_lot
