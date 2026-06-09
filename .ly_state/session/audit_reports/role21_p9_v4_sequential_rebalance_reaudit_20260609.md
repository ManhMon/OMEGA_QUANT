# L3 Re-Audit Report - P9 v4 Sequential Dynamic Rebalance

Date: 2026-06-09T14:14:23+07:00
Role: Role 21 - Code Reviewer (L3 Codex)
Scope: Re-audit PIT safety fix after L2 OpenCode implementation.
Repo: C:\Users\GHC\repos\OMEGA_QUANT
Branch: feature/p9-dynamic-rebalance
VERDICT: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS

## Gate Contract

- Session ID: 1423d9ca-a67d-4641-b975-5335ac47ea8d
- Session Key: codex:role21:p9-v4-sequential-rebalance-reaudit:20260609T141423+0700
- audit_report_path: .ly_state/session/audit_reports/role21_p9_v4_sequential_rebalance_reaudit_20260609.md
- final_verdict: [NEEDS_FIX]

## Inputs Reviewed

- L2 report: `.ly_state/session/l2_p9_sequential_fix_report_20260609.md`
- Prior L3 report: `.ly_state/session/audit_reports/role21_p9_dynamic_rebalance_audit_20260609.md`
- Production file: `src/omega/quant/phase35_walk_forward.py`
- Test file: `tests/phase35/test_p9_dynamic_rebalance_pit_safety.py`

## Verification Performed

- Confirmed branch: `feature/p9-dynamic-rebalance` at `ac66109`.
- Checked state: `active_tasks.json` empty, `agent_locks.json` has `Codex: false`.
- RAM preflight: 10.27 GB free / 23.7 GB total.
- Code-review graph `get_minimal_context` attempted; timed out after 120s, so audit used direct file/diff inspection.
- Ran `python -m pytest tests/phase35/test_p9_dynamic_rebalance_pit_safety.py -q`: 3 passed.
- Ran `python -m pytest tests/phase35/ -q`: 103 passed.
- Reconstructed the prior fold-level lookahead pattern and ran the new future-mutation regression against it: the test failed as intended, with early weight `A` changing from `0.333333` to `0.000000` on `2024-02-19`.
- Ran a synthetic checkpoint trace against current sequential logic: frequency calls at available-date counts `[0, 5, 7, 14]`; observed weight changes at indices `[0, 5, 7]`.

## Blocking Finding

### 1. Dynamic cadence can rebalance too early after frequency changes

Severity: High

The PIT leak is fixed, but the sequential cadence implementation has a behavioral flaw around `current_rebal_freq` and `last_rebal_checkpoint_idx`.

In `src/omega/quant/phase35_walk_forward.py:972-981`, the code decides to recompute frequency with `idx % current_rebal_freq == 0`, then immediately sets `last_rebal_checkpoint_idx = idx`. In `src/omega/quant/phase35_walk_forward.py:987-994`, `should_rebalance` is then computed from that just-reset checkpoint, so any frequency-update date becomes an immediate rebalance date.

This mixes two different clocks:

- absolute fold index: `idx % current_rebal_freq == 0`
- elapsed dates since last actual checkpoint: `idx - last_rebal_checkpoint_idx`

Concrete failure mode:

- idx 0 starts at base 7, recomputes freq to 5, rebalances.
- idx 5 recomputes freq to 7, resets `last_rebal_checkpoint_idx = 5`, rebalances.
- idx 7 also satisfies absolute `7 % 7 == 0`, resets `last_rebal_checkpoint_idx = 7`, and rebalances only 2 dates after idx 5.

Synthetic evidence from current code:

```text
freq_calls_available_date_counts= [0, 5, 7, 14]
observed_weight_changes= [(0, '2024-01-01', (1.0, 0.0)), (5, '2024-01-08', (0.0, 1.0)), (7, '2024-01-10', (1.0, 0.0))]
```

That violates the intended dynamic cadence. Once freq is changed to 7 at idx 5, the next eligible rebalance should not fire at idx 7 solely because absolute index 7 is divisible by 7.

Required fix: drive both frequency recompute and rebalance eligibility from elapsed distance since the last actual rebalance checkpoint. Do not set `last_rebal_checkpoint_idx` before computing `should_rebalance` in a way that makes the update self-approve as an immediate rebalance. Add a regression test for a freq sequence like `7 -> 5 -> 7` proving no rebalance occurs before the new elapsed cadence is satisfied.

## PIT Safety Assessment

PASS for the prior blocking issue.

- The prior fold-level `current_vol = ...iloc[-1]` lookahead pattern is gone from the production file.
- `_compute_sequential_dynamic_freq()` computes baseline volatility from `train_df` only at `src/omega/quant/phase35_walk_forward.py:823-828`.
- At each frequency computation, caller filters available OOS data as `test_df[test_df['date'] < date]` at `src/omega/quant/phase35_walk_forward.py:977`, excluding current and future dates.
- `_compute_sequential_dynamic_freq()` only consumes its `available_test_df` argument for current volatility at `src/omega/quant/phase35_walk_forward.py:834-859`.
- First OOS date safely falls back to train baseline when no prior test data exists.

Important distinction: the remaining blocker is cadence correctness, not lookahead. The frequency decision data window is PIT-safe for each date where the code chooses to make a decision.

## Regression Test Assessment

Adequacy for prior PIT leak: PASS.

- `test_future_data_mutation_does_not_affect_early_weights()` mutates future test closes after an early checkpoint and asserts early weights are invariant.
- Reconstructed prior full-test fold-level logic fails this test, so it does catch the old lookahead pattern.
- `test_sequential_freq_computation_with_empty_available_test()` covers first-OOS empty prior-test behavior.

Coverage gap: FAIL for dynamic cadence.

- `test_dynamic_rebalance_frequency_updates_sequentially()` only asserts the fold runs without error.
- No test records actual rebalance dates or protects against the `idx 5 -> idx 7` early-rebalance bug.
- Add a deterministic unit test with a monkeypatched frequency schedule and changing top ticker signals, then assert weight changes occur only at allowed elapsed checkpoints.

## Stage 2 Behavior

- Top-N selection: PASS. Current rebalance path still uses `alpha_row.nlargest(min(top_n, len(alpha_row)))` at `src/omega/quant/phase35_walk_forward.py:998-1002`.
- Carry-forward weights: PASS. `last_weights` is carried into `weight_wide.loc[date]` at `src/omega/quant/phase35_walk_forward.py:1011-1012`.
- Sector cap: PASS. Existing `_apply_sector_caps` delegation remains at `src/omega/quant/phase35_walk_forward.py:1003-1005`.
- Dynamic cadence: FAIL. Rebalance timing can occur earlier than the updated frequency interval, as described in the blocking finding.

## Role Compliance

PASS.

- Role 21 audit-only work performed.
- No production code modified.
- No test code modified.
- Audit artifacts/state only: skill load state refreshed and this report written.
- L2 implementation remains separate from this L3 audit.

## Final Verdict

The prior PIT lookahead blocker is resolved, and the new PIT regression test is meaningful. However, the current sequential cadence has a high-severity timing bug that can rebalance earlier than the updated frequency allows. Do not approve until cadence state transition is fixed and covered by a deterministic regression test.

VERDICT: [NEEDS_FIX]
PIT Safety: PASS
Role Compliance: PASS
