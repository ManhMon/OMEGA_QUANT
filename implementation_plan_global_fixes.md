# Fix Global Test Suite (8 Out-of-Scope Failures)

This plan details the root causes and precise fixes for the 8 pre-existing test failures across the global test suite, as well as fixing a medium severity unbounded lock wait in the macro pipeline.

## Segregation of Duties (SoD) Metadata
- **Gate**: `fix_global_test_suite_20260809`
- **L2 Implementer**: `Role 15 (data-engineer)`
- **L3 Auditor**: `Role 17 (qa-engineer)`
- **Independence Check**: Writer (15) != Auditor (17). Self-approval is strictly forbidden.

## Proposed Changes

### Alpha Generation: Hybrid Alpha Miner (`src/omega/quant/evolution/hybrid_alpha_miner.py`)
- **[MODIFY] `CandidateRecord` class**:
  Add/Restore the `clear_signals()` method. This method MUST clear all cached signals, including calling `self._fold_values.clear()`, so memory is released when candidates fall out of the top-k selection buffer. Fixes `test_candidate_record_clear_signals_releases_cached_arrays`.
- **[MODIFY] `HybridAlphaMiner.run()`**:
  Ensure that `clear_signals()` is called on non-selected candidates after top-k selection. Fixes `test_hybrid_alpha_miner_clears_non_selected_candidate_buffers_after_top_k`.
- **[MODIFY] `tests/test_hybrid_alpha_real_market.py`**:
  Update `test_nested_objective_reuses_injected_synth_instance` to remove the unexpected `synth` keyword argument from the mock of `NestedCVObjective.score_candidate()`, making it precisely match the production signature.

### Reconciliation Layer (`tests/test_legacy_reconciliation_contract.py`)
- **[MODIFY] `tests/test_legacy_reconciliation_contract.py`**:
  Fix the test `test_retry1_gate3_absent_from_immutable_predecessor_uses_pinned_claim`. Currently, the dynamic mock for `field_drift` is invalid. We will align the test's fixture/mock for `field_drift` strictly to match the schema required by the production `sod.validate_legacy_residual_provenance_retry1` logic without altering the production expected result `(True, 'legacy residual reconciliation: 17 resolved; 1 open')`.

### Execution Sim (`src/omega/quant/execution/smart_execution.py` & Tests)
- **[MODIFY] `src/omega/quant/execution/smart_execution.py`**:
  Implement the kill switch logic in `apply_realistic_tc_kill_switch` to explicitly raise `ExecutionSafetyError`.
  - **Threshold**: Slippage > 10.0%
  - **Condition**: If the absolute slippage percentage exceeds this threshold, halt execution.
  - **Error Message**: `"Slippage exceeds 10.0% kill switch threshold"`
- **[MODIFY] `tests/test_paper_execution_pipeline.py`**:
  Fix the `TestMarketDataExecutionGate.test_valid_newest_v2_terminal_receipt_is_executable` test. The production contract asserts V2 receipt eligibility. The test's `evidence` dict is currently missing fields. We will NOT change the expectation. Instead, we will fix the mock `evidence` to include the required V2 receipt fields: `schema_version = 2`, `cutoff_at = "2026-07-29T10:00:00+00:00"`, `pointer_path`, and `pointer_sha256`.

### Market Data Updater (`scripts/update_market_data.py` & Macro Pipeline)
- **[MODIFY] `scripts/update_market_data.py`**:
  1. Wrap the `_load_ticker_lifecycle()` read in `if not skip_refetch:`. This ensures the mutable lifecycle state is NOT read when skipping refetches (fixing `test_hnx_only_vci_candidate_is_authoritative`).
  2. Fix validation-write logic so `atomic_write_with_backup` is called *exactly once* when the combined dataset is valid, and *zero times* when invalid (fixing `test_write_proceeds_when_combined_valid`).
- **[MODIFY] `src/omega/data/macro_pipeline.py`**:
  Address the deep audit advisory: `FileLock(..., timeout=-1)` can block indefinitely. Set a finite timeout (e.g., `timeout=120`) and catch `filelock.Timeout`, raising an actionable pipeline error `RuntimeError("Macro data concurrent lock acquisition timeout")`. Add a contention test for this.

## Verification Plan
1. **Targeted Tests**: Run `pytest tests/test_hybrid_alpha_real_market.py tests/test_legacy_reconciliation_contract.py tests/test_paper_execution_pipeline.py tests/test_smart_execution.py tests/test_update_market_data_official_watermark.py tests/test_vci_updater_validation_write_blocker.py -v` to ensure the 8 failing tests now pass.
2. **Full Suite Regression**: Run `pytest -q` to verify the global test suite is 100% green.
3. **SoD Enforcer**: Run `python scripts/sod_gate_enforcer.py` to ensure L2 and L3 compliance.
