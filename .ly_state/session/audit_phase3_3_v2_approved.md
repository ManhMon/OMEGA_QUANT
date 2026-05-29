# L3 Audit Report - Phase 3.3 v2 (Re-audit APPROVED)

Auditor: L3-Audit:Role21-Review (Codex CLI session marine-orbit)
Date: 2026-05-29 21:18 GMT+7
Pattern: 2-step (codex Step 1 STDOUT, Ly Step 2 write) - SOD v2.1 compliant
File: scripts/backtest_v2_cpcv.py (147 lines, post-fix)
Result: .ly_state/session/phase3_3_v2_full.json
Original audit: .ly_state/session/audit_phase3_3.md (NEEDS_FIX)

## VERDICT: APPROVED

All 7 audit fixes verified PASS. Math sanity check confirms DSR=0.993 consistent.

## Fixes Verified

| ID | Sev | Status | Evidence |
|----|-----|--------|----------|
| P0-1 | P0 | PASS | inner.split(X_tr) only; final fits full X_tr predicts X_te ONCE |
| P0-2 | P0 | PASS | n_trials=n_alphas=4 in DSR call |
| P1-1 | P1 | PASS | per_date_returns groupby date, demedian per date, equal-weight L/S |
| P1-2 | P1 | PASS | bar_horizon = 5 * max_per_date (= 245 in full run) |
| P1-3 | P1 | PASS | mu/sd computed on X_tr only, applied to X_te per fold |
| P2-1 | P2 | PASS | trial_srs.append(sr) no filter |
| P2-2 | P2 | PASS | DSR receives daily_rets pooled array (n_daily=11269) |

## Statistical Sanity (codex)

T=11269, daily SR=0.1216, skew=0.55, kurt=7.83, n_trials=4
sigma^2(SR) = (1 - 0.55*0.1216 + (7.83-1)/4 * 0.1216^2) / 11268 ~= 8.5e-5
sigma(SR) ~= 0.00922
z-score >> 4 -> DSR = 0.993 mathematically consistent.

## Advisory (non-blocking)

- P2-info: CPCV daily returns NOT iid (each date in multiple folds)
  Recommendation: median-fold DSR alongside pooled DSR for Phase 4
- P3-info: n_trials=4 captures only inner alpha grid; outer research DOF
  (feature top_n=125, horizon=5, universe size, alpha grid) not counted
- P3-info: embargo (574 bars) > horizon (245 bars) - safe but coincidental.
  Recommendation: assert embargo_bars >= label_horizon in cpcv.py

## Codex empirical concern

Ann SR 1.93 on 5y VN equity is aggressive vs institutional 0.5-1.5.
Possible causes:
1. Universe selection bias (Phase 1 classifier trained 2020-2024 on FUTURE data
   to select 50 from 192 - look-ahead at universe level, NOT caught by CPCV)
2. Per-date demedian creates artificial market-neutral
3. Phase 3.4 microstructure alphas may have subtle PIT violations

Required for Phase 4 production:
- Re-train universe classifier with walk-forward (2018->2019->2020 etc)
- Ablation: DSR with vs without each alpha source
- Compare against unselected VN30 baseline

## Gate Decision

l3_session_id: 019e7418-ca97-7063-9600-97a607c51553
l3_session_key: marine-orbit
audit_report_path: .ly_state/session/audit_phase3_3_v2_approved.md
final_verdict: APPROVED

Phase 3.3 production gate: APPROVED for use as baseline before Phase 4.
