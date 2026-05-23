"""
PIT-Safe Rebalancer - Institutional Grade

Enforces Point-in-Time (PIT) safety with T-1 lag:
- All decisions use T-1 data (no look-ahead bias)
- Rebalancing triggers: drift-based, schedule-based
- Board-lot rounding (100 shares)
- Liquidity constraints (40% ADV max)
- Transaction cost estimation

PIT Safety Contract:
- timestamp parameter is REQUIRED (no system clock usage)
- All market data must be from T-1 or earlier
- Rebalancer validates data timestamps
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np

from src.portfolio.constraints import (
    PortfolioConstraints,
    round_to_board_lot,
    validate_portfolio,
)


@dataclass
class RebalanceConfig:
    """Configuration for PIT-safe rebalancer."""
    drift_threshold: float = 0.01  # 1% total drift triggers rebalance
    schedule: str = "daily"  # "daily", "weekly", "monthly", "none"
    schedule_day: int = 4  # Friday (0=Monday, 4=Friday) for weekly
    max_turnover: float = 0.25  # Max 25% turnover per rebalance
    min_trade_value: float = 100_000.0  # Min 100K VND per trade
    transaction_cost_bps: float = 15.0  # 15 bps round-trip
    constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)


@dataclass
class RebalanceDecision:
    """Decision output from rebalancer."""
    should_rebalance: bool
    reason: str = ""
    target_changes: Dict[str, Dict] = field(default_factory=dict)
    estimated_turnover: float = 0.0
    estimated_cost: float = 0.0
    liquidity_violations: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    data_timestamp: Optional[datetime] = None  # T-1 data timestamp for PIT validation


class PITRebalancer:
    """
    PIT-safe portfolio rebalancer with institutional constraints.
    
    Features:
    - T-1 lag enforcement (no look-ahead)
    - Drift-based triggers
    - Schedule-based triggers
    - Board-lot rounding (100 shares)
    - Liquidity constraints (40% ADV)
    - Transaction cost estimation
    - Turnover limits with proportional scaling
    
    PIT Safety:
    - timestamp parameter is REQUIRED for all operations
    - Validates that market_data is from T-1 or earlier
    - Raises ValueError if PIT safety is violated
    """

    def __init__(self, config: Optional[RebalanceConfig] = None):
        """
        Initialize PIT-safe rebalancer.
        
        Args:
            config: Rebalance configuration (uses defaults if None)
        """
        self.config = config or RebalanceConfig()
        self.last_rebalance_time: Optional[datetime] = None

    def rebalance(
        self,
        target_portfolio: Dict[str, float],
        current_positions: Dict[str, Dict],
        market_data: Dict[str, Dict],
        portfolio_value: float,
        timestamp: datetime,
        data_timestamp: datetime,
    ) -> RebalanceDecision:
        """
        Determine if portfolio should be rebalanced and compute trades.
        
        PIT Safety: All market_data must be from T-1 or earlier.
        
        Args:
            target_portfolio: Target weights {symbol: weight}
            current_positions: Current positions {symbol: {qty, price, weight}}
            market_data: Market data {symbol: {price, adv, timestamp}}
            portfolio_value: Total portfolio value (VND)
            timestamp: Current decision timestamp (T)
            data_timestamp: Market data timestamp (REQUIRED, must be T-1 or earlier)
            
        Returns:
            RebalanceDecision with trades and metadata
            
        Raises:
            ValueError: If timestamp is None (PIT safety violation)
            ValueError: If data_timestamp is None (PIT safety violation)
            ValueError: If data_timestamp > timestamp - 1 day (look-ahead bias)
        """
        # PIT Safety: timestamp is REQUIRED
        if timestamp is None:
            raise ValueError(
                "PITRebalancer.timestamp is REQUIRED for PIT safety. "
                "Pass current_date from orchestrator."
            )

        # PIT Safety: data_timestamp is REQUIRED (no default allowed)
        if data_timestamp is None:
            raise ValueError(
                "PITRebalancer.data_timestamp is REQUIRED for PIT safety. "
                "Pass the timestamp of market_data to enforce T-1 lag. "
                "This prevents accidental use of T+0 data (look-ahead bias)."
            )

        # PIT Safety: Validate data timestamp (T-1 lag)
        # T-1 means data must be from previous day (before current day starts)
        current_day_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        if data_timestamp >= current_day_start:
            raise ValueError(
                f"PIT Safety violation: data_timestamp {data_timestamp} "
                f"is not from T-1 (must be before {current_day_start}). "
                f"Market data must be from T-1 or earlier to prevent look-ahead bias."
            )

        # Extract current weights
        current_weights = {
            sym: pos.get("weight", 0.0)
            for sym, pos in current_positions.items()
        }

        # Check if rebalance is needed
        should_rebal, reason = self._should_rebalance(
            current_weights, target_portfolio, timestamp
        )

        if not should_rebal:
            return RebalanceDecision(
                should_rebalance=False,
                reason=reason,
                timestamp=timestamp,
                data_timestamp=data_timestamp,
            )

        # Compute target changes
        changes: Dict[str, Dict] = {}
        total_drift = 0.0
        liquidity_violations: List[str] = []

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

            # Calculate target shares with board-lot rounding
            # Price is in '1000 VND' units, so multiply by 1000
            target_shares = int(target_value / (current_price * 1000.0))
            target_shares = round_to_board_lot(
                target_shares, self.config.constraints.board_lot
            )

            shares_delta = target_shares - current_qty

            if shares_delta == 0:
                continue

            # Check liquidity constraint (ADV participation)
            adv_vnd = market_data.get(symbol, {}).get("adv", 0.0)
            if adv_vnd > 0 and current_price > 0:
                # Convert ADV from VND/day to shares/day
                adv_shares = adv_vnd / (current_price * 1000.0)
                participation = abs(shares_delta) / adv_shares

                if participation > self.config.constraints.max_adv_participation:
                    liquidity_violations.append(
                        f"{symbol}: participation {participation:.2%} exceeds "
                        f"limit {self.config.constraints.max_adv_participation:.2%}"
                    )
                    # Scale down to meet liquidity constraint
                    max_shares = int(
                        adv_shares * self.config.constraints.max_adv_participation
                    )
                    if shares_delta > 0:
                        shares_delta = min(shares_delta, max_shares)
                    else:
                        shares_delta = max(shares_delta, -max_shares)
                    shares_delta = round_to_board_lot(
                        shares_delta, self.config.constraints.board_lot
                    )

            # Calculate trade value (price in '1000 VND' units)
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

        # Calculate turnover: sum of absolute weight changes (one-way)
        estimated_turnover = total_drift

        # Check turnover constraint - scale down proportionally
        if estimated_turnover > self.config.max_turnover and changes:
            scale = self.config.max_turnover / estimated_turnover
            for symbol in list(changes.keys()):
                old_delta = changes[symbol]["shares_delta"]
                scaled_delta = int(old_delta * scale)
                scaled_delta = round_to_board_lot(
                    scaled_delta, self.config.constraints.board_lot
                )

                if scaled_delta == 0:
                    changes[symbol]["shares_delta"] = 0
                else:
                    changes[symbol]["shares_delta"] = scaled_delta
                    changes[symbol]["target_qty"] = (
                        changes[symbol]["current_qty"] + scaled_delta
                    )
                    cprice = market_data.get(symbol, {}).get("price", 0.0)
                    changes[symbol]["trade_value"] = abs(
                        scaled_delta * cprice * 1000.0
                    )

            # Remove zero trades
            changes = {k: v for k, v in changes.items() if v["shares_delta"] != 0}

            # Recalculate turnover
            if portfolio_value > 0:
                estimated_turnover = (
                    sum(v["trade_value"] for v in changes.values()) / portfolio_value
                )
            else:
                estimated_turnover = 0.0

        # Estimate transaction costs
        total_trade_value = sum(v["trade_value"] for v in changes.values())
        estimated_cost = total_trade_value * (
            self.config.transaction_cost_bps / 10_000.0
        )

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
            data_timestamp=data_timestamp,
        )

    def _should_rebalance(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        timestamp: datetime,
    ) -> tuple:
        """Determine if portfolio should be rebalanced."""
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())
        total_drift = sum(
            abs(target_weights.get(sym, 0.0) - current_weights.get(sym, 0.0))
            for sym in all_symbols
        )

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
