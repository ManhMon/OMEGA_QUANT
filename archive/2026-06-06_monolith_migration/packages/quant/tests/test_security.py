"""
Unit Tests for OMEGA_QUANT Security & Governance
Phase 8: Security & Governance

Author: DevOps Engineer (Role 11)
Date: 2026-05-13
"""

import pytest
import json
from pathlib import Path
from omega.security.core import SecretsVault, ComplianceChecker, AuditTrail, AccessLevel

@pytest.fixture
def security_setup(tmp_path):
    vault_dir = tmp_path / "secrets"
    audit_dir = tmp_path / "audit"
    
    vault = SecretsVault(vault_dir=str(vault_dir))
    compliance = ComplianceChecker()
    audit = AuditTrail(audit_dir=str(audit_dir))
    
    return vault, compliance, audit

def test_secrets_vault_store_and_retrieve(security_setup):
    """Test storing and retrieving secrets."""
    vault, _, _ = security_setup
    
    vault.store_secret("api_key", "secret123", AccessLevel.DEVELOPER)
    retrieved = vault.get_secret("api_key")
    
    assert retrieved == "secret123"
    assert "api_key" in vault.list_secrets()

def test_secrets_vault_access_control(security_setup):
    """Test access control for secrets."""
    vault, _, _ = security_setup
    
    vault.store_secret("admin_secret", "admin123", AccessLevel.ADMIN)
    vault.store_secret("dev_secret", "dev123", AccessLevel.DEVELOPER)
    
    # Admin can access both
    assert vault.get_secret("admin_secret") == "admin123"
    assert vault.get_secret("dev_secret") == "dev123"

def test_compliance_pit_safety(security_setup):
    """Test PIT safety compliance check."""
    _, compliance, _ = security_setup
    
    # Valid: available_at <= as_of_date
    valid_data = {
        "available_at": "2026-05-12",
        "as_of_date": "2026-05-13",
    }
    assert compliance.pit_safety_check(valid_data)
    
    # Invalid: available_at > as_of_date (look-ahead)
    invalid_data = {
        "available_at": "2026-05-14",
        "as_of_date": "2026-05-13",
    }
    assert not compliance.pit_safety_check(invalid_data)

def test_compliance_data_quality(security_setup):
    """Test data quality compliance check."""
    _, compliance, _ = security_setup
    
    # Valid: no nulls or NaNs
    valid_data = {"values": [1.0, 2.0, 3.0]}
    assert compliance.data_quality_check(valid_data)
    
    # Invalid: contains NaN
    invalid_data = {"values": [1.0, float('nan'), 3.0]}
    assert not compliance.data_quality_check(invalid_data)

def test_audit_trail(security_setup):
    """Test immutable audit trail."""
    _, _, audit = security_setup
    
    audit.log_event(
        event_type="SECRET_ACCESS",
        user="developer",
        action="GET",
        resource="api_key",
        result="SUCCESS",
    )
    
    events = audit.get_events(event_type="SECRET_ACCESS")
    assert len(events) == 1
    assert events[0]["user"] == "developer"
    assert events[0]["result"] == "SUCCESS"

