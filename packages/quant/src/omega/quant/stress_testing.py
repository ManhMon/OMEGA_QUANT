"""
OMEGA_QUANT Phase 22.2: Scenario Analysis & Stress Testing
Institutional-grade stress testing for portfolio shock resilience.

Stress dimensions:
- Price shock (gap up/down)
- Volatility multiplier (risk expansion)
- Liquidity haircut (forced liquidation penalty)

Strict PIT Safety:
- as_of must be strictly T-1 vs timestamp
- available_at must be strictly < timestamp
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import numpy as np


@dataclass
class StressScenario:
    """Single stress scenario definition."""
    name: str
    price_shock_pct: float           # e.g. -0.07 for -7%
    vol_multiplier: float = 1.0      # e.g. 1.5 means vol expansion +50%
    liquidity_haircut_pct: float = 0.0  # e.g. 0.01 means 1% liquidation penalty


@dataclass
class StressResult:
    """Stress result per scenario."""
    scenario_name: str
    stressed_pnl: float
    stressed_loss_pct: float
    stressed_var95: float
    estimated_drawdown_pct: float
    pass_limits: bool


class ScenarioStressTester:
    """
    Stress testing engine for portfolio-level shock diagnostics.
    """

    def __init__(
        self,
        price_scale: float = 1000.0,
        max_loss_threshold_pct: float = 0.10,
    ):
        self.price_scale = price_scale
        self.max_loss_threshold_pct = max_loss_threshold_pct

    @staticmethod
    def _validate_pit(as_of: datetime, available_at: datetime, timestamp: datetime):
        if as_of is None or available_at is None or timestamp is None:
            raise ValueError("PIT violation: as_of/available_at/timestamp required")
        if as_of.date() >= timestamp.date():
            raise ValueError(
                f"PIT violation (T-1): as_of ({as_of.date()}) >= timestamp ({timestamp.date()})"
            )
        if available_at >= timestamp:
            raise ValueError(
                f"PIT violation: available_at ({available_at}) >= timestamp ({timestamp})"
            )

    def run_scenarios(
        self,
        positions: Dict[str, int],
        prices: Dict[str, float],
        volatilities: Dict[str, float],
        scenarios: List[StressScenario],
        portfolio_equity: float,
        as_of: datetime,
        available_at: datetime,
        timestamp: datetime,
    ) -> Dict[str, StressResult]:
        """
        Run all scenarios and compute stress outcomes.

        Args:
            positions: {symbol: shares}
            prices: {symbol: current_price}
            volatilities: {symbol: daily_volatility_decimal}
            scenarios: stress scenario list
            portfolio_equity: current equity in VND
            as_of: market data timestamp
            available_at: market data availability timestamp
            timestamp: current run timestamp
        """
        self._validate_pit(as_of=as_of, available_at=available_at, timestamp=timestamp)

        if portfolio_equity <= 0:
            raise ValueError("portfolio_equity must be > 0")

        symbols = [s for s in positions.keys() if s in prices and s in volatilities]
        if not symbols:
            return {}

        qty = np.array([positions[s] for s in symbols], dtype=float)
        px = np.array([prices[s] for s in symbols], dtype=float)
        vol = np.array([volatilities[s] for s in symbols], dtype=float)

        if np.any(px <= 0):
            raise ValueError("Invalid price <= 0 in prices")
        if np.any(vol < 0):
            raise ValueError("Invalid volatility < 0 in volatilities")

        notional = qty * px * self.price_scale
        gross_notional = float(np.sum(np.abs(notional)))
        if gross_notional == 0:
            return {
                sc.name: StressResult(
                    scenario_name=sc.name,
                    stressed_pnl=0.0,
                    stressed_loss_pct=0.0,
                    stressed_var95=0.0,
                    estimated_drawdown_pct=0.0,
                    pass_limits=True,
                )
                for sc in scenarios
            }

        # Volatility weighted proxy for portfolio risk
        abs_weights = np.abs(notional) / gross_notional
        portfolio_vol = float(np.sum(abs_weights * vol))

        results: Dict[str, StressResult] = {}

        for scenario in scenarios:
            if scenario.vol_multiplier <= 0:
                raise ValueError(f"Scenario {scenario.name}: vol_multiplier must be > 0")
            if scenario.liquidity_haircut_pct < 0:
                raise ValueError(f"Scenario {scenario.name}: liquidity_haircut_pct must be >= 0")

            # 1) Price shock P&L
            shocked_prices = px * (1.0 + scenario.price_shock_pct)
            directional_pnl = np.sum(qty * (shocked_prices - px) * self.price_scale)

            # 2) Volatility expansion penalty proxy
            vol_penalty = gross_notional * portfolio_vol * (scenario.vol_multiplier - 1.0)

            # 3) Liquidity haircut cost
            liquidity_penalty = gross_notional * scenario.liquidity_haircut_pct

            stressed_pnl = float(directional_pnl - vol_penalty - liquidity_penalty)
            stressed_loss_pct = float((-stressed_pnl / portfolio_equity) if stressed_pnl < 0 else 0.0)

            # 95% one-day VaR proxy
            stressed_var95 = float(
                1.65 * gross_notional * portfolio_vol * scenario.vol_multiplier
            )

            estimated_drawdown_pct = stressed_loss_pct
            pass_limits = stressed_loss_pct <= self.max_loss_threshold_pct

            results[scenario.name] = StressResult(
                scenario_name=scenario.name,
                stressed_pnl=stressed_pnl,
                stressed_loss_pct=stressed_loss_pct,
                stressed_var95=stressed_var95,
                estimated_drawdown_pct=estimated_drawdown_pct,
                pass_limits=pass_limits,
            )

        return results
