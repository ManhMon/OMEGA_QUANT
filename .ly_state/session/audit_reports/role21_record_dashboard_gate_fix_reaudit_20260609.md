# Role 21 Re-Audit: record_dashboard_gate parsing compatibility

- Role: Code Reviewer / Role 21
- Verdict: [NEEDS_FIX]
- PIT Safety: N/A
- Role Compliance: PASS
- Gate Contract:
  - l3_session_id: 0e6878e9-1eed-41e0-91af-1b1346048366
  - l3_session_key: role21_record_dashboard_gate_fix_reaudit_20260609
  - audit_report_path: .ly_state/session/audit_reports/role21_record_dashboard_gate_fix_reaudit_20260609.md
  - final_verdict: [NEEDS_FIX]

## Scope

Inputs reviewed:
- .ly_state/session/l2_record_dashboard_gate_fix_report_20260609.md
- .ly_state/session/record_dashboard_gate_l2_opencode_20260609.jsonl

Files audited:
- scripts/record_dashboard_gate.py
- tests/test_record_dashboard_gate.py

## Required Check Results

- Legacy audit format: PASS. `VERDICT: [APPROVED]` with legacy session fields is still accepted by tests.
- Gate Contract format: FAIL. Basic approved Gate Contract format is accepted, but inconsistent Gate Contract verdicts can be approved unsafely.
- `[NEEDS_FIX]` and missing verdict reports: PASS for simple single-verdict cases.
- Fake/synthetic session IDs: PASS for covered fake ID case.
- Optional missing L2 session: PASS with caveat. The implementation records `not_provided_in_audit_report` rather than inventing an ID, but this path needs the verdict fix below before it is safe.
- Tests: PARTIAL. The suite is isolated and passes, but misses the inconsistent-verdict safety case.
- Unrelated dashboard/trading changes: PASS. Git diff for audited files shows only `scripts/record_dashboard_gate.py`; `tests/test_record_dashboard_gate.py` is untracked test coverage. No dashboard/trading code diff found.

## Blockers

1. `scripts/record_dashboard_gate.py:42` accepts `- Verdict: [APPROVED]` before checking `final_verdict`, so a Gate Contract report with top-level `- Verdict: [APPROVED]` and `- final_verdict: [NEEDS_FIX]` is recorded as approved.
   - Evidence: temp probe accepted the inconsistent report and wrote `final_verdict: [APPROVED]` to `phase_gates.json`.
   - Risk: Gate Contract `final_verdict` can be bypassed by an earlier approved display verdict, violating the required rejection of `[NEEDS_FIX]` reports.
   - Minimal L2 repair: make Gate Contract `final_verdict` authoritative when present. If both `Verdict` and `final_verdict` exist, require exact agreement; otherwise reject. Add a negative test where `Verdict=[APPROVED]` and `final_verdict=[NEEDS_FIX]` must exit 1 and must not record a gate.

## Verification Run

Commands executed:
- `python -m pytest tests/test_record_dashboard_gate.py -q`
- `python scripts/sod_gate_enforcer.py`

Results:
- `pytest`: PASS, `6 passed`; warning only: pytest cache path creation warning.
- `sod_gate_enforcer`: PASS, verified 72 phases, safe to push.

## Verdict Rationale

The L2 fix improves compatibility and current tests pass, but the parser can still approve a Gate Contract report whose contract-level `final_verdict` is `[NEEDS_FIX]`. Because this is an approval-safety path in the gate recorder, the change cannot be approved until the contract verdict precedence is fixed and covered by a regression test.
