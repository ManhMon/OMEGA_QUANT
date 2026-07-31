# L2 Role 9 Remediation Record

- Session: `l2_role9_gate4_original_provenance_sidecar_fix1_20260731`
- Gate: `gate4_original_provenance_sidecar_fix1_20260731`
- Scope: Gate4 provenance validator, contract tests, canonical sidecar and lock only.

## Sources

- `.agents/AGENTS.md`
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.ly_state/session/audit_reports/role21_gate4_original_provenance_sidecar_20260731.md`
- `scripts/sod_gate_enforcer.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/legacy_gate4_original_provenance_20260731.json`
- `.ly_state/session/legacy_gate4_original_provenance_20260731.sha256`

## Changes

- Pinned predecessor raw SHA-256 and predecessor lock to non-bundle-controlled literal `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`.
- Strictly parse `published_at` as UTC `Z`; reject malformed and future instants.
- Reissued canonical sidecar with implementation-time UTC `published_at` `2026-07-30T23:50:13Z` and matching SHA-256 lock.
- Added canonical-pass, joint predecessor/lock/sidecar replacement, malformed timestamp, and future timestamp contract coverage.
- Preserved no-clobber and partial-artifact fail-closed publisher rules.

## Verification

- `python -m pytest -q tests/test_legacy_reconciliation_contract.py`: `76 passed`; unrelated pytest cache warning.
- `python -m py_compile scripts/sod_gate_enforcer.py`: passed.
- `git diff --check -- scripts/sod_gate_enforcer.py tests/test_legacy_reconciliation_contract.py .ly_state/session/legacy_gate4_original_provenance_20260731.json .ly_state/session/legacy_gate4_original_provenance_20260731.sha256`: passed.
- `python scripts/sod_gate_enforcer.py`: expected fail, `retry1 provenance trusted tag object OID pin unset`.

## Forbidden Path Scan

- Scan of scoped source found only enforcement constants for `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` in `scripts/sod_gate_enforcer.py`.
- No authoritative reliance on forbidden paths. Repo-local role and declared skill sources listed above.
