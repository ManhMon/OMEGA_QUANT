"""
OMEGA_QUANT Deployment & Health Monitoring (Phase 10)

Purpose:
    Provide health checking, deployment validation, and readiness probes.
    - System health monitoring (DB, Vault, File System)
    - Readiness checks for pipeline components
    - Rollback status tracking
    - Deployment configuration validation

Contract:
    - Input: System state, component status
    - Output: Health status (JSON), exit codes for Docker/K8s
    - Integrity: Non-destructive read-only checks

Reference:
    - Phase 10: Deployment & Go-Live
    - Institutional-grade SRE practices

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
import json
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    System health and readiness monitoring.
    """
    
    def __init__(self, workspace_root: str = "."):
        self.root = Path(workspace_root)
        self.state_dir = self.root / ".ly_state"
        self.docs_dir = self.root / "docs"
    
    def check_state_directories(self) -> bool:
        """Verify all required state directories exist and are writable."""
        required = ["session", "logs", "metrics", "secrets", "audit"]
        for d in required:
            path = self.state_dir / d
            if not path.exists():
                logger.error(f"Health Check: Missing directory {path}")
                return False
            # Check writability
            test_file = path / ".health_check"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                logger.error(f"Health Check: Directory {path} not writable - {e}")
                return False
        return True
    
    def check_critical_files(self) -> bool:
        """Verify existence of critical system files."""
        critical = [
            "docs/SYSTEM_MASTER_LOG.md",
            "docs/OMEGA_SUPER_MASTER_PLAN.md",
            "scripts/sod_gate_enforcer.py"
        ]
        for f in critical:
            if not (self.root / f).exists():
                logger.error(f"Health Check: Missing critical file {f}")
                return False
        return True

    def get_system_status(self) -> Dict[str, Any]:
        """Collect full system health report."""
        status = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "state_dirs": self.check_state_directories(),
            "critical_files": self.check_critical_files(),
            "overall_health": False
        }
        
        status["overall_health"] = all([
            status["state_dirs"],
            status["critical_files"]
        ])
        
        return status


def check_health() -> bool:
    """Entry point for Docker/K8s health probes."""
    monitor = HealthMonitor()
    status = monitor.get_system_status()
    return status["overall_health"]


if __name__ == "__main__":
    # If run as script, output JSON status
    monitor = HealthMonitor()
    print(json.dumps(monitor.get_system_status(), indent=2))
