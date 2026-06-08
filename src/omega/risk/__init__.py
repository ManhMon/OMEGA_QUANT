"""Risk Management package for OMEGA_QUANT Phase 5."""

from .individual_risk_guard import IndividualRiskGuard
from .circuit_breaker import CircuitBreaker
from .contagion_validator import ContagionRiskValidator

from .risk_gate_chain import (
    GateResult,
    GateSeverity,
    GateCheckResult,
    RiskContext,
    RiskGate,
    PreTradeRiskGate,
    PostTradeRiskGate,
    StrategyRiskGate,
    RuntimeRiskGate,
    ChainResult,
    RiskGateChain,
)

__all__ = [
    "IndividualRiskGuard",
    "CircuitBreaker",
    "ContagionRiskValidator",
    # risk_gate_chain
    "GateResult",
    "GateSeverity",
    "GateCheckResult",
    "RiskContext",
    "RiskGate",
    "PreTradeRiskGate",
    "PostTradeRiskGate",
    "StrategyRiskGate",
    "RuntimeRiskGate",
    "ChainResult",
    "RiskGateChain",
]


try:
    from . import advanced_circuit_breaker
except ImportError:
    pass

try:
    from . import advanced_validators
except ImportError:
    pass

try:
    from . import capital_config
except ImportError:
    pass

try:
    from . import contagion_risk_validator
except ImportError:
    pass

try:
    from . import covariance_estimator
except ImportError:
    pass

try:
    from . import cvar
except ImportError:
    pass

try:
    from . import factor_exposure
except ImportError:
    pass

try:
    from . import liquidity_filter
except ImportError:
    pass

try:
    from . import liquidity_stress
except ImportError:
    pass

try:
    from . import models
except ImportError:
    pass

try:
    from . import risk_manager
except ImportError:
    pass

try:
    from . import risk_monitor
except ImportError:
    pass

try:
    from . import validators
except ImportError:
    pass

try:
    from . import volatility_targeter
except ImportError:
    pass
