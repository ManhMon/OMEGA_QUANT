"""OMEGA_QUANT Quant Package - Legacy Compatibility Layer
(Minimal Version for Migration)
"""

# Import with fallbacks for missing modules
__all__ = []

try:
    from omega.memory.memory_archive import AlphaMemory, ErrorMemory
    __all__.extend(["AlphaMemory", "ErrorMemory"])
except ImportError:
    pass

try:
    from omega.memory.memory_retrieval import AlphaRetriever
    __all__.append("AlphaRetriever")
except ImportError:
    pass

try:
    from omega.risk.risk_monitor import RiskMonitor
    __all__.append("RiskMonitor")
except ImportError:
    pass

try:
    from omega.observability import StructuredLogger, MetricsRegistry
    __all__.extend(["StructuredLogger", "MetricsRegistry"])
except ImportError:
    pass

try:
    from omega.security import SecretsVault
    __all__.append("SecretsVault")
except ImportError:
    pass

try:
    from omega.execution.broker_gateway import BrokerOrder
    from omega.execution.order_router import OrderRouter
    __all__.extend(["BrokerOrder", "OrderRouter"])
except ImportError:
    pass
