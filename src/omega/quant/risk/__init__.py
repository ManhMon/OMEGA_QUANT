"""
Risk Management Init File
"""

from omega.quant.risk.risk_monitor import RiskMonitor, RiskMetrics, RiskLimit
from omega.quant.risk.advanced_circuit_breaker import AdvancedCircuitBreaker, AdvancedCircuitBreakerConfig, RiskBreachStatus
from omega.quant.risk.contagion_risk_validator import ContagionRiskValidator, ContagionRiskConfig, GlobalIndexData, ContagionReport
from omega.quant.risk.individual_risk_guard import IndividualRiskGuard, IndividualRiskGuardConfig, IndividualRiskGuardResult

__all__ = [
    "RiskMonitor",
    "RiskMetrics",
    "RiskLimit",
    "AdvancedCircuitBreaker",
    "AdvancedCircuitBreakerConfig",
    "RiskBreachStatus",
    "ContagionRiskValidator",
    "ContagionRiskConfig",
    "GlobalIndexData",
    "ContagionReport",
    "IndividualRiskGuard",
    "IndividualRiskGuardConfig",
    "IndividualRiskGuardResult"
]

# Auto-wired submodules and subpackages
try:
    from . import advanced_circuit_breaker
except ImportError:
    pass

try:
    from . import contagion_risk_validator
except ImportError:
    pass

try:
    from . import individual_risk_guard
except ImportError:
    pass

try:
    from . import production_monitor
except ImportError:
    pass

try:
    from . import risk_monitor
except ImportError:
    pass

try:
    from . import risk_monitor_l07
except ImportError:
    pass
