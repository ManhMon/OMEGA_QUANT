# L2 Implementation Report — Role 14 (data-scientist)

**Gate**: REGIME_ROUTING_E2E_AB_20260615
**Role**: 14 (data-scientist) — Tier 2, implementation only
**Date**: 2026-06-15
**Status**: RESEARCH_ONLY / DO_NOT_PROMOTE

---

## 1. Commands Executed

### Baseline (no regime routing)
```bash
python scripts/run_phase35_backtest.py \
  --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --output-tag regime_ab_baseline_20260615
```
**Exit code**: 0 (success)
**Output files**:
- `data/phase35_results/phase35_backtest_results_regime_ab_baseline_20260615_baseline.json`
- `data/phase35_results/phase35_backtest_summary_regime_ab_baseline_20260615_baseline.txt`

### Treatment (with regime routing)
```bash
python scripts/run_phase35_backtest.py \
  --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --enable-regime-routing \
  --output-tag regime_ab_enabled_20260615
```
**Exit code**: 0 (success)
**Output files**:
- `data/phase35_results/phase35_backtest_results_regime_ab_enabled_20260615_baseline.json`
- `data/phase35_results/phase35_backtest_summary_regime_ab_enabled_20260615_baseline.txt`

## 2. Results Summary

| Metric | Baseline | Treatment | Delta |
|--------|----------|-----------|-------|
| Avg Portfolio IC | 0.0344 | 0.0344 | **0.0000** |
| Avg Raw Signal IC | 0.0200 | 0.0200 | **0.0000** |
| Avg Raw CS IC | 0.0216 | 0.0216 | **0.0000** |
| Avg Portfolio Sharpe | 3.1570 | 3.1570 | **0.0000** |
| Avg Max Drawdown | -12.34% | -12.34% | **0.00%** |
| Positive IC Rate | 10/12 (83.3%) | 10/12 (83.3%) | **0** |
| Positive Sharpe Rate | 11/12 (91.7%) | 11/12 (91.7%) | **0** |
| Positive Return Rate | 11/12 (91.7%) | 11/12 (91.7%) | **0** |

**All 12 folds are bit-identical between baseline and treatment.**

## 3. Routing Evidence

| Aggregate | Value |
|-----------|-------|
| Total test dates | 80,726 |
| Routed dates | 29,213 (36.2%) |
| Fallback dates | 51,513 (63.8%) |
| Folds at 100% fallback | 3 (folds 3, 4, 11) |
| PIT-safe | YES |

## 4. analyze_alpha_weakness.py Compatibility

NOT compatible — file naming pattern `^(baseline|ra_guard|ra_no_guard)_.*backtest_results_.*\.json$` does not match output files. Comparison computed directly from JSON.

## 5. Research Verdict

**FAIL — NO IMPACT**

- Zero delta on all aggregate and per-fold metrics
- Regime routing is PIT-safe but produces no measurable alpha
- High fallback rate (63.8%) indicates limited regime discriminative power
- **RESEARCH_ONLY / DO_NOT_PROMOTE** — do not enable as default behavior

## 6. Tier 3 Audit Submission

This report and all artifacts are submitted to:
- **Code Reviewer (role 21)**: Code quality and reproducibility review
- **QA Engineer (role 17)**: Model validation and testing review

**Cannot proceed until**: All relevant Tier 3 roles return [APPROVED].

## 7. Source Compliance

**Repo-local files read (authoritative)**:
- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

**Forbidden path scan**: `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.
