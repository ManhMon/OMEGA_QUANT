"""
OMEGA_QUANT Phase 18: Portfolio Rebalancing Engine
Institutional-grade rebalancer with drift-based & schedule-based triggers.

Author: Backend Engineer (Role 09)
Date: 2026-05-15
Version: 1.0.0

Features:
- Drift-based rebalancing (weight deviation threshold)
- Schedule-based rebalancing (daily, weekly, monthly)
- Board-lot 100 constraint for HOSE/HNX
- Liquidity constraints (ADV participation limits)
- Transaction cost estimation
- Turnover limits with proportional scaling
- PIT safety with T-1 lag enforcement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, List, Optional
from enum import Enum
import numpy as np
import pandas as pd

logger_name = "OmegaRebalancer"

@dataclass
class RebalanceConfig:
    """Configuration for rebalancer."""
    drift_threshold: float = 0.01       # 1% total drift triggers rebalance
    schedule: str = "daily"             # "daily", "weekly", "monthly", "none"
    schedule_day: int = 4               # Friday (0=Monday, 4=Friday)
    max_turnover: float = 0.25          # Max 25% turnover per rebalance
    min_trade_value: float = 100_000.0  # Min 100K VND to execute
    board_lot: int = 100                # HOSE/HNX board lot
    max_adv_participation: float = 0.10  # Max 10% of ADV per symbol
    transaction_cost_bps: float = 15.0   # 15 bps (0.15%) round-trip


@dataclass
class RebalanceDecision:
    """Decision output from rebalancer."""
    should_rebalance: bool
    reason: str = ""
    target_changes: Dict[str, Dict] = field(default_factory=dict)
    estimated_turnover: float = 0.0
    estimated_cost: float = 0.0
    liquidity_violations: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[datetime] = None


class Rebalancer:
    """
    Institutional-grade portfolio rebalancer.
    
    Features:
    - Drift-based triggers (total weight deviation > threshold)
    - Schedule-based triggers (daily/weekly/monthly)
    - Board-lot rounding (100 shares for HOSE/HNX)
    - Liquidity constraints (ADV participation caps)
    - Transaction cost estimation
    - Turnover limit with proportional trade scaling
    - PIT safety: T-1 lag enforcement on market data
    """

    def __init__(self, config: Optional[RebalanceConfig] = None):
        self.config = config or RebalanceConfig()
        self.last_rebalance_time: Optional[datetime] = None

    def rebalance(
        self,
        target_portfolio: Dict[str, float],
        current_positions: Dict[str, Dict],
        market_data: Dict[str, Dict],
        portfolio_value: float,
        timestamp: Optional[datetime] = None,
        constraint_solver: Optional[object] = None,
        industry_map: Optional[Dict[str, str]] = None,
        prices_df: Optional[pd.DataFrame] = None,
    ) -> RebalanceDecision:
        """
        Determine if portfolio should be rebalanced and compute trades.

        Args:
            target_portfolio: Target weights {symbol: weight}
            current_positions: Current positions {symbol: {qty, price, weight}}
            market_data: Market data {symbol: {price, adv, as_of, available_at}}
            portfolio_value: Total portfolio value in VND
            timestamp: Current timestamp (required for deterministic backtesting)
            constraint_solver: Optional ConstraintSolver to validate post-trade constraints
            industry_map: Optional industry mapping {symbol: sector} for ConstraintSolver
            prices_df: Optional DataFrame with columns [asset, price, as_of] for ConstraintSolver

        Returns:
            RebalanceDecision with trades and metadata
        """
        if timestamp is None:
            raise ValueError(
                "Rebalancer.timestamp is required for deterministic backtesting. "
                "Please pass current_date from the orchestrator."
            )

        # PIT Safety: Verify strict T-1 lag on market data
        for symbol, mdata in market_data.items():
            as_of = mdata.get("as_of")
            available_at = mdata.get("available_at")
            
            # Institutional Grade: PIT metadata is MANDATORY
            if not as_of or not available_at:
                raise ValueError(
                    f"PIT metadata missing for {symbol}: as_of and available_at required."
                )

            # Must be T-1: as_of date must be strictly before current timestamp date
            if as_of.date() >= timestamp.date():
                raise ValueError(
                    f"PIT violation (T-1): {symbol} as_of={as_of.date()} >= timestamp={timestamp.date()}"
                )
            
            if available_at >= timestamp:
                raise ValueError(
                    f"PIT violation (Availability): {symbol} available_at={available_at} >= timestamp={timestamp}"
                )

        # Extract current weights
        current_weights = {}
        for sym, pos in current_positions.items():
            current_weights[sym] = pos.get("weight", 0.0)

        # Check if rebalance is needed
        should_rebal, reason = self._should_rebalance(
            current_weights, target_portfolio, timestamp
        )

        if not should_rebal:
            return RebalanceDecision(
                should_rebalance=False,
                reason=reason,
                timestamp=timestamp,
            )

        # Compute target changes
        changes: Dict[str, Dict] = {}
        total_drift = 0.0
        liquidity_violations: Dict[str, str] = {}

        all_symbols = set(current_weights.keys()) | set(target_portfolio.keys())

        for symbol in all_symbols:
            current_weight = current_weights.get(symbol, 0.0)
            target_weight = target_portfolio.get(symbol, 0.0)
            drift = target_weight - current_weight

            if abs(drift) < 1e-6:
                continue

            # Calculate target value and shares
            target_value = target_weight * portfolio_value
            current_qty = current_positions.get(symbol, {}).get("qty", 0)
            current_price = market_data.get(symbol, {}).get("price", 0.0)

            if current_price <= 0:
                continue

            # Calculate target shares
            # Price scale: 1000x (prices in '1000 VND' units)
            target_shares = int(target_value / (current_price * 1000.0))
            
            # Board-lot rounding: MUST round the DELTA to ensure trade is 100-lot compliant
            raw_delta = target_shares - current_qty
            shares_delta = self._round_to_board_lot(raw_delta)

            if shares_delta == 0:
                continue

            # Check liquidity constraint
            adv_vnd = market_data.get(symbol, {}).get("adv", 0.0)
            if adv_vnd > 0 and current_price > 0:
                adv_shares = adv_vnd / (current_price * 1000.0)
                participation = abs(shares_delta) / adv_shares
                if participation > self.config.max_adv_participation:
                    liquidity_violations[symbol] = (
                        f"Participation {participation:.2%} exceeds "
                        f"limit {self.config.max_adv_participation:.2%}"
                    )
                    # Scale down to meet liquidity constraint
                    max_shares = int(adv_shares * self.config.max_adv_participation)
                    if shares_delta > 0:
                        shares_delta = min(shares_delta, max_shares)
                    else:
                        shares_delta = max(shares_delta, -max_shares)
                    shares_delta = self._round_to_board_lot(shares_delta)

            # Calculate trade value
            trade_value = abs(shares_delta * current_price * 1000.0)

            # Skip if trade value too small
            if trade_value < self.config.min_trade_value:
                continue

            changes[symbol] = {
                "current_weight": current_weight,
                "target_weight": target_weight,
                "drift": drift,
                "current_qty": current_qty,
                "target_qty": current_qty + shares_delta,
                "shares_delta": shares_delta,
                "trade_value": trade_value,
            }

            total_drift += abs(drift)

        # Calculate turnover
        estimated_turnover = total_drift

        # Check turnover constraint - scale down proportionally
        if estimated_turnover > self.config.max_turnover and changes:
            scale = self.config.max_turnover / estimated_turnover
            for symbol in list(changes.keys()):
                old_delta = changes[symbol]["shares_delta"]
                scaled_delta = int(old_delta * scale)
                scaled_delta = self._round_to_board_lot(scaled_delta)

                if scaled_delta == 0:
                    changes[symbol]["shares_delta"] = 0
                else:
                    changes[symbol]["shares_delta"] = scaled_delta
                    changes[symbol]["target_qty"] = (
                        changes[symbol]["current_qty"] + scaled_delta
                    )
                    cprice = market_data.get(symbol, {}).get("price", 0.0)
                    changes[symbol]["trade_value"] = abs(scaled_delta * cprice * 1000.0)

            # Remove zero trades
            new_changes = {}
            for k, v in changes.items():
                if v["shares_delta"] != 0:
                    new_changes[k] = v
            changes = new_changes

            # Recalculate turnover
            if portfolio_value > 0:
                turnover_sum = 0.0
                for v in changes.values():
                    turnover_sum += v["trade_value"]
                estimated_turnover = turnover_sum / portfolio_value
            else:
                estimated_turnover = 0.0

        # Estimate transaction costs
        total_trade_value = 0.0
        for v in changes.values():
            total_trade_value += v["trade_value"]
        estimated_cost = total_trade_value * (self.config.transaction_cost_bps / 10_000.0)

        # Pre-execution Risk Constraint Check (Phase 20 ConstraintSolver Integration)
        if constraint_solver is not None and industry_map is not None and prices_df is not None:
            post_positions = []
            for symbol in all_symbols:
                qty = current_positions.get(symbol, {}).get("qty", 0)
                if symbol in changes:
                    qty = changes[symbol]["target_qty"]
                post_positions.append({"asset": symbol, "quantity": qty})
            
            post_pos_df = pd.DataFrame(post_positions)
            
            # Normalize prices_df to VND if they appear in thousand units
            solver_prices = prices_df.copy()
            for idx, row in solver_prices.iterrows():
                sym = row['asset']
                md_price = market_data.get(sym, {}).get('price')
                if md_price and row['price'] > 0:
                    # If prices_df price is close to market_data price (thousand units), scale it to VND
                    if np.isclose(row['price'], md_price, rtol=1e-2):
                        solver_prices.at[idx, 'price'] = row['price'] * 1000.0
            
            try:
                # pass portfolio_value directly as current_cash because:
                # cash_after_trades = portfolio_value - target_notional_vnd
                is_valid, solver_violations = constraint_solver.validate_constraints(
                    positions=post_pos_df,
                    prices=solver_prices,
                    industry_map=industry_map,
                    as_of=timestamp,
                    current_cash=portfolio_value
                )
                
                if not is_valid:
                    for v in solver_violations:
                        reason_key = f"RISK_{v.constraint_type}"
                        if v.asset:
                            reason_key += f"_{v.asset}"
                        liquidity_violations[reason_key] = str(v)
            except Exception as e:
                # Institutional robustness: fallback gracefully if constraint solver fails
                liquidity_violations["CONSTRAINT_SOLVER_ERROR"] = f"Failed to validate constraints: {str(e)}"

        # Update last rebalance time
        self.last_rebalance_time = timestamp

        return RebalanceDecision(
            should_rebalance=True,
            reason=reason,
            target_changes=changes,
            estimated_turnover=estimated_turnover,
            estimated_cost=estimated_cost,
            liquidity_violations=liquidity_violations,
            timestamp=timestamp,
        )

    def _should_rebalance(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        timestamp: datetime,
    ) -> tuple:
        """Determine if portfolio should be rebalanced."""
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())
        total_drift = 0.0
        for sym in all_symbols:
            total_drift += abs(target_weights.get(sym, 0.0) - current_weights.get(sym, 0.0))

        # Always rebalance on first day
        if self.last_rebalance_time is None:
            return True, f"Initial rebalance (drift={total_drift:.2%})"

        # Check drift threshold
        if total_drift > self.config.drift_threshold:
            return True, (
                f"Drift {total_drift:.2%} exceeds "
                f"threshold {self.config.drift_threshold:.2%}"
            )

        # Check schedule
        if self.config.schedule != "none" and self._check_schedule(timestamp):
            return True, f"Scheduled rebalance ({self.config.schedule})"

        return False, "No drift or schedule trigger"

    def _check_schedule(self, timestamp: datetime) -> bool:
        """Check if scheduled rebalance is due."""
        if self.last_rebalance_time is None:
            return True

        if self.config.schedule == "daily":
            return timestamp.date() > self.last_rebalance_time.date()

        elif self.config.schedule == "weekly":
            days_since = (timestamp - self.last_rebalance_time).days
            is_scheduled_day = timestamp.weekday() == self.config.schedule_day
            return is_scheduled_day and days_since >= 7

        elif self.config.schedule == "monthly":
            return (
                timestamp.year > self.last_rebalance_time.year
                or timestamp.month > self.last_rebalance_time.month
            )

        return False

    def _round_to_board_lot(self, shares: int) -> int:
        """Round shares to board lot (100 for HOSE/HNX)."""
        if shares == 0:
            return 0
        board_lot = self.config.board_lot
        result = int(shares / board_lot) * board_lot
        return result
