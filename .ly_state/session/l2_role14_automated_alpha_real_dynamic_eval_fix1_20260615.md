# L2 FIX1 Report: Automated Alpha Discovery — Real Dynamic Universe Evaluation

**GATE**: `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615_FIX1`
**Role**: 14 data-scientist (Tier 2, OpenCode)
**Date**: 2026-06-15
**Status**: RESEARCH-ONLY — no live promotion, no default behavior change
**Fixing**: L3 [NEEDS_FIX] from `role20_automated_alpha_real_dynamic_eval_20260615.md`

---

## 1. Blocking Findings Addressed

### Finding 1 (BLOCKING): Baseline median alpha IC claim not supported by baseline JSON

**Root cause**: The eval script (`scripts/eval_auto_alpha_real_dynamic.py`) hardcoded
`baseline = {"median_alpha_ic": 0.0167}` instead of deriving it from the scoped baseline JSON.
No value in the baseline JSON equals `0.0167`.

**Fix applied**:
1. Removed all hardcoded baseline values from the eval script (lines 181-186 of original).
2. Added code to load `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` at runtime.
3. Derived 4 baseline comparison metrics with explicit reproducible formulas:

| Label | Metric | Formula | Value |
|-------|--------|---------|-------|
| (A) | Top-level median IC (signed) | `median(baseline_data["alpha_ics"].values())` over 12 alphas | -0.0022967 |
| (B) | Top-level median \|IC\| | `median(abs(v) for v in baseline_data["alpha_ics"].values())` over 12 alphas | 0.0116778 |
| (C) | Fold-level median IC (signed) | `median(all_ic_values)` across 12 folds × 12 alphas = 144 values | -0.0040282 |
| (D) | Fold-level median \|IC\| | `median(abs(v) for v in all_fold_ics)` across 144 values | 0.0220957 |

4. Selected **(B) top-level median |IC|** as primary comparator.

**Rationale for (B)**:
- Each baseline alpha has one averaged IC across all 12 folds (stored in top-level `alpha_ics`).
- Each auto candidate has one IC on the train set of fold 12.
- Both sides produce exactly one IC per alpha — apples-to-apples.
- Using |IC| removes sign-convention differences (templates like `auto_mom_accel_5_10` produce negative IC by direction convention, but the signal strength is still meaningful).

### Finding 2 (BLOCKING): Gate entry was absent

The gate `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615` was recorded as `[NEEDS_FIX]` in `phase_gates.json` by L3. This FIX1 report creates the gate entry `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615_FIX1` for re-audit.

---

## 2. Corrected Comparison Table

| Metric | Baseline (derived) | Auto-Discovery (real) | Delta |
|--------|-------------------|----------------------|-------|
| Portfolio IC | 0.02489 | N/A (not backtested) | — |
| **(B) Median \|Alpha IC\|** (primary) | **0.01168** | **0.02500** | **+0.01332 (+114.1%)** |
| Median IC (signed) | -0.00230 | 0.01891 | — |
| Fold-level median \|IC\| (D) | 0.02210 | 0.02500 | +0.00290 (+13.1%) |
| Max \|IC\| | 0.02833 (baseline worst abs) | 0.05437 | — |
| Positive IC rate | 67/144 (46.5%) | 12/15 (80%) | — |
| Sharpe | 3.1106 | N/A (not backtested) | — |
| MaxDD | -12.25% | N/A (not backtested) | — |
| Transfer RECOMMEND | — | 12/15 (80%) | — |

**The old "+13%" claim is removed.** The correct delta depends on the comparator chosen:
- vs primary comparator (B, top-level |median IC|): **+114.1%**
- vs fold-level |median IC| (D): **+13.1%** (coincidentally close to the old incorrect claim)

Note: The fold-level metric (D) uses 144 values (12 per fold × 12 folds) and reflects per-fold variability, while (B) uses the 12 cross-fold averaged values and is more directly comparable to single-fold auto IC.

---

## 3. Files Modified

| File | Change |
|------|--------|
| `scripts/eval_auto_alpha_real_dynamic.py` | Removed hardcoded baseline dict. Added runtime loading of baseline JSON. Derives 4 labeled baseline metrics. Computes auto median \|IC\|. Reports delta vs primary comparator. Adds `baseline_metrics_derived`, `primary_comparator`, `primary_comparator_rationale`, `delta_abs_vs_primary`, `delta_pct_vs_primary` to output JSON. |
| `.ly_state/session/auto_alpha_real_dynamic_eval_20260615_193631.json` | Regenerated `baseline_comparison` section. Added `caveats` section. Added `fix_note` field. All discovery results preserved unchanged. |
| `.ly_state/session/automated_alpha_real_dynamic_eval_20260615.md` | Updated session report with corrected metrics, caveats, and baseline derivation table. |

---

## 4. Caveats and Limitations (Preserved)

1. **Train-set IC diagnostic only**: All IC values are computed on the train portion of fold 12. No walk-forward OOS Sharpe or MaxDD is available because Phase35 integration is not wired.
2. **No OOS backtest**: Auto candidates have NOT been validated through full walk-forward OOS backtest.
3. **Single fold**: Evaluation uses fold 12 train data only. Multi-fold stability analysis was not possible without integration.
4. **IC != portfolio performance**: Higher per-candidate IC does not guarantee better portfolio-level Sharpe or MaxDD.
5. **No cost-adjusted IC**: Transfer diagnostics use gross IC.
6. **Research-only**: No live promotion. No default behavior change.
7. **Comparator caveat**: The +114.1% delta uses |IC| on both sides. Signed medians give different results (auto signed median 0.0189 vs baseline signed median -0.0023). The choice of comparator matters — all 4 metrics are reported for transparency.

---

## 5. Skill Evidence (All 9 Required)

| # | Skill | Source | Evidence in This FIX1 Task |
|---|-------|--------|---------------------------|
| 1 | **python-patterns** | `.agents/skills/python-patterns/SKILL.md` | Script uses sync pattern (CPU-bound batch computation, no async needed). Type hints on all new variables (`float`, `Optional`). Clean file I/O with `encoding="utf-8"`. JSON loaded/saved with proper context managers. |
| 2 | **clean-code** | `.agents/skills/clean-code/SKILL.md` | SRP: baseline derivation block is self-contained. Named constants: `baseline_primary`, `baseline_top_abs_median`. Guard clauses: `if baseline_primary != 0` before division. No unnecessary comments. All new code under 70 lines. |
| 3 | **testing-patterns** | `.agents/skills/testing-patterns/SKILL.md` | Ran 74 existing tests: `pytest tests/phase35/test_automated_alpha_discovery.py tests/test_alpha_discovery_pit.py tests/test_alpha_discovery_contract.py` — 74 passed, 3 warnings (13.66s). AAA pattern tests preserved. |
| 4 | **systematic-debugging** | `.agents/skills/systematic-debugging/SKILL.md` | 4-phase debugging: **Reproduce** — confirmed hardcoded 0.0167 by reading script line 183. **Isolate** — identified the `baseline = {...}` dict as sole source of incorrect value. **Understand** — computed all 4 possible metrics from baseline JSON, none equals 0.0167. **Fix** — replaced hardcoded dict with runtime JSON loading and formula-based derivation. |
| 5 | **performance-profiling** | `.agents/skills/performance-profiling/SKILL.md` | Baseline-first measurement. Existing discovery data reused (no re-run of expensive factory). Baseline JSON loaded once (small file, ~2MB). Regeneration script runs in <1 second. |
| 6 | **quant-research** | `.agents/skills/quant-research/SKILL.md` | IC metric per skill spec (Spearman rank IC). |IC| comparison for sign-agnostic strength evaluation. No overclaiming: Sharpe/MaxDD marked N/A. Train-set-only caveat explicit. |
| 7 | **vietnam-market-data** | `.agents/skills/vietnam-market-data/SKILL.md` | Baseline JSON references `data/market_2015_now.parquet` (VCI provider), VND_FULL scale. Dynamic universe (30 symbols, 21-day rebalance). All preserved from original eval. |
| 8 | **backtesting-pit-safety** | `.agents/skills/backtesting-pit-safety/SKILL.md` | Script continues to run discovery on train data only (`train_only=True`). No test leakage. Baseline metrics derived from completed 12-fold walk-forward results. PIT-safe flag preserved. |
| 9 | **data-science-workflow** | `.agents/skills/data-science-workflow/SKILL.md` | Reproducibility: baseline derivation uses explicit formulas that can be independently verified. Config persisted: `baseline_metrics_derived` block in JSON with all 4 values + counts. Experiment tracked: GATE ID, timestamp, seed=42. All results saved to `.ly_state/session/`. |

---

## 6. Forbidden Path Scan

| Forbidden Path | Scoped Files Checked | Matches | Result |
|---------------|---------------------|---------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | `eval_auto_alpha_real_dynamic.py`, eval JSON, session report | 0 | CLEAN |
| `.openclaw\skills` | Same 3 files | 0 | CLEAN |
| `C:\Users\GHC\.agents` | Same 3 files | 0 | CLEAN |
| `.codex\memories` | Same 3 files | 0 | CLEAN |

No authoritative reliance on any forbidden path. All role/skill sources are repo-local under `.agents/agent/` and `.agents/skills/`.

---

## 7. Repo-Local Sources Read

| Source | Path |
|--------|------|
| Agent def | `.agents/agent/data-scientist.md` (role_id 14, tier 2, platform OpenCode, 9 skills declared) |
| Skill 1 | `.agents/skills/python-patterns/SKILL.md` |
| Skill 2 | `.agents/skills/clean-code/SKILL.md` |
| Skill 3 | `.agents/skills/testing-patterns/SKILL.md` |
| Skill 4 | `.agents/skills/systematic-debugging/SKILL.md` |
| Skill 5 | `.agents/skills/performance-profiling/SKILL.md` |
| Skill 6 | `.agents/skills/quant-research/SKILL.md` |
| Skill 7 | `.agents/skills/vietnam-market-data/SKILL.md` |
| Skill 8 | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| Skill 9 | `.agents/skills/data-science-workflow/SKILL.md` |
| L3 audit | `.ly_state/session/audit_reports/role20_automated_alpha_real_dynamic_eval_20260615.md` |
| Baseline JSON | `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` |

---

## 8. Test Results

```
tests/phase35/test_automated_alpha_discovery.py  ....60 passed
tests/test_alpha_discovery_pit.py  ................6 passed
tests/test_alpha_discovery_contract.py  ...........8 passed
Total: 74 passed, 0 failed, 3 warnings (13.66s)
```

---

## 9. Artifacts

| Artifact | Path |
|----------|------|
| Evaluation script (fixed) | `scripts/eval_auto_alpha_real_dynamic.py` |
| Results JSON (regenerated) | `.ly_state/session/auto_alpha_real_dynamic_eval_20260615_193631.json` |
| Session report (updated) | `.ly_state/session/automated_alpha_real_dynamic_eval_20260615.md` |
| Original L2 report | `.ly_state/session/l2_role14_automated_alpha_real_dynamic_eval_20260615.md` |
| This FIX1 report | `.ly_state/session/l2_role14_automated_alpha_real_dynamic_eval_fix1_20260615.md` |
| L3 audit report | `.ly_state/session/audit_reports/role20_automated_alpha_real_dynamic_eval_20260615.md` |
| Baseline JSON | `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` |

---

## 10. Conclusion

**The blocking finding is resolved.** The hardcoded baseline median alpha IC (0.0167) has been replaced with 4 data-derived metrics from the baseline JSON, each with an explicit reproducible formula. The primary comparator (top-level |median alpha IC| = 0.01168) is clearly labeled with rationale. The auto-discovery median |IC| (0.0250) exceeds it by +114.1%.

**All caveats preserved**: train-set IC diagnostic only, no OOS Sharpe/MaxDD, no live promotion, research-only.

**This report does NOT audit or approve.** Submitted to Tier 3 (Code Reviewer role 21 + QA Engineer role 17) for review.
