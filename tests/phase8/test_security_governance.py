"""
Tests for Security & Governance - OMEGA_QUANT Phase 8 Migration
"""

import os
import tempfile
import time

from omega.security.vault import SecretsVault
from omega.governance.rbac import RBACManager, Role
from omega.governance.audit_trail import AuditLogger
from omega.governance.compliance import ComplianceChecker


def test_vault_encrypt_decrypt():
    vault = SecretsVault()
    
    vault.store_secret("api_key", "secret123")
    retrieved = vault.get_secret("api_key")
    
    assert retrieved == "secret123"
    assert vault.list_secrets() == ["api_key"]
    
    assert vault.delete_secret("api_key") is True
    assert vault.get_secret("api_key") is None


def test_rbac_access_control():
    rbac = RBACManager()
    
    rbac.add_role("trader", ["execute:*", "view:reports"])
    rbac.add_role("viewer", ["view:*"])
    
    rbac.assign_role("user1", "trader")
    rbac.assign_role("user2", "viewer")
    
    assert rbac.check_access("user1", "execute:order") is True
    assert rbac.check_access("user1", "view:reports") is True
    assert rbac.check_access("user2", "execute:order") is False
    assert rbac.check_access("user2", "view:reports") is True


def test_audit_trail_hash_chain():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)
        
        hash1 = logger.log_action("system", "start", "engine")
        hash2 = logger.log_action("user1", "trade", "AAPL", {"qty": 100})
        
        assert hash1 != hash2
        assert logger.verify_chain() is True


def test_compliance_pit_safety():
    checker = ComplianceChecker()
    
    import pandas as pd
    
    # Safe: features and labels uncorrelated
    features = pd.Series([1, 2, 3, 4, 5])
    labels = pd.Series([1, 5, 2, 4, 3])  # Uncorrelated
    
    result = checker.check_pit_safety(features, labels)
    assert result["passed"] is True
    
    # Unsafe: features perfectly aligned with future labels
    features_leak = pd.Series([1, 2, 3, 4, 5])
    labels_leak = pd.Series([1, 2, 3, 4, 5])  # Exact copy (leakage)
    
    result_leak = checker.check_pit_safety(features_leak, labels_leak)
    assert result_leak["passed"] is False
