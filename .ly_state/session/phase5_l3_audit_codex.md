# L3 Audit — Phase 5 Data Sanitization (Codex 2-step retroactive)

**Date**: 2026-05-30 14:08 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e77b0-8fed-7c41-a02c-fc84c3f8ae9b`
**Rollout**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-02-00-019e77b0-*.jsonl`
**Wall time**: ~6 min, multi-file read + cross-check.
**Invocation**: SOUL.md Rule 9.1 (stdin pipe).
**Replaces**: prior Python audit `phase5_audit_python.stdout` (codex stuck during initial Phase 5 audit).

## Verdict

**[APPROVED]** — 8 verification points PASS. 1 P1 docstring claim corrected, 2 P2 cosmetic deferred.

## Findings

### P1 — Fixed in follow-up commit

1. **`scripts/backtest_v2_cpcv.py:47-49`**: `sanitize_ohlcv` docstring claimed "outlier bounds are per-symbol expanding-style statistics, not per-date", but canonical `DataSanitizer.fit/apply` uses full-sample groupby mean/std (`packages/data/src/omega/data/sanitizer.py:108-130` -> `_clip_outliers_fitted` at 369-412). Legacy expanding path (`_clip_outliers`, lines 325-367) is NOT used by fit/apply. In-slice scope preserved (single backtest universe), but full panel for `load_panel_walk_forward` spans `year_start-1 .. year_end` so cleaning of an early date can technically see later in-slice statistics. Bounded but not strict per-date.
   **STATUS**: Docstring updated to reflect actual behavior ("BOUNDED to backtest slice, NOT strict per-date") with explicit guidance to switch to legacy expanding path for live paper-trading.

### P2 — Deferred (cosmetic)

2. **`backtest_v2_cpcv.py:442-448`** bare `try/except: pass` around winsorize block silently swallows errors. Suggest `logger.warning("winsorize skipped: %s", exc)` instead of silent pass.

3. **`backtest_v2_cpcv.py:27-30`** AlphaSanitizer imported but never invoked. Phase 5 summary documents this as intentional placeholder. Either wire (per-fold replacement of inline numpy winsorize+zscore) or remove dead import.

### Confirmed correct (no fix)

- **mask_suspended drops volume==0 BEFORE ADV** (load_panel:146-149, load_panel_walk_forward:179-187): suspended bars never enter ADV.
- **DataSanitizer.as_of_time=max(panel.date)**: `_enforce_pit_safety` raises if None, clamps `as_of <= available_at(=date+1d)`.
- **Re-attach ticker after .apply**: lines 62-74 build `ticker_map` from `_orig_idx` and reattach. Robust to canonical sanitizer dropping symbol col.
- **Counter logging**: lines 76-79 log full breakdown.
- **Cleaning order in BOTH load functions**: mask_suspended → sanitize_ohlcv → _attach_adv → in-fold year filter.
- **universe_year_map preserves (ticker, date) → year tagging across sanitize dedup**: `max(get(key,0), year)` correctly assigns owner year to surviving row from `dedup keep='first'`. Final filter `date.year == _universe_year` keeps only in-fold rows.
- **Per-fold winsorize 1%/99%**: `np.nanpercentile(X_tr, axis=0)` train-only, `np.clip(X_tr/X_te, lo, hi)` BEFORE z-score. Strictly PIT.
- **z-score mu/sd train-only**: lines 449-453, sd_floor=1e-12 (existing P1-3 path preserved).
- **AlphaSanitizer NOT called**: only import exists, no .fit/.apply. Acknowledged placeholder.
- **Numerical sanity 1B**: median_test_ic=0.01729 (~0.0173), n_samples=45746, n_folds=45, fold_SR_ann=3.6715. Matches Phase 5 summary.
- **Cost monotone with capital**: 1B 2.49 / 10B 4.04 / 100B 19.60 bps/bar.
- **No NaN in cost_breakdown / fold_dsr** across 1B/10B/100B JSONs.
- **SOD**: L3 (Codex) reading L2 (OpenCode) artifacts; no file writes; STDOUT-only. Writer ≠ Reviewer. No self-approval.

## Disposition

**Phase 5 gate APPROVED** with codex audit (replacing prior Python-only audit).
- P1 docstring fixed.
- P2 cosmetic deferred (not blocking production).

## Evidence chain

- `.ly_state/session/phase5_codex_audit_v2.stdout` — codex agent_message extracted
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-02-00-*.jsonl` — full session log
- Original Python audit: `.ly_state/session/phase5_audit_python.stdout` (kept as supplementary evidence)
