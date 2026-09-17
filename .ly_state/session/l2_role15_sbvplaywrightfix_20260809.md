# L2 Remediation Evidence: sbv_playwright_integration_20260809

Status: EVIDENCE SUBMITTED. No approval asserted. No production or test code changed.

## Scope

- `src/omega/data/macro_pipeline.py`

## Finding

The `pytest -q` failures reported by L3 are a pre-existing, out-of-scope baseline. The same eight test identifiers were independently recorded before this gate:

- `2026-08-07`: `.ly_state/session/audit_reports/role20_news_collection_remediation_v10_fix3_20260807.md`, line 16, records eight full-suite failures outside its news scope.
- `2026-08-08`: `.ly_state/session/audit_reports/role21_macro_calendar_fix_20260808.md`, lines 17-27, records the exact eight identifiers while its scope was `src/omega/data/macro_pipeline.py` and `tests/test_macro_pipeline.py`.
- `2026-08-08`: `.ly_state/session/audit_reports/role21_macro_sbv_graceful_20260808.md`, lines 20-22, records `3171 passed`, `8 failed`, `3 skipped` for the same macro-pipeline scope.

## Current Reproduction

- Command: `python -m pytest -q`
- Result: failed with the same eight identifiers named by the 2026-08-08 macro audit:
  1. `tests/test_hybrid_alpha_real_market.py::test_candidate_record_clear_signals_releases_cached_arrays`
  2. `tests/test_hybrid_alpha_real_market.py::test_nested_objective_reuses_injected_synth_instance`
  3. `tests/test_hybrid_alpha_real_market.py::test_hybrid_alpha_miner_clears_non_selected_candidate_buffers_after_top_k`
  4. `tests/test_legacy_reconciliation_contract.py::test_retry1_gate3_absent_from_immutable_predecessor_uses_pinned_claim`
  5. `tests/test_paper_execution_pipeline.py::TestMarketDataExecutionGate::test_valid_newest_v2_terminal_receipt_is_executable`
  6. `tests/test_smart_execution.py::test_apply_realistic_tc_kill_switch_raises_on_extreme_slippage`
  7. `tests/test_update_market_data_official_watermark.py::test_hnx_only_vci_candidate_is_authoritative`
  8. `tests/test_vci_updater_validation_write_blocker.py::TestCombinedValidationWriteBlocker::test_write_proceeds_when_combined_valid`

## Scope Independence

- L3's gate report identifies the implementation scope as `src/omega/data/macro_pipeline.py`, `requirements.txt`, and `tests/test_macro_pipeline.py`; all eight failing tests are outside it.
- Searches of each six failing test module for `macro_pipeline.py` returned `NO_MATCH`; the three hybrid failures share one module.
- Searches of `src/omega/` locate failure-domain code only in independent modules, including `src/omega/quant/evolution/hybrid_alpha_miner.py` and `src/omega/quant/execution_sim.py`.
- The scoped targeted suite was already verified by L3: `pytest tests/test_macro_pipeline.py -q` returned `21 passed`.

## Repo-Local Files Read

- `REPO_AGENT_ROOT=.agents/agent`
- `REPO_SKILL_ROOT=.agents/skills`
- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `.ly_state/session/audit_reports/role17_sbv_playwright_integration_20260809.md`
- `.ly_state/session/audit_reports/role20_news_collection_remediation_v10_fix3_20260807.md`
- `.ly_state/session/audit_reports/role21_macro_calendar_fix_20260808.md`
- `.ly_state/session/audit_reports/role21_macro_sbv_graceful_20260808.md`
- `.ly_state/session/l2_role15_sbv_playwright_20260809.md`
- `src/omega/data/macro_pipeline.py`
- `scripts/sod_report_evidence.py`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.
- Strict forbidden-path mention scanner: scoped source `src/omega/data/macro_pipeline.py` returned `NO_MATCH` for all four forbidden paths. No forbidden source was read.

## Lesson Applied

- Strict forbidden-path mention scanner: exact canonical scan lines supplied; scoped source scan returned `NO_MATCH`.

## Submission

The eight failures predate `sbv_playwright_integration_20260809`, reproduce unchanged, and have no import/reference relationship to `src/omega/data/macro_pipeline.py`. This L2 report supplies evidence only; independent L3 review determines the gate verdict.
