# L3 Audit - Phase 3.4 Tail Controls

Auditor: L3-Audit:Role21-Review (codex session sharp-crustacean, exit 0)
Date: 2026-05-29 22:14 GMT+7
Pattern: 2-step (codex Step 1 STDOUT, Ly Step 2 write)
Files: tail_controls.py, test_tail_controls.py, backtest_v2_cpcv.py
Result: phase3_4_full.json (DSR=0.996 PASS, ann SR=2.54)

## VERDICT: NEEDS_FIX

8 issues (7 P1 + 1 P2). DSR 0.996 IS OPTIMISTIC due to per-fold warmup leakage.

## P1 issues

| ID | File | Issue | Fix |
|----|------|-------|-----|
| TC-1 | tail_controls.py:46 | cap_weights doc says "renormalize when feasible" but body is bare clip | Update doc OR implement renorm |
| TC-2 | tail_controls.py:111-124 | Entry-count vs calendar windows; state reset per fold | Document non-portable state OR pass dates |
| TC-3 | tail_controls.py:120-122 | DD breaker NON-persistent (releases when peak rolls out window) | Add persistent tripped flag, release on equity >= HWM |
| TC-4 | tail_controls.py:113-122 | Feedback loop: vol-target uses post-DD-cut returns -> levers up after trip | Use unleveraged returns for vol estimation |
| TC-5 | tail_controls.py:115 | max_leverage hardcoded 3.0 inside apply_tail_controls | Lift to function arg |
| BT-1 | backtest_v2_cpcv.py:131-148 | Pivot fills missing (date,ticker) with 0 | Use df.pivot or active-name only |
| BT-2 | backtest_v2_cpcv.py:131-148 | **Per-fold warmup eats 24% of OOS at scale=1.0** -> inflates ann SR 1.36->2.54 | Concat-then-slice OR seed vol from train data |

## P2

| TC-6 | tail_controls.py:111 | Magic 60/252 hardcoded inside apply_tail_controls |
| TT-1 | test_tail_controls.py:71 | No PIT perturbation test; no DSR reproducibility check |

## Codex critical insight (NOTES)

> Tail controls on unbiased strategy normally raise risk-adjusted return MODESTLY (5-30%)
> by cutting bad-tail bars. Near-doubling ann SR (1.36 -> 2.54, +87%) is a RED FLAG.
> Most likely cause = per-fold warmup leverage + DD-breaker non-persistence jointly
> amplify favorable bars while breaker only mutes a few worst bars.
> 
> Expected ann SR after fix: 1.6-1.9 range.
> If still > 2.4 after fix, params (0.15, 0.05, 0.08, 20) are tuned to 2020-2024 sample
> (especially 2022 drawdown) and result is OVERFIT.

## Codex sensitivity grid (recommended before sign-off)

target_vol_ann in [0.10, 0.15, 0.20]
max_abs_weight in [0.03, 0.05, 0.08]
dd_threshold in [0.05, 0.08, 0.12]
dd_window in [10, 20, 40]
=> 81 cells, report DSR/SR/skew/kurt/max-DD/turnover

If (0.15, 0.05, 0.08, 20) is local max => treat as overfit.

## Codex flagged Phase 3.3 inheritance issue

CPCV pools 11277 daily_rets vs only ~1260 unique calendar days
(5y x 252) -> 9x oversampled. DSR n_trials=4 only adjusts for
alpha grid, NOT for this overlap. Pre-existing (not 3.4) but
makes DSR=0.996 optimistic.

## What was verified correct (PIT-safe)

- history.append + eq_curve.append AFTER scale decision -> no look-ahead at function boundary
- pivot construction iterates groupby date in chronological order
- recent_eq excludes to-be-realized bar (eq_curve length t+1 at iter t)

## Required fix priority

P0 (blocker): BT-2 per-fold warmup -> THIS is the primary inflation source
P0 (blocker): TC-3 DD breaker persistence -> circuit breaker semantically broken
P1 (important): TC-1, TC-2, TC-4, TC-5, BT-1
P2 (cleanup): TC-6, TT-1

## Gate decision

l3_session_id: codex-cli session sharp-crustacean
l3_session_key: sharp-crustacean
audit_report_path: .ly_state/session/audit_phase3_4.md
final_verdict: NEEDS_FIX

DO NOT use Phase 3.4 result (DSR 0.996) as production baseline yet.
Apply fixes, re-run, re-audit before proceeding to Phase 4.
