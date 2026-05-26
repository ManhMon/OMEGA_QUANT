"""Policy enforcement engine for security controls.

Implements policy engine with:
- PolicyRule for defining security policies
- PolicyEngine for rule evaluation and enforcement
- File access, network access, and execution permission policies
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
from datetime import datetime
import threading


logger = logging.getLogger(__name__)


class PolicyAction(Enum):
    """Policy action types."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK_CONNECT = "network_connect"
    NETWORK_LISTEN = "network_listen"
    EXECUTE_COMMAND = "execute_command"
    EXECUTE_CODE = "execute_code"
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"
    API_CALL = "api_call"


class PolicyDecision(Enum):
    """Policy decision."""
    ALLOW = "allow"
    DENY = "deny"


class PolicyEffect(Enum):
    """Policy effect."""
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PolicyContext:
    """Context for policy evaluation."""
    action: PolicyAction
    resource: str
    principal: str  # User, role, or service
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PolicyEvaluationResult:
    """Result of policy evaluation."""
    decision: PolicyDecision
    matched_rules: List[str]
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyRule:
    """Security policy rule."""
    name: str
    effect: PolicyEffect
    actions: List[PolicyAction]
    resources: List[str]  # Resource patterns (supports wildcards)
    principals: List[str]  # Principal patterns (supports wildcards)
    condition: Optional[Callable[[PolicyContext], bool]] = None
    enabled: bool = True
    priority: int = 0  # Higher priority rules evaluated first
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, context: PolicyContext) -> bool:
        """Check if rule matches the context.
        
        Args:
            context: Policy context
            
        Returns:
            True if rule matches
        """
        if not self.enabled:
            return False
        
        # Check action
        if context.action not in self.actions:
            return False
        
        # Check resource pattern
        if not self._matches_pattern(context.resource, self.resources):
            return False
        
        # Check principal pattern
        if not self._matches_pattern(context.principal, self.principals):
            return False
        
        # Check condition if present
        if self.condition:
            try:
                if not self.condition(context):
                    return False
            except Exception as e:
                logger.error("Error evaluating condition for rule %s: %s", self.name, e)
                return False
        
        return True
    
    def _matches_pattern(self, value: str, patterns: List[str]) -> bool:
        """Check if value matches any pattern.
        
        Args:
            value: Value to check
            patterns: List of patterns (supports * wildcard)
            
        Returns:
            True if value matches any pattern
        """
        for pattern in patterns:
            if pattern == "*":
                return True
            
            if "*" in pattern:
                # Simple wildcard matching
                if pattern.endswith("*"):
                    prefix = pattern[:-1]
                    if value.startswith(prefix):
                        return True
                elif pattern.startswith("*"):
                    suffix = pattern[1:]
                    if value.endswith(suffix):
                        return True
                else:
                    # Pattern has * in middle
                    parts = pattern.split("*")
                    if value.startswith(parts[0]) and value.endswith(parts[-1]):
                        return True
            else:
                # Exact match
                if value == pattern:
                    return True
        
        return False


class PolicyEngine:
    """Policy enforcement engine."""
    
    def __init__(self, default_decision: PolicyDecision = PolicyDecision.DENY):
        """Initialize policy engine.
        
        Args:
            default_decision: Default decision when no rules match
        """
        self.default_decision = default_decision
        
        self._rules: List[PolicyRule] = []
        self._rules_lock = threading.Lock()
        
        # Evaluation history
        self._evaluations: List[PolicyEvaluationResult] = []
        self._evaluations_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "total_evaluations": 0,
            "allowed": 0,
            "denied": 0,
            "by_action": {}
        }
        self._stats_lock = threading.Lock()
        
        logger.info("PolicyEngine initialized with default decision: %s", default_decision.value)
    
    def add_rule(self, rule: PolicyRule):
        """Add a policy rule.
        
        Args:
            rule: PolicyRule to add
        """
        with self._rules_lock:
            self._rules.append(rule)
            # Sort by priority (higher first)
            self._rules.sort(key=lambda r: r.priority, reverse=True)
        
        logger.info("Added policy rule: %s (effect=%s, priority=%d)", 
                   rule.name, rule.effect.value, rule.priority)
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a policy rule.
        
        Args:
            rule_name: Name of rule to remove
            
        Returns:
            True if rule was removed
        """
        with self._rules_lock:
            for i, rule in enumerate(self._rules):
                if rule.name == rule_name:
                    self._rules.pop(i)
                    logger.info("Removed policy rule: %s", rule_name)
                    return True
        return False
    
    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """Evaluate policy for an action.
        
        Args:
            context: Policy context
            
        Returns:
            PolicyDecision (ALLOW or DENY)
        """
        result = self._evaluate_with_details(context)
        
        # Record evaluation
        with self._evaluations_lock:
            self._evaluations.append(result)
            # Keep last 10000 evaluations
            if len(self._evaluations) > 10000:
                self._evaluations = self._evaluations[-10000:]
        
        # Update statistics
        self._update_statistics(context, result)
        
        # Log decision
        log_level = logging.DEBUG if result.decision == PolicyDecision.ALLOW else logging.WARNING
        logger.log(
            log_level,
            "Policy decision: %s for %s on %s by %s (matched: %s)",
            result.decision.value,
            context.action.value,
            context.resource,
            context.principal,
            ", ".join(result.matched_rules) if result.matched_rules else "none"
        )
        
        return result.decision
    
    def _evaluate_with_details(self, context: PolicyContext) -> PolicyEvaluationResult:
        """Evaluate policy and return detailed result."""
        with self._rules_lock:
            rules = self._rules.copy()
        
        matched_rules = []
        explicit_allow = False
        explicit_deny = False
        
        # Evaluate rules in priority order
        for rule in rules:
            if rule.matches(context):
                matched_rules.append(rule.name)
                
                if rule.effect == PolicyEffect.DENY:
                    # Explicit deny takes precedence
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.DENY,
                        matched_rules=matched_rules,
                        reason=f"Denied by rule: {rule.name}",
                        details={"rule": rule.name, "effect": rule.effect.value}
                    )
                elif rule.effect == PolicyEffect.ALLOW:
                    explicit_allow = True
        
        # If we have an explicit allow and no deny, allow
        if explicit_allow:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                matched_rules=matched_rules,
                reason=f"Allowed by rules: {', '.join(matched_rules)}",
                details={"matched_rules": matched_rules}
            )
        
        # No matching rules, use default decision
        return PolicyEvaluationResult(
            decision=self.default_decision,
            matched_rules=[],
            reason=f"No matching rules, using default: {self.default_decision.value}",
            details={"default_decision": self.default_decision.value}
        )
    
    def enable_rule(self, rule_name: str) -> bool:
        """Enable a rule.
        
        Args:
            rule_name: Rule name
            
        Returns:
            True if rule was enabled
        """
        with self._rules_lock:
            for rule in self._rules:
                if rule.name == rule_name:
                    rule.enabled = True
                    logger.info("Enabled rule: %s", rule_name)
                    return True
        return False
    
    def disable_rule(self, rule_name: str) -> bool:
        """Disable a rule.
        
        Args:
            rule_name: Rule name
            
        Returns:
            True if rule was disabled
        """
        with self._rules_lock:
            for rule in self._rules:
                if rule.name == rule_name:
                    rule.enabled = False
                    logger.info("Disabled rule: %s", rule_name)
                    return True
        return False
    
    def get_rule(self, rule_name: str) -> Optional[PolicyRule]:
        """Get a rule by name.
        
        Args:
            rule_name: Rule name
            
        Returns:
            PolicyRule or None if not found
        """
        with self._rules_lock:
            for rule in self._rules:
                if rule.name == rule_name:
                    return rule
        return None
    
    def get_rules(self) -> List[PolicyRule]:
        """Get all rules.
        
        Returns:
            List of PolicyRule instances
        """
        with self._rules_lock:
            return self._rules.copy()
    
    def _update_statistics(self, context: PolicyContext, result: PolicyEvaluationResult):
        """Update statistics."""
        with self._stats_lock:
            self._stats["total_evaluations"] += 1
            
            if result.decision == PolicyDecision.ALLOW:
                self._stats["allowed"] += 1
            else:
                self._stats["denied"] += 1
            
            action_key = context.action.value
            if action_key not in self._stats["by_action"]:
                self._stats["by_action"][action_key] = {"allowed": 0, "denied": 0}
            
            if result.decision == PolicyDecision.ALLOW:
                self._stats["by_action"][action_key]["allowed"] += 1
            else:
                self._stats["by_action"][action_key]["denied"] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get policy engine statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        with self._rules_lock:
            stats["total_rules"] = len(self._rules)
            stats["enabled_rules"] = sum(1 for r in self._rules if r.enabled)
        
        return stats
    
    def get_evaluation_history(
        self,
        action: Optional[PolicyAction] = None,
        decision: Optional[PolicyDecision] = None,
        limit: int = 100
    ) -> List[PolicyEvaluationResult]:
        """Get evaluation history.
        
        Args:
            action: Optional filter by action
            decision: Optional filter by decision
            limit: Maximum number of results
            
        Returns:
            List of PolicyEvaluationResult
        """
        with self._evaluations_lock:
            evaluations = self._evaluations.copy()
        
        # Apply filters (would need to store context in result for this)
        if decision:
            evaluations = [e for e in evaluations if e.decision == decision]
        
        return evaluations[-limit:]
    
    def clear_history(self):
        """Clear evaluation history."""
        with self._evaluations_lock:
            self._evaluations.clear()
        logger.info("Cleared evaluation history")
    
    def reset_statistics(self):
        """Reset statistics counters."""
        with self._stats_lock:
            self._stats = {
                "total_evaluations": 0,
                "allowed": 0,
                "denied": 0,
                "by_action": {}
            }
        logger.info("Reset policy engine statistics")


# Predefined policy rule factories

def create_file_access_rule(
    name: str,
    effect: PolicyEffect,
    paths: List[str],
    principals: List[str],
    read_only: bool = False
) -> PolicyRule:
    """Create a file access policy rule.
    
    Args:
        name: Rule name
        effect: Policy effect (ALLOW or DENY)
        paths: List of path patterns
        principals: List of principal patterns
        read_only: If True, only allow read access
        
    Returns:
        PolicyRule instance
    """
    actions = [PolicyAction.FILE_READ]
    if not read_only:
        actions.extend([PolicyAction.FILE_WRITE, PolicyAction.FILE_DELETE])
    
    return PolicyRule(
        name=name,
        effect=effect,
        actions=actions,
        resources=paths,
        principals=principals
    )


def create_network_access_rule(
    name: str,
    effect: PolicyEffect,
    hosts: List[str],
    principals: List[str]
) -> PolicyRule:
    """Create a network access policy rule.
    
    Args:
        name: Rule name
        effect: Policy effect (ALLOW or DENY)
        hosts: List of host patterns
        principals: List of principal patterns
        
    Returns:
        PolicyRule instance
    """
    return PolicyRule(
        name=name,
        effect=effect,
        actions=[PolicyAction.NETWORK_CONNECT, PolicyAction.NETWORK_LISTEN],
        resources=hosts,
        principals=principals
    )


def create_execution_rule(
    name: str,
    effect: PolicyEffect,
    commands: List[str],
    principals: List[str]
) -> PolicyRule:
    """Create an execution policy rule.
    
    Args:
        name: Rule name
        effect: Policy effect (ALLOW or DENY)
        commands: List of command patterns
        principals: List of principal patterns
        
    Returns:
        PolicyRule instance
    """
    return PolicyRule(
        name=name,
        effect=effect,
        actions=[PolicyAction.EXECUTE_COMMAND, PolicyAction.EXECUTE_CODE],
        resources=commands,
        principals=principals
    )


# Global policy engine instance
_global_policy_engine: Optional[PolicyEngine] = None
_engine_lock = threading.Lock()


def get_policy_engine() -> PolicyEngine:
    """Get or create global policy engine instance.
    
    Returns:
        Global PolicyEngine instance
    """
    global _global_policy_engine
    
    with _engine_lock:
        if _global_policy_engine is None:
            _global_policy_engine = PolicyEngine()
        return _global_policy_engine
