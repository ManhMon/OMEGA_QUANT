# Gate3 Provenance Bundle Remediation

**Session:** `l2_role9_gate3_provenance_remediation_20260801`
**Role:** 9 backend-engineer (OpenCode L2)
**Gate:** `gate3_provenance_bundle_remediation_20260801`
**Status:** implementation complete; no approval requested or given.

## Root Cause And Fix

`validate_legacy_residual_provenance_retry1` required every retry1 record to exist in the immutable predecessor. Gate3 is deliberately absent from the immutable 17-record predecessor, so its recorded claim could never reach its existing pinned-record validation.

Gate3 now skips only that predecessor-membership claim. Its claim remains fail-closed against the pinned immutable Gate3 record. Gate1 and Gate2 retain the original predecessor-membership condition byte-for-byte. Gate3's reduced schema uses its canonical sidecar and pinned historical record.

## Changed Allowlisted Files

- `scripts/sod_gate_enforcer.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/legacy_residual_provenance_retry1_20260730.bundle.json` pre-existing Gate3 bundle addition retained; not rewritten in this remediation.
- `.ly_state/session/l2_role9_gate3_provenance_remediation_20260801.md`

## Regression

`test_retry1_gate3_absent_from_immutable_predecessor_uses_pinned_claim` reads `C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\legacy_residual_reconciliation_20260727.json` read-only. It asserts Gate3 absence, expects exactly `17 resolved; 1 open`, then rehashes a Gate3 recorded-claim mutation and expects validation failure.

## Verification

- `python -m py_compile scripts/sod_gate_enforcer.py`: passed.
- `git diff --check`: passed.
- `python -m pytest -q tests/test_legacy_reconciliation_contract.py`: blocked during collection. `scripts/verify_legacy_gate_manifest.py` is absent, causing `ModuleNotFoundError: No module named 'verify_legacy_gate_manifest'` at test line 14.
- Direct read-only predecessor probe: predecessor exists, SHA-256 and lock value both `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`, record count `17`; Gate3 absent. Direct full validator then stops at unavailable pre-existing Gate1 audit report in this checkout: `retry1 provenance record GP_ALT_DATA_FETCHER_OPTIMIZATION audit report path invalid`.
- No full enforcer run or pass claimed.
- `PROVENANCE_TRUST_TAG_OBJECT_OID` unchanged: `774c3330169b2f0e1619a960fabe490303f3210d`.

## Repo-Local Files Read

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/audit_reports/role21_gate3_provenance_bundle_audit_20260731.md`
- `.ly_state/session/legacy_residual_provenance_retry1_20260730.bundle.json`

## Forbidden-Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: absent; not used.
- `.openclaw\skills`: absent; not used.
- `C:\Users\GHC\.agents`: exists; not used.
- `.codex\memories`: absent; not used.
- `.agents/knowledge`: exists; excluded; not read as authority or modified.
- `scripts/sod_report_evidence.py`: exists; excluded; not read or modified.
