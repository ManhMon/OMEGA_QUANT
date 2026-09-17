# L2 Staged Diagnosis: B1 Manifest Gate4 Hash Drift

**Role**: 11 `devops-engineer` (OpenCode L2)
**Status**: `NEEDS_FIX`
**Date**: 2026-07-28
**Mode**: Read-only diagnosis; no implementation performed.

## Evidence Read

- `.agents/AGENTS.md`
- `.agents/agent/devops-engineer.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/verify_legacy_gate_manifest.py`
- `.ly_state/session/legacy_gate_migration_b1_manifest_20260728.json`
- `.ly_state/session/phase_gates.json`
- `.ly_state/session/audit_reports/role21_b1_gate4_reaudit_20260728.md`
- `tests/test_legacy_reconciliation_contract.py`
- Relevant current git diff/status.

## Reproduction

Command:

```text
python scripts/verify_legacy_gate_manifest.py
```

Observed:

```text
B1 manifest verification: FAIL: phase_gates.json hash mismatch
```

The current `phase_gates.json` SHA-256 is `556d0e74707a2b59321f736b5e7d8c8d89488f0d63ebfaa2926bdeab735aab87`.
The manifest has no populated `phase_gates_file_sha256` value visible in the B1 JSON, so the verifier compares the current file against a missing/invalid expected value and fails before Gate4 staged metadata validation.

## Root Cause

1. `verify_legacy_gate_manifest.py:85-87` requires the SHA-256 of the entire mutable `phase_gates.json` to equal `data["phase_gate_file_sha256"]`.
2. Gate4 was legitimately updated with the new L3 audit identity and report path at `phase_gates.json:93-98`.
3. The B1 manifest still stores the prior Gate4 snapshot hash (`phase_gate_snapshot_sha256=5761e767de8579f2d8410f9b2b49727f24702787df8e445f77b17fbdd3881a9c`) and does not contain the staged report hash.
4. `verify_legacy_gate_manifest.py:92-94` hashes the full current `phase[key]`, including mutable L3 metadata, against that immutable snapshot. Any valid L3 update therefore causes a second failure after the whole-file hash is corrected.
5. `validate_staged_l3_metadata()` already checks `expected_l3_report_path` and optionally checks `expected_l3_report_sha256`, but the Gate4 B1 entry only has `expected_l3_report_path`; the report hash allowlist is absent.

The failure is contract/design drift, not an invalid Gate4 audit. The audit report contains `[APPROVED]`, matches the current Gate4 L3 session/path, and records the pre-audit manifest verification as PASS, which is stale relative to the current staged manifest state.

## Missing Implementation

Implement the approved staged-L3 metadata contract in two layers:

- Add a narrow immutable-vs-mutable Gate4 comparison in `verify_legacy_gate_manifest.py`. Snapshot only the B1 immutable Gate4 fields, excluding explicitly allowed staged L3 metadata. Do not hash the full mutable Gate4 object for `phase_gate_snapshot_sha256`.
- Replace the unconditional whole-file `phase_gates.json` hash gate, or redefine it as a staged-file contract that records the exact expected current file hash after metadata staging. The former is safer for later valid L3 updates; the latter requires regenerating the manifest for every approved metadata update. The prior approved plan requires the staged allowlist, so prefer immutable structural validation plus explicit staged metadata validation.
- Populate per-entry expected report hashes, especially Gate4, then validate the report bytes before accepting `[APPROVED]`.
- Recompute `manifest_sha256` only after the schema and all expected hashes are final. Never permit runtime phase-gate metadata to rewrite the manifest automatically.

## Allowed Staged Metadata

The B1 manifest should explicitly allow only these mutable Gate4 fields:

```text
l3_session_id
l3_session_key
l3_role_id
l3_role_name
audit_report_path
final_verdict
```

Recommended staged-entry fields:

```json
{
  "expected_l3_report_path": ".ly_state/session/audit_reports/role21_b1_gate4_reaudit_20260728.md",
  "expected_l3_report_sha256": "<sha256 of exact report bytes>",
  "expected_l3_session_id": "l3_role21_b1_gate4_reaudit_20260728",
  "expected_l3_session_key": "l3_role21_b1_gate4_reaudit_20260728",
  "expected_l3_role_id": 21,
  "expected_l3_role_name": "code-reviewer",
  "expected_l3_verdict": "[APPROVED]"
}
```

The verifier must reject unknown staged metadata fields and reject changes to all other Gate4 fields, including `l2_*`, `scope`, `timestamp`, `repo_local_skill_sources`, `forbidden_path_scan`, and audit/check evidence. `l3_role_id` and `l3_role_name` need explicit validation; current code validates only session ID/key/verdict.

## Audit Hash Storage/Validation Design

- Store `expected_l3_report_sha256` in each B1 gate entry. Hash exact report bytes with the existing `sha256(Path)` helper; do not hash normalized text.
- Store an immutable Gate4 baseline snapshot separately from staged metadata, for example `immutable_phase_gate_snapshot` plus `immutable_phase_gate_snapshot_sha256`. Canonicalize with the existing `canonical()` function.
- Compare only the immutable projection against the stored snapshot hash. Validate the current phase gate by merging the immutable projection with the allowlisted staged projection, then compare each allowlisted field to its expected value.
- Keep `manifest_sha256` over the complete unsigned manifest, including allowlist values and report hashes.
- If retaining `phase_gate_file_sha256`, define it as the expected hash of the exact staged `phase_gates.json` artifact and update it atomically with the manifest. Do not use it as a stable invariant across future valid L3 metadata changes.
- Validate path safety before reading: repo-relative, no `..`, under `.ly_state/session/audit_reports/`. Fail closed on missing hash, missing report, hash mismatch, verdict mismatch, identity mismatch, or unknown metadata.

## Focused Tests Needed

Add or extend `tests/test_legacy_reconciliation_contract.py`:

1. Gate4 valid staged L3 metadata passes with an exact `expected_l3_report_sha256`.
2. Gate4 valid L3 session/path/report update passes without changing the immutable snapshot hash.
3. Report byte mutation fails with `staged L3 report hash mismatch`.
4. Missing expected report hash fails closed for a staged entry.
5. Unknown staged metadata field fails closed.
6. Changes to immutable Gate4 fields fail with snapshot/hash drift.
7. `l3_role_id` or `l3_role_name` mismatch fails closed.
8. A valid non-Gate4 B1 entry remains unchanged and still validates.
9. Whole-file phase-gate hash behavior is tested according to the selected contract: stable immutable validation, or exact staged artifact hash regeneration.
10. Run the direct verifier as an integration test and assert `B1 manifest verification: PASS`.

## Verdict

`NEEDS_FIX`: the verifier needs staged L3 allowlist enforcement, immutable Gate4 projection hashing, exact audit report hash storage/validation, and focused regression coverage. No source or test mutation made in this diagnosis.
