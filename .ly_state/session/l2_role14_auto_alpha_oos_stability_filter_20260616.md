# L2 Implementation Report: Auto-Alpha OOS Stability Filter

**Gate ID**: `AUTO_ALPHA_OOS_STABILITY_FILTER_20260616`
**Role**: 14 (Data Scientist) — OpenCode L2 Implementation
**Date**: 2026-06-16
**Tier**: 2 (Implementation-only, test required, no self-approval, submit to Tier3)

---

## 1. Files Read - Repo-Local Skill Source Evidence

### Role Definition (Authoritative)
- `.agents/agent/data-scientist.md` — Role 14 frontmatter parsed: role_id=14, tier=2, platform=OpenCode, skills=[python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]

### Skill Files Read (All Authoritative, Repo-Local)
1. `.agents/skills/python-patterns/SKILL.md`
2. `.agents/skills/clean-code/SKILL.md`
3. `.agents/skills/testing-patterns/SKILL.md`
4. `.agents/skills/systematic-debugging/SKILL.md`
5. `.agents/skills/performance-profiling/SKILL.md`
6. `.agents/skills/quant-research/SKILL.md`
7. `.agents/skills/vietnam-market-data/SKILL.md`
8. `.agents/skills/backtesting-pit-safety/SKILL.md`
9. `.agents/skills/data-science-workflow/SKILL.md`

no authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

---

## 2. Implementation Summary

### Gate: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616

**Purpose**: PIT-safe opt-in stability filter for the auto-alpha bundle. Uses ONLY train/in-fold pre-OOS evidence to assess IC stability before allowing auto-bundle alphas into the portfolio signal. Filters alphas that lack stable train-time evidence to improve OOS transfer.

### Files Modified (Repo-Relative Paths)

| File | Changes |
|------|---------|
| `src/omega/quant/alpha/phase35.py` | Added gate ID constant, FoldMetrics field, constructor params (5 new), `_apply_oos_stability_filter` method (~200 lines), wiring into `run_fold` single-horizon path, evidence persistence |
| `scripts/run_phase35_backtest.py` | Added 4 CLI args, logging, engine constructor wiring, evidence serialization in `serialize_fold_details`, config persistence in results JSON |
| `tests/phase35/test_oos_stability_filter.py` | New test file: 28 targeted tests across 11 test classes |

### Design Decisions

1. **Opt-in/default-off**: `enable_oos_stability_filter=False` by default. No live/default behavior change.
2. **PIT-safe**: Method `_apply_oos_stability_filter` takes `train_df` only — never `test_df`. Evidence dict contains `pit_safe=True` and `no_oos_label_use=True`.
3. **Bundle-scoped**: Only filters alphas with `auto_` prefix. Non-bundle alphas pass through unchanged.
4. **Three stability metrics**:
   - **ICIR threshold**: |mean(daily IC)| / std(daily IC) >= `stability_min_icir` (default 0.15)
   - **IC sign consistency**: Fraction of sub-windows with same sign as overall IC >= `stability_min_sign_consistency` (default 0.55)
   - **IC decay penalty**: Penalizes composite score when recent-third IC opposes oldest-third IC
5. **Conservative fallback**: If all bundle alphas are excluded, re-includes all to avoid zero-signal fold.
6. **Evidence serialization**: Per-fold evidence dict with full metrics per alpha, pass/exclude verdicts, and gate configuration.

### Constructor Parameters

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `enable_oos_stability_filter` | bool | False | Master switch |
| `stability_min_icir` | float | 0.15 | Min absolute ICIR |
| `stability_min_sign_consistency` | float | 0.55 | Min sign consistency fraction |
| `stability_decay_penalty_factor` | float | 1.0 | Decay penalty multiplier |
| `stability_min_sub_windows` | int | 3 | Min sub-windows for evaluation |

---

## 3. Test Results

### Targeted Tests: 28/28 PASSED
```
tests/phase35/test_oos_stability_filter.py
  TestDefaultOff (4 tests) — engine default disabled, gate ID present, comment block, FoldMetrics field
  TestCLIWiring (7 tests) — all CLI flags present, engine wiring, config serialization, evidence serialization
  TestPITSafety (3 tests) — method signature (train_df only), evidence marks pit_safe, source inspection
  TestStableAlphaPasses (2 tests) — high ICIR passes, non-bundle passthrough
  TestUnstableAlphaExcluded (1 test) — low ICIR excluded
  TestDecayPenalty (1 test) — negative ratio penalty applied
  TestConservativeFallback (1 test) — fallback re-includes all
  TestDisabledPassthrough (2 tests) — disabled returns all, no metrics computed
  TestConstructorValidation (4 tests) — invalid types raise ValueError
  TestEvidenceStructure (2 tests) — JSON serializable, all required keys present
  TestMissingColumnPassthrough (1 test) — missing column graceful handling
```

### Regression Tests: 890/890 PASSED
Full `tests/phase35/` suite passes with zero failures. No existing behavior changed.

---

## 4. Context and Comparison

### Dynamic Universe Baseline (Current Best)
- Portfolio IC: 0.0249
- Median IC: 0.0167
- Sharpe: 3.1106
- MaxDD: -12.25%
- Avg PnL: ~616M VND

### Auto Bundle (Underperformed)
- Underperformed baseline — metrics degraded

### Winner Guard Allowlist (Research-Only, Worsened)
- IC: -0.0004
- Sharpe: 2.2783
- PnL: 444.7M VND
- Guard was protective but worsened metrics

### This Filter (12-Fold OOS Backtested 2026-06-16)
- **Backtest completed**: 12-fold CPCV with dynamic universe + formulaic v3_pruned + winner guard + auto OOS bundle + OOS stability filter
- **Result JSON**: `data/phase35_results/phase35_backtest_results_auto_stability_filter_20260616_baseline.json`
- **Summary TXT**: `data/phase35_results/phase35_backtest_summary_auto_stability_filter_20260616_baseline.txt`
- Portfolio IC: 0.0149, Sharpe: 3.0756, MaxDD: -12.11%, PnL: 609.3M VND
- **Identical to auto bundle**: Winner guard excludes all auto alphas before stability filter acts → filter is a no-op in this config
- Default off — zero impact on existing configs
- Conservative fallback prevents zero-signal folds
- **Verdict: Research-only, do NOT promote** — underperforms dynamic baseline (IC 0.0149 vs 0.0249)

---

## 5. PIT Safety Verification

| Check | Status |
|-------|--------|
| Method takes only train_df (no test_df) | VERIFIED |
| Source inspection: no test_df in method body | VERIFIED |
| Evidence: `pit_safe=True` | VERIFIED |
| Evidence: `no_oos_label_use=True` | VERIFIED |
| No OOS labels used for filtering decisions | VERIFIED |
| No current-bar data accessed | VERIFIED |
| Per-date IC computed on embargoed train data only | VERIFIED |

---

## 6. SOD Compliance

| Guardrail | Status |
|-----------|--------|
| No self-approval | COMPLIANT — submitting to Tier 3 |
| No live/default promotion | COMPLIANT — default off |
| Evidence persisted per fold | COMPLIANT — `oos_stability_filter_evidence` field |
| Tier 3 audit submission | REQUIRED — Code Reviewer (role 21) + QA Engineer (role 17) |

---

## 7. 12-Fold OOS Backtest Evidence

### CLI Executed (2026-06-16)
```bash
python scripts/run_phase35_backtest.py \
  --n-folds 12 \
  --enable-automated-oos-bundle \
  --enable-oos-stability-filter \
  --stability-min-icir 0.15 \
  --stability-min-sign-consistency 0.55 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --dynamic-universe --dynamic-universe-top-n 30 \
  --output-tag auto_stability_filter_20260616
```

### 12-Fold Results Summary

| Metric | Dynamic Baseline | Auto Bundle | WG Allowlist | **Stability Filter** |
|--------|----------------:|------------:|-------------:|---------------------:|
| Portfolio IC | 0.0249 | 0.0149 | -0.0004 | **0.0149** |
| Sharpe | 3.11 | 3.08 | 2.28 | **3.08** |
| MaxDD | -12.25% | -12.11% | -12.09% | **-12.11%** |
| PnL (VND) | 616M | 609M | 445M | **609M** |

### Per-Fold Stability Filter Activity (all 12 folds: 0 bundle alphas reached filter)

The formulaic winner guard excluded all auto-bundle alphas from the final alpha selection in every fold before the stability filter could evaluate them. The stability filter correctly reported 0 passed / 0 excluded in all 12 folds, confirming the filter is **conditionally dormant** when the winner guard is active.

### Output Artifacts
- `data/phase35_results/phase35_backtest_results_auto_stability_filter_20260616_baseline.json`
- `data/phase35_results/phase35_backtest_summary_auto_stability_filter_20260616_baseline.txt`

---

## 8. Verdict

**IMPLEMENTATION COMPLETE + 12-FOLD OOS EVIDENCE COMPLETE** — Submitted to Tier 3 for audit.

- 28/28 targeted tests PASSED
- 890/890 regression tests PASSED
- PIT-safe: VERIFIED
- Opt-in/default-off: VERIFIED
- No live/default promotion: VERIFIED
- Evidence serialization: VERIFIED
- **12-fold OOS: COMPLETED** — metrics identical to auto bundle (IC=0.0149, Sharpe=3.08)
- **Underperforms dynamic baseline** (IC=0.0249, Sharpe=3.11) — do NOT promote
- Stability filter is a no-op when formulaic winner guard is active (correct behavior)
