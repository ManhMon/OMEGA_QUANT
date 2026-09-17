# Code Review Audit Report

**Role**: 21 code-reviewer (Codex L3)
**Date**: 2026-06-12
**Gate**: LLM_CLOSED_LOOP_FORMULA_SEARCH_20260612
**L2 Session**: l2_role9_llm_closed_loop_formula_search_20260612
**L2 Role**: 9 backend-engineer
**Verdict**: [NEEDS_FIX]

## SOD Checks

- Writer != auditor: PASS. L2 role_id 9 != L3 role_id 21.
- Role spec validation: PASS. `backend-engineer.md` is tier 2 OpenCode; `code-reviewer.md` is tier 3 Codex with `sod_boundary`.
- L3 boundary: PASS. Audit wrote only this report and will update only `.ly_state/session/phase_gates.json`.
- Scope reviewed: scoped source/test/evidence files only. `.ly_state/session/llm_formula_search_memory_20260612.json` is missing.

## Blocking Findings

1. **tests/quant_test_infinite_evolution.py:1474**: Required test suite fails. `test_prompt_v3_no_secrets` asserts the v3 prompt must not contain `secret`, but `llm_symbolic_synthesizer.py:860` includes `NO SECRETS`, causing a direct failure. This blocks approval because the mandated `pytest tests/quant_test_infinite_evolution.py -q` command exits 1.

2. **tests/quant_test_infinite_evolution.py:1694**: Required test suite has a broken test. `FormulaSearchRunner.__init__.__defaults__` is `None`, so `test_formula_search_aggregate_stats_only` raises `TypeError`. L2 reported tests as verified, but the actual pytest command fails.

3. **src/omega/quant/evolution/llm_formula_search.py:359**: Closed-loop accepted candidates are discarded. The loop records counts, then `final_candidates` is initialized empty and the code re-runs synthesis/scoring after the loop at lines 372-388. This means returned candidates are not the accepted candidates from the iterative batches, can be nondeterministic, and do not reflect evidence counts. The implementation does not satisfy iterative closed-loop batch generation semantics.

4. **src/omega/quant/evolution/llm_formula_search.py:57**: Bad motif feedback is not implemented. `enable_motif_blacklist` and `bad_motifs` exist, but `rg` shows no runner logic that extracts bad motifs, calls `add_bad_motif`, or passes motifs into the v3 prompt. Evidence `bad_motifs_count` will remain 0 unless state is manually modified, so the requested bad motif feedback loop is not functional.

5. **scripts/backtest_v2_cpcv.py:1506**: Required memory/evidence path is not produced. Backtest writes `--llm-search-evidence` at lines 1518-1522, but never calls `runner.save_state(...)`; `.ly_state/session/llm_formula_search_memory_20260612.json` is absent. This violates the scoped evidence expectation and weakens reproducibility of search memory/dedupe.

## Verification Evidence

- `python scripts/sod_gate_enforcer.py` before gate update: PASS, exit 0, existing gates safe.
- `python -m py_compile src/omega/quant/evolution/llm_formula_search.py src/omega/quant/evolution/llm_symbolic_synthesizer.py src/omega/quant/evolution/llm_formula_scorer.py scripts/backtest_v2_cpcv.py tests/quant_test_infinite_evolution.py`: PASS, exit 0.
- `pytest tests/quant_test_infinite_evolution.py -q`: FAIL, exit 1. Result: 47 passed, 3 failed.
  - `test_prompt_v3_no_secrets`: prompt contains `secret`.
  - `test_formula_search_aggregate_stats_only`: `TypeError: 'NoneType' object is not subscriptable`.
  - `test_formula_search_state_persistence`: `PermissionError` under this sandbox temp path. This one appears environment-related, but the test command still fails as required-run evidence.

## PIT / Leakage Review

- Backtest integration calls `runner.run_search(... labels=None)` at feature generation, so no test-label values are passed from the CPCV flow.
- Aggregate failure stats are scalar-only in `_compute_aggregate_failure_stats`; no row-level arrays are stored there.
- Naming is misleading: prompt text says `Median Test IC` while code comments claim train-only metrics. L2 should rename this to train/validation aggregate metric language to avoid implying test feedback in prompts.

## Required Fixes

1. Make the required pytest command pass without weakening the checks.
2. Accumulate accepted nodes from each closed-loop iteration and return exactly those accepted nodes, not a post-loop re-synthesis.
3. Implement functional bad motif extraction/blacklist feedback and include aggregate motif guidance in the v3 prompt without row-level data.
4. Persist the search memory/state artifact at the scoped path or remove it from gate scope and evidence claims.
5. Rename prompt/evidence fields from `test_ic` / `median_test_ic` to train-only or validation-only terminology unless true held-out test data is intentionally used outside prompts.

## Verdict

[NEEDS_FIX]

The implementation is not approvable until the required tests pass and the closed-loop search/motif-memory behavior matches the gate requirements.
