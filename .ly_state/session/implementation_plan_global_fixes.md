# Implementation Plan: Fix Global Test Suite

**Gate**: `fix_global_test_suite_20260809`
**Plan approval**: `[APPROVED]`
**Approval session**: `019fe4d2-1ce4-7870-81a1-30c68435f617`
**L2 writer**: Role 15 (`data-engineer`)
**L3 auditor**: Role 17 (`qa-engineer`)

1. Restore `CandidateRecord.clear_signals()` and clear non-selected top-k buffers.
2. Align the nested-objective mock with the production signature.
3. Correct the legacy reconciliation `field_drift` fixture schema without changing production behavior.
4. Enforce the 10.0% execution slippage kill switch.
5. Complete the V2 terminal-receipt fixture fields.
6. Skip lifecycle reads during `skip_refetch` and write valid combined data exactly once.
7. Bound macro lock acquisition to 120 seconds and test timeout handling.
8. Run targeted tests, full suite, compliance scripts, then write the L2 report.

Preserve unrelated dirty work. Modify only the approved scope. No self-approval.
