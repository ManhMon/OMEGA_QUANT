# Gate3 Provenance Regression Remediation

**Session:** `l2_role9_gate3_provenance_regression_remediation_20260801`
**Role:** 9 backend-engineer (OpenCode L2)
**Gate:** `gate3_provenance_regression_remediation_20260801`
**Status:** implementation complete; no approval requested or given.

## Scope

- Modified only `tests/test_legacy_reconciliation_contract.py` and this report.
- No production enforcer, bundle, sidecar, authority, phase-gate, or validation module changes.

## Remediation

- Removed the Gate3 regression's global `sod._sha256` monkeypatch.
- The regression reads the primary immutable predecessor and its lock directly, asserting their real SHA-256/lock values match the retry1 bundle pins.
- It builds a temporary workspace fixture for unrelated Gate1/Gate2 report dependencies. Gate1 uses exact recovered immutable blob `9c588c18506f0d9fe9a3aebc785fbbb18df6f929`, verified against the declared SHA-256. Gate2 preserves its existing current-record semantics. Gate3 authority/original reports remain byte copies of their current real artifacts.
- The sole trust stub is `_trusted_provenance_bundle`; all bundle canonical/hash checks, predecessor lock/hash checks, report hashes, report content, immutable Git blob, pinned-record, and mutation hashes execute normally.
- Proven: `legacy residual reconciliation: 17 resolved; 1 open`. A rehashed Gate3 `recorded_claim_sha256` mutation fails validation.

## Verification

- `python -m py_compile tests/test_legacy_reconciliation_contract.py`: PASS.
- `git diff --check -- tests/test_legacy_reconciliation_contract.py`: PASS.
- `python -m pytest -q tests/test_legacy_reconciliation_contract.py`: BLOCKED during collection by pre-existing missing `scripts/verify_legacy_gate_manifest.py`.
- Direct target execution with only an inert module for the unrelated missing collection import: PASS. The test's enforcer validation requirements were not stubbed except trusted-signature verification.

## Repo-Local Sources Read

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden-Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: absent; not used.
- `.openclaw\skills`: absent; not used.
- `C:\Users\GHC\.agents`: exists; not used as an authoritative source.
- `.codex\memories`: absent; not used.
