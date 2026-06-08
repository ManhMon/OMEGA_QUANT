"""
Deployment Tests for OMEGA_QUANT
Phase 10: Deployment & Go-Live

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
"""

import pytest
from pathlib import Path
from omega.quant.deployment import HealthMonitor, check_health

@pytest.fixture
def health_monitor(tmp_path):
    """Create HealthMonitor with temp workspace."""
    # Setup required directories
    state_dir = tmp_path / ".ly_state"
    for d in ["session", "logs", "metrics", "secrets", "audit"]:
        (state_dir / d).mkdir(parents=True, exist_ok=True)
    
    # Setup critical files
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "SYSTEM_MASTER_LOG.md").touch()
    (docs_dir / "OMEGA_SUPER_MASTER_PLAN.md").touch()
    
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "sod_gate_enforcer.py").touch()
    
    return HealthMonitor(workspace_root=str(tmp_path))

def test_health_monitor_state_directories(health_monitor):
    """Test state directory validation."""
    assert health_monitor.check_state_directories() is True

def test_health_monitor_critical_files(health_monitor):
    """Test critical file validation."""
    assert health_monitor.check_critical_files() is True

def test_health_monitor_system_status(health_monitor):
    """Test full system status report."""
    status = health_monitor.get_system_status()
    
    assert "timestamp" in status
    assert status["state_dirs"] is True
    assert status["critical_files"] is True
    assert status["overall_health"] is True

def test_check_health_function(tmp_path):
    """Test health check entry point."""
    # Setup minimal environment
    state_dir = tmp_path / ".ly_state"
    for d in ["session", "logs", "metrics", "secrets", "audit"]:
        (state_dir / d).mkdir(parents=True, exist_ok=True)
    
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "SYSTEM_MASTER_LOG.md").touch()
    (docs_dir / "OMEGA_SUPER_MASTER_PLAN.md").touch()
    
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "sod_gate_enforcer.py").touch()
    
    # Change to temp directory for check
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = check_health()
        assert result is True
    finally:
        os.chdir(old_cwd)

