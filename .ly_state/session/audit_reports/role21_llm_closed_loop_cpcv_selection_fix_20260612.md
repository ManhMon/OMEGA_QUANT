# Code Review Audit Report
**Role**: 21 code-reviewer (Codex L3)
**Date**: 2026-06-12T12:15:00+07:00
**Gate**: LLM_CLOSED_LOOP_CPCV_SELECTION_FIX_20260612
**L2 Session**: l2_role9_llm_closed_loop_cpcv_selection_fix_20260612
**Tier 2 Engineer**: 9 backend-engineer (OpenCode)
**Verdict**: [NEEDS_FIX]

## SOD Boundary
- Writer != auditor verified: l2_role_id=9, l3_role_id=21.
- L2 role spec valid: backend-engineer, role_id=9, tier=2, platform=OpenCode.
- L3 role spec valid: code-reviewer, role_id=21, tier=3, platform=Codex, sod_boundary present.
- L3 production/test/source write boundary honored by this audit.

## Findings
1. BLOCKING - test-label leakage in CPCV candidate selection. `scripts/backtest_v2_cpcv.py:1526-1529` and `scripts/backtest_v2_cpcv.py:1635-1639` pass full-sample `target.values` into LLM scoring/top-K before CPCV splits are created (`scripts/backtest_v2_cpcv.py:1936`, `scripts/backtest_v2_cpcv.py:758`). Candidate selection can see labels from later CPCV test/OOS rows. This violates train-fold supervised selection and no test-label leakage. `test_no_test_label_leakage` only uses a synthetic train-only unit panel, so it does not cover this integration path.
2. BLOCKING - top-K metadata is not persisted to evidence JSON. `scripts/backtest_v2_cpcv.py:1536-1540` writes `search_evidence` before `top_k_selection` and `final_candidate_count_after_topk` are added at `scripts/backtest_v2_cpcv.py:1570-1575`.
3. MAJOR - closed-loop summary still mixes count scopes. `scripts/backtest_v2_cpcv.py:1684-1689` maps total to raw generated and accepted to scoring accepted, then computes rejected as raw-generated minus scoring-accepted. This is non-negative but misleading when safety/dedup drops candidates.

## Verified Good
- Stage-count fields exist in `llm_formula_search.py`; per-iteration `scoring_rejected = scoring_input - scoring_accepted` is same-scope and non-negative.
- `deployment_ready` remains false and `requires_full_cpcv` remains true in search evidence.
- `--llm-top-k` and `OMEGA_LLM_TOP_K` handling are present.
- IC/DSR proxy metrics compute when labels are supplied; aggregate failure stats persist on search state.

## Verification Run
- Pre-update `python scripts/sod_gate_enforcer.py`: PASS, 106 phases, safe to push before this gate.
- `python -m py_compile` scoped files: PASS.
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`: FAIL from sandbox temp write denial in `test_formula_search_state_persistence`; 57/58 completed before failure. Reruns with `TMP/TEMP=C:\tmp` and repo-local `tempfile.tempdir` still failed because temp dirs were not writable in this sandbox.

## Required Fixes
1. Move supervised LLM scoring/top-K inside each CPCV training fold, or pass only fold-train rows/labels into selection.
2. Persist top-K evidence after mutation or defer writing evidence JSON until after final top-K selection.
3. Use same-scope summary counts: total_scoring_input, total_scoring_accepted, total_scoring_rejected, plus separate final_after_topk.
4. Add integration test proving `backtest_v2_cpcv.py` never passes held-out/test labels into LLM search/top-K.

## Verdict
[NEEDS_FIX]
