# Phase 8 Kickoff — Security & Governance Migration

## Purpose
Implement Secrets Management, RBAC, and Immutable Audit Trails for OMEGA_QUANT.

## Objectives
1. Simple Secrets Vault (encrypted storage for API keys).
2. Role-Based Access Control (RBAC) for system components.
3. Immutable Audit Logger (action tracking).
4. Compliance Checker (PIT safety validation).

## In-Scope Modules
- `packages/security/src/omega/security/vault.py`
- `packages/governance/src/omega/governance/rbac.py`
- `packages/governance/src/omega/governance/audit_trail.py`
- `packages/governance/src/omega/governance/compliance.py`
- `tests/phase8/test_security_governance.py`

## Constraints
- Encryption: Fernet (symmetric) for vault.
- Immutability: Append-only audit logs with checksums.

## Acceptance Tests
1. Vault encrypts/decrypts secrets correctly.
2. RBAC denies unauthorized actions.
3. Audit logs record all sensitive actions with timestamps.
4. Compliance checker flags PIT violations.
