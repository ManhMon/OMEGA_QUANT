"""Role-Based Access Control (RBAC) system.

Implements RBAC with:
- Role and Permission definitions
- AccessController for permission checking
- 25 predefined roles mapping
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import logging
import threading


logger = logging.getLogger(__name__)


class Permission(Enum):
    """System permissions."""
    # Data access
    READ_MARKET_DATA = "read_market_data"
    WRITE_MARKET_DATA = "write_market_data"
    READ_PORTFOLIO = "read_portfolio"
    WRITE_PORTFOLIO = "write_portfolio"
    READ_ORDERS = "read_orders"
    WRITE_ORDERS = "write_orders"
    
    # Execution
    SUBMIT_ORDER = "submit_order"
    CANCEL_ORDER = "cancel_order"
    MODIFY_ORDER = "modify_order"
    EXECUTE_STRATEGY = "execute_strategy"
    
    # Risk management
    VIEW_RISK = "view_risk"
    MODIFY_RISK_LIMITS = "modify_risk_limits"
    OVERRIDE_RISK = "override_risk"
    
    # Configuration
    READ_CONFIG = "read_config"
    WRITE_CONFIG = "write_config"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    
    # System
    VIEW_LOGS = "view_logs"
    VIEW_METRICS = "view_metrics"
    SYSTEM_ADMIN = "system_admin"
    
    # Model management
    TRAIN_MODEL = "train_model"
    DEPLOY_MODEL = "deploy_model"
    VIEW_MODEL = "view_model"
    
    # Audit
    VIEW_AUDIT = "view_audit"
    EXPORT_DATA = "export_data"


@dataclass
class Role:
    """Role definition with permissions."""
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    inherits_from: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class AccessController:
    """RBAC access controller."""
    
    def __init__(self):
        """Initialize access controller."""
        self._roles: Dict[str, Role] = {}
        self._roles_lock = threading.Lock()
        
        self._user_roles: Dict[str, Set[str]] = {}
        self._users_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "permission_checks": 0,
            "granted": 0,
            "denied": 0
        }
        self._stats_lock = threading.Lock()
        
        # Initialize predefined roles
        self._initialize_roles()
        
        logger.info("AccessController initialized with %d roles", len(self._roles))
    
    def _initialize_roles(self):
        """Initialize 25 predefined roles."""
        roles = [
            # Executive roles
            Role(
                name="ceo",
                description="Chief Executive Officer - Full system access",
                permissions={p for p in Permission}
            ),
            Role(
                name="cto",
                description="Chief Technology Officer - Technical administration",
                permissions={
                    Permission.SYSTEM_ADMIN, Permission.VIEW_LOGS, Permission.VIEW_METRICS,
                    Permission.READ_CONFIG, Permission.WRITE_CONFIG, Permission.MANAGE_USERS,
                    Permission.MANAGE_ROLES, Permission.VIEW_AUDIT
                }
            ),
            Role(
                name="cfo",
                description="Chief Financial Officer - Financial oversight",
                permissions={
                    Permission.READ_PORTFOLIO, Permission.VIEW_RISK, Permission.VIEW_AUDIT,
                    Permission.VIEW_METRICS, Permission.EXPORT_DATA
                }
            ),
            
            # Trading roles
            Role(
                name="head_trader",
                description="Head Trader - Full trading authority",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.WRITE_ORDERS, Permission.SUBMIT_ORDER, Permission.CANCEL_ORDER,
                    Permission.MODIFY_ORDER, Permission.EXECUTE_STRATEGY, Permission.VIEW_RISK,
                    Permission.OVERRIDE_RISK
                }
            ),
            Role(
                name="senior_trader",
                description="Senior Trader - Advanced trading permissions",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.WRITE_ORDERS, Permission.SUBMIT_ORDER, Permission.CANCEL_ORDER,
                    Permission.MODIFY_ORDER, Permission.EXECUTE_STRATEGY, Permission.VIEW_RISK
                }
            ),
            Role(
                name="trader",
                description="Trader - Standard trading permissions",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.SUBMIT_ORDER, Permission.CANCEL_ORDER, Permission.VIEW_RISK
                }
            ),
            Role(
                name="junior_trader",
                description="Junior Trader - Limited trading permissions",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.VIEW_RISK
                }
            ),
            
            # Risk management roles
            Role(
                name="risk_manager",
                description="Risk Manager - Risk oversight and control",
                permissions={
                    Permission.VIEW_RISK, Permission.MODIFY_RISK_LIMITS, Permission.OVERRIDE_RISK,
                    Permission.READ_PORTFOLIO, Permission.READ_ORDERS, Permission.VIEW_AUDIT,
                    Permission.CANCEL_ORDER
                }
            ),
            Role(
                name="risk_analyst",
                description="Risk Analyst - Risk monitoring",
                permissions={
                    Permission.VIEW_RISK, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.VIEW_METRICS
                }
            ),
            
            # Quantitative roles
            Role(
                name="quant_researcher",
                description="Quantitative Researcher - Model development",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.TRAIN_MODEL, Permission.VIEW_MODEL,
                    Permission.READ_PORTFOLIO, Permission.VIEW_METRICS
                }
            ),
            Role(
                name="quant_developer",
                description="Quantitative Developer - Strategy implementation",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.TRAIN_MODEL, Permission.DEPLOY_MODEL,
                    Permission.VIEW_MODEL, Permission.EXECUTE_STRATEGY, Permission.READ_CONFIG,
                    Permission.WRITE_CONFIG
                }
            ),
            Role(
                name="data_scientist",
                description="Data Scientist - Data analysis and modeling",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.TRAIN_MODEL, Permission.VIEW_MODEL,
                    Permission.VIEW_METRICS, Permission.EXPORT_DATA
                }
            ),
            
            # Operations roles
            Role(
                name="operations_manager",
                description="Operations Manager - Operational oversight",
                permissions={
                    Permission.READ_ORDERS, Permission.READ_PORTFOLIO, Permission.VIEW_RISK,
                    Permission.VIEW_LOGS, Permission.VIEW_METRICS, Permission.VIEW_AUDIT
                }
            ),
            Role(
                name="operations_analyst",
                description="Operations Analyst - Operations monitoring",
                permissions={
                    Permission.READ_ORDERS, Permission.READ_PORTFOLIO, Permission.VIEW_LOGS,
                    Permission.VIEW_METRICS
                }
            ),
            
            # Technology roles
            Role(
                name="system_admin",
                description="System Administrator - System management",
                permissions={
                    Permission.SYSTEM_ADMIN, Permission.READ_CONFIG, Permission.WRITE_CONFIG,
                    Permission.VIEW_LOGS, Permission.VIEW_METRICS, Permission.MANAGE_USERS
                }
            ),
            Role(
                name="devops_engineer",
                description="DevOps Engineer - Deployment and monitoring",
                permissions={
                    Permission.DEPLOY_MODEL, Permission.READ_CONFIG, Permission.WRITE_CONFIG,
                    Permission.VIEW_LOGS, Permission.VIEW_METRICS
                }
            ),
            Role(
                name="software_engineer",
                description="Software Engineer - Development access",
                permissions={
                    Permission.READ_CONFIG, Permission.VIEW_LOGS, Permission.VIEW_METRICS,
                    Permission.VIEW_MODEL
                }
            ),
            
            # Compliance and audit roles
            Role(
                name="compliance_officer",
                description="Compliance Officer - Compliance oversight",
                permissions={
                    Permission.VIEW_AUDIT, Permission.VIEW_RISK, Permission.READ_ORDERS,
                    Permission.READ_PORTFOLIO, Permission.EXPORT_DATA, Permission.VIEW_LOGS
                }
            ),
            Role(
                name="auditor",
                description="Auditor - Audit access",
                permissions={
                    Permission.VIEW_AUDIT, Permission.READ_ORDERS, Permission.READ_PORTFOLIO,
                    Permission.EXPORT_DATA, Permission.VIEW_LOGS
                }
            ),
            
            # Data roles
            Role(
                name="data_engineer",
                description="Data Engineer - Data infrastructure",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.WRITE_MARKET_DATA,
                    Permission.READ_CONFIG, Permission.WRITE_CONFIG, Permission.VIEW_LOGS
                }
            ),
            Role(
                name="data_analyst",
                description="Data Analyst - Data analysis",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.VIEW_METRICS,
                    Permission.EXPORT_DATA
                }
            ),
            
            # Support roles
            Role(
                name="support_engineer",
                description="Support Engineer - Technical support",
                permissions={
                    Permission.VIEW_LOGS, Permission.VIEW_METRICS, Permission.READ_CONFIG,
                    Permission.READ_ORDERS
                }
            ),
            
            # Read-only roles
            Role(
                name="viewer",
                description="Viewer - Read-only access",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.VIEW_RISK, Permission.VIEW_METRICS
                }
            ),
            Role(
                name="guest",
                description="Guest - Minimal access",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.VIEW_METRICS
                }
            ),
            
            # Service accounts
            Role(
                name="api_service",
                description="API Service - Automated API access",
                permissions={
                    Permission.READ_MARKET_DATA, Permission.READ_PORTFOLIO, Permission.READ_ORDERS,
                    Permission.SUBMIT_ORDER, Permission.CANCEL_ORDER
                }
            ),
            Role(
                name="monitoring_service",
                description="Monitoring Service - System monitoring",
                permissions={
                    Permission.VIEW_LOGS, Permission.VIEW_METRICS, Permission.VIEW_RISK
                }
            )
        ]
        
        for role in roles:
            self._roles[role.name] = role
    
    def has_permission(self, role: str, action: Permission) -> bool:
        """Check if a role has a specific permission.
        
        Args:
            role: Role name
            action: Permission to check
            
        Returns:
            True if role has permission
        """
        with self._stats_lock:
            self._stats["permission_checks"] += 1
        
        result = self._check_permission(role, action)
        
        with self._stats_lock:
            if result:
                self._stats["granted"] += 1
            else:
                self._stats["denied"] += 1
        
        logger.debug("Permission check: role=%s, action=%s, result=%s", 
                    role, action.value, result)
        
        return result
    
    def _check_permission(self, role_name: str, action: Permission) -> bool:
        """Internal permission check with inheritance."""
        with self._roles_lock:
            role = self._roles.get(role_name)
        
        if not role:
            logger.warning("Role not found: %s", role_name)
            return False
        
        # Check direct permissions
        if action in role.permissions:
            return True
        
        # Check inherited permissions
        for parent_role_name in role.inherits_from:
            if self._check_permission(parent_role_name, action):
                return True
        
        return False
    
    def assign_role(self, user: str, role: str) -> bool:
        """Assign a role to a user.
        
        Args:
            user: User identifier
            role: Role name
            
        Returns:
            True if role was assigned
        """
        with self._roles_lock:
            if role not in self._roles:
                logger.warning("Cannot assign unknown role: %s", role)
                return False
        
        with self._users_lock:
            if user not in self._user_roles:
                self._user_roles[user] = set()
            self._user_roles[user].add(role)
        
        logger.info("Assigned role %s to user %s", role, user)
        return True
    
    def revoke_role(self, user: str, role: str) -> bool:
        """Revoke a role from a user.
        
        Args:
            user: User identifier
            role: Role name
            
        Returns:
            True if role was revoked
        """
        with self._users_lock:
            if user in self._user_roles and role in self._user_roles[user]:
                self._user_roles[user].remove(role)
                logger.info("Revoked role %s from user %s", role, user)
                return True
        return False
    
    def get_user_roles(self, user: str) -> Set[str]:
        """Get roles assigned to a user.
        
        Args:
            user: User identifier
            
        Returns:
            Set of role names
        """
        with self._users_lock:
            return self._user_roles.get(user, set()).copy()
    
    def user_has_permission(self, user: str, action: Permission) -> bool:
        """Check if a user has a specific permission through their roles.
        
        Args:
            user: User identifier
            action: Permission to check
            
        Returns:
            True if user has permission
        """
        roles = self.get_user_roles(user)
        
        for role in roles:
            if self.has_permission(role, action):
                return True
        
        return False
    
    def add_role(self, role: Role) -> bool:
        """Add a custom role.
        
        Args:
            role: Role to add
            
        Returns:
            True if role was added
        """
        with self._roles_lock:
            if role.name in self._roles:
                logger.warning("Role already exists: %s", role.name)
                return False
            self._roles[role.name] = role
        
        logger.info("Added role: %s", role.name)
        return True
    
    def remove_role(self, role_name: str) -> bool:
        """Remove a role.
        
        Args:
            role_name: Role name
            
        Returns:
            True if role was removed
        """
        with self._roles_lock:
            if role_name in self._roles:
                del self._roles[role_name]
                logger.info("Removed role: %s", role_name)
                return True
        return False
    
    def get_role(self, role_name: str) -> Optional[Role]:
        """Get a role by name.
        
        Args:
            role_name: Role name
            
        Returns:
            Role or None if not found
        """
        with self._roles_lock:
            return self._roles.get(role_name)
    
    def list_roles(self) -> List[str]:
        """List all role names.
        
        Returns:
            List of role names
        """
        with self._roles_lock:
            return list(self._roles.keys())
    
    def get_role_permissions(self, role_name: str) -> Set[Permission]:
        """Get all permissions for a role (including inherited).
        
        Args:
            role_name: Role name
            
        Returns:
            Set of permissions
        """
        permissions = set()
        
        with self._roles_lock:
            role = self._roles.get(role_name)
        
        if not role:
            return permissions
        
        # Add direct permissions
        permissions.update(role.permissions)
        
        # Add inherited permissions
        for parent_role_name in role.inherits_from:
            permissions.update(self.get_role_permissions(parent_role_name))
        
        return permissions
    
    def get_statistics(self) -> Dict:
        """Get access controller statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        with self._roles_lock:
            stats["total_roles"] = len(self._roles)
        
        with self._users_lock:
            stats["total_users"] = len(self._user_roles)
        
        if stats["permission_checks"] > 0:
            stats["grant_rate"] = stats["granted"] / stats["permission_checks"]
        
        return stats
    
    def reset_statistics(self):
        """Reset statistics counters."""
        with self._stats_lock:
            self._stats = {
                "permission_checks": 0,
                "granted": 0,
                "denied": 0
            }
        logger.info("Reset access controller statistics")


# Global access controller instance
_global_access_controller: Optional[AccessController] = None
_controller_lock = threading.Lock()


def get_access_controller() -> AccessController:
    """Get or create global access controller instance.
    
    Returns:
        Global AccessController instance
    """
    global _global_access_controller
    
    with _controller_lock:
        if _global_access_controller is None:
            _global_access_controller = AccessController()
        return _global_access_controller
