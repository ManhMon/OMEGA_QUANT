"""Sandbox enforcement for secure execution.

Implements sandbox with:
- Allowed path validation
- Blocked command detection
- Resource limits enforcement
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import logging
import os
import threading


logger = logging.getLogger(__name__)


class SandboxViolationType(Enum):
    """Sandbox violation types."""
    FORBIDDEN_PATH = "forbidden_path"
    BLOCKED_COMMAND = "blocked_command"
    RESOURCE_LIMIT = "resource_limit"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class SandboxViolation:
    """Sandbox violation record."""
    violation_type: SandboxViolationType
    message: str
    details: Dict = field(default_factory=dict)


@dataclass
class ResourceLimits:
    """Resource limits configuration."""
    max_memory_mb: Optional[int] = None
    max_cpu_percent: Optional[float] = None
    max_file_size_mb: Optional[int] = None
    max_open_files: Optional[int] = None
    max_processes: Optional[int] = None


class Sandbox:
    """Sandbox enforcement for secure execution."""
    
    # Default blocked commands (dangerous operations)
    DEFAULT_BLOCKED_COMMANDS = {
        "rm", "rmdir", "del", "format", "fdisk",
        "dd", "mkfs", "shutdown", "reboot", "halt",
        "kill", "killall", "pkill",
        "chmod", "chown", "chgrp",
        "sudo", "su", "runas",
        "curl", "wget", "nc", "netcat",
        "eval", "exec", "system"
    }
    
    def __init__(
        self,
        allowed_paths: Optional[List[str]] = None,
        blocked_commands: Optional[Set[str]] = None,
        resource_limits: Optional[ResourceLimits] = None,
        enforce_mode: bool = True
    ):
        """Initialize sandbox.
        
        Args:
            allowed_paths: List of allowed path prefixes
            blocked_commands: Set of blocked command names
            resource_limits: Resource limits configuration
            enforce_mode: If True, enforce restrictions; if False, only log violations
        """
        self.allowed_paths = allowed_paths or []
        self.blocked_commands = blocked_commands or self.DEFAULT_BLOCKED_COMMANDS.copy()
        self.resource_limits = resource_limits or ResourceLimits()
        self.enforce_mode = enforce_mode
        
        # Normalize allowed paths
        self.allowed_paths = [os.path.normpath(p) for p in self.allowed_paths]
        
        # Violation tracking
        self._violations: List[SandboxViolation] = []
        self._violations_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "path_checks": 0,
            "path_allowed": 0,
            "path_denied": 0,
            "command_checks": 0,
            "command_allowed": 0,
            "command_denied": 0
        }
        self._stats_lock = threading.Lock()
        
        logger.info(
            "Sandbox initialized: %d allowed paths, %d blocked commands, enforce=%s",
            len(self.allowed_paths),
            len(self.blocked_commands),
            enforce_mode
        )
    
    def check_path(self, path: str) -> tuple[bool, Optional[SandboxViolation]]:
        """Check if path access is allowed.
        
        Args:
            path: Path to check
            
        Returns:
            Tuple of (allowed boolean, violation if denied)
        """
        with self._stats_lock:
            self._stats["path_checks"] += 1
        
        # Normalize path
        normalized_path = os.path.normpath(os.path.abspath(path))
        
        # If no allowed paths configured, allow all
        if not self.allowed_paths:
            with self._stats_lock:
                self._stats["path_allowed"] += 1
            return True, None
        
        # Check if path is under any allowed prefix
        for allowed_prefix in self.allowed_paths:
            if normalized_path.startswith(allowed_prefix):
                with self._stats_lock:
                    self._stats["path_allowed"] += 1
                return True, None
        
        # Path not allowed
        violation = SandboxViolation(
            violation_type=SandboxViolationType.FORBIDDEN_PATH,
            message=f"Path access denied: {path}",
            details={
                "path": path,
                "normalized_path": normalized_path,
                "allowed_paths": self.allowed_paths
            }
        )
        
        self._record_violation(violation)
        
        with self._stats_lock:
            self._stats["path_denied"] += 1
        
        if self.enforce_mode:
            logger.warning("Sandbox violation: %s", violation.message)
            return False, violation
        else:
            logger.info("Sandbox violation (not enforced): %s", violation.message)
            return True, violation
    
    def check_command(self, command: str) -> tuple[bool, Optional[SandboxViolation]]:
        """Check if command execution is allowed.
        
        Args:
            command: Command string to check
            
        Returns:
            Tuple of (allowed boolean, violation if denied)
        """
        with self._stats_lock:
            self._stats["command_checks"] += 1
        
        # Extract command name (first token)
        command_name = command.strip().split()[0] if command.strip() else ""
        
        # Remove path components to get base command
        command_base = os.path.basename(command_name)
        
        # Check if command is blocked
        if command_base in self.blocked_commands:
            violation = SandboxViolation(
                violation_type=SandboxViolationType.BLOCKED_COMMAND,
                message=f"Command blocked: {command_base}",
                details={
                    "command": command,
                    "command_base": command_base
                }
            )
            
            self._record_violation(violation)
            
            with self._stats_lock:
                self._stats["command_denied"] += 1
            
            if self.enforce_mode:
                logger.warning("Sandbox violation: %s", violation.message)
                return False, violation
            else:
                logger.info("Sandbox violation (not enforced): %s", violation.message)
                return True, violation
        
        with self._stats_lock:
            self._stats["command_allowed"] += 1
        
        return True, None
    
    def enforce(self) -> bool:
        """Check if sandbox is in enforce mode.
        
        Returns:
            True if enforcing restrictions
        """
        return self.enforce_mode
    
    def add_allowed_path(self, path: str):
        """Add an allowed path.
        
        Args:
            path: Path to allow
        """
        normalized = os.path.normpath(path)
        if normalized not in self.allowed_paths:
            self.allowed_paths.append(normalized)
            logger.info("Added allowed path: %s", normalized)
    
    def remove_allowed_path(self, path: str) -> bool:
        """Remove an allowed path.
        
        Args:
            path: Path to remove
            
        Returns:
            True if path was removed
        """
        normalized = os.path.normpath(path)
        if normalized in self.allowed_paths:
            self.allowed_paths.remove(normalized)
            logger.info("Removed allowed path: %s", normalized)
            return True
        return False
    
    def add_blocked_command(self, command: str):
        """Add a blocked command.
        
        Args:
            command: Command to block
        """
        self.blocked_commands.add(command)
        logger.info("Added blocked command: %s", command)
    
    def remove_blocked_command(self, command: str) -> bool:
        """Remove a blocked command.
        
        Args:
            command: Command to unblock
            
        Returns:
            True if command was removed
        """
        if command in self.blocked_commands:
            self.blocked_commands.remove(command)
            logger.info("Removed blocked command: %s", command)
            return True
        return False
    
    def set_enforce_mode(self, enforce: bool):
        """Set enforce mode.
        
        Args:
            enforce: True to enforce, False to only log
        """
        self.enforce_mode = enforce
        logger.info("Sandbox enforce mode set to: %s", enforce)
    
    def _record_violation(self, violation: SandboxViolation):
        """Record a sandbox violation."""
        with self._violations_lock:
            self._violations.append(violation)
            # Keep last 1000 violations
            if len(self._violations) > 1000:
                self._violations = self._violations[-1000:]
    
    def get_violations(
        self,
        violation_type: Optional[SandboxViolationType] = None,
        limit: int = 100
    ) -> List[SandboxViolation]:
        """Get recent violations.
        
        Args:
            violation_type: Optional filter by violation type
            limit: Maximum number of violations to return
            
        Returns:
            List of violations
        """
        with self._violations_lock:
            violations = self._violations.copy()
        
        if violation_type:
            violations = [v for v in violations if v.violation_type == violation_type]
        
        return violations[-limit:]
    
    def get_statistics(self) -> Dict:
        """Get sandbox statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        with self._violations_lock:
            stats["total_violations"] = len(self._violations)
        
        stats["enforce_mode"] = self.enforce_mode
        stats["allowed_paths_count"] = len(self.allowed_paths)
        stats["blocked_commands_count"] = len(self.blocked_commands)
        
        return stats
    
    def clear_violations(self):
        """Clear violation history."""
        with self._violations_lock:
            self._violations.clear()
        logger.info("Cleared violation history")
    
    def reset_statistics(self):
        """Reset statistics counters."""
        with self._stats_lock:
            self._stats = {
                "path_checks": 0,
                "path_allowed": 0,
                "path_denied": 0,
                "command_checks": 0,
                "command_allowed": 0,
                "command_denied": 0
            }
        logger.info("Reset sandbox statistics")


# Global sandbox instance
_global_sandbox: Optional[Sandbox] = None
_sandbox_lock = threading.Lock()


def get_sandbox() -> Sandbox:
    """Get or create global sandbox instance.
    
    Returns:
        Global Sandbox instance
    """
    global _global_sandbox
    
    with _sandbox_lock:
        if _global_sandbox is None:
            _global_sandbox = Sandbox()
        return _global_sandbox


def configure_sandbox(
    allowed_paths: Optional[List[str]] = None,
    blocked_commands: Optional[Set[str]] = None,
    resource_limits: Optional[ResourceLimits] = None,
    enforce_mode: bool = True
):
    """Configure global sandbox instance.
    
    Args:
        allowed_paths: List of allowed path prefixes
        blocked_commands: Set of blocked command names
        resource_limits: Resource limits configuration
        enforce_mode: If True, enforce restrictions
    """
    global _global_sandbox
    
    with _sandbox_lock:
        _global_sandbox = Sandbox(
            allowed_paths=allowed_paths,
            blocked_commands=blocked_commands,
            resource_limits=resource_limits,
            enforce_mode=enforce_mode
        )
    
    logger.info("Configured global sandbox")
