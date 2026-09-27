# W1 Rollback Procedure

## Rollback Target
- **Target Commit**: `1c19b8727e1a12c53e50e226f420dc7dde18669a` (Commit closing `GATE_JEV_DEEP_INTEGRATION_W0_20260927`)
- **Gate**: `GATE_JEV_DEEP_INTEGRATION_W1_20260927`

## Rollback Steps
1. Preserve any uncommitted work first. Inspect `git diff` and `git status`; save scoped changes separately before rollback. Do not discard other contributors' changes.
2. Restore only the two W1 code files from the baseline commit after preserving their local changes:
   ```powershell
   git checkout 1c19b8727e1a12c53e50e226f420dc7dde18669a -- src/omega/core/llm_config.py tests/test_sod_jev_model_routing.py
   ```
3. Retain W1 evidence and audit trail. Quarantine or back up the SQLite cache before reusing it: the baseline implementation may not understand v2 rows. SQLite WAL/SHM files belong with the cache. Do not delete a shared cache while another writer is active.
4. Re-verify the scoped test suite:
   ```powershell
   python -m pytest -o addopts="" tests/test_sod_jev_model_routing.py -q
   ```
5. L1/L3 owns gate verification and any gate transition; rollback itself does not approve or close the gate.

Legacy v1 daily cache rows and v2 full-cutoff rows have distinct fingerprints. Restore cache only after verifying the target implementation accepts its schema.
