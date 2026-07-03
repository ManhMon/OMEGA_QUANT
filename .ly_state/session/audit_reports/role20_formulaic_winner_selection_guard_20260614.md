# Compliance Audit Report
**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-14T21:14:22+07:00
**Gate**: FORMULAIC_WINNER_SELECTION_GUARD_20260614
**Submission**: l2_role14_formulaic_winner_selection_guard_20260614
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Source Evidence
- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Forbidden path scan result: no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source

## Scope Reviewed
- `src/omega/quant/alpha/phase35.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_formulaic_winner_selection_guard.py`
- `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_baseline.json`
- `.ly_state/session/l2_role14_formulaic_winner_selection_guard_20260614.md`

## Checks
- Writer != auditor: PASS (`14 != 20`)
- L3 boundary: PASS (audit report + phase gate only)
- Default disabled/no live behavior change: PASS (`formulaic_winner_guard=False`, CLI `store_true`)
- Guard opt-in/research-only: PASS (CLI gated by `--formulaic-winner-guard` or `--winner-alpha-filter`)
- PIT safety: PASS for IC source; guard IC uses `val_actual` from current fold at `phase35.py:2465-2473`
- Evidence persisted per fold: PASS (JSON has 12 folds with `winner_guard_evidence`)
- CPCV12 output: PASS (12 requested, 12 executed, 12 fold details)
- Test command: PASS, `51 passed` via `python -m pytest tests/phase35/test_formulaic_winner_selection_guard.py -q`

## Blocking Findings
1. **L2 forbidden-path wording is not enforcer-compliant.**  
   `.ly_state/session/l2_role14_formulaic_winner_selection_guard_20260614.md` says: `Scanned for .gemini/, .antigravity-ide/, .openclaw/, C:\Users\GHC\.agents, .codex/memories -- none found in repo tree`. This does not use the required sentence-level non-authoritative wording and does not name `.gemini\antigravity-ide\scratch\ag-kit` or `.openclaw\skills` exactly. Per audit instruction, this requires [NEEDS_FIX].

   Required replacement wording:

   `no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source`

2. **Winner guard can re-admit non-allowlist legacy alphas after excluding all candidates.**  
   `phase35.py:1193-1203` falls back to original `candidate_alphas` when all are excluded. CPCV evidence shows this happened:
   - fold 2 `post_guard_alphas`: `alpha_p34_volume_clock_acceleration_10`, `alpha_p34_close_auction_drift_10`
   - fold 7 `post_guard_alphas`: `alpha_p34_volatility_compression_5`, `alpha_p34_tick_signed_volume_imbalance_5`, `alpha_p34_volume_clock_acceleration_10`

   This contradicts the stated contract that the enabled guard constrains the selection/fallback pool to the allowlist and prevents negative legacy alphas from entering. The current tests also encode this behavior as expected at `tests/phase35/test_formulaic_winner_selection_guard.py:243-253` and `:275-285`, so the suite passes while preserving the contract violation.

## Required Fixes
1. Update the L2 report forbidden-path scan sentence to the exact required wording above.
2. Change winner-guard fallback semantics so guard-enabled selection/fallback evidence and actual candidate pools do not re-admit non-allowlist legacy alphas. If empty selection must be avoided, use an allowlist-only fallback or mark the fold excluded; do not restore original legacy candidates.
3. Update tests to assert no non-allowlist alpha appears in guard-enabled post-guard/fallback pools, including all-excluded cases.
4. Regenerate CPCV12 evidence and verify all 12 folds have allowlist-only guard-enabled `post_guard_alphas` and fallback evidence.

## CODEX AUDIT VERDICT
**Status:** [NEEDS_FIX]
**l3_session_id:** l3_role20_formulaic_winner_selection_guard_20260614
**l3_session_key:** role20_formulaic_winner_selection_guard_20260614
**audit_report_path:** .ly_state/session/audit_reports/role20_formulaic_winner_selection_guard_20260614.md
**final_verdict:** [NEEDS_FIX]

**Signature:** Codex L3 Compliance Officer
