# Gate3 Provenance Bundle Remediation Re-Audit

**Role:** 21 code-reviewer (Codex L3)
**Date:** 2026-08-01
**Gate:** `gate3_provenance_bundle_remediation_20260801`
**L2 Session:** `l2_role9_gate3_provenance_remediation_20260801`
**Writer/Auditor:** PASS (`9 backend-engineer != 21 code-reviewer`)

## Scope

- Reviewed remediation diff only: `scripts/sod_gate_enforcer.py`, `tests/test_legacy_reconciliation_contract.py`, L2 report.
- Read-only inputs: Gate3 sidecar, lock, retry1 bundle, pinned authority/original reports, immutable predecessor.
- Excluded: `.ly_state/session/phase_gates.json`, `scripts/sod_report_evidence.py`, `.agents/knowledge`.
- No production, test, bundle, sidecar, lock, phase-gate, PIT, or knowledge files modified by this audit.

## Findings

1. **BLOCKING - regression does not prove the valid real-predecessor path.** `tests/test_legacy_reconciliation_contract.py:671` points at the real immutable predecessor, but the checkout lacks the Gate1 authority report required by the same bundle. Direct execution with only `_trusted_provenance_bundle` bypassed returns `retry1 provenance record GP_ALT_DATA_FETCHER_OPTIMIZATION audit report path invalid`, not `17 resolved; 1 open`. Collection is additionally blocked by the pre-existing missing `scripts/verify_legacy_gate_manifest.py`. Therefore the new assertion was never demonstrated runnable and would fail after collection is repaired unless all referenced real evidence is supplied or the test narrowly fixtures unrelated Gate1/2 evidence.
2. **BLOCKING - broad hash replacement can mask predecessor/bundle defects.** `tests/test_legacy_reconciliation_contract.py:679` replaces `sod._sha256` globally and special-cases the predecessor bytes. The real predecessor SHA-256 already equals the pinned bundle value `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`; this replacement is unnecessary and weakens the claimed real hash/lock verification. Keep only the explicit trusted-signature bypass, leaving canonical bundle, predecessor raw hash, predecessor lock, pinned record, sidecar, and mutation hashes on the real implementation.

## Confirmed

- Gate3 is absent from the immutable 17-record predecessor.
- Production change exempts only Gate3 from predecessor-membership lookup; Gate1/Gate2 membership logic remains unchanged.
- Gate3 still binds `recorded_claim_sha256` to `_immutable_gate_record(_pinned_gate_record("12d9e88de0d8510720595757e95b146c6593307d", key))`.
- Gate3 sidecar validates successfully against the pinned commit, original L2/audit blobs, authority report hash/session tuple, and current immutable record.
- Sidecar/authority tuple and `PROVENANCE_TRUST_TAG_OBJECT_OID` remain pinned.
- No full enforcer pass claimed. PIT behavior untouched.

## Checks

- `python -m py_compile scripts/sod_gate_enforcer.py`: PASS.
- `git diff --check`: PASS.
- Focused pytest collection: BLOCKED by missing `verify_legacy_gate_manifest`.
- Direct Gate3 sidecar validation: PASS.
- Direct retry1 validation using the real predecessor plus signature-trust bypass only: FAILS on missing Gate1 authority report before reaching the target result.
- Real predecessor raw SHA-256 and lock: both match the bundle pin.

## Required Remediation

1. Remove the `_sha256` monkeypatch from the Gate3 regression.
2. Make the focused test runnable with real predecessor hash/lock checks and narrowly controlled unrelated Gate1/2 report dependencies.
3. Demonstrate both exact success `17 resolved; 1 open` and rehashed Gate3 recorded-claim mutation failure.

## Repo-Local Sources

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Forbidden-Path Scan

- No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.
- `.agents/knowledge` and `scripts/sod_report_evidence.py` excluded from audit authority and inspection.

## Verdict

[NEEDS_FIX]
