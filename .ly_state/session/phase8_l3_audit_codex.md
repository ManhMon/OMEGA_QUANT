# L3 Audit — Phase 8 Label Horizon Sweep (Codex)

**Date**: 2026-05-30 14:43 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e77d5-567f-73b0-ba72-f0e66d828228`
**Rollout**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-42-10-019e77d5-*.jsonl`
**Wall time**: ~1.5 min
**Invocation**: SOUL.md Rule 9.1 (stdin pipe), audit performed BEFORE gate lock (proper SOD flow restored).

## Verdict

**[APPROVED]** — all 8 verification points PASS, only P2 cosmetic findings. Alpha confirmed REAL via falsification.

## Findings (all P2, none blocking)

1. **`backtest_v2_cpcv.py:244`** `_per_date_zscore` defined but unused. Dead code with explanatory comment. Acceptable for one cycle; either wire on prediction side or delete in future phase.

2. **Audit-context narrative nit**: task brief said "h=60 100B sign flip from negative to positive", but Phase 5 h=20 100B was actually +0.188 (barely positive). It's a **large magnitude jump**, not a sign flip. `phase8_summary.md` already states this correctly. Cosmetic only.

3. **`compute_target`** uses `s.shift(-horizon)/s - 1.0` — correct forward return: today's row gets next `horizon` bars' return. Label leaks into future not past. PIT-safe.

4. **CPCV `label_horizon` param** correctly threaded into purge logic (no embargo regression with longer horizon).

## Confirmed correct (no fix)

- **PIT/SOD invariance**: Phase 5 sanitization stack intact (winsorize 1%/99%, train-fold zscore, Ridge inner KFold, CPCV(10,2) embargo_pct=0.01 + label_horizon for purge). Only `--label-horizon` CLI flag changes between Phase 5 and Phase 8. No PIT-affecting deltas.
- **Numerical sanity h=60 @ 1B**: med_IC=0.03403, fold_SR_ann=5.548, fold_DSR=0.423, pool_SR=5.629. n_samples=39066 (vs h=20 45746, delta 6680 = ~40-bar bigger forward-dropna).
- **Capacity mechanics**: turnover 0.0395 (h=60) vs 0.0772 (h=20) → slippage at 100B drops 19.60 → 4.93 bps/bar (~4x lower). This is the mechanical reason capacity expands.
- **Falsification quality**: med_IC sign-flips (+0.0340 → -0.0661), fold_SR collapses to 12.7% of real (sign flip), pool_SR sign-flips, pos_folds 36/45 → 10/45. Same quality as Phase 5 h=20. Alpha is REAL.
- **Compare scripts** (`compare_phase8_horizons.py`, `compare_phase8_h60_capacity.py`, `compare_phase8_h60_falsification.py`): all 3 load JSONs correctly, compute fold_pos% and deltas correctly. Numbers reproduce against the JSONs.
- **SOD**: Codex read-only inspection on L2 artifacts. No `apply_patch`, no test runs, no state mutation.

## Production decision

**Switch production label horizon from h=20 to h=60.** All criteria met:
1. Alpha REAL (falsification PASS)
2. PIT-safe (no pipeline changes)
3. SR uplift across all capitals (1B/10B/100B)
4. Capacity ceiling pushed from ~50B to >100B
5. Cost halved (lower turnover from slower signal)

Phase 5 baseline (h=20) remains as fallback in code; switch is a 1-arg config change at runtime.

## Evidence chain

- `.ly_state/session/phase8_codex_audit.stdout` — codex agent_message extracted
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-42-10-*.jsonl` — full session log
- `phase8_summary.md` — implementation summary
- `phase8_h{5,60}_*.json` — backtest artifacts (5 files)
