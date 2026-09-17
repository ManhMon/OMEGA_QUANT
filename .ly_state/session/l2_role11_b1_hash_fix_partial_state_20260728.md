# B1 Hash-Fix Partial Recovery State

## Identity

- Session: `l2_role11_b1_hash_fix_partial_state_20260728`
- Role: `11 devops-engineer` (OpenCode L2)
- Date: `2026-07-28`
- Status: `NEEDS_FIX`
- Mode: read-only recovery assessment
- Scope requested: `scripts/sod_gate_enforcer.py`, `scripts/verify_legacy_gate_manifest.py`, `tests/test_legacy_reconciliation_contract.py`, legacy sidecars, `git diff/status`
- Mutation performed: this report only

## Repo-Local Sources

- `.agents/AGENTS.md`
- `.agents/agent/devops-engineer.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `scripts/verify_legacy_gate_manifest.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/l2_role11_b1_gate4_hash_drift_diagnosis_20260728.md`
- `.ly_state/session/l2_role11_b1_gate4_hash_fix_recovery_diagnosis_20260728.md`

Forbidden-path scan: no forbidden path used as an authoritative source. Checked `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories` only as prohibited-source references.

## Exact Worktree Inventory

### Tracked edits in requested code/test scope

`git status --short` / `git diff --name-status`:

```text
 M scripts/sod_gate_enforcer.py
AM tests/test_legacy_reconciliation_contract.py
```

`scripts/sod_gate_enforcer.py`

- Diff size: `+637 / -10` lines.
- Added legacy residual/reconciliation constants and validators.
- Added canonical gate loading and report identity helpers.
- Added Gate4 original snapshot resolver.
- Added retry2/retry3 sidecar resolution.
- Added gate-date/report-wording validation.
- Added residual reconciliation enforcement to `check_sod_compliance()`.
- Removed automatic `extract_lessons()` call from `main()`.
- Syntax/import valid, but implementation is partial: `validate_legacy_reconciliation()` invokes `resolve_original_gate_snapshot()` for every legacy record. Only Gate4 records carry snapshot fields. This breaks ordinary records and contradicts the intended Gate4-only exception documented in the prior recovery diagnosis.

`tests/test_legacy_reconciliation_contract.py`

- Existing tracked file is staged-added/worktree-modified state (`AM`), with baseline index blob plus working-tree additions.
- Added `verify_legacy_gate_manifest` import.
- Added retry2/retry3 fixture monkeypatches.
- Added Gate4 snapshot tests, manifest path test, retry2/retry3 tests, residual ledger/reconciliation tests, and compliance fail-closed tests.
- Contains two duplicate identical writes in `test_missing_sidecar_fails_closed()` at lines 190-191. Harmless but indicates interrupted/partial patching.
- 39 tests collected.

`scripts/verify_legacy_gate_manifest.py`

- Untracked (`??`), not present in `git diff`.
- File is syntactically valid and imports successfully.
- No corrective diff exists to assess; treat as a partial/untracked sidecar of the canceled patch, not as an established baseline.

### Untracked legacy sidecars

All listed files are untracked. Each JSON lock matches current bytes; this is integrity evidence only, not provenance approval.

| File | Records | SHA-256 / lock result |
|---|---:|---|
| `.ly_state/session/legacy_gate_reconciliation_20260727.json` | 14 | `d29045a45c49ff42eaff77ae2b47995a8fe74e82ed52bdd1e14c394853e66e97`; match |
| `.ly_state/session/legacy_gate_reconciliation_retry2_20260727.json` | 14 | `ffa6552d4aa5dc536cb839a42a0c4d3fd55c41f52c860d754da33f1bf5fff06f`; match |
| `.ly_state/session/legacy_gate_reconciliation_retry3_20260727.json` | 14 | `8248295de899262b16a9efca5917c2d0c64be43547c089d7b5d86c9dc7bc16`; lock match |
| `.ly_state/session/legacy_residual_evidence_20260727.json` | 17 | `3dd408c81d89a8b7611b1363393d11bd523781ecf8ab3fe23af8050550ed69e3`; match |
| `.ly_state/session/legacy_residual_reconciliation_20260727.json` | 17 | `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`; match |

Gate4 residual snapshot exists. Non-Gate4 residual snapshots: not inspected as present in the residual sidecar inventory; prior diagnosis records zero non-Gate4 snapshots.

## Syntax and Import Validity

```text
scripts/sod_gate_enforcer.py AST: PASS
scripts/verify_legacy_gate_manifest.py AST: PASS
tests/test_legacy_reconciliation_contract.py AST: PASS
imports: PASS
```

`python -m py_compile` passed for all three requested Python files.

## Test Baseline

Command:

```text
python -m pytest tests/test_legacy_reconciliation_contract.py -vv -ra
```

Result: `36 passed, 3 failed, 2 warnings`.

Failures:

1. `test_valid_sidecar_preserves_gate_timestamp_and_null_semantics`: validator returns `legacy record ALPHA_WEAKNESS_DIAGNOSTICS_20260614 original gate snapshot missing or key mismatch` instead of valid.
2. `test_original_record_hash_drift_rejected`: expected `original gate record hash drift`; actual `legacy record ALPHA_WEAKNESS_DIAGNOSTICS_20260614 original gate hash drift`.
3. `test_non_gate4_legacy_record_uses_original_hash_compatibility`: ordinary non-Gate4 record rejected for missing snapshot.

`python -m unittest discover -s tests -p 'test_legacy_reconciliation_contract.py' -v`: `Ran 0 tests`, exit `5`; expected because this file uses pytest functions.

Full collection command:

```text
python -m pytest --collect-only -q
```

Result: exit `0`; 39 targeted tests collected in the requested file during targeted run. Full suite collection emitted unrelated existing warnings.

## Runtime Baseline

```text
python scripts/sod_gate_enforcer.py
INFO: legacy residual evidence valid; 17 residuals remain NEEDS_FIX
SoD Compliance: [PASS]
```

Exit: `0`.

```text
python scripts/verify_legacy_gate_manifest.py
B1 manifest verification: FAIL: phase_gates.json hash mismatch
```

Exit: `1`.

The manifest pins `phase_gates.json` SHA-256 `671435336c07c4de4ff069a2250c3f0c45e61d22258bbaeeda099516e3659dae`; current mutable file differs. This is a pre-existing/shared-worktree state issue, not evidence that the manifest verifier code is valid for recovery. Do not overwrite `phase_gates.json` in this read-only assessment.

## Recovery Decision

Clean recovery cannot continue in-place. Restore individual hunks / reconstruct from the known-good baseline, then reapply the minimal intended patch.

Reasons:

- `sod_gate_enforcer.py` has a large partial patch with a confirmed semantic defect, not merely an unfinished tail.
- Three contract tests fail specifically because snapshot validation was applied to non-Gate4 records.
- `verify_legacy_gate_manifest.py` is untracked and absent from the diff, so its intended baseline status is unknown.
- Legacy sidecars are untracked; locks match bytes, but untracked status prevents treating them as safely recovered artifacts.
- Manifest verification is blocked by current `phase_gates.json` hash drift.

## Minimal Patch Sequence

1. Preserve this report and all unrelated worktree changes. Do not use destructive reset/checkout.
2. Compare the canceled session patch against the known-good L2 reports and the original committed files. Restore only the intended hunks in `scripts/sod_gate_enforcer.py` and `tests/test_legacy_reconciliation_contract.py`; do not replace whole files blindly.
3. In `validate_legacy_reconciliation()`, apply the Gate4-only guard:

   ```python
   if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704":
       _, snapshot_message = resolve_original_gate_snapshot(record, key)
       if snapshot_message != "ok":
           return False, f"legacy record {key} {snapshot_message}"
   elif _sha256(_immutable_gate_record(gate)) != record["original_gate_record_sha256"]:
       return False, f"legacy record {key} original gate record hash drift"
   ```

   Preserve all other fail-closed checks. Adjust exact error text only as required by the existing contract tests.
4. Keep snapshot fields exclusive to Gate4. Do not derive or regenerate historical hashes from mutable `phase_gates.json`.
5. Remove duplicate no-op fixture write in the test only if it belongs to the canceled patch; otherwise leave unrelated user changes untouched.
6. Treat `scripts/verify_legacy_gate_manifest.py` and the five untracked sidecars as artifacts requiring explicit recovery decision. Do not stage or delete them during this recovery assessment.
7. Restore/verify the manifest-pinned `phase_gates.json` baseline through the owning recovery session before using manifest verification as a meaningful gate. No manual hash replacement.
8. Re-run:

   ```text
   python -m pytest tests/test_legacy_reconciliation_contract.py -q
   python scripts/verify_legacy_gate_manifest.py
   python scripts/sod_gate_enforcer.py
   ```

9. Submit to L3 only after targeted tests pass, manifest verification passes, and all intended artifacts are explicitly tracked/approved.

## Disposition

`NEEDS_FIX`. Partial edits are syntactically valid but semantically incomplete. Recovery requires individual-hunk restoration plus Gate4-only snapshot validation. No approval, staging, sidecar regeneration, manifest overwrite, or source correction performed.
