# Role 21 Provenance Re-Audit - Gate4 Hash Drift

**Role**: 21 `code-reviewer`, Codex L3  
**Date**: 2026-07-30  
**Gate**: `GP_OVERFITTING_REMEDIATION_GATE4_20260704`  
**Boundary**: only this report written

## Sources

Authoritative repo-local reads: `.agents/AGENTS.md`, `.agents/agent/code-reviewer.md`, and declared `code-review-checklist`, `clean-code`, `testing-patterns`, `audit-cycle`, `omega-sod` skill files. Forbidden paths `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories` were non-authoritative scan evidence only.

Compared current gate; residual reconciliation+lock; original commit `f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344`; original Role 23 report; retry1/2/3; historical/fresh Role 21 reports; Role 9/11/16 evidence; B1 manifest; validators.

## Drift

- Residual raw/lock: `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f` - match.
- Snapshot envelope: `c7e1aa1fb1b2947d0d2db376d7fbe09313fa1424fa1e515d3ff3f30db2b0ce1c` - match.
- Snapshot embedded record canonical hash: `722208a37465f0aec8158185fd94ae12ab7177bb8dea0f61f4745b0646821b9e`.
- Stored original claim: `a406d7bfda3ab8c312bcfe4e7ed97973535c4d9a1a6beb6bb3016da98651ed66` - **mismatch**.
- Current immutable projection: `be0861d7e1bfc40685e6f483d64887bcf817f0315587f7e6a7096700f9e6433f`.

`resolve_original_gate_snapshot()` validates the envelope and equality of two stored strings, but never validates `_sha256(snapshot["record"])`. It returns `ok` despite `722208... != a406...`.

Snapshot-to-current fields: `l2_session_id` changed from `l2_role16_gp_gate4_20260704` to `l2_role16_b1_gate4_reconcile_20260728`; `canonical_source_evidence` changed absent to six entries.

Original-commit-to-snapshot fields: `timestamp` changed from `2026-07-04T00:40:00+07:00` to `2026-06-26T06:36:11.4153000+07:00`; `codex_approval=APPROVED` and `claude_code_approval=APPROVED` disappeared. Original L3 Role 23 identity/report differs from current Role 21 B1 identity/report. L3 fields are mutable; timestamp and dual approvals are not.

## Authority

- Current `phase_gates.json`: current metadata only.
- Commit `f34fcbba...` plus original Role 23 report: original published gate.
- Residual sidecar: byte integrity only; embedded record/hash binding invalid.
- Retries repeat `a406...`; repetition is not proof.
- B1 manifest binds later B1 state, not original state.
- Audit approvals cannot repair the broken hash binding.

Authority for `a406...` is not proven.

## Required Append-Only Repair

Publish a new Gate4-only sidecar. Exact fields: `schema_version=legacy-gate-original-provenance/v1`, `gate`, `predecessor_path`, `predecessor_raw_sha256`, `predecessor_lock_path`, `predecessor_lock_value`, `original_commit`, `original_gate_path`, `original_gate_record`, `original_gate_record_sha256`, `original_audit_report_path`, `original_audit_report_sha256`, `current_gate_record_sha256`, `supersedes_claim_sha256`, `reason`, `published_at`.

Exact predecessor: `.ly_state/session/legacy_residual_reconciliation_20260727.json`; raw/lock hash `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`. Original commit: `f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344`. Original paths: `.ly_state/session/phase_gates.json`, `.ly_state/session/audit_reports/role23_gp_gate4_20260704.md`. Current hash: `be0861d7e1bfc40685e6f483d64887bcf817f0315587f7e6a7096700f9e6433f`. Superseded claim: `a406d7bfda3ab8c312bcfe4e7ed97973535c4d9a1a6beb6bb3016da98651ed66`.

Extract `original_gate_record` directly from the pinned commit. Publication: canonical UTF-8/LF temp JSON; exact-schema re-read; recompute hashes; raw-byte lock; no-clobber sidecar then lock; partial/invalid new artifact blocks fallback.

Validator must bind exact predecessor hashes; verify predecessor bytes/lock; resolve pinned commit; recompute embedded record hash; compare pinned Gate4 field-for-field; verify pinned report bytes/hash, Role 23, Gate4, `[APPROVED]`. Reject unknown fields, tamper, partial publication, predecessor drift, missing commit, report drift, hash drift. Tests: each rejection, no-clobber, invalid-new-sidecar no-fallback.

## Validation

- `python scripts/sod_gate_enforcer.py`: FAIL; first current failure is unrelated `GP_ALT_DATA_FETCHER_OPTIMIZATION original gate record hash drift`.
- `python scripts/verify_legacy_gate_manifest.py`: blocked by mandatory failing enforcer subprocess.
- Gate4 resolver defect independently reproduced.

## Verdict

[NEEDS_FIX]

Original Gate4 hash authority unproven. Append-only pinned-commit sidecar, predecessor-bound lock, fail-closed validator required.
