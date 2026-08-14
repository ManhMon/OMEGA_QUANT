# VCI Final Safety Closure Plan

Approved remediation scope for `role21_vci_final_safety_fix1_20260728`:

1. Recompute the canonical versioned exception hash before exception semantic entry checks; cover hash-priority behavior.
2. Recover stale publication locks by atomic rename claim, never unlink then reacquire; cover contention/ownership behavior.
3. Keep Windows directory durability fail-closed and make relevant tests explicit about the capability contract.
4. Convert strict timestamp contract errors in `validate_release_gates` into the documented provenance gate failure.
5. Verify the relevant Windows suites without refresh, network, live publish, data mutation, or phase-gate mutation.
