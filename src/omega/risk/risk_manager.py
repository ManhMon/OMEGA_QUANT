from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Tuple, Optional, List, Dict, Any
from datetime import datetime
import json
import os
import numpy as np

from ..strategy_logic.position_sizer import TargetPortfolio
from .models import ApprovedPortfolio, RiskViolation
from .validators import (
    AssetLimitValidator,
    SectorLimitValidator,
    LiquidityValidator,
    DrawdownValidator,
    VaRValidator,
    ExposureValidator,
    BaseValidator
)
from .covariance_estimator import CovarianceEstimator
from .cvar import CVaRManager
from .liquidity_stress import LiquidityStressValidator
# FIXED (v21.28.1): Unified risk modules - consolidated to single directory
from .volatility_targeter import VolatilityTargeter
from .circuit_breaker import DrawdownCircuitBreaker


from enum import Enum

class RiskLevel(Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"

@dataclass(frozen=True)
class RiskReport:
    """Detailed risk report for a portfolio."""
    level: RiskLevel
    is_safe: bool
    violations: List[str]
    suggested_trim_factor: float = 1.0  # 1.0 = keep all, 0.0 = reject all
    metrics: Dict[str, Any] = None

from .capital_config import CAPITAL_SETTING

@dataclass(frozen=True)
class RiskManagerConfig:
    """Configuration for RiskManager."""
    strict_mode: bool = True
    asset_limit_pct: float = CAPITAL_SETTING.max_notional_per_asset_pct
    sector_limit_pct: float = CAPITAL_SETTING.max_notional_per_sector_pct
    liquidity_limit_pct: float = CAPITAL_SETTING.liquidity_max_participation_pct
    drawdown_limit_pct: float = CAPITAL_SETTING.max_drawdown_limit_pct
    var_limit_pct: float = CAPITAL_SETTING.daily_var_limit_pct
    var_confidence: float = 0.95
    risk_log_path: str = "state/risk_events.jsonl"
    enable_covariance_check: bool = True
    enable_cvar_check: bool = True
    enable_liquidity_stress: bool = True
    cvar_limit_pct: float = 0.05
    cvar_concentration_limit_pct: float = 0.50
    max_exit_days: int = 3
    # Graceful degradation thresholds (relative to limits)
    amber_threshold_multiplier: float = 0.8  # Warning at 80% of limit


@runtime_checkable
class PortfolioProtocol(Protocol):
    """Protocol defining the interface for portfolio objects."""
    def get_symbol_weights(self) -> dict[str, float]: ...
    def get_sector_weights(self) -> dict[str, float]: ...
    def get_order_sizes(self) -> dict[str, float]: ...
    def get_adv_data(self) -> dict[str, float]: ...
    def get_returns_data(self) -> dict[str, list[float]]: ...
    def get_equity_curve(self) -> list[float]: ...


@dataclass
class RiskManager:
    """
    Layer 04 Risk Management Gate.

    Receives TargetPortfolio from Layer 02 and returns ApprovedPortfolio or RiskViolation.
    Implements strict mode fail-safe: if any error occurs during validation,
    defaults to rejecting the entire portfolio.
    """
    config: RiskManagerConfig
    _validators: list[BaseValidator]

    def __init__(self, config: Optional[RiskManagerConfig] = None):
        """Initialize RiskManager with optional configuration."""
        self.config = config or RiskManagerConfig()
        self._validators = self._initialize_validators()
        # Initialize institutional risk modules
        self._cov_estimator = CovarianceEstimator(method="ledoit-wolf") if self.config.enable_covariance_check else None
        self._cvar_manager = CVaRManager(confidence=self.config.var_confidence) if self.config.enable_cvar_check else None
        self._liquidity_validator = LiquidityStressValidator(max_exit_days=self.config.max_exit_days) if self.config.enable_liquidity_stress else None
        # NEW (v21.10.1): Volatility Targeting & Drawdown Circuit Breaker
        self._vol_targeter = VolatilityTargeter(target_vol=0.15, lookback_days=20)
        self._circuit_breaker = DrawdownCircuitBreaker()
        # Ensure risk log directory exists
        log_dir = os.path.dirname(self.config.risk_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def _initialize_validators(self) -> list[BaseValidator]:
        """Initialize all risk validators."""
        return [
            AssetLimitValidator(self.config.asset_limit_pct),
            SectorLimitValidator(self.config.sector_limit_pct),
            LiquidityValidator(self.config.liquidity_limit_pct),
            DrawdownValidator(self.config.drawdown_limit_pct),
            VaRValidator(self.config.var_limit_pct, self.config.var_confidence),
            ExposureValidator(max_exposure=1.0)
        ]

    def _log_risk_event(self, event_type: str, details: dict, approved: bool) -> None:
        """Log risk event to JSONL file."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "approved": approved,
            "details": details
        }
        try:
            with open(self.config.risk_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            # Fail-safe: if logging fails, continue without breaking risk management
            pass

    def _validate_portfolio_with_tiers(self, target_portfolio: TargetPortfolio, market_regime: str = None) -> RiskReport:
        """
        Validate portfolio and categorize into GREEN/AMBER/RED.
        
        Args:
            target_portfolio: Portfolio to validate
            market_regime: Market regime ('Bull', 'Bear', 'Volatile Sideways', etc.)
                          Adjusts risk parameters based on regime
        """
        violations = []
        metrics = {}
        level = RiskLevel.GREEN
        trim_factor = 1.0
        
        # Market regime adjustments
        var_multiplier = 1.0
        position_limit_multiplier = 1.0
        
        if market_regime:
            metrics['market_regime'] = market_regime
            # FIX P0: Accept both 'Bear' AND 'Volatile Sideways' for risk tightening
            if market_regime == 'Bear' or market_regime == 'Volatile Sideways':
                # Increase risk buffers in adverse regimes
                var_multiplier = 1.2  # VaR buffer +20%
                position_limit_multiplier = 0.8  # Reduce position limits by 20%
                violations.append(f"INFO: Market regime '{market_regime}' - applying conservative risk parameters")
            elif market_regime == 'Bull':
                # Normal risk parameters in bull market
                var_multiplier = 1.0
                position_limit_multiplier = 1.0
            
            metrics['var_multiplier'] = var_multiplier
            metrics['position_limit_multiplier'] = position_limit_multiplier

        try:
            symbol_weights = getattr(target_portfolio, 'get_symbol_weights', lambda: {})()
            sector_weights = getattr(target_portfolio, 'get_sector_weights', lambda: {})()
            order_sizes = getattr(target_portfolio, 'get_order_sizes', lambda: {})()
            adv_data = getattr(target_portfolio, 'get_adv_data', lambda: {})()
            returns_data_raw = getattr(target_portfolio, 'get_returns_data', lambda: {})()
            equity_curve = getattr(target_portfolio, 'get_equity_curve', lambda: [])()

            # FIX P0 (v21.25.4): PIT Leakage Protection - Apply .shift(1) at the TOP
            # Clean returns_data BEFORE passing to ANY validator or risk calculation
            returns_data = {}
            for symbol, rets in returns_data_raw.items():
                if rets and len(rets) >= 2:
                    # Exclude most recent return (equivalent to .shift(1))
                    returns_data[symbol] = rets[:-1]
                elif rets:
                    returns_data[symbol] = []  # Not enough data after shift
                else:
                    returns_data[symbol] = []

            # 1. Check Covariance Matrix (for VaR)
            cov_matrix = None
            if self._cov_estimator and returns_data:
                try:
                    symbols = sorted(returns_data.keys())
                    returns_matrix = np.array([returns_data[s] for s in symbols]).T
                    cov_matrix = self._cov_estimator.estimate(returns_matrix)
                except Exception:
                    pass

        # 2. Run standard validators with Tier Logic
            for validator in self._validators:
                # Apply regime-based adjustments to limits
                validator_kwargs = {
                    'symbol_weights': symbol_weights,
                    'sector_weights': sector_weights,
                    'order_sizes': order_sizes,
                    'adv_data': adv_data,
                    'returns_data': returns_data,
                    'equity_curve': equity_curve,
                    'covariance_matrix': cov_matrix if isinstance(validator, VaRValidator) else None
                }
                
                # FIX P0: Apply position limit multiplier for asset/sector validators
                # Create new validator instances with adjusted limits instead of modifying frozen dataclass
                if isinstance(validator, AssetLimitValidator) and position_limit_multiplier != 1.0:
                    adjusted_validator = AssetLimitValidator(
                        max_weight_pct=validator.max_weight_pct * position_limit_multiplier
                    )
                    is_valid, msg = adjusted_validator.validate(**validator_kwargs)
                elif isinstance(validator, SectorLimitValidator) and position_limit_multiplier != 1.0:
                    adjusted_validator = SectorLimitValidator(
                        max_weight_pct=validator.max_weight_pct * position_limit_multiplier
                    )
                    is_valid, msg = adjusted_validator.validate(**validator_kwargs)
                elif isinstance(validator, VaRValidator) and var_multiplier != 1.0:
                    # FIX P0: Apply VaR buffer multiplier - stricter limit (lower threshold)
                    adjusted_validator = VaRValidator(
                        max_var_pct=validator.max_var_pct / var_multiplier,
                        confidence=validator.confidence
                    )
                    is_valid, msg = adjusted_validator.validate(**validator_kwargs)
                else:
                    is_valid, msg = validator.validate(**validator_kwargs)

                if not is_valid:
                    level = RiskLevel.RED
                    violations.append(f"CRITICAL: {msg}")
                else:
                    # Check for AMBER warnings (close to limit)
                    # Note: Simplified for now, in prod we'd query each validator for its internal metric
                    pass

            # NEW (v21.10.1): Volatility Targeting - scale weights based on realized vol
            # FIX P1 & P1 (v21.25.4): Use WEIGHTED portfolio returns + robust ragged array handling
            if returns_data and symbol_weights:
                try:
                    # FIX P1: Build WEIGHTED portfolio returns (not equal-weighted mean)
                    # FIX P1: Handle ragged arrays robustly
                    min_len = min((len(r) for r in returns_data.values() if r), default=0)
                    if min_len >= 5:  # Need at least 5 for vol calc (already shifted above)
                        # Collect weighted returns for each symbol
                        weighted_returns_list = []
                        for symbol in symbol_weights:
                            weight = symbol_weights[symbol]
                            rets = returns_data.get(symbol, [])
                            if weight > 0 and rets and len(rets) >= min_len:
                                # Truncate to min_len to handle ragged arrays
                                rets_truncated = rets[-min_len:]
                                weighted_returns_list.append(np.array(rets_truncated) * weight)

                        if weighted_returns_list:
                            # Sum weighted returns across symbols (vectorized)
                            portfolio_returns = np.sum(weighted_returns_list, axis=0).tolist()

                            vol_scaling = self._vol_targeter.calculate_scaling_factor_from_returns(portfolio_returns)
                            metrics["vol_scaling_factor"] = vol_scaling
                            if vol_scaling < trim_factor:
                                trim_factor = vol_scaling
                            if vol_scaling < 0.5:
                                level = RiskLevel.AMBER if level == RiskLevel.GREEN else level
                                violations.append(f"WARNING: High volatility detected. Scaling factor: {vol_scaling:.2%}")
                except Exception:
                    pass  # Fail gracefully - don't block on vol targeting errors

            # NEW (v21.10.1): Drawdown Circuit Breaker - check equity curve
            if equity_curve and len(equity_curve) >= 2:
                try:
                    dd_status = self._circuit_breaker.check_risk_from_equity_curve(equity_curve)
                    metrics["drawdown"] = dd_status.drawdown
                    metrics["dd_breaker_active"] = dd_status.is_active
                    if dd_status.is_active:
                        # Circuit breaker overrides vol scaling if more restrictive
                        if dd_status.risk_multiplier < trim_factor:
                            trim_factor = dd_status.risk_multiplier
                        if dd_status.risk_multiplier == 0.0:
                            level = RiskLevel.RED
                            violations.append(f"EMERGENCY DRAWDOWN: {dd_status.message}")
                        elif level != RiskLevel.RED:
                            level = RiskLevel.AMBER
                            violations.append(f"DRAWDOWN WARNING: {dd_status.message}")
                except Exception:
                    pass  # Fail gracefully

            # 3. Institutional CVaR Check
            # FIX P0 (v21.25.4): returns_data already cleaned at top of function
            if self._cvar_manager and returns_data:
                try:
                    # Build weighted portfolio returns (already PIT-safe from top of function)
                    min_len = min((len(r) for r in returns_data.values() if r), default=0)
                    if min_len >= 5:
                        weighted_returns_list = []
                        for symbol, rets in returns_data.items():
                            weight = symbol_weights.get(symbol, 0.0)
                            if weight > 0 and rets and len(rets) >= min_len:
                                # Truncate to min_len for ragged array handling
                                rets_truncated = rets[-min_len:]
                                weighted_returns_list.append(np.array(rets_truncated) * weight)

                        if weighted_returns_list:
                            # Sum weighted returns across symbols
                            port_ret = np.sum(weighted_returns_list, axis=0).tolist()
                            cvar = self._cvar_manager.calculate_cvar(port_ret)
                            metrics['cvar'] = cvar
                            contributions, concentration_warning = self._cvar_manager.detect_risk_concentration(
                                returns_data,
                                symbol_weights,
                            )
                            metrics['cvar_contributions'] = contributions
                            if len(contributions) >= 2:
                                total_contribution = sum(contributions.values())
                                max_contribution = max(contributions.values()) if contributions else 0.0
                                concentration_ratio = (
                                    max_contribution / total_contribution
                                    if total_contribution > 0
                                    else 0.0
                                )
                                metrics['cvar_concentration_ratio'] = concentration_ratio
                                if concentration_ratio > self.config.cvar_concentration_limit_pct:
                                    if level != RiskLevel.RED:
                                        level = RiskLevel.AMBER
                                    violations.append(
                                        f"WARNING: {concentration_warning} Limit {self.config.cvar_concentration_limit_pct:.1%}."
                                    )
                            if cvar > self.config.cvar_limit_pct:
                                level = RiskLevel.RED
                                violations.append(f"CVaR {cvar:.2%} exceeds limit {self.config.cvar_limit_pct:.2%}")
                            elif cvar > self.config.cvar_limit_pct * self.config.amber_threshold_multiplier:
                                if level != RiskLevel.RED:
                                    level = RiskLevel.AMBER
                                    # Suggest trimming to bring CVaR back to safe zone
                                    trim_factor = min(trim_factor, (self.config.cvar_limit_pct * 0.9) / cvar)
                                    violations.append(f"WARNING: CVaR {cvar:.2%} is in warning zone. Trimming suggested.")
                except Exception as e:
                    if self.config.strict_mode:
                        level = RiskLevel.RED
                        violations.append(f"CVaR Error: {str(e)}")

        except Exception as e:
            level = RiskLevel.RED
            violations.append(f"General Risk Error: {str(e)}")

        is_safe = level != RiskLevel.RED
        if self.config.strict_mode and level == RiskLevel.AMBER:
            is_safe = False # In strict mode, AMBER is treated as RED

        return RiskReport(
            level=level,
            is_safe=is_safe,
            violations=violations,
            suggested_trim_factor=trim_factor,
            metrics=metrics
        )

    def evaluate(self, target_portfolio: TargetPortfolio, market_regime: str = None) -> ApprovedPortfolio | RiskViolation:
        """
        Main entry point with Tiered Risk support.
        
        Args:
            target_portfolio: Portfolio to evaluate
            market_regime: Optional market regime ('Bull', 'Bear', 'Volatile Sideways')
                          Adjusts risk parameters based on regime
        """
        try:
            report = self._validate_portfolio_with_tiers(target_portfolio, market_regime=market_regime)

            if report.is_safe:
                # FIX (v21.10.2): Actually apply the trim_factor to the portfolio weights
                # If AMBER or scaled by volatility, we MUST adjust the weights before approval
                final_portfolio = target_portfolio
                if report.suggested_trim_factor < 1.0:
                    scaled_weights = self._vol_targeter.scale_weights(
                        target_portfolio.weights,
                        report.suggested_trim_factor
                    )

                    # FIX (v21.10.3): Robust CASH handling - ensure CASH is never in scaled weights
                    # FIX (v21.22.1): CRITICAL - Handle CASH safely with explicit checks
                    new_cash_weight = 0.0
                    if "CASH" in scaled_weights:
                        new_cash_weight = scaled_weights.pop("CASH")
                    elif hasattr(target_portfolio, 'cash_weight'):
                        new_cash_weight = target_portfolio.cash_weight

                    # Ensure no CASH leakage into weights dict
                    scaled_weights = {k: v for k, v in scaled_weights.items() if k != "CASH"}
                    
                    # Reconstruct portfolio with scaled weights
                    from ..strategy_logic.position_sizer import TargetPortfolio
                    final_portfolio = TargetPortfolio(
                        weights=scaled_weights,
                        shares={}, # Execution engine will re-calculate shares
                        cash_weight=new_cash_weight,
                        metadata={**target_portfolio.metadata, "risk_trimmed": True, "trim_factor": report.suggested_trim_factor}
                    )
                    
                approved = ApprovedPortfolio(
                    target_portfolio=final_portfolio,
                    risk_approved=True,
                    notes=tuple(report.violations)
                )
                self._log_risk_event("portfolio_approved",
                                   {"level": report.level.value, "metrics": report.metrics},
                                   True)
                return approved
            else:
                violation = RiskViolation(
                    target_portfolio=target_portfolio,
                    violations=tuple(report.violations),
                    risk_approved=False
                )
                self._log_risk_event("portfolio_rejected",
                                   {"level": report.level.value, "violations": report.violations},
                                   False)
                return violation

        except Exception as e:
            error_msg = f"RiskManager critical failure: {str(e)}"
            violation = RiskViolation(
                target_portfolio=target_portfolio,
                violations=(error_msg,),
                risk_approved=False
            )
            return violation


# Backward compatibility alias
RiskManagementGate = RiskManager
