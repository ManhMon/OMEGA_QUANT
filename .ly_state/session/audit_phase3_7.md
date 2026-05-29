# L3 Audit - Phase 3.7 Signal Cadence

Auditor: L3-Audit:Role21-Review (codex session mellow-bison, exit 0)
Date: 2026-05-30 04:03 GMT+7
Pattern: 2-step (codex Step 1 STDOUT, Ly Step 2 write)

## VERDICT: NEEDS_FIX (PENDING_AUDIT)

Cannot APPROVE: ann SR 3.20 with DSR 0.048 = strategy not statistically
significant after multiple-testing correction. Codex flags 3 leakage
hypotheses ranked by probability.

## P0 issues (blockers)

### P0-1: DSR=0.048 contradicts SR=3.20 narrative
- DSR < 0.05 means: after multiple-testing correction, strategy is
  STATISTICALLY INDISTINGUISHABLE FROM LUCK
- Reporting SR 3.20 without flagging this is misleading
- Per Bailey-LdP 2014: any single-trial SR > 2 with DSR < 0.95 should
  NOT be treated as significant
- FIX: gate APPROVAL on DSR >= 0.95 (not SR alone). Recompute DSR with
  CORRECT n_trials counting full research history (h grid, EMA span grid,
  feature variants). Currently n_trials=4 only counts inner ridge alpha.

### P0-2: EMA cross-fold state leakage
- ewm.groupby(ticker) after sort(ticker, date) carries state from one
  test block into a LATER disjoint test block
- Different fold-models produce different predictions; smoothing across
  fold seams violates fold isolation
- FIX: groupby (ticker, fold_id) so EMA resets at each test-block start
- Verification: EMA at first row of each contiguous segment == raw pred

## P1 issues (important)

### P1-1: Embargo < label_horizon in row units
- embargo = 1% * N = 616 rows
- bar_horizon = 20 days * 50 max_per_date = 1000 rows
- AFML CPCV: embargo MUST be >= horizon to remove serial-correlation leak
- FIX: embargo_rows = max(ceil(0.01*N), bar_horizon). Re-run.
  Expected: SR drops if leakage was source

### P1-2: EMA semantics not pinned
- adjust=False is set (good - causal)
- min_periods unspecified (defaults to 1) - early-bar SNR inflated
- FIX: pin min_periods=span, drop first (span-1) rows of each test block

### P1-3: pos roundtrip relies on stable sort
- pandas sort_values not guaranteed stable across (ticker, date) ties
- FIX: kind='mergesort' explicit + assert pos monotonic increasing post-restore

### P1-4: Cost model omits slippage (fee-only floor)
- 1.66 bps/bar = 30 bps roundtrip * 5.5% turnover (matches numerically)
- VN HoSE mid/small-caps: 10-40 bps additional slippage at >1% ADV
- FIX: pass daily_adv, apply sqrt(participation) impact
  Expected SR haircut: 0.5-1.0

## P2 issues (cleanup)

- P2-1: bar_horizon assumes max_per_date = cross-section width. Add assertion log.
- P2-2: kurt 8.2 with skew +0.37: fat tails. Report Sortino + Calmar + worst 1%.
- P2-3: EMA span=5 picked after seeing span=5 buggy=-2.66, fixed=+3.20.
  Researcher DOF inflation. FIX: pre-register span grid, fold pick into DSR n_trials.

## Notes (codex critical assessment)

- Statistical plausibility: ann SR 3.20 net of fees on daily VN long/short
  is at 99th percentile of published results
- Renaissance Medallion gross ~2.0-2.5 across hundreds of uncorrelated
  strategies; SINGLE-MODEL strategy at 3.20 net is prima facie LEAKAGE
- Literature: Harvey-Liu 2015 + Bailey-LdP 2014 require DSR >= 0.95 to claim significance
- Median fold SR 0.24 per-bar = 3.81 ann if extrapolated; 3.20 headline
  is fold-mean phenomenon - check fold dispersion before claiming

## Codex artifact ranking (most -> least likely)

1. EMA cross-fold leakage (P0-2) - easiest to falsify
2. Researcher DOF in (h, span) grid not in DSR (P0-1)
3. Embargo < horizon (P1-1)
4. Optimistic cost model (P1-4)
5. Real alpha - LAST hypothesis after above ruled out

## Recommended falsification protocol

(a) y-shuffle test: randomize labels, re-run full pipeline INCLUDING EMA.
    Expected: ann SR collapse to ~0 with DSR ~ 0.5.
    If NOT collapse -> leakage CONFIRMED.

(b) EMA-reset-per-fold: groupby (ticker, fold_id).
    Expected drop: 0.5-1.5 SR.

(c) Embargo bump to 1000 rows.
    Expected drop: 0.2-0.5 SR.

If all three pass and DSR still >= 0.95 -> approve.
If DSR < 0.95 after fixes -> strategy is NOT viable as claimed.

## Gate decision

l3_session_id: codex session mellow-bison (019e758b-ebe0-7fb3-afe3-615247ecd73e)
l3_session_key: mellow-bison
audit_report_path: .ly_state/session/audit_phase3_7.md
final_verdict: NEEDS_FIX -> PENDING_AUDIT

DO NOT use Phase 3.7 ann SR 3.20 as production claim until falsification
protocol passes and DSR >= 0.95.
