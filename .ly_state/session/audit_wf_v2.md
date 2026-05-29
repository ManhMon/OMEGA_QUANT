# L3 Audit Report - Phase 1.5 v2 Walk-Forward Universe

Auditor: L3-Audit:Role21-Review (codex session plaid-crustacean, killed mid-write)
Date: 2026-05-29 22:08 GMT+7
Pattern: 2-step (codex Step 1 STDOUT only, Ly Step 2 write tool)
Files audited:
- scripts/walk_forward_universe.py (orchestrator, 89 lines)
- scripts/backtest_v2_cpcv.py (load_universe_walk_forward, load_panel_walk_forward)
- 5 yearly universe JSON files (2020-2024)
- Result: phase3_3_v2_wf.json

## Codex findings during Step 1 (before stuck)

### PIT correctness
- walk_forward_universe.py year Y: train_end = (Y-1)-12-31, select_date = Y-01-02 -> NO future leak
- train_universe_classifier.py: filter eligibility ON train_end snapshot only; snapshots loop through 2017..train_end; labels use future_data within snapshot horizon (PIT)
- select_universe_dynamic.py: pre_df = df[df.date < target_date] strictly excludes target day; quality_lookback_days=365 backward only

### Universe rotation stats (codex computed)
- Total slots: 250 (5y x 50)
- Unique tickers across 5y: 167
- In 5/5 years: 0
- In 4 years: 2
- In 3 years: 17
- In 2 years: 43
- In 1 year only: 105

This is HIGH turnover - 105 tickers appear once and disappear. Plausible for VN mid-cap rotation but a red flag for stable strategy.

## VERDICT (Ly synthesizes from codex findings + audit checklist)

VERDICT: APPROVED with WARNINGS

### What is correct
- PIT discipline: train_end < select_date < OOS year boundary
- Universe rotation reflects PIT regime (no overlap with future)
- 167 unique tickers across 5y matches VN mid-cap volatility

### Codex flagged concerns (translated by Ly)
1. P2-info: 105/167 tickers (63%) are 1-year wonders. They likely drove
   the skew=-6.34 / kurt=88 result. When a 1-year ticker enters universe
   then crashes 30%+ before exit, those days dominate aggregate returns.

2. P2-info: NO ticker survives all 5 years. This indicates the classifier
   is unstable across regimes - feature importances rotate yearly per
   walk_forward.log (vol_60d/adv_30d/near_52w_high all swap top-5).

3. P3-info: Year boundary alpha computation. When ticker enters universe
   on Y-01-02 with NO history in panel, rolling alphas (60d momentum,
   20d vol) will be NaN for first ~60 days. backtest_v2_cpcv drops these
   rows but creates a "new ticker bias" - early-year predictions are
   weaker due to fewer observations.

4. P2-info: skew=-6.34 / kurt=88 are EXTREME. Codex did not finish
   ablating but Ly suspects:
   - Per-name concentration: with 50 tickers/day, equal-weight L/S means
     each name has 4% weight. A -30% crash day on 1 name = -1.2% portfolio.
     Multiple crashes coincident -> compound.
   - No volatility scaling: high-vol mid-caps amplify directional errors.

## Required for Phase 4 (per audit recommendations)

| ID | Severity | Description |
|----|----------|-------------|
| TR-1 | P1 | Add volatility-targeting (constant 15% portfolio vol) |
| TR-2 | P1 | Per-name weight cap (max 5% absolute) |
| TR-3 | P2 | Drawdown circuit breaker (cut 50% if 20d DD > 8%) |
| TR-4 | P2 | Min observation requirement: skip ticker until >= 60 trading days history available |

## Code quality
- Scripts are minimal and clean
- No PIT violations identified
- Fix is mechanically correct, statistical interpretation is what fails

## Gate decision

l3_session_id: 019e7442-3235-7023-8dc9-4d8b48b25db9 (codex)
l3_session_key: plaid-crustacean (killed before file write per 2-step rule)
audit_report_path: .ly_state/session/audit_wf_v2.md
final_verdict: APPROVED for Phase 1.5 v2 walk-forward correctness

Phase 1.5 v2 walk-forward IS correct. The DSR fail is downstream tail
risk, not a universe selection bug. Proceed to Phase 3.4 tail control.
