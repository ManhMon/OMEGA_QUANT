# Gate3 Phase B Tag OID Pin Audit

- Gate: `gate3_phaseb_tag_oid_pin_20260801`
- L2 session: `l2_role9_gate3_phaseb_oid_pin_20260801`
- Writer: Role 9 backend-engineer (OpenCode L2)
- Auditor: Role 21 code-reviewer (Codex L3)
- Date: `2026-08-01`
- Scope: `scripts/sod_gate_enforcer.py`; `tests/test_legacy_reconciliation_contract.py`; L2 report.
- Exclusions honored: bundle, sidecar, historical reports, `phase_gates.json`, validation module/lock, tags, commits, push.

## Repo-Local Sources

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- Forbidden paths were not used as authoritative sources.

## Findings

- Writer/auditor separation valid: Role 9 != Role 21.
- Exact trust ref pinned at `scripts/sod_gate_enforcer.py:140`: `refs/tags/omega-provenance-retry1-gate3-20260801`.
- Exact annotated-tag object OID pinned at `scripts/sod_gate_enforcer.py:142`: `58cbde4924eef16166ea57b9ee8e6197fdced302`.
- Independent Git plumbing observed object type `tag`; peeled commit `29020665d2a2a86eb5cbc0d943010eeb72fac6de`.
- Independent `git verify-tag --raw` observed `VALIDSIG 9EEB38EC57367763580E1FC95936F757A44783BB` and valid signature status.
- `scripts/sod_gate_enforcer.py:490` rejects lightweight/wrong-type refs through `^{tag}`.
- `scripts/sod_gate_enforcer.py:492`-`496` rejects moved or recreated refs before signature validation when tag-object OID differs.
- `scripts/sod_gate_enforcer.py:497`-`500` rejects invalid, wrong-signer, malformed, missing, or duplicate signature status.
- `scripts/sod_gate_enforcer.py:501`-`508` resolves the peeled commit only after exact tag-object and signature validation, then requires trusted-commit and index bundle bytes to equal local canonical bytes. The exact annotated-tag object OID cryptographically fixes its target commit; a different peeled commit requires a different tag-object OID and fails the earlier pin.
- Added assertions at `tests/test_legacy_reconciliation_contract.py:636`-`637` bind regression coverage to the exact ref and OID. Existing negative contracts cover unset/moved/recreated OID and strict signature parsing.
- Gate3/Gate1/Gate2 validation logic and PIT controls are unchanged by the two constant edits and two assertions.

## Independent Validation

- `git rev-parse refs/tags/omega-provenance-retry1-gate3-20260801`: `58cbde4924eef16166ea57b9ee8e6197fdced302`.
- `git cat-file -t refs/tags/omega-provenance-retry1-gate3-20260801`: `tag`.
- `git rev-parse 'refs/tags/omega-provenance-retry1-gate3-20260801^{}'`: `29020665d2a2a86eb5cbc0d943010eeb72fac6de`.
- Direct trusted bundle check: `_trusted_provenance_bundle(raw) == (True, "ok")`.
- `python -m py_compile scripts/sod_gate_enforcer.py tests/test_legacy_reconciliation_contract.py`: exit 0.
- Full bundle validation returned `retry1 provenance predecessor unreadable`; full enforcer returned `legacy residual evidence ledger and lock are required`. These are missing excluded manifest/ledger evidence, not defects in the scoped OID-pin change.
- No full enforcer success independently observed or claimed.

## Verdict

[APPROVED]
