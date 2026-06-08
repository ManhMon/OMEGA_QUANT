"""Security package for OMEGA_QUANT."""

from .vault import SecretsVault

from .sandbox import (
    SandboxViolationType,
    SandboxViolation,
    ResourceLimits,
    Sandbox,
    get_sandbox,
    configure_sandbox,
)

from .policy_enforcement import (
    PolicyAction,
    PolicyDecision,
    PolicyEffect,
    PolicyContext,
    PolicyEvaluationResult,
    PolicyRule,
    PolicyEngine,
    create_file_access_rule,
    create_network_access_rule,
    create_execution_rule,
    get_policy_engine,
)

from .access_control import (
    Permission,
    Role,
    AccessController,
    get_access_controller,
)

__all__ = [
    "SecretsVault",
    # sandbox
    "SandboxViolationType",
    "SandboxViolation",
    "ResourceLimits",
    "Sandbox",
    "get_sandbox",
    "configure_sandbox",
    # policy_enforcement
    "PolicyAction",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyContext",
    "PolicyEvaluationResult",
    "PolicyRule",
    "PolicyEngine",
    "create_file_access_rule",
    "create_network_access_rule",
    "create_execution_rule",
    "get_policy_engine",
    # access_control
    "Permission",
    "Role",
    "AccessController",
    "get_access_controller",
]

try:
    from . import core
except ImportError:
    pass
