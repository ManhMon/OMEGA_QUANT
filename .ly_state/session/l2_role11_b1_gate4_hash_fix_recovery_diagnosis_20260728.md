# Task-13170 Recovery Diagnosis

**Role:** 11 `devops-engineer` (L2 OpenCode)
**Status:** `NEEDS_FIX`
**Mode:** Read-only recovery diagnosis. No source, test, or sidecar mutation performed.

## Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/devops-engineer.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `scripts/verify_legacy_gate_manifest.py`
- `.ly_state/session/legacy_residual_reconciliation_20260727.json`
- `tests/test_legacy_reconciliation_contract.py`
- `git diff` for the requested scope

## Forbidden-Path Scan

No forbidden path was used as an authoritative source. Repo-local sources only.

Checked against the protocol forbidden set:

- `.gemini\\antigravity-ide\\scratch\\ag-kit`
- `.openclaw\\skills`
- `C:\\Users\\GHC\\.agents`
- `.codex\\memories`

## Findings

1. `validate_residual_reconciliation()` already models the required record shape: `LEGACY_SNAPSHOT_FIELDS` is allowed only for `GP_OVERFITTING_REMEDIATION_GATE4_20260704` at `scripts/sod_gate_enforcer.py:310-329`.
2. The active residual sidecar contains 17 records. Only `GP_OVERFITTING_REMEDIATION_GATE4_20260704` contains `original_gate_snapshot` and `original_gate_sha256`; all other 16 records correctly omit both fields.
3. `validate_legacy_reconciliation()` still calls `resolve_original_gate_snapshot(record, key)` unconditionally at `scripts/sod_gate_enforcer.py:572-574`. This makes every legacy record require Gate4 snapshot metadata, despite the sidecar schema and tests defining a Gate4-only exception.
4. The legacy validator must not bypass legacy validation. Timestamp equality, original record hash, historical evidence hash/path, fresh L3 report approval, identity uniqueness, workflow state, gate identity, and reconciliation timestamp checks remain mandatory for every non-Gate4 record.
5. The scoped diff shows partial Task-13170 edits in `scripts/sod_gate_enforcer.py` and `tests/test_legacy_reconciliation_contract.py`. `scripts/verify_legacy_gate_manifest.py` has no corrective implementation in the inspected diff.

## Exact Minimal Correction

In the affected legacy resolver, guard only the historical snapshot check:

```python
if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704":
    _, snapshot_message = resolve_original_gate_snapshot(record, key)
    if snapshot_message != "ok":
        return False, f"legacy record {key} {snapshot_message}"
```

Do not add snapshot fields to ordinary legacy records. Do not derive snapshots from active mutable gate metadata. Do not weaken or skip any other legacy validation. The existing residual resolver's Gate4-only schema/check must remain unchanged.

## Required Recovery Sequence

1. Restore `scripts/sod_gate_enforcer.py` and `tests/test_legacy_reconciliation_contract.py` to the intended pre-cancellation baseline, then apply only the Gate4 conditional above.
2. Restore the canonical `legacy_residual_reconciliation_20260727.json` bytes from the known-good sidecar. Preserve its existing Gate4 snapshot and omit snapshots from all other records.
3. Verify `.ly_state/session/legacy_residual_reconciliation_20260727.sha256` against the restored sidecar bytes. Never regenerate the sidecar from mutable active gate metadata.
4. Run `python -m pytest tests/test_legacy_reconciliation_contract.py -q`.
5. Add/retain regression coverage proving non-Gate4 legacy records pass without snapshots, Gate4 snapshot hash drift fails, and all legacy validation remains fail-closed.
6. Run `python scripts/verify_legacy_gate_manifest.py`. Current read-only result: `FAIL: phase_gates.json hash mismatch`; restore the manifest-pinned `phase_gates.json` baseline before treating manifest verification as meaningful.
7. Run `python scripts/sod_gate_enforcer.py` only after sidecar, lock, manifest, and tests are restored and verified.

## Integrity Evidence

- Sidecar record count: 17.
- Gate4 snapshot present: yes.
- Non-Gate4 snapshots present: 0.
- Current sidecar lock matches current bytes: yes.
- Current manifest verification: failed because `phase_gates.json` hash differs from the B1 manifest.

**Conclusion:** `NEEDS_FIX`. Apply one Gate4-only snapshot guard, retain every other legacy check, restore/verify the sidecar lock and manifest-pinned state, then rerun the contract tests and enforcer.
