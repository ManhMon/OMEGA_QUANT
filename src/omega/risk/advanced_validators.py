"""
Advanced Risk Validators for V21 Institutional Grade.

Implements:
- Gross/Net Exposure Guard
- Correlation Concentration Guard
- Volatility Shock Guard
- Stress Scenario Check
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np

from .validators import BaseValidator


@dataclass(frozen=True)
class ExposureValidator(BaseValidator):
    """
    Validates gross and net exposure limits.
    
    Gross exposure = sum(abs(weights))
    Net exposure = sum(weights)
    
    For long-only: gross = net = sum(weights)
    """
    max_gross_exposure: float = 0.95  # 95% max gross
    max_net_exposure: float = 0.95    # 95% max net (long-only)
    min_net_exposure: float = 0.0     # 0% min net
    
    def validate(
        self,
        symbol_weights: Dict[str, float],
        sector_weights: Dict[str, float],
        order_sizes: Dict[str, float],
        adv_data: Dict[str, float],
        returns_data: Dict[str, List[float]],
        equity_curve: List[float]
    ) -> Tuple[bool, str]:
        """Check gross and net exposure limits."""
        if not symbol_weights:
            return True, "No weights to validate"
        
        weights = list(symbol_weights.values())
        gross_exposure = sum(abs(w) for w in weights)
        net_exposure = sum(weights)
        
        if gross_exposure > self.max_gross_exposure + 1e-9:
            return False, f"Gross exposure {gross_exposure:.2%} exceeds limit {self.max_gross_exposure:.2%}"
        
        if net_exposure > self.max_net_exposure + 1e-9:
            return False, f"Net exposure {net_exposure:.2%} exceeds limit {self.max_net_exposure:.2%}"
        
        if net_exposure < self.min_net_exposure - 1e-9:
            return False, f"Net exposure {net_exposure:.2%} below minimum {self.min_net_exposure:.2%}"
        
        return True, f"Exposure OK (gross={gross_exposure:.2%}, net={net_exposure:.2%})"


@dataclass(frozen=True)
class CorrelationConcentrationValidator(BaseValidator):
    """
    Validates correlation concentration risk.
    
    Checks if portfolio is too concentrated in highly correlated assets.
    Uses recent returns to estimate correlation matrix.
    """
    max_avg_correlation: float = 0.7  # Max average pairwise correlation
    lookback_days: int = 60           # Days of returns for correlation
    
    def validate(
        self,
        symbol_weights: Dict[str, float],
        sector_weights: Dict[str, float],
        order_sizes: Dict[str, float],
        adv_data: Dict[str, float],
        returns_data: Dict[str, List[float]],
        equity_curve: List[float]
    ) -> Tuple[bool, str]:
        """Check correlation concentration."""
        if not symbol_weights or not returns_data:
            return True, "Insufficient data for correlation check"
        
        # Filter to symbols with weights > 0
        active_symbols = [s for s, w in symbol_weights.items() if w > 1e-6]
        
        if len(active_symbols) < 2:
            return True, "Less than 2 active positions, no correlation risk"
        
        # Build returns matrix
        returns_matrix = []
        valid_symbols = []
        
        for symbol in active_symbols:
            if symbol in returns_data and len(returns_data[symbol]) >= self.lookback_days:
                returns_matrix.append(returns_data[symbol][-self.lookback_days:])
                valid_symbols.append(symbol)
        
        if len(valid_symbols) < 2:
            return True, "Insufficient return history for correlation check"
        
        # Compute correlation matrix
        returns_array = np.array(returns_matrix)
        corr_matrix = np.corrcoef(returns_array)
        
        # Compute average pairwise correlation (excluding diagonal)
        n = len(valid_symbols)
        if n < 2:
            return True, "Not enough symbols for correlation"
        
        # Sum off-diagonal elements and divide by n*(n-1)
        total_corr = np.sum(corr_matrix) - np.trace(corr_matrix)
        avg_corr = total_corr / (n * (n - 1))
        
        if avg_corr > self.max_avg_correlation:
            return False, f"Average correlation {avg_corr:.2f} exceeds limit {self.max_avg_correlation:.2f}"
        
        return True, f"Correlation OK (avg={avg_corr:.2f})"


@dataclass(frozen=True)
class VolatilityShockValidator(BaseValidator):
    """
    Validates against volatility shock events.
    
    Checks if recent realized volatility has spiked significantly
    above historical average, indicating unstable market conditions.
    """
    max_vol_spike_ratio: float = 2.5  # Max ratio of recent vol / avg vol
    recent_window: int = 5             # Days for recent vol
    historical_window: int = 60        # Days for historical avg vol
    
    def validate(
        self,
        symbol_weights: Dict[str, float],
        sector_weights: Dict[str, float],
        order_sizes: Dict[str, float],
        adv_data: Dict[str, float],
        returns_data: Dict[str, List[float]],
        equity_curve: List[float]
    ) -> Tuple[bool, str]:
        """Check for volatility shock."""
        if not returns_data:
            return True, "No returns data for volatility check"
        
        # Compute portfolio-level volatility shock
        # For simplicity, check each symbol and flag if any has vol shock
        shocked_symbols = []
        
        for symbol, returns in returns_data.items():
            if len(returns) < self.historical_window:
                continue
            
            recent_returns = returns[-self.recent_window:]
            historical_returns = returns[-self.historical_window:]
            
            if len(recent_returns) < 2 or len(historical_returns) < 2:
                continue
            
            recent_vol = np.std(recent_returns)
            historical_vol = np.std(historical_returns)
            
            if historical_vol < 1e-9:
                continue
            
            vol_ratio = recent_vol / historical_vol
            
            if vol_ratio > self.max_vol_spike_ratio:
                shocked_symbols.append((symbol, vol_ratio))
        
        if shocked_symbols:
            symbols_str = ", ".join(f"{s}({r:.1f}x)" for s, r in shocked_symbols[:3])
            return False, f"Volatility shock detected in: {symbols_str}"
        
        return True, "No volatility shock detected"


@dataclass(frozen=True)
class StressScenarioValidator(BaseValidator):
    """
    Validates portfolio under historical stress scenarios.
    
    Applies simple historical shock templates (e.g., -10% market crash)
    and checks if portfolio loss exceeds tolerance.
    """
    max_stress_loss_pct: float = 0.15  # Max 15% loss in stress scenario
    
    # Predefined stress scenarios (market shock percentages)
    SCENARIOS = {
        "market_crash": -0.10,      # -10% market drop
        "sector_rotation": -0.08,   # -8% sector-specific drop
        "liquidity_crisis": -0.12,  # -12% with correlation spike
    }
    
    def validate(
        self,
        symbol_weights: Dict[str, float],
        sector_weights: Dict[str, float],
        order_sizes: Dict[str, float],
        adv_data: Dict[str, float],
        returns_data: Dict[str, List[float]],
        equity_curve: List[float]
    ) -> Tuple[bool, str]:
        """Check portfolio under stress scenarios."""
        if not symbol_weights:
            return True, "No weights to stress test"
        
        # Simple stress test: apply uniform shock to all positions
        # In reality, would use factor models and correlation structure
        
        worst_loss = 0.0
        worst_scenario = ""
        
        for scenario_name, shock_pct in self.SCENARIOS.items():
            # Assume all positions move by shock_pct (simplified)
            # In reality: use beta, correlation, sector-specific shocks
            portfolio_loss = sum(symbol_weights.values()) * shock_pct
            
            if portfolio_loss < worst_loss:
                worst_loss = portfolio_loss
                worst_scenario = scenario_name
        
        if abs(worst_loss) > self.max_stress_loss_pct:
            return False, f"Stress scenario '{worst_scenario}' loss {worst_loss:.2%} exceeds limit {self.max_stress_loss_pct:.2%}"
        
        return True, f"Stress test OK (worst loss={worst_loss:.2%} in {worst_scenario})"
