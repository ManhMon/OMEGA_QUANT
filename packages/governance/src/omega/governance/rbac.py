"""
Role-Based Access Control - OMEGA_QUANT Phase 8.
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass
import fnmatch

@dataclass
class Role:
    name: str
    permissions: List[str]

class RBACManager:
    """Manages roles and permissions for system components."""
    
    def __init__(self):
        self.roles: Dict[str, Role] = {}
        self.user_roles: Dict[str, Set[str]] = {}
        
    def add_role(self, name: str, permissions: List[str]):
        """Add or update a role."""
        self.roles[name] = Role(name, permissions)
        
    def assign_role(self, user_id: str, role_name: str) -> bool:
        """Assign role to user."""
        if role_name not in self.roles:
            return False
            
        if user_id not in self.user_roles:
            self.user_roles[user_id] = set()
            
        self.user_roles[user_id].add(role_name)
        return True
        
    def check_access(self, user_id: str, required_permission: str) -> bool:
        """Check if user has permission."""
        if user_id not in self.user_roles:
            return False
            
        for role_name in self.user_roles[user_id]:
            role = self.roles.get(role_name)
            if not role:
                continue
                
            for perm in role.permissions:
                if fnmatch.fnmatch(required_permission, perm):
                    return True
                    
        return False
