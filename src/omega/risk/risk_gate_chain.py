"""Risk gate chain for multi-layer risk validation.

Implements formal gate chain with multiple risk gates:
- PreTradeRiskGate: Pre-trade risk checks
- PostTradeRiskGate: Post-trade risk validation
- StrategyRiskGate: Strategy-level risk limits
- RuntimeRiskGate: Runtime risk monitoring
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import logging
from datetime import datetime
import threading


logger = logging.getLogger(__name__)


class GateResult(Enum):
    """Gate check result."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


class GateSeverity(Enum):
    """Gate failure severity."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class GateCheckResult:
    """Result from a single gate check."""
    gate_name: str
    result: GateResult
    severity: GateSeverity
    message: str
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskContext:
    """Context for risk gate evaluation."""
    action_type: str  # "order", "trade", "strategy_start", "runtime_check"
    data: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


class RiskGate:
    """Base class for risk gates."""
    
    def __init__(self, name: str, enabled: bool = True):
        """Initialize risk gate.
        
        Args:
            name: Gate name
            enabled: Whether gate is enabled
        """
        self.name = name
        self.enabled = enabled
        self._check_count = 0
        self._pass_count = 0
        self._fail_count = 0
        self._lock = threading.Lock()
    
    def check(self, context: RiskContext) -> GateCheckResult:
        """Run gate check.
        
        Args:
            context: Risk context
            
        Returns:
            GateCheckResult
        """
        if not self.enabled:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.PASS,
                severity=GateSeverity.INFO,
                message="Gate disabled"
            )
        
        with self._lock:
            self._check_count += 1
        
        result = self._execute_check(context)
        
        with self._lock:
            if result.result == GateResult.PASS:
                self._pass_count += 1
            else:
                self._fail_count += 1
        
        return result
    
    def _execute_check(self, context: RiskContext) -> GateCheckResult:
        """Execute gate-specific check logic. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _execute_check")
    
    def get_statistics(self) -> Dict:
        """Get gate statistics."""
        with self._lock:
            return {
                "name": self.name,
                "enabled": self.enabled,
                "check_count": self._check_count,
                "pass_count": self._pass_count,
                "fail_count": self._fail_count,
                "pass_rate": self._pass_count / self._check_count if self._check_count > 0 else 0.0
            }


class PreTradeRiskGate(RiskGate):
    """Pre-trade risk gate."""
    
    def __init__(
        self,
        max_order_value: float = 1000000.0,
        max_position_concentration: float = 0.2,
        enabled: bool = True
    ):
        """Initialize pre-trade risk gate.
        
        Args:
            max_order_value: Maximum order value in dollars
            max_position_concentration: Maximum position concentration (0.2 = 20%)
            enabled: Whether gate is enabled
        """
        super().__init__("PreTradeRiskGate", enabled)
        self.max_order_value = max_order_value
        self.max_position_concentration = max_position_concentration
    
    def _execute_check(self, context: RiskContext) -> GateCheckResult:
        """Execute pre-trade risk checks."""
        order_data = context.data
        
        # Check order value
        order_value = order_data.get("quantity", 0.0) * order_data.get("price", 0.0)
        if order_value > self.max_order_value:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.CRITICAL,
                message=f"Order value ${order_value:,.2f} exceeds limit ${self.max_order_value:,.2f}",
                details={"order_value": order_value, "limit": self.max_order_value}
            )
        
        # Check position concentration
        portfolio_value = context.metadata.get("portfolio_value", 0.0)
        if portfolio_value > 0:
            concentration = order_value / portfolio_value
            if concentration > self.max_position_concentration:
                return GateCheckResult(
                    gate_name=self.name,
                    result=GateResult.FAIL,
                    severity=GateSeverity.CRITICAL,
                    message=f"Position concentration {concentration:.2%} exceeds limit {self.max_position_concentration:.2%}",
                    details={"concentration": concentration, "limit": self.max_position_concentration}
                )
        
        return GateCheckResult(
            gate_name=self.name,
            result=GateResult.PASS,
            severity=GateSeverity.INFO,
            message="Pre-trade risk checks passed"
        )


class PostTradeRiskGate(RiskGate):
    """Post-trade risk gate."""
    
    def __init__(
        self,
        max_daily_loss: float = 50000.0,
        max_drawdown: float = 0.1,
        enabled: bool = True
    ):
        """Initialize post-trade risk gate.
        
        Args:
            max_daily_loss: Maximum daily loss in dollars
            max_drawdown: Maximum drawdown (0.1 = 10%)
            enabled: Whether gate is enabled
        """
        super().__init__("PostTradeRiskGate", enabled)
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
    
    def _execute_check(self, context: RiskContext) -> GateCheckResult:
        """Execute post-trade risk checks."""
        # Check daily loss
        daily_pnl = context.metadata.get("daily_pnl", 0.0)
        if daily_pnl < -self.max_daily_loss:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.CRITICAL,
                message=f"Daily loss ${abs(daily_pnl):,.2f} exceeds limit ${self.max_daily_loss:,.2f}",
                details={"daily_pnl": daily_pnl, "limit": -self.max_daily_loss}
            )
        
        # Check drawdown
        drawdown = context.metadata.get("drawdown", 0.0)
        if drawdown > self.max_drawdown:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.CRITICAL,
                message=f"Drawdown {drawdown:.2%} exceeds limit {self.max_drawdown:.2%}",
                details={"drawdown": drawdown, "limit": self.max_drawdown}
            )
        
        return GateCheckResult(
            gate_name=self.name,
            result=GateResult.PASS,
            severity=GateSeverity.INFO,
            message="Post-trade risk checks passed"
        )


class StrategyRiskGate(RiskGate):
    """Strategy-level risk gate."""
    
    def __init__(
        self,
        max_leverage: float = 2.0,
        max_var: float = 100000.0,
        enabled: bool = True
    ):
        """Initialize strategy risk gate.
        
        Args:
            max_leverage: Maximum leverage ratio
            max_var: Maximum Value at Risk in dollars
            enabled: Whether gate is enabled
        """
        super().__init__("StrategyRiskGate", enabled)
        self.max_leverage = max_leverage
        self.max_var = max_var
    
    def _execute_check(self, context: RiskContext) -> GateCheckResult:
        """Execute strategy risk checks."""
        # Check leverage
        leverage = context.metadata.get("leverage", 0.0)
        if leverage > self.max_leverage:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.CRITICAL,
                message=f"Leverage {leverage:.2f}x exceeds limit {self.max_leverage:.2f}x",
                details={"leverage": leverage, "limit": self.max_leverage}
            )
        
        # Check VaR
        var = context.metadata.get("var", 0.0)
        if var > self.max_var:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.CRITICAL,
                message=f"VaR ${var:,.2f} exceeds limit ${self.max_var:,.2f}",
                details={"var": var, "limit": self.max_var}
            )
        
        return GateCheckResult(
            gate_name=self.name,
            result=GateResult.PASS,
            severity=GateSeverity.INFO,
            message="Strategy risk checks passed"
        )


class RuntimeRiskGate(RiskGate):
    """Runtime risk monitoring gate."""
    
    def __init__(
        self,
        max_order_rate: float = 100.0,
        max_error_rate: float = 0.05,
        enabled: bool = True
    ):
        """Initialize runtime risk gate.
        
        Args:
            max_order_rate: Maximum orders per second
            max_error_rate: Maximum error rate (0.05 = 5%)
            enabled: Whether gate is enabled
        """
        super().__init__("RuntimeRiskGate", enabled)
        self.max_order_rate = max_order_rate
        self.max_error_rate = max_error_rate
    
    def _execute_check(self, context: RiskContext) -> GateCheckResult:
        """Execute runtime risk checks."""
        # Check order rate
        order_rate = context.metadata.get("order_rate", 0.0)
        if order_rate > self.max_order_rate:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.WARNING,
                message=f"Order rate {order_rate:.2f}/s exceeds limit {self.max_order_rate:.2f}/s",
                details={"order_rate": order_rate, "limit": self.max_order_rate}
            )
        
        # Check error rate
        error_rate = context.metadata.get("error_rate", 0.0)
        if error_rate > self.max_error_rate:
            return GateCheckResult(
                gate_name=self.name,
                result=GateResult.FAIL,
                severity=GateSeverity.WARNING,
                message=f"Error rate {error_rate:.2%} exceeds limit {self.max_error_rate:.2%}",
                details={"error_rate": error_rate, "limit": self.max_error_rate}
            )
        
        return GateCheckResult(
            gate_name=self.name,
            result=GateResult.PASS,
            severity=GateSeverity.INFO,
            message="Runtime risk checks passed"
        )


@dataclass
class ChainResult:
    """Result from running the gate chain."""
    passed: bool
    gate_results: List[GateCheckResult]
    failed_gates: List[str]
    critical_failures: List[str]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class RiskGateChain:
    """Chain of risk gates for comprehensive risk validation."""
    
    def __init__(self, gates: Optional[List[RiskGate]] = None):
        """Initialize risk gate chain.
        
        Args:
            gates: List of risk gates (default: all standard gates)
        """
        if gates is None:
            gates = [
                PreTradeRiskGate(),
                PostTradeRiskGate(),
                StrategyRiskGate(),
                RuntimeRiskGate()
            ]
        
        self.gates = gates
        self._lock = threading.Lock()
        self._total_checks = 0
        self._total_passes = 0
        self._total_failures = 0
        
        logger.info("RiskGateChain initialized with %d gates", len(gates))
    
    def run_all(self, context: RiskContext) -> tuple[bool, List[GateCheckResult]]:
        """Run all gates in the chain.
        
        Args:
            context: Risk context
            
        Returns:
            Tuple of (pass/fail boolean, list of gate results)
        """
        with self._lock:
            self._total_checks += 1
        
        gate_results = []
        failed_gates = []
        critical_failures = []
        
        # Run each gate
        for gate in self.gates:
            result = gate.check(context)
            gate_results.append(result)
            
            if result.result == GateResult.FAIL:
                failed_gates.append(gate.name)
                if result.severity == GateSeverity.CRITICAL:
                    critical_failures.append(gate.name)
        
        # Overall pass/fail
        passed = len(failed_gates) == 0
        
        with self._lock:
            if passed:
                self._total_passes += 1
            else:
                self._total_failures += 1
        
        # Log results
        if passed:
            logger.info("Risk gate chain passed all %d gates", len(self.gates))
        else:
            logger.warning(
                "Risk gate chain failed: %d/%d gates failed (%s)",
                len(failed_gates),
                len(self.gates),
                ", ".join(failed_gates)
            )
        
        return passed, gate_results
    
    def add_gate(self, gate: RiskGate):
        """Add a gate to the chain.
        
        Args:
            gate: RiskGate to add
        """
        self.gates.append(gate)
        logger.info("Added gate %s to chain", gate.name)
    
    def remove_gate(self, gate_name: str) -> bool:
        """Remove a gate from the chain.
        
        Args:
            gate_name: Name of gate to remove
            
        Returns:
            True if removed, False if not found
        """
        for i, gate in enumerate(self.gates):
            if gate.name == gate_name:
                self.gates.pop(i)
                logger.info("Removed gate %s from chain", gate_name)
                return True
        return False
    
    def enable_gate(self, gate_name: str) -> bool:
        """Enable a gate.
        
        Args:
            gate_name: Name of gate to enable
            
        Returns:
            True if found and enabled
        """
        for gate in self.gates:
            if gate.name == gate_name:
                gate.enabled = True
                logger.info("Enabled gate %s", gate_name)
                return True
        return False
    
    def disable_gate(self, gate_name: str) -> bool:
        """Disable a gate.
        
        Args:
            gate_name: Name of gate to disable
            
        Returns:
            True if found and disabled
        """
        for gate in self.gates:
            if gate.name == gate_name:
                gate.enabled = False
                logger.info("Disabled gate %s", gate_name)
                return True
        return False
    
    def get_gate(self, gate_name: str) -> Optional[RiskGate]:
        """Get a gate by name.
        
        Args:
            gate_name: Name of gate
            
        Returns:
            RiskGate or None if not found
        """
        for gate in self.gates:
            if gate.name == gate_name:
                return gate
        return None
    
    def get_statistics(self) -> Dict:
        """Get chain statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            chain_stats = {
                "total_checks": self._total_checks,
                "total_passes": self._total_passes,
                "total_failures": self._total_failures,
                "pass_rate": self._total_passes / self._total_checks if self._total_checks > 0 else 0.0,
                "gate_count": len(self.gates),
                "enabled_gates": sum(1 for g in self.gates if g.enabled),
                "gates": []
            }
        
        # Add per-gate statistics
        for gate in self.gates:
            chain_stats["gates"].append(gate.get_statistics())
        
        return chain_stats
    
    def reset_statistics(self):
        """Reset all statistics."""
        with self._lock:
            self._total_checks = 0
            self._total_passes = 0
            self._total_failures = 0
        
        for gate in self.gates:
            gate._check_count = 0
            gate._pass_count = 0
            gate._fail_count = 0
        
        logger.info("Reset statistics for all gates")
