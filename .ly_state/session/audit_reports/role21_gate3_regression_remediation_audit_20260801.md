# Gate3 Provenance Regression Remediation Re-Audit

**Role:** 21 code-reviewer (Codex L3)
**Date:** 2026-08-01T12:29:22+07:00
**Gate:** `gate3_provenance_regression_remediation_20260801`
**L2 Session:** `l2_role9_gate3_provenance_regression_remediation_20260801`
**Writer/Auditor:** PASS (`9 backend-engineer != 21 code-reviewer`)

## Scope

- Audited `tests/test_legacy_reconciliation_contract.py` and the L2 report.
- Read-only inspection covered the existing validator, retry1 bundle, Gate3 sidecar/lock, authority/original reports, and immutable predecessor/lock.
- Excluded `.ly_state/session/phase_gates.json`, `scripts/sod_report_evidence.py`, `.agents/knowledge`, production changes, and evidence-data changes.
- This audit writes only this report. No phase-gate update.

## Findings

- No blocking finding.
- The remediation removes the global `sod._sha256` monkeypatch. Real SHA-256 execution remains active for predecessor, bundle, report, pinned-record, and mutation checks.
- The test reads the primary immutable predecessor and lock directly. Both equal the retry1 pin `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`; Gate3 is absent from its 17 records.
- Fixture substitution is limited to unrelated Gate1/Gate2 report dependencies. Gate1 uses immutable blob `9c588c18506f0d9fe9a3aebc785fbbb18df6f929` with declared hash verification. Gate2 current-record and pinned-record drift semantics remain active. Gate3 reports remain real artifact bytes.
- The sole validation bypass is `_trusted_provenance_bundle`. Canonical bundle hashing, predecessor hash/lock, report hashes/content, Git blob lookup, pinned records, and mutation hashing execute normally.
- Direct focused execution passes and returns exact `legacy residual reconciliation: 17 resolved; 1 open`. Rehashing Gate3 `recorded_claim_sha256` to an invalid claim makes validation fail.
- PIT behavior is unchanged. No full enforcer pass is claimed.

## Verification

- `python -m py_compile tests/test_legacy_reconciliation_contract.py`: PASS.
- `git diff --check -- tests/test_legacy_reconciliation_contract.py`: PASS.
- `python -m pytest -q tests/test_legacy_reconciliation_contract.py`: BLOCKED during collection by missing `scripts/verify_legacy_gate_manifest.py`, producing `ModuleNotFoundError: No module named 'verify_legacy_gate_manifest'` at test import line 14.
- Focused execution of `test_retry1_gate3_absent_from_immutable_predecessor_uses_pinned_claim` with only an inert module for that unrelated missing collection import: PASS.
- The checkout-local default retry1 test remains unable to read its absent checkout predecessor; this pre-existing fixture availability issue is outside this remediation and is not represented as a full-suite or enforcer pass.

## Repo-Local Sources

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Forbidden-Path Scan

- No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.
- `.agents/knowledge` and `scripts/sod_report_evidence.py` remained excluded.

## Verdict

[APPROVED]
