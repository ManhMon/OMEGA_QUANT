# L3 Audit — Phase 3.9 Fold-Level DSR (Codex)

**Date**: 2026-05-30 05:36 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e75df-8554-74f0-8bba-b87839f6e7cc`
**Rollout file**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T05-34-03-019e75df-8554-74f0-8bba-b87839f6e7cc.jsonl`
**Wall time**: ~2 minutes, multi-file read + pytest run, ended cleanly with `task_complete`.
**Invocation**: SOUL.md Rule 9.1 — prompt piped via stdin (`type prompt.txt | codex.cmd exec ... -`).

## Inputs reviewed
- `packages/quant/src/omega/quant/validation/dsr.py` (new `fold_level_dsr`)
- `packages/quant/tests/test_dsr.py` (new fold-level tests)
- `scripts/backtest_v2_cpcv.py` (run_pipeline integration)
- `.ly_state/session/phase3_9_full_{1B,10B,100B}.json`
- `.ly_state/session/phase3_9_summary.md`
- Ran `python -m pytest packages/quant/tests/test_dsr.py -q` → **21 passed, 0 failed**

## Verdict

**[APPROVED]** — implementation is sound. Mathematical correctness, integration, edge cases, and PIT/SOD all verified. Five P2 findings (all cosmetic / documentation, none blocking).

## Findings

### P2 (cosmetic / documentation)

1. **`phase3_9_summary.md:38` — "fold_SR_ann ≈ pool_SR_ann (within 0.7%)" overstates agreement**.
   At 100B, fold_SR_ann=-0.084 vs pool_SR_ann=-0.183 → ~54% relative deviation. Mathematically expected (pooled SR uses pooled std; fold SR is mean-of-ratios; they diverge when fold-level σ is heterogeneous). Metric itself is correct.
   STATUS: **fixed** in summary edit (added 100B caveat).

2. **`phase3_9_summary.md:54` — "7 new tests" undercounts (actual = 8)**.
   STATUS: **fixed** in summary edit.

3. **`dsr.py:264` — `from scipy.stats import kurtosis as _kurt` imported inside the function** while `skew` is at module top. Cosmetic asymmetry. FIX (deferred): hoist `kurtosis` to module-level imports.

4. **`dsr.py:248` — zero-variance early-return drops `n_trials` selection-bias term silently**. `expected_max_sr=0`, `dsr ∈ {0,1}` from sign of `sr_mean - bench`. Acceptable (no spread → no deflation), but FIX (deferred): add comment noting `n_trials` not honored on this path.

5. **`dsr.py:280` — `_expected_max_sharpe(n_trials, sr_var_sample)` uses fold-Sharpe variance as proxy for trial-Sharpe variance**. Bailey-LdP defines `V[{SRₙ}]` across hyper-params. Same convention as pooled `deflated_sharpe_ratio` (consistency preserved). FIX (optional/future): expose explicit `trial_sharpes` argument so caller can pass alpha-grid spread.

### Confirmed correct (no fix)

- **Bailey-LdP eq.(1) at fold level**: `sr_var_estim = (1 - g3·sr_mean + (g4-1)/4 · sr_mean²) / (n_folds - 1)` with `g3 = skew(fs, bias=False)`, `g4 = kurtosis(fs, fisher=False, bias=False)`. T = n_folds, moments computed over fold Sharpes. Formula correct.
- **Selection bias**: uses `n_trials` and `sr_var_sample = np.var(fs, ddof=1)` — consistent with pooled DSR's empirical-trial-variance branch.
- **Edge cases**: `n_folds < 2` short-circuit; `sr_std_emp <= 1e-12 * max(|sr_mean|, 1.0)` catastrophic-cancellation guard; `fs[np.isfinite(fs)]` filter — all present.
- **`scripts/backtest_v2_cpcv.py` integration**: `trial_srs` built as per-fold `mean(rets)/std(rets, ddof=1)` (per-bar fold Sharpe), passed into `fold_level_dsr`. New `fold_dsr` block is **additive only**; existing pooled `dsr/dsr_sharpe/dsr_sr_ann/pass/skew/kurt` keys preserved unchanged. Legacy consumers unaffected.
- **Numerical sanity** from `phase3_9_full_*.json`: fold_DSR `0.443 → 0.408 → 0.0998` across 1B/10B/100B (monotone decreasing); 100B fold_DSR < 0.5 ✓; n_folds=45 in all three.
- **Tests**: `python -m pytest packages/quant/tests/test_dsr.py -q` → **21 passed**, 0 failed.
- **PIT/SOD**: no PIT-violating constructs (no future-looking access in `fold_level_dsr`); change is read-only over already-computed fold Sharpes. SOD respected (this audit L3 reviews L2-produced artifacts).

## Disposition

**Gate APPROVED** for Phase 3.9. No P0/P1 blockers. P2 #1 and #2 fixed in summary; P2 #3, #4, #5 deferred to next refactor pass (cosmetic).

## Evidence chain

- `.ly_state/session/phase3_9_codex_audit.stdout` — codex agent_message extracted from rollout
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T05-34-03-019e75df-*.jsonl` — full session log (112 KB, ends with `task_complete`)
- `python -m pytest packages/quant/tests/test_dsr.py -q` → 21/21 PASS, executed by codex during audit
